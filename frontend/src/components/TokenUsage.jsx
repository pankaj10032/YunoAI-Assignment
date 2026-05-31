import React from "react";
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getAllMessages, getRuns } from "../services/api";

export default function TokenUsage() {
  const [messages, setMessages] = useState([]);
  const [runs, setRuns] = useState([]);
  const [range, setRange] = useState("7d");

  useEffect(() => {
    Promise.all([getAllMessages({ limit: 1000 }), getRuns({ limit: 500 })])
      .then(([messageData, runData]) => {
        setMessages(messageData);
        setRuns(runData);
      })
      .catch(() => {
        setMessages([]);
        setRuns([]);
      });
  }, [range]);

  const tokensByAgent = useMemo(() => {
    const grouped = {};
    messages.forEach((message) => {
      const key = message.sender_agent_id ? `Agent ${message.sender_agent_id}` : "External";
      grouped[key] = (grouped[key] || 0) + (message.metadata?.tokens || 0);
    });
    return Object.entries(grouped).map(([agent, tokens]) => ({ agent, tokens }));
  }, [messages]);

  const costOverTime = useMemo(() => {
    const grouped = {};
    runs.forEach((run) => {
      const day = run.started_at ? new Date(run.started_at).toLocaleDateString() : "unknown";
      grouped[day] = (grouped[day] || 0) + (run.total_cost || 0);
    });
    return Object.entries(grouped).map(([day, cost]) => ({ day, cost }));
  }, [runs]);

  const totalTokens = messages.reduce((sum, item) => sum + (item.metadata?.tokens || 0), 0);
  const totalCost = runs.reduce((sum, run) => sum + (run.total_cost || 0), 0);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between rounded-md border border-line bg-surface p-4 transition-colors">
        <div>
          <p className="text-sm text-muted">Total usage</p>
          <p className="text-2xl font-bold">{totalTokens} tokens · ${totalCost.toFixed(6)}</p>
        </div>
        <select value={range} onChange={(event) => setRange(event.target.value)} className="rounded-md border border-line px-3 py-2 text-sm">
          <option value="24h">Last 24h</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
        </select>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-md border border-line bg-surface p-4 transition-colors">
          <h3 className="text-sm font-semibold">Tokens per Agent</h3>
          <div className="mt-4 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={tokensByAgent}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="agent" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="tokens" fill="#172026" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="rounded-md border border-line bg-surface p-4 transition-colors">
          <h3 className="text-sm font-semibold">Cost over Time</h3>
          <div className="mt-4 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={costOverTime}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="day" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="cost" stroke="#0f766e" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}