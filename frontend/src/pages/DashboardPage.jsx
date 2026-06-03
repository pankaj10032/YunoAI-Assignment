import React from "react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { getAgents, getAllMessages, getWorkflows, runWorkflow } from "../services/api";

export default function DashboardPage() {
  const [agents, setAgents] = useState([]);
  const [workflows, setWorkflows] = useState([]);
  const [messages, setMessages] = useState([]);
  const [runs, setRuns] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getAgents(), getWorkflows(), getAllMessages({ limit: 50 })])
      .then(([agentData, workflowData, messageData]) => {
        setAgents(agentData);
        setWorkflows(workflowData);
        setMessages(messageData);
      })
      .catch((err) => {
        setError(err.response?.data?.detail || "Could not load dashboard data.");
      });
  }, []);

  const templates = useMemo(
    () => workflows.filter((workflow) => workflow.is_template),
    [workflows],
  );

  const handleRunTemplate = async () => {
    const template = templates[0];
    if (!template) return;
    setError("");
    try {
      const run = await runWorkflow(template.id, {
        input: "Run the demo template with a concise output.",
      });
      setRuns((current) => [run, ...current]);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not run template.");
    }
  };

  const statCards = [
    { label: "Total Agents", value: agents.length },
    {
      label: "Active Workflows",
      value: workflows.filter((workflow) => !workflow.is_template).length,
    },
    { label: "Messages Loaded", value: messages.length },
    {
      label: "Token Usage",
      value: runs.reduce((sum, run) => sum + (run.total_tokens || 0), 0),
    },
  ];

  return (
    <div className="space-y-6">
      {error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 shadow-sm">
          {error}
        </div>
      ) : null}

      <section className="overflow-hidden rounded-3xl border border-line bg-gradient-to-br from-surface via-surface to-soft/60 p-6 shadow-[0_20px_60px_rgba(0,0,0,0.06)] transition-colors">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl space-y-3">
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-muted">
              Orchestration control room
            </p>
            <h2 className="text-3xl font-black tracking-tight sm:text-4xl">
              Ship, observe, and steer multi-agent work from one place.
            </h2>
            <p className="max-w-xl text-sm leading-6 text-muted sm:text-base">
              This dashboard surfaces agent capacity, workflow activity, message volume,
              and the latest run actions so reviewers can understand the platform at a glance.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:min-w-[520px]">
            {statCards.map((card) => (
              <div
                key={card.label}
                className="card-lift rounded-2xl border border-line bg-surface/90 p-4 shadow-sm backdrop-blur"
              >
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted">
                  {card.label}
                </p>
                <p className="mt-2 text-3xl font-black tracking-tight">{card.value}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="overflow-hidden rounded-3xl border border-line bg-surface shadow-sm transition-colors">
          <div className="flex items-center justify-between border-b border-line px-5 py-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted">
                Execution feed
              </p>
              <h3 className="mt-1 text-lg font-semibold">Recent workflow runs</h3>
            </div>
            <div className="rounded-full bg-soft px-3 py-1 text-xs font-semibold text-muted">
              Live review
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-line text-left text-sm">
              <thead className="bg-soft/80 text-xs uppercase tracking-[0.14em] text-muted">
                <tr>
                  <th className="px-4 py-3">Run ID</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Logs</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {runs.length ? (
                  runs.map((run) => (
                    <tr key={run.run_id}>
                      <td className="px-4 py-3">#{run.run_id}</td>
                      <td className="px-4 py-3">{run.status}</td>
                      <td className="px-4 py-3 text-muted">{run.websocket_url}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td className="px-4 py-8 text-center text-muted" colSpan="3">
                      No runs launched from this session yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card-lift rounded-3xl border border-line bg-surface p-5 shadow-sm transition-colors">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted">
              Shortcuts
            </p>
            <h3 className="mt-1 text-lg font-semibold">Quick actions</h3>
          </div>
          <div className="mt-4 grid gap-3">
            <Link
              to="/agents"
              className="card-lift rounded-2xl border border-line bg-surface-strong px-4 py-3 text-sm font-semibold shadow-sm hover:border-ink/20"
            >
              Create Agent
            </Link>
            <Link
              to="/workflows"
              className="card-lift rounded-2xl border border-line bg-surface-strong px-4 py-3 text-sm font-semibold shadow-sm hover:border-ink/20"
            >
              Create Workflow
            </Link>
            <button
              onClick={handleRunTemplate}
              disabled={!templates.length}
              className="card-lift rounded-2xl bg-ink px-4 py-3 text-left text-sm font-semibold text-white shadow-lg shadow-black/10 disabled:opacity-50"
            >
              Run Template
            </button>
          </div>
          <div className="mt-6 rounded-2xl border border-line bg-soft/40 p-4 text-sm text-muted">
            Use the template runner to generate a visible run in the monitor view and quickly validate the end-to-end path.
          </div>
        </div>
      </section>
    </div>
  );
}
