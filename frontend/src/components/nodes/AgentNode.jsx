import React from "react";
import { Handle, Position } from "@xyflow/react";

const statusStyles = {
  idle: "bg-gray-400",
  running: "bg-blue-500",
  completed: "bg-emerald-500",
  error: "bg-red-500",
};

const toolIcons = {
  search: "S",
  calculator: "C",
  memory: "M",
};

export default function AgentNode({ id, data }) {
  const status = data.status || "idle";
  const tools = data.tools || [];
  const errors = data.validationErrors || [];

  return (
    <div className={`w-64 rounded-md border bg-surface shadow-sm transition-colors ${errors.length ? "border-red-300 ring-2 ring-red-100" : "border-blue-300"}`}>
      <Handle type="target" position={Position.Left} />
      <div className="flex items-start justify-between gap-3 border-b border-line px-3 py-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${statusStyles[status]}`} />
            <p className="truncate text-sm font-semibold">{data.label || "Agent"}</p>
          </div>
          <p className="mt-1 truncate text-xs text-muted">{data.role || "No role"}</p>
        </div>
        <button
          type="button"
          onClick={() => data.onDelete?.(id)}
          className="rounded px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-50"
        >
          Del
        </button>
      </div>
      <div className="px-3 py-2">
        <div className="flex flex-wrap gap-1">
          {tools.length ? (
            tools.map((tool) => (
              <span
                key={tool}
                className="inline-flex h-6 w-6 items-center justify-center rounded border border-line bg-soft text-xs font-bold transition-colors"
                title={tool}
              >
                {toolIcons[tool] || tool.slice(0, 1).toUpperCase()}
              </span>
            ))
          ) : (
            <span className="text-xs text-muted">No tools</span>
          )}
        </div>
        {errors.length ? <p className="mt-2 text-xs font-medium text-red-700">{errors[0]}</p> : null}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
