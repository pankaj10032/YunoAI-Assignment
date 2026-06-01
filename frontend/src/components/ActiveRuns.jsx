import React from "react";
import { useEffect, useState } from "react";

import {
  getAgents,
  getMessages,
  getRun,
  getRuns,
  getWorkflows,
  rerunWorkflowRun,
  resumeWorkflow,
} from "../services/api";
import { connectRunSocket } from "../services/websocket";
import WorkflowTimeline from "./WorkflowTimeline";

const statusClass = {
  pending: "bg-amber-100 text-amber-800",
  running: "bg-blue-100 text-blue-800",
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
  paused: "bg-violet-100 text-violet-800",
};

export default function ActiveRuns({ onSelectRun }) {
  const [runs, setRuns] = useState([]);
  const [workflows, setWorkflows] = useState([]);
  const [agents, setAgents] = useState([]);
  const [timelineRunId, setTimelineRunId] = useState(null);
  const [timelineSteps, setTimelineSteps] = useState([]);
  const [replayingRunId, setReplayingRunId] = useState(null);
  const [replayLinks, setReplayLinks] = useState({});
  const [comparisonEnabled, setComparisonEnabled] = useState(false);

  useEffect(() => {
    let active = true;
    const load = () =>
      Promise.all([getRuns({ limit: 100 }), getWorkflows(), getAgents()])
        .then(([runData, workflowData, agentData]) => {
          if (!active) return;
          setRuns(runData);
          setWorkflows(workflowData);
          setAgents(agentData);
        })
        .catch(() => active && setRuns([]));
    load();
    // Increased polling interval from 5s to 10s to reduce server load
    const timer = window.setInterval(load, 10000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!runs.length) {
      setTimelineRunId(null);
      setTimelineSteps([]);
      return;
    }
    if (!timelineRunId || !runs.some((run) => run.id === timelineRunId)) {
      const preferred = runs.find((run) => run.status === "running") || runs[0];
      setTimelineRunId(preferred.id);
    }
  }, [runs, timelineRunId]);

  const timelineRun = runs.find((run) => run.id === timelineRunId) || null;
  const timelineWorkflow = timelineRun
    ? workflows.find((workflow) => workflow.id === timelineRun.workflow_id)
    : null;
  const replayDisabledReason =
    timelineRun && timelineWorkflow
      ? modifiedAgentWarning(timelineWorkflow, timelineRun, agents)
      : "";

  useEffect(() => {
    if (!timelineRun || !timelineWorkflow) {
      setTimelineSteps([]);
      return;
    }
    setTimelineSteps((current) =>
      buildSteps(timelineWorkflow, timelineRun, current),
    );
  }, [timelineRun?.id, timelineRun?.status, timelineWorkflow?.id]);

  useEffect(() => {
    if (!timelineRun || timelineRun.status !== "running") return undefined;
    const socket = connectRunSocket(timelineRun.id);

    socket.on("*", (event) => {
      setTimelineSteps((current) => updateStepsFromEvent(current, event));
      if (event.type === "completed" || event.type === "failed") {
        getMessages(timelineRun.id)
          .then((messages) => {
            setTimelineSteps((current) => mergeMessagesIntoSteps(current, messages));
          })
          .catch(() => {});
      }
    });

    return () => socket.close();
  }, [timelineRun?.id, timelineRun?.status]);

  const exportTimeline = () => {
    const payload = {
      run_id: timelineRun?.id,
      workflow_id: timelineRun?.workflow_id,
      status: timelineRun?.status,
      exported_at: new Date().toISOString(),
      steps: timelineSteps,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `workflow-run-${timelineRun?.id || "timeline"}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleRerun = async () => {
    if (!timelineRun || replayDisabledReason) return;
    setReplayingRunId(timelineRun.id);
    try {
      await getRun(timelineRun.id);
      const replay = await rerunWorkflowRun(timelineRun.id);
      setReplayLinks((current) => ({ ...current, [timelineRun.id]: replay.run_id }));
      const refreshed = await getRuns({ limit: 100 });
      setRuns(refreshed);
      setTimelineRunId(replay.run_id);
    } finally {
      setReplayingRunId(null);
    }
  };

  const handleResume = async (run) => {
    if (!run) return;
    await resumeWorkflow(run.workflow_id, run.id);
    const refreshed = await getRuns({ limit: 100 });
    setRuns(refreshed);
    setTimelineRunId(run.id);
  };

  const groupedRuns = groupRunsByWorkflow(runs, workflows);

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
      <div className="overflow-hidden rounded-md border border-line bg-surface transition-colors">
        <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-line text-left text-sm">
          <thead className="bg-soft text-xs uppercase text-muted">
            <tr>
              <th className="px-4 py-3">Workflow Run</th>
              <th className="px-4 py-3">Started</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Progress</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {groupedRuns.map((group) => (
              <RunGroup
                key={group.workflowId}
                group={group}
                timelineRunId={timelineRunId}
                replayLinks={replayLinks}
                onTimeline={setTimelineRunId}
                onSelectRun={onSelectRun}
                onResume={handleResume}
              />
            ))}
            {!runs.length ? (
              <tr>
                <td className="px-4 py-8 text-center text-muted" colSpan="5">
                  No workflow runs yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
        </div>
      </div>

      <WorkflowTimeline
        title={timelineWorkflow?.name || "Execution Timeline"}
        steps={timelineSteps}
        status={timelineRun?.status}
        runId={timelineRun?.id}
        replayTargetId={timelineRun ? replayLinks[timelineRun.id] : null}
        isReplaying={replayingRunId === timelineRun?.id}
        replayDisabledReason={replayDisabledReason}
        comparisonEnabled={comparisonEnabled}
        onComparisonToggle={() => setComparisonEnabled((value) => !value)}
        onRerun={handleRerun}
        onExport={timelineRun?.status === "completed" || timelineRun?.status === "failed" ? exportTimeline : null}
      />
      {comparisonEnabled && timelineRun && replayLinks[timelineRun.id] ? (
        <div className="rounded-md border border-line bg-surface p-4 text-sm transition-colors xl:col-start-2">
          <p className="font-semibold">Replay comparison</p>
          <p className="mt-1 text-muted">
            Run #{timelineRun.id} is being compared with Run #{replayLinks[timelineRun.id]}.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function RunGroup({ group, timelineRunId, replayLinks, onTimeline, onSelectRun, onResume }) {
  return (
    <>
      <tr className="bg-soft/50">
        <td className="px-4 py-2 text-xs font-semibold uppercase text-muted" colSpan="5">
          {group.workflowName} · {group.runs.length} run{group.runs.length === 1 ? "" : "s"}
        </td>
      </tr>
      {group.runs.map((run) => {
        const progress =
          run.status === "completed" ? 100 : run.status === "failed" ? 100 : run.status === "paused" ? 65 : run.status === "running" ? 55 : 15;
        const isTimelineRun = run.id === timelineRunId;
        return (
          <tr key={run.id} className={isTimelineRun ? "bg-soft/60" : ""}>
            <td className="px-4 py-3">
              <p className="font-semibold">Run #{run.id}</p>
              {replayLinks[run.id] ? (
                <p className="text-xs text-muted">Replay to Run #{replayLinks[run.id]}</p>
              ) : null}
            </td>
            <td className="px-4 py-3 text-muted">
              {run.started_at ? new Date(run.started_at).toLocaleString() : "Not started"}
            </td>
            <td className="px-4 py-3">
              <span className={`rounded-full px-2 py-1 text-xs font-semibold ${statusClass[run.status] || statusClass.pending}`}>
                {run.status}
              </span>
            </td>
            <td className="px-4 py-3">
              <div className="h-2 w-40 rounded-full bg-soft">
                <div className="h-2 rounded-full bg-ink transition-all" style={{ width: `${progress}%` }} />
              </div>
            </td>
            <td className="px-4 py-3 text-right">
              <button onClick={() => onTimeline(run.id)} className="rounded-md border border-line px-3 py-1.5 font-medium">
                Timeline
              </button>
              <button onClick={() => onSelectRun(run)} className="ml-2 rounded-md border border-line px-3 py-1.5 font-medium">
                View Details
              </button>
              {run.status === "paused" || run.status === "failed" ? (
                <button onClick={() => onResume(run)} className="ml-2 rounded-md border border-line px-3 py-1.5 font-medium">
                  Resume
                </button>
              ) : null}
              <button disabled className="ml-2 rounded-md border border-line px-3 py-1.5 font-medium text-muted opacity-60">
                Stop
              </button>
            </td>
          </tr>
        );
      })}
    </>
  );
}

function groupRunsByWorkflow(runs, workflows) {
  const names = new Map(workflows.map((workflow) => [workflow.id, workflow.name]));
  const groups = new Map();
  runs.forEach((run) => {
    if (!groups.has(run.workflow_id)) {
      groups.set(run.workflow_id, {
        workflowId: run.workflow_id,
        workflowName: names.get(run.workflow_id) || `Workflow #${run.workflow_id}`,
        runs: [],
      });
    }
    groups.get(run.workflow_id).runs.push(run);
  });
  return [...groups.values()];
}

