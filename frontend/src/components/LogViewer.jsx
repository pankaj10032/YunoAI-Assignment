import React from "react";
import { useEffect, useRef, useState } from "react";

import { getRuns } from "../services/api";
import { connectRunSocket } from "../services/websocket";

const levelClass = {
  INFO: "text-emerald-300",
  DEBUG: "text-sky-300",
  ERROR: "text-rose-300",
};

export default function LogViewer() {
  const [runId, setRunId] = useState("");
  const [runs, setRuns] = useState([]);
  const [logs, setLogs] = useState([]);
  const [paused, setPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef = useRef(null);

  useEffect(() => {
    getRuns({ limit: 100 }).then(setRuns).catch(() => setRuns([]));
  }, []);

  useEffect(() => {
    if (!runId) return undefined;
    const socket = connectRunSocket(runId);
    const unsubscribe = socket.on("*", (event) => {
      if (paused) return;
      setLogs((current) => [
        ...current,
        {
          level: event.type === "failed" || event.type === "error" ? "ERROR" : "INFO",
          message: event.message || event.result || JSON.stringify(event),
          time: new Date().toLocaleTimeString(),
        },
      ]);
    });
    return () => {
      unsubscribe();
      socket.close();
    };
  }, [runId, paused]);

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, autoScroll]);

  return (
    <div className="overflow-hidden rounded-3xl border border-line bg-surface shadow-sm transition-colors">
      <div className="flex flex-wrap items-center gap-3 border-b border-line p-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted">Stream logs</p>
          <h3 className="mt-1 text-lg font-semibold">Real-time execution feed</h3>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <select
            value={runId}
            onChange={(event) => setRunId(event.target.value)}
            className="rounded-xl border border-line bg-surface px-3 py-2 text-sm shadow-sm"
          >
            <option value="">Select run stream</option>
            {runs.map((run) => (
              <option key={run.id} value={run.id}>
                Run #{run.id} - {run.status}
              </option>
            ))}
          </select>
          <button
            onClick={() => setPaused((value) => !value)}
            className="rounded-xl border border-line px-3 py-2 text-sm font-semibold transition hover:bg-soft"
          >
            {paused ? "Resume" : "Pause"}
          </button>
          <label className="flex items-center gap-2 rounded-xl border border-line px-3 py-2 text-sm">
            <input type="checkbox" checked={autoScroll} onChange={(event) => setAutoScroll(event.target.checked)} />
            Auto-scroll
          </label>
        </div>
      </div>

      <div className="h-[520px] overflow-y-auto bg-[#0d1117] p-4 font-mono text-sm text-gray-100">
        <div className="mb-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-gray-300">
          Streaming events appear here when a run is selected. This gives reviewers a visible runtime trace.
        </div>
        {logs.map((log, index) => (
          <div key={`${log.time}-${index}`} className="py-1">
            <span className="text-gray-500">{log.time}</span>{" "}
            <span className={levelClass[log.level]}>{log.level}</span>{" "}
            <span>{log.message}</span>
          </div>
        ))}
        {!logs.length ? <p className="text-gray-400">Select a run to stream logs.</p> : null}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
