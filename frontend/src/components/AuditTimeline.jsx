import React, { useEffect, useRef, useState } from "react";
import { api } from "../services/api";

/* ── helpers ──────────────────────────────────────────────── */
const EVENT_ICONS = {
  workflow_started:   "🚀",
  workflow_completed: "✅",
  workflow_failed:    "❌",
  step_started:       "▶️",
  step_completed:     "✔️",
  step_failed:        "💥",
  tool_call:          "🔧",
  agent_message:      "💬",
  llm_call:           "🤖",
  checkpoint:         "💾",
  ui_error:           "⚠️",
  usage:              "📊",
  default:            "📋",
};

function icon(type = "") {
  for (const [key, val] of Object.entries(EVENT_ICONS)) {
    if (type.includes(key)) return val;
  }
  return EVENT_ICONS.default;
}

function fmtTs(ts) {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return ts;
  }
}

function badge(type = "") {
  if (type.includes("fail") || type.includes("error")) return "badge--error";
  if (type.includes("complete") || type.includes("success")) return "badge--success";
  if (type.includes("start")) return "badge--info";
  return "badge--neutral";
}

/* ── Event row ───────────────────────────────────────────── */
function EventRow({ event }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const payload = event.payload || {};
  const hasPayload = Object.keys(payload).length > 0;
  const jsonStr = JSON.stringify(payload, null, 2);

  function copy() {
    navigator.clipboard.writeText(jsonStr).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className={`audit-row ${expanded ? "audit-row--expanded" : ""}`}>
      <div className="audit-row__header" onClick={() => hasPayload && setExpanded((v) => !v)}>
        <span className="audit-row__icon">{icon(event.event_type || event.type || "")}</span>
        <span className="audit-row__time">{fmtTs(event.timestamp || event.created_at)}</span>
        <span className={`badge ${badge(event.event_type || "")}`}>
          {event.event_type || event.type || "event"}
        </span>
        <span className="audit-row__source">{event.source || event.agent_name || ""}</span>
        <span className="audit-row__summary">
          {event.message || event.description || payload.step || ""}
        </span>
        {event.correlation_id && (
          <span className="audit-row__cid" title={`Correlation ID: ${event.correlation_id}`}>
            #{String(event.correlation_id).slice(0, 8)}
          </span>
        )}
        {hasPayload && (
          <span className="audit-row__chevron">{expanded ? "▲" : "▼"}</span>
        )}
      </div>

      {expanded && (
        <div className="audit-row__body">
          <button className="audit-copy-btn" onClick={copy}>
            {copied ? "✔ Copied" : "Copy JSON"}
          </button>
          <pre className="audit-json">{jsonStr}</pre>
        </div>
      )}
    </div>
  );
}

/* ── Main component ──────────────────────────────────────── */
export default function AuditTimeline({ runId }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    api
      .get(`/api/audit/run/${runId}`)
      .then((res) => setEvents(res.data?.events || []))
      .catch((e) => setError(e?.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, [runId]);

  const filtered = filter.trim()
    ? events.filter((e) => {
        const hay = JSON.stringify(e).toLowerCase();
        return filter
          .toLowerCase()
          .split(" ")
          .every((word) => hay.includes(word));
      })
    : events;

  if (!runId) {
    return (
      <div className="audit-empty">
        Select a workflow run to view its audit timeline.
      </div>
    );
  }

  return (
    <div className="audit-timeline">
      {/* Header */}
      <div className="audit-header">
        <h3 className="audit-title">
          📋 Audit Timeline
          <span className="audit-run-id">Run #{runId}</span>
        </h3>
        <input
          className="audit-filter"
          placeholder="Filter events…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <span className="audit-count">
          {filtered.length} / {events.length} events
        </span>
      </div>

      {/* Body */}
      {loading && (
        <div className="audit-loading">
          <div className="tg-spinner" />
          Loading events…
        </div>
      )}

      {!loading && error && (
        <div className="audit-error">⚠ {error}</div>
      )}

      {!loading && !error && filtered.length === 0 && (
        <div className="audit-empty">No events found for this run.</div>
      )}

      {!loading && !error && filtered.length > 0 && (
        <div className="audit-list">
          {filtered.map((ev, i) => (
            <EventRow key={ev.id || i} event={ev} />
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
