from datetime import datetime, timezone
import time

from app.memory.graph import add_edge, add_node, cleanup_expired_nodes, query_context
from app.models.models import Agent, MemoryEdge, MemoryNode

from .conftest import create_agent


def test_memory_graph_builds_and_returns_context(client, db, monkeypatch):
    agents = [
        create_agent(
            client,
            {
                "name": f"Graph Agent {index}",
                "role": f"Agent {index}",
                "system_prompt": f"Agent {index} system prompt.",
                "model": "gpt-4o-mini",
                "tools": [{"name": "memory"}],
                "channels": ["web"],
                "memory_enabled": True,
                "guardrails": {},
                "schedule": None,
            },
        )
        for index in range(5)
    ]
    workflow = {
        "name": "Graph Workflow",
        "description": "Five step message flow",
        "nodes": [
            {"id": f"agent-{index}", "type": "agent", "position": {"x": index * 160, "y": 0}, "data": {"agent_id": agent["id"], "label": agent["name"]}}
            for index, agent in enumerate(agents)
        ],
        "edges": [
            {"id": f"e{index}", "source": f"agent-{index}", "target": f"agent-{index + 1}"}
            for index in range(4)
        ],
        "is_template": False,
    }
    created = client.post("/workflows", json=workflow)
    assert created.status_code == 201, created.text

    monkeypatch.setattr(
        "app.agents.runtime.AgentRuntime.execute_single_agent",
        lambda self, agent_id, task_description: f"fact from agent {agent_id}",
    )
    response = client.post(
        f"/api/workflows/{created.json()['id']}/run",
        json={"input_data": {"topic": "memory graph"}},
    )
    assert response.status_code == 202

    first_agent_id = agents[0]["id"]
    for _ in range(60):
        db.expire_all()
        if db.query(MemoryNode).filter(MemoryNode.node_type == "message").count() >= 5:
            break
        time.sleep(0.05)

    graph_response = client.get(f"/api/agents/{first_agent_id}/memory/graph", params={"depth": 5})
    assert graph_response.status_code == 200
    graph = graph_response.json()
    assert graph["nodes"]
    assert isinstance(graph["context"], str)

    root = add_node(first_agent_id, "agent_state", "Agent says alpha", facts={"facts": ["alpha fact"]}, db=db)
    child = add_node(first_agent_id, "message", "Agent says beta", facts={"facts": ["beta fact"]}, db=db)
    add_edge(root.id, child.id, "sender->receiver", db=db)
    manual_graph = client.get(f"/api/agents/{first_agent_id}/memory/graph", params={"depth": 5}).json()
    assert manual_graph["edges"]
    context = query_context(first_agent_id, depth=2, db=db)
    assert "alpha fact" in context
    assert "beta fact" in context


def test_memory_graph_ttl_cleanup(db):
    node = MemoryNode(
        agent_id=_create_agent(db).id,
        node_type="message",
        source_id=1,
        content="expired content",
        facts={"facts": ["expired content"]},
        ttl_expires_at=datetime.now(timezone.utc),
    )
    db.add(node)
    db.commit()

    removed = cleanup_expired_nodes(db)

    assert removed == 1
    assert db.query(MemoryNode).count() == 0
    assert db.query(MemoryEdge).count() == 0


def _create_agent(db):
    agent = Agent(
        name="TTL Agent",
        role="TTL",
        system_prompt="TTL.",
        model="gpt-4o-mini",
        tools=[{"name": "memory"}],
        channels=["web"],
        memory_enabled=True,
        guardrails={},
        schedule=None,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent
