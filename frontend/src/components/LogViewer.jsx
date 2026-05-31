import React from "react";
import { useEffect, useRef, useState } from "react";

import { getRuns } from "../services/api";
import { connectRunSocket } from "../services/websocket";

const levelClass = {
  INFO: "text-blue-700",
  DEBUG: "text-gray-600",
  ERROR: "text-red-700",
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
    <div className="rounded-md border border-line bg-surface transition-colors">
      <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
        <select value={runId} onChange={(event) => setRunId(event.target.value)} className="rounded-md border border-line px-3 py-2 text-sm">
          <option value="">Select run stream</option>
          {runs.map((run) => <option key={run.id} value={run.id}>Run #{run.id} · {run.status}</option>)}
        </select>
        <button onClick={() => setPaused((value) => !value)} className="rounded-md border border-line px-3 py-2 text-sm font-semibold">
          {paused ? "Resume" : "Pause"}
        </button>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={autoScroll} onChange={(event) => setAutoScroll(event.target.checked)} />
          Auto-scroll
        </label>
      </div>
      <div className="h-[520px] overflow-y-auto bg-[#101418] p-4 font-mono text-sm text-gray-100">
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