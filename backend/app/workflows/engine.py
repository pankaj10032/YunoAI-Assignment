from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.agents.runtime import AgentRuntime
from app.models.database import SessionLocal
from app.models.models import Agent, Message, Workflow, WorkflowRun, WorkflowRunStep


MAX_STEP_VISITS = 25


class WorkflowExecutionError(RuntimeError):
    pass


class WorkflowPaused(RuntimeError):
    def __init__(self, step_id: str):
        super().__init__(f"Workflow paused at step '{step_id}'")
        self.step_id = step_id


@dataclass(frozen=True)
class EdgeRoute:
    target: str
    condition: str | None = None


def execute_workflow(
    workflow_id: int,
    input_data: dict[str, Any],
    resume_from_step: str | None = None,
    run_id: int | None = None,
) -> str:
    db = SessionLocal()
    try:
        run = db.get(WorkflowRun, run_id) if run_id else None
        workflow = db.get(Workflow, workflow_id)
        if not workflow:
            raise WorkflowExecutionError("Workflow not found")
        if not run:
            run = WorkflowRun(
                workflow_id=workflow_id,
                status="pending",
                started_at=_utc_now(),
                input_data=input_data or {},
            )
            db.add(run)
            db.commit()
            db.refresh(run)
        return StatefulWorkflowEngine(db).execute(workflow, run, input_data, resume_from_step)
    finally:
        db.close()


