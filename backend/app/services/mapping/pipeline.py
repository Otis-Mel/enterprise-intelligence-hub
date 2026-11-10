"""Pipeline chuẩn hóa THUẦN (không DB): raw records -> NormalizedItem (+ issues, + trùng lặp).

Lớp DB (services/ingestion/normalize.py) và script đánh giá đều dùng cùng hàm này, nên số liệu đánh giá phản ánh
đúng logic chạy thật.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.domain.enums import Priority, TaskStatus
from app.services.extraction.base import Extractor, ground_items
from app.services.mapping.columns import map_columns
from app.services.mapping.normalizers import (
    clean_text,
    detect_date_order,
    fold,
    normalize_priority,
    normalize_status,
    parse_date,
    parse_progress,
)
from app.services.validation.rules import validate_fields


@dataclass
class NormalizedItem:
    row_ref: str
    extraction_method: str  # "mapping" | tên extractor ("gemini", "pattern")
    title: str | None = None
    external_id: str | None = None
    assignee_raw: str | None = None
    status: TaskStatus = TaskStatus.UNKNOWN
    priority: Priority = Priority.UNKNOWN
    progress: float | None = None
    due_date: date | None = None
    evidence: str | None = None
    raw: dict = field(default_factory=dict)  # giá trị gốc từng trường (để hiển thị và đối chiếu)
    flags: dict = field(default_factory=dict)  # {"due_date": "ambiguous"...}
    duplicate_of: str | None = None  # row_ref của dòng gốc
    issues: list = field(default_factory=list)


@dataclass
class NormalizeResult:
    items: list[NormalizedItem] = field(default_factory=list)
    column_mappings: dict[str, dict[str, str]] = field(default_factory=dict)  # {sheet: {header: field}}
    unmapped_headers: dict[str, list[str]] = field(default_factory=dict)
    date_orders: dict[str, str | None] = field(default_factory=dict)  # {nhóm: DMY|MDY|CONFLICT|None}
    warnings: list[str] = field(default_factory=list)


def _sheet_of(row_ref: str) -> str:
    return row_ref.rsplit("!", 1)[0] if "!" in row_ref else ""


def _populate(item: NormalizedItem, *, assignee, status, priority, progress, due, date_order) -> None:
    item.raw = {k: (None if v is None else str(v)) for k, v in
                {"assignee": assignee, "status": status, "priority": priority, "progress": progress, "due_date": due}.items()}
    item.assignee_raw = clean_text(assignee)
    item.status = normalize_status(status)
    item.priority = normalize_priority(priority)
    item.progress, p_flag = parse_progress(progress)
    item.due_date, d_flag = parse_date(due, date_order)
    if p_flag:
        item.flags["progress"] = p_flag
    if d_flag:
        item.flags["due_date"] = d_flag


def _validate(item: NormalizedItem, check_assignee: bool = False) -> None:
    item.issues = validate_fields(
        title=item.title, assignee_raw=item.assignee_raw, assignee_id=None, check_assignee=check_assignee,
        status=item.status, priority=item.priority, progress=item.progress, due_date=item.due_date,
        raw=item.raw, flags=item.flags, is_duplicate=item.duplicate_of is not None,
    )


def _mark_duplicates(items: list[NormalizedItem]) -> None:
    """Dòng sau trùng dòng trước: cùng mã (nếu có) hoặc cùng (tên, người, hạn). Dòng đầu tiên luôn được giữ."""
    seen: dict[tuple, str] = {}
    for it in items:
        if it.external_id:
            key: tuple = ("id", fold(it.external_id))
        elif it.title:
            key = ("fp", fold(it.title), fold(it.assignee_raw or ""), it.due_date)
        else:
            continue
        if key in seen:
            it.duplicate_of = seen[key]
        else:
            seen[key] = it.row_ref


def normalize_items(
    records: list[Any],
    *,
    extractor: Extractor | None = None,
    column_overrides: dict[str, str] | None = None,
    date_order: str | None = None,
) -> NormalizeResult:
    """records: đối tượng có .row_ref, .kind ('row'|'text'), .payload (ParsedRecord hoặc RawRecord). Thứ tự = thứ tự trong file."""
    result = NormalizeResult()
    forced = date_order if date_order in ("DMY", "MDY") else None

    # ---------- bảng
    groups: dict[str, list[Any]] = {}
    for r in records:
        if r.kind == "row":
            groups.setdefault(_sheet_of(r.row_ref), []).append(r)

    for sheet, rows in groups.items():
        headers: list[str] = []
        for r in rows:
            headers.extend(h for h in r.payload if h not in headers)
        mapping, unmapped = map_columns(headers, column_overrides)
        result.column_mappings[sheet] = mapping
        if unmapped:
            result.unmapped_headers[sheet] = unmapped
        by_field = {f: h for h, f in reversed(list(mapping.items())) if f != "ignore"}  # cột đầu tiên thắng
        if "title" not in by_field:
            result.warnings.append(f"[{sheet or 'file'}] Không xác định được cột tên công việc; hãy chỉ định column_mapping.")

        def cell(rec, f, _bf=by_field):
            return rec.payload.get(_bf[f]) if f in _bf else None

        order = forced or detect_date_order(cell(r, "due_date") for r in rows)
        result.date_orders[sheet or "file"] = order
        eff = None if order == "CONFLICT" else order
        if order == "CONFLICT":
            result.warnings.append(f"[{sheet or 'file'}] Cột hạn chót vừa có dạng ngày/tháng vừa có tháng/ngày; xử lý từng giá trị.")

        for r in rows:
            it = NormalizedItem(row_ref=r.row_ref, extraction_method="mapping")
            it.title = clean_text(cell(r, "title"))
            it.external_id = clean_text(cell(r, "external_id"))
            _populate(it, assignee=cell(r, "assignee"), status=cell(r, "status"), priority=cell(r, "priority"),
                      progress=cell(r, "progress"), due=cell(r, "due_date"), date_order=eff)
            result.items.append(it)

    # ---------- văn bản tự do
    text_records = [r for r in records if r.kind == "text"]
    if text_records:
        if extractor is None:
            result.warnings.append("Có văn bản tự do nhưng chưa có extractor; bỏ qua phần này.")
        else:
            staged: list[tuple[NormalizedItem, dict]] = []
            for r in text_records:
                text = r.payload.get("text", "")
                rep = ground_items(extractor.extract(text), text)
                if rep.rejected_no_evidence:
                    result.warnings.append(f"[{r.row_ref}] {rep.rejected_no_evidence} mục bị loại vì không có bằng chứng trong văn bản.")
                if rep.fields_dropped:
                    result.warnings.append(f"[{r.row_ref}] {rep.fields_dropped} giá trị bị bỏ vì không nằm trong câu bằng chứng.")
                for i, x in enumerate(rep.kept, start=1):
                    it = NormalizedItem(row_ref=f"{r.row_ref}#{i}", extraction_method=extractor.name, title=x["title"], evidence=x["evidence"])
                    staged.append((it, x))
            order = forced or detect_date_order(x["due_date"] for _, x in staged)
            result.date_orders["text"] = order
            eff = None if order == "CONFLICT" else order
            for it, x in staged:
                _populate(it, assignee=x["assignee"], status=x["status"], priority=None, progress=x["progress"],
                          due=x["due_date"], date_order=eff)
                result.items.append(it)

    _mark_duplicates(result.items)
    for it in result.items:
        _validate(it)
    return result
