import React from "react";
import { useEffect, useState } from "react";

import { api } from "../services/api";

export default function SettingsPage() {
  const [telegram, setTelegram] = useState(null);

  useEffect(() => {
    api
      .get("/api/channels/telegram/status")
      .then((response) => setTelegram(response.data))
      .catch(() => setTelegram({ configured: false, connected: false }));
  }, []);

  return (
    <section className="rounded-md border border-line bg-surface p-5 transition-colors">
      <h3 className="text-lg font-semibold">Settings</h3>
      <div className="mt-4 rounded-md border border-line bg-surface-strong p-4 transition-colors">
        <p className="font-medium">Telegram Channel</p>
        <p className="mt-1 text-sm text-muted">
          Configured: {telegram?.configured ? "yes" : "no"} · Connected:{" "}
          {telegram?.connected ? "yes" : "no"}
        </p>
      </div>
    </section>
  );
}