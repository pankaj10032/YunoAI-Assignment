from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agents.tools import load_tools
from app.config import settings
from app.models.models import Agent as AgentModel, Message
from app.prompts.template import cached_render

try:
    from crewai import Agent, Crew, Process, Task
except Exception:  # pragma: no cover
    Agent = Crew = Process = Task = None  # type: ignore


class AgentRuntime:
    def __init__(self, db: Session):
        self.db = db

    def create_crewai_agent(
        self,
        agent_model: AgentModel,
        prompt: str | None = None,
    ):
        if Agent is None:
            raise RuntimeError("CrewAI is not installed")

        tools = load_tools(agent_model.tools, agent_model.memory_enabled)
        prompt = prompt or agent_model.system_prompt or f"Complete tasks as {agent_model.name}."
        return Agent(
            role=agent_model.role or agent_model.name,
            goal=prompt,
            backstory=(
                f"You are {agent_model.name}, an AI agent in a collaborative orchestration platform. "
                f"Respect these guardrails: {agent_model.guardrails or {}}"
            ),
            tools=tools,
            verbose=True,
            allow_delegation=True,
            llm=self._llm_name(agent_model.model),
            max_iter=settings.max_agent_iterations,
        )

    def create_task(self, agent, goal: str, description: str):
        if Task is None:
            raise RuntimeError("CrewAI is not installed")
        return Task(
            description=f"{description}\n\nGoal: {goal}",
            expected_output="A concise, useful result that can be passed to the next agent.",
            agent=agent,
        )

    def execute_single_agent(self, agent_id: int, task_description: str) -> str:
        agent_model = self.db.get(AgentModel, agent_id)
        if not agent_model:
            raise ValueError("Agent not found")

        memory_summary = self.build_memory_summary(agent_id)
        prompt = self.render_agent_prompt(
            agent_model,
            user_context=task_description,
            memory_summary=memory_summary,
        )
        crew_agent = self.create_crewai_agent(agent_model, prompt=prompt)
        task = self.create_task(crew_agent, "Complete the requested task", task_description)
        crew = Crew(agents=[crew_agent], tasks=[task], process=Process.sequential, verbose=True)
        return str(crew.kickoff())

    def render_agent_prompt(
        self,
        agent_model: AgentModel,
        user_context: str,
        memory_summary: str,
    ) -> str:
        base_prompt = agent_model.system_prompt or f"Complete tasks as {agent_model.name}."
        variables = {
            "user_context": user_context,
            "memory_summary": memory_summary,
            "guardrail_rules": agent_model.guardrails or {},
            "current_time": _current_time_iso(),
            "context_window": self._context_window(agent_model),
        }
        return cached_render(
            template_key=f"agent:{agent_model.id}",
            base_prompt=base_prompt,
            variables=variables,
            version_key=agent_model.updated_at.isoformat() if agent_model.updated_at else None,
        )

    def execute_workflow(
        self,
        workflow_nodes: list[dict[str, Any]],
        workflow_edges: list[dict[str, Any]],
        input_data: dict[str, Any],
    ) -> str:
        if Crew is None:
            raise RuntimeError("CrewAI is not installed")

        node_by_id = {node.get("id"): node for node in workflow_nodes}
        ordered_nodes = self._topological_order(workflow_nodes, workflow_edges)
        agents = []
        tasks = []
        previous_context = str(input_data.get("input", input_data))

        for node in ordered_nodes:
            data = node.get("data", {})
            agent_id = data.get("agent_id") or data.get("agentId")
            if not agent_id:
                continue
            agent_model = self.db.get(AgentModel, int(agent_id))
            if not agent_model:
                continue

            memory_summary = self.build_memory_summary(int(agent_id))
            prompt = self.render_agent_prompt(
                agent_model,
                user_context=previous_context,
                memory_summary=memory_summary,
            )
            crew_agent = self.create_crewai_agent(agent_model, prompt=prompt)
            label = data.get("label") or agent_model.name
            description = data.get("task") or f"{label}: process the current workflow context."
            task = self.create_task(
                crew_agent,
                goal=f"Advance the workflow using this context: {previous_context}",
                description=description,
            )
            agents.append(crew_agent)
            tasks.append(task)

        if not agents or not tasks:
            raise ValueError("Workflow has no executable agent nodes")

        crew = Crew(agents=agents, tasks=tasks, process=Process.sequential, verbose=True)
        return str(crew.kickoff(inputs=input_data))

    def _topological_order(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        incoming = {node.get("id"): 0 for node in nodes}
        outgoing: dict[str, list[str]] = {node.get("id"): [] for node in nodes}
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            if source in outgoing and target in incoming:
                outgoing[source].append(target)
                incoming[target] += 1

        queue = [node_id for node_id, count in incoming.items() if count == 0]
        ordered_ids = []
        while queue:
            node_id = queue.pop(0)
            ordered_ids.append(node_id)
            for target in outgoing.get(node_id, []):
                incoming[target] -= 1
                if incoming[target] == 0:
                    queue.append(target)

        if len(ordered_ids) != len(nodes):
            return nodes
        node_by_id = {node.get("id"): node for node in nodes}
        return [node_by_id[node_id] for node_id in ordered_ids if node_id in node_by_id]

    def _llm_name(self, model: str) -> str:
        if settings.llm_provider == "ollama":
            return f"ollama/{model or settings.ollama_model}"
        return model or settings.openai_model

    def _context_window(self, agent_model: AgentModel) -> int:
        guardrails = agent_model.guardrails or {}
        try:
            return int(guardrails.get("context_window") or 8000)
        except (TypeError, ValueError):
            return 8000

    def build_memory_summary(self, agent_id: int) -> str:
        messages = (
            self.db.query(Message)
            .filter((Message.sender_agent_id == agent_id) | (Message.receiver_agent_id == agent_id))
            .order_by(Message.timestamp.desc())
            .limit(5)
            .all()
        )
        snippets = [message.content.strip() for message in messages if message.content.strip()]
        return " | ".join(snippets[:5])


def _current_time_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
