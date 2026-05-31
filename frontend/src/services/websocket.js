import { API_BASE_URL } from "./api";

export class RunSocket {
  constructor(runId) {
    this.runId = runId;
    this.listeners = new Map();
    this.socket = null;
    this.closed = false;
    this.retries = 0;
  }

  connect() {
    const wsBase = API_BASE_URL.replace(/^http/, "ws");
    this.socket = new WebSocket(`${wsBase}/ws/run/${this.runId}`);
    this.socket.onopen = () => {
      this.retries = 0;
      this.emit("open", { type: "open", run_id: this.runId });
    };
    this.socket.onmessage = (event) => {
      const payload = this.parse(event.data);
      this.emit(payload.type || "message", payload);
      this.emit("*", payload);
    };
    this.socket.onerror = () => {
      this.emit("error", { type: "error", message: "WebSocket error" });
    };
    this.socket.onclose = () => {
      this.emit("close", { type: "close" });
      if (!this.closed && this.retries < 5) {
        this.retries += 1;
        window.setTimeout(() => this.connect(), this.retries * 1000);
      }
    };
    return this;
  }

  on(type, callback) {
    const listeners = this.listeners.get(type) || new Set();
    listeners.add(callback);
    this.listeners.set(type, listeners);
    return () => listeners.delete(callback);
  }

  emit(type, payload) {
    (this.listeners.get(type) || []).forEach((callback) => callback(payload));
  }

  close() {
    this.closed = true;
    this.socket?.close();
  }

  parse(value) {
    try {
      return JSON.parse(value);
    } catch {
      return { type: "message", message: value };
    }
  }
}

export function connectRunSocket(runId) {
  return new RunSocket(runId).connect();
}
