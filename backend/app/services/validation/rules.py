"""Kiểm tra hợp lệ dựa trên TRẠNG THÁI hiện tại của bản ghi chuẩn hóa.

Vì chỉ nhìn vào trạng thái hiện tại (giá trị + cờ), sau khi người duyệt sửa một trường thì chạy lại hàm này là
cảnh báo cũ tự biến mất, không cần xử lý riêng.

severity 'error' chặn việc duyệt; 'warning' người duyệt được phép chấp nhận (ví dụ task chưa có người phụ trách).
"""
from app.domain.enums import Priority, TaskStatus


def _issue(code: str, severity: str, field: str | None, message: str) -> dict:
    return {"code": code, "severity": severity, "field": field, "message": message}


def validate_fields(
    *,
    title,
    assignee_raw,
    assignee_id,
    check_assignee: bool,
    status: TaskStatus,
    priority: Priority,
    progress,
    due_date,
    raw: dict,
    flags: dict,
    is_duplicate: bool,
) -> list[dict]:
    issues: list[dict] = []

    if not (title or "").strip():
        issues.append(_issue("MISSING_TITLE", "error", "title", "Thiếu tên công việc."))

    if status == TaskStatus.UNKNOWN:
        r = raw.get("status")
        msg = f"Không nhận ra trạng thái '{r}'." if r else "Thiếu trạng thái."
        issues.append(_issue("UNKNOWN_STATUS", "warning", "status", msg + " Cần người chọn trạng thái."))

    if priority == Priority.UNKNOWN and raw.get("priority"):
        issues.append(_issue("UNMAPPED_PRIORITY", "warning", "priority", f"Không nhận ra mức ưu tiên '{raw['priority']}'."))

    if assignee_id is None:
        if not assignee_raw:
            issues.append(_issue("MISSING_ASSIGNEE", "warning", "assignee", "Chưa có người phụ trách."))
        elif check_assignee:
            issues.append(
                _issue("ASSIGNEE_NOT_FOUND", "warning", "assignee", f"'{assignee_raw}' không khớp người dùng nào trong phòng ban.")
            )

    due_flag = flags.get("due_date")
    if due_flag == "ambiguous":
        issues.append(
            _issue("AMBIGUOUS_DATE", "warning", "due_date", f"Không xác định được ngày/tháng của '{raw.get('due_date')}'.")
        )
    elif due_flag == "invalid":
        issues.append(_issue("INVALID_DATE", "warning", "due_date", f"Ngày '{raw.get('due_date')}' không hợp lệ."))
    elif due_date is None and not raw.get("due_date"):
        issues.append(_issue("MISSING_DUE_DATE", "warning", "due_date", "Chưa có hạn chót."))

    prog_flag = flags.get("progress")
    if prog_flag == "ambiguous":
        issues.append(
            _issue("AMBIGUOUS_PROGRESS", "warning", "progress", f"Tiến độ '{raw.get('progress')}' có thể là phần trăm hoặc phân số.")
        )
    elif prog_flag == "invalid":
        issues.append(_issue("INVALID_PROGRESS", "warning", "progress", f"Tiến độ '{raw.get('progress')}' không hợp lệ."))

    if progress is not None:
        if status == TaskStatus.DONE and progress < 100:
            issues.append(_issue("STATUS_PROGRESS_MISMATCH", "warning", "progress", f"Đã hoàn thành nhưng tiến độ {progress:g}%."))
        elif status == TaskStatus.TODO and progress > 0:
            issues.append(_issue("STATUS_PROGRESS_MISMATCH", "warning", "progress", f"Chưa làm nhưng tiến độ {progress:g}%."))

    if is_duplicate:
        issues.append(_issue("DUPLICATE_IN_FILE", "warning", None, "Trùng với một dòng khác trong cùng file."))

    return issues


def has_error(issues: list[dict]) -> bool:
    return any(i["severity"] == "error" for i in issues)
