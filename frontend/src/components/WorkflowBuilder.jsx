import React from "react";
import { useCallback, useMemo, useRef } from "react";
import {
  addEdge,
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from "@xyflow/react";

import AgentNode from "./nodes/AgentNode";
import ConditionNode from "./nodes/ConditionNode";
import InputNode from "./nodes/InputNode";
import OutputNode from "./nodes/OutputNode";
import { edgeTypes } from "./edges/WorkflowEdges";

const nodeTypes = {
  agent: AgentNode,
  condition: ConditionNode,
  input: InputNode,
  output: OutputNode,
};

const GRID_SIZE = 24;

function snap(position) {
  return {
    x: Math.round(position.x / GRID_SIZE) * GRID_SIZE,
    y: Math.round(position.y / GRID_SIZE) * GRID_SIZE,
  };
}

function toolsFromAgent(agent) {
  return (agent.tools || []).map((tool) => (typeof tool === "string" ? tool : tool.name)).filter(Boolean);
}

function makeNode(payload, position) {
  const id = `${payload.type}-${Date.now()}-${Math.round(Math.random() * 1000)}`;
  const snappedPosition = snap(position);
  if (payload.type === "agent") {
    const agent = payload.agent;
    return {
      id,
      type: "agent",
      position: snappedPosition,
      data: {
        agent_id: agent.id,
        agentId: agent.id,
        label: agent.name,
        role: agent.role,
        status: "idle",
        tools: toolsFromAgent(agent),
        task: agent.system_prompt || `Complete work as ${agent.name}.`,
      },
    };
  }
  if (payload.type === "condition") {
    return {
      id,
      type: "condition",
      position: snappedPosition,
      data: { label: "Condition", expression: "" },
    };
  }
  return {
    id,
    type: payload.type,
    position: snappedPosition,
    data: { label: payload.label },
  };
}

function edgeFromConnection(params) {
  const label = params.sourceHandle === "true" ? "true" : params.sourceHandle === "false" ? "false" : "";
  const isConditional = Boolean(label);
  return {
    ...params,
    id: `e-${params.source}-${params.target}-${Date.now()}`,
    type: isConditional ? "conditional" : "default",
    label,
    animated: isConditional,
    markerEnd: { type: MarkerType.ArrowClosed },
    data: isConditional ? { condition: label } : {},
  };
}

function autoConnectEdges(nextNode, currentNodes, currentEdges) {
  if (!currentNodes.length || nextNode.type === "input") return [];
  const candidates = currentNodes
    .filter((node) => node.type !== "output" && node.position.x <= nextNode.position.x)
    .map((node) => ({
      node,
      distance: Math.abs(node.position.x - nextNode.position.x) + Math.abs(node.position.y - nextNode.position.y),
    }))
    .sort((a, b) => a.distance - b.distance);
  const source = candidates[0]?.node;
  if (!source || currentEdges.some((edge) => edge.source === source.id && edge.target === nextNode.id)) return [];
  const sourceHandle =
    source.type === "condition"
      ? currentEdges.some((edge) => edge.source === source.id && edge.sourceHandle === "true")
        ? "false"
        : "true"
      : undefined;
  return [edgeFromConnection({ source: source.id, target: nextNode.id, sourceHandle })];
}

export default function WorkflowBuilder({
  nodes,
  edges,
  onNodesChange,
  onEdgesChange,
  setNodes,
  setEdges,
}) {
  const wrapperRef = useRef(null);
  const { screenToFlowPosition, zoomIn, zoomOut } = useReactFlow();

  const decoratedNodes = useMemo(
    () =>
      nodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          onDelete: (id) => {
            setNodes((items) => items.filter((item) => item.id !== id));
            setEdges((items) => items.filter((edge) => edge.source !== id && edge.target !== id));
          },
          onChange: (id, patch) => {
            setNodes((items) =>
              items.map((item) =>
                item.id === id ? { ...item, data: { ...item.data, ...patch } } : item,
              ),
            );
          },
        },
      })),
    [nodes, setEdges, setNodes],
  );

  const onConnect = useCallback(
    (params) => {
      setEdges((items) => addEdge(edgeFromConnection(params), items));
    },
    [setEdges],
  );

  const onDrop = useCallback(
    (event) => {
      event.preventDefault();
      const raw = event.dataTransfer.getData("application/reactflow");
      if (!raw) return;
      const payload = JSON.parse(raw);
      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });
      setNodes((items) => {
        const node = makeNode(payload, position);
        setEdges((currentEdges) => [...currentEdges, ...autoConnectEdges(node, items, currentEdges)]);
        return [...items, node];
      });
    },
    [screenToFlowPosition, setEdges, setNodes],
  );

  const onDragOver = useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  return (
    <div ref={wrapperRef} className="h-[680px] min-h-[520px] flex-1">
      <ReactFlow
        nodes={decoratedNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onEdgeDoubleClick={(_, edge) => {
          setEdges((items) =>
            items.map((item) =>
              item.id === edge.id
                ? {
                    ...item,
                    type: item.type === "feedback" ? "default" : "feedback",
                    label: item.type === "feedback" ? item.label : "feedback",
                    data: {
                      ...(item.data || {}),
                      feedback_loop: item.type !== "feedback",
                    },
                  }
                : item,
            ),
          );
        }}
        onDrop={onDrop}
        onDragOver={onDragOver}
        snapToGrid
        snapGrid={[GRID_SIZE, GRID_SIZE]}
        fitView
      >
        <Background gap={GRID_SIZE} />
        <MiniMap
          pannable
          zoomable
          nodeColor={(node) =>
            node.type === "agent" ? "#2563eb" : node.type === "condition" ? "#f59e0b" : node.type === "input" ? "#22c55e" : "#10b981"
          }
        />
        <Controls />
      </ReactFlow>
      <div className="hidden">
        <button onClick={() => zoomIn()} />
        <button onClick={() => zoomOut()} />
      </div>
    </div>
  );
}

export function useWorkflowState(initialNodes = [], initialEdges = []) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  return { nodes, setNodes, onNodesChange, edges, setEdges, onEdgesChange };
}
