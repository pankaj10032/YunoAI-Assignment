from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.models import Agent


class ChannelManager:
    def __init__(self):
        self._channels: dict[str, Any] = {}

    def register_channel(self, name: str, channel: Any) -> None:
        self._channels[name] = channel

    def get_channel(self, name: str) -> Any | None:
        return self._channels.get(name)

    def status(self) -> dict[str, Any]:
        return {
            name: channel.status()
            for name, channel in self._channels.items()
            if hasattr(channel, "status")
        }

    def find_agent_for_channel(self, db: Session, channel: str, chat_id: int | str) -> Agent | None:
        agents = db.query(Agent).all()
        for agent in agents:
            if self._agent_chat_id(agent, channel) == str(chat_id):
                return agent
        return None

    def format_agent_list(self, agents: list[Agent]) -> str:
        if not agents:
            return "No Telegram-enabled agents are available yet."
        lines = ["Available agents:"]
        for agent in agents:
            lines.append(f"{agent.id}. {agent.name} - {agent.role or 'Agent'}")
        lines.append("\nUse /connect <agent_id> to link this chat.")
        return "\n".join(lines)

    def _agent_chat_id(self, agent: Agent, channel: str) -> str | None:
        channels = agent.channels or []
        for item in channels:
            if isinstance(item, dict) and item.get("name") == channel and item.get("chat_id"):
                return str(item["chat_id"])
        return None


channel_manager = ChannelManager()
