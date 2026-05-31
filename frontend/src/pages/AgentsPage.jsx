import React from "react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import AgentCard, { AgentCardSkeleton } from "../components/AgentCard";
import AgentChatConsole from "../components/AgentChatConsole";
import AgentForm from "../components/AgentForm";
import AgentGenerator from "../components/AgentGenerator";
import { notifySuccess, notifyWarning } from "../components/ErrorToast";
import SearchFilterBar, { fuzzyMatch, getQueryFilters } from "../components/SearchFilterBar";
import { createAgent, deleteAgent, getAgents, getAllMessages, updateAgent } from "../services/api";

function readableList(items = []) {
  return items
    .map((item) => (typeof item === "string" ? item : item.name))
    .filter(Boolean)
    .join(", ");
}

export default function AgentsPage() {
  const [searchParams] = useSearchParams();
  const [agents, setAgents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingAgent, setEditingAgent] = useState(null);
  const [generatedAgent, setGeneratedAgent] = useState(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isGeneratorOpen, setIsGeneratorOpen] = useState(false);
  const [chatAgent, setChatAgent] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [usageByAgent, setUsageByAgent] = useState({});

  const activeCount = useMemo(
    () => agents.filter((agent) => agent.channels?.length).length,
    [agents],
  );
  const filters = useMemo(
    () => getQueryFilters(searchParams, ["status", "model", "channel"]),
    [searchParams],
  );

  const filterGroups = useMemo(
    () => [
      {
        key: "status",
        label: "Status",
        options: [
          { value: "active", label: "Active" },
          { value: "inactive", label: "Inactive" },
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
    ],
    [agents],
  );

  const filteredAgents = useMemo(
    () =>
      agents.filter((agent) => {
        const channelNames = readableArray(agent.channels);
        const status = channelNames.length ? "active" : "inactive";
        const queryMatches =
          fuzzyMatch(agent.name, filters.q) ||
          String(agent.role || "").toLowerCase().includes(filters.q.toLowerCase()) ||
          readableList(agent.tools).toLowerCase().includes(filters.q.toLowerCase());
        const statusMatches = !filters.status.length || filters.status.includes(status);
        const modelMatches = !filters.model.length || filters.model.includes(agent.model);
        const channelMatches =
          !filters.channel.length || filters.channel.every((channel) => channelNames.includes(channel));
        return queryMatches && statusMatches && modelMatches && channelMatches;
      }).sort(sortAgents),
    [agents, filters],
  );

  const loadAgents = async () => {
    setIsLoading(true);
    setError("");
    try {
      setAgents(await getAgents());
    } catch (err) {
      setError(err.response?.data?.detail || "Could not load agents.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadAgents();
  }, []);

  useEffect(() => {
    if (!agents.length) {
      setUsageByAgent({});
      return;
    }
    let active = true;
    Promise.all(
      agents.map((agent) =>
        getAllMessages({ agent_id: agent.id, limit: 7 })
          .then((messages) => [
            agent.id,
            messages
              .slice()
              .reverse()
              .map((message) => ({
                timestamp: message.timestamp,
                tokens: message.metadata?.tokens || 0,
              })),
          ])
          .catch(() => [agent.id, []]),
      ),
    ).then((entries) => {
      if (active) setUsageByAgent(Object.fromEntries(entries));
    });
    return () => {
      active = false;
    };
  }, [agents]);

  const openCreate = () => {
    setEditingAgent(null);
    setGeneratedAgent(null);
    setIsModalOpen(true);
  };

  const openGenerator = () => {
    setEditingAgent(null);
    setGeneratedAgent(null);
    setIsGeneratorOpen(true);
  };

  const openEdit = (agent) => {
    setEditingAgent(agent);
    setGeneratedAgent(null);
    setIsModalOpen(true);
  };

  const openChat = (agent) => {
    setChatAgent(agent);
  };

  const useGeneratedConfig = (config) => {
    if (!config) return;
    setGeneratedAgent(config);
    setEditingAgent(null);
    setIsGeneratorOpen(false);
    setIsModalOpen(true);
  };

  const handleSubmit = async (payload) => {
    setIsSaving(true);
    setError("");
    try {
      if (editingAgent) {
        await updateAgent(editingAgent.id, payload);
        notifySuccess("Agent updated");
      } else {
        await createAgent(payload);
        notifySuccess("Agent created");
      }
      setIsModalOpen(false);
      setGeneratedAgent(null);
      await loadAgents();
    } catch (err) {
      setError(err.response?.data?.detail || "Could not save agent.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = (agent) => {
    notifyWarning(`Delete ${agent.name}?`, {
      description: "This removes the agent configuration from the registry.",
      action: {
        label: "Delete",
        onClick: () => confirmDelete(agent),
      },
      cancel: {
        label: "Dismiss",
        onClick: () => {},
      },
    });
  };

  const confirmDelete = async (agent) => {
    setError("");
    try {
      await deleteAgent(agent.id);
      notifySuccess("Agent deleted");
      await loadAgents();
    } catch (err) {
      setError(err.response?.data?.detail || "Could not delete agent.");
    }
  };

  return (
    <div className="space-y-5">
      <section className="flex flex-col justify-between gap-3 rounded-md border border-line bg-surface p-4 transition-colors sm:flex-row sm:items-center">
        <div>
          <h3 className="text-lg font-semibold">Agent Registry</h3>
          <p className="text-sm text-muted">
            {agents.length} total agents, {activeCount} channel-enabled.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={openGenerator}
            className="rounded-md border border-line px-4 py-2 text-sm font-semibold"
          >
            ✨ Create from Prompt
          </button>
          <button
            onClick={openCreate}
            className="rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white"
          >
            Create Agent
          </button>
        </div>
      </section>

      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <SearchFilterBar
        filters={filters}
        groups={filterGroups}
        totalCount={agents.length}
        resultCount={filteredAgents.length}
        emptyLabel="No agents match. Try adjusting filters."
      />

      <section>
        {isLoading ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <AgentCardSkeleton key={index} />
            ))}
          </div>
        ) : filteredAgents.length ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {filteredAgents.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                usageData={usageByAgent[agent.id] || []}
                onEdit={openEdit}
                onTest={openChat}
                onDelete={handleDelete}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-line bg-surface px-4 py-12 text-center transition-colors">
            <p className="text-sm font-semibold">
              {agents.length ? "No agents match. Try adjusting filters." : "No agents yet. Create one to start."}
            </p>
            <p className="mt-1 text-sm text-muted">
              {agents.length ? "Clear a chip or search for another role." : "Generated or manual agents will appear here as preview cards."}
            </p>
          </div>
        )}
      </section>

      {isGeneratorOpen ? (
        <AgentGenerator
          onClose={() => setIsGeneratorOpen(false)}
          onUseConfig={useGeneratedConfig}
        />
      ) : null}

      {isModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4">
          <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-md bg-surface p-5 shadow-xl transition-colors">
            <div className="mb-4">
              <h3 className="text-xl font-bold">
                {editingAgent ? "Edit Agent" : "Create Agent"}
              </h3>
              <p className="text-sm text-muted">
                {generatedAgent
                  ? "Generated draft loaded. Review and edit before saving."
                  : "Configure personality, tools, channels, memory, limits, and schedules."}
              </p>
            </div>
            <AgentForm
              agent={editingAgent}
              initialValues={generatedAgent}
              isSaving={isSaving}
              onCancel={() => {
                setIsModalOpen(false);
                setGeneratedAgent(null);
              }}
              onSubmit={handleSubmit}
            />
          </div>
        </div>
      ) : null}

      {chatAgent ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-3 sm:p-4">
          <div className="w-full max-w-5xl">
            <AgentChatConsole
              agent={chatAgent}
              onClose={() => setChatAgent(null)}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
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

function sortAgents(a, b) {
  const lastUsedA = new Date(a.last_used_at || a.updated_at || a.created_at || 0).getTime();
  const lastUsedB = new Date(b.last_used_at || b.updated_at || b.created_at || 0).getTime();
  if (lastUsedA !== lastUsedB) return lastUsedB - lastUsedA;

  const statusA = readableArray(a.channels).length ? 1 : 0;
  const statusB = readableArray(b.channels).length ? 1 : 0;
  if (statusA !== statusB) return statusB - statusA;

  return String(a.name || "").localeCompare(String(b.name || ""));
}