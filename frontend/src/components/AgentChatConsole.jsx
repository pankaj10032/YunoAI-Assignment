import React from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import { executeAgent, getMessages } from "../services/api";
import { connectRunSocket } from "../services/websocket";

function formatTime(timestamp) {
  try {
    return new Date(timestamp).toLocaleString();
  } catch {
    return "";
  }
}

function normalizeMessage(message) {
  const content = String(message.content || message.message || "").trim();
  const metadata = message.metadata || message.message_metadata || {};
  return {
    id: message.id || `${message.role || message.channel || "msg"}-${message.timestamp || Date.now()}`,
    role: message.role || (message.sender_agent_id ? "agent" : "assistant"),
    content,
    metadata,
    timestamp: message.timestamp || new Date().toISOString(),
    senderName: message.senderName || message.sender_name || message.agent_name || "Agent",
  };
}

function detectToolCall(content, metadata = {}) {
  const toolName =
    metadata.tool_name ||
    metadata.tool ||
    metadata.name ||
    (content.match(/\b(SearchTool|CalculatorTool|MemoryTool)\b/i)?.[1] || "");
  if (!toolName) return null;

  const results =
    metadata.results ||
    metadata.result_count ||
    content.match(/(\d+)\s+results?/i)?.[1] ||
    content.match(/found\s+(\d+)/i)?.[1] ||
    "";

  return {
    name: toolName.replace(/Tool$/i, ""),
    results: results ? Number(results) : null,
    details: content,
  };
}

function buildAssistantMessage(payload) {
  const content =
    payload.result ||
    payload.message ||
    payload.content ||
    payload.text ||
    "Execution completed.";
  const metadata = payload.usage || payload.metadata || {};
  return normalizeMessage({
    id: `${payload.run_id || "run"}-${payload.type || "assistant"}-${Date.now()}`,
    role: "agent",
    content,
    metadata: {
      ...metadata,
      tool_call: detectToolCall(content, payload),
    },
    timestamp: new Date().toISOString(),
    senderName: payload.agent_name || "Agent",
  });
}

