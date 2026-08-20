import { useEffect, useState } from "react";
import { fetchSchema, runQuery, type QueryResponse, type SchemaResponse } from "./api";
import { SchemaPanel } from "./components/SchemaPanel";
import { SchemaDiagram } from "./components/SchemaDiagram";
import { QueryForm } from "./components/QueryForm";
import { ResultsTable } from "./components/ResultsTable";
import { CacheAnalytics } from "./components/CacheAnalytics";
import { DatabaseSelector } from "./components/DatabaseSelector";

export type MainViewType = "query" | "canvas" | "cache";

interface ActiveConnection {
  connectionId: string;
  filename: string;
}

function App() {
  const [schema, setSchema] = useState<SchemaResponse | null>(null);
  const [schemaLoading, setSchemaLoading] = useState(true);
  const [schemaError, setSchemaError] = useState<string | null>(null);

  const [result, setResult] = useState<QueryResponse | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);
  const [mainView, setMainView] = useState<MainViewType>("query");
  const [writeMode, setWriteMode] = useState(false);
  const [fallbackStatus, setFallbackStatus] = useState<string | null>(null);

  // null = using the default configured DATABASE_URL database.
  const [activeConnection, setActiveConnection] = useState<ActiveConnection | null>(null);

  function loadSchema(connectionId: string | null) {
    setSchemaLoading(true);
    setSchemaError(null);
    fetchSchema(connectionId)
      .then(setSchema)
      .catch((err: Error) => setSchemaError(err.message))
      .finally(() => setSchemaLoading(false));
  }

  useEffect(() => {
    loadSchema(activeConnection?.connectionId ?? null);
    // Switching databases invalidates any results shown from the previous one.
    setResult(null);
  }, [activeConnection]);

  async function handleSubmit(question: string) {
    setQueryLoading(true);
    setQueryError(null);
    setLastQuestion(question);
    setFallbackStatus(null);
    try {
      const response = await runQuery(
        question,
        activeConnection?.connectionId ?? null,
        writeMode,
        (status) => setFallbackStatus(status)
      );
      setResult(response);
    } catch (err) {
      setResult(null);
      setQueryError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setQueryLoading(false);
    }
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-neutral-50">
      {/* Left Sidebar */}
      <aside className="w-72 shrink-0 border-r border-neutral-200 bg-white flex flex-col h-screen overflow-hidden">
        <div className="shrink-0">
          <DatabaseSelector
            activeConnection={activeConnection}
            onUploaded={setActiveConnection}
            onReset={() => setActiveConnection(null)}
          />
        </div>
        <div className="flex-1 min-h-0 overflow-hidden">
          <SchemaPanel
            schema={schema}
            loading={schemaLoading}
            error={schemaError}
            mainView={mainView}
            onViewChange={setMainView}
            bare
          />
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden min-w-0">
        {/* Top Header */}
        <header className="shrink-0 border-b border-neutral-200 bg-white px-8 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-semibold text-neutral-900">Analytics Query Assistant</h1>
              <p className="mt-0.5 text-xs text-neutral-500">
                {mainView === "canvas"
                  ? "Interactive Entity-Relationship (ER) Diagram. Drag nodes, pan, zoom, or search schema."
                  : writeMode
                    ? "Write mode is ON — queries will be executed on the database."
                    : "Ask questions about your data in plain English. Only read-only queries are executed."}
              </p>
            </div>

            <div className="flex items-center gap-4">
              {mainView === "query" && (
                <label className="flex cursor-pointer items-center gap-2">
                  <span className={"text-xs font-medium " + (writeMode ? "text-red-600" : "text-neutral-500")}>
                    Write Mode
                  </span>
                  <div className="relative">
                    <input
                      type="checkbox"
                      checked={writeMode}
                      onChange={(e) => setWriteMode(e.target.checked)}
                      className="peer sr-only"
                    />
                    <div className={"h-5 w-9 rounded-full transition-colors " + (writeMode ? "bg-red-500" : "bg-neutral-300")} />
                    <div className={"absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform " + (writeMode ? "translate-x-4" : "translate-x-0")} />
                  </div>
                </label>
              )}

              {/* View Switcher Tabs in Main Header */}
              <div className="flex gap-1 rounded-md border border-neutral-200 bg-neutral-50 p-1">
                <button
                  type="button"
                  onClick={() => setMainView("query")}
                  className={
                    "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors " +
                    (mainView === "query"
                      ? "bg-white shadow-xs text-neutral-900 font-semibold"
                      : "text-neutral-500 hover:text-neutral-700")
                  }
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="11" cy="11" r="8" />
                    <line x1="21" y1="21" x2="16.65" y2="16.65" />
                  </svg>
                  Query Assistant
                </button>

                <button
                  type="button"
                  onClick={() => setMainView("canvas")}
                  className={
                    "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors " +
                    (mainView === "canvas"
                      ? "bg-white shadow-xs text-neutral-900 font-semibold"
                      : "text-neutral-500 hover:text-neutral-700")
                  }
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect width="6" height="6" x="3" y="3" rx="1" />
                    <rect width="6" height="6" x="15" y="15" rx="1" />
                    <path d="M9 6h6a3 3 0 0 1 3 3v6" />
                  </svg>
                  ER Diagram
                </button>

                <button
                  type="button"
                  onClick={() => setMainView("cache")}
                  className={
                    "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors " +
                    (mainView === "cache"
                      ? "bg-white shadow-xs text-neutral-900 font-semibold"
                      : "text-neutral-500 hover:text-neutral-700")
                  }
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 2v20" />
                    <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
                  </svg>
                  Cache Analytics
                </button>
              </div>
            </div>
          </div>
        </header>

        {/* Dynamic Main Section */}
        <div className="flex-1 overflow-hidden relative">
          {mainView === "query" && (
            <div className="h-full overflow-y-auto">
              <div className="mx-auto flex max-w-4xl flex-col gap-6 px-8 py-8">
                <QueryForm onSubmit={handleSubmit} loading={queryLoading} fallbackStatus={fallbackStatus} />

                {queryError && (
                  <div className="rounded-md border border-neutral-200 bg-white px-4 py-3 text-sm text-neutral-700">
                    <p className="font-medium text-neutral-800">Couldn't answer that question</p>
                    <p className="mt-0.5 text-neutral-500">{queryError}</p>
                  </div>
                )}

                {queryLoading && (
                  <p className="text-sm text-neutral-500">
                    Generating SQL for "{lastQuestion}"…
                  </p>
                )}

                {result && !queryLoading && <ResultsTable result={result} />}
              </div>
            </div>
          )}

          {mainView === "canvas" && (
            <div className="w-full h-full flex flex-col">
              <SchemaDiagram schema={schema} showMiniMap={true} className="w-full h-full flex-1" />
            </div>
          )}

          {mainView === "cache" && (
            <div className="h-full overflow-y-auto">
              <div className="mx-auto flex max-w-4xl flex-col gap-6 px-8 py-8">
                <CacheAnalytics
                  activeConnection={activeConnection}
                  isDefault={activeConnection === null}
                />
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
