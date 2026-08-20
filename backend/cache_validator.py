"""Validates, invalidates, and updates cached SQL queries using Redis for speed and PostgreSQL for Audit Logging.

A cached query is shared globally across all users for maximum cache hits and cost savings.
A cached query is considered valid only if the schema hash of the tables it
references is unchanged since it was cached. Pure data changes never
invalidate the cache; only structural schema changes do.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone

from dotenv import load_dotenv
import redis
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from db_models import CacheAuditLog, DynamicQueryCache, QueryCache
import schema_hasher

# Load environment variables from backend/.env
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path, override=True)

# Initialize Redis client (supports REDIS_URL or separate host/port/password + SSL for Upstash)
REDIS_URL = os.getenv("REDIS_URL")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_SSL = os.getenv("REDIS_SSL", "").lower() == "true" or "upstash.io" in REDIS_HOST.lower()

if REDIS_URL:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
else:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD if REDIS_PASSWORD else None,
        ssl=REDIS_SSL,
        decode_responses=True,
    )

# Time-to-Live for cache entries (7 days)
CACHE_TTL_SECONDS = 60 * 60 * 24 * 7


def normalize_question(question: str) -> str:
    """Normalizes whitespace, lowercases, and strips surrounding punctuation to maximize cache hits."""
    q = question.strip().lower()
    q = re.sub(r"[^\w\s]", "", q)
    q = re.sub(r"\s+", " ", q)
    return q


def compute_question_hash(
    question: str,
    connection_id: str | None = None,
) -> str:
    """Normalize and hash a question scoped to the database connection (global shared cache)."""
    normalized = normalize_question(question)
    connection_scope = (connection_id and connection_id.strip()) or "default"
    value = f"{connection_scope}::{normalized}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def get_redis_key(
    connection_id: str | None,
    question_hash: str,
) -> str:
    """Creates a shared Redis key scoped to the database connection."""
    safe_conn_id = (connection_id and connection_id.strip()) or "default"
    return f"sql_cache:{safe_conn_id}:{question_hash}"


def check_redis_cache(
    question: str,
    connection_id: str | None,
    engine: Engine,
    db_session: Session,
) -> dict | None:
    """Checks Redis for a valid cached query in the shared global cache.
    Automatically invalidates if the schema changed and records the invalidation in the PostgreSQL Audit Log.
    """
    question_hash = compute_question_hash(question, connection_id)
    cache_key = get_redis_key(connection_id, question_hash)

    try:
        cached_data_str = redis_client.get(cache_key)
    except Exception as e:
        print(f"[Redis] Error reading cache: {e}")
        return None

    if not cached_data_str:
        return None  # Cache Miss

    try:
        cached_data = json.loads(cached_data_str)
    except Exception:
        return None

    # Check if the database schema has changed since this query was cached
    try:
        current_schema_hash = schema_hasher.get_schema_hash_for_query(
            cached_data.get("sql", ""), engine
        )
    except Exception:
        current_schema_hash = None

    if (
        current_schema_hash is None
        or cached_data.get("schema_hash") != current_schema_hash
    ):
        # Schema changed (e.g. table renamed, column dropped/modified) -> Invalidate key!
        try:
            redis_client.delete(cache_key)
        except Exception as e:
            print(f"[Redis] Error deleting stale key: {e}")

        # Delete database model entries if present
        if connection_id:
            db_session.query(DynamicQueryCache).filter_by(question_hash=question_hash).delete()
        else:
            db_session.query(QueryCache).filter_by(question_hash=question_hash).delete()

        # Log the invalidation to PostgreSQL for audit & analytics
        db_session.add(
            CacheAuditLog(
                question=question,
                connection_id=connection_id,
                cache_status="invalidated",
                reason="schema_changed",
                old_schema_hash=cached_data.get("schema_hash"),
                new_schema_hash=current_schema_hash,
                query_execution_time_ms=0,
                api_tokens_used=0,
                api_cost_saved=0.0,
                user_id="shared_user",
            )
        )
        db_session.commit()
        return None

    # Schema is still valid, return the cached payload
    return cached_data


def update_redis_cache(
    question: str,
    connection_id: str | None,
    sql: str,
    engine: Engine,
    tokens_used: int,
    api_cost: float,
    db_session: Session | None = None,
) -> None:
    """Saves the newly generated SQL and the current schema hash to Redis in the global shared cache."""
    question_hash = compute_question_hash(question, connection_id)
    cache_key = get_redis_key(connection_id, question_hash)

    try:
        current_schema_hash = schema_hasher.get_schema_hash_for_query(sql, engine)
    except Exception:
        current_schema_hash = "unknown"

    payload = {
        "sql": sql,
        "schema_hash": current_schema_hash,
        "tokens_used": tokens_used,
        "cost": api_cost,
        "question": question,
        "connection_id": connection_id,
    }

    try:
        # Store in Redis with TTL (7 days)
        redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(payload))
    except Exception as e:
        print(f"[Redis] Error writing to cache: {e}")

    # Synchronize with PostgreSQL database models for analytics visibility
    if db_session is not None:
        now = datetime.now(timezone.utc)
        if connection_id:
            entry = (
                db_session.query(DynamicQueryCache)
                .filter_by(question_hash=question_hash)
                .first()
            )
            if entry is None:
                entry = DynamicQueryCache(
                    connection_id=connection_id,
                    question=question,
                    question_hash=question_hash,
                    generated_sql=sql,
                    schema_hash_at_cache_time=current_schema_hash,
                    api_tokens_used=tokens_used,
                    api_cost=api_cost,
                    hit_count=0,
                    cache_status="miss",
                    last_used_at=now,
                )
                db_session.add(entry)
            else:
                entry.generated_sql = sql
                entry.schema_hash_at_cache_time = current_schema_hash
                entry.api_tokens_used = tokens_used
                entry.api_cost = api_cost
                entry.last_used_at = now
        else:
            entry = (
                db_session.query(QueryCache)
                .filter_by(question_hash=question_hash)
                .first()
            )
            if entry is None:
                entry = QueryCache(
                    question=question,
                    question_hash=question_hash,
                    generated_sql=sql,
                    schema_hash_at_cache_time=current_schema_hash,
                    api_tokens_used=tokens_used,
                    api_cost=api_cost,
                    hit_count=0,
                    cache_status="miss",
                    last_used_at=now,
                )
                db_session.add(entry)
            else:
                entry.generated_sql = sql
                entry.schema_hash_at_cache_time = current_schema_hash
                entry.api_tokens_used = tokens_used
                entry.api_cost = api_cost
                entry.last_used_at = now

        db_session.commit()


def record_cache_hit(
    question: str,
    cached_data: dict,
    db_session: Session,
    execution_time_ms: int,
    connection_id: str | None = None,
) -> None:
    """Records a successful cache hit in the PostgreSQL Audit Log."""
    question_hash = compute_question_hash(question, connection_id)
    now = datetime.now(timezone.utc)

    # Increment hit count on DB cache model for analytics
    if connection_id:
        entry = db_session.query(DynamicQueryCache).filter_by(question_hash=question_hash).first()
        if entry:
            entry.hit_count += 1
            entry.cache_status = "hit"
            entry.last_used_at = now
    else:
        entry = db_session.query(QueryCache).filter_by(question_hash=question_hash).first()
        if entry:
            entry.hit_count += 1
            entry.cache_status = "hit"
            entry.last_used_at = now

    db_session.add(
        CacheAuditLog(
            question=question,
            connection_id=connection_id,
            cache_status="hit",
            reason=None,
            old_schema_hash=None,
            new_schema_hash=cached_data.get("schema_hash"),
            query_execution_time_ms=execution_time_ms,
            api_tokens_used=0,
            api_cost_saved=cached_data.get("cost", 0.0),
            user_id="shared_user",
        )
    )
    db_session.commit()


def record_cache_miss(
    question: str,
    db_session: Session,
    execution_time_ms: int,
    tokens_used: int,
    schema_hash: str | None,
    cache_status: str = "miss",
    connection_id: str | None = None,
) -> None:
    """Logs a cache miss or regenerated event in CacheAuditLog."""
    db_session.add(
        CacheAuditLog(
            question=question,
            connection_id=connection_id,
            cache_status=cache_status,
            reason="schema_changed" if cache_status == "regenerated_schema_changed" else None,
            old_schema_hash=None,
            new_schema_hash=schema_hash,
            query_execution_time_ms=execution_time_ms,
            api_tokens_used=tokens_used,
            api_cost_saved=0.0,
            user_id="shared_user",
        )
    )
    db_session.commit()
