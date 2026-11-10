"""Test logic chuẩn hóa thuần (không DB). Trọng tâm: KHÔNG ĐOÁN - giá trị lạ/mơ hồ phải bị chuyển duyệt, không bị gán bừa."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.domain.enums import Priority, TaskStatus
from app.services.mapping.columns import map_columns
from app.services.mapping.normalizers import (
    detect_date_order,
    fold,
    normalize_priority,
    normalize_status,
    parse_date,
    parse_progress,
)
from app.services.mapping.pipeline import normalize_items


def rows(*dicts):
    return [SimpleNamespace(row_ref=f"R{i + 2}", kind="row", payload=d) for i, d in enumerate(dicts)]


# ---------------------------------------------------------------- status / priority
@pytest.mark.parametrize("raw,expected", [
    ("Đang làm", TaskStatus.IN_PROGRESS), ("  ĐANG  LÀM ", TaskStatus.IN_PROGRESS), ("dang lam", TaskStatus.IN_PROGRESS),
    ("In Progress", TaskStatus.IN_PROGRESS), ("WIP", TaskStatus.IN_PROGRESS),
    ("Hoàn thành", TaskStatus.DONE), ("closed", TaskStatus.DONE), ("Won't Fix", TaskStatus.CANCELLED),
    ("Vướng", TaskStatus.BLOCKED), ("On hold", TaskStatus.BLOCKED), ("Chưa làm", TaskStatus.TODO),
])
def test_known_status_variants(raw, expected):
    assert normalize_status(raw) == expected


@pytest.mark.parametrize("raw", ["pending review", "TBD", "?", "Chờ duyệt", "Đang xử lý", "Hoàn tất", "ok", "", None, "   "])
def test_unseen_or_missing_status_is_unknown_not_guessed(raw):
    assert normalize_status(raw) == TaskStatus.UNKNOWN


def test_priority():
    assert normalize_priority("P1") == Priority.HIGH
    assert normalize_priority("Trung bình") == Priority.MEDIUM
    assert normalize_priority("Khẩn cấp") == Priority.CRITICAL
    assert normalize_priority("meh") == Priority.UNKNOWN and normalize_priority(None) == Priority.UNKNOWN


def test_fold_handles_vietnamese_d_and_marks():
    assert fold("Đang Làm!") == "dang lam" and fold("Tiến độ (%)") == "tien do %"


# ---------------------------------------------------------------- progress
@pytest.mark.parametrize("raw,value,flag", [
    (70, 70.0, None), ("70", 70.0, None), ("70%", 70.0, None), ("70,5", 70.5, None), (0, 0.0, None), ("100%", 100.0, None),
    (None, None, None), ("", None, None),
    (0.7, None, "ambiguous"),  # Excel lưu 70% thành 0.7: không tự nhân 100
    ("0.5%", 0.5, None),  # có dấu % thì rõ ràng
    (150, None, "invalid"), ("-5", None, "invalid"), ("abc", None, "invalid"), (True, None, "invalid"),
])
def test_progress(raw, value, flag):
    assert parse_progress(raw) == (value, flag)


# ---------------------------------------------------------------- dates
def test_iso_and_excel_datetime():
    assert parse_date("2026-10-16") == (date(2026, 10, 16), None)
    assert parse_date("2026-10-16T00:00:00") == (date(2026, 10, 16), None)
    assert parse_date("2026-13-40") == (None, "invalid")


def test_slash_date_unambiguous_by_value():
    assert parse_date("15/10/2026") == (date(2026, 10, 15), None)  # 15 không thể là tháng
    assert parse_date("10/15/2026") == (date(2026, 10, 15), None)  # 15 không thể là tháng
    assert parse_date("05/05/2026") == (date(2026, 5, 5), None)  # a == b


def test_slash_date_ambiguous_value_is_not_guessed():
    assert parse_date("03/04/2026") == (None, "ambiguous")


def test_column_level_order_resolves_ambiguous_values():
    col = ["03/04/2026", "25/12/2026", "07/08/2026"]
    assert detect_date_order(col) == "DMY"
    assert parse_date("03/04/2026", "DMY") == (date(2026, 4, 3), None)
    assert detect_date_order(["03/04/2026", "12/25/2026"]) == "MDY"
    assert parse_date("03/04/2026", "MDY") == (date(2026, 3, 4), None)


def test_conflicting_column_and_no_evidence():
    assert detect_date_order(["25/12/2026", "12/25/2026"]) == "CONFLICT"
    assert detect_date_order(["03/04/2026", "05/06/2026"]) is None


def test_invalid_dates():
    assert parse_date("31/02/2026", "DMY") == (None, "invalid")
    assert parse_date("hôm qua") == (None, "invalid")
    assert parse_date("15/10/26") == (None, "invalid")  # năm 2 chữ số: không đoán thế kỷ
    assert parse_date(None) == (None, None) and parse_date("  ") == (None, None)


# ---------------------------------------------------------------- map cột
def test_map_columns_vietnamese_and_english():
    m, un = map_columns(["Mã CV", "Tên công việc", "Người phụ trách", "Trạng thái", "Mức ưu tiên", "Tiến độ (%)", "Hạn chót", "Ghi chú"])
    assert m["Tên công việc"] == "title" and m["Tiến độ (%)"] == "progress" and m["Ghi chú"] == "notes" and un == []
    m, _ = map_columns(["Task", "Owner", "State", "Pri", "%", "Due", "Notes"])
    assert set(m.values()) == {"title", "assignee", "status", "priority", "progress", "due_date", "notes"}


def test_unknown_header_reported_and_override_wins():
    m, un = map_columns(["Việc cần làm", "Ai làm"])
    assert un == ["Việc cần làm", "Ai làm"] and m == {}
    m, un = map_columns(["Việc cần làm", "Ai làm"], {"Việc cần làm": "title", "Ai làm": "assignee"})
    assert m == {"Việc cần làm": "title", "Ai làm": "assignee"} and un == []


def test_one_column_per_field_first_wins():
    m, un = map_columns(["Tên", "Tên công việc"])
    assert m == {"Tên": "title"} and un == ["Tên công việc"]


# ---------------------------------------------------------------- pipeline
def test_pipeline_unseen_values_routed_not_guessed():
    recs = rows(
        {"Task": "A", "State": "Đang xử lý", "Due": "03/04/2026", "%": 0.7, "Owner": "Lê An", "Pri": "meh"},
        {"Task": "B", "State": "Done", "Due": "05/06/2026", "%": 40, "Owner": None, "Pri": "High"},
    )
    res = normalize_items(recs)
    a, b = res.items
    assert a.status == TaskStatus.UNKNOWN and a.due_date is None and a.progress is None
    assert a.flags == {"due_date": "ambiguous", "progress": "ambiguous"}
    codes_a = {i["code"] for i in a.issues}
    assert {"UNKNOWN_STATUS", "AMBIGUOUS_DATE", "AMBIGUOUS_PROGRESS", "UNMAPPED_PRIORITY"} <= codes_a
    codes_b = {i["code"] for i in b.issues}
    assert {"MISSING_ASSIGNEE", "STATUS_PROGRESS_MISMATCH", "AMBIGUOUS_DATE"} <= codes_b
    assert b.assignee_raw is None  # không bịa người phụ trách


def test_pipeline_missing_title_is_error():
    res = normalize_items(rows({"Task": None, "State": "Done"}))
    assert any(i["code"] == "MISSING_TITLE" and i["severity"] == "error" for i in res.items[0].issues)


def test_pipeline_title_column_missing_warns():
    res = normalize_items(rows({"Việc cần làm": "A", "Trạng thái": "Done"}))
    assert res.unmapped_headers[""] == ["Việc cần làm"] and any("column_mapping" in w for w in res.warnings)
    res2 = normalize_items(rows({"Việc cần làm": "A"}), column_overrides={"Việc cần làm": "title"})
    assert res2.items[0].title == "A"


def test_pipeline_forced_date_order_overrides_detection():
    recs = rows({"Task": "A", "Due": "03/04/2026"}, {"Task": "B", "Due": "25/12/2026"})
    assert normalize_items(recs).items[0].due_date == date(2026, 4, 3)  # cột có 25/12 -> DMY
    assert normalize_items(recs, date_order="MDY").items[0].due_date == date(2026, 3, 4)


def test_pipeline_duplicates_by_id_and_by_fingerprint():
    recs = rows(
        {"ID": "X-1", "Task": "A"}, {"ID": "X-1", "Task": "A"},
        {"Task": "Họp", "Owner": "Lê An", "Due": "2026-11-01"}, {"Task": "họp", "Owner": "LÊ AN", "Due": "2026-11-01"},
        {"Task": "Họp", "Owner": "Lê An", "Due": "2026-11-02"},  # khác hạn -> không trùng
    )
    # ID chỉ có ở 2 dòng đầu: dòng không có ID dùng dấu vân tay
    res = normalize_items(recs)
    assert [i.duplicate_of for i in res.items] == [None, "R2", None, "R4", None]


def test_pipeline_sheets_are_independent():
    recs = [
        SimpleNamespace(row_ref="S1!R2", kind="row", payload={"Task": "A", "Due": "03/04/2026"}),
        SimpleNamespace(row_ref="S1!R3", kind="row", payload={"Task": "B", "Due": "25/12/2026"}),
        SimpleNamespace(row_ref="S2!R2", kind="row", payload={"Task": "C", "Due": "03/04/2026"}),
        SimpleNamespace(row_ref="S2!R3", kind="row", payload={"Task": "D", "Due": "04/05/2026"}),
    ]
    res = normalize_items(recs)
    by = {i.title: i for i in res.items}
    assert by["A"].due_date == date(2026, 4, 3)  # sheet 1 có bằng chứng DMY
    assert by["C"].due_date is None and by["C"].flags["due_date"] == "ambiguous"  # sheet 2 không có bằng chứng


def test_vietnamese_long_dates_are_unambiguous():
    from datetime import date
    from app.services.mapping.normalizers import parse_date
    for raw in ("15 tháng 10 năm 2026", "ngày 15 tháng 10 năm 2026", "Ngày 15 tháng 10, 2026"):
        assert parse_date(raw) == (date(2026, 10, 15), None)
    assert parse_date("5 tháng 10 năm 2026") == (date(2026, 10, 5), None)   # ngày <= 12 vẫn không mơ hồ vì có chữ 'tháng'
    assert parse_date("31 tháng 2 năm 2026") == (None, "invalid")           # ngày không tồn tại: không đoán
    assert parse_date("15 tháng 10") == (None, "invalid")                   # thiếu năm: không bịa năm
