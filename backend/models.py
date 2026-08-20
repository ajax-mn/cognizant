from datetime import datetime
from typing import Any

from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str
    connection_id: str | None = None  # targets an uploaded DB instead of the default DATABASE_URL
    previous_sql: str | None = None
    conversation_history: list[dict[str, str]] | None = None


class QueryResponse(BaseModel):
    question: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    source: str  # "template" or "llm"

    # Query cache metadata
    from_cache: bool = False
    cache_status: str = "miss"  # "hit" | "miss" | "regenerated_schema_changed" | "n/a"
    schema_hash: str | None = None
    execution_time_ms: int = 0
    api_tokens_used: int = 0
    api_cost: float = 0.0
    api_cost_saved: float = 0.0


class ExecuteSQLRequest(BaseModel):
    sql: str
    connection_id: str | None = None


class UploadDatabaseResponse(BaseModel):
    connection_id: str
    filename: str


class ErrorResponse(BaseModel):
    detail: str


class TopCachedQuery(BaseModel):
    question: str
    hit_count: int
    cost_saved: float
    last_used_at: datetime | None


class CacheAnalyticsResponse(BaseModel):
    total_queries_cached: int
    total_cache_hits: int
    total_cache_misses: int
    total_invalidations: int
    hit_rate: float
    total_cost_saved: float
    top_cached_queries: list[TopCachedQuery]


class CacheInvalidationEvent(BaseModel):
    question: str
    reason: str | None
    old_schema_hash: str | None
    new_schema_hash: str | None
    created_at: datetime | None


class CacheInvalidationsResponse(BaseModel):
    invalidations: list[CacheInvalidationEvent]
