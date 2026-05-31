import React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import ExportButton from "./ExportButton";
import SparklineChart, { tokenCost, usageColor } from "./SparklineChart";

const stateStyles = {
  pending: {
    node: "border-line bg-soft text-muted",
    line: "bg-line",
    label: "Pending",
    icon: "⏳",
  },
  running: {
    node: "border-blue-300 bg-blue-50 text-blue-700 dark:bg-blue-950/50 dark:text-blue-200 timeline-pulse",
    line: "bg-blue-400",
    label: "Running",
    icon: "🔄",
  },
  done: {
    node: "border-emerald-300 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200",
    line: "bg-emerald-400",
    label: "Done",
    icon: "✅",
  },
  failed: {
    node: "border-red-300 bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-200",
    line: "bg-red-400",
    label: "Failed",
    icon: "❌",
  },
};

function formatTime(value) {
  if (!value) return "Not started";
  try {
    return new Date(value).toLocaleTimeString();
  } catch {
    return "Not started";
  }
}

function executionTime(step) {
  if (step.duration_ms != null) {
    return `${Math.max(0, step.duration_ms / 1000).toFixed(1)}s`;
  }
  if (!step.timestamp) return "Waiting";
  const end = step.completed_at ? new Date(step.completed_at).getTime() : Date.now();
  const start = new Date(step.timestamp).getTime();
  if (Number.isNaN(start)) return "Waiting";
  return `${Math.max(0, (end - start) / 1000).toFixed(1)}s`;
}

export default function WorkflowTimeline({
  steps = [],
  title = "Execution Timeline",
  status,
  runId,
  replayTargetId,
  isReplaying = false,
  replayDisabledReason = "",
  comparisonEnabled = false,
  onComparisonToggle,
  onExport,
  onRerun,
}) {
  const [expandedIndex, setExpandedIndex] = useState(null);
  const activeRef = useRef(null);

  const activeIndex = useMemo(
    () => steps.findIndex((step) => step.status === "running"),
    [steps],
  );
  const exportData = useMemo(
    () => ({
      run_id: runId,
      status,
      title,
      steps,
    }),
    [runId, status, title, steps],
  );

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeIndex]);

  return (
    <section className="rounded-md border border-line bg-surface p-4 transition-colors">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold">{title}</h3>
          <p className="text-xs text-muted">{steps.length} workflow step{steps.length === 1 ? "" : "s"}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {onComparisonToggle ? (
            <button
              type="button"
              onClick={onComparisonToggle}
              className="rounded-md border border-line px-3 py-2 text-sm font-semibold transition-colors hover:bg-soft"
            >
              {comparisonEnabled ? "Hide comparison" : "Compare"}
            </button>
          ) : null}
          {status === "completed" && onRerun ? (
            <button
              type="button"
              onClick={onRerun}
              disabled={isReplaying || Boolean(replayDisabledReason)}
              title={replayDisabledReason || "Rerun with original input"}
              className="rounded-md border border-line px-3 py-2 text-sm font-semibold transition-colors hover:bg-soft disabled:cursor-not-allowed disabled:opacity-55"
            >
              {isReplaying ? "Replaying..." : "Rerun"}
            </button>
          ) : null}
          {onExport ? (
            <button
              type="button"
              onClick={onExport}
              className="rounded-md border border-line px-3 py-2 text-sm font-semibold transition-colors hover:bg-soft"
            >
              Export
            </button>
          ) : null}
          <ExportButton data={exportData} label={`workflow-run-${runId || "timeline"}`} />
        </div>
      </div>
      {replayTargetId ? (
        <p className="mt-3 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-semibold text-blue-800">
          Run #{runId} to Run #{replayTargetId}
        </p>
      ) : null}
      {replayDisabledReason ? (
        <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          {replayDisabledReason}
        </p>
      ) : null}

      <div className="mt-4 max-h-[520px] overflow-y-auto pr-1">
        {steps.length ? (
          <ol className="relative space-y-0">
            {steps.map((step, index) => {
              const style = stateStyles[step.status] || stateStyles.pending;
              const isExpanded = expandedIndex === index;
              return (
                <li
                  key={`${step.agent_name}-${index}`}
                  ref={index === activeIndex ? activeRef : null}
                  className="relative grid grid-cols-[2.5rem_1fr] gap-3 pb-4 last:pb-0"
                >
                  <div className="relative flex justify-center">
                    {index < steps.length - 1 ? (
                      <span
                        className={`absolute top-10 h-[calc(100%-1rem)] w-px transition-colors ${style.line}`}
                        aria-hidden="true"
                      />
                    ) : null}
                    <button
                      type="button"
                      onClick={() => setExpandedIndex(isExpanded ? null : index)}
                      className={`z-10 flex h-9 w-9 items-center justify-center rounded-full border text-sm shadow-sm transition-all ${style.node}`}
                      aria-label={`Toggle ${step.agent_name} details`}
                    >
                      <span aria-hidden="true">{style.icon}</span>
                    </button>
                  </div>

                  <div className="min-w-0 rounded-md border border-line bg-surface-strong p-3 transition-colors">
                    <button
                      type="button"
                      onClick={() => setExpandedIndex(isExpanded ? null : index)}
                      className="flex w-full items-start justify-between gap-3 text-left"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold">{step.agent_name}</span>
                        <span className="mt-1 block text-xs text-muted">
                          {style.label} · {formatTime(step.timestamp)} · {executionTime(step)}
                        </span>
                      </span>
                      <span className="shrink-0 rounded-full bg-soft px-2 py-1 text-xs font-semibold text-muted">
                        {step.tokens || 0} tokens
                      </span>
                    </button>

                    <div className="mt-3">
                      <SparklineChart
                        data={step.usage || [{ timestamp: step.timestamp, tokens: step.tokens || 0 }]}
                        color={usageColor(step.tokens || 0)}
                        height={38}
                      />
                    </div>

                    {isExpanded ? (
                      <div className="mt-3 space-y-2 border-t border-line pt-3 text-xs text-muted">
                        <p>
                          <span className="font-semibold text-ink">Cost:</span> ${tokenCost(step.tokens || 0).toFixed(4)}
                        </p>
                        {step.error ? <p className="text-red-700 dark:text-red-300">{step.error}</p> : null}
                        {step.input ? (
                          <p>
                            <span className="font-semibold text-ink">Input:</span> {step.input}
                          </p>
                        ) : null}
                        {step.output ? (
                          <p className="whitespace-pre-wrap">
                            <span className="font-semibold text-ink">Output:</span> {step.output}
                          </p>
                        ) : null}
                        {!step.error && !step.input && !step.output ? (
                          <p>No step details available yet.</p>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ol>
        ) : (
          <div className="rounded-md border border-dashed border-line bg-surface-strong px-4 py-8 text-center text-sm text-muted">
            Select or run a workflow to see the execution timeline.
          </div>
        )}
      </div>
    </section>
  );
}