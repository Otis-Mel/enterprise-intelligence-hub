"""Tính chỉ số dashboard. Hàm THUẦN (không DB) để kiểm thử được độc lập.

Định nghĩa (khớp tài liệu docs/data-model.md):
- Task "đang chạy" (active): trạng thái khác DONE và CANCELLED.
- Quá hạn (overdue): đang chạy và hạn chót < hôm nay.
- Sắp đến hạn (due_soon): đang chạy và hạn chót trong [hôm nay, hôm nay + N ngày].
- Tỷ lệ hoàn thành: DONE / (tổng - CANCELLED). Việc đã hủy không tính vào mẫu số.
- Tiến độ trung bình: trung bình `progress` của task đang chạy CÓ giá trị tiến độ (task thiếu tiến độ không bị tính là 0).
- Thiếu người phụ trách: không có cả assignee_id lẫn tên người phụ trách gốc.
- Chưa liên kết người phụ trách: có tên trong nguồn nhưng chưa khớp user nào.
- Stale: đang chạy và không được cập nhật quá N ngày.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.domain.enums import TaskStatus

CLOSED = (TaskStatus.DONE, TaskStatus.CANCELLED)


@dataclass
class KpiTask:
    id: str
    title: str
    project_id: str | None
    status: TaskStatus
    due_date: date | None
    assignee_id: object | None
    assignee_name_raw: str | None
    updated_at: datetime | None
    progress: float | None


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite trả datetime không múi giờ


def _pct(num: int, den: int) -> float | None:
    return round(100 * num / den, 1) if den else None


def compute_kpis(
    tasks: list[KpiTask],
    project_names: dict[str, str],
    today: date,
    now: datetime | None = None,
    stale_days: int = 14,
    due_soon_days: int = 7,
    list_limit: int = 10,
) -> dict:
    now = _aware(now) or datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=stale_days)
    soon_end = today + timedelta(days=due_soon_days)

    by_status = {s.value: 0 for s in TaskStatus}
    overdue, upcoming = [], []
    k = dict(overdue=0, due_soon=0, blocked=0, unknown_status=0, missing_assignee=0, unlinked_assignee=0, missing_due_date=0, stale=0)
    progress_vals: list[float] = []
    per_project: dict[str | None, dict] = {}

    for t in tasks:
        by_status[t.status.value] += 1
        active = t.status not in CLOSED
        p = per_project.setdefault(t.project_id, dict(total=0, done=0, cancelled=0, overdue=0, blocked=0))
        p["total"] += 1
        p["done"] += t.status == TaskStatus.DONE
        p["cancelled"] += t.status == TaskStatus.CANCELLED

        if t.status == TaskStatus.BLOCKED:
            k["blocked"] += 1
            p["blocked"] += 1
        if t.status == TaskStatus.UNKNOWN:
            k["unknown_status"] += 1
        if t.assignee_id is None and not t.assignee_name_raw:
            k["missing_assignee"] += 1
        elif t.assignee_id is None:
            k["unlinked_assignee"] += 1
        if t.due_date is None:
            k["missing_due_date"] += 1

        if not active:
            continue
        if t.progress is not None:
            progress_vals.append(float(t.progress))
        upd = _aware(t.updated_at)
        if upd is not None and upd < stale_cutoff:
            k["stale"] += 1
        if t.due_date is not None:
            row = dict(
                id=t.id, title=t.title, project=project_names.get(t.project_id) if t.project_id else None,
                due_date=t.due_date, days_overdue=(today - t.due_date).days, assignee=t.assignee_name_raw, status=t.status.value,
            )
            if t.due_date < today:
                k["overdue"] += 1
                p["overdue"] += 1
                overdue.append(row)
            elif t.due_date <= soon_end:
                k["due_soon"] += 1
                upcoming.append(row)

    total = len(tasks)
    cancelled = by_status[TaskStatus.CANCELLED.value]
    done = by_status[TaskStatus.DONE.value]
    projects = [
        dict(
            project_id=pid, name=project_names.get(pid, "Không rõ") if pid else "Không rõ",
            total=v["total"], done=v["done"], overdue=v["overdue"], blocked=v["blocked"],
            completion_rate=_pct(v["done"], v["total"] - v["cancelled"]),
        )
        for pid, v in per_project.items()
    ]
    projects.sort(key=lambda x: (-x["overdue"], -x["total"], x["name"]))
    overdue.sort(key=lambda r: (-r["days_overdue"], r["title"]))
    upcoming.sort(key=lambda r: (r["due_date"], r["title"]))

    return {
        "as_of": today,
        "total": total,
        "active": total - done - cancelled,
        "by_status": by_status,
        "completion_rate": _pct(done, total - cancelled),
        "avg_progress_active": round(sum(progress_vals) / len(progress_vals), 1) if progress_vals else None,
        **k,
        "by_project": projects,
        "overdue_tasks": overdue[:list_limit],
        "upcoming_tasks": upcoming[:list_limit],
    }
