import React from "react";
export default function WorkflowToolbar({
  templates,
  selectedTemplate,
  onTemplateChange,
  onSave,
  onRun,
  onClear,
  onValidate,
  onExport,
  onImport,
  onZoomIn,
  onZoomOut,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
  isSaving,
  isRunning,
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-line bg-surface p-3 transition-colors">
      <button onClick={onSave} disabled={isSaving} className="rounded-md bg-ink px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">
        {isSaving ? "Saving..." : "Save"}
      </button>
      <button onClick={onRun} disabled={isRunning} className="rounded-md border border-line px-3 py-2 text-sm font-semibold disabled:opacity-50">
        {isRunning ? "Running..." : "Run"}
      </button>
      <button onClick={onValidate} className="rounded-md border border-line px-3 py-2 text-sm font-semibold">
        Validate
      </button>
      <button onClick={onUndo} disabled={!canUndo} title="Undo (Ctrl+Z)" className="rounded-md border border-line px-3 py-2 text-sm font-semibold disabled:opacity-50">
        Undo
      </button>
      <button onClick={onRedo} disabled={!canRedo} title="Redo (Ctrl+Y)" className="rounded-md border border-line px-3 py-2 text-sm font-semibold disabled:opacity-50">
        Redo
      </button>
      <button onClick={onClear} className="rounded-md border border-line px-3 py-2 text-sm font-semibold">
        Clear
      </button>
      <span className="mx-1 h-6 w-px bg-line" />
      <button onClick={onZoomIn} className="rounded-md border border-line px-3 py-2 text-sm font-semibold">
        +
      </button>
      <button onClick={onZoomOut} className="rounded-md border border-line px-3 py-2 text-sm font-semibold">
        -
      </button>
      <span className="mx-1 h-6 w-px bg-line" />
      <select
        value={selectedTemplate}
        onChange={(event) => onTemplateChange(event.target.value)}
        className="rounded-md border border-line px-3 py-2 text-sm"
      >
        <option value="">Load Template</option>
        {templates.map((template) => (
          <option key={template.id || template.name} value={template.id || template.name}>
            {template.name}
          </option>
        ))}
      </select>
      <button onClick={onExport} className="rounded-md border border-line px-3 py-2 text-sm font-semibold">
        Export JSON
      </button>
      <label className="cursor-pointer rounded-md border border-line px-3 py-2 text-sm font-semibold">
        Import JSON
        <input type="file" accept="application/json" onChange={onImport} className="hidden" />
      </label>
    </div>
  );
}
