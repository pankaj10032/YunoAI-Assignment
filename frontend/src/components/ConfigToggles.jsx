import React from "react";
const configItems = [
  {
    id: "search",
    group: "tools",
    label: "Search",
    icon: "S",
    description: "Web search via DuckDuckGo",
    tooltip: "Web search via DuckDuckGo",
  },
  {
    id: "calculator",
    group: "tools",
    label: "Calculator",
    icon: "C",
    description: "Run calculations during tasks",
    tooltip: "Math and numeric helper",
  },
  {
    id: "memory",
    group: "tools",
    label: "Memory",
    icon: "M",
    description: "Keep short context between steps",
    tooltip: "Stores lightweight agent context",
  },
  {
    id: "telegram",
    group: "channels",
    label: "Telegram",
    icon: "T",
    description: "Receive and send Telegram messages",
    tooltip: "Telegram bot channel",
  },
  {
    id: "web",
    group: "channels",
    label: "Web",
    icon: "W",
    description: "Use the web app test console",
    tooltip: "Browser-based agent testing",
  },
];

function ToggleSwitch({ enabled }) {
  return (
    <span
      className={`flex h-6 w-11 items-center rounded-full p-0.5 transition-colors ${
        enabled ? "bg-emerald-500" : "bg-line"
      }`}
      aria-hidden="true"
    >
      <span
        className={`h-5 w-5 rounded-full bg-white shadow-sm transition-transform ${
          enabled ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </span>
  );
}

export default function ConfigToggles({
  tools = [],
  channels = [],
  onToolsChange,
  onChannelsChange,
  disabled = false,
  maxTools = 3,
  maxChannels = 2,
}) {
  const toolSet = new Set(tools);
  const channelSet = new Set(channels);
  const toolLimitReached = toolSet.size >= maxTools;
  const channelLimitReached = channelSet.size >= maxChannels;

  const toggleItem = (item) => {
    if (disabled) return;
    if (item.group === "tools") {
      const next = new Set(toolSet);
      if (next.has(item.id)) {
        next.delete(item.id);
      } else if (!toolLimitReached) {
        next.add(item.id);
      }
      onToolsChange([...next]);
      return;
    }

    const next = new Set(channelSet);
    if (next.has(item.id)) {
      next.delete(item.id);
    } else if (!channelLimitReached) {
      next.add(item.id);
    }
    onChannelsChange([...next]);
  };

  return (
    <section className="space-y-3">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h4 className="text-sm font-semibold">Tools and Channels</h4>
          <p className="text-xs text-muted">Toggle capabilities for this agent.</p>
        </div>
        <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">
          ✓ Config saved
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {configItems.map((item) => {
          const enabled =
            item.group === "tools" ? toolSet.has(item.id) : channelSet.has(item.id);
          const limitReached =
            item.group === "tools" ? toolLimitReached : channelLimitReached;
          const isDisabled = disabled || (!enabled && limitReached);
          return (
            <button
              key={`${item.group}-${item.id}`}
              type="button"
              title={item.tooltip}
              disabled={isDisabled}
              onClick={() => toggleItem(item)}
              className={`min-h-28 rounded-md border p-3 text-left transition-all focus:outline-none focus:ring-2 focus:ring-ink/30 disabled:cursor-not-allowed disabled:opacity-55 ${
                enabled
                  ? "border-emerald-400 bg-emerald-50 dark:bg-emerald-950/30"
                  : "border-line bg-surface hover:bg-soft"
              }`}
              aria-pressed={enabled}
            >
              <span className="flex items-start justify-between gap-3">
                <span className="flex min-w-0 gap-3">
                  <span
                    className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-sm font-bold ${
                      enabled ? "bg-emerald-600 text-white" : "bg-soft text-ink"
                    }`}
                  >
                    {item.icon}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold">{item.label}</span>
                    <span className="mt-1 block text-xs leading-5 text-muted">
                      {item.description}
                    </span>
                  </span>
                </span>
                <ToggleSwitch enabled={enabled} />
              </span>
            </button>
          );
        })}
      </div>

      {!channels.length ? (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Select at least one channel before saving.
        </p>
      ) : null}
      {(toolLimitReached || channelLimitReached) ? (
        <p className="text-xs text-muted">
          Limit reached: up to {maxTools} tools and {maxChannels} channels can be enabled.
        </p>
      ) : null}
    </section>
  );
}