from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.agents.runtime import AgentRuntime
from app.channels.base import BaseChannel
from app.models.database import SessionLocal
from app.models.models import Agent, Message, Workflow, WorkflowRun
from app.utils.observability import get_request_context, set_request_context

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
except Exception:  # pragma: no cover
    Application = CommandHandler = ContextTypes = MessageHandler = Update = filters = None  # type: ignore


logger = logging.getLogger(__name__)


class TelegramChannel(BaseChannel):
    name = "telegram"

    def __init__(self):
        self.application: Application | None = None
        self.bot_token: str | None = None
        self.connected = False
        self.polling_task: asyncio.Task | None = None

    def initialize(self, bot_token: str) -> None:
        if Application is None:
            raise RuntimeError("python-telegram-bot is not installed")
        self.bot_token = bot_token
        self.application = Application.builder().token(bot_token).build()
        self.application.add_handler(CommandHandler("start", self.handle_start))
        self.application.add_handler(CommandHandler("help", self.handle_help))
        self.application.add_handler(CommandHandler("agents", self.handle_agents))
        self.application.add_handler(CommandHandler("connect", self.handle_connect))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def connect(self) -> None:
        if not self.application:
            raise RuntimeError("Telegram channel is not initialized")
        await self.application.initialize()
        await self.application.start()
        self.connected = True

    async def disconnect(self) -> None:
        if self.polling_task:
            self.polling_task.cancel()
            self.polling_task = None
        if self.application and self.connected:
            await self.application.stop()
            await self.application.shutdown()
        self.connected = False

    async def receive(self, payload: Any) -> Any:
        if not self.application or Update is None:
            raise RuntimeError("Telegram channel is not initialized")
        update = Update.de_json(payload, self.application.bot)
        await self.application.process_update(update)
        return {"ok": True}

    async def send(self, recipient: str | int, message: str) -> None:
        await self.send_message(recipient, message)

    async def send_message(self, chat_id: str | int, text: str) -> None:
        if not self.application:
            raise RuntimeError("Telegram channel is not initialized")
        await self.application.bot.send_message(chat_id=chat_id, text=text[:4096])

    async def set_webhook(self, webhook_url: str) -> Any:
        if not self.application:
            raise RuntimeError("Telegram channel is not initialized")
        if not webhook_url.startswith("https://"):
            raise ValueError("Webhook URL must start with https://")
        return await self.application.bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True,
        )

    async def delete_webhook(self) -> Any:
        if not self.application:
            raise RuntimeError("Telegram channel is not initialized")
        return await self.application.bot.delete_webhook(drop_pending_updates=True)

    async def get_webhook_info(self) -> Any:
        if not self.application:
            raise RuntimeError("Telegram channel is not initialized")
        return await self.application.bot.get_webhook_info()

    async def register_agent(self, agent_id: int, chat_id: str | int) -> Agent:
        db = SessionLocal()
        try:
            chat_id_str = str(chat_id)
            # Ensure a Telegram chat is linked to exactly one agent.
            for other in db.query(Agent).all():
                if other.id == agent_id:
                    continue
                other_channels = other.channels or []
                updated_channels = [
                    item
                    for item in other_channels
                    if not (
                        isinstance(item, dict)
                        and item.get("name") == "telegram"
                        and str(item.get("chat_id")) == chat_id_str
                    )
                ]
                if updated_channels != other_channels:
                    other.channels = updated_channels

            agent = db.get(Agent, agent_id)
            if not agent:
                raise ValueError("Agent not found")
            channels = _upsert_telegram_channel(agent.channels or [], chat_id_str)
            agent.channels = channels
            db.commit()
            db.refresh(agent)
            return agent
        finally:
            db.close()

    async def start_webhook(self, app=None) -> None:
        if not self.application:
            raise RuntimeError("Telegram channel is not initialized")
        if self.connected:
            return
        await self.connect()

    async def start_polling(self) -> None:
        if not self.application:
            raise RuntimeError("Telegram channel is not initialized")
        if not self.connected:
            await self.connect()
        if not self.application.updater:
            raise RuntimeError("Telegram updater is unavailable")
        await self.application.updater.start_polling()
        while True:
            await asyncio.sleep(3600)

    async def handle_start(self, update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id if update.effective_chat else "unknown"
        await update.message.reply_text(
            "AI Orchestrator is online.\n"
            f"Chat ID: {chat_id}\n"
            "Use /agents to see Telegram-enabled agents, then /connect <agent_id>."
        )

    async def handle_help(self, update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id if update.effective_chat else "unknown"
        await update.message.reply_text(
            "Commands:\n"
            "/start - Check bot status\n"
            "/agents - List available agents\n"
            "/connect <agent_id> - Link this chat to an agent\n"
            f"Current chat ID: {chat_id}\n"
            "After connecting, send any message to run that agent."
        )

    async def handle_agents(self, update, context: ContextTypes.DEFAULT_TYPE) -> None:
        db = SessionLocal()
        try:
            agents = [agent for agent in db.query(Agent).order_by(Agent.name).all() if agent.has_telegram_enabled()]
            await update.message.reply_text(_format_agent_list(agents))
        finally:
            db.close()

    async def handle_connect(self, update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Usage: /connect <agent_id>")
            return
        try:
            agent_id = int(context.args[0])
            agent = await self.register_agent(agent_id, update.effective_chat.id)
            await update.message.reply_text(f"Connected this chat to {agent.name}.")
        except Exception as exc:
            await update.message.reply_text(f"Could not connect agent: {exc}")

    async def handle_message(self, update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        text = update.message.text or ""
        correlation_id = get_request_context().get("correlation_id")
        db = SessionLocal()
        try:
            agent = _find_agent_by_chat_id(db, chat_id)
            if not agent:
                await update.message.reply_text("No agent is linked to this chat. Use /agents then /connect <agent_id>.")
                return

            run = _create_direct_telegram_run(db, agent)
            _persist_message(
                db=db,
                run_id=run.id,
                sender_agent_id=None,
                receiver_agent_id=agent.id,
                channel="telegram",
                content=text,
                metadata={"chat_id": str(chat_id), "direction": "inbound"},
            )
            await update.message.reply_text(f"{agent.name} is working on it...")

            set_request_context(correlation_id=correlation_id, agent_id=str(agent.id), run_id=str(run.id), step="telegram_message")
            runtime = AgentRuntime(db)
            result = await asyncio.to_thread(runtime.execute_single_agent, agent.id, text)
            _persist_message(
                db=db,
                run_id=run.id,
                sender_agent_id=agent.id,
                receiver_agent_id=None,
                channel="telegram",
                content=result,
                metadata={"chat_id": str(chat_id), "direction": "outbound"},
            )
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
            await self.send_message(chat_id, result)
        except Exception as exc:
            logger.exception("Telegram message handling failed")
            await update.message.reply_text(f"Agent execution failed: {exc}")
        finally:
            db.close()

    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(self.bot_token),
            "connected": self.connected,
            "polling": bool(self.polling_task and not self.polling_task.done()),
        }


def _upsert_telegram_channel(channels: list[Any], chat_id: str) -> list[Any]:
    normalized = []
    found = False
    for item in channels:
        if item == "telegram":
            normalized.append({"name": "telegram", "chat_id": chat_id})
            found = True
        elif isinstance(item, dict) and item.get("name") == "telegram":
            normalized.append({**item, "chat_id": chat_id})
            found = True
        else:
            normalized.append(item)
    if not found:
        normalized.append({"name": "telegram", "chat_id": chat_id})
    return normalized


def _find_agent_by_chat_id(db: Session, chat_id: str | int) -> Agent | None:
    # Prefer the most recently linked agent if legacy data still contains duplicates.
    for agent in db.query(Agent).order_by(Agent.updated_at.desc(), Agent.id.desc()).all():
        for item in agent.channels or []:
            if isinstance(item, dict) and item.get("name") == "telegram" and str(item.get("chat_id")) == str(chat_id):
                return agent
    return None


def _format_agent_list(agents: list[Agent]) -> str:
    if not agents:
        return "No Telegram-enabled agents are available yet."
    lines = ["Available agents:"]
    for agent in agents:
        chat_id = None
        for item in agent.channels or []:
            if isinstance(item, dict) and item.get("name") == "telegram" and item.get("chat_id"):
                chat_id = str(item.get("chat_id"))
                break
        suffix = f" [chat_id: {chat_id}]" if chat_id else ""
        lines.append(f"{agent.id}. {agent.name} - {agent.role or 'Agent'}{suffix}")
    lines.append("\nUse /connect <agent_id> to link this chat.")
    return "\n".join(lines)


def _create_direct_telegram_run(db: Session, agent: Agent) -> WorkflowRun:
    workflow = Workflow(
        name=f"Telegram chat: {agent.name}",
        description="Ephemeral workflow created for a Telegram message.",
        nodes=[
            {
                "id": f"agent-{agent.id}",
                "type": "agent",
                "data": {"agent_id": agent.id, "label": agent.name},
                "position": {"x": 0, "y": 0},
            }
        ],
        edges=[],
        is_template=False,
    )
    db.add(workflow)
    db.flush()
    run = WorkflowRun(
        workflow_id=workflow.id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _persist_message(
    db: Session,
    run_id: int,
    sender_agent_id: int | None,
    receiver_agent_id: int | None,
    channel: str,
    content: str,
    metadata: dict[str, Any],
) -> Message:
    message = Message(
        workflow_run_id=run_id,
        sender_agent_id=sender_agent_id,
        receiver_agent_id=receiver_agent_id,
        channel=channel,
        content=content,
        message_metadata=metadata,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


telegram_channel = TelegramChannel()
