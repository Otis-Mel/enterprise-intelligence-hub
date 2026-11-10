import uuid
from datetime import date

from pydantic import BaseModel


class TaskBrief(BaseModel):
    id: str
    title: str
    project: str | None
    due_date: date
    days_overdue: int
    assignee: str | None
    status: str


class ProjectProgress(BaseModel):
    project_id: str | None
    name: str
    total: int
    done: int
    overdue: int
    blocked: int
    completion_rate: float | None


class DashboardSummary(BaseModel):
    as_of: date
    total: int
    active: int
    by_status: dict[str, int]
    completion_rate: float | None
    avg_progress_active: float | None
    overdue: int
    due_soon: int
    blocked: int
    unknown_status: int
    missing_assignee: int
    unlinked_assignee: int
    missing_due_date: int
    stale: int
    pending_review: int
    by_project: list[ProjectProgress]
    overdue_tasks: list[TaskBrief]
    upcoming_tasks: list[TaskBrief]


class DirectoryUser(BaseModel):
    id: uuid.UUID
    full_name: str