class StatefulWorkflowEngine:
    def __init__(self, db: Session):
        self.db = db
        self.runtime = AgentRuntime(db)

    def execute(
        self,
        workflow: Workflow,
        run: WorkflowRun,
        input_data: dict[str, Any],
        resume_from_step: str | None = None,
    ) -> str:
        nodes = {str(node.get("id")): node for node in workflow.nodes or [] if node.get("id")}
        if not nodes:
            raise WorkflowExecutionError("Workflow has no nodes")

        context = self._load_context(run) or {"input": input_data or {}, "outputs": {}, "last_output": ""}
        outgoing = self._build_edges(workflow.edges or [])
        current_step = self._next_resume_step(
            run,
            nodes,
            outgoing,
            resume_from_step,
        ) or self._start_node(nodes, workflow.edges or [])
        visits: dict[str, int] = {}

        run.status = "running"
        run.started_at = run.started_at or _utc_now()
        self.db.commit()

        while current_step:
            visits[current_step] = visits.get(current_step, 0) + 1
            if visits[current_step] > MAX_STEP_VISITS:
                raise WorkflowExecutionError(
                    f"Workflow loop limit exceeded at step '{current_step}'"
                )

            node = nodes.get(current_step)
            if not node:
                raise WorkflowExecutionError(f"Workflow step '{current_step}' was not found")

            try:
                output = self._run_node(run, node, context, visits[current_step])
            except Exception as exc:
                self._save_checkpoint(
                    run,
                    node,
                    context,
                    "failed",
                    None,
                    visits[current_step],
                    str(exc),
                )
                raise
            context["outputs"][current_step] = output
            context["last_output"] = output
            if self._should_pause(node):
                self._save_checkpoint(run, node, context, "paused", output, visits[current_step])
                run.status = "paused"
                self.db.commit()
                raise WorkflowPaused(current_step)

            self._save_checkpoint(run, node, context, "completed", output, visits[current_step])
            current_step = self._next_step(node, outgoing.get(current_step, []), context)

        result = str(context.get("last_output") or context.get("input") or "")
        run.status = "completed"
        run.completed_at = _utc_now()
        usage = _estimate_usage(result)
        run.total_tokens = usage["tokens"]
        run.total_cost = usage["cost"]
        self.db.commit()
        return result

    def _run_node(
        self,
        run: WorkflowRun,
        node: dict[str, Any],
        context: dict[str, Any],
        visit: int,
    ) -> str:
        self._save_checkpoint(run, node, context, "running", None, visit)
        node_type = (node.get("type") or "").lower()
        data = node.get("data") or {}
        if node_type == "input":
            return str(context.get("input") or "")
        if node_type == "output":
            return str(context.get("last_output") or context.get("input") or "")
        if node_type == "condition":
            result = self._evaluate_condition(data.get("expression") or "", context)
            context["condition_result"] = result
            return "true" if result else "false"
        if node_type == "agent":
            agent_id = data.get("agent_id") or data.get("agentId")
            if not agent_id:
                raise WorkflowExecutionError(f"Agent node '{node.get('id')}' has no agent_id")
            agent = self.db.get(Agent, int(agent_id))
            if not agent:
                raise WorkflowExecutionError(f"Agent '{agent_id}' not found")
            task = data.get("task") or f"{agent.name}: process the current workflow context."
            prompt = f"{task}\n\nWorkflow context:\n{context}"
            output = self.runtime.execute_single_agent(int(agent_id), prompt)
            _persist_message(self.db, run.id, int(agent_id), None, "internal", str(output))
            return str(output)
        return str(context.get("last_output") or "")

    def _save_checkpoint(
        self,
        run: WorkflowRun,
        node: dict[str, Any],
        context: dict[str, Any],
        status: str,
        output: str | None,
        visit: int,
        error: str | None = None,
    ) -> WorkflowRunStep:
        step_id = str(node.get("id"))
        checkpoint = (
            self.db.query(WorkflowRunStep)
            .filter(
                WorkflowRunStep.workflow_run_id == run.id,
                WorkflowRunStep.step_id == step_id,
                WorkflowRunStep.sequence == visit,
            )
            .one_or_none()
        )
        if not checkpoint:
            checkpoint = WorkflowRunStep(
                workflow_run_id=run.id,
                step_id=step_id,
                node_type=node.get("type") or "agent",
                agent_id=(node.get("data") or {}).get("agent_id")
                or (node.get("data") or {}).get("agentId"),
                sequence=visit,
            )
            self.db.add(checkpoint)
        checkpoint.status = status
        checkpoint.context_snapshot = deepcopy(context)
        checkpoint.agent_output = output
        checkpoint.error = error
        if status == "running":
            checkpoint.started_at = checkpoint.started_at or _utc_now()
        if status in {"completed", "failed", "paused"}:
            checkpoint.completed_at = _utc_now()
        self.db.commit()
        self.db.refresh(checkpoint)
        return checkpoint

    def _build_edges(self, edges: list[dict[str, Any]]) -> dict[str, list[EdgeRoute]]:
        outgoing: dict[str, list[EdgeRoute]] = {}
        for edge in edges:
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            if not source or not target:
                continue
            condition = (
                edge.get("sourceHandle")
                or edge.get("label")
                or (edge.get("data") or {}).get("condition")
            )
            outgoing.setdefault(source, []).append(EdgeRoute(target=target, condition=condition))
        return outgoing

    def _start_node(self, nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]]) -> str:
        targets = {str(edge.get("target")) for edge in edges if edge.get("target")}
        starters = [node_id for node_id in nodes if node_id not in targets]
        input_starters = [
            node_id for node_id in starters if (nodes[node_id].get("type") or "").lower() == "input"
        ]
        return (input_starters or starters or list(nodes))[0]

    def _next_resume_step(
        self,
        run: WorkflowRun,
        nodes: dict[str, dict[str, Any]],
        outgoing: dict[str, list[EdgeRoute]],
        resume_from_step: str | None,
    ) -> str | None:
        checkpoint = self._resume_checkpoint(run, resume_from_step)
        if not checkpoint:
            return resume_from_step
        node = nodes.get(checkpoint.step_id)
        if checkpoint.status == "paused" and node:
            context = checkpoint.context_snapshot or {}
            return self._next_step(node, outgoing.get(checkpoint.step_id, []), context)
        return checkpoint.step_id

    def _resume_checkpoint(
        self,
        run: WorkflowRun,
        resume_from_step: str | None,
    ) -> WorkflowRunStep | None:
        query = self.db.query(WorkflowRunStep).filter(WorkflowRunStep.workflow_run_id == run.id)
        if resume_from_step:
            return (
                query.filter(WorkflowRunStep.step_id == resume_from_step)
                .order_by(WorkflowRunStep.id.desc())
                .first()
            )
        failed_or_running = (
            query.filter(WorkflowRunStep.status.in_(["running", "failed", "paused"]))
            .order_by(WorkflowRunStep.id.desc())
            .first()
        )
        return failed_or_running

    def _load_context(self, run: WorkflowRun) -> dict[str, Any] | None:
        checkpoint = (
            self.db.query(WorkflowRunStep)
            .filter(WorkflowRunStep.workflow_run_id == run.id)
            .order_by(WorkflowRunStep.id.desc())
            .first()
        )
        return checkpoint.context_snapshot if checkpoint else None

    def _next_step(
        self,
        node: dict[str, Any],
        routes: list[EdgeRoute],
        context: dict[str, Any],
    ) -> str | None:
        if not routes:
            return None
        if (node.get("type") or "").lower() == "condition":
            desired = "true" if context.get("condition_result") else "false"
            for route in routes:
                if str(route.condition).lower() == desired:
                    return route.target
        return routes[0].target

    def _evaluate_condition(self, expression: str, context: dict[str, Any]) -> bool:
        if not expression.strip():
            return bool(context.get("last_output"))
        tree = ast.parse(expression, mode="eval")
        for node in ast.walk(tree):
            if not isinstance(
                node,
                (
                    ast.Expression,
                    ast.BoolOp,
                    ast.UnaryOp,
                    ast.BinOp,
                    ast.Compare,
                    ast.Name,
                    ast.Load,
                    ast.Constant,
                    ast.Subscript,
                    ast.Attribute,
                    ast.Dict,
                    ast.List,
                    ast.Tuple,
                    ast.And,
                    ast.Or,
                    ast.Not,
                    ast.Eq,
                    ast.NotEq,
                    ast.Lt,
                    ast.LtE,
                    ast.Gt,
                    ast.GtE,
                    ast.In,
                    ast.NotIn,
                    ast.Add,
                    ast.Sub,
                    ast.Mult,
                    ast.Div,
                    ast.Mod,
                ),
            ):
                raise WorkflowExecutionError("Condition expression contains unsupported syntax")
        namespace = _DotDict(
            {
                "input": _wrap(context.get("input", {})),
                "outputs": _wrap(context.get("outputs", {})),
                "last_output": context.get("last_output"),
            }
        )
        return bool(eval(compile(tree, "<condition>", "eval"), {"__builtins__": {}}, namespace))

    def _should_pause(self, node: dict[str, Any]) -> bool:
        data = node.get("data") or {}
        return bool(data.get("pause") or data.get("pause_on_condition"))


class _DotDict(dict):
    def __getattr__(self, item: str) -> Any:
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


def _wrap(value: Any) -> Any:
    if isinstance(value, dict):
        return _DotDict({key: _wrap(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_wrap(item) for item in value]
    return value


def _persist_message(
    db: Session,
    run_id: int,
    sender_agent_id: int | None,
    receiver_agent_id: int | None,
    channel: str,
    content: str,
) -> Message:
    message = Message(
        workflow_run_id=run_id,
        sender_agent_id=sender_agent_id,
        receiver_agent_id=receiver_agent_id,
        channel=channel,
        content=content,
        message_metadata=_estimate_usage(content),
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def _estimate_usage(text: str) -> dict[str, Any]:
    tokens = max(1, len(str(text).split()) * 2)
    return {"tokens": tokens, "cost": round(tokens * 0.00000015, 8), "estimated": True}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
