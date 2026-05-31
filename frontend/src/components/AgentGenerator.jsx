import React from "react";
import { useState } from "react";

import { generateAgentConfig } from "../services/api";

export default function AgentGenerator({ onClose, onUseConfig }) {
  const [prompt, setPrompt] = useState("");
  const [config, setConfig] = useState(null);
  const [error, setError] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);

  const generate = async () => {
    if (!prompt.trim()) return;
    setIsGenerating(true);
    setError("");
    try {
      const response = await generateAgentConfig(prompt);
      setConfig(response.config);
    } catch (err) {
      setError(
        err.response?.data?.error ||
          err.response?.data?.detail ||
          "Generation failed. Create manually or try again.",
      );
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-md bg-surface p-5 shadow-xl transition-colors">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-xl font-bold">Describe & Generate Agent</h3>
            <p className="text-sm text-muted">
              Describe the job, tone, tools, and channels. You can edit everything before saving.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-line px-3 py-1.5 text-sm font-medium"
          >
            Discard
          </button>
        </div>

        <label className="mt-4 block space-y-1">
          <span className="text-sm font-medium">Describe your agent...</span>
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            className="min-h-36 w-full rounded-md border border-line px-3 py-2"
            placeholder="I need a customer support agent that handles refund requests and checks order status..."
          />
        </label>

        {isGenerating ? (
          <div className="mt-3 rounded-md border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
            Analyzing prompt & generating configuration...
          </div>
        ) : null}

        {error ? (
          <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        {config ? (
          <section className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-4">
            <p className="text-sm font-semibold text-amber-900">
              Review & edit before saving
            </p>
            <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
              <div>
                <dt className="font-medium text-muted">Name</dt>
                <dd>{config.name}</dd>
              </div>
              <div>
                <dt className="font-medium text-muted">Role</dt>
                <dd>{config.role}</dd>
              </div>
              <div>
                <dt className="font-medium text-muted">Model</dt>
                <dd>{config.model}</dd>
              </div>
              <div>
                <dt className="font-medium text-muted">Tools</dt>
                <dd>{readable(config.tools)}</dd>
              </div>
            </dl>
            <p className="mt-3 line-clamp-4 text-sm text-muted">
              {config.system_prompt}
            </p>
          </section>
        ) : null}

        <div className="mt-5 flex flex-wrap justify-end gap-2 border-t border-line pt-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-line px-4 py-2 text-sm font-medium"
          >
            Discard
          </button>
          <button
            type="button"
            onClick={generate}
            disabled={isGenerating || !prompt.trim()}
            className="rounded-md border border-line px-4 py-2 text-sm font-semibold disabled:opacity-50"
          >
            {config ? "Regenerate" : "Generate"}
          </button>
          <button
            type="button"
            onClick={() => onUseConfig(config)}
            disabled={!config || isGenerating}
            className="rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            Continue to Save
          </button>
        </div>
      </div>
    </div>
  );
}

function readable(items = []) {
  return items
    .map((item) => (typeof item === "string" ? item : item.name))
    .filter(Boolean)
    .join(", ");
}