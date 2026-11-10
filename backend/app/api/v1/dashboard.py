"""Dashboard: chỉ số tính trên đúng phạm vi dữ liệu người dùng được xem (permissions.visible_tasks_stmt)."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import permissions as perm
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import NormalizedRecord, Organization, Project, ReviewStatus, UploadedFile, User
from app.schemas.dashboard import DashboardSummary
from app.services.analytics.kpis import KpiTask, compute_kpis

router = APIRouter(tags=["dashboard"])


def _tz(name: str | None):
    try:
        return ZoneInfo(name) if name else timezone.utc
    except Exception:
        return timezone.utc


def compute_summary(db: Session, user: User, as_of: date | None = None, stale_days: int = 14) -> dict:
    """Số liệu KPI trong PHẠM VI QUYỀN của `user` (dùng chung cho dashboard và báo cáo)."""
    tasks = db.scalars(perm.visible_tasks_stmt(user)).all()
    pids = {t.project_id for t in tasks}
    names = {str(i): n for i, n in db.execute(select(Project.id, Project.name).where(Project.id.in_(pids))).all()} if pids else {}

    org = db.get(Organization, user.organization_id)
    now = datetime.now(_tz(org.timezone if org else None))
    kpi_tasks = [
        KpiTask(
            id=str(t.id), title=t.title, project_id=str(t.project_id), status=t.status_normalized, due_date=t.due_date,
            assignee_id=t.assignee_id, assignee_name_raw=t.assignee_name_raw, updated_at=t.updated_at,
            progress=None if t.progress is None else float(t.progress),
        )
        for t in tasks
    ]
    out = compute_kpis(kpi_tasks, names, today=as_of or now.date(), now=now, stale_days=stale_days)

    visible_files = perm.visible_files_stmt(user).with_only_columns(UploadedFile.id)
    out["pending_review"] = db.scalar(
        select(func.count()).select_from(NormalizedRecord).where(
            NormalizedRecord.uploaded_file_id.in_(visible_files),
            NormalizedRecord.review_status.in_([ReviewStatus.PENDING, ReviewStatus.CLEAN]),
        )
    ) or 0
    return out


@router.get("/dashboard/summary", response_model=DashboardSummary)
def summary(
    as_of: date | None = Query(None, description="Giả lập 'hôm nay' (dùng cho demo); bỏ trống = ngày hiện tại theo múi giờ tổ chức"),
    stale_days: int = Query(14, ge=1, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return compute_summary(db, user, as_of, stale_days)
