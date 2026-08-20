import os
import socket

# Monkeypatch socket.getaddrinfo to bypass local DNS resolution timeouts if requested
if os.getenv("BYPASS_DNS_TIMEOUTS", "false").lower() == "true":
    _orig_getaddrinfo = socket.getaddrinfo

    def custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if host == "generativelanguage.googleapis.com":
            return _orig_getaddrinfo("172.217.117.4", port, family, type, proto, flags)
        elif host == "ep-wispy-sun-axuj92z8-pooler.c-4.us-east-2.aws.neon.tech":
            return _orig_getaddrinfo("18.226.241.3", port, family, type, proto, flags)
        return _orig_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = custom_getaddrinfo

import time

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import cache_validator
import db_connections
import schema_hasher
from analytics import router as analytics_router
from database import get_db_session, get_engine
from db_connections import InvalidDatabaseFileError
from db_models import Base, CacheAuditLog, QueryCache
from models import ExecuteSQLRequest, QueryRequest, QueryResponse, UploadDatabaseResponse
from schema_introspection import format_schema_for_context, get_database_schema
from sql_generator import generate_sql_from_question
from sql_templates import try_template_match
from sql_validator import is_write_query, validate_sql

app = FastAPI(title="Text-to-SQL Analytics API")
app.include_router(analytics_router)

# Create the query cache tables on startup if they don't already exist.
Base.metadata.create_all(bind=get_engine())

ENABLE_QUERY_CACHE = os.getenv("ENABLE_QUERY_CACHE", "true").lower() == "true"
CACHE_INVALIDATION_ON_SCHEMA_CHANGE = (
    os.getenv("CACHE_INVALIDATION_ON_SCHEMA_CHANGE", "true").lower() == "true"
)
GEMINI_PRICE_PER_TOKEN = float(
    os.getenv("GEMINI_PRICE_PER_TOKEN", os.getenv("HAIKU_PRICE_PER_TOKEN", "0.000000375"))
)

allowed_origins_str = os.getenv("ALLOWED_ORIGINS")
allowed_origins = [origin.strip().rstrip("/") for origin in allowed_origins_str.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run_select(sql: str, engine: Engine) -> tuple[list[str], list[dict]]:
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
    return columns, rows


def _run_write(sql: str, engine: Engine) -> int:
    """Execute a write/DDL statement and return the number of affected rows."""
    with engine.begin() as conn:
        result = conn.execute(text(sql))
        return result.rowcount if result.rowcount and result.rowcount >= 0 else 0


def _resolve_engine(connection_id: str | None) -> Engine:
    """Default DATABASE_URL engine, unless an uploaded DB connection_id is given."""
    try:
        return db_connections.get_engine_for_connection(connection_id, get_engine())
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown connection_id: {connection_id}")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/schema")
def schema(connection_id: str | None = None):
    try:
        engine = _resolve_engine(connection_id)
        tables = get_database_schema(engine)
        return {"tables": tables}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/database/upload", response_model=UploadDatabaseResponse)
async def upload_database(file: UploadFile):
    file_bytes = await file.read()
    try:
        connection = db_connections.register_uploaded_db(file_bytes, file.filename or "uploaded.db")
    except InvalidDatabaseFileError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return UploadDatabaseResponse(connection_id=connection.connection_id, filename=connection.filename)


