import { useState } from "react";
import type { SchemaResponse } from "../api";

interface Props {
  schema: SchemaResponse | null;
  loading: boolean;
  error: string | null;
  /** Current main area view ('query', 'canvas', 'cache') */
  mainView?: "query" | "canvas" | "cache";
  /** Callback to switch the main area view */
  onViewChange?: (view: "query" | "canvas") => void;
  /** When true, renders without its own <aside> wrapper (for embedding inside another sidebar). */
  bare?: boolean;
}

export function SchemaPanel({
  schema,
  loading,
  error,
  mainView = "query",
  onViewChange,
  bare,
}: Props) {
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedTables, setExpandedTables] = useState<Record<string, boolean>>({});

  const toggleTable = (tableName: string) => {
    setExpandedTables((prev) => ({
      ...prev,
      [tableName]: prev[tableName] === false ? true : false,
    }));
  };

  const tableEntries = Object.entries(schema?.tables || {});
  const filteredTables = tableEntries.filter(([tableName, cols]) => {
    if (!searchTerm.trim()) return true;
    const term = searchTerm.toLowerCase();
    return (
      tableName.toLowerCase().includes(term) ||
      cols.some((c) => c.name.toLowerCase().includes(term))
    );
  });

  const content = (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header with Title & Main View Switcher */}
      <div className="border-b border-neutral-200 px-4 py-3 bg-white shrink-0">
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center gap-1.5">
            <svg
              className="h-4 w-4 text-blue-600"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <ellipse cx="12" cy="5" rx="9" ry="3" />
              <path d="M3 5V19A9 3 0 0 0 21 19V5" />
              <path d="M3 12A9 3 0 0 0 21 12" />
            </svg>
            <h2 className="text-xs font-bold uppercase tracking-wider text-neutral-700">
              Database Schema
            </h2>
          </div>
          <span className="font-mono text-[10px] text-neutral-400">
            {tableEntries.length} {tableEntries.length === 1 ? "table" : "tables"}
          </span>
        </div>

        {/* View Switcher Toggle: Switches between Query Assistant and Large Visual Canvas in Main Area */}
        <div className="flex rounded-lg bg-neutral-100 p-0.5 text-xs">
          <button
            type="button"
            onClick={() => onViewChange?.("query")}
            className={`flex-1 flex items-center justify-center gap-1 rounded-md py-1 font-medium transition-all ${
              mainView === "query"
                ? "bg-white text-neutral-900 shadow-xs"
                : "text-neutral-500 hover:text-neutral-700"
            }`}
          >
            <svg
              className="h-3.5 w-3.5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <line x1="8" y1="6" x2="21" y2="6" />
              <line x1="8" y1="12" x2="21" y2="12" />
              <line x1="8" y1="18" x2="21" y2="18" />
              <line x1="3" y1="6" x2="3.01" y2="6" />
              <line x1="3" y1="12" x2="3.01" y2="12" />
              <line x1="3" y1="18" x2="3.01" y2="18" />
            </svg>
            Query
          </button>
          <button
            type="button"
            onClick={() => onViewChange?.("canvas")}
            className={`flex-1 flex items-center justify-center gap-1 rounded-md py-1 font-medium transition-all ${
              mainView === "canvas"
                ? "bg-white text-neutral-900 shadow-xs"
                : "text-neutral-500 hover:text-neutral-700"
            }`}
          >
            <svg
              className="h-3.5 w-3.5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <rect width="6" height="6" x="3" y="3" rx="1" />
              <rect width="6" height="6" x="15" y="15" rx="1" />
              <path d="M9 6h6a3 3 0 0 1 3 3v6" />
            </svg>
            Visual Canvas
          </button>
        </div>
      </div>

      {/* Main Content Area - Always displays the text-based List view */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0">
        {loading && (
          <div className="p-5 text-center">
            <div className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-neutral-300 border-t-blue-600 mb-2" />
            <p className="text-xs text-neutral-400">Loading database schema…</p>
          </div>
        )}

        {error && (
          <div className="p-3.5 rounded-md bg-white border border-neutral-200 text-xs text-neutral-700">
            <p className="font-semibold mb-0.5 text-neutral-800">Failed to fetch schema</p>
            <p className="text-neutral-500">{error}</p>
          </div>
        )}

        {!loading && !error && schema && (
          <>
            {/* Search input */}
            <div className="relative mb-2">
              <input
                type="text"
                placeholder="Filter tables & columns…"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full rounded-md border border-neutral-200 bg-neutral-50 px-2.5 py-1.5 text-xs text-neutral-800 placeholder-neutral-400 focus:border-blue-500 focus:bg-white focus:outline-none"
              />
              {searchTerm && (
                <button
                  type="button"
                  onClick={() => setSearchTerm("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 text-xs"
                >
                  ✕
                </button>
              )}
            </div>

            {filteredTables.length === 0 ? (
              <p className="text-xs text-neutral-400 text-center py-4">No matching tables</p>
            ) : (
              filteredTables.map(([tableName, columns]) => {
                const isExpanded = expandedTables[tableName] !== false;
                const pkCount = columns.filter((c) => c.primary_key).length;
                const fkCount = columns.filter((c) => c.is_foreign_key).length;

                return (
                  <div
                    key={tableName}
                    className="rounded-lg border border-neutral-200 bg-white overflow-hidden shadow-2xs"
                  >
                    <button
                      type="button"
                      onClick={() => toggleTable(tableName)}
                      className="w-full flex items-center justify-between px-3 py-2 bg-neutral-50/80 hover:bg-neutral-100/80 transition-colors text-left"
                    >
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className="text-[10px] text-neutral-400">
                          {isExpanded ? "▼" : "▶"}
                        </span>
                        <span className="font-mono text-xs font-semibold text-neutral-800 truncate">
                          {tableName}
                        </span>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        {pkCount > 0 && (
                          <span className="rounded bg-amber-50 px-1 py-0.5 font-mono text-[9px] font-medium text-amber-700 border border-amber-200/50">
                            {pkCount} PK
                          </span>
                        )}
                        {fkCount > 0 && (
                          <span className="rounded bg-indigo-50 px-1 py-0.5 font-mono text-[9px] font-medium text-indigo-700 border border-indigo-200/50">
                            {fkCount} FK
                          </span>
                        )}
                        <span className="font-mono text-[10px] text-neutral-400">
                          {columns.length}
                        </span>
                      </div>
                    </button>

                    {isExpanded && (
                      <div className="divide-y divide-neutral-100 px-3 py-1">
                        {columns.map((col) => (
                          <div
                            key={col.name}
                            className="flex items-center justify-between gap-2 py-1 text-xs"
                          >
                            <div className="flex items-center gap-1.5 min-w-0">
                              {col.primary_key ? (
                                <span
                                  className="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded bg-amber-100 text-[8px] text-amber-800 font-bold"
                                  title="Primary Key"
                                >
                                  🔑
                                </span>
                              ) : col.is_foreign_key ? (
                                <span
                                  className="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded bg-indigo-100 text-[8px] text-indigo-800 font-bold"
                                  title="Foreign Key"
                                >
                                  ↗
                                </span>
                              ) : (
                                <span className="h-1 w-1 shrink-0 rounded-full bg-neutral-300 ml-1.5 mr-1" />
                              )}
                              <span
                                className={`truncate font-mono text-[11px] ${
                                  col.primary_key
                                    ? "font-semibold text-amber-900"
                                    : col.is_foreign_key
                                    ? "font-medium text-indigo-900"
                                    : "text-neutral-700"
                                }`}
                              >
                                {col.name}
                              </span>
                            </div>
                            <span className="shrink-0 font-mono text-[10px] text-neutral-400">
                              {col.type.toLowerCase()}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </>
        )}
      </div>
    </div>
  );

  if (bare) {
    return content;
  }

  return (
    <aside className="w-72 shrink-0 border-r border-neutral-200 bg-white flex flex-col h-full overflow-hidden">
      {content}
    </aside>
  );
}
