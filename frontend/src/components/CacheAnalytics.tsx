import { useEffect, useState } from "react";
import {
  fetchCacheAnalytics,
  type CacheAnalyticsResponse,
} from "../api";



function MetricCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div className="rounded-md border border-neutral-200 bg-white px-4 py-3 shadow-2xs">
      <p className="text-[11px] font-medium uppercase tracking-wide text-neutral-500">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${accent}`}>{value}</p>
    </div>
  );
}

export interface CacheAnalyticsProps {
  activeConnection?: {
    connectionId: string;
    filename: string;
  } | null;
  isDefault?: boolean;
}

export function CacheAnalytics({ activeConnection, isDefault }: CacheAnalyticsProps) {
  const [analytics, setAnalytics] = useState<CacheAnalyticsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const isDefaultDb = isDefault !== undefined ? isDefault : !activeConnection;
  const connectionId = activeConnection?.connectionId ?? null;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    function load() {
      Promise.all([
        fetchCacheAnalytics({ isDefault: isDefaultDb, connectionId }),
      ])
        .then(([a]) => {
          if (!cancelled) {
            setAnalytics(a);
            setError(null);
            setLoading(false);
          }
        })
        .catch((err: Error) => {
          if (!cancelled) {
            setError(err.message);
            setLoading(false);
          }
        });
    }

    load();
    const interval = setInterval(load, 30_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [connectionId, isDefaultDb]);

  if (error) {
    return (
      <div className="rounded-md border border-neutral-200 bg-white p-4 text-sm text-neutral-700">
        <p className="font-semibold text-neutral-800">Failed to load cache analytics</p>
        <p className="mt-1 text-xs text-neutral-500">{error}</p>
      </div>
    );
  }

  if (loading && !analytics) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center text-sm text-neutral-400">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-neutral-300 border-t-neutral-600 mb-3" />
        <p>Loading cache analytics for active database…</p>
      </div>
    );
  }

  if (!analytics) {
    return null;
  }

  const total =
    analytics.total_cache_hits + analytics.total_cache_misses;

  return (
    <div className="flex flex-col gap-6">
      {/* Active Database Context Banner */}
      <div className="flex items-center justify-between rounded-lg border border-neutral-200 bg-white px-4 py-3">
        <div className="flex items-center gap-2.5">
          <div className={`h-2.5 w-2.5 rounded-full ${isDefaultDb ? "bg-blue-500" : "bg-emerald-500"}`} />
          <div>
            <span className="text-xs font-semibold text-neutral-900">
              {isDefaultDb
                ? "Default Database"
                : `Uploaded Database (${activeConnection?.filename ?? "SQLite"})`}
            </span>
            <p className="text-[11px] text-neutral-500">
              {isDefaultDb
                ? "Displaying cache analytics for the configured database"
                : `Displaying isolated cache data for connection ID: ${connectionId?.slice(0, 12)}…`}
            </p>
          </div>
        </div>
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium ${isDefaultDb
              ? "bg-blue-50 text-blue-700 border border-blue-200"
              : "bg-emerald-50 text-emerald-700 border border-emerald-200"
            }`}
        >
          {isDefaultDb ? "Configured DB" : "Uploaded File"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard
          label="Hit Rate"
          value={`${(analytics.hit_rate * 100).toFixed(1)}%`}
          accent="text-emerald-600"
        />
        <MetricCard
          label="Cache Hits"
          value={String(analytics.total_cache_hits)}
          accent="text-blue-600"
        />
        <MetricCard
          label="Cost Saved"
          value={`$${analytics.total_cost_saved.toFixed(6)}`}
          accent="text-emerald-600"
        />
        <MetricCard
          label="Unique Queries"
          value={String(analytics.total_queries_cached)}
          accent="text-purple-600"
        />
      </div>

      {total > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-neutral-500">
            Hits vs Misses
          </p>
          <div className="flex h-2.5 overflow-hidden rounded-full bg-neutral-100">
            <div
              className="bg-emerald-500"
              style={{ width: `${(analytics.total_cache_hits / total) * 100}%` }}
            />
            <div
              className="bg-blue-500"
              style={{ width: `${(analytics.total_cache_misses / total) * 100}%` }}
            />
          </div>
          <div className="mt-1.5 flex gap-4 text-[11px] text-neutral-500">
            <span>🟢 Hits: {analytics.total_cache_hits}</span>
            <span>🔵 Misses: {analytics.total_cache_misses}</span>
          </div>
        </div>
      )}

      <div>
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-neutral-500">
          Top Cached Queries ({isDefaultDb ? "Default DB" : activeConnection?.filename ?? "Uploaded DB"})
        </p>
        <div className="overflow-x-auto rounded-md border border-neutral-200">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-neutral-200 bg-neutral-50">
                <th className="px-3 py-2 text-xs font-semibold text-neutral-600">Question</th>
                <th className="px-3 py-2 text-xs font-semibold text-neutral-600">Hits</th>
                <th className="px-3 py-2 text-xs font-semibold text-neutral-600">Cost Saved</th>
                <th className="px-3 py-2 text-xs font-semibold text-neutral-600">Cached SQL</th>
              </tr>
            </thead>
            <tbody>
              {analytics.top_cached_queries.map((q) => (
                <tr key={q.question} className="border-b border-neutral-100 last:border-0">
                  <td className="max-w-xs truncate px-3 py-2 text-neutral-800">{q.question}</td>
                  <td className="px-3 py-2 text-neutral-800">{q.hit_count}</td>
                  <td className="px-3 py-2 text-neutral-800">${q.cost_saved.toFixed(6)}</td>
                  <td className="max-w-xs truncate px-3 py-2 font-mono text-xs text-neutral-500" title={q.sql}>{q.sql}</td>
                </tr>
              ))}
              {analytics.top_cached_queries.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-neutral-400">
                    No cached queries for this database yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
}
