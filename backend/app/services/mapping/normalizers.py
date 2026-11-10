"""Chuẩn hóa từng giá trị đơn lẻ. Nguyên tắc: KHÔNG ĐOÁN.

Giá trị không nhận ra, mơ hồ hoặc không hợp lệ -> trả về None/UNKNOWN kèm cờ (flag) để đưa vào hàng chờ duyệt,
thay vì chọn bừa một giá trị "có vẻ đúng".
"""
import re
import unicodedata
from collections.abc import Iterable
from datetime import date

from app.domain.enums import Priority, TaskStatus


def fold(text) -> str:
    """Bỏ dấu, hạ chữ thường, chỉ giữ chữ-số-% (so khớp tiêu đề cột/trạng thái không phụ thuộc dấu và ký tự lạ)."""
    s = unicodedata.normalize("NFD", str(text))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("Đ", "D").replace("đ", "d").lower()
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", s).split())


def clean_text(v) -> str | None:
    if v is None:
        return None
    s = " ".join(unicodedata.normalize("NFC", str(v)).split())
    return s or None


# ---------------------------------------------------------------- status / priority
_STATUS_SYNONYMS: dict[TaskStatus, list[str]] = {
    TaskStatus.TODO: [
        "todo", "to do", "backlog", "not started", "open", "new", "planned", "pending start",
        "chưa làm", "chưa bắt đầu", "mới", "chưa thực hiện", "kế hoạch",
    ],
    TaskStatus.IN_PROGRESS: [
        "in progress", "doing", "wip", "ongoing", "started",
        "đang làm", "đang thực hiện", "đang triển khai", "đang tiến hành",
    ],
    TaskStatus.BLOCKED: [
        "blocked", "on hold", "stuck", "impediment",
        "vướng", "bị chặn", "đang bị vướng", "tạm dừng", "bị vướng",
    ],
    TaskStatus.DONE: [
        "done", "completed", "complete", "closed", "finished", "resolved",
        "hoàn thành", "xong", "đã hoàn thành", "đã xong",
    ],
    TaskStatus.CANCELLED: [
        "cancelled", "canceled", "won't fix", "wont fix", "dropped", "abandoned",
        "hủy", "đã hủy", "huỷ", "bỏ",
    ],
}
_STATUS_LOOKUP = {fold(s): st for st, words in _STATUS_SYNONYMS.items() for s in words}

_PRIORITY_SYNONYMS: dict[Priority, list[str]] = {
    Priority.CRITICAL: ["critical", "blocker", "urgent", "p0", "khẩn cấp", "khẩn"],
    Priority.HIGH: ["high", "p1", "cao"],
    Priority.MEDIUM: ["medium", "normal", "p2", "trung bình", "vừa", "tb"],
    Priority.LOW: ["low", "p3", "thấp", "minor"],
}
_PRIORITY_LOOKUP = {fold(s): p for p, words in _PRIORITY_SYNONYMS.items() for s in words}


def normalize_status(raw) -> TaskStatus:
    """Thiếu hoặc không nhận ra -> UNKNOWN (sẽ bị đưa vào hàng chờ duyệt), không tự gán TODO."""
    if raw is None or not str(raw).strip():
        return TaskStatus.UNKNOWN
    return _STATUS_LOOKUP.get(fold(raw), TaskStatus.UNKNOWN)


def normalize_priority(raw) -> Priority:
    if raw is None or not str(raw).strip():
        return Priority.UNKNOWN
    return _PRIORITY_LOOKUP.get(fold(raw), Priority.UNKNOWN)


# ---------------------------------------------------------------- progress
_NUM = re.compile(r"^\d+(?:[.,]\d+)?$")


