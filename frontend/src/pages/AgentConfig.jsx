import React from "react";
import { useEffect, useMemo, useState } from "react";

import ConfigToggles from "../components/ConfigToggles";
import { createAgent, executeAgent, getToolList } from "../services/api";
import { connectRunSocket } from "../services/websocket";

const tabs = ["Basics", "Tools/Memory", "Schedules", "Guardrails", "Channels"];
const models = ["gpt-4o-mini", "gpt-4", "gpt-3.5-turbo", "llama3.1"];
const draftKey = "agent-config-draft";

const defaultValues = {
  name: "",
  role: "",
  system_prompt: "",
  model: "gpt-4o-mini",
  tools: [{ name: "memory" }],
  channels: ["web"],
  memory_enabled: true,
  guardrails: {},
  schedule: null,
};

function toolNames(tools) {
  if (Array.isArray(tools)) return tools.map((tool) => (typeof tool === "string" ? tool : tool.name)).filter(Boolean);
  return tools?.enabled || [];
}

function channelNames(channels) {
  return (channels || []).map((channel) => (typeof channel === "string" ? channel : channel.name)).filter(Boolean);
}

function validate(values, guardrailsText) {
  const errors = {};
  const name = values.name.trim();
  if (!name) errors.name = "Name is required.";
  if (name.length > 120) errors.name = "Name must be 120 characters or fewer.";
  if ((values.role || "").length > 255) errors.role = "Role must be 255 characters or fewer.";
  if (!values.model.trim()) errors.model = "Model is required.";
  if (!models.includes(values.model)) errors.model = "Choose a supported model.";
  if (!channelNames(values.channels).length) errors.channels = "Select at least one channel.";
  if (values.schedule?.cron && values.schedule.cron.trim().split(/\s+/).length !== 5) {
    errors.schedule = "Cron schedule must have 5 parts.";
  }
  try {
    const parsed = guardrailsText.trim() ? JSON.parse(guardrailsText) : {};
    if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
      errors.guardrails = "Guardrails must be a JSON object.";
    }
    if (parsed.max_tokens !== undefined && Number(parsed.max_tokens) <= 0) {
      errors.guardrails = "guardrails.max_tokens must be positive.";
    }
    if (parsed.blocked_terms !== undefined && !Array.isArray(parsed.blocked_terms)) {
      errors.guardrails = "guardrails.blocked_terms must be an array.";
    }
  } catch {
    errors.guardrails = "Guardrails must be valid JSON.";
  }
  return errors;
}

