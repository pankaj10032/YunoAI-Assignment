import React from "react";
import { useEffect, useState } from "react";

import { getMessages } from "../services/api";

export default function RunDetails({ run, onClose }) {
  const [messages, setMessages] = useState([]);

  useEffect(() => {
    if (run?.id) getMessages(run.id).then(setMessages).catch(() => setMessages([]));
  }, [run]);

  if (!run) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/35">
      <aside className="h-full w-full max-w-3xl overflow-y-auto bg-surface p-5 shadow-xl transition-colors">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-xl font-bold">Run #{run.id}</h3>
            <p className="text-sm text-muted">{run.status} · {run.total_tokens || 0} tokens · ${Number(run.total_cost || 0).toFixed(6)}</p>
          </div>
          <button onClick={onClose} className="rounded-md border border-line px-3 py-2 text-sm font-semibold">Close</button>
        </div>
        <section className="mt-5 rounded-md border border-line p-4">
          <h4 className="font-semibold">Workflow Diagram</h4>
          <p className="mt-2 text-sm text-muted">Execution status is reflected in the builder canvas while a run is active.</p>
        </section>
        <section className="mt-5 rounded-md border border-line p-4">
          <h4 className="font-semibold">Timeline</h4>
          <div className="mt-3 space-y-3">
            <div className="rounded-md bg-soft p-3 text-sm transition-colors">Started: {run.started_at ? new Date(run.started_at).toLocaleString() : "pending"}</div>
            <div className="rounded-md bg-soft p-3 text-sm transition-colors">Completed: {run.completed_at ? new Date(run.completed_at).toLocaleString() : "not completed"}</div>
          </div>
        </section>
        <section className="mt-5 rounded-md border border-line p-4">
          <h4 className="font-semibold">Messages</h4>
          <div className="mt-3 space-y-2">
            {messages.map((message) => (
              <div key={message.id} className="rounded-md border border-line p-3 text-sm">
                <p className="text-xs text-muted">{message.channel} · {new Date(message.timestamp).toLocaleString()} · {message.metadata?.tokens || 0} tokens</p>
                <p className="mt-1 whitespace-pre-wrap">{message.content}</p>
              </div>
            ))}
            {!messages.length ? <p className="text-sm text-muted">No messages persisted for this run yet.</p> : null}
          </div>
        </section>
      </aside>
    </div>
  );
}