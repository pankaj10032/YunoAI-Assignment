import React from "react";
import { useEffect, useMemo, useState } from "react";

import { getAgents, getAllMessages } from "../services/api";

export default function MessageHistory() {
  const [messages, setMessages] = useState([]);
  const [agents, setAgents] = useState([]);
  const [filters, setFilters] = useState({
    agent_id: "",
    channel: "",
    run_id: "",
    start_date: "",
    end_date: "",
  });

  const load = () => {
    const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value));
    return getAllMessages(params).then(setMessages);
  };

  useEffect(() => {
    getAgents().then(setAgents).catch(() => setAgents([]));
  }, []);

  useEffect(() => {
    load().catch(() => setMessages([]));
    const timer = window.setInterval(() => load().catch(() => {}), 5000);
    return () => window.clearInterval(timer);
  }, [filters.agent_id, filters.channel, filters.run_id]);

  const agentById = useMemo(
    () => Object.fromEntries(agents.map((agent) => [agent.id, agent])),
    [agents],
  );

  const visibleMessages = useMemo(
    () =>
      messages.filter((message) => {
        const time = new Date(message.timestamp).getTime();
        if (filters.start_date && time < new Date(filters.start_date).getTime()) return false;
        if (filters.end_date && time > new Date(`${filters.end_date}T23:59:59`).getTime()) return false;
        return true;
      }),
    [messages, filters.start_date, filters.end_date],
  );

  return (
    <div className="rounded-md border border-line bg-surface transition-colors">
      <div className="grid gap-3 border-b border-line p-4 md:grid-cols-5">
        <select value={filters.agent_id} onChange={(event) => setFilters((current) => ({ ...current, agent_id: event.target.value }))} className="rounded-md border border-line px-3 py-2 text-sm">
          <option value="">All agents</option>
          {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
        </select>
        <select value={filters.channel} onChange={(event) => setFilters((current) => ({ ...current, channel: event.target.value }))} className="rounded-md border border-line px-3 py-2 text-sm">
          <option value="">All channels</option>
          <option value="telegram">Telegram</option>
          <option value="internal">Internal</option>
          <option value="web">Web</option>
        </select>
        <input value={filters.run_id} onChange={(event) => setFilters((current) => ({ ...current, run_id: event.target.value }))} placeholder="Workflow run ID" className="rounded-md border border-line px-3 py-2 text-sm" />
        <input type="date" value={filters.start_date} onChange={(event) => setFilters((current) => ({ ...current, start_date: event.target.value }))} className="rounded-md border border-line px-3 py-2 text-sm" />
        <input type="date" value={filters.end_date} onChange={(event) => setFilters((current) => ({ ...current, end_date: event.target.value }))} className="rounded-md border border-line px-3 py-2 text-sm" />
      </div>
      <div className="max-h-[560px] space-y-3 overflow-y-auto p-4">
        {visibleMessages.map((message) => {
          const sender = agentById[message.sender_agent_id]?.name || "External/User";
          return (
            <div key={message.id} className={`max-w-3xl rounded-md border border-line p-3 transition-colors ${message.sender_agent_id ? "ml-auto bg-soft" : "bg-surface-strong"}`}>
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
                <span>{sender} · {message.channel}</span>
                <span>{new Date(message.timestamp).toLocaleString()}</span>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm">{message.content}</p>
              <p className="mt-2 text-xs text-muted">{message.metadata?.tokens || 0} tokens</p>
            </div>
          );
        })}
        {!visibleMessages.length ? <p className="py-8 text-center text-sm text-muted">No messages match these filters.</p> : null}
      </div>
    </div>
  );
}