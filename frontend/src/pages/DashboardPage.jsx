import React from "react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { getAgents, getWorkflows, runWorkflow } from "../services/api";

export default function DashboardPage() {
  const [agents, setAgents] = useState([]);
  const [workflows, setWorkflows] = useState([]);
  const [runs, setRuns] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getAgents(), getWorkflows()])
      .then(([agentData, workflowData]) => {
        setAgents(agentData);
        setWorkflows(workflowData);
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
    { label: "Messages Today", value: "0" },
    {
      label: "Token Usage",
      value: runs.reduce((sum, run) => sum + (run.total_tokens || 0), 0),
    },
  ];

  return (
    <div className="space-y-5">
      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {statCards.map((card) => (
          <div key={card.label} className="rounded-md border border-line bg-surface p-4 transition-colors">
            <p className="text-sm font-medium text-muted">{card.label}</p>
            <p className="mt-2 text-3xl font-bold">{card.value}</p>
          </div>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-[1fr_320px]">
        <div className="rounded-md border border-line bg-surface transition-colors">
          <div className="border-b border-line px-4 py-3">
            <h3 className="font-semibold">Recent Workflow Runs</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-line text-left text-sm">
            <thead className="bg-soft text-xs uppercase text-muted">
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

        <div className="rounded-md border border-line bg-surface p-4 transition-colors">
          <h3 className="font-semibold">Quick Actions</h3>
          <div className="mt-4 grid gap-2">
            <Link
              to="/agents"
              className="rounded-md border border-line px-3 py-2 text-sm font-medium"
            >
              Create Agent
            </Link>
            <Link
              to="/workflows"
              className="rounded-md border border-line px-3 py-2 text-sm font-medium"
            >
              Create Workflow
            </Link>
            <button
              onClick={handleRunTemplate}
              disabled={!templates.length}
              className="rounded-md bg-ink px-3 py-2 text-left text-sm font-semibold text-white disabled:opacity-50"
            >
              Run Template
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}