import React from "react";
import { Handle, Position } from "@xyflow/react";

export default function InputNode({ id, data }) {
  const errors = data.validationErrors || [];
  return (
    <div className={`w-56 rounded-md border bg-green-50 px-3 py-2 shadow-sm ${errors.length ? "border-red-300 ring-2 ring-red-100" : "border-green-200"}`}>
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-green-950">{data.label || "Workflow Input"}</p>
        <button
          type="button"
          onClick={() => data.onDelete?.(id)}
          className="rounded px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-50"
        >
          Del
        </button>
      </div>
      <p className="mt-1 text-xs text-green-800">Entry point</p>
      {errors.length ? <p className="mt-1 text-xs font-medium text-red-700">{errors[0]}</p> : null}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
