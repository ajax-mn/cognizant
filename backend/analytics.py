"""Cache analytics endpoints: hit rate, cost saved, top cached queries, invalidations scoped to the active database context."""

  
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db_session
from db_models import CacheAuditLog, DynamicQueryCache, QueryCache
from models import (
    CacheAnalyticsResponse,
    CacheInvalidationEvent,
    CacheInvalidationsResponse,
    TopCachedQuery,
)

router = APIRouter(prefix="/analytics", tags=["cache-analytics"])


@router.get("", response_model=CacheAnalyticsResponse)
@router.get("/cache", response_model=CacheAnalyticsResponse)
def cache_analytics(
    is_default: bool | None = None,
    connection_id: str | None = None,
    schema_hash: str | None = None,
    db: Session = Depends(get_db_session),
):
    """Returns context-aware cache analytics for the currently active database.

    - If is_default is True or (connection_id is None and schema_hash is None):
      Fetches aggregates and top queries ONLY from the default PostgreSQL database (query_cache).
    - If it's an uploaded DB (connection_id or schema_hash provided, or is_default=False):
      Fetches aggregates and top queries ONLY from dynamic_query_cache for that connection/schema.
    """
    is_dynamic = bool(
        (is_default is False)
        or (connection_id and connection_id.strip())
        or (schema_hash and schema_hash.strip())
    )

    if is_dynamic:
        # 1. Filter dynamic_query_cache
        dynamic_query = db.query(DynamicQueryCache)
        if connection_id and connection_id.strip():
            dynamic_query = dynamic_query.filter(DynamicQueryCache.connection_id == connection_id.strip())
        elif schema_hash and schema_hash.strip():
            dynamic_query = dynamic_query.filter(
                (DynamicQueryCache.schema_hash_at_cache_time == schema_hash.strip())
                | (DynamicQueryCache.schema_hash == schema_hash.strip())
            )

        total_queries_cached = dynamic_query.count()
        top_entries = (
            dynamic_query.order_by(DynamicQueryCache.hit_count.desc())
            .limit(10)
            .all()
        )

        # 2. Filter CacheAuditLog for dynamic db
        if connection_id and connection_id.strip():
            audit_filter = (CacheAuditLog.connection_id == connection_id.strip())
        elif schema_hash and schema_hash.strip():
            audit_filter = (CacheAuditLog.new_schema_hash == schema_hash.strip())
        else:
            audit_filter = (CacheAuditLog.connection_id.isnot(None))

        total_hits = (
            db.query(CacheAuditLog)
            .filter(audit_filter, CacheAuditLog.cache_status == "hit")
            .count()
        )
        total_misses = (
            db.query(CacheAuditLog)
            .filter(audit_filter, CacheAuditLog.cache_status == "miss")
            .count()
        )
        total_invalidations = (
            db.query(CacheAuditLog)
            .filter(
                audit_filter,
                CacheAuditLog.cache_status.in_(["invalidated", "regenerated_schema_changed"]),
            )
            .count()
        )
        total_cost_saved = (
            db.query(func.coalesce(func.sum(CacheAuditLog.api_cost_saved), 0.0))
            .filter(audit_filter, CacheAuditLog.cache_status == "hit")
            .scalar()
            or 0.0
        )

    else:
        # Default database (PostgreSQL configured DATABASE_URL)
        total_queries_cached = db.query(QueryCache).count()
        top_entries = (
            db.query(QueryCache)
            .order_by(QueryCache.hit_count.desc())
            .limit(10)
            .all()
        )

        # In CacheAuditLog, default DB queries have connection_id as NULL or empty
        audit_filter = (CacheAuditLog.connection_id.is_(None)) | (CacheAuditLog.connection_id == "")

        total_hits = (
            db.query(CacheAuditLog)
            .filter(audit_filter, CacheAuditLog.cache_status == "hit")
            .count()
        )
        total_misses = (
            db.query(CacheAuditLog)
            .filter(audit_filter, CacheAuditLog.cache_status == "miss")
            .count()
        )
        total_invalidations = (
            db.query(CacheAuditLog)
            .filter(
                audit_filter,
                CacheAuditLog.cache_status.in_(["invalidated", "regenerated_schema_changed"]),
            )
            .count()
        )
        total_cost_saved = (
            db.query(func.coalesce(func.sum(CacheAuditLog.api_cost_saved), 0.0))
            .filter(audit_filter, CacheAuditLog.cache_status == "hit")
            .scalar()
            or 0.0
        )

    denominator = total_hits + total_misses + total_invalidations
    hit_rate = round(total_hits / denominator, 4) if denominator else 0.0

    top_cached_queries = [
        TopCachedQuery(
            question=entry.question or getattr(entry, "user_question", "") or "",
            hit_count=entry.hit_count,
            cost_saved=round(entry.hit_count * (entry.api_cost or 0.0), 6),
            last_used_at=entry.last_used_at,
        )
        for entry in top_entries
    ]

    return CacheAnalyticsResponse(
        total_queries_cached=total_queries_cached,
        total_cache_hits=total_hits,
        total_cache_misses=total_misses,
        total_invalidations=total_invalidations,
        hit_rate=hit_rate,
        total_cost_saved=round(total_cost_saved, 6),
        top_cached_queries=top_cached_queries,
    )


@router.get("/cache-invalidations", response_model=CacheInvalidationsResponse)
def cache_invalidations(
    is_default: bool | None = None,
    connection_id: str | None = None,
    schema_hash: str | None = None,
    db: Session = Depends(get_db_session),
):
    """Returns recent cache invalidation events scoped to the active database context."""
    is_dynamic = bool(
        (is_default is False)
        or (connection_id and connection_id.strip())
        or (schema_hash and schema_hash.strip())
    )

    if is_dynamic:
        if connection_id and connection_id.strip():
            audit_filter = (CacheAuditLog.connection_id == connection_id.strip())
        elif schema_hash and schema_hash.strip():
            audit_filter = (CacheAuditLog.new_schema_hash == schema_hash.strip())
        else:
            audit_filter = (CacheAuditLog.connection_id.isnot(None))
    else:
        audit_filter = (CacheAuditLog.connection_id.is_(None)) | (CacheAuditLog.connection_id == "")

    events = (
        db.query(CacheAuditLog)
        .filter(
            audit_filter,
            (CacheAuditLog.cache_status.in_(["invalidated", "regenerated_schema_changed"]))
            | (CacheAuditLog.reason.isnot(None)),
        )
        .order_by(CacheAuditLog.created_at.desc())
        .limit(50)
        .all()
    )
    return CacheInvalidationsResponse(
        invalidations=[
            CacheInvalidationEvent(
                question=event.question,
                reason=event.reason,
                old_schema_hash=event.old_schema_hash,
                new_schema_hash=event.new_schema_hash,
                created_at=event.created_at,
            )
            for event in events
        ]
    )
