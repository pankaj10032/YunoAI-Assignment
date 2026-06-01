import { useEffect, useRef, useState, useCallback } from 'react';

// Simple WebSocket hook with auto-reconnect and local log queueing
export function useWorkflowStream(runId) {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState([]);
  const wsRef = useRef(null);
  const reconnectRef = useRef({ attempts: 0 });
  const queueRef = useRef([]);

  const connect = useCallback(() => {
    if (!runId) return;
    const url = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/run/${runId}`;
    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectRef.current.attempts = 0;
        setConnected(true);
        // flush queued local logs
        queueRef.current.forEach((msg) => ws.send(JSON.stringify(msg)));
        queueRef.current = [];
      };

      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          setEvents((prev) => [...prev, data]);
        } catch (e) {
          // ignore
        }
      };

      ws.onclose = () => {
        setConnected(false);
        // exponential backoff
        const attempt = ++reconnectRef.current.attempts;
        const timeout = Math.min(30000, 500 * Math.pow(2, attempt));
        setTimeout(() => connect(), timeout);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch (e) {
      // schedule reconnect
      setTimeout(() => connect(), 1000);
    }
  }, [runId]);

  useEffect(() => {
    connect();
    return () => {
      try {
        if (wsRef.current) wsRef.current.close();
      } catch (e) {}
    };
  }, [connect]);

  const sendLocal = useCallback((msg) => {
    // queue locally if not connected
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    } else {
      queueRef.current.push(msg);
    }
  }, []);

  return { connected, events, sendLocal };
}
