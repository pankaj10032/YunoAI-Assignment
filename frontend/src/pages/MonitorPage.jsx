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
    <div className="space-y-5">
      <section className="overflow-hidden rounded-3xl border border-line bg-gradient-to-br from-surface via-surface to-soft/60 p-5 shadow-sm transition-colors">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-muted">
              Live observability
            </p>
            <h2 className="text-3xl font-black tracking-tight">Follow runs, logs, and usage in one place.</h2>
            <p className="text-sm leading-6 text-muted sm:text-base">
              This panel combines execution state, message history, runtime logs, and token-cost trends
              so the review path feels concrete instead of theoretical.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:min-w-[520px]">
            <div className="card-lift rounded-2xl border border-line bg-surface/90 p-4 shadow-sm backdrop-blur">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted">Runs</p>
              <p className="mt-2 text-3xl font-black tracking-tight">{runs.length}</p>
            </div>
            <div className="card-lift rounded-2xl border border-line bg-surface/90 p-4 shadow-sm backdrop-blur">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted">Tokens</p>
              <p className="mt-2 text-3xl font-black tracking-tight" style={{ color: usageColor(latestTokens) }}>
                {totalTokens ? totalTokens.toLocaleString() : "--"}
              </p>
            </div>
            <div className="card-lift rounded-2xl border border-line bg-surface/90 p-4 shadow-sm backdrop-blur">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted">Latest</p>
              <p className="mt-2 text-3xl font-black tracking-tight">{latestTokens ? latestTokens.toLocaleString() : "--"}</p>
            </div>
            <div className="card-lift rounded-2xl border border-line bg-surface/90 p-4 shadow-sm backdrop-blur">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted">Cost</p>
              <p className="mt-2 text-3xl font-black tracking-tight">${tokenCost(totalTokens).toFixed(4)}</p>
            </div>
          </div>
        </div>
      </section>

      <div className="rounded-2xl border border-line bg-surface p-2 shadow-sm transition-colors">
        <div className="flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`rounded-xl px-3 py-2 text-sm font-semibold transition ${
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
