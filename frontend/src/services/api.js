import axios from "axios";
import { notifyApiError } from "../components/ErrorToast";

// Use strict undefined check so that VITE_API_BASE_URL="" (empty string for
// relative URLs in production Docker builds) is NOT overridden by the fallback.
const envUrl = import.meta.env.VITE_API_BASE_URL;
export const API_BASE_URL =
  envUrl !== undefined && envUrl !== null ? envUrl : "http://localhost:8000";

export const api = axios.create({
  baseURL: API_BASE_URL || undefined,
  timeout: 15000,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (!error.config?.skipToast) {
      const canRetry = String(error.config?.method || "get").toLowerCase() === "get";
      notifyApiError(error, {
        detailsHref: "/monitor",
        retry: canRetry
          ? () => api.request({ ...error.config, skipToast: true })
          : undefined,
      });
    }
    return Promise.reject(error);
  },
);

const unwrap = (response) => response.data;

export const getAgents = () => api.get("/api/agents").then(unwrap);
export const createAgent = (payload) => api.post("/api/agents", payload).then(unwrap);
export const generateAgentConfig = (prompt) =>
  api.post("/api/agents/generate", { prompt }).then(unwrap);
export const updateAgent = (id, payload) =>
  api.put(`/api/agents/${id}`, payload).then(unwrap);
export const deleteAgent = (id) => api.delete(`/api/agents/${id}`).then(unwrap);
export const getToolList = () => api.get("/api/tools/list").then(unwrap);
export const reloadTools = () => api.post("/api/tools/reload").then(unwrap);

export const getWorkflows = (params = {}) =>
  api.get("/api/workflows", { params }).then(unwrap);
export const createWorkflow = (payload) =>
  api.post("/api/workflows", payload).then(unwrap);
export const updateWorkflow = (id, payload) =>
  api.put(`/api/workflows/${id}`, payload).then(unwrap);
export const runWorkflow = (id, inputData = {}) =>
  api.post(`/api/workflows/${id}/run`, { input_data: inputData }).then(unwrap);
export const resumeWorkflow = (id, runId, resumeFromStep = null) =>
  api
    .post(`/api/workflows/${id}/resume`, {
      run_id: runId,
      resume_from_step: resumeFromStep,
    })
    .then(unwrap);
export const executeAgent = (id, taskDescription) =>
  api
    .post(`/api/agents/${id}/execute`, { task_description: taskDescription })
    .then(unwrap);

export const getMessages = (runId) =>
  api.get(`/api/runs/${runId}/messages`).then(unwrap);
export const getAllMessages = (params = {}) =>
  api.get("/api/messages", { params }).then(unwrap);

export const getRun = (runId) => api.get(`/api/runs/${runId}`).then(unwrap);
export const getRuns = (params = {}) =>
  api.get("/api/runs", { params }).then(unwrap);
export const rerunWorkflowRun = (runId) =>
  api.post(`/api/runs/${runId}/rerun`).then(unwrap);
export const stopWorkflowRun = (runId) =>
  api.post(`/api/runs/${runId}/stop`).then(unwrap);

export const streamLogs = (runId, handlers = {}) => {
  // Build WebSocket URL: if API_BASE_URL is absolute use it, otherwise
  // derive from the current page location so it works on any deployment.
  let wsBase;
  if (API_BASE_URL && /^https?:\/\//.test(API_BASE_URL)) {
    wsBase = API_BASE_URL.replace(/^http/, "ws");
  } else {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    wsBase = `${proto}//${window.location.host}${API_BASE_URL}`;
  }
  const socket = new WebSocket(`${wsBase}/ws/run/${runId}`);

  socket.onopen = handlers.onOpen || null;
  socket.onerror = handlers.onError || null;
  socket.onclose = handlers.onClose || null;
  socket.onmessage = (event) => {
    try {
      handlers.onMessage?.(JSON.parse(event.data));
    } catch {
      handlers.onMessage?.({ type: "raw", message: event.data });
    }
  };

  return socket;
};

// ── Telegram channel ────────────────────────────────────────
export const getTelegramStatus = () =>
  api.get("/api/channels/telegram/status", { skipToast: true }).then(unwrap);

export const connectTelegramAgent = (agentId, chatId) =>
  api.post("/api/channels/telegram/connect", { agent_id: agentId, chat_id: chatId }).then(unwrap);

export const setTelegramWebhook = (webhookUrl) =>
  api.post("/api/channels/telegram/webhook/set", { webhook_url: webhookUrl }).then(unwrap);

export const deleteTelegramWebhook = () =>
  api.post("/api/channels/telegram/webhook/delete").then(unwrap);

export const getTelegramWebhookInfo = () =>
  api.get("/api/channels/telegram/webhook/info", { skipToast: true }).then(unwrap);

export const sendTelegramMessage = (chatId, text) =>
  api.post("/api/channels/telegram/send", { chat_id: chatId, text }).then(unwrap);
