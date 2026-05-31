from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


ChannelName = Literal["telegram", "internal", "web", "slack", "whatsapp"]
ChannelConfig = ChannelName | dict[str, Any]
RunStatus = Literal["pending", "running", "completed", "failed", "paused"]


def _validate_json_object(value: Any, field_name: str) -> Any:
    if value is None:
        return value
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return value


def _validate_json_list(value: Any, field_name: str) -> Any:
    if value is None:
        return value
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a JSON array")
    return value


class AgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    role: str | None = Field(default=None, max_length=255)
    system_prompt: str | None = None
    model: str = Field(default="gpt-4o-mini", min_length=1, max_length=120)
    tools: list[dict[str, Any]] | dict[str, Any] = Field(default_factory=list)
    channels: list[ChannelConfig] = Field(default_factory=lambda: ["web"])
    memory_enabled: bool = True
    guardrails: dict[str, Any] = Field(default_factory=dict)
    schedule: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name cannot be empty")
        return value

    @field_validator("channels")
    @classmethod
    def require_channels(cls, value: list[ChannelConfig]) -> list[ChannelConfig]:
        if not value:
            raise ValueError("at least one channel is required")
        return _dedupe_channels(value)

    @field_validator("guardrails", "schedule")
    @classmethod
    def validate_object_fields(cls, value: Any, info):
        return _validate_json_object(value, info.field_name)


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, max_length=255)
    system_prompt: str | None = None
    model: str | None = Field(default=None, min_length=1, max_length=120)
    tools: list[dict[str, Any]] | dict[str, Any] | None = None
    channels: list[ChannelConfig] | None = None
    memory_enabled: bool | None = None
    guardrails: dict[str, Any] | None = None
    schedule: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("name cannot be empty")
        return value

    @field_validator("channels")
    @classmethod
    def require_channels(cls, value: list[ChannelConfig] | None):
        if value is not None and not value:
            raise ValueError("at least one channel is required")
        return _dedupe_channels(value) if value else value

    @field_validator("guardrails", "schedule")
    @classmethod
    def validate_object_fields(cls, value: Any, info):
        return _validate_json_object(value, info.field_name)


class AgentResponse(AgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


def _dedupe_channels(channels: list[ChannelConfig]) -> list[ChannelConfig]:
    deduped: list[ChannelConfig] = []
    seen: set[str] = set()
    for channel in channels:
        key = channel.get("name") if isinstance(channel, dict) else channel
        if key not in seen:
            seen.add(key)
            deduped.append(channel)
    return deduped


class WorkflowBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    description: str | None = None
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    is_template: bool = False

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name cannot be empty")
        return value

    @field_validator("nodes", "edges")
    @classmethod
    def validate_flow_arrays(cls, value: Any, info):
        return _validate_json_list(value, info.field_name)


class WorkflowCreate(WorkflowBase):
    pass


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    nodes: list[dict[str, Any]] | None = None
    edges: list[dict[str, Any]] | None = None
    is_template: bool | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("name cannot be empty")
        return value

    @field_validator("nodes", "edges")
    @classmethod
    def validate_flow_arrays(cls, value: Any, info):
        return _validate_json_list(value, info.field_name)


class WorkflowResponse(WorkflowBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class MessageBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workflow_run_id: int
    sender_agent_id: int | None = None
    receiver_agent_id: int | None = None
    channel: Literal["telegram", "internal", "web"]
    content: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("message_metadata", "metadata"),
    )


class MessageCreate(MessageBase):
    pass


class MessageUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1)
    metadata: dict[str, Any] | None = None


class MessageResponse(MessageBase):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    timestamp: datetime


class WorkflowRunBase(BaseModel):
    workflow_id: int
    status: RunStatus = "pending"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_tokens: int = Field(default=0, ge=0)
    total_cost: float = Field(default=0.0, ge=0)
    input_data: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunCreate(WorkflowRunBase):
    pass


class WorkflowRunUpdate(BaseModel):
    status: RunStatus | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_tokens: int | None = Field(default=None, ge=0)
    total_cost: float | None = Field(default=None, ge=0)
    input_data: dict[str, Any] | None = None


class WorkflowRunStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step_id: str
    node_type: str
    agent_id: int | None = None
    status: str
    sequence: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    agent_output: str | None = None
    context_snapshot: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class WorkflowRunResponse(WorkflowRunBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    steps: list[WorkflowRunStepResponse] = Field(default_factory=list)


class WorkflowResumeRequest(BaseModel):
    run_id: int
    resume_from_step: str | None = None


class AgentExecuteRequest(BaseModel):
    task_description: str = Field(..., min_length=1)


class AgentGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)


class WorkflowRunRequest(BaseModel):
    input_data: dict[str, Any] = Field(default_factory=dict)


class RunAcceptedResponse(BaseModel):
    run_id: int
    status: RunStatus
    websocket_url: str


class TelegramConnectRequest(BaseModel):
    agent_id: int
    chat_id: str = Field(..., min_length=1)


class TelegramStatusResponse(BaseModel):
    configured: bool
    connected: bool
    polling: bool = False


class PromptPreviewRequest(BaseModel):
    base_prompt: str = Field(..., min_length=1)
    variables: dict[str, Any] = Field(default_factory=dict)
    context_window: int | None = Field(default=None, ge=1)


class PromptPreviewResponse(BaseModel):
    rendered_prompt: str
