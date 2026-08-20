import { memo } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { type TableNodeData, NODE_WIDTH } from "../utils/schemaFlowMapper";

export type TableNodeType = Node<TableNodeData, "tableNode">;

function TableNodeComponent({ data, selected }: NodeProps<TableNodeType>) {
  const { tableName, columns = [] } = data;

  const pkCount = columns.filter((c) => c.primary_key).length;
  const fkCount = columns.filter((c) => c.is_foreign_key).length;

  return (
    <div
      style={{ width: `${NODE_WIDTH}px` }}
      className={`rounded-xl border bg-white shadow-sm transition-all select-none ${
        selected
          ? "border-blue-500 ring-2 ring-blue-500/20 shadow-md"
          : "border-slate-200 hover:border-slate-300 hover:shadow-md"
      }`}
    >
      {/* Table Header */}
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/80 px-3.5 py-2.5 rounded-t-xl">
        <div className="flex items-center gap-2 min-w-0">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-blue-100 text-blue-700">
            <svg
              className="h-3.5 w-3.5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 3v18" />
              <rect width="18" height="18" x="3" y="3" rx="2" />
              <path d="M3 9h18" />
              <path d="M3 15h18" />
            </svg>
          </span>
          <h3 className="truncate font-mono text-xs font-bold text-slate-800" title={tableName}>
            {tableName}
          </h3>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {pkCount > 0 && (
            <span className="rounded bg-amber-50 px-1.5 py-0.5 font-mono text-[9px] font-semibold text-amber-700 border border-amber-200/60">
              {pkCount} PK
            </span>
          )}
          {fkCount > 0 && (
            <span className="rounded bg-indigo-50 px-1.5 py-0.5 font-mono text-[9px] font-semibold text-indigo-700 border border-indigo-200/60">
              {fkCount} FK
            </span>
          )}
          <span className="rounded bg-slate-200/70 px-1.5 py-0.5 font-mono text-[9px] font-medium text-slate-600">
            {columns.length}
          </span>
        </div>
      </div>

      {/* Columns List */}
      <div className="divide-y divide-slate-50 py-1">
        {columns.map((col) => {
          const isPK = Boolean(col.primary_key);
          const isFK = Boolean(col.is_foreign_key);

          return (
            <div
              key={col.name}
              className="relative flex items-center justify-between gap-3 px-3.5 py-1.5 hover:bg-slate-50/70 text-xs transition-colors h-[32px]"
            >
              {/* Target Handle STRICTLY on Position.Left */}
              <Handle
                type="target"
                position={Position.Left}
                id={`${tableName}-${col.name}-target`}
                className="!absolute !-left-1.5 !top-1/2 !-translate-y-1/2 !h-2.5 !w-2.5 !rounded-full !border-2 !border-white !bg-blue-500"
              />

              <div className="flex items-center gap-1.5 min-w-0">
                {isPK ? (
                  <span
                    className="flex h-4 w-4 shrink-0 items-center justify-center rounded bg-amber-100 text-[9px] font-bold text-amber-800"
                    title="Primary Key"
                  >
                    🔑
                  </span>
                ) : isFK ? (
                  <span
                    className="flex h-4 w-4 shrink-0 items-center justify-center rounded bg-indigo-100 text-[9px] font-bold text-indigo-700"
                    title="Foreign Key"
                  >
                    ↗
                  </span>
                ) : (
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-slate-300 ml-1.5 mr-1" />
                )}
                <span
                  className={`truncate font-mono text-[11px] ${
                    isPK
                      ? "font-bold text-amber-900"
                      : isFK
                      ? "font-medium text-indigo-900"
                      : "text-slate-700"
                  }`}
                  title={col.name}
                >
                  {col.name}
                </span>
              </div>

              <div className="flex shrink-0 items-center gap-1">
                <span className="font-mono text-[10px] text-slate-400">
                  {col.type.toLowerCase()}
                </span>
              </div>

              {/* Source Handle STRICTLY on Position.Right */}
              <Handle
                type="source"
                position={Position.Right}
                id={`${tableName}-${col.name}-source`}
                className="!absolute !-right-1.5 !top-1/2 !-translate-y-1/2 !h-2.5 !w-2.5 !rounded-full !border-2 !border-white !bg-blue-500"
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export const TableNode = memo(TableNodeComponent);
