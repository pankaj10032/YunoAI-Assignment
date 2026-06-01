import React, { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/* ── helpers ──────────────────────────────────────────────── */
const COST_PER_1K = 0.003;

export function tokenCost(tokens = 0) {
  return (Number(tokens || 0) / 1000) * COST_PER_1K;
}

function fmtLabel(value) {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}

function normalizeData(data = []) {
  return data
    .map((p, i) => ({
      label: p.timestamp || p.started_at || p.completed_at || `Run ${i + 1}`,
      tokens: Number(p.tokens || p.total_tokens || 0),
      cost: Number(p.cost || p.total_cost || 0) || tokenCost(p.tokens || p.total_tokens || 0),
    }))
    .filter((p) => Number.isFinite(p.tokens));
}

function colorFor(tokens = 0) {
  if (tokens > 5000) return "#ef4444";
  if (tokens >= 1000) return "#f59e0b";
  return "#10b981";
}

/* ── CSV export ──────────────────────────────────────────── */
function exportCsv(data, filename = "token_usage.csv") {
  const header = "label,tokens,cost_usd\n";
  const rows = data
    .map((r) => `"${r.label}",${r.tokens},${r.cost.toFixed(6)}`)
    .join("\n");
  const blob = new Blob([header + rows], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/* ── Custom tooltip ──────────────────────────────────────── */
function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const tokens = payload[0]?.value ?? 0;
  const cost = payload[1]?.value ?? tokenCost(tokens);
  return (
    <div
      style={{
        background: "var(--color-surface, #fff)",
        border: "1px solid var(--color-border, #d8dee4)",
        borderRadius: 8,
        padding: "8px 12px",
        fontSize: 12,
        boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
      }}
    >
      <p style={{ fontWeight: 600, marginBottom: 2 }}>{fmtLabel(label)}</p>
      <p style={{ color: "#3b82f6" }}>{tokens.toLocaleString()} tokens</p>
      <p style={{ color: "#10b981" }}>${cost.toFixed(4)} est. cost</p>
    </div>
  );
}

/* ── Main component ──────────────────────────────────────── */
export default function DashboardAnalytics({ data = [], title = "Token Usage & Cost" }) {
  const chartData = useMemo(() => normalizeData(data), [data]);
  const totalTokens = chartData.reduce((s, r) => s + r.tokens, 0);
  const totalCost = chartData.reduce((s, r) => s + r.cost, 0);
  const stroke = colorFor(totalTokens);

  if (!chartData.length) {
    return (
      <div className="dashboard-analytics dashboard-analytics--empty">
        <p>No usage data available yet.</p>
      </div>
    );
  }

  return (
    <div className="dashboard-analytics">
      {/* Header row */}
      <div className="dashboard-analytics__header">
        <h3 className="dashboard-analytics__title">{title}</h3>
        <div className="dashboard-analytics__meta">
          <span className="badge badge--tokens">
            {totalTokens.toLocaleString()} tokens
          </span>
          <span className="badge badge--cost">${totalCost.toFixed(4)}</span>
          <button
            id="export-csv-btn"
            className="btn-export"
            onClick={() => exportCsv(chartData)}
            title="Export as CSV"
          >
            ↓ CSV
          </button>
        </div>
      </div>

      {/* Dual-area chart */}
      <ResponsiveContainer width="100%" height={160}>
        <AreaChart
          data={chartData}
          margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
        >
          <defs>
            <linearGradient id="grad-tokens" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.3} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="grad-cost" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="var(--color-border, #e5e7eb)"
            strokeOpacity={0.5}
          />
          <XAxis
            dataKey="label"
            tickFormatter={fmtLabel}
            tick={{ fontSize: 10, fill: "var(--color-muted, #667085)" }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            yAxisId="tokens"
            orientation="left"
            tick={{ fontSize: 10, fill: "var(--color-muted, #667085)" }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            yAxisId="cost"
            orientation="right"
            tickFormatter={(v) => `$${v.toFixed(3)}`}
            tick={{ fontSize: 10, fill: "#3b82f6" }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip content={<CustomTooltip />} animationDuration={100} />
          <Area
            yAxisId="tokens"
            type="monotone"
            dataKey="tokens"
            stroke={stroke}
            strokeWidth={2}
            fill="url(#grad-tokens)"
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0, fill: stroke }}
            animationDuration={300}
          />
          <Area
            yAxisId="cost"
            type="monotone"
            dataKey="cost"
            stroke="#3b82f6"
            strokeWidth={1.5}
            fill="url(#grad-cost)"
            dot={false}
            activeDot={{ r: 3, strokeWidth: 0, fill: "#3b82f6" }}
            animationDuration={300}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
