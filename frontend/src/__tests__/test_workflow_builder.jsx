import React from "react";
import { describe, expect, it } from "vitest";

import {
  compileWorkflow,
  decorateValidation,
  hydrateWorkflowNodes,
  validateWorkflow,
} from "../utils/workflowCompiler";

describe("workflow builder validation", () => {
  it("adds nodes, connects edges, and compiles workflow", () => {
    const nodes = [
      { id: "input", type: "input", position: { x: 0, y: 0 }, data: { label: "Input" } },
      {
        id: "agent",
        type: "agent",
        position: { x: 100, y: 0 },
        data: { agent_id: 1, label: "Agent" },
      },
      { id: "output", type: "output", position: { x: 200, y: 0 }, data: { label: "Output" } },
    ];
    const edges = [
      { id: "e1", source: "input", target: "agent" },
      { id: "e2", source: "agent", target: "output" },
    ];

    const validation = validateWorkflow(nodes, edges);
    const compiled = compileWorkflow(nodes, edges);

    expect(validation.valid).toBe(true);
    expect(compiled.nodes).toHaveLength(3);
    expect(compiled.edges).toHaveLength(2);
  });

  it("hydrates agent nodes by saved id or label", () => {
    const nodes = [
      {
        id: "agent-1",
        type: "agent",
        position: { x: 100, y: 0 },
        data: { agent_id: "1", label: "Researcher" },
      },
      {
        id: "agent-2",
        type: "agent",
        position: { x: 200, y: 0 },
        data: { label: "Writer" },
      },
    ];
    const agents = [
      { id: 1, name: "Researcher", role: "Research", tools: ["search"] },
      { id: 2, name: "Writer", role: "Writing", tools: ["memory"] },
    ];

    const hydrated = hydrateWorkflowNodes(nodes, agents);

    expect(hydrated[0].data.agent_id).toBe(1);
    expect(hydrated[0].data.agentId).toBe(1);
    expect(hydrated[1].data.agent_id).toBe(2);
    expect(hydrated[1].data.label).toBe("Writer");
  });

  it("flags cyclic graphs and decorates inline errors", () => {
    const nodes = [
      { id: "input", type: "input", position: { x: 0, y: 0 }, data: { label: "Input" } },
      { id: "agent-a", type: "agent", position: { x: 100, y: 0 }, data: { agent_id: 1, label: "Agent A" } },
      { id: "agent-b", type: "agent", position: { x: 200, y: 0 }, data: { agent_id: 2, label: "Agent B" } },
      { id: "output", type: "output", position: { x: 300, y: 0 }, data: { label: "Output" } },
    ];
    const edges = [
      { id: "e1", source: "input", target: "agent-a" },
      { id: "e2", source: "agent-a", target: "agent-b" },
      { id: "e3", source: "agent-b", target: "agent-a" },
      { id: "e4", source: "agent-b", target: "output" },
    ];

    const validation = validateWorkflow(nodes, edges);
    const decorated = decorateValidation(nodes, edges, validation);

    expect(validation.valid).toBe(false);
    expect(validation.errors.join(" ")).toContain("cycle");
    expect(decorated.nodes.find((node) => node.id === "agent-a").data.validationErrors.length).toBeGreaterThan(0);
  });

  it("allows cycles that are explicitly marked as feedback loops", () => {
    const nodes = [
      { id: "input", type: "input", position: { x: 0, y: 0 }, data: { label: "Input" } },
      { id: "agent-a", type: "agent", position: { x: 100, y: 0 }, data: { agent_id: 1, label: "Agent A" } },
      { id: "agent-b", type: "agent", position: { x: 200, y: 0 }, data: { agent_id: 2, label: "Agent B" } },
      { id: "output", type: "output", position: { x: 300, y: 0 }, data: { label: "Output" } },
    ];
    const edges = [
      { id: "e1", source: "input", target: "agent-a" },
      { id: "e2", source: "agent-a", target: "agent-b" },
      { id: "e3", source: "agent-b", target: "agent-a", type: "feedback", data: { feedback_loop: true } },
      { id: "e4", source: "agent-b", target: "output" },
    ];

    expect(validateWorkflow(nodes, edges).valid).toBe(true);
  });
});
