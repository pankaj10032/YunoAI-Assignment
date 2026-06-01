import React, {
  createContext,
  useCallback,
  useContext,
  useId,
  useRef,
  useState,
} from "react";

/* ── Context ──────────────────────────────────────────────── */
const ToastContext = createContext(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}

/* ── Icon helpers ─────────────────────────────────────────── */
const ICONS = {
  success: "✓",
  error: "✕",
  info: "ℹ",
  warning: "⚠",
};

const COLORS = {
  success: {
    bg: "var(--toast-success-bg, #ecfdf5)",
    border: "var(--toast-success-border, #6ee7b7)",
    text: "var(--toast-success-text, #065f46)",
    icon: "#10b981",
  },
  error: {
    bg: "var(--toast-error-bg, #fef2f2)",
    border: "var(--toast-error-border, #fca5a5)",
    text: "var(--toast-error-text, #7f1d1d)",
    icon: "#ef4444",
  },
  info: {
    bg: "var(--toast-info-bg, #eff6ff)",
    border: "var(--toast-info-border, #93c5fd)",
    text: "var(--toast-info-text, #1e3a5f)",
    icon: "#3b82f6",
  },
  warning: {
    bg: "var(--toast-warning-bg, #fffbeb)",
    border: "var(--toast-warning-border, #fcd34d)",
    text: "var(--toast-warning-text, #78350f)",
    icon: "#f59e0b",
  },
};

/* ── Single Toast item ────────────────────────────────────── */
function ToastItem({ id, type, message, description, onDismiss }) {
  const color = COLORS[type] || COLORS.info;
  return (
    <div
      className="toast-item"
      style={{
        background: color.bg,
        border: `1px solid ${color.border}`,
        color: color.text,
      }}
      role="alert"
      aria-live="polite"
    >
      <span className="toast-icon" style={{ color: color.icon }}>
        {ICONS[type] || ICONS.info}
      </span>
      <div className="toast-content">
        <p className="toast-message">{message}</p>
        {description && <p className="toast-description">{description}</p>}
      </div>
      <button
        className="toast-close"
        aria-label="Dismiss notification"
        onClick={() => onDismiss(id)}
        style={{ color: color.text }}
      >
        ×
      </button>
    </div>
  );
}

/* ── Provider ─────────────────────────────────────────────── */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const dedupe = useRef(new Map());

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback(
    ({ type = "info", message, description, duration = 5000 }) => {
      const dedupeKey = `${type}:${message}`;
      const now = Date.now();
      const last = dedupe.current.get(dedupeKey) || 0;
      if (now - last < 2500) return; // suppress duplicate within 2.5 s
      dedupe.current.set(dedupeKey, now);

      const id = `${now}-${Math.random().toString(36).slice(2)}`;
      setToasts((prev) => [{ id, type, message, description }, ...prev].slice(0, 5));
      setTimeout(() => dismiss(id), duration);
    },
    [dismiss],
  );

  const api = {
    success: (msg, desc) => addToast({ type: "success", message: msg, description: desc }),
    error: (msg, desc) => addToast({ type: "error", message: msg, description: desc }),
    info: (msg, desc) => addToast({ type: "info", message: msg, description: desc }),
    warning: (msg, desc) => addToast({ type: "warning", message: msg, description: desc }),
    addToast,
    dismiss,
  };

  return (
    <ToastContext.Provider value={api}>
      {children}

      {/* Toast container — fixed top-right */}
      <div
        id="toast-container"
        aria-label="Notifications"
        style={{
          position: "fixed",
          top: 16,
          right: 16,
          zIndex: 99999,
          display: "flex",
          flexDirection: "column",
          gap: 8,
          minWidth: 300,
          maxWidth: 400,
          pointerEvents: "none",
        }}
      >
        {toasts.map((t) => (
          <div key={t.id} style={{ pointerEvents: "auto" }}>
            <ToastItem {...t} onDismiss={dismiss} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
