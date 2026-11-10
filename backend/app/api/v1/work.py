"""Projects & Tasks - mọi truy vấn đều đi qua phạm vi dữ liệu trong core/permissions.py."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import permissions as perm
from app.core.deps import audit, get_current_user, require_roles
from app.db.session import get_db
from app.models import Department, Project, ProjectMember, Role, Task, TaskUpdate, User
from app.schemas import ProjectCreate, ProjectOut, TaskCreate, TaskOut, TaskPatch

router = APIRouter(tags=["work"])

_TRACKED = ["title", "description", "assignee_id", "status_normalized", "priority_normalized", "progress", "start_date", "due_date"]


def _ser(v):
    return v.value if hasattr(v, "value") else (str(v) if v is not None and not isinstance(v, (int, float, str)) else v)


# ---------- Projects ----------
@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PM, Role.DEPT_LEADER)),
):
    dept = db.get(Department, body.department_id)
    if not dept or dept.organization_id != user.organization_id:
        raise HTTPException(422, "Unknown department")
    if user.department_id != body.department_id:
        raise HTTPException(403, "Cannot create projects outside your department")
    owner_id = body.owner_id or (user.id if user.role == Role.PM else None)
    if user.role == Role.PM and owner_id != user.id:
        raise HTTPException(403, "PM can only own their own projects")
    project = Project(
        organization_id=user.organization_id,
        department_id=body.department_id,
        name=body.name,
        owner_id=owner_id,
        status=body.status,
        start_date=body.start_date,
        due_date=body.due_date,
    )
    db.add(project)
    db.flush()
    for uid in set(body.member_ids):
        member = db.get(User, uid)
        if member and member.organization_id == user.organization_id:
            db.add(ProjectMember(project_id=project.id, user_id=uid))
    audit(db, user, "project.create", "project", project.id)
    db.commit()
    return project


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(perm.visible_projects_stmt(user)).all()


# ---------- Tasks ----------
@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(
    body: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.PM, Role.DEPT_LEADER)),
):
    project = db.get(Project, body.project_id)
    if not project or not perm.can_manage_project(user, project):
        raise HTTPException(403, "No permission on this project")
    if body.assignee_id:
        a = db.get(User, body.assignee_id)
        if not a or a.organization_id != user.organization_id:
            raise HTTPException(422, "Unknown assignee")
    task = Task(
        organization_id=user.organization_id,
        department_id=project.department_id,
        source_system="manual",
        status_original=body.status_normalized.value,
        priority_original=body.priority_normalized.value,
        last_synced_at=datetime.now(timezone.utc),
        **body.model_dump(),
    )
    db.add(task)
    db.flush()
    audit(db, user, "task.create", "task", task.id)
    db.commit()
    return task


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    project_id: uuid.UUID | None = None,
    status_: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = perm.visible_tasks_stmt(user)
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if status_:
        stmt = stmt.where(Task.status_normalized == status_)
    return db.scalars(stmt.order_by(Task.due_date.is_(None), Task.due_date)).all()


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = db.scalar(perm.visible_tasks_stmt(user).where(Task.id == task_id))
    if not task:
        raise HTTPException(404, "Task not found")  # 404 thay vì 403 để không lộ sự tồn tại
    return task


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def patch_task(
    task_id: uuid.UUID,
    body: TaskPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = db.scalar(perm.visible_tasks_stmt(user).where(Task.id == task_id))
    if not task:
        raise HTTPException(404, "Task not found")
    project = db.get(Project, task.project_id)

    changes = body.model_dump(exclude_unset=True)
    comment = changes.pop("comment", None)

    if perm.can_edit_task_fully(user, task, project):
        allowed = set(_TRACKED)
    elif perm.can_update_task_progress(user, task):
        allowed = {"status_normalized", "progress"}
    else:
        raise HTTPException(403, "No permission to edit this task")

    forbidden = set(changes) - allowed
    if forbidden:
        raise HTTPException(403, f"Not allowed to change: {', '.join(sorted(forbidden))}")

    if "assignee_id" in changes and changes["assignee_id"]:
        a = db.get(User, changes["assignee_id"])
        if not a or a.organization_id != user.organization_id:
            raise HTTPException(422, "Unknown assignee")

    old, new = {}, {}
    for k, v in changes.items():
        if getattr(task, k) != v:
            old[k], new[k] = _ser(getattr(task, k)), _ser(v)
            setattr(task, k, v)
    if "status_normalized" in changes:
        task.status_original = task.status_normalized.value  # nguồn = nhập tay trong hệ thống
    if new or comment:
        db.add(TaskUpdate(task_id=task.id, updated_by=user.id, old_values=old, new_values=new, comment=comment))
        audit(db, user, "task.update", "task", task.id, {"fields": list(new)})
    db.commit()
    return task
