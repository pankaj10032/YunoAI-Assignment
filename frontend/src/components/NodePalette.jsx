import React from "react";
const specialNodes = [
  { type: "input", label: "Input" },
  { type: "condition", label: "Condition" },
  { type: "output", label: "Output" },
];

function dragData(payload) {
  return JSON.stringify(payload);
}

export default function NodePalette({ agents }) {
  const startDrag = (event, payload) => {
    event.dataTransfer.setData("application/reactflow", dragData(payload));
    event.dataTransfer.effectAllowed = "move";
  };

  return (
    <aside className="w-full shrink-0 border-b border-line bg-surface p-3 transition-colors lg:w-72 lg:border-b-0 lg:border-r">
      <div className="space-y-4">
        <section>
          <h3 className="text-sm font-semibold">Agents</h3>
          <div className="mt-2 space-y-2">
            {agents.map((agent) => (
              <div
                key={agent.id}
                draggable
                onDragStart={(event) =>
                  startDrag(event, {
                    type: "agent",
                    agent,
                  })
                }
                className="cursor-grab rounded-md border border-line bg-surface-strong p-3 transition-colors active:cursor-grabbing"
              >
                <p className="text-sm font-semibold">{agent.name}</p>
                <p className="mt-1 truncate text-xs text-muted">{agent.role || "Agent"}</p>
              </div>
            ))}
            {!agents.length ? <p className="text-sm text-muted">Create agents first.</p> : null}
          </div>
        </section>

        <section>
          <h3 className="text-sm font-semibold">Special Nodes</h3>
          <div className="mt-2 grid grid-cols-3 gap-2 lg:grid-cols-1">
            {specialNodes.map((node) => (
              <div
                key={node.type}
                draggable
                onDragStart={(event) => startDrag(event, node)}
                className="cursor-grab rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium transition-colors active:cursor-grabbing"
              >
                {node.label}
              </div>
            ))}
          </div>
        </section>
      </div>
    </aside>
  );
}