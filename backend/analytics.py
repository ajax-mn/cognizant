"""Cache analytics endpoints — all data sourced from Redis."""

import json

from fastapi import APIRouter

from cache_validator import redis_client, get_cache_stats
from models import (
    CacheAnalyticsResponse,
    TopCachedQuery,
)

router = APIRouter(prefix="/analytics", tags=["cache-analytics"])


def _scan_redis_cache(connection_id: str | None = None) -> list[dict]:
    """Scans Redis for all cached query entries, optionally filtered by connection_id.

    Returns a list of parsed cache payloads (dicts) from Redis.
    """
    safe_conn_id = (connection_id and connection_id.strip()) or "default"
    pattern = f"sql_cache:{safe_conn_id}:*"
    entries = []

    try:
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
            for key in keys:
                raw = redis_client.get(key)
                if raw:
                    try:
                        entries.append(json.loads(raw))
                    except (json.JSONDecodeError, TypeError):
                        continue
            if cursor == 0:
                break
    except Exception as e:
        print(f"[Redis] Error scanning cache keys: {e}")

    return entries


def _get_top_cached_queries(entries: list[dict], limit: int = 10) -> list[TopCachedQuery]:
    """Sorts Redis cache entries by hit_count descending and returns the top N as TopCachedQuery models."""
    sorted_entries = sorted(entries, key=lambda e: e.get("hit_count", 0), reverse=True)
    return [
        TopCachedQuery(
            question=entry.get("question", ""),
            sql=entry.get("sql", ""),
            hit_count=entry.get("hit_count", 0),
            cost_saved=round(entry.get("hit_count", 0) * entry.get("cost", 0.0), 6),
        )
        for entry in sorted_entries[:limit]
    ]


@router.get("", response_model=CacheAnalyticsResponse)
@router.get("/cache", response_model=CacheAnalyticsResponse)
def cache_analytics(
    is_default: bool | None = None,
    connection_id: str | None = None,
    schema_hash: str | None = None,
):
    """Returns cache analytics sourced entirely from Redis.

    - Cache entries (total cached, top queries, SQL) from Redis key scan
    - Hit/miss/invalidation counters from Redis hash counters
    """
    is_dynamic = bool(
        (is_default is False)
        or (connection_id and connection_id.strip())
        or (schema_hash and schema_hash.strip())
    )

    # Determine which connection scope to query
    scope_conn_id = connection_id if is_dynamic else None

    # Scan Redis for live cache entries
    redis_entries = _scan_redis_cache(connection_id=scope_conn_id)
    total_queries_cached = len(redis_entries)
    top_cached_queries = _get_top_cached_queries(redis_entries)

    # Read analytics counters from Redis
    stats = get_cache_stats(connection_id=scope_conn_id)
    total_hits = stats["hits"]
    total_misses = stats["misses"]
    total_invalidations = stats["invalidations"]
    total_cost_saved = stats["cost_saved"]

    denominator = total_hits + total_misses + total_invalidations
    hit_rate = round(total_hits / denominator, 4) if denominator else 0.0

    return CacheAnalyticsResponse(
        total_queries_cached=total_queries_cached,
        total_cache_hits=total_hits,
        total_cache_misses=total_misses,
        total_invalidations=total_invalidations,
        hit_rate=hit_rate,
        total_cost_saved=round(total_cost_saved, 6),
        top_cached_queries=top_cached_queries,
    )