function modifiedAgentWarning(workflow, run, agents) {
  if (!run.started_at) return "";
  const started = new Date(run.started_at).getTime();
  const agentIds = new Set(
    (workflow.nodes || [])
      .filter((node) => node.type === "agent")
      .map((node) => node.data?.agent_id || node.data?.agentId)
      .filter(Boolean)
      .map(String),
  );
  const modified = agents.find(
    (agent) =>
      agentIds.has(String(agent.id)) &&
      new Date(agent.updated_at || agent.created_at).getTime() > started,
  );
  return modified ? `Replay disabled because ${modified.name} changed after this run.` : "";
}

function buildSteps(workflow, run, current = []) {
  if (run.steps?.length) {
    return run.steps.map((step) => ({
      agent_name: labelForStep(workflow, step.step_id),
      status: step.status === "completed" ? "done" : step.status,
      timestamp: step.started_at,
      completed_at: step.completed_at,
      error: step.error,
      input: step.context_snapshot?.last_output || workflow.description || "",
      output: step.agent_output || "",
      tokens: step.agent_output ? Math.max(1, step.agent_output.split(/\s+/).length * 2) : 0,
    }));
  }
  const agentNodes = (workflow.nodes || []).filter((node) => node.type === "agent");
  const baseNodes = agentNodes.length
    ? agentNodes
    : [{ id: `workflow-${workflow.id}`, data: { label: workflow.name } }];
  const currentByName = new Map(current.map((step) => [step.agent_name, step]));
  const activeIndex = Math.max(0, current.findIndex((step) => step.status === "running"));

  return baseNodes.map((node, index) => {
    const name = node.data?.label || node.data?.agent_name || `Step ${index + 1}`;
    const existing = currentByName.get(name) || {};
    const status = statusForRun(run.status, index, activeIndex, existing.status);
    return {
      agent_name: name,
      status,
      timestamp:
        existing.timestamp ||
        (status !== "pending" ? run.started_at || new Date().toISOString() : null),
      completed_at:
        existing.completed_at ||
        (status === "done" || status === "failed" ? run.completed_at : null),
      error: status === "failed" ? existing.error || "Execution failed." : existing.error,
      input: existing.input || node.data?.task || workflow.description || "",
      output: existing.output || "",
      tokens: existing.tokens || (status === "done" ? Math.floor((run.total_tokens || 0) / baseNodes.length) : 0),
    };
  });
}