export default function AgentConfig({ agent, initialValues, onCancel, onSubmit, isSaving = false }) {
  const initial = useMemo(() => agent || initialValues || defaultValues, [agent, initialValues]);
  const [activeTab, setActiveTab] = useState(tabs[0]);
  const [values, setValues] = useState(defaultValues);
  const [guardrailsText, setGuardrailsText] = useState("{}");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [draftStatus, setDraftStatus] = useState("Draft ready");
  const [submitError, setSubmitError] = useState("");
  const [testPrompt, setTestPrompt] = useState("");
  const [testMessages, setTestMessages] = useState([]);
  const [isTesting, setIsTesting] = useState(false);
  const [isLocalSaving, setIsLocalSaving] = useState(false);
  const [toolOptions, setToolOptions] = useState([]);

  useEffect(() => {
    const draft = !agent && !initialValues ? readDraft() : null;
    const source = draft || initial;
    setValues({
      ...defaultValues,
      ...source,
      tools: toolNames(source.tools).map((name) => ({ name })),
      channels: channelNames(source.channels),
    });
    setGuardrailsText(JSON.stringify(source.guardrails || {}, null, 2));
  }, [agent, initial, initialValues]);

  useEffect(() => {
    getToolList()
      .then((tools) => setToolOptions(tools))
      .catch(() => setToolOptions([]));
  }, []);

  const errors = useMemo(() => validate(values, guardrailsText), [guardrailsText, values]);
  const isValid = Object.keys(errors).length === 0;
  const previewPrompt = values.system_prompt?.trim() || [
    `You are ${values.name || "an unnamed agent"}.`,
    values.role ? `Role: ${values.role}.` : "",
    values.memory_enabled ? "Use memory when helpful and respect saved context." : "Do not persist memory.",
    "Follow configured guardrails and respond clearly.",
  ].filter(Boolean).join("\n");

  useEffect(() => {
    setDraftStatus("Saving draft...");
    const timer = window.setTimeout(() => {
      localStorage.setItem(draftKey, JSON.stringify({ ...values, guardrails: safeJson(guardrailsText) }));
      setDraftStatus("Draft saved");
    }, 450);
    return () => window.clearTimeout(timer);
  }, [guardrailsText, values]);

  const setField = (field, value) => setValues((current) => ({ ...current, [field]: value }));
  const setTools = (next) => {
    const unique = [...new Set(next)];
    setField("tools", unique.map((name) => ({ name })));
    setField("memory_enabled", unique.includes("memory"));
  };
  const setChannels = (next) => setField("channels", [...new Set(next)]);

  const handleSubmit = (event) => {
    event.preventDefault();
    setSubmitError("");
    const currentErrors = validate(values, guardrailsText);
    if (Object.keys(currentErrors).length) {
      setSubmitError("Fix highlighted fields before saving.");
      setActiveTab(tabForError(currentErrors));
      return;
    }
    const payload = {
      ...values,
      name: values.name.trim(),
      role: values.role?.trim() || null,
      guardrails: safeJson(guardrailsText),
      schedule: values.schedule?.cron ? values.schedule : null,
    };
    if (onSubmit) {
      onSubmit(payload);
      return;
    }
    setIsLocalSaving(true);
    createAgent(payload)
      .then(() => {
        setDraftStatus("Agent saved");
        localStorage.removeItem(draftKey);
      })
      .catch(() => setSubmitError("Could not save agent."))
      .finally(() => setIsLocalSaving(false));
  };

  const handleTestAgent = async () => {
    if (!agent?.id || !testPrompt.trim()) return;
    setIsTesting(true);
    setTestMessages((current) => [...current, { role: "user", content: testPrompt }]);
    try {
      const run = await executeAgent(agent.id, testPrompt);
      const socket = connectRunSocket(run.run_id);
      socket.on("*", (event) => {
        if (event.type === "completed") {
          setTestMessages((current) => [...current, { role: "agent", content: event.result || "Completed." }]);
          setIsTesting(false);
          socket.close();
        }
        if (event.type === "failed") {
          setTestMessages((current) => [...current, { role: "error", content: event.message || "Execution failed." }]);
          setIsTesting(false);
          socket.close();
        }
      });
      setTestPrompt("");
    } catch {
      setTestMessages((current) => [...current, { role: "error", content: "Could not start test run." }]);
      setIsTesting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2 border-b border-line pb-2" role="tablist" aria-label="Agent configuration sections">
          {tabs.map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={activeTab === tab}
              onClick={() => setActiveTab(tab)}
              className={`rounded-md px-3 py-2 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-ink/30 ${
                activeTab === tab ? "bg-ink text-white" : "text-muted hover:bg-soft hover:text-ink"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {submitError ? <InlineAlert>{submitError}</InlineAlert> : null}

        {activeTab === "Basics" ? (
          <BasicsTab values={values} errors={errors} setField={setField} previewPrompt={previewPrompt} />
        ) : null}
        {activeTab === "Tools/Memory" ? (
          <ToolsTab values={values} toolOptions={toolOptions} setTools={setTools} setField={setField} advancedOpen={advancedOpen} setAdvancedOpen={setAdvancedOpen} />
        ) : null}
        {activeTab === "Schedules" ? <ScheduleTab values={values} errors={errors} setField={setField} /> : null}
        {activeTab === "Guardrails" ? (
          <GuardrailsTab value={guardrailsText} setValue={setGuardrailsText} error={errors.guardrails} advancedOpen={advancedOpen} setAdvancedOpen={setAdvancedOpen} />
        ) : null}
        {activeTab === "Channels" ? (
          <ChannelsTab values={values} errors={errors} setChannels={setChannels} />
        ) : null}

        {agent?.id ? (
          <TestPanel
            testPrompt={testPrompt}
            setTestPrompt={setTestPrompt}
            testMessages={testMessages}
            isTesting={isTesting}
            onTest={handleTestAgent}
          />
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4">
          <span className="text-sm text-muted" aria-live="polite">{draftStatus}</span>
          <div className="flex gap-2">
            <button type="button" onClick={onCancel || (() => window.history.back())} className="rounded-md border border-line px-4 py-2 text-sm font-medium">
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSaving || isLocalSaving || !isValid}
              title={!isValid ? "Fix validation errors before saving" : "Save agent"}
              className="rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
            >
              {isSaving || isLocalSaving ? "Saving..." : "Save Agent"}
            </button>
          </div>
        </div>
      </div>

      <PreviewPanel values={values} prompt={previewPrompt} guardrails={safeJson(guardrailsText)} errors={errors} />
    </form>
  );
}

function BasicsTab({ values, errors, setField, previewPrompt }) {
  return (
    <section className="space-y-4" role="tabpanel">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" error={errors.name} required>
          <input value={values.name} onChange={(event) => setField("name", event.target.value)} className={inputClass(errors.name)} placeholder="Researcher" />
        </Field>
        <Field label="Role" error={errors.role}>
          <input value={values.role || ""} onChange={(event) => setField("role", event.target.value)} className={inputClass(errors.role)} placeholder="Market research agent" />
        </Field>
      </div>
      <Field label="Model" error={errors.model} required>
        <select value={values.model} onChange={(event) => setField("model", event.target.value)} className={inputClass(errors.model)}>
          {models.map((model) => <option key={model} value={model}>{model}</option>)}
        </select>
      </Field>
      <Field label="System Prompt">
        <textarea value={values.system_prompt || ""} onChange={(event) => setField("system_prompt", event.target.value)} className="min-h-32 w-full rounded-md border border-line px-3 py-2" placeholder={previewPrompt} />
      </Field>
    </section>
  );
}

function ToolsTab({ values, toolOptions, setTools, setField, advancedOpen, setAdvancedOpen }) {
  return (
    <section className="space-y-4" role="tabpanel">
      <ConfigToggles toolItems={toolOptions} tools={toolNames(values.tools)} channels={channelNames(values.channels)} onToolsChange={setTools} onChannelsChange={() => {}} maxChannels={10} />
      <label className="flex items-center justify-between rounded-md border border-line bg-surface px-3 py-2">
        <span><span className="block text-sm font-medium">Memory Enabled</span><span className="text-xs text-muted">Let the agent store short context.</span></span>
        <input type="checkbox" checked={values.memory_enabled} onChange={(event) => {
          const selected = new Set(toolNames(values.tools));
          if (event.target.checked) selected.add("memory"); else selected.delete("memory");
          setTools([...selected]);
        }} className="h-5 w-5" />
      </label>
      <button type="button" onClick={() => setAdvancedOpen((value) => !value)} className="rounded-md border border-line px-3 py-2 text-sm font-semibold">
        {advancedOpen ? "Hide Advanced" : "Show Advanced"}
      </button>
      {advancedOpen ? (
        <Field label="Tool Notes">
          <textarea value={values.tool_notes || ""} onChange={(event) => setField("tool_notes", event.target.value)} className="min-h-20 w-full rounded-md border border-line px-3 py-2" placeholder="Optional notes for tool use." />
        </Field>
      ) : null}
    </section>
  );
}

function ScheduleTab({ values, errors, setField }) {
  return (
    <section className="space-y-4" role="tabpanel">
      <Field label="Schedule" error={errors.schedule}>
        <input value={values.schedule?.cron || ""} onChange={(event) => setField("schedule", { cron: event.target.value })} className={inputClass(errors.schedule)} placeholder="0 9 * * 1" />
      </Field>
      <p className="rounded-md border border-line bg-soft px-3 py-2 text-sm text-muted">Leave blank for manual-only execution.</p>
    </section>
  );
}

function GuardrailsTab({ value, setValue, error, advancedOpen, setAdvancedOpen }) {
  return (
    <section className="space-y-4" role="tabpanel">
      <Field label="Guardrails JSON" error={error}>
        <textarea value={value} onChange={(event) => setValue(event.target.value)} className={`${inputClass(error)} min-h-40 font-mono text-sm`} />
      </Field>
      <button type="button" onClick={() => setAdvancedOpen((next) => !next)} className="rounded-md border border-line px-3 py-2 text-sm font-semibold">
        {advancedOpen ? "Hide Advanced" : "Show Advanced"}
      </button>
      {advancedOpen ? <p className="text-sm text-muted">Supported fields include max_tokens and blocked_terms.</p> : null}
    </section>
  );
}

function ChannelsTab({ values, errors, setChannels }) {
  return (
    <section className="space-y-4" role="tabpanel">
      <ConfigToggles tools={toolNames(values.tools)} channels={channelNames(values.channels)} onToolsChange={() => {}} onChannelsChange={setChannels} maxTools={10} />
      {errors.channels ? <InlineAlert>{errors.channels}</InlineAlert> : null}
    </section>
  );
}

function PreviewPanel({ values, prompt, guardrails, errors }) {
  const tools = toolNames(values.tools);
  const channels = channelNames(values.channels);
  return (
    <aside className="rounded-md border border-line bg-surface-strong p-4 lg:sticky lg:top-4 lg:self-start">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Live Preview</h3>
        <span className={`rounded-full px-2 py-1 text-xs font-semibold ${Object.keys(errors).length ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"}`}>
          {Object.keys(errors).length ? "Needs fixes" : "Valid"}
        </span>
      </div>
      <div className="mt-4 space-y-4 text-sm">
        <PreviewBlock title="Rendered System Prompt">{prompt}</PreviewBlock>
        <PreviewBlock title="Tools">{tools.length ? tools.join(", ") : "No tools enabled"}</PreviewBlock>
        <PreviewBlock title="Channels">{channels.length ? channels.join(", ") : "No channels selected"}</PreviewBlock>
        <PreviewBlock title="Schedule">{values.schedule?.cron || "Manual only"}</PreviewBlock>
        <PreviewBlock title="Guardrails">{Object.keys(guardrails || {}).length ? JSON.stringify(guardrails) : "No guardrails configured"}</PreviewBlock>
      </div>
    </aside>
  );
}

function TestPanel({ testPrompt, setTestPrompt, testMessages, isTesting, onTest }) {
  return (
    <section className="rounded-md border border-line bg-surface-strong p-3">
      <div className="flex items-center justify-between gap-3">
        <div><p className="text-sm font-semibold">Test Agent</p><p className="text-xs text-muted">Send a direct task and stream the response.</p></div>
        <button type="button" onClick={onTest} disabled={isTesting || !testPrompt.trim()} className="rounded-md bg-ink px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">{isTesting ? "Testing..." : "Test Agent"}</button>
      </div>
      <div className="mt-3 max-h-48 space-y-2 overflow-y-auto">
        {testMessages.map((message, index) => (
          <div key={`${message.role}-${index}`} className={`rounded-md px-3 py-2 text-sm ${message.role === "user" ? "ml-auto max-w-[80%] bg-surface" : message.role === "error" ? "bg-red-50 text-red-700" : "mr-auto max-w-[80%] bg-emerald-50"}`}>{message.content}</div>
        ))}
      </div>
      <textarea value={testPrompt} onChange={(event) => setTestPrompt(event.target.value)} className="mt-3 min-h-20 w-full rounded-md border border-line px-3 py-2 text-sm" placeholder="Ask this agent to do something..." />
    </section>
  );
}

function Field({ label, error, required, children }) {
  const id = label.replace(/\W+/g, "-").toLowerCase();
  return (
    <label className="block space-y-1" title={error || ""}>
      <span className="text-sm font-medium">{label}{required ? <span className="text-red-600"> *</span> : null}</span>
      {React.cloneElement(children, { id, "aria-label": label, "aria-invalid": Boolean(error), "aria-describedby": error ? `${id}-error` : undefined })}
      {error ? <span id={`${id}-error`} className="block text-xs font-medium text-red-700">{error}</span> : null}
    </label>
  );
}

function PreviewBlock({ title, children }) {
  return <div><p className="text-xs font-semibold uppercase text-muted">{title}</p><p className="mt-1 whitespace-pre-wrap rounded-md border border-line bg-surface p-2">{children}</p></div>;
}

function InlineAlert({ children }) {
  return <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{children}</div>;
}

function inputClass(error) {
  return `w-full rounded-md border px-3 py-2 ${error ? "border-red-300 bg-red-50" : "border-line"}`;
}

function safeJson(text) {
  try {
    const parsed = text.trim() ? JSON.parse(text) : {};
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function readDraft() {
  try {
    return JSON.parse(localStorage.getItem(draftKey) || "null");
  } catch {
    return null;
  }
}

function tabForError(errors) {
  if (errors.name || errors.role || errors.model) return "Basics";
  if (errors.schedule) return "Schedules";
  if (errors.guardrails) return "Guardrails";
  if (errors.channels) return "Channels";
  return "Basics";
}
