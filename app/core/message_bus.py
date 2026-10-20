"""O1/O2: local request/reply bus, validation, state and dispatch evidence.

The bus is synchronous inside a bounded worker. It is not a distributed broker.
Persist-before-dispatch does not imply exactly-once delivery or automatic retry.
"""
import logging
import time
from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from pydantic import BaseModel, TypeAdapter, JsonValue

from .events import AgentCancelled, AgentMessage, AgentState, StateMachine
from ..models import DomainError

JSON_OBJECT = TypeAdapter(dict[str, JsonValue])


@dataclass(frozen=True)
class Handler:
    schema: type[BaseModel]
    callback: Callable[[BaseModel], dict]
    retrieving: bool = False


class MessageBus:
    """Per-trace handler registry. Never share state machines across jobs."""
    def __init__(self, trace_id: str, emit: Callable):
        self.trace_id = trace_id
        self.emit = emit
        self.handlers: dict[tuple[str, str], Handler] = {}
        self.states: dict[str, StateMachine] = {}

    def register(self, recipient: str, kind: str, schema: type[BaseModel], callback: Callable,
                 *, retrieving: bool = False) -> None:
        key = recipient, kind
        if key in self.handlers:
            raise ValueError("Handler already registered")
        self.handlers[key] = Handler(schema, callback, retrieving)

    def transition(self, agent: str, target: AgentState) -> None:
        machine = self.states.setdefault(agent, StateMachine())
        previous = machine.transition(target)
        self.emit("agent_state_changed", agent,
                  {"trace_id": self.trace_id, "previous": previous.value, "state": target.value})

    def request(self, recipient: str, kind: str, payload: dict, *, purpose: str) -> dict:
        handler = self.handlers.get((recipient, kind))
        if handler is None:
            raise DomainError("No permitted agent handler for this message.", 403)
        validated = handler.schema.model_validate(payload)
        message = AgentMessage(sender="Orchestrator", recipient=recipient, type=kind,
                               payload=validated.model_dump(mode="json"), trace_id=self.trace_id,
                               step_id=str(uuid4()))
        self.emit("message_sent", "Orchestrator", message.model_dump(mode="json", by_alias=True))
        self.transition(recipient, AgentState.THINKING)
        try:
            if handler.retrieving:
                self.transition(recipient, AgentState.RETRIEVING)
            self.transition(recipient, AgentState.WORKING)
            # The existing queue adds presentation delay here, before timing begins.
            self.emit("agent_started", recipient, {"trace_id": self.trace_id,
                      "step_id": message.step_id, "purpose": purpose, **message.payload})
            started = time.perf_counter()
            output = JSON_OBJECT.validate_python(handler.callback(validated))
            duration = round((time.perf_counter() - started) * 1000, 3)
            reply = AgentMessage(sender=recipient, recipient="Orchestrator", type="result",
                                 payload=output, trace_id=self.trace_id, step_id=message.step_id,
                                 causation_id=message.id)
            self.emit("message_sent", recipient, reply.model_dump(mode="json", by_alias=True))
            self.transition(recipient, AgentState.DONE)
            self.emit("step_completed", recipient, {"trace_id": self.trace_id,
                      "step_id": message.step_id, "duration_ms": duration})
            self.emit("agent_completed", recipient, {**output, "trace_id": self.trace_id,
                      "step_id": message.step_id, "duration_ms": duration})
            logging.getLogger(__name__).info("trace=%s step=%s agent=%s duration_ms=%s",
                                             self.trace_id, message.step_id, recipient, duration)
            return output
        except Exception as error:
            state = self.states[recipient].state
            if state != AgentState.DONE:
                self.transition(recipient, AgentState.CANCELLED if isinstance(error, AgentCancelled) else AgentState.ERROR)
            self.emit("error", recipient, {"trace_id": self.trace_id, "step_id": message.step_id,
                      "cancelled": isinstance(error, AgentCancelled),
                      "error": error.message if isinstance(error, DomainError) else
                      "Execution cancelled at a safe boundary." if isinstance(error, AgentCancelled) else
                      "Agent execution failed; see server logs."})
            raise
