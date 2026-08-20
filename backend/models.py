from datetime import datetime
from typing import Any

from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str
    connection_id: str | None = None  # targets an uploaded DB instead of the default DATABASE_URL
    allow_write: bool = False  # when True, write/DDL queries are executed on the database
    user_id: str | None = None  # user identifier for isolated Redis cache space


class QueryResponse(BaseModel):
    question: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    source: str  # "template" or "llm"
    is_preview: bool = False  # True when query was generated but NOT executed (write/DDL)

    # Query cache metadata
    from_cache: bool = False
    cache_status: str = "miss"  # "hit" | "miss" | "regenerated_schema_changed" | "n/a"
    schema_hash: str | None = None
    execution_time_ms: int = 0
    api_tokens_used: int = 0
    api_cost: float = 0.0
    api_cost_saved: float = 0.0

    # Standardized metadata flags for frontend components
    is_cached: bool = False
    generation_time_ms: int = 0
    cost_saved: float = 0.0
    fallback_notice: str | None = None
    model_used: str | None = None


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
    sql: str = ""
    hit_count: int
    cost_saved: float



class CacheAnalyticsResponse(BaseModel):
    total_queries_cached: int
    total_cache_hits: int
    total_cache_misses: int
    total_invalidations: int
    hit_rate: float
    total_cost_saved: float
    top_cached_queries: list[TopCachedQuery]

