WORKFLOW_TEMPLATES = [
    {
        "name": "Research & Summarize",
        "description": "Researcher gathers context, Writer drafts the summary, Reviewer checks quality.",
        "is_template": True,
        "nodes": [
            {
                "id": "researcher",
                "type": "agent",
                "position": {"x": 0, "y": 80},
                "data": {
                    "label": "Researcher",
                    "role": "Research Agent",
                    "task": "Research the topic and return key findings with sources.",
                    "tools": ["search", "memory"],
                },
            },
            {
                "id": "writer",
                "type": "agent",
                "position": {"x": 320, "y": 80},
                "data": {
                    "label": "Writer",
                    "role": "Writing Agent",
                    "task": "Turn the research into a concise, structured summary.",
                    "tools": ["memory"],
                },
            },
            {
                "id": "reviewer",
                "type": "agent",
                "position": {"x": 640, "y": 80},
                "data": {
                    "label": "Reviewer",
                    "role": "Review Agent",
                    "task": "Review the summary for accuracy, clarity, and missing context.",
                    "tools": ["calculator", "memory"],
                },
            },
        ],
        "edges": [
            {"id": "researcher-writer", "source": "researcher", "target": "writer"},
            {"id": "writer-reviewer", "source": "writer", "target": "reviewer"},
        ],
    },
    {
        "name": "Customer Support Router",
        "description": "Router classifies an issue, specialists prepare answers, Aggregator returns a final response.",
        "is_template": True,
        "nodes": [
            {
                "id": "router",
                "type": "agent",
                "position": {"x": 0, "y": 120},
                "data": {
                    "label": "Router",
                    "role": "Support Router",
                    "task": "Classify the customer issue and route it to the right specialist.",
                    "tools": ["memory"],
                },
            },
            {
                "id": "billing-specialist",
                "type": "agent",
                "position": {"x": 320, "y": 20},
                "data": {
                    "label": "Billing Specialist",
                    "role": "Billing Support Agent",
                    "task": "Handle pricing, invoices, refunds, and subscription issues.",
                    "condition": "billing",
                    "tools": ["calculator", "memory"],
                },
            },
            {
                "id": "technical-specialist",
                "type": "agent",
                "position": {"x": 320, "y": 220},
                "data": {
                    "label": "Technical Specialist",
                    "role": "Technical Support Agent",
                    "task": "Handle setup, bugs, integrations, and troubleshooting.",
                    "condition": "technical",
                    "tools": ["search", "memory"],
                },
            },
            {
                "id": "aggregator",
                "type": "agent",
                "position": {"x": 680, "y": 120},
                "data": {
                    "label": "Aggregator",
                    "role": "Support Response Aggregator",
                    "task": "Combine specialist guidance into a polished customer reply.",
                    "tools": ["memory"],
                },
            },
        ],
        "edges": [
            {"id": "router-billing", "source": "router", "target": "billing-specialist", "data": {"condition": "billing"}},
            {"id": "router-technical", "source": "router", "target": "technical-specialist", "data": {"condition": "technical"}},
            {"id": "billing-aggregator", "source": "billing-specialist", "target": "aggregator"},
            {"id": "technical-aggregator", "source": "technical-specialist", "target": "aggregator"},
        ],
    },
]


def seed_workflow_templates(db):
    from app.models.models import Agent, Workflow

    for template in WORKFLOW_TEMPLATES:
        exists = (
            db.query(Workflow)
            .filter(Workflow.name == template["name"], Workflow.is_template.is_(True))
            .first()
        )
        if not exists:
            for node in template["nodes"]:
                _node_with_seeded_agent(db, node)
            template_payload = {
                **template,
                "nodes": template["nodes"],
            }
            db.add(Workflow(**template_payload))
    db.commit()


def _node_with_seeded_agent(db, node):
    from app.models.models import Agent

    data = dict(node.get("data", {}))
    label = data.get("label", node.get("id", "Agent"))
    agent = db.query(Agent).filter(Agent.name == label).first()
    if not agent:
        try:
            agent = Agent(
                name=label,
                role=data.get("role", label),
                system_prompt=data.get("task", f"Act as {label} in the workflow."),
                model="gpt-4o-mini",
                tools=[{"name": tool} for tool in data.get("tools", ["memory"])],
                channels=["web", "telegram"],
                memory_enabled=True,
                guardrails={"tone": "concise", "cite_sources_when_available": True},
            )
            db.add(agent)
            db.flush()
        except Exception:
            db.rollback()
            agent = db.query(Agent).filter(Agent.name == label).first()
    data["agent_id"] = agent.id
    return {**node, "data": data}
