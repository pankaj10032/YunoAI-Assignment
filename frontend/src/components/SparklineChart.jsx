import React from "react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

const COST_PER_1K_TOKENS = 0.003;

export function tokenCost(tokens = 0) {
  return (Number(tokens || 0) / 1000) * COST_PER_1K_TOKENS;
}

export function usageColor(tokens = 0) {
  if (tokens > 5000) return "#dc2626";
  if (tokens >= 1000) return "#ca8a04";
  return "#16a34a";
}

function normalizeData(data = []) {
  return data
    .map((point, index) => ({
      timestamp: point.timestamp || point.started_at || point.completed_at || `Run ${index + 1}`,
      tokens: Number(point.tokens || point.total_tokens || 0),
    }))
    .filter((point) => Number.isFinite(point.tokens));
}

function SparkTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const tokens = payload[0].value || 0;
  return (
    <div className="rounded-md border border-line bg-surface px-2 py-1 text-xs shadow-sm">
      <p className="font-semibold">{tokens.toLocaleString()} tokens</p>
      <p className="text-muted">${tokenCost(tokens).toFixed(4)}</p>
      <p className="text-muted">{formatLabel(label)}</p>
    </div>
  );
}

export default function SparklineChart({
  data = [],
  color,
  height = 48,
  fallback = "-- tokens",
}) {
  const chartData = normalizeData(data);
  const total = chartData.reduce((sum, point) => sum + point.tokens, 0);
  const stroke = color || usageColor(total);

  if (!chartData.length) {
    return (
      <div
        className="flex items-center justify-center rounded-md border border-line bg-surface-strong text-xs font-semibold text-muted"
        style={{ height }}
      >
        {fallback}
      </div>
    );
  }

  return (
    <div className="min-w-0" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 4, right: 2, bottom: 2, left: 2 }}>
          <defs>
            <linearGradient id={`spark-${stroke.replace("#", "")}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.32} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0.03} />
            </linearGradient>
          </defs>
          <Tooltip
            content={<SparkTooltip />}
            cursor={{ stroke, strokeOpacity: 0.2 }}
            animationDuration={120}
          />
          <Area
            type="monotone"
            dataKey="tokens"
            stroke={stroke}
            strokeWidth={2}
            fill={`url(#spark-${stroke.replace("#", "")})`}
            isAnimationActive
            animationDuration={260}
            dot={false}
            activeDot={{ r: 3, strokeWidth: 0, fill: stroke }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function formatLabel(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}