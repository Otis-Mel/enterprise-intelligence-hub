"""Test tính chỉ số dashboard (hàm thuần). Mỗi định nghĩa trong docstring của kpis.py có một test tương ứng."""
from datetime import date, datetime, timedelta, timezone

from app.domain.enums import TaskStatus as S
from app.services.analytics.kpis import KpiTask, compute_kpis

TODAY = date(2026, 11, 1)
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def t(i, status, due=None, assignee_id=None, raw=None, project="p1", progress=None, updated=None):
    return KpiTask(id=f"t{i}", title=f"Việc {i}", project_id=project, status=status, due_date=due, assignee_id=assignee_id,
                   assignee_name_raw=raw, updated_at=updated or NOW, progress=progress)


def run(tasks, **kw):
    return compute_kpis(tasks, {"p1": "Dự án 1", "p2": "Dự án 2"}, TODAY, now=NOW, **kw)


def test_empty():
    r = run([])
    assert r["total"] == 0 and r["completion_rate"] is None and r["avg_progress_active"] is None
    assert r["overdue_tasks"] == [] and r["by_project"] == []


def test_completion_rate_excludes_cancelled_from_denominator():
    r = run([t(1, S.DONE), t(2, S.DONE), t(3, S.IN_PROGRESS), t(4, S.CANCELLED), t(5, S.CANCELLED)])
    assert r["total"] == 5 and r["active"] == 1
    assert r["completion_rate"] == round(100 * 2 / 3, 1)  # 2 / (5 - 2)
    assert r["by_status"]["CANCELLED"] == 2


def test_all_cancelled_has_no_rate_not_zero_division():
    assert run([t(1, S.CANCELLED)])["completion_rate"] is None


def test_overdue_only_counts_active_and_strictly_before_today():
    r = run([
        t(1, S.IN_PROGRESS, due=TODAY - timedelta(days=3)),   # quá hạn
        t(2, S.TODO, due=TODAY - timedelta(days=1)),          # quá hạn
        t(3, S.DONE, due=TODAY - timedelta(days=30)),         # đã xong: không tính
        t(4, S.CANCELLED, due=TODAY - timedelta(days=30)),    # đã hủy: không tính
        t(5, S.IN_PROGRESS, due=TODAY),                       # hạn là hôm nay: chưa quá hạn
        t(6, S.IN_PROGRESS, due=None),                        # không có hạn: không thể quá hạn
    ])
    assert r["overdue"] == 2
    assert [x["id"] for x in r["overdue_tasks"]] == ["t1", "t2"]  # trễ nhiều nhất lên đầu
    assert r["overdue_tasks"][0]["days_overdue"] == 3 and r["overdue_tasks"][0]["project"] == "Dự án 1"


def test_due_soon_window_is_inclusive_and_active_only():
    r = run([
        t(1, S.TODO, due=TODAY),
        t(2, S.TODO, due=TODAY + timedelta(days=7)),   # biên: tính
        t(3, S.TODO, due=TODAY + timedelta(days=8)),   # ngoài cửa sổ
        t(4, S.DONE, due=TODAY + timedelta(days=2)),   # đã xong
    ])
    assert r["due_soon"] == 2 and [x["id"] for x in r["upcoming_tasks"]] == ["t1", "t2"]
    assert run([t(1, S.TODO, due=TODAY + timedelta(days=8))], due_soon_days=10)["due_soon"] == 1


def test_blocked_and_unknown_status():
    r = run([t(1, S.BLOCKED), t(2, S.BLOCKED), t(3, S.UNKNOWN), t(4, S.TODO)])
    assert r["blocked"] == 2 and r["unknown_status"] == 1


def test_assignee_quality_buckets_are_exclusive():
    r = run([
        t(1, S.TODO),                                   # không có gì -> thiếu
        t(2, S.TODO, raw="Lê An"),                      # có tên trong nguồn, chưa khớp user -> chưa liên kết
        t(3, S.TODO, assignee_id="u1", raw="Lê An"),    # đã liên kết
        t(4, S.TODO, assignee_id="u1"),                 # đã liên kết
    ])
    assert r["missing_assignee"] == 1 and r["unlinked_assignee"] == 1


def test_missing_due_date_counts_all_statuses():
    assert run([t(1, S.DONE), t(2, S.TODO, due=TODAY)])["missing_due_date"] == 1


def test_stale_tasks_active_only_and_naive_datetimes_ok():
    old = NOW - timedelta(days=20)
    r = run([
        t(1, S.IN_PROGRESS, updated=old),
        t(2, S.DONE, updated=old),                       # đã xong không bị coi là stale
        t(3, S.IN_PROGRESS, updated=old.replace(tzinfo=None)),  # SQLite trả datetime không múi giờ
        t(4, S.IN_PROGRESS, updated=NOW - timedelta(days=13)),
    ])
    assert r["stale"] == 2
    assert run([t(1, S.IN_PROGRESS, updated=old)], stale_days=30)["stale"] == 0


def test_avg_progress_ignores_missing_and_closed():
    r = run([t(1, S.IN_PROGRESS, progress=20), t(2, S.IN_PROGRESS, progress=60), t(3, S.IN_PROGRESS, progress=None),
             t(4, S.DONE, progress=100)])
    assert r["avg_progress_active"] == 40.0  # thiếu tiến độ không bị tính là 0


def test_by_project_sorted_by_overdue_then_size():
    r = run([
        t(1, S.DONE, project="p1"), t(2, S.TODO, project="p1"),
        t(3, S.IN_PROGRESS, project="p2", due=TODAY - timedelta(days=1)), t(4, S.BLOCKED, project="p2"),
    ])
    assert [p["name"] for p in r["by_project"]] == ["Dự án 2", "Dự án 1"]
    p2, p1 = r["by_project"]
    assert (p2["overdue"], p2["blocked"], p2["completion_rate"]) == (1, 1, 0.0)
    assert p1["completion_rate"] == 50.0


def test_list_limit():
    tasks = [t(i, S.TODO, due=TODAY - timedelta(days=i + 1)) for i in range(30)]
    r = run(tasks, list_limit=5)
    assert r["overdue"] == 30 and len(r["overdue_tasks"]) == 5 and r["overdue_tasks"][0]["id"] == "t29"
