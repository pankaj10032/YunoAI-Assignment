import React from "react";
import { Handle, Position } from "@xyflow/react";

export default function ConditionNode({ id, data }) {
  const errors = data.validationErrors || [];
  return (
    <div className={`relative w-72 rounded-md border bg-amber-50 shadow-sm ${errors.length ? "border-red-300 ring-2 ring-red-100" : "border-amber-300"}`}>
      <Handle type="target" position={Position.Left} />
      <div className="border-b border-amber-200 px-3 py-2">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold text-amber-950">Condition</p>
          <button
            type="button"
            onClick={() => data.onDelete?.(id)}
            className="rounded px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-50"
          >
            Del
          </button>
        </div>
      </div>
      <div className="space-y-2 px-3 py-2">
        <label className="block text-xs font-medium text-amber-950">
          Expression
          <input
            value={data.expression || ""}
            onChange={(event) => data.onChange?.(id, { expression: event.target.value })}
            className="mt-1 w-full rounded-md border border-amber-300 bg-surface px-2 py-1 text-xs transition-colors"
            placeholder="input.priority == 'high'"
          />
        </label>
        {errors.length ? <p className="text-xs font-medium text-red-700">{errors[0]}</p> : null}
      </div>
      <Handle id="true" type="source" position={Position.Right} style={{ top: 36 }} />
      <Handle id="false" type="source" position={Position.Right} style={{ top: 76 }} />
      <span className="absolute -right-10 top-7 text-xs font-semibold text-emerald-700">true</span>
      <span className="absolute -right-11 top-[68px] text-xs font-semibold text-red-700">false</span>
    </div>
  );
}