export default function AgentChatConsole({ agent, onClose }) {
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [activeRunId, setActiveRunId] = useState(null);
  const [socketState, setSocketState] = useState("idle");
  const [error, setError] = useState("");
  const [queue, setQueue] = useState([]);
  const listRef = useRef(null);
  const socketRef = useRef(null);
  const pendingRunRef = useRef(null);

  const agentName = agent?.name || "Agent";
  const canSend = Boolean(agent?.id && draft.trim() && !isSending);
  const visibleMessages = useMemo(() => messages, [messages]);

  useEffect(() => {
    setMessages([]);
    setDraft("");
    setError("");
    setActiveRunId(null);
    setSocketState("idle");
    setQueue([]);
    pendingRunRef.current = null;
    socketRef.current?.close?.();
    socketRef.current = null;
  }, [agent?.id]);

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [visibleMessages, isSending]);

  useEffect(() => {
    return () => socketRef.current?.close?.();
  }, []);

  useEffect(() => {
    if (isSending || !queue.length || !agent?.id) return;
    const [next, ...rest] = queue;
    setQueue(rest);
    void sendExecution(next);
  }, [queue, isSending, agent?.id]);

  const closeSocket = () => {
    socketRef.current?.close?.();
    socketRef.current = null;
  };

  const attachSocket = (runId) => {
    closeSocket();
    const socket = connectRunSocket(runId);
    socketRef.current = socket;
    setSocketState("connecting");

    socket.on("open", () => setSocketState("connected"));
    socket.on("*", async (event) => {
      if (event.type === "connected" || event.type === "log") {
        setSocketState("connected");
        if (event.message) {
          setMessages((current) => {
            const next = [...current];
            const exists = next.some((entry) => entry.id === `log-${runId}-${event.message}`);
            if (!exists) {
              next.push(
                normalizeMessage({
                  id: `log-${runId}-${Date.now()}`,
                  role: "agent",
                  content: event.message,
                  metadata: { stage: "thinking" },
                  timestamp: new Date().toISOString(),
                  senderName: agentName,
                }),
              );
            }
            return next;
          });
        }
      }

      if (event.type === "completed") {
        const assistant = buildAssistantMessage({
          ...event,
          agent_name: agentName,
        });
        setMessages((current) => [...current.filter((item) => item.role !== "thinking"), assistant]);
        setIsSending(false);
        setSocketState("done");
        closeSocket();
        try {
          const persisted = await getMessages(runId);
          setMessages(
            persisted.length
              ? persisted.map((message) =>
                  normalizeMessage({
                    ...message,
                    role: message.sender_agent_id ? "agent" : "user",
                    senderName: message.sender_agent_id ? agentName : "User",
                  }),
                )
              : [assistant],
          );
        } catch {
          // keep optimistic view
        }
      }

      if (event.type === "failed") {
        setMessages((current) => [
          ...current,
          normalizeMessage({
            id: `failed-${runId}-${Date.now()}`,
            role: "system",
            content: event.message || "Execution failed.",
            metadata: { failed: true },
            timestamp: new Date().toISOString(),
            senderName: "System",
          }),
        ]);
        setError("Execution failed. Try again.");
        setIsSending(false);
        setSocketState("failed");
        closeSocket();
      }
    });
  };

  const sendExecution = async (text) => {
    setError("");
    setIsSending(true);
    setMessages((current) => [
      ...current,
      normalizeMessage({
        id: `user-${Date.now()}`,
        role: "user",
        content: text,
        timestamp: new Date().toISOString(),
        senderName: "You",
        metadata: { tokens: Math.max(1, Math.ceil(text.length / 4)) },
      }),
      normalizeMessage({
        id: `thinking-${Date.now()}`,
        role: "thinking",
        content: "Agent is thinking...",
        timestamp: new Date().toISOString(),
        senderName: agentName,
      }),
    ]);

    try {
      const response = await executeAgent(agent.id, text);
      setActiveRunId(response.run_id);
      pendingRunRef.current = response.run_id;
      attachSocket(response.run_id);
      window.setTimeout(async () => {
        if (pendingRunRef.current !== response.run_id) return;
        try {
          const persisted = await getMessages(response.run_id);
          if (persisted.length) {
            setMessages(
              persisted.map((message) =>
                normalizeMessage({
                  ...message,
                  role: message.sender_agent_id ? "agent" : "user",
                  senderName: message.sender_agent_id ? agentName : "User",
                }),
              ),
            );
          }
        } catch {
          // ignore polling fallback failures
        }
      }, 1500);
    } catch (exc) {
      setIsSending(false);
      setMessages((current) =>
        current.filter((entry) => entry.role !== "thinking"),
      );
      setError(exc.response?.data?.detail || "Could not start agent test.");
    }
  };

  const sendMessage = async () => {
    const text = draft.trim();
    if (!text || !agent?.id) return;
    setDraft("");
    if (isSending) {
      setQueue((current) => [...current, text]);
      return;
    }
    await sendExecution(text);
  };

  const clearConversation = () => {
    setMessages([]);
    setDraft("");
    setError("");
    setActiveRunId(null);
    setSocketState("idle");
    closeSocket();
  };

  return (
    <div className="flex h-[80vh] flex-col overflow-hidden rounded-md border border-line bg-surface shadow-xl transition-colors">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <h3 className="text-lg font-semibold">{agentName} Test Console</h3>
          <p className="text-xs text-muted">
            {activeRunId ? `Run #${activeRunId}` : "Select an agent and start testing"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={clearConversation}
            className="rounded-md border border-line px-3 py-2 text-sm font-medium transition-colors hover:bg-soft"
          >
            Clear conversation
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-line px-3 py-2 text-sm font-medium transition-colors hover:bg-soft"
          >
            Close
          </button>
        </div>
      </div>

      <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto bg-canvas px-4 py-4 transition-colors">
        {!messages.length ? (
          <div className="flex h-full items-center justify-center rounded-md border border-dashed border-line bg-surface-strong px-4 py-10 text-sm text-muted transition-colors">
            Select an agent and start testing
          </div>
        ) : null}

        {messages.map((message) => {
          const isUser = message.role === "user";
          const isThinking = message.role === "thinking";
          const toolCall = message.metadata?.tool_call;
          return (
            <div
              key={message.id}
              className={`flex ${isUser ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[92%] rounded-2xl border px-4 py-3 text-sm shadow-sm transition-colors sm:max-w-[78%] ${
                  isUser
                    ? "border-blue-200 bg-blue-600 text-white"
                    : isThinking
                      ? "border-line bg-surface-strong text-muted"
                      : "border-line bg-surface text-ink"
                }`}
              >
                <div className="mb-1 flex flex-wrap items-center gap-2 text-xs opacity-80">
                  <span className="font-semibold">{message.senderName}</span>
                  <span>{formatTime(message.timestamp)}</span>
                  {message.metadata?.tokens ? <span>{message.metadata.tokens} tokens</span> : null}
                </div>

                {isThinking ? (
                  <ThinkingDots />
                ) : (
                  <>
                    <p className="whitespace-pre-wrap leading-6">{message.content}</p>
                    {toolCall ? (
                      <details className="mt-3 rounded-md border border-line bg-soft px-3 py-2 text-xs transition-colors">
                        <summary className="cursor-pointer list-none font-semibold">
                          🔍 {toolCall.name} {toolCall.results ? `→ ${toolCall.results} results` : "→ tool call"}
                        </summary>
                        <p className="mt-2 whitespace-pre-wrap text-muted">{toolCall.details}</p>
                      </details>
                    ) : null}
                  </>
                )}
              </div>
            </div>
          );
        })}

        {isSending ? (
          <div className="flex justify-start">
            <div className="rounded-2xl border border-line bg-surface px-4 py-3 text-sm text-muted shadow-sm transition-colors">
              Agent is thinking...
              <ThinkingDots />
            </div>
          </div>
        ) : null}
      </div>

      {error ? (
        <div className="border-t border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      {queue.length ? (
        <div className="border-t border-line bg-soft px-4 py-2 text-xs text-muted">
          {queue.length} queued message{queue.length === 1 ? "" : "s"}
        </div>
      ) : null}

      <div className="sticky bottom-0 border-t border-line bg-surface p-3 transition-colors">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
              }
            }}
            className="min-h-24 flex-1 rounded-md border border-line bg-surface px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-ink/20"
            placeholder="Type a prompt, press Enter to send."
          />
          <button
            type="button"
            onClick={sendMessage}
            disabled={!canSend}
            className="rounded-md bg-ink px-4 py-3 text-sm font-semibold text-white disabled:opacity-50"
          >
            {isSending ? "Sending..." : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ThinkingDots() {
  return (
    <span className="mt-2 inline-flex items-center gap-1">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current [animation-delay:150ms]" />
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current [animation-delay:300ms]" />
    </span>
  );
}