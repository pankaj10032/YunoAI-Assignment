import React from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  getSmoothStepPath,
} from "@xyflow/react";

function EdgeLabel({ x, y, label, errors }) {
  if (!label && !errors?.length) return null;
  return (
    <EdgeLabelRenderer>
      <div
        className={`nodrag nopan absolute rounded-md border px-2 py-1 text-xs font-semibold shadow-sm ${
          errors?.length
            ? "border-red-200 bg-red-50 text-red-700"
            : "border-line bg-surface text-ink"
        }`}
        style={{ transform: `translate(-50%, -50%) translate(${x}px, ${y}px)` }}
      >
        {errors?.length ? errors[0] : label}
      </div>
    </EdgeLabelRenderer>
  );
}

export function ConditionalEdge(props) {
  const [path, labelX, labelY] = getSmoothStepPath(props);
  const isFalse = props.label === "false" || props.sourceHandle === "false";
  const stroke = isFalse ? "#dc2626" : "#059669";
  return (
    <>
      <BaseEdge
        path={path}
        markerEnd={props.markerEnd}
        style={{ stroke, strokeWidth: 2, ...(props.style || {}) }}
      />
      <EdgeLabel
        x={labelX}
        y={labelY}
        label={props.label || props.data?.condition}
        errors={props.data?.validationErrors}
      />
    </>
  );
}

export function FeedbackEdge(props) {
  const [path, labelX, labelY] = getBezierPath({
    ...props,
    curvature: 0.55,
  });
  return (
    <>
      <BaseEdge
        path={path}
        markerEnd={props.markerEnd}
        style={{
          stroke: "#7c3aed",
          strokeDasharray: "7 5",
          strokeWidth: 2,
          ...(props.style || {}),
        }}
      />
      <EdgeLabel
        x={labelX}
        y={labelY}
        label={props.label || "feedback"}
        errors={props.data?.validationErrors}
      />
    </>
  );
}

export const edgeTypes = {
  conditional: ConditionalEdge,
  feedback: FeedbackEdge,
};
