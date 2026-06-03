import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../services/api";
import {
  connectTelegramAgent,
  deleteTelegramWebhook,
  getAgents,
  getTelegramStatus,
  getTelegramWebhookInfo,
  sendTelegramMessage,
  setTelegramWebhook,
} from "../services/api";
import { useToast } from "../components/ToastProvider";
import ErrorBoundary from "../components/ErrorBoundary";

/* ── helpers ─────────────────────────────────────────────── */
function StatusDot({ on }) {
  return (
    <span
      style={{
        display: "inline-block",
        width: 10,
        height: 10,
        borderRadius: "50%",
        background: on ? "#10b981" : "#9ca3af",
        marginRight: 7,
        flexShrink: 0,
      }}
    />
  );
}

function Card({ title, children, accent }) {
  return (
    <div className="tg-card" style={accent ? { borderColor: "#2563eb" } : {}}>
      {title && <h3 className="tg-card__title">{title}</h3>}
      {children}
    </div>
  );
}

function CopyBtn({ value }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="tg-btn tg-btn--ghost"
      style={{ padding: "2px 8px", fontSize: "0.75rem" }}
      onClick={() => {
        navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
      }}
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

/* ── Main page ───────────────────────────────────────────── */
export default function SettingsPage() {
  return (
    <ErrorBoundary>
      <div className="tg-page">
        <TelegramSection />
      </div>
    </ErrorBoundary>
  );
}

function TelegramSection() {
  const toast = useToast();
  const [status, setStatus] = useState(null);
  const [webhookInfo, setWebhookInfo] = useState(null);
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const pollRef = useRef(null);

  // ── load status ──────────────────────────────────────────
  const refreshStatus = useCallback(async () => {
    try {
      const [s, w, a] = await Promise.all([
        getTelegramStatus(),
        getTelegramWebhookInfo().catch(() => null),
        getAgents(),
      ]);
      setStatus(s);
      setWebhookInfo(w);
      setAgents(a || []);
    } catch {
      setStatus({ configured: false, connected: false, polling: false });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    pollRef.current = setInterval(refreshStatus, 15_000);
    return () => clearInterval(pollRef.current);
  }, [refreshStatus]);

  if (loading) {
    return (
      <div className="tg-loading">
        <div className="tg-spinner" />
        <span>Checking Telegram status…</span>
      </div>
    );
  }

  return (
    <div className="tg-section">
      <StatusCard status={status} webhookInfo={webhookInfo} onRefresh={refreshStatus} toast={toast} />
      <WebhookCard webhookInfo={webhookInfo} onRefresh={refreshStatus} toast={toast} />
      <ConnectAgentCard agents={agents} onRefresh={refreshStatus} toast={toast} />
      <SendMessageCard toast={toast} />
      <CommandReferenceCard />
    </div>
  );
}

/* ── Status card ─────────────────────────────────────────── */
function StatusCard({ status, webhookInfo, onRefresh, toast }) {
  return (
    <Card title="🤖 Telegram Bot Status">
      <div className="tg-status-grid">
        <div className="tg-status-row">
          <StatusDot on={status?.configured} />
          <span>Bot token configured</span>
        </div>
        <div className="tg-status-row">
          <StatusDot on={status?.connected} />
          <span>Bot connected</span>
        </div>
        <div className="tg-status-row">
          <StatusDot on={status?.polling} />
          <span>Polling active</span>
        </div>
        {webhookInfo?.url && (
          <div className="tg-status-row">
            <StatusDot on />
            <span style={{ wordBreak: "break-all" }}>
              Webhook: <strong>{webhookInfo.url}</strong>
            </span>
          </div>
        )}
        {webhookInfo?.last_error_message && (
          <div className="tg-status-row" style={{ color: "#ef4444" }}>
            ⚠ Last error: {webhookInfo.last_error_message}
          </div>
        )}
      </div>

      {!status?.configured && (
        <div className="tg-alert tg-alert--warn">
          <strong>TELEGRAM_BOT_TOKEN</strong> is not set. Add it to your <code>.env</code> file and restart the backend.
        </div>
      )}

      {status?.configured && !status?.connected && (
        <div className="tg-alert tg-alert--info">
          Bot is configured but not yet connected. Set up a webhook below or enable <code>ENABLE_TELEGRAM_POLLING=true</code>.
        </div>
      )}

      <div className="tg-actions">
        <button className="tg-btn tg-btn--ghost" onClick={onRefresh}>
          ↻ Refresh
        </button>
      </div>
    </Card>
  );
}

/* ── Webhook card ────────────────────────────────────────── */
function WebhookCard({ webhookInfo, onRefresh, toast }) {
  const [url, setUrl] = useState(webhookInfo?.url || "");
  const [busy, setBusy] = useState(false);

  const handleSet = async () => {
    if (busy) return;
    if (!url.startsWith("https://")) {
      toast.error("Webhook URL must start with https://");
      return;
    }
    setBusy(true);
    try {
      await setTelegramWebhook(url);
      toast.success("Webhook set successfully!");
      onRefresh();
    } catch (e) {
      toast.error("Failed to set webhook", e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    setBusy(true);
    try {
      await deleteTelegramWebhook();
      toast.success("Webhook removed.");
      setUrl("");
      onRefresh();
    } catch (e) {
      toast.error("Failed to remove webhook", e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="🔗 Webhook Configuration">
      <p className="tg-hint">
        Use a webhook when running behind a public HTTPS domain (e.g. on Render, Railway, or ngrok). For local dev use polling mode instead.
      </p>

      {webhookInfo?.url && (
        <div className="tg-code-row">
          <code className="tg-code">{webhookInfo.url}</code>
          <CopyBtn value={webhookInfo.url} />
        </div>
      )}

      <div className="tg-field">
        <label className="tg-label" htmlFor="webhook-url-input">Webhook URL</label>
        <input
          id="webhook-url-input"
          className="tg-input"
          placeholder="https://yourdomain.com/api/channels/telegram/webhook"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
      </div>

      <div className="tg-actions">
        <button className="tg-btn tg-btn--primary" onClick={handleSet} disabled={busy || !url}>
          {busy ? "Setting…" : "Set Webhook"}
        </button>
        {webhookInfo?.url && (
          <button className="tg-btn tg-btn--danger" onClick={handleDelete} disabled={busy}>
            Delete Webhook
          </button>
        )}
      </div>

      <div className="tg-alert tg-alert--info" style={{ marginTop: 12 }}>
        <strong>Local dev with ngrok:</strong><br />
        <code>ngrok http 8000</code> → copy the <code>https://…ngrok.io</code> URL → append <code>/api/channels/telegram/webhook</code> → paste above.
      </div>
    </Card>
  );
}

/* ── Connect agent card ──────────────────────────────────── */
function ConnectAgentCard({ agents, onRefresh, toast }) {
  const [agentId, setAgentId] = useState("");
  const [chatId, setChatId] = useState("");
  const [busy, setBusy] = useState(false);

  const telegramAgents = agents.filter((a) =>
    (a.channels || []).some((c) => c === "telegram" || (typeof c === "object" && c?.name === "telegram"))
  );

  const handleConnect = async () => {
    if (!agentId || !chatId) {
      toast.error("Select an agent and enter a Telegram chat ID.");
      return;
    }
    setBusy(true);
    try {
      const agent = await connectTelegramAgent(Number(agentId), chatId);
      toast.success(`Connected "${agent.name}" to chat ${chatId}`);
      onRefresh();
    } catch (e) {
      toast.error("Connection failed", e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="🔌 Connect Agent to Telegram Chat">
      <p className="tg-hint">
        Link an agent to a specific Telegram chat ID. After connecting, messages sent to that chat will be processed by this agent.
      </p>

      <div className="tg-form-row">
        <div className="tg-field">
          <label className="tg-label" htmlFor="tg-agent-select">Agent</label>
          <select id="tg-agent-select" className="tg-input" value={agentId} onChange={(e) => setAgentId(e.target.value)}>
            <option value="">-- select agent --</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>{a.name} (#{a.id})</option>
            ))}
          </select>
        </div>
        <div className="tg-field">
          <label className="tg-label" htmlFor="tg-chat-input">
            Chat ID
            <span className="tg-hint-inline"> (send /start to bot → note the chat ID)</span>
          </label>
          <input
            id="tg-chat-input"
            className="tg-input"
            placeholder="-100123456789"
            value={chatId}
            onChange={(e) => setChatId(e.target.value)}
          />
        </div>
      </div>

      <div className="tg-actions">
        <button className="tg-btn tg-btn--primary" onClick={handleConnect} disabled={busy || !agentId || !chatId}>
          {busy ? "Connecting…" : "Connect Agent"}
        </button>
      </div>

      {telegramAgents.length > 0 && (
        <div className="tg-connected-list">
          <p className="tg-label" style={{ marginBottom: 6 }}>Currently connected agents:</p>
          {telegramAgents.map((a) => {
            const tgChannel = (a.channels || []).find((c) => typeof c === "object" && c?.name === "telegram");
            return (
              <div key={a.id} className="tg-connected-item">
                <StatusDot on />
                <span><strong>{a.name}</strong></span>
                {tgChannel?.chat_id && (
                  <span className="tg-tag">chat: {tgChannel.chat_id}</span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

/* ── Send message card ───────────────────────────────────── */
function SendMessageCard({ toast }) {
  const [chatId, setChatId] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const handleSend = async () => {
    if (!chatId || !text.trim()) {
      toast.error("Enter both a chat ID and message text.");
      return;
    }
    setBusy(true);
    try {
      await sendTelegramMessage(chatId, text);
      toast.success("Message sent!");
      setText("");
    } catch (e) {
      toast.error("Send failed", e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="📨 Send Test Message">
      <p className="tg-hint">Manually push a message to any Telegram chat to verify connectivity.</p>
      <div className="tg-form-row">
        <div className="tg-field" style={{ flex: "0 0 200px" }}>
          <label className="tg-label" htmlFor="test-chat-id">Chat ID</label>
          <input id="test-chat-id" className="tg-input" placeholder="-100…" value={chatId} onChange={(e) => setChatId(e.target.value)} />
        </div>
        <div className="tg-field" style={{ flex: 1 }}>
          <label className="tg-label" htmlFor="test-msg-text">Message</label>
          <input id="test-msg-text" className="tg-input" placeholder="Hello from AI Orchestrator!" value={text} onChange={(e) => setText(e.target.value)} />
        </div>
      </div>
      <div className="tg-actions">
        <button className="tg-btn tg-btn--primary" onClick={handleSend} disabled={busy || !chatId || !text.trim()}>
          {busy ? "Sending…" : "Send"}
        </button>
      </div>
    </Card>
  );
}

/* ── Command reference ───────────────────────────────────── */
function CommandReferenceCard() {
  const commands = [
    { cmd: "/start", desc: "Check bot status and confirm it's online" },
    { cmd: "/help", desc: "List all available bot commands" },
    { cmd: "/agents", desc: "Show all Telegram-enabled agents" },
    { cmd: "/connect <agent_id>", desc: "Link this Telegram chat to the specified agent" },
    { cmd: "<any text>", desc: "After /connect — runs the linked agent with your message" },
  ];

  return (
    <Card title="📖 Bot Command Reference">
      <p className="tg-hint">Open your bot in Telegram and use these commands to control it:</p>
      <table className="tg-table">
        <thead>
          <tr>
            <th>Command</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          {commands.map(({ cmd, desc }) => (
            <tr key={cmd}>
              <td><code className="tg-code">{cmd}</code></td>
              <td>{desc}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="tg-alert tg-alert--info" style={{ marginTop: 16 }}>
        <strong>Quick Setup:</strong>
        <ol style={{ margin: "8px 0 0 16px", lineHeight: 1.8 }}>
          <li>Open <a href="https://t.me/BotFather" target="_blank" rel="noreferrer" style={{ color: "#3b82f6" }}>@BotFather</a> → <code>/newbot</code> → copy the token</li>
          <li>Add <code>TELEGRAM_BOT_TOKEN=&lt;token&gt;</code> to your <code>.env</code> and restart backend</li>
          <li>Choose polling (local dev) or webhook (production) in the section above</li>
          <li>Open your bot → send <code>/start</code> → note your <strong>chat ID</strong></li>
          <li>Come back here → <strong>Connect Agent</strong> with that chat ID</li>
          <li>Send any message to the bot → agent responds instantly ✅</li>
        </ol>
      </div>
    </Card>
  );
}
