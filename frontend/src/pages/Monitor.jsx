import React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getAgents, getRuns, getWorkflows, stopWorkflowRun } from "../services/api";
import { useRunStream } from "../hooks/useRunStream";
import AuditTimeline from "../components/AuditTimeline";

const tabs = ["Active Runs", "Message Stream", "Token/Cost", "Audit Trail"];
const budgetLimit = 100000;

const statusClass = {
  pending: "bg-amber-100 text-amber-800",
  running: "bg-blue-100 text-blue-800",
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
  paused: "bg-violet-100 text-violet-800",
};

const levelClass = {
  INFO: "border-gray-200 bg-gray-50 text-gray-700",
  TOOL: "border-blue-200 bg-blue-50 text-blue-700",
  ERROR: "border-red-200 bg-red-50 text-red-700",
  COST: "border-emerald-200 bg-emerald-50 text-emerald-700",
};

export default function Monitor() {
  const [activeTab, setActiveTab] = useState(tabs[0]);
  const [runs, setRuns] = useState([]);
  const [workflows, setWorkflows] = useState([]);
  const [agents, setAgents] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [filters, setFilters] = useState({ agent: "", channel: "", level: "" });
  const bottomRef = useRef(null);

  const load = async () => {
    const [runData, workflowData, agentData] = await Promise.all([
      getRuns({ limit: 100 }),
      getWorkflows(),
      getAgents(),
    ]);
    setRuns(runData);
    setWorkflows(workflowData);
    setAgents(agentData);
    setSelectedRunId((current) => current || String(runData.find((run) => run.status === "running")?.id || runData[0]?.id || ""));
  };

  useEffect(() => {
    let active = true;
    const refresh = () => load().catch(() => active && setRuns([]));
    refresh();
    const timer = window.setInterval(refresh, 6000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const selectedRun = runs.find((run) => String(run.id) === String(selectedRunId));
  const selectedWorkflow = workflows.find((workflow) => workflow.id === selectedRun?.workflow_id);
  const stream = useRunStream(selectedRunId, {
    enabled: Boolean(selectedRunId),
    onSync: ({ run }) => {
      if (!run) return;
      setRuns((current) => current.map((item) => (item.id === run.id ? { ...item, ...run } : item)));
    },
  });

  const agentById = useMemo(
    () => new Map(agents.map((agent) => [String(agent.id), agent])),
    [agents],
  );
  const workflowById = useMemo(
    () => new Map(workflows.map((workflow) => [workflow.id, workflow])),
    [workflows],
  );

  const messageEvents = useMemo(() => {
    const persisted = stream.messages.map((message) => ({
      id: `message-${message.id}`,
      run_id: message.workflow_run_id,
      timestamp: message.timestamp,
      level: message.metadata?.cost ? "COST" : "INFO",
      channel: message.channel,
      agent_id: message.sender_agent_id,
      message: message.content,
      usage: message.metadata,
      raw: message,
    }));
    return [...persisted, ...stream.events].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    );
  }, [stream.events, stream.messages]);

  const filteredEvents = useMemo(
    () =>
      messageEvents.filter((event) => {
        const agentMatches = !filters.agent || String(event.agent_id || "") === filters.agent;
        const channelMatches = !filters.channel || event.channel === filters.channel;
        const levelMatches = !filters.level || event.level === filters.level;
        // Filter out repetitive system messages
        const isSystemNoise = event.channel === "internal" && 
          (event.message?.includes("Connection interrupted") || 
           event.message?.includes("Reconnecting") ||
           event.message?.includes("Connected to run"));
        return agentMatches && channelMatches && levelMatches && !isSystemNoise;
      }),
    [filters, messageEvents],
  );

  const visibleEvents = filteredEvents.slice(-300);
  const usagePoints = useMemo(() => {
    const runPoints = runs
      .slice()
      .reverse()
      .map((run) => ({
        label: run.started_at ? new Date(run.started_at).toLocaleTimeString() : `Run ${run.id}`,
        tokens: run.total_tokens || 0,
        cost: Number(run.total_cost || 0),
      }));
    if (stream.run && selectedRunId) {
      runPoints.push({
        label: `Run ${selectedRunId}`,
        tokens: stream.run.total_tokens || 0,
        cost: Number(stream.run.total_cost || 0),
      });
    }
    return runPoints.slice(-30);
  }, [runs, selectedRunId, stream.run]);

  const totals = usagePoints.reduce(
    (sum, point) => ({
      tokens: sum.tokens + point.tokens,
      cost: sum.cost + point.cost,
    }),
    { tokens: 0, cost: 0 },
  );
  const budgetPct = Math.min(100, Math.round((totals.tokens / budgetLimit) * 100));

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [visibleEvents.length]);

  return (
    <div className="space-y-4">
      <section className="grid gap-3 rounded-md border border-line bg-surface p-4 lg:grid-cols-[1fr_240px_240px] lg:items-center">
        <div>
          <p className="text-xs font-semibold uppercase text-muted">Real-time monitor</p>
          <h2 className="mt-1 text-xl font-semibold">
            {selectedWorkflow?.name || "Workflow execution stream"}
          </h2>
          <p className="text-sm text-muted">
            {selectedRunId ? `Watching run #${selectedRunId}` : "Start a workflow to begin streaming."}
          </p>
        </div>
        <Metric label="Connection" value={stream.connectionState} tone={stream.isReconnecting ? "amber" : "emerald"} />
        <Metric label="Queued Logs" value={stream.queuedLogs.length} tone={stream.queuedLogs.length ? "amber" : "gray"} />
      </section>

      <div className="sticky top-0 z-10 rounded-md border border-line bg-surface p-2">
        <div className="flex flex-wrap items-center gap-2">
          {tabs.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`rounded-md px-3 py-2 text-sm font-semibold ${
                activeTab === tab ? "bg-ink text-white" : "text-muted hover:bg-soft hover:text-ink"
              }`}
            >
              {tab}
            </button>
          ))}
          <select
            value={selectedRunId}
            onChange={(event) => setSelectedRunId(event.target.value)}
            className="ml-auto rounded-md border border-line px-3 py-2 text-sm"
          >
            <option value="">Select run</option>
            {runs.map((run) => (
              <option key={run.id} value={run.id}>
                Run #{run.id} · {workflowById.get(run.workflow_id)?.name || `Workflow #${run.workflow_id}`}
              </option>
            ))}
          </select>
        </div>
      </div>

      {activeTab === "Active Runs" ? (
        <ActiveRunsPanel
          runs={runs}
          workflowById={workflowById}
          selectedRunId={selectedRunId}
          onStop={async (run) => {
            await stopWorkflowRun(run.id);
            await load();
          }}
          onSelect={(run) => {
            setSelectedRunId(String(run.id));
            setActiveTab("Message Stream");
          }}
        />
      ) : null}

      {activeTab === "Message Stream" ? (
        <MessageStreamPanel
          events={visibleEvents}
          filters={filters}
          setFilters={setFilters}
          agents={agents}
          agentById={agentById}
          isReconnecting={stream.isReconnecting}
          queuedLogs={stream.queuedLogs}
          bottomRef={bottomRef}
        />
      ) : null}

      {activeTab === "Token/Cost" ? (
        <TokenCostPanel points={usagePoints} totals={totals} budgetPct={budgetPct} />
      ) : null}

      {activeTab === "Audit Trail" ? (
        <AuditTimeline runId={selectedRunId} />
      ) : null}
    </div>
  );
}

function Metric({ label, value, tone }) {
  const colors = {
    amber: "text-amber-700",
    emerald: "text-emerald-700",
    gray: "text-muted",
  };
  return (
    <div className="rounded-md border border-line bg-surface-strong p-3">
      <p className="text-xs font-semibold uppercase text-muted">{label}</p>
      <p className={`mt-1 text-xl font-bold capitalize ${colors[tone] || colors.gray}`}>{value || "--"}</p>
    </div>
  );
}

function ActiveRunsPanel({ runs, workflowById, selectedRunId, onSelect, onStop }) {
  return (
    <div className="overflow-hidden rounded-md border border-line bg-surface">
      <div className="max-h-[620px] overflow-auto">
        <table className="min-w-full divide-y divide-line text-left text-sm">
          <thead className="sticky top-0 z-10 bg-soft text-xs uppercase text-muted">
            <tr>
              <th className="px-4 py-3">Workflow</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Progress</th>
              <th className="px-4 py-3">Tokens</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {runs.map((run) => {
              const progress = progressForRun(run.status);
              return (
                <tr key={run.id} className={String(run.id) === String(selectedRunId) ? "bg-soft/60" : ""}>
                  <td className="px-4 py-3">
                    <p className="font-semibold">{workflowById.get(run.workflow_id)?.name || `Workflow #${run.workflow_id}`}</p>
                    <p className="text-xs text-muted">Run #{run.id}</p>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${statusClass[run.status] || statusClass.pending}`}>
                      {run.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="h-2 w-48 rounded-full bg-soft">
                      <div className="h-2 rounded-full bg-ink transition-all" style={{ width: `${progress}%` }} />
                    </div>
                  </td>
                  <td className="px-4 py-3 text-muted">{(run.total_tokens || 0).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => onSelect(run)} className="rounded-md border border-line px-3 py-1.5 font-medium">
                      View
                    </button>
                    <button
                      onClick={() => onStop(run)}
                      disabled={!["pending", "running"].includes(run.status)}
                      className="ml-2 rounded-md border border-line px-3 py-1.5 font-medium disabled:text-muted disabled:opacity-60"
                    >
                      Stop
                    </button>
                  </td>
                </tr>
              );
            })}
            {!runs.length ? (
              <tr>
                <td colSpan="5" className="px-4 py-8 text-center text-muted">No workflow runs yet.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MessageStreamPanel({ events, filters, setFilters, agents, agentById, isReconnecting, queuedLogs, bottomRef }) {
  return (
    <div className="relative rounded-md border border-line bg-surface">
      {isReconnecting ? (
        <div className="absolute inset-x-0 top-0 z-20 border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-800">
          Reconnecting... {queuedLogs.length ? `${queuedLogs.length} local log${queuedLogs.length === 1 ? "" : "s"} queued` : "Syncing stream"}
        </div>
      ) : null}
      <div className="sticky top-14 z-10 flex flex-wrap gap-2 border-b border-line bg-surface p-3">
        <select value={filters.agent} onChange={(event) => setFilters((current) => ({ ...current, agent: event.target.value }))} className="rounded-md border border-line px-3 py-2 text-sm">
          <option value="">All agents</option>
          {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
        </select>
        <select value={filters.channel} onChange={(event) => setFilters((current) => ({ ...current, channel: event.target.value }))} className="rounded-md border border-line px-3 py-2 text-sm">
          <option value="">All channels</option>
          <option value="internal">internal</option>
          <option value="web">web</option>
          <option value="telegram">telegram</option>
        </select>
        <select value={filters.level} onChange={(event) => setFilters((current) => ({ ...current, level: event.target.value }))} className="rounded-md border border-line px-3 py-2 text-sm">
          <option value="">All levels</option>
          <option value="INFO">INFO</option>
          <option value="TOOL">TOOL</option>
          <option value="ERROR">ERROR</option>
          <option value="COST">COST</option>
        </select>
      </div>
      <div className="h-[620px] overflow-y-auto bg-soft/40 p-4">
        <div className="mx-auto max-w-5xl space-y-3">
          {events.map((event) => (
            <div key={event.id} className={`rounded-md border p-3 shadow-sm ${levelClass[event.level] || levelClass.INFO}`}>
              <div className="flex flex-wrap items-center gap-2 text-xs font-semibold">
                <span>{event.level}</span>
                <span>{new Date(event.timestamp).toLocaleTimeString()}</span>
                <span>{agentById.get(String(event.agent_id))?.name || (event.agent_id ? `Agent ${event.agent_id}` : "System")}</span>
                <span>{event.channel}</span>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm">{event.message}</p>
              {event.usage?.tokens ? (
                <p className="mt-2 text-xs font-semibold">
                  {event.usage.tokens.toLocaleString()} tokens · ${(event.usage.cost || 0).toFixed(6)}
                </p>
              ) : null}
            </div>
          ))}
          {!events.length ? <p className="py-16 text-center text-sm text-muted">Select a run to stream logs and messages.</p> : null}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}

function TokenCostPanel({ points, totals, budgetPct }) {
  return (
    <div className="space-y-4">
      <section className="grid gap-3 md:grid-cols-3">
        <Metric label="Tokens" value={totals.tokens.toLocaleString()} tone="gray" />
        <Metric label="Cost" value={`$${totals.cost.toFixed(6)}`} tone="emerald" />
        <div className="rounded-md border border-line bg-surface-strong p-3">
          <p className="text-xs font-semibold uppercase text-muted">Budget Gauge</p>
          <p className={`mt-1 text-xl font-bold ${budgetPct >= 90 ? "text-red-600" : budgetPct >= 70 ? "text-amber-600" : "text-emerald-600"}`}>
            {budgetPct}%
          </p>
          <div className="mt-2 h-2.5 rounded-full bg-soft">
            <div
              className={`h-2.5 rounded-full transition-all ${
                budgetPct >= 90 ? "bg-red-500" : budgetPct >= 70 ? "bg-amber-500" : "bg-emerald-600"
              }`}
              style={{ width: `${budgetPct}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-muted">
            {budgetPct >= 90 ? "⚠ Budget nearly exhausted" : budgetPct >= 70 ? "Budget warning threshold" : "Within budget"}
          </p>
        </div>
      </section>
      <section className="grid gap-4 xl:grid-cols-2">
        <UsageChart title="Token Stream" data={points} dataKey="tokens" color="#2563eb" />
        <UsageChart title="Cost Stream" data={points} dataKey="cost" color="#059669" />
      </section>
    </div>
  );
}

function UsageChart({ title, data, dataKey, color }) {
  return (
    <div className="rounded-md border border-line bg-surface p-4">
      <h3 className="text-sm font-semibold">{title}</h3>
      <div className="mt-4 h-72">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <XAxis dataKey="label" hide />
            <YAxis />
            <Tooltip />
            <Area type="monotone" dataKey={dataKey} stroke={color} fill={color} fillOpacity={0.16} strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function progressForRun(status) {
  if (status === "completed") return 100;
  if (status === "failed") return 100;
  if (status === "paused") return 65;
  if (status === "running") return 55;
  return 15;
}
