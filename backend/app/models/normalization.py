"""Phase 3: bản ghi đã chuẩn hóa nằm trong hàng chờ duyệt, TRƯỚC khi vào bảng tasks (canonical)."""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import Priority, ReviewStatus, TaskStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


class NormalizedRecord(Base):
    __tablename__ = "normalized_records"
    __table_args__ = (UniqueConstraint("uploaded_file_id", "row_ref", name="uq_norm_file_row"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"), index=True)
    uploaded_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploaded_files.id"), index=True)
    raw_record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_records.id"), index=True)
    row_ref: Mapped[str] = mapped_column(String(220))  # vị trí trong file nguồn (+ '#n' cho mục trích từ văn bản)

    extraction_method: Mapped[str] = mapped_column(String(30))  # mapping | pattern | gemini
    evidence: Mapped[str | None] = mapped_column(Text)  # câu trích nguyên văn (với văn bản tự do)

    external_id: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(500))
    assignee_raw: Mapped[str | None] = mapped_column(String(200))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # chỉ khi khớp CHÍNH XÁC tên người dùng
    status_normalized: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.UNKNOWN)
    priority_normalized: Mapped[Priority] = mapped_column(Enum(Priority), default=Priority.UNKNOWN)
    progress: Mapped[float | None] = mapped_column(Numeric(5, 2, asdecimal=False))
    due_date: Mapped[date | None] = mapped_column(Date)

    raw: Mapped[dict] = mapped_column(JSON, default=dict)  # giá trị gốc từng trường
    field_flags: Mapped[dict] = mapped_column(JSON, default=dict)  # {"due_date": "ambiguous"}
    issues: Mapped[list] = mapped_column(JSON, default=list)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("normalized_records.id"))

    review_status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.PENDING, index=True)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
