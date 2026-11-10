"""Map tiêu đề cột trong file -> trường chuẩn. Dùng từ điển; cột không nhận ra được báo lại (không đoán)."""
from app.services.mapping.normalizers import fold

CANONICAL_FIELDS = (
    "external_id", "title", "assignee", "status", "priority", "progress", "due_date", "start_date", "description", "notes",
)
IGNORE = "ignore"
ALLOWED_TARGETS = frozenset(CANONICAL_FIELDS) | {IGNORE}

_SYNONYMS: dict[str, list[str]] = {
    "external_id": ["mã cv", "mã", "mã công việc", "mã task", "id", "key", "task id", "issue key", "stt", "no"],
    "title": ["tên công việc", "công việc", "tên task", "nội dung", "task", "summary", "title", "name", "tên"],
    "assignee": ["người phụ trách", "phụ trách", "người thực hiện", "người được giao", "owner", "assignee", "assigned to"],
    "status": ["trạng thái", "tình trạng", "status", "state"],
    "priority": ["mức ưu tiên", "ưu tiên", "độ ưu tiên", "priority", "pri"],
    "progress": ["tiến độ", "tiến độ (%)", "% hoàn thành", "progress", "%", "percent complete", "completion"],
    "due_date": ["hạn chót", "hạn", "hạn hoàn thành", "deadline", "due", "due date", "ngày hết hạn"],
    "start_date": ["ngày bắt đầu", "bắt đầu", "start", "start date"],
    "description": ["mô tả", "description", "chi tiết"],
    "notes": ["ghi chú", "notes", "note", "comment", "comments"],
}
_LOOKUP = {fold(s): field for field, words in _SYNONYMS.items() for s in words}


def map_columns(headers: list[str], overrides: dict[str, str] | None = None) -> tuple[dict[str, str], list[str]]:
    """-> ({header: field}, [header chưa map được]). Mỗi trường chuẩn chỉ nhận 1 cột (cột đầu tiên thắng).

    overrides: người dùng chỉ định tay {header: field | 'ignore'}, luôn được ưu tiên.
    """
    overrides = overrides or {}
    mapping: dict[str, str] = {}
    unmapped: list[str] = []
    taken: set[str] = set()

    for h, target in overrides.items():  # override trước để chiếm chỗ
        if h in headers and target in ALLOWED_TARGETS:
            mapping[h] = target
            if target != IGNORE:
                taken.add(target)

    for h in headers:
        if h in mapping:
            continue
        field = _LOOKUP.get(fold(h))
        if field and field not in taken:
            mapping[h] = field
            taken.add(field)
        elif not h.startswith("col_"):
            unmapped.append(h)
    return mapping, unmapped
