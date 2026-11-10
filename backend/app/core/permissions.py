"""RBAC + phạm vi dữ liệu (least privilege).

- ADMIN: quản trị người dùng/phòng ban/cấu hình. KHÔNG mặc định xem nội dung nghiệp vụ
  (projects/tasks) - đúng nguyên tắc "tách quyền quản trị kỹ thuật khỏi nội dung nhạy cảm".
- DEPT_LEADER: toàn bộ project/task thuộc phòng ban của mình.
- PM: project do mình phụ trách (owner_id) và task trong các project đó.
- EMPLOYEE: project mình là thành viên; task được giao cho mình.
"""
from sqlalchemy import or_, select
from sqlalchemy.sql import Select

from app.models import Project, ProjectMember, Role, Task, UploadedFile, User


def visible_projects_stmt(user: User) -> Select:
    stmt = select(Project).where(Project.organization_id == user.organization_id)
    if user.role == Role.ADMIN:
        return stmt.where(Project.id.is_(None))  # không xem nội dung nghiệp vụ
    if user.role == Role.DEPT_LEADER:
        return stmt.where(Project.department_id == user.department_id)
    if user.role == Role.PM:
        return stmt.where(Project.owner_id == user.id)
    member_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
    return stmt.where(Project.id.in_(member_ids))


def visible_tasks_stmt(user: User) -> Select:
    stmt = select(Task).where(Task.organization_id == user.organization_id)
    if user.role == Role.ADMIN:
        return stmt.where(Task.id.is_(None))
    if user.role == Role.DEPT_LEADER:
        return stmt.where(Task.department_id == user.department_id)
    if user.role == Role.PM:
        own_projects = select(Project.id).where(Project.owner_id == user.id)
        return stmt.where(Task.project_id.in_(own_projects))
    return stmt.where(Task.assignee_id == user.id)


def visible_files_stmt(user: User) -> Select:
    """File đã upload: nhân viên chỉ thấy file mình tải lên; PM và Dept Leader (người duyệt dữ liệu) thấy file cả phòng ban;
    Admin không thấy nội dung."""
    stmt = select(UploadedFile).where(UploadedFile.organization_id == user.organization_id)
    if user.role == Role.ADMIN:
        return stmt.where(UploadedFile.id.is_(None))
    if user.role in (Role.DEPT_LEADER, Role.PM):
        return stmt.where(UploadedFile.department_id == user.department_id)
    return stmt.where(UploadedFile.uploaded_by == user.id)


def can_manage_project(user: User, project: Project) -> bool:
    if user.organization_id != project.organization_id:
        return False
    if user.role == Role.DEPT_LEADER:
        return project.department_id == user.department_id
    if user.role == Role.PM:
        return project.owner_id == user.id
    return False


def can_edit_task_fully(user: User, task: Task, project: Project) -> bool:
    return can_manage_project(user, project)


def can_update_task_progress(user: User, task: Task) -> bool:
    """Nhân viên chỉ cập nhật status/progress trên task được giao cho mình."""
    return user.role == Role.EMPLOYEE and task.assignee_id == user.id
