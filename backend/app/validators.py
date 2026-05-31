from __future__ import annotations

from typing import Any


VALID_MODELS = {"gpt-4o-mini", "gpt-4", "gpt-3.5-turbo", "llama3.1"}
VALID_CHANNELS = {"web", "telegram", "internal", "slack", "whatsapp"}


class ValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_workflow(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    errors: list[str] = []
    node_ids = {node.get("id") for node in nodes if node.get("id")}

    if not nodes:
        errors.append("workflow must include at least one node")

    connected: set[str] = set()
    adjacency = {node_id: [] for node_id in node_ids}
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source not in node_ids:
            errors.append(f"edge {edge.get('id', '<unknown>')} has invalid source")
        if target not in node_ids:
            errors.append(f"edge {edge.get('id', '<unknown>')} has invalid target")
        if source in node_ids and target in node_ids:
            adjacency[source].append(target)
            connected.update({source, target})

    for node in nodes:
        node_id = node.get("id")
        node_type = node.get("type")
        if not node_id:
            errors.append("every node must have an id")
            continue
        if node_type not in {"agent", "condition", "input", "output"}:
            errors.append(f"node {node_id} has unsupported type")
        if node_type not in {"input", "output"} and node_id not in connected:
            errors.append(f"node {node_id} is orphaned")
        if node_type == "agent":
            data = node.get("data") or {}
            if not (data.get("agent_id") or data.get("agentId")):
                errors.append(f"agent node {node_id} is not linked to an agent")

    if _has_cycle(adjacency) and not _cycles_are_marked_feedback(edges):
        errors.append("workflow graph contains a cycle")

    if errors:
        raise ValidationError(errors)


def validate_agent_config(config: dict[str, Any]) -> None:
    errors: list[str] = []
    if not str(config.get("name", "")).strip():
        errors.append("agent name is required")
    if config.get("model") and config["model"] not in VALID_MODELS:
        errors.append("agent model is not supported")
    for channel in config.get("channels") or []:
        channel_name = channel.get("name") if isinstance(channel, dict) else channel
        if channel_name not in VALID_CHANNELS:
            errors.append(f"channel {channel_name} is not supported")
    validate_guardrules(config.get("guardrails") or {})
    if errors:
        raise ValidationError(errors)


def validate_guardrules(rules: dict[str, Any]) -> None:
    errors: list[str] = []
    if not isinstance(rules, dict):
        raise ValidationError(["guardrails must be a JSON object"])
    if "max_tokens" in rules and int(rules["max_tokens"]) <= 0:
        errors.append("guardrails.max_tokens must be positive")
    if "blocked_terms" in rules and not isinstance(rules["blocked_terms"], list):
        errors.append("guardrails.blocked_terms must be an array")
    if errors:
        raise ValidationError(errors)


def _has_cycle(adjacency: dict[str, list[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for target in adjacency.get(node_id, []):
            if visit(target):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    return any(visit(node_id) for node_id in adjacency)


def _cycles_are_marked_feedback(edges: list[dict[str, Any]]) -> bool:
    return any(
        bool((edge.get("data") or {}).get("feedback_loop") or edge.get("feedback_loop"))
        for edge in edges
    )
