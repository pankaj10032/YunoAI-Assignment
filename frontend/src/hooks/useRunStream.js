import { useCallback, useEffect, useRef, useState } from "react";

import { API_BASE_URL, getMessages, getRun } from "../services/api";

const MAX_BACKOFF_MS = 12000;

function parseEvent(value) {
  try {
    return JSON.parse(value);
  } catch {
    return { type: "message", message: value };
  }
}

function normalizeEvent(event, runId) {
  return {
    id: `${runId}-${event.type || "event"}-${event.timestamp || Date.now()}-${Math.random()}`,
    run_id: event.run_id || Number(runId),
    timestamp: event.timestamp || new Date().toISOString(),
    level: levelForEvent(event),
    channel: event.channel || "internal",
    agent_id: event.agent_id || event.sender_agent_id || null,
    message: event.message || event.result || event.content || JSON.stringify(event),
    usage: event.usage || event.metadata || null,
    raw: event,
  };
}

function levelForEvent(event) {
  if (event.type === "failed" || event.type === "error") return "ERROR";
  if (event.type === "tool") return "TOOL";
  if (event.usage || event.type === "cost") return "COST";
  return "INFO";
}

export function useRunStream(runId, { enabled = true, onSync } = {}) {
  const [events, setEvents] = useState([]);
  const [messages, setMessages] = useState([]);
  const [run, setRun] = useState(null);
  const [connectionState, setConnectionState] = useState(runId ? "connecting" : "idle");
  const [queuedLogs, setQueuedLogs] = useState([]);
  const socketRef = useRef(null);
  const closedRef = useRef(false);
  const retriesRef = useRef(0);
  const reconnectTimerRef = useRef(null);

  const appendEvent = useCallback(
    (event, queued = false) => {
      const normalized = normalizeEvent(event, runId);
      setEvents((current) => [...current.slice(-499), normalized]);
      if (queued) setQueuedLogs((current) => [...current.slice(-99), normalized]);
      if (normalized.usage) {
        setRun((current) => ({
          ...(current || {}),
          total_tokens: normalized.usage.tokens ?? current?.total_tokens ?? 0,
          total_cost: normalized.usage.cost ?? current?.total_cost ?? 0,
        }));
      }
    },
    [runId],
  );

  const onSyncRef = useRef(onSync);
  useEffect(() => {
    onSyncRef.current = onSync;
  }, [onSync]);

  const syncLatest = useCallback(async () => {
    if (!runId) return;
    const [latestRun, latestMessages] = await Promise.all([
      getRun(runId).catch(() => null),
      getMessages(runId).catch(() => []),
    ]);
    if (latestRun) setRun(latestRun);
    setMessages(latestMessages);
    onSyncRef.current?.({ run: latestRun, messages: latestMessages });
  }, [runId]);

  useEffect(() => {
    if (!runId || !enabled) {
      setConnectionState(runId ? "paused" : "idle");
      return undefined;
    }

    closedRef.current = false;
    setEvents([]);
    setMessages([]);
    setQueuedLogs([]);

    const connect = () => {
      if (closedRef.current) return;
      setConnectionState(retriesRef.current ? "reconnecting" : "connecting");
      const wsBase = API_BASE_URL.replace(/^http/, "ws");
      const socket = new WebSocket(`${wsBase}/ws/run/${runId}`);
      socketRef.current = socket;

      socket.onopen = () => {
        retriesRef.current = 0;
        setConnectionState("connected");
        setQueuedLogs([]);
        appendEvent({ type: "connected", message: `Connected to run #${runId}` });
        syncLatest().catch(() => {});
      };

      socket.onmessage = (message) => {
        const event = parseEvent(message.data);
        appendEvent(event);
      };

      socket.onerror = () => {
        appendEvent({ type: "error", message: "WebSocket connection error" }, true);
      };

      socket.onclose = () => {
        if (closedRef.current) return;
        setConnectionState("reconnecting");
        // Only log reconnection message if we had a successful connection before
        if (retriesRef.current === 0) {
          appendEvent({ type: "log", message: "Connection interrupted. Reconnecting..." }, true);
        }
        const delay = Math.min(2 ** retriesRef.current * 1000, MAX_BACKOFF_MS);
        retriesRef.current += 1;
        // Stop reconnecting after 5 attempts
        if (retriesRef.current > 5) {
          setConnectionState("disconnected");
          appendEvent({ type: "error", message: "Failed to reconnect after 5 attempts. Please refresh the page." }, true);
          return;
        }
        reconnectTimerRef.current = window.setTimeout(connect, delay);
      };
    };

    syncLatest().catch(() => {});
    connect();

    return () => {
      closedRef.current = true;
      window.clearTimeout(reconnectTimerRef.current);
      socketRef.current?.close();
    };
  }, [appendEvent, enabled, runId, syncLatest]);

  return {
    events,
    messages,
    run,
    connectionState,
    isReconnecting: connectionState === "reconnecting" || connectionState === "connecting",
    queuedLogs,
    syncLatest,
  };
}
