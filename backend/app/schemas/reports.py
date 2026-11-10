import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ReportCreate(BaseModel):
    title: str | None = None
    as_of: date | None = None
    use_llm: bool = False  # True: Gemini diễn đạt nhận xét (cần GEMINI_API_KEY); số liệu vẫn do code tính và được kiểm tra


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    as_of: date
    status: str
    narrative: dict
    narrative_method: str
    narrative_notes: list
    kpis: dict
    created_by: uuid.UUID
    created_at: datetime
    published_by: uuid.UUID | None
    published_at: datetime | None


class ReportListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    as_of: date
    status: str
    narrative_method: str
    created_at: datetime
    published_at: datetime | None
