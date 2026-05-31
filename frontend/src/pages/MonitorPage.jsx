import React from "react";
import { useEffect, useMemo, useState } from "react";

import ActiveRuns from "../components/ActiveRuns";
import LogViewer from "../components/LogViewer";
import MessageHistory from "../components/MessageHistory";
import RunDetails from "../components/RunDetails";
import SparklineChart, { tokenCost, usageColor } from "../components/SparklineChart";
import TokenUsage from "../components/TokenUsage";
import { getRuns } from "../services/api";

const tabs = ["Active Runs", "Message History", "Token Usage", "System Logs"];

export default function MonitorPage() {
  const [activeTab, setActiveTab] = useState(tabs[0]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [runs, setRuns] = useState([]);

  useEffect(() => {
    let active = true;
    const load = () =>
      getRuns({ limit: 30 })
        .then((data) => active && setRuns(data))
        .catch(() => active && setRuns([]));
    load();
    const timer = window.setInterval(load, 7000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const usageData = useMemo(
    () =>
      runs
        .slice()
        .reverse()
        .map((run) => ({
          timestamp: run.completed_at || run.started_at,
          tokens: run.total_tokens || 0,
        })),
    [runs],
  );
  const totalTokens = usageData.reduce((sum, point) => sum + point.tokens, 0);
  const latestTokens = usageData.at(-1)?.tokens || 0;

  return (
    <div className="space-y-4">
      <section className="grid gap-3 rounded-md border border-line bg-surface p-4 transition-colors lg:grid-cols-[1fr_220px_220px] lg:items-center">
        <div>
          <p className="text-xs font-semibold uppercase text-muted">Run Usage</p>
          <h3 className="mt-1 text-lg font-semibold">Token and cost trend</h3>
          <p className="text-sm text-muted">
            {usageData.length ? `${usageData.length} recent runs` : "No run usage yet"}
          </p>
        </div>
        <div className="rounded-md border border-line bg-surface-strong p-3">
          <p className="text-xs font-semibold uppercase text-muted">Tokens</p>
          <p className="mt-1 text-xl font-bold" style={{ color: usageColor(latestTokens) }}>
            {totalTokens ? totalTokens.toLocaleString() : "--"}
          </p>
          <p className="text-xs text-muted">latest {latestTokens ? latestTokens.toLocaleString() : "--"}</p>
        </div>
        <div className="rounded-md border border-line bg-surface-strong p-3">
          <p className="text-xs font-semibold uppercase text-muted">Estimated Cost</p>
          <p className="mt-1 text-xl font-bold">${tokenCost(totalTokens).toFixed(4)}</p>
          <SparklineChart data={usageData} color={usageColor(latestTokens)} height={42} />
        </div>
      </section>

      <div className="rounded-md border border-line bg-surface p-2 transition-colors">
        <div className="flex flex-wrap gap-2">
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
        </div>
      </div>

      {activeTab === "Active Runs" ? <ActiveRuns onSelectRun={setSelectedRun} /> : null}
      {activeTab === "Message History" ? <MessageHistory /> : null}
      {activeTab === "Token Usage" ? <TokenUsage /> : null}
      {activeTab === "System Logs" ? <LogViewer /> : null}

      <RunDetails run={selectedRun} onClose={() => setSelectedRun(null)} />
    </div>
  );
}