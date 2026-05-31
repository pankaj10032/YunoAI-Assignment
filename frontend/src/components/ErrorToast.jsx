import React from "react";
import { Toaster, toast } from "sonner";

const recentToasts = new Map();
const DEDUPE_MS = 2500;

const codeMessages = {
  400: "Invalid config",
  401: "Authentication required",
  403: "Access denied",
  404: "Resource not found",
  409: "Conflict detected",
  422: "Validation failed",
  429: "Rate limited",
  500: "Server error",
};

function getToastMessage(error, fallback = "Something went wrong") {
  const status = error?.response?.status;
  return codeMessages[status] || error?.response?.data?.detail || error?.message || fallback;
}

function getDetails(error) {
  const detail = error?.response?.data?.detail || error?.response?.data?.error || error?.message;
  if (Array.isArray(detail)) return detail.join("\n");
  if (typeof detail === "object" && detail) return JSON.stringify(detail, null, 2);
  return detail || "No additional details available.";
}

function shouldSuppress(key) {
  const now = Date.now();
  const last = recentToasts.get(key) || 0;
  recentToasts.set(key, now);
  return now - last < DEDUPE_MS;
}

function notify(type, message, options = {}) {
  const key = `${type}:${message}`;
  if (shouldSuppress(key)) return null;
  return toast[type](message, {
    duration: 5000,
    closeButton: true,
    ...options,
  });
}

export function notifySuccess(message, options = {}) {
  return notify("success", message, options);
}

export function notifyInfo(message, options = {}) {
  return notify("info", message, options);
}

export function notifyWarning(message, options = {}) {
  return notify("warning", message, options);
}

export function notifyError(error, options = {}) {
  const message = options.message || getToastMessage(error);
  const description = options.description || getDetails(error);
  return notify("error", message, {
    description,
    action: options.retry
      ? {
          label: "Retry",
          onClick: options.retry,
        }
      : options.action,
    cancel: {
      label: "Dismiss",
      onClick: () => {},
    },
  });
}

export function notifyApiError(error, options = {}) {
  return notifyError(error, {
    ...options,
    action:
      options.action ||
      (options.detailsHref
        ? {
            label: "View Details",
            onClick: () => {
              window.location.href = options.detailsHref;
            },
          }
        : undefined),
  });
}

export default function ErrorToastHost() {
  return (
    <Toaster
      richColors
      closeButton
      visibleToasts={3}
      duration={5000}
      position="top-right"
      toastOptions={{
        classNames: {
          toast:
            "border-line bg-surface text-ink shadow-lg dark:bg-surface dark:text-ink",
          description: "text-muted",
          actionButton: "bg-ink text-white",
          cancelButton: "bg-soft text-ink",
        },
      }}
    />
  );
}