"""Báo cáo tiến độ: ảnh chụp số liệu tại thời điểm tạo + đoạn nhận xét. Nháp -> người có quyền duyệt -> chính thức."""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    as_of: Mapped[date] = mapped_column(Date)
    kpis: Mapped[dict] = mapped_column(JSON)  # ảnh chụp: báo cáo không đổi khi dữ liệu task đổi sau đó
    narrative: Mapped[dict] = mapped_column(JSON)
    narrative_method: Mapped[str] = mapped_column(String(20))  # gemini | template
    narrative_notes: Mapped[list] = mapped_column(JSON, default=list)  # lý do bỏ bản Gemini (nếu có)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)  # DRAFT | PUBLISHED
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    published_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
