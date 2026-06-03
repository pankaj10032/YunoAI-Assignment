import React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { applyEdgeChanges, applyNodeChanges, ReactFlowProvider, useReactFlow } from "@xyflow/react";
import { useSearchParams } from "react-router-dom";

import NodePalette from "../components/NodePalette";
import SearchFilterBar, { fuzzyMatch, getQueryFilters } from "../components/SearchFilterBar";
import WorkflowBuilder from "../components/WorkflowBuilder";
import WorkflowToolbar from "../components/WorkflowToolbar";
import {
  createWorkflow,
  getAgents,
  getWorkflows,
  runWorkflow,
  streamLogs,
  updateWorkflow,
} from "../services/api";
import customerSupport from "../templates/customerSupport.json";
import researchSummary from "../templates/researchSummary.json";
import {
  compileWorkflow,
  decorateValidation,
  hydrateWorkflowNodes,
  validateWorkflow,
} from "../utils/workflowCompiler";

const localTemplates = [researchSummary, customerSupport];

const emptyWorkflow = {
  name: "Untitled Workflow",
  description: "",
  nodes: [
    {
      id: "input-1",
      type: "input",
      position: { x: -260, y: 80 },
      data: { label: "Workflow Input" },
    },
    {
      id: "output-1",
      type: "output",
      position: { x: 520, y: 80 },
      data: { label: "Workflow Output" },
    },
  ],
  edges: [],
  is_template: false,
};

function toolsFromAgent(agent) {
  return (agent.tools || [])
    .map((tool) => (typeof tool === "string" ? tool : tool.name))
    .filter(Boolean);
}

