import React from "react";
import { useEffect, useMemo, useState } from "react";

const LARGE_PAYLOAD_BYTES = 50 * 1024;
const SENSITIVE_PATTERNS = [
  /api[_-]?key/i,
  /token/i,
  /secret/i,
  /password/i,
  /credential/i,
  /authorization/i,
];

function isSensitiveKey(key) {
  return SENSITIVE_PATTERNS.some((pattern) => pattern.test(key));
}

export function sanitizeConfig(value) {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeConfig(item));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => !isSensitiveKey(key))
        .map(([key, item]) => [key, sanitizeConfig(item)]),
    );
  }
  return value;
}

function downloadJson(filename, content) {
  const blob = new Blob([content], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function ExportButton({ data, label = "config" }) {
  const [toast, setToast] = useState("");
  const json = useMemo(
    () => JSON.stringify(sanitizeConfig(data || {}), null, 2),
    [data],
  );
  const isLarge = new Blob([json]).size > LARGE_PAYLOAD_BYTES;

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(""), 1800);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    const onShortcut = (event) => {
      const isModifier = event.ctrlKey || event.metaKey;
      if (isModifier && event.shiftKey && event.key.toLowerCase() === "e") {
        event.preventDefault();
        void copyJson();
      }
    };
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, [json]);

  const confirmLarge = () =>
    !isLarge || window.confirm("This JSON payload is larger than 50KB. Continue?");

  const copyJson = async () => {
    if (!confirmLarge()) return;
    try {
      await navigator.clipboard.writeText(json);
      setToast("Copied to clipboard");
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = json;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setToast("Copied to clipboard");
    }
  };

  const download = () => {
    if (!confirmLarge()) return;
    const filename = `${String(label || "config")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "") || "config"}.json`;
    downloadJson(filename, json);
    setToast("Download ready");
  };

  return (
    <div className="relative flex flex-wrap gap-2">
      <button
        type="button"
        onClick={copyJson}
        className="rounded-md border border-line px-3 py-2 text-sm font-semibold transition-colors hover:bg-soft"
      >
        Copy JSON
      </button>
      <button
        type="button"
        onClick={download}
        className="rounded-md border border-line px-3 py-2 text-sm font-semibold transition-colors hover:bg-soft"
      >
        Download .json
      </button>
      {toast ? (
        <span className="absolute right-0 top-full z-10 mt-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 shadow-sm">
          ✓ {toast}
        </span>
      ) : null}
    </div>
  );
}