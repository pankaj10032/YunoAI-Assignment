import React from "react";
import { Handle, Position } from "@xyflow/react";

export default function OutputNode({ id, data }) {
  const errors = data.validationErrors || [];
  return (
    <div className={`w-56 rounded-md border bg-emerald-50 px-3 py-2 shadow-sm ${errors.length ? "border-red-300 ring-2 ring-red-100" : "border-emerald-200"}`}>
      <Handle type="target" position={Position.Left} />
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-emerald-950">{data.label || "Workflow Output"}</p>
        <button
          type="button"
          onClick={() => data.onDelete?.(id)}
          className="rounded px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-50"
        >
          Del
        </button>
      </div>
      <p className="mt-1 text-xs text-emerald-800">Final response</p>
      {errors.length ? <p className="mt-1 text-xs font-medium text-red-700">{errors[0]}</p> : null}
    </div>
  );
}
