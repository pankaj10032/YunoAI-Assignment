export function compileWorkflow(nodes, edges) {
  const compiledNodes = nodes.map((node) => ({
    id: node.id,
    type: node.type,
    position: node.position,
    data: {
      ...node.data,
      onDelete: undefined,
      onChange: undefined,
      validationErrors: undefined,
    },
  }));

  const compiledEdges = edges.map((edge) => ({
    id: edge.id,
    type: edge.type,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle,
    targetHandle: edge.targetHandle,
    label: edge.label,
    data: edge.data || {},
  }));

  return { nodes: compiledNodes, edges: compiledEdges };
}

function normalizeAgentId(value) {
  if (value === null || value === undefined) return undefined;
  return String(value).trim();
}

function normalizeLabel(value) {
  return String(value || "").trim().toLowerCase();
}

function toolsFromAgent(agent) {
  return (agent.tools || []).map((tool) => (typeof tool === "string" ? tool : tool.name)).filter(Boolean);
}

export function hydrateWorkflowNodes(nodes, agents) {
  return nodes.map((node) => {
    if (node.type !== "agent") return node;

    const agentId = normalizeAgentId(node.data?.agent_id ?? node.data?.agentId);
    const label = normalizeLabel(node.data?.label);
    const match =
      agents.find((agent) => normalizeAgentId(agent.id) === agentId) ||
      (label ? agents.find((agent) => normalizeLabel(agent.name) === label) : undefined);

    if (!match) return node;

    return {
      ...node,
      data: {
        ...node.data,
        agent_id: match.id,
        agentId: match.id,
        label: match.name,
        role: match.role || node.data?.role,
        tools: toolsFromAgent(match).length ? toolsFromAgent(match) : node.data?.tools,
      },
    };
  });
}

export function validateWorkflow(nodes, edges) {
  const errors = [];
  const nodeErrors = {};
  const edgeErrors = {};
  const nodeIds = new Set(nodes.map((node) => node.id));
  const connected = new Set();
  const adjacency = Object.fromEntries(nodes.map((node) => [node.id, []]));

  const addNodeError = (nodeId, message) => {
    nodeErrors[nodeId] = [...(nodeErrors[nodeId] || []), message];
    errors.push(message);
  };

  const addEdgeError = (edgeId, message) => {
    edgeErrors[edgeId] = [...(edgeErrors[edgeId] || []), message];
    errors.push(message);
  };

  edges.forEach((edge) => {
    if (!nodeIds.has(edge.source)) addEdgeError(edge.id, `Edge ${edge.id} has missing source.`);
    if (!nodeIds.has(edge.target)) addEdgeError(edge.id, `Edge ${edge.id} has missing target.`);
    if (nodeIds.has(edge.source) && nodeIds.has(edge.target)) {
      connected.add(edge.source);
      connected.add(edge.target);
      adjacency[edge.source].push(edge.target);
    }

    const sourceNode = nodes.find((node) => node.id === edge.source);
    const targetNode = nodes.find((node) => node.id === edge.target);
    if (sourceNode?.type === "output") addEdgeError(edge.id, "Output nodes cannot start a connection.");
    if (targetNode?.type === "input") addEdgeError(edge.id, "Input nodes cannot receive a connection.");
    if (edge.source === edge.target) addEdgeError(edge.id, "A node cannot connect to itself.");
  });

  nodes.forEach((node) => {
    if (node.type !== "input" && node.type !== "output" && !connected.has(node.id)) {
      addNodeError(node.id, `${node.data?.label || node.id} is not connected.`);
    }
    if (node.type === "agent" && !(node.data?.agent_id || node.data?.agentId)) {
      addNodeError(node.id, `${node.data?.label || node.id} is not linked to a saved agent.`);
    }
  });

  if (!nodes.some((node) => node.type === "input")) {
    errors.push("Workflow needs an input node.");
  }
  if (!nodes.some((node) => node.type === "output")) {
    errors.push("Workflow needs an output node.");
  }
  if (!nodes.some((node) => node.type === "agent")) {
    errors.push("Workflow needs at least one agent node.");
  }

  const conditionNodes = nodes.filter((node) => node.type === "condition");
  conditionNodes.forEach((node) => {
    const outgoing = edges.filter((edge) => edge.source === node.id);
    const handles = new Set(outgoing.map((edge) => edge.sourceHandle));
    if (!handles.has("true") || !handles.has("false")) {
      addNodeError(node.id, `${node.data?.label || node.id} needs true and false branches.`);
    }
  });

  const cycleNodes = findCycleNodes(adjacency);
  if (cycleNodes.size) {
    const markedFeedback = edges.some((edge) => edge.type === "feedback" || edge.data?.feedback_loop);
    if (!markedFeedback) {
      cycleNodes.forEach((nodeId) => {
        addNodeError(nodeId, `${nodes.find((node) => node.id === nodeId)?.data?.label || nodeId} participates in a cycle.`);
      });
      errors.push("Workflow graph contains a cycle. Mark intentional loops as feedback edges.");
    }
  }

  return {
    valid: errors.length === 0,
    errors,
    nodeErrors,
    edgeErrors,
  };
}

export function decorateValidation(nodes, edges, validation) {
  return {
    nodes: nodes.map((node) => ({
      ...node,
      data: {
        ...node.data,
        validationErrors: validation.nodeErrors?.[node.id] || [],
      },
    })),
    edges: edges.map((edge) => ({
      ...edge,
      data: {
        ...(edge.data || {}),
        validationErrors: validation.edgeErrors?.[edge.id] || [],
      },
    })),
  };
}

function findCycleNodes(adjacency) {
  const visiting = new Set();
  const visited = new Set();
  const cycleNodes = new Set();
  const stack = [];

  function visit(nodeId) {
    if (visiting.has(nodeId)) {
      const index = stack.indexOf(nodeId);
      stack.slice(index).forEach((item) => cycleNodes.add(item));
      return;
    }
    if (visited.has(nodeId)) return;
    visiting.add(nodeId);
    stack.push(nodeId);
    (adjacency[nodeId] || []).forEach(visit);
    stack.pop();
    visiting.delete(nodeId);
    visited.add(nodeId);
  }

  Object.keys(adjacency).forEach(visit);
  return cycleNodes;
}