def parse_progress(raw) -> tuple[float | None, str | None]:
    """Trả về (giá trị 0-100, cờ). Cờ: None | 'ambiguous' | 'invalid'.

    - '70%', '70', 70 -> 70.
    - 0.7 (không có %) -> 'ambiguous': Excel lưu ô định dạng phần trăm thành 0.7 nhưng cũng có thể là 0.7%.
    - Ngoài 0..100 hoặc không phải số -> 'invalid'.
    """
    if raw is None:
        return None, None
    if isinstance(raw, bool):
        return None, "invalid"
    if isinstance(raw, (int, float)):
        text, has_pct = str(raw), False
    else:
        text = str(raw).strip()
        if not text:
            return None, None
        has_pct = text.endswith("%")
        text = text.rstrip("%").strip()
    if not _NUM.match(text):
        return None, "invalid"
    value = float(text.replace(",", "."))
    if value > 100:
        return None, "invalid"
    if not has_pct and 0 < value < 1:
        return None, "ambiguous"
    return value, None


# ---------------------------------------------------------------- dates
_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?$")
_SLASH = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$")
_YMD_SLASH = re.compile(r"^(\d{4})[/.](\d{1,2})[/.](\d{1,2})$")
# Ngày viết chữ tiếng Việt, có tên 'tháng' nên KHÔNG mơ hồ: '15 tháng 10 năm 2026', 'ngày 5 tháng 10, 2026'
_VN_LONG = re.compile(r"^(?:ngày\s+)?(\d{1,2})\s+tháng\s+(\d{1,2})(?:\s*(?:năm|,)\s*|\s+)(\d{4})$", re.IGNORECASE)


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        out = date(y, m, d)
    except ValueError:
        return None
    return out if 1990 <= out.year <= 2100 else None


def _classify(raw):
    """-> ('iso', date|None) | ('slash', a, b, y) | ('invalid',) | None (thiếu)."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        return ("invalid",)
    s = raw.strip()
    if not s:
        return None
    if m := _ISO.match(s):
        return ("iso", _mk(int(m[1]), int(m[2]), int(m[3])))
    if m := _YMD_SLASH.match(s):
        return ("iso", _mk(int(m[1]), int(m[2]), int(m[3])))
    if m := _VN_LONG.match(" ".join(s.split())):
        return ("iso", _mk(int(m[3]), int(m[2]), int(m[1])))
    if m := _SLASH.match(s):
        return ("slash", int(m[1]), int(m[2]), int(m[3]))
    return ("invalid",)


def detect_date_order(values: Iterable) -> str | None:
    """Suy ra thứ tự ngày/tháng của CẢ CỘT từ bằng chứng chắc chắn.

    Có giá trị dạng 'a/b/yyyy' với a>12 -> DMY; b>12 -> MDY. Cả hai -> 'CONFLICT'. Không có bằng chứng -> None.
    """
    dmy = mdy = False
    for v in values:
        c = _classify(v)
        if c and c[0] == "slash":
            _, a, b, _y = c
            dmy |= a > 12 >= b
            mdy |= b > 12 >= a
    if dmy and mdy:
        return "CONFLICT"
    return "DMY" if dmy else "MDY" if mdy else None


def parse_date(raw, order: str | None = None) -> tuple[date | None, str | None]:
    """Trả về (date, cờ). Cờ: None | 'ambiguous' | 'invalid'. Thiếu giá trị -> (None, None)."""
    c = _classify(raw)
    if c is None:
        return None, None
    if c[0] == "invalid":
        return None, "invalid"
    if c[0] == "iso":
        return (c[1], None) if c[1] else (None, "invalid")
    _, a, b, y = c
    if a == b:  # 05/05/2026: không mơ hồ
        d = _mk(y, b, a)
        return (d, None) if d else (None, "invalid")
    if order in ("DMY", "MDY"):
        d = _mk(y, b, a) if order == "DMY" else _mk(y, a, b)
        return (d, None) if d else (None, "invalid")
    # Không có thứ tự chung cho cả cột -> quyết theo từng giá trị chỉ khi chắc chắn
    if a > 12 >= b:
        d = _mk(y, b, a)
    elif b > 12 >= a:
        d = _mk(y, a, b)
    elif a > 12 and b > 12:
        return None, "invalid"
    else:
        return None, "ambiguous"
    return (d, None) if d else (None, "invalid")
