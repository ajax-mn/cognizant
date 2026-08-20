"""Validates, invalidates, and updates cached SQL queries using Redis.

A cached query is shared globally across all users for maximum cache hits and cost savings.
A cached query is considered valid only if the schema hash of the tables it
references is unchanged since it was cached. Pure data changes never
invalidate the cache; only structural schema changes do.
"""

import hashlib
import json
import os
import re

import redis
from sqlalchemy.engine import Engine

import schema_hasher

# Initialize Redis client (configurable via environment variables)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD if REDIS_PASSWORD else None,
    decode_responses=True,
)

# Time-to-Live for cache entries (7 days)
CACHE_TTL_SECONDS = 60 * 60 * 24 * 7


def _stats_key(connection_id: str | None) -> str:
    """Returns the Redis hash key for cache analytics counters."""
    safe_conn_id = (connection_id and connection_id.strip()) or "default"
    return f"cache_stats:{safe_conn_id}"


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
) -> dict | None:
    """Checks Redis for a valid cached query in the shared global cache.
    Automatically invalidates if the schema changed and increments the invalidation counter.
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

        # Increment invalidation counter in Redis
        try:
            redis_client.hincrby(_stats_key(connection_id), "invalidations", 1)
        except Exception:
            pass

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
        "hit_count": 0,
    }

    try:
        # Store in Redis with TTL (7 days)
        redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(payload))
    except Exception as e:
        print(f"[Redis] Error writing to cache: {e}")


def record_cache_hit(
    question: str,
    cached_data: dict,
    execution_time_ms: int,
    connection_id: str | None = None,
) -> None:
    """Records a successful cache hit entirely in Redis."""
    question_hash = compute_question_hash(question, connection_id)
    cache_key = get_redis_key(connection_id, question_hash)
    stats_key = _stats_key(connection_id)

    # Increment hit count in the cached payload
    try:
        cached_str = redis_client.get(cache_key)
        if cached_str:
            payload = json.loads(cached_str)
            payload["hit_count"] = payload.get("hit_count", 0) + 1
            remaining_ttl = redis_client.ttl(cache_key)
            if remaining_ttl and remaining_ttl > 0:
                redis_client.setex(cache_key, remaining_ttl, json.dumps(payload))
            else:
                redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(payload))
    except Exception as e:
        print(f"[Redis] Error incrementing hit count: {e}")

    # Increment global analytics counters
    try:
        redis_client.hincrby(stats_key, "hits", 1)
        cost_saved = cached_data.get("cost", 0.0)
        redis_client.hincrbyfloat(stats_key, "cost_saved", cost_saved)
    except Exception as e:
        print(f"[Redis] Error updating stats: {e}")


def record_cache_miss(
    question: str,
    execution_time_ms: int,
    tokens_used: int,
    schema_hash: str | None,
    cache_status: str = "miss",
    connection_id: str | None = None,
) -> None:
    """Records a cache miss in Redis analytics counters."""
    try:
        redis_client.hincrby(_stats_key(connection_id), "misses", 1)
    except Exception as e:
        print(f"[Redis] Error recording miss: {e}")


def get_cache_stats(connection_id: str | None = None) -> dict:
    """Returns the analytics counters (hits, misses, invalidations, cost_saved) from Redis."""
    try:
        stats = redis_client.hgetall(_stats_key(connection_id))
    except Exception:
        stats = {}

    return {
        "hits": int(stats.get("hits", 0)),
        "misses": int(stats.get("misses", 0)),
        "invalidations": int(stats.get("invalidations", 0)),
        "cost_saved": float(stats.get("cost_saved", 0.0)),
    }
