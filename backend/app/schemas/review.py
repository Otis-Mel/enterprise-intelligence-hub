import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import Priority, ProcessingStatus, ReviewStatus, TaskStatus
from app.services.mapping.columns import ALLOWED_TARGETS


class NormalizeRequest(BaseModel):
    column_mapping: dict[str, str] = {}  # {tiêu đề cột trong file: trường chuẩn | 'ignore'}
    date_order: Literal["DMY", "MDY"] | None = None  # ép thứ tự ngày/tháng cho cả file (bỏ trống = tự phát hiện)
    use_llm: bool = False  # True: dùng Gemini cho văn bản tự do và gợi ý map cột (cần GEMINI_API_KEY)
    force: bool = False

    @field_validator("column_mapping")
    @classmethod
    def _targets(cls, v):
        bad = {t for t in v.values() if t not in ALLOWED_TARGETS}
        if bad:
            raise ValueError(f"Trường chuẩn không hợp lệ: {sorted(bad)}")
        return v


class NormalizeSummary(BaseModel):
    job_id: uuid.UUID
    file_status: ProcessingStatus
    total: int
    by_review_status: dict[str, int]
    issue_counts: dict[str, int]
    detected_date_orders: dict
    unmapped_headers: dict[str, list[str]]
    suggested_mapping: dict[str, str]
    warnings: list[str]
    note: str | None = None


class IssueOut(BaseModel):
    code: str
    severity: str
    field: str | None
    message: str


class NormalizedRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    row_ref: str
    extraction_method: str
    evidence: str | None
    external_id: str | None
    title: str | None
    assignee_raw: str | None
    assignee_id: uuid.UUID | None
    status_normalized: TaskStatus
    priority_normalized: Priority
    progress: float | None
    due_date: date | None
    raw: dict
    issues: list[IssueOut]
    duplicate_of_id: uuid.UUID | None
    review_status: ReviewStatus
    edited: bool
    reviewed_at: datetime | None


class NormalizedRecordPatch(BaseModel):
    """Người duyệt sửa giá trị và/hoặc quyết định. Trường không gửi = giữ nguyên."""

    title: str | None = Field(default=None, max_length=500)
    assignee_id: uuid.UUID | None = None
    status_normalized: TaskStatus | None = None
    priority_normalized: Priority | None = None
    progress: float | None = Field(default=None, ge=0, le=100)
    due_date: date | None = None
    decision: Literal["APPROVE", "REJECT", "REOPEN"] | None = None


class ApproveCleanResult(BaseModel):
    approved: int


class CommitRequest(BaseModel):
    project_id: uuid.UUID


class CommitResult(BaseModel):
    created: int
    updated: int
    unchanged: int
    file_status: ProcessingStatus