@app.delete("/database/{connection_id}")
def remove_uploaded_database(connection_id: str):
    db_connections.remove_connection(connection_id)
    return {"status": "removed"}


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, db: Session = Depends(get_db_session)):
    engine = _resolve_engine(request.connection_id)
    start_time = time.perf_counter()

    from_cache = False
    cache_status = "n/a"
    schema_hash = None
    tokens_used = 0
    api_cost = 0.0
    api_cost_saved = 0.0
    source = "template"
    sql = None
    cached_entry = None
    schema_changed_invalidation = False
    # Scoped by connection_id so an uploaded DB never shares cache entries
    # with the default database (or with a different upload).
    question_hash = cache_validator.compute_question_hash(request.question, request.connection_id)

    # 1. Try the cache first (only ever populated by LLM-generated queries).
    if ENABLE_QUERY_CACHE:
        existing_entry = db.query(QueryCache).filter_by(question_hash=question_hash).first()
        if existing_entry is not None:
            valid, current_hash = cache_validator.is_cache_valid(existing_entry, engine)
            if valid:
                cached_entry = existing_entry
                sql = existing_entry.generated_sql
                source = "llm"
                from_cache = True
                cache_status = "hit"
                schema_hash = current_hash
                api_cost_saved = existing_entry.api_cost
                # execution time is recorded below, once the query actually runs.
            elif CACHE_INVALIDATION_ON_SCHEMA_CHANGE:
                cache_validator.invalidate_cache_entry(
                    question_hash, db, reason="schema_changed", new_schema_hash=current_hash
                )
                schema_changed_invalidation = True

    # 2. No valid cache entry: try the deterministic template match, then the LLM.
    if sql is None:
        try:
            tables = get_database_schema(engine)
            schema_context = format_schema_for_context(tables)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read schema: {e}")

        sql = try_template_match(request.question, tables)
        source = "template"

        if sql is None:
            try:
                sql, tokens_used = generate_sql_from_question(request.question, schema_context)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"SQL generation failed: {e}")
            source = "llm"

            try:
                schema_hash = schema_hasher.get_schema_hash_for_query(sql, engine)
            except Exception:
                schema_hash = None

            api_cost = round(tokens_used * GEMINI_PRICE_PER_TOKEN, 6)
            cache_status = "regenerated_schema_changed" if schema_changed_invalidation else "miss"

            if ENABLE_QUERY_CACHE and schema_hash is not None:
                cache_validator.update_cache_entry(
                    question=request.question,
                    question_hash=question_hash,
                    new_sql=sql,
                    new_hash=schema_hash,
                    tokens_used=tokens_used,
                    api_cost=api_cost,
                    db_session=db,
                    cache_status=cache_status,
                )

    # If the generated query is a write / DDL statement, either execute it
    # (when allow_write is on) or return a preview.
    if is_write_query(sql):
        if not request.allow_write:
            return QueryResponse(
                question=request.question,
                sql=sql,
                columns=[],
                rows=[],
                row_count=0,
                source=source,
                is_preview=True,
            )

        # Write mode is ON — execute the statement.
        try:
            affected = _run_write(sql, engine)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Write query failed: {e} | SQL: {sql}")

        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        return QueryResponse(
            question=request.question,
            sql=sql,
            columns=["affected_rows"],
            rows=[{"affected_rows": affected}],
            row_count=1,
            source=source,
            is_preview=False,
            execution_time_ms=execution_time_ms,
            api_tokens_used=tokens_used,
            api_cost=api_cost,
        )

    try:
        validate_sql(sql)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Generated SQL rejected: {e} | SQL: {sql}")

    try:
        columns, rows = _run_select(sql, engine)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query execution failed: {e} | SQL: {sql}")

    execution_time_ms = int((time.perf_counter() - start_time) * 1000)

    if from_cache:
        cache_validator.record_cache_hit(cached_entry, db, execution_time_ms)
    elif source == "llm":
        db.add(
            CacheAuditLog(
                question=request.question,
                cache_status=cache_status,
                reason="schema_changed" if cache_status == "regenerated_schema_changed" else None,
                old_schema_hash=None,
                new_schema_hash=schema_hash,
                query_execution_time_ms=execution_time_ms,
                api_tokens_used=tokens_used,
                api_cost_saved=0.0,
                user_id="demo_user",
            )
        )
        db.commit()

    return QueryResponse(
        question=request.question,
        sql=sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        source=source,
        from_cache=from_cache,
        cache_status=cache_status,
        schema_hash=schema_hash,
        execution_time_ms=execution_time_ms,
        api_tokens_used=tokens_used,
        api_cost=api_cost,
        api_cost_saved=api_cost_saved,
    )


@app.post("/execute-sql")
def execute_sql(request: ExecuteSQLRequest):
    try:
        validate_sql(request.sql)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    engine = _resolve_engine(request.connection_id)

    try:
        columns, rows = _run_select(request.sql, engine)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query execution failed: {e}")

    return {"sql": request.sql, "columns": columns, "rows": rows, "row_count": len(rows)}
