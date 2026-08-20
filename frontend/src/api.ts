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
  is_preview: boolean; // true = write/DDL query generated but NOT executed
  fallback_notice?: string | null;
  model_used?: string | null;
}

export interface UploadDatabaseResponse {
  connection_id: string;
  filename: string;
}

export interface TopCachedQuery {
  question: string;
  sql: string;
  hit_count: number;
  cost_saved: number;
}

export interface CacheAnalyticsResponse {
  total_queries_cached: number;
  total_cache_hits: number;
  total_cache_misses: number;
  hit_rate: number;
  total_cost_saved: number;
  top_cached_queries: TopCachedQuery[];
}

export interface SchemaColumn {
  name: string;
  type: string;
  primary_key?: boolean;
  is_foreign_key?: boolean;
  nullable?: boolean;
}

export interface SchemaRelationship {
  id?: string;
  source_table: string;
  source_column: string;
  target_table: string;
  target_column: string;
  constraint_name?: string | null;
}

export interface SchemaResponse {
  tables: Record<string, SchemaColumn[]>;
  relationships?: SchemaRelationship[];
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

export async function runQuery(
  question: string,
  connectionId?: string | null,
  allowWrite: boolean = false,
  onStatus?: (status: string) => void
): Promise<QueryResponse> {
  const res = await fetch(`${BASE_URL}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      connection_id: connectionId ?? null,
      allow_write: allowWrite,
    }),
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore parse error
    }
    throw new Error(detail);
  }

  const reader = res.body?.getReader();
  if (!reader) {
    return res.json();
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let queryResult: QueryResponse | null = null;
  let errorDetail: string | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const item = JSON.parse(line);
        if (item.type === "status") {
          if (onStatus) onStatus(item.message || "Switching to the Local Model!");
        } else if (item.type === "result") {
          queryResult = item.data;
        } else if (item.type === "error") {
          errorDetail = item.detail || "An error occurred during query generation.";
        }
      } catch {
        // partial line or parse error
      }
    }
  }

  if (buffer.trim()) {
    try {
      const item = JSON.parse(buffer);
      if (item.type === "result") {
        queryResult = item.data;
      } else if (item.type === "error") {
        errorDetail = item.detail;
      }
    } catch {
      // ignore
    }
  }

  if (errorDetail) {
    throw new Error(errorDetail);
  }

  if (queryResult) {
    return queryResult;
  }

  throw new Error("No response received from server.");
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

export interface FetchCacheAnalyticsOptions {
  isDefault?: boolean;
  connectionId?: string | null;
  schemaHash?: string | null;
}

export async function fetchCacheAnalytics(
  options?: FetchCacheAnalyticsOptions
): Promise<CacheAnalyticsResponse> {
  const params = new URLSearchParams();
  if (options?.isDefault !== undefined) {
    params.set("is_default", String(options.isDefault));
  }
  if (options?.connectionId) {
    params.set("connection_id", options.connectionId);
  }
  if (options?.schemaHash) {
    params.set("schema_hash", options.schemaHash);
  }
  const queryString = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`${BASE_URL}/analytics/cache${queryString}`);
  return handleResponse<CacheAnalyticsResponse>(res);
}

