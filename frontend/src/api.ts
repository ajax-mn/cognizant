export type CacheStatus = "hit" | "miss" | "regenerated_schema_changed" | "n/a";

export interface QueryResponse {
  question: string;
  sql: string;
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  source: "template" | "llm";
  from_cache: boolean;
  cache_status: CacheStatus;
  schema_hash: string | null;
  execution_time_ms: number;
  api_tokens_used: number;
  api_cost: number;
  api_cost_saved: number;
}

export interface UploadDatabaseResponse {
  connection_id: string;
  filename: string;
}

export interface TopCachedQuery {
  question: string;
  hit_count: number;
  cost_saved: number;
  last_used_at: string | null;
}

export interface CacheAnalyticsResponse {
  total_queries_cached: number;
  total_cache_hits: number;
  total_cache_misses: number;
  total_invalidations: number;
  hit_rate: number;
  total_cost_saved: number;
  top_cached_queries: TopCachedQuery[];
}

export interface CacheInvalidationEvent {
  question: string;
  reason: string | null;
  old_schema_hash: string | null;
  new_schema_hash: string | null;
  created_at: string | null;
}

export interface CacheInvalidationsResponse {
  invalidations: CacheInvalidationEvent[];
}

export interface SchemaColumn {
  name: string;
  type: string;
}

export interface SchemaResponse {
  tables: Record<string, SchemaColumn[]>;
}

const BASE_URL = import.meta.env.VITE_API_URL || "/api";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore parse errors, fall back to statusText
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function fetchSchema(connectionId?: string | null): Promise<SchemaResponse> {
  const query = connectionId ? `?connection_id=${encodeURIComponent(connectionId)}` : "";
  const res = await fetch(`${BASE_URL}/schema${query}`);
  return handleResponse<SchemaResponse>(res);
}

export interface ChatMessage {
  role: string;
  content: string;
}

export async function runQuery(
  question: string,
  connectionId?: string | null,
  previousSql?: string | null,
  conversationHistory?: ChatMessage[] | null
): Promise<QueryResponse> {
  const res = await fetch(`${BASE_URL}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      connection_id: connectionId ?? null,
      previous_sql: previousSql ?? null,
      conversation_history: conversationHistory ?? null,
    }),
  });
  return handleResponse<QueryResponse>(res);
}

export async function uploadDatabase(file: File): Promise<UploadDatabaseResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${BASE_URL}/database/upload`, {
    method: "POST",
    body: formData,
  });
  return handleResponse<UploadDatabaseResponse>(res);
}

export async function removeUploadedDatabase(connectionId: string): Promise<void> {
  await fetch(`${BASE_URL}/database/${encodeURIComponent(connectionId)}`, {
    method: "DELETE",
  });
}

export async function fetchCacheAnalytics(): Promise<CacheAnalyticsResponse> {
  const res = await fetch(`${BASE_URL}/analytics/cache`);
  return handleResponse<CacheAnalyticsResponse>(res);
}

export async function fetchCacheInvalidations(): Promise<CacheInvalidationsResponse> {
  const res = await fetch(`${BASE_URL}/analytics/cache-invalidations`);
  return handleResponse<CacheInvalidationsResponse>(res);
}
