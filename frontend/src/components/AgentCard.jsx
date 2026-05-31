import React from "react";
import ExportButton from "./ExportButton";
import SparklineChart, { tokenCost, usageColor } from "./SparklineChart";

function readableItems(items = []) {
  return items
    .map((item) => (typeof item === "string" ? item : item.name))
    .filter(Boolean);
}

function initials(name = "AI") {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

function toolLabel(tool) {
  const labels = {
    search: "Search",
    calculator: "Calculator",
    memory: "Memory",
  };
  return labels[tool] || tool;
}

function channelLabel(channel) {
  const labels = {
    web: "Web",
    telegram: "Telegram",
    internal: "Internal",
    slack: "Slack",
    whatsapp: "WhatsApp",
  };
  return labels[channel] || channel;
}

export function AgentCardSkeleton() {
  return (
    <div className="min-h-72 rounded-md border border-line bg-surface p-4 transition-colors">
      <div className="flex items-start gap-3">
        <div className="h-12 w-12 animate-pulse rounded-md bg-soft" />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="h-4 w-2/3 animate-pulse rounded bg-soft" />
          <div className="h-3 w-1/2 animate-pulse rounded bg-soft" />
        </div>
      </div>
      <div className="mt-5 space-y-3">
        <div className="h-3 w-full animate-pulse rounded bg-soft" />
        <div className="h-3 w-5/6 animate-pulse rounded bg-soft" />
        <div className="h-3 w-2/3 animate-pulse rounded bg-soft" />
      </div>
      <div className="mt-6 flex flex-wrap gap-2">
        <div className="h-7 w-20 animate-pulse rounded-full bg-soft" />
        <div className="h-7 w-24 animate-pulse rounded-full bg-soft" />
      </div>
    </div>
  );
}

export default function AgentCard({ agent, usageData = [], onEdit, onTest, onDelete }) {
  const tools = readableItems(agent.tools);
  const channels = readableItems(agent.channels);
  const isActive = channels.length > 0;
  const latestTokens = usageData.at(-1)?.tokens || 0;
  const exportData = {
    name: agent.name,
    role: agent.role,
    system_prompt: agent.system_prompt,
    model: agent.model,
    tools: agent.tools,
    channels: agent.channels,
    memory_enabled: agent.memory_enabled,
    guardrails: agent.guardrails,
    schedule: agent.schedule,
  };

  return (
    <article className="group relative flex min-h-72 flex-col rounded-md border border-line bg-surface p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:border-ink/30 hover:shadow-md focus-within:border-ink/40">
      <div className="absolute right-3 top-3 cursor-grab rounded border border-line bg-soft px-2 py-1 text-xs font-semibold text-muted">
        ::
      </div>

      <div className="flex items-start gap-3 pr-10">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-soft text-sm font-bold text-ink">
          {initials(agent.name)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-base font-semibold">{agent.name}</h3>
            <span
              className={`rounded-full px-2 py-1 text-xs font-semibold ${
                isActive
                  ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200"
                  : "bg-soft text-muted"
              }`}
            >
              {isActive ? "active" : "inactive"}
            </span>
          </div>
          <p className="mt-1 line-clamp-2 text-sm text-muted">
            {agent.role || "No role set"}
          </p>
        </div>

        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between gap-3">
            <p className="text-xs font-semibold uppercase text-muted">Usage</p>
            <span
              className="rounded-full px-2 py-1 text-xs font-semibold"
              style={{
                color: usageColor(latestTokens),
                background: `${usageColor(latestTokens)}1A`,
              }}
            >
              {latestTokens ? `${latestTokens.toLocaleString()} tokens` : "-- tokens"}
            </span>
          </div>
          <SparklineChart
            data={usageData}
            color={usageColor(latestTokens)}
            height={46}
          />
          {latestTokens ? (
            <p className="mt-1 text-xs text-muted">
              Last run est. ${tokenCost(latestTokens).toFixed(4)}
            </p>
          ) : null}
        </div>
      </div>

      <div className="mt-4 flex-1">
        <p className="text-xs font-semibold uppercase text-muted">Model</p>
        <p className="mt-1 text-sm font-medium">{agent.model}</p>

        <div className="mt-4">
          <p className="text-xs font-semibold uppercase text-muted">Tools</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {tools.length ? (
              tools.map((tool) => (
                <span key={tool} className="rounded-full border border-line bg-soft px-2.5 py-1 text-xs font-semibold">
                  {toolLabel(tool)}
                </span>
              ))
            ) : (
              <span className="text-sm text-muted">No tools</span>
            )}
          </div>
        </div>

        <div className="mt-4">
          <p className="text-xs font-semibold uppercase text-muted">Channels</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {channels.length ? (
              channels.map((channel) => (
                <span key={channel} className="rounded-full border border-line bg-surface-strong px-2.5 py-1 text-xs font-semibold">
                  {channelLabel(channel)}
                </span>
              ))
            ) : (
              <span className="text-sm text-muted">No channels</span>
            )}
          </div>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-3 gap-2 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
        <button
          type="button"
          onClick={() => onEdit(agent)}
          className="rounded-md border border-line px-3 py-2 text-sm font-semibold transition-colors hover:bg-soft"
        >
          Edit
        </button>
        <button
          type="button"
          onClick={() => onTest(agent)}
          className="rounded-md border border-line px-3 py-2 text-sm font-semibold transition-colors hover:bg-soft"
        >
          Test
        </button>
        <button
          type="button"
          onClick={() => onDelete(agent)}
          className="rounded-md border border-red-200 px-3 py-2 text-sm font-semibold text-red-700 transition-colors hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-950/30"
        >
          Delete
        </button>
      </div>
      <div className="mt-3 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
        <ExportButton data={exportData} label={`agent-${agent.name}`} />
      </div>
    </article>
  );
}