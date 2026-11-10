import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import Priority, ProjectStatus, Role, TaskStatus


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(min_length=8)
    role: Role = Role.EMPLOYEE
    department_id: uuid.UUID | None = None


class UserOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    department_id: uuid.UUID | None
    is_active: bool


class DepartmentCreate(BaseModel):
    name: str
    parent_department_id: uuid.UUID | None = None
    leader_user_id: uuid.UUID | None = None


class DepartmentOut(ORM):
    id: uuid.UUID
    name: str
    parent_department_id: uuid.UUID | None
    leader_user_id: uuid.UUID | None


class ProjectCreate(BaseModel):
    name: str
    department_id: uuid.UUID
    owner_id: uuid.UUID | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    start_date: date | None = None
    due_date: date | None = None
    member_ids: list[uuid.UUID] = []


class ProjectOut(ORM):
    id: uuid.UUID
    name: str
    department_id: uuid.UUID
    owner_id: uuid.UUID | None
    status: ProjectStatus
    start_date: date | None
    due_date: date | None


class TaskCreate(BaseModel):
    project_id: uuid.UUID
    title: str
    description: str | None = None
    assignee_id: uuid.UUID | None = None  # không tự đoán; để None nếu chưa rõ
    status_normalized: TaskStatus = TaskStatus.TODO
    priority_normalized: Priority = Priority.UNKNOWN
    progress: float | None = Field(default=None, ge=0, le=100)
    start_date: date | None = None
    due_date: date | None = None


class TaskPatch(BaseModel):
    """PM/Leader có thể sửa mọi trường; Employee chỉ status/progress/comment."""

    title: str | None = None
    description: str | None = None
    assignee_id: uuid.UUID | None = None
    status_normalized: TaskStatus | None = None
    priority_normalized: Priority | None = None
    progress: float | None = Field(default=None, ge=0, le=100)
    start_date: date | None = None
    due_date: date | None = None
    comment: str | None = None


class TaskOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    department_id: uuid.UUID
    title: str
    description: str | None
    assignee_id: uuid.UUID | None
    assignee_name_raw: str | None = None
    status_original: str | None
    status_normalized: TaskStatus
    priority_original: str | None
    priority_normalized: Priority
    progress: float | None
    start_date: date | None
    due_date: date | None
    source_system: str | None
    external_id: str | None
    last_synced_at: datetime | None
    updated_at: datetime
