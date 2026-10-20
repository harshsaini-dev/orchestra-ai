"""O1: typed request payloads for the Phase 2 agent handlers."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue
from ..models import ApprovalRequest, WorkflowRequest


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DataRequest(Payload):
    order_id: str = Field(pattern=r"^ORD-\d{4}$")


class PolicyRequest(Payload):
    message: str = Field(min_length=3, max_length=2000)
    intent: Literal["status", "cancel", "refund", "unknown"]
    use_rag: bool = False


class DecisionRequest(Payload):
    request: WorkflowRequest
    intent: Literal["status", "cancel", "refund", "unknown"]
    order: dict[str, JsonValue]
    evidence: list[dict[str, JsonValue]]
    rag_retrieval: dict[str, JsonValue] | None = None
    mode: str
    warnings: list[str]


class ReviewRequest(Payload):
    workflow_id: str = Field(pattern=r"^WF-[A-F0-9]{12}$")
    review: ApprovalRequest
