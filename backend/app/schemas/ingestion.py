import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ProcessingStatus


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UploadedFileOut(_ORM):
    id: uuid.UUID
    file_name: str
    file_type: str
    size_bytes: int
    checksum: str
    uploaded_at: datetime
    processing_status: ProcessingStatus
    duplicate: bool = False  # True nếu file giống hệt đã được upload trước đó (trả lại bản cũ)


class ImportRequest(BaseModel):
    file_id: uuid.UUID


class ImportJobOut(_ORM):
    id: uuid.UUID
    uploaded_file_id: uuid.UUID
    status: ProcessingStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    records_read: int
    records_created: int
    records_skipped: int
    warnings: list
    error_summary: str | None


class RawRecordOut(_ORM):
    row_ref: str
    kind: str
    payload: dict


class ImportListItem(BaseModel):
    """Một lần import hiển thị trong danh sách (kèm tên file) để giao diện chọn và mở hàng chờ duyệt."""

    job_id: uuid.UUID
    file_id: uuid.UUID
    file_name: str
    status: ProcessingStatus
    created_at: datetime
    records_read: int
    records_created: int
    error_summary: str | None
