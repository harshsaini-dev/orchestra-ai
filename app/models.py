from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class WorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    order_id: str = Field(pattern=r"^ORD-\d{4}$")
    message: str = Field(min_length=3, max_length=2000)
    intent: Literal["auto", "status", "cancel", "refund"] = "auto"
    use_gemini: bool = False
    use_rag: bool = False
    request_key: str | None = Field(
        default=None, min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$"
    )


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    approve: bool
    reviewer: str = Field(min_length=2, max_length=80)
    note: str = Field(default="", max_length=500)


class DomainError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: WorkflowRequest
    guided: bool = True


class ReviewJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review: ApprovalRequest
    guided: bool = True


class DocumentUpload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    filename: str = Field(min_length=1, max_length=180)
    content_base64: str = Field(min_length=1, max_length=2800000)


class RagQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=3, max_length=1500)
    scope: Literal["all", "policy"] = "all"
    top_k: int = Field(default=4, ge=1, le=6)