function labelForStep(workflow, stepId) {
  const node = (workflow.nodes || []).find((item) => item.id === stepId);
  return node?.data?.label || node?.data?.agent_name || stepId;
}

function statusForRun(runStatus, index, activeIndex, existingStatus) {
  if (runStatus === "completed") return "done";
  if (runStatus === "failed") {
    if (existingStatus === "done") return "done";
    return index === activeIndex ? "failed" : index < activeIndex ? "done" : "pending";
  }
  if (runStatus === "paused") {
    if (existingStatus === "done") return "done";
    return index === activeIndex ? "paused" : index < activeIndex ? "done" : "pending";
  }
  if (runStatus === "running") {
    if (existingStatus === "done") return "done";
    if (existingStatus === "running") return "running";
    return index === 0 ? "running" : "pending";
  }
  return "pending";
}

function updateStepsFromEvent(steps, event) {
  if (!steps.length) return steps;
  if (event.type === "completed") {
    return steps.map((step, index) => ({
      ...step,
      status: "done",
      completed_at: new Date().toISOString(),
      output: index === steps.length - 1 ? event.result || step.output : step.output,
      tokens: step.tokens || Math.floor((event.usage?.tokens || 0) / steps.length),
    }));
  }
  if (event.type === "failed" || event.type === "paused") {
    const runningIndex = Math.max(0, steps.findIndex((step) => step.status === "running"));
    return steps.map((step, index) =>
      index === runningIndex
        ? { ...step, status: event.type, error: event.message || "Execution failed." }
        : step,
    );
  }
  if (event.type === "log" || event.type === "connected") {
    const runningIndex = Math.max(0, steps.findIndex((step) => step.status === "running"));
    return steps.map((step, index) =>
      index === runningIndex
        ? {
            ...step,
            status: "running",
            timestamp: step.timestamp || new Date().toISOString(),
            output: event.message || step.output,
          }
        : step,
    );
  }
  return steps;
}

function mergeMessagesIntoSteps(steps, messages) {
  if (!steps.length || !messages.length) return steps;
  const lastMessage = messages[messages.length - 1];
  const tokens = messages.reduce((sum, message) => sum + (message.metadata?.tokens || 0), 0);
  return steps.map((step, index) =>
    index === steps.length - 1
      ? {
          ...step,
          output: lastMessage.content || step.output,
          tokens: step.tokens || tokens,
        }
      : step,
  );
}
