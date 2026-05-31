from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class Agent(Base, TimestampMixin):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(120), default="gpt-4o-mini", nullable=False)
    tools: Mapped[list | dict] = mapped_column(JSON, default=list, nullable=False)
    channels: Mapped[list] = mapped_column(JSON, default=lambda: ["web"], nullable=False)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    guardrails: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    schedule: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    sent_messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="sender_agent",
        foreign_keys="Message.sender_agent_id",
    )
    received_messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="receiver_agent",
        foreign_keys="Message.receiver_agent_id",
    )

    def has_telegram_enabled(self) -> bool:
        for channel in self.channels or []:
            if channel == "telegram":
                return True
            if isinstance(channel, dict) and channel.get("name") == "telegram":
                return True
        return False


class Workflow(Base, TimestampMixin):
    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    nodes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    edges: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    runs: Mapped[list["WorkflowRun"]] = relationship(
        "WorkflowRun",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    input_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="runs")
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="workflow_run",
        cascade="all, delete-orphan",
    )
    steps: Mapped[list["WorkflowRunStep"]] = relationship(
        "WorkflowRunStep",
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        order_by="WorkflowRunStep.sequence",
    )


class WorkflowRunStep(Base):
    __tablename__ = "workflow_run_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workflow_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False, default="agent")
    agent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    agent_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    workflow_run: Mapped["WorkflowRun"] = relationship(
        "WorkflowRun",
        back_populates="steps",
    )


class AgentMessage(Base, TimestampMixin):
    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sender_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    receiver_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    payload: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSON,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeadLetterMessage(Base, TimestampMixin):
    __tablename__ = "dlq"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    original_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sender_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    receiver_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    payload: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSON,
        nullable=False,
    )
    error_reason: Mapped[str] = mapped_column(Text, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class TelemetryEvent(Base, TimestampMixin):
    __tablename__ = "telemetry_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="llm_router")
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class MemoryNode(Base, TimestampMixin):
    __tablename__ = "memory_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    agent_id: Mapped[int] = mapped_column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    facts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    ttl_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class MemoryEdge(Base, TimestampMixin):
    __tablename__ = "memory_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_node_id: Mapped[int] = mapped_column(Integer, ForeignKey("memory_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    target_node_id: Mapped[int] = mapped_column(Integer, ForeignKey("memory_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    edge_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    metadata_payload: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class QuotaCounter(Base, TimestampMixin):
    __tablename__ = "quota_counters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    entity_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    quota_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    requests_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    concurrent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workflow_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_agent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    receiver_agent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    workflow_run: Mapped["WorkflowRun"] = relationship(
        "WorkflowRun", back_populates="messages"
    )
    sender_agent: Mapped["Agent | None"] = relationship(
        "Agent",
        back_populates="sent_messages",
        foreign_keys=[sender_agent_id],
    )
    receiver_agent: Mapped["Agent | None"] = relationship(
        "Agent",
        back_populates="received_messages",
        foreign_keys=[receiver_agent_id],
    )


Index("ix_messages_run_timestamp", Message.workflow_run_id, Message.timestamp)
Index("ix_workflow_runs_status_started", WorkflowRun.status, WorkflowRun.started_at)
Index("ix_workflow_run_steps_run_step", WorkflowRunStep.workflow_run_id, WorkflowRunStep.step_id)
Index("ix_agent_messages_status_id", AgentMessage.status, AgentMessage.id)
Index("ix_dlq_original_message", DeadLetterMessage.original_message_id)
Index("ix_telemetry_events_type_created", TelemetryEvent.event_type, TelemetryEvent.created_at)
Index("ix_audit_events_run_created", AuditEvent.run_id, AuditEvent.created_at)
Index("ix_audit_events_correlation_created", AuditEvent.correlation_id, AuditEvent.created_at)
Index("ix_memory_nodes_agent_created", MemoryNode.agent_id, MemoryNode.created_at)
Index("ix_memory_edges_source_target", MemoryEdge.source_node_id, MemoryEdge.target_node_id)
Index("ix_quota_counters_entity_type", QuotaCounter.entity_id, QuotaCounter.quota_type)
