"""O1/O2: validated message envelopes and explicit per-run agent states."""
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class AgentCancelled(Exception):
    """Cooperative cancellation at a safe agent boundary."""


class AgentState(StrEnum):
    IDLE = "idle"
    THINKING = "thinking"
    RETRIEVING = "retrieving"
    WORKING = "working"
    WAITING_APPROVAL = "waiting_approval"
    DONE = "done"
    ERROR = "error"
    RECOVERING = "recovering"
    CANCELLED = "cancelled"


TRANSITIONS = {
    AgentState.IDLE: {AgentState.THINKING, AgentState.WAITING_APPROVAL, AgentState.DONE},
    AgentState.THINKING: {AgentState.RETRIEVING, AgentState.WORKING, AgentState.ERROR, AgentState.CANCELLED},
    AgentState.RETRIEVING: {AgentState.WORKING, AgentState.ERROR, AgentState.CANCELLED},
    AgentState.WORKING: {AgentState.DONE, AgentState.WAITING_APPROVAL, AgentState.ERROR, AgentState.CANCELLED},
    AgentState.WAITING_APPROVAL: {AgentState.THINKING, AgentState.DONE, AgentState.CANCELLED},
    AgentState.ERROR: {AgentState.RECOVERING},
    AgentState.RECOVERING: {AgentState.THINKING, AgentState.ERROR, AgentState.CANCELLED},
    AgentState.DONE: set(),
    AgentState.CANCELLED: set(),
}


class StateMachine:
    """A new instance belongs to exactly one agent in one execution trace."""
    def __init__(self) -> None:
        self.state = AgentState.IDLE

    def transition(self, target: AgentState) -> AgentState:
        previous = self.state
        if target not in TRANSITIONS[previous]:
            raise ValueError(f"Invalid agent transition: {previous} -> {target}")
        self.state = target
        return previous


class AgentMessage(BaseModel):
    """JSON-only bus contract. Unknown envelope fields are rejected."""
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)
    schema_version: Literal[1] = 1
    id: str = Field(default_factory=lambda: str(uuid4()))
    sender: str = Field(alias="from", min_length=1, max_length=80)
    recipient: str = Field(alias="to", min_length=1, max_length=80)
    type: str = Field(min_length=1, max_length=80)
    payload: dict[str, JsonValue]
    trace_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    causation_id: str | None = None
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