function downloadJson(filename, payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function WorkflowsInner() {
  const [searchParams] = useSearchParams();
  const [agents, setAgents] = useState([]);
  const [workflows, setWorkflows] = useState([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const [workflowMeta, setWorkflowMeta] = useState(emptyWorkflow);
  const [nodes, setNodesRaw] = useState(emptyWorkflow.nodes);
  const [edges, setEdgesRaw] = useState(emptyWorkflow.edges);
  const historyRef = useRef({ undo: [], redo: [] });
  const [, forceHistoryRender] = useState(0);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [workflowInput, setWorkflowInput] = useState("Run this workflow from the visual builder.");
  const [latestRunOutput, setLatestRunOutput] = useState("");
  const [latestRunId, setLatestRunId] = useState(null);
  const { zoomIn, zoomOut, fitView } = useReactFlow();

  const snapshot = useCallback(
    () => ({
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
    }),
    [edges, nodes],
  );

  const pushHistory = useCallback(() => {
    historyRef.current.undo.push(snapshot());
    historyRef.current.redo = [];
    forceHistoryRender((value) => value + 1);
  }, [snapshot]);

  const setNodes = useCallback(
    (updater) => {
      pushHistory();
      setNodesRaw((current) => (typeof updater === "function" ? updater(current) : updater));
    },
    [pushHistory],
  );

  const setEdges = useCallback(
    (updater) => {
      pushHistory();
      setEdgesRaw((current) => (typeof updater === "function" ? updater(current) : updater));
    },
    [pushHistory],
  );

  const replaceCanvas = useCallback(
    (nextNodes, nextEdges, keepHistory = false) => {
      if (keepHistory) pushHistory();
      setNodesRaw(nextNodes);
      setEdgesRaw(nextEdges);
    },
    [pushHistory],
  );

  const onNodesChange = useCallback(
    (changes) => {
      if (changes.some((change) => change.type !== "dimensions")) pushHistory();
      setNodesRaw((current) => applyNodeChanges(changes, current));
    },
    [pushHistory],
  );

  const onEdgesChange = useCallback(
    (changes) => {
      pushHistory();
      setEdgesRaw((current) => applyEdgeChanges(changes, current));
    },
    [pushHistory],
  );

  const undo = useCallback(() => {
    const previous = historyRef.current.undo.pop();
    if (!previous) return;
    historyRef.current.redo.push(snapshot());
    setNodesRaw(previous.nodes);
    setEdgesRaw(previous.edges);
    forceHistoryRender((value) => value + 1);
  }, [snapshot]);

  const redo = useCallback(() => {
    const next = historyRef.current.redo.pop();
    if (!next) return;
    historyRef.current.undo.push(snapshot());
    setNodesRaw(next.nodes);
    setEdgesRaw(next.edges);
    forceHistoryRender((value) => value + 1);
  }, [snapshot]);

  const templates = useMemo(
    () => [
      ...localTemplates.map((template) => ({ ...template, id: `local:${template.name}` })),
      ...workflows.filter((workflow) => workflow.is_template),
    ],
    [workflows],
  );
  const filters = useMemo(
    () => getQueryFilters(searchParams, ["status", "model", "channel", "template"]),
    [searchParams],
  );

  const filterGroups = useMemo(
    () => [
      {
        key: "status",
        label: "Status",
        options: [
          { value: "valid", label: "Valid" },
          { value: "invalid", label: "Needs Fixes" },
        ],
      },
      {
        key: "model",
        label: "Model",
        options: uniqueOptions(agents.map((agent) => agent.model).filter(Boolean)),
      },
      {
        key: "channel",
        label: "Channel",
        options: uniqueOptions(agents.flatMap((agent) => readableArray(agent.channels))),
      },
      {
        key: "template",
        label: "Template",
        options: [
          { value: "template", label: "Templates" },
          { value: "workflow", label: "Workflows" },
        ],
      },
    ],
    [agents],
  );

  const workflowFilter = useCallback(
    (workflow) => workflowMatchesFilters(workflow, filters, agents),
    [filters, agents],
  );
  const filteredWorkflows = useMemo(
    () => workflows.filter(workflowFilter),
    [workflows, workflowFilter],
  );
  const filteredTemplates = useMemo(
    () => templates.filter(workflowFilter),
    [templates, workflowFilter],
  );
  const resultCount = filteredWorkflows.length + filteredTemplates.length;
  const totalCount = workflows.length + templates.length;

  const loadData = useCallback(async () => {
    const [agentData, workflowData] = await Promise.all([getAgents(), getWorkflows()]);
    setAgents(agentData);
    setWorkflows(workflowData);
  }, []);

  useEffect(() => {
    loadData().catch(() => setError("Could not load workflows or agents."));
  }, [loadData]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      if (event.key.toLowerCase() === "z") {
        event.preventDefault();
        undo();
      }
      if (event.key.toLowerCase() === "y") {
        event.preventDefault();
        redo();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [redo, undo]);

  const applyWorkflow = (workflow) => {
    setWorkflowMeta({
      id: workflow.id,
      name: workflow.name,
      description: workflow.description || "",
      is_template: Boolean(workflow.is_template),
    });
    replaceCanvas(hydrateWorkflowNodes(workflow.nodes || [], agents), workflow.edges || []);
    setSelectedWorkflowId(workflow.id ? String(workflow.id) : "");
    setTimeout(() => fitView({ padding: 0.2 }), 0);
  };

  const createNewWorkflow = () => {
    setSelectedWorkflowId("");
    setWorkflowMeta(emptyWorkflow);
    replaceCanvas(emptyWorkflow.nodes, emptyWorkflow.edges, true);
    setMessage("Started a new workflow.");
  };

  const handleTemplateChange = (value) => {
    setSelectedTemplate(value);
    if (!value) return;
    const local = templates.find((template) => String(template.id) === value);
    if (local) {
      applyWorkflow({
        ...local,
        id: undefined,
        is_template: false,
      });
      setWorkflowMeta((current) => ({
        ...current,
        name: `${local.name} Copy`,
        is_template: false,
      }));
    }
  };

  const handleSelectWorkflow = (id) => {
    const workflow = workflows.find((item) => String(item.id) === id);
    if (workflow) applyWorkflow(workflow);
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError("");
    const validation = validateWorkflow(nodes, edges);
    if (!validation.valid) {
      const decorated = decorateValidation(nodes, edges, validation);
      replaceCanvas(decorated.nodes, decorated.edges);
      setError(validation.errors.join(" "));
      setIsSaving(false);
      return;
    }
    const compiled = compileWorkflow(nodes, edges);
    const payload = {
      name: workflowMeta.name || "Untitled Workflow",
      description: workflowMeta.description || "",
      nodes: compiled.nodes,
      edges: compiled.edges,
      is_template: false,
    };
    try {
      const saved = selectedWorkflowId
        ? await updateWorkflow(selectedWorkflowId, payload)
        : await createWorkflow(payload);
      setMessage(`Saved ${saved.name}.`);
      await loadData();
      applyWorkflow(saved);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not save workflow.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleRun = async () => {
    setError("");
    setIsRunning(true);
    setLatestRunOutput("");
    try {
      let workflowId = selectedWorkflowId;
      if (!workflowId) {
        await handleSave();
        const refreshed = await getWorkflows();
        const latest = refreshed.find((workflow) => workflow.name === workflowMeta.name);
        workflowId = latest?.id;
      }
      if (!workflowId) throw new Error("Save workflow before running.");

      setNodes((items) =>
        items.map((node) =>
          node.type === "agent" ? { ...node, data: { ...node.data, status: "running" } } : node,
        ),
      );
      const run = await runWorkflow(workflowId, {
        input: workflowInput.trim(),
      });
      setLatestRunId(run.run_id);
      setMessage(`Started run #${run.run_id}.`);
      const socket = streamLogs(run.run_id, {
        onMessage: (event) => {
          if (event.type === "completed") {
            setLatestRunOutput(event.result || "");
            setNodes((items) =>
              items.map((node) =>
                node.type === "agent"
                  ? { ...node, data: { ...node.data, status: "completed" } }
                  : node,
              ),
            );
            setIsRunning(false);
          }
          if (event.type === "failed") {
            setLatestRunOutput("");
            setNodes((items) =>
              items.map((node) =>
                node.type === "agent" ? { ...node, data: { ...node.data, status: "error" } } : node,
              ),
            );
            setError(event.message || "Workflow run failed.");
            setIsRunning(false);
          }
        },
        onClose: () => setIsRunning(false),
      });
      return () => socket.close();
    } catch (err) {
      setError(err.message || err.response?.data?.detail || "Could not run workflow.");
      setIsRunning(false);
    }
  };

  const handleValidate = () => {
    const validation = validateWorkflow(nodes, edges);
    const decorated = decorateValidation(nodes, edges, validation);
    replaceCanvas(decorated.nodes, decorated.edges);
    if (validation.valid) {
      setError("");
      setMessage("Workflow is valid.");
    } else {
      setMessage("");
      setError(validation.errors.join(" "));
    }
  };

  const handleExport = () => {
    downloadJson(`${workflowMeta.name || "workflow"}.json`, {
      ...workflowMeta,
      ...compileWorkflow(nodes, edges),
    });
  };

  const handleImport = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const imported = JSON.parse(await file.text());
      applyWorkflow({
        ...imported,
        id: undefined,
        is_template: false,
      });
      setMessage(`Imported ${imported.name || "workflow"}.`);
    } catch {
      setError("Could not import workflow JSON.");
    } finally {
      event.target.value = "";
    }
  };

  return (
    <div className="space-y-4">
      <section className="rounded-md border border-line bg-surface p-4 transition-colors">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div className="grid flex-1 gap-3 md:grid-cols-[1fr_1.4fr]">
            <label className="space-y-1">
              <span className="text-sm font-medium">Workflow Name</span>
              <input
                value={workflowMeta.name}
                onChange={(event) =>
                  setWorkflowMeta((current) => ({ ...current, name: event.target.value }))
                }
                className="w-full rounded-md border border-line px-3 py-2"
              />
            </label>
            <label className="space-y-1">
              <span className="text-sm font-medium">Description</span>
              <input
                value={workflowMeta.description || ""}
                onChange={(event) =>
                  setWorkflowMeta((current) => ({
                    ...current,
                    description: event.target.value,
                  }))
                }
                className="w-full rounded-md border border-line px-3 py-2"
              />
            </label>
          </div>
          <div className="flex flex-wrap gap-2">
            <select
              value={selectedWorkflowId}
              onChange={(event) => handleSelectWorkflow(event.target.value)}
              className="rounded-md border border-line px-3 py-2 text-sm"
            >
              <option value="">Saved workflows</option>
              {workflows.map((workflow) => (
                <option key={workflow.id} value={workflow.id}>
                  {workflow.name}
                </option>
              ))}
            </select>
            <button
              onClick={createNewWorkflow}
              className="rounded-md border border-line px-3 py-2 text-sm font-semibold"
            >
              Create Workflow
            </button>
          </div>
        </div>
      </section>

      {message ? (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {message}
        </div>
      ) : null}
      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <SearchFilterBar
        filters={filters}
        groups={filterGroups}
        totalCount={totalCount}
        resultCount={resultCount}
        emptyLabel="No workflows match. Try adjusting filters."
      />

      <section className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-md border border-line bg-surface p-4 transition-colors">
          <h3 className="text-sm font-semibold">Saved Workflows</h3>
          <div className="mt-3 grid gap-2">
            {filteredWorkflows.length ? (
              filteredWorkflows.map((workflow) => (
                <button
                  key={workflow.id}
                  onClick={() => applyWorkflow(workflow)}
                  className="rounded-md border border-line px-3 py-2 text-left transition-colors hover:bg-soft"
                >
                  <span className="block text-sm font-semibold">{workflow.name}</span>
                  <span className="block text-xs text-muted">
                    {workflow.is_template ? "Template" : "Workflow"} · {workflow.nodes?.length || 0} nodes
                  </span>
                </button>
              ))
            ) : (
              <p className="text-sm text-muted">
                {workflows.length ? "No workflows match. Try adjusting filters." : "No saved workflows yet."}
              </p>
            )}
          </div>
        </div>
        <div className="rounded-md border border-line bg-surface p-4 transition-colors">
          <h3 className="text-sm font-semibold">Template Library</h3>
          <div className="mt-3 grid gap-2">
            {filteredTemplates.length ? (
              filteredTemplates.map((template) => (
                <button
                  key={template.id || template.name}
                  onClick={() => handleTemplateChange(String(template.id || template.name))}
                  className="rounded-md border border-line px-3 py-2 text-left transition-colors hover:bg-soft"
                >
                  <span className="block text-sm font-semibold">{template.name}</span>
                  <span className="block text-xs text-muted">
                    {template.description || "Reusable workflow template"}
                  </span>
                </button>
              ))
            ) : (
              <p className="text-sm text-muted">No templates match. Try adjusting filters.</p>
            )}
          </div>
        </div>
      </section>

      <section className="grid gap-3 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-md border border-line bg-surface p-4 transition-colors">
          <h3 className="text-sm font-semibold">Workflow Input</h3>
          <p className="mt-1 text-xs text-muted">
            This value is sent to the workflow as `input` when you click Run.
          </p>
          <textarea
            value={workflowInput}
            onChange={(event) => setWorkflowInput(event.target.value)}
            rows={5}
            className="mt-3 w-full rounded-md border border-line px-3 py-2 text-sm outline-none transition-colors focus:border-ink"
            placeholder="Enter the custom input for this workflow..."
          />
        </div>

        <div className="rounded-md border border-line bg-surface p-4 transition-colors">
          <h3 className="text-sm font-semibold">Latest Output</h3>
          <p className="mt-1 text-xs text-muted">
            {latestRunId ? `Run #${latestRunId}` : "No workflow has finished yet."}
          </p>
          <div className="mt-3 min-h-28 rounded-md border border-dashed border-line bg-soft px-3 py-2 text-sm text-ink">
            {latestRunOutput ? (
              <pre className="whitespace-pre-wrap font-sans text-sm">{latestRunOutput}</pre>
            ) : (
              <span className="text-muted">The completed workflow response will appear here.</span>
            )}
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-md border border-line bg-surface transition-colors">
        <WorkflowToolbar
          templates={templates}
          selectedTemplate={selectedTemplate}
          onTemplateChange={handleTemplateChange}
          onSave={handleSave}
          onRun={handleRun}
          onClear={() => {
            replaceCanvas([], [], true);
          }}
          onValidate={handleValidate}
          onExport={handleExport}
          onImport={handleImport}
          onZoomIn={() => zoomIn()}
          onZoomOut={() => zoomOut()}
          onUndo={undo}
          onRedo={redo}
          canUndo={historyRef.current.undo.length > 0}
          canRedo={historyRef.current.redo.length > 0}
          isSaving={isSaving}
          isRunning={isRunning}
        />
        <div className="flex flex-col lg:flex-row">
          <NodePalette agents={agents} />
          <WorkflowBuilder
            nodes={nodes}
            edges={edges}
            setNodes={setNodes}
            setEdges={setEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
          />
        </div>
      </section>
    </div>
  );
}

function workflowMatchesFilters(workflow, filters, agents) {
  const linkedAgents = linkedWorkflowAgents(workflow, agents);
  const status = validateWorkflow(workflow.nodes || [], workflow.edges || []).valid ? "valid" : "invalid";
  const templateTag = workflow.is_template || String(workflow.id || "").startsWith("local:") ? "template" : "workflow";
  const haystack = [
    workflow.name,
    workflow.description,
    ...(workflow.nodes || []).map((node) => node.data?.label || ""),
    ...linkedAgents.map((agent) => `${agent.name} ${agent.role || ""}`),
  ].join(" ");
  const queryMatches = fuzzyMatch(haystack, filters.q);
  const statusMatches = !filters.status.length || filters.status.includes(status);
  const templateMatches = !filters.template.length || filters.template.includes(templateTag);
  const modelMatches =
    !filters.model.length || filters.model.every((model) => linkedAgents.some((agent) => agent.model === model));
  const channelMatches =
    !filters.channel.length ||
    filters.channel.every((channel) =>
      linkedAgents.some((agent) => readableArray(agent.channels).includes(channel)),
    );
  return queryMatches && statusMatches && templateMatches && modelMatches && channelMatches;
}

function linkedWorkflowAgents(workflow, agents) {
  return (workflow.nodes || [])
    .filter((node) => node.type === "agent")
    .map((node) => {
      const agentId = node.data?.agent_id || node.data?.agentId;
      return (
        agents.find((agent) => String(agent.id) === String(agentId)) ||
        agents.find((agent) => agent.name === node.data?.label)
      );
    })
    .filter(Boolean);
}

function readableArray(items = []) {
  return items
    .map((item) => (typeof item === "string" ? item : item.name))
    .filter(Boolean);
}

function uniqueOptions(values = []) {
  return [...new Set(values)]
    .sort((a, b) => String(a).localeCompare(String(b)))
    .map((value) => ({ value, label: value }));
}

export default function WorkflowsPage() {
  return (
    <ReactFlowProvider>
      <WorkflowsInner />
    </ReactFlowProvider>
  );
}
