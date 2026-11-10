"""Đoạn nhận xét cho báo cáo: số liệu do CODE tính, Gemini (nếu bật) chỉ diễn đạt lại.

Cơ chế an toàn:
- LLM chỉ nhận `facts` (số liệu đã tính sẵn) và phải trả JSON gồm các câu.
- `verify_narrative` tìm MỌI con số trong các câu; số nào không có trong `facts` thì cả đoạn bị loại.
- Bị loại hoặc Gemini lỗi -> dùng `template_narrative` (xác định, không dùng LLM). Báo cáo luôn tạo được.
- Kết quả chỉ là bản NHÁP; người có quyền duyệt mới thành chính thức (xem API reports).
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date

NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
SECTIONS = ("highlights", "risks", "next_actions")
MAX_SENTENCES = 6
MAX_LEN = 300


def _num(x) -> float | None:
    if isinstance(x, bool) or x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    return None


def _walk(obj, out: list[float]) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _walk(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk(v, out)
    else:
        n = _num(obj)
        if n is not None:
            out.append(n)


def _names(obj, out: set[str]) -> None:
    """Tên dự án / công việc / người: có thể chứa chữ số ('Dự án 2'), không được tính là con số do LLM bịa."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("name", "title", "project", "assignee") and isinstance(v, str) and v:
                out.add(v)
            else:
                _names(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _names(v, out)


def build_facts(kpis: dict, top_n: int = 5) -> dict:
    """Rút gọn kết quả compute_kpis thành tập dữ kiện được phép nhắc tới."""
    f = {k: kpis.get(k) for k in (
        "total", "active", "completion_rate", "avg_progress_active", "overdue", "due_soon", "blocked", "unknown_status",
        "missing_assignee", "unlinked_assignee", "missing_due_date", "stale", "pending_review")}
    f["as_of"] = str(kpis.get("as_of"))
    f["by_status"] = dict(kpis.get("by_status") or {})
    f["projects"] = [{k: p.get(k) for k in ("name", "total", "done", "overdue", "blocked", "completion_rate")}
                     for p in (kpis.get("by_project") or [])[:top_n]]
    f["overdue_tasks"] = [{k: t.get(k) for k in ("title", "project", "assignee", "days_overdue")}
                          for t in (kpis.get("overdue_tasks") or [])[:top_n]]
    return f


def _allowed_numbers(facts: dict) -> list[float]:
    nums: list[float] = []
    _walk({k: v for k, v in facts.items() if k != "as_of"}, nums)
    try:  # ngày tính số liệu có thể được nhắc: cho phép ngày/tháng/năm của nó
        d = date.fromisoformat(str(facts.get("as_of")))
        nums += [d.day, d.month, d.year]
    except ValueError:
        pass
    return nums


def find_unsupported_numbers(text: str, facts: dict) -> list[str]:
    names: set[str] = set()
    _names(facts, names)
    cleaned = text
    for n in sorted(names, key=len, reverse=True):  # bỏ tên trước khi dò số
        cleaned = cleaned.replace(n, " ")
    allowed = _allowed_numbers(facts)
    bad = []
    for m in NUM_RE.findall(cleaned):
        v = float(m.replace(",", "."))
        if not any(abs(v - a) <= 0.051 for a in allowed):
            bad.append(m)
    return bad


def verify_narrative(narr: dict, facts: dict) -> tuple[bool, list[str]]:
    """(hợp lệ?, danh sách lý do). Chỉ chấp nhận đúng cấu trúc và các con số có trong facts."""
    problems: list[str] = []
    if not isinstance(narr, dict) or not isinstance(narr.get("headline"), str) or not narr["headline"].strip():
        return False, ["thiếu headline"]
    texts = [narr["headline"]]
    for sec in SECTIONS:
        items = narr.get(sec, [])
        if not isinstance(items, list) or any(not isinstance(s, str) for s in items):
            return False, [f"{sec} không đúng định dạng"]
        if len(items) > MAX_SENTENCES:
            problems.append(f"{sec} quá dài")
        texts += items
    for t in texts:
        if len(t) > MAX_LEN:
            problems.append("có câu quá dài")
        if re.search(r"https?://|<[^>]+>", t):
            problems.append("chứa liên kết hoặc thẻ")
        bad = find_unsupported_numbers(t, facts)
        if bad:
            problems.append(f"số không có trong dữ liệu: {', '.join(bad)}")
    return not problems, problems


def clean_narrative(narr: dict) -> dict:
    return {"headline": narr["headline"].strip(),
            **{sec: [s.strip() for s in narr.get(sec, []) if s.strip()][:MAX_SENTENCES] for sec in SECTIONS}}


def _fmt(v) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}"


def template_narrative(facts: dict) -> dict:
    """Bản xác định, không dùng LLM: luôn đúng số liệu, văn phong đơn giản."""
    f = facts
    highlights, risks, actions = [], [], []
    if f.get("total"):
        rate = f.get("completion_rate")
        highlights.append(f"Có {f['total']} công việc, {f['active']} việc đang thực hiện"
                          + (f", tỷ lệ hoàn thành {_fmt(rate)}%." if rate is not None else "."))
    if f.get("avg_progress_active") is not None:
        highlights.append(f"Tiến độ trung bình của các việc đang làm là {_fmt(f['avg_progress_active'])}%.")
    if f.get("overdue"):
        risks.append(f"{f['overdue']} việc đang quá hạn.")
        actions.append("Rà soát và chốt lại hạn hoặc người phụ trách cho các việc quá hạn.")
    if f.get("blocked"):
        risks.append(f"{f['blocked']} việc đang bị chặn.")
        actions.append("Xác định và gỡ vướng cho các việc bị chặn.")
    if f.get("stale"):
        risks.append(f"{f['stale']} việc đang làm nhưng lâu không được cập nhật.")
    if f.get("due_soon"):
        highlights.append(f"{f['due_soon']} việc đến hạn trong 7 ngày tới.")
    if f.get("unknown_status"):
        risks.append(f"{f['unknown_status']} việc có trạng thái chưa rõ, cần xác nhận.")
    if f.get("missing_assignee"):
        risks.append(f"{f['missing_assignee']} việc chưa có người phụ trách.")
        actions.append("Phân công người phụ trách cho các việc còn trống.")
    if f.get("pending_review"):
        actions.append(f"Duyệt {f['pending_review']} bản ghi nhập đang chờ.")
    worst = next((p for p in f.get("projects", []) if p.get("overdue")), None)
    if worst:
        risks.append(f"Dự án {worst['name']} có {worst['overdue']} việc quá hạn.")
    head = (f"Tình hình công việc tính đến {f['as_of']}: "
            + ("có rủi ro cần xử lý." if f.get("overdue") or f.get("blocked") else "chưa ghi nhận rủi ro lớn."))
    return {"headline": head, "highlights": highlights, "risks": risks, "next_actions": actions}


@dataclass
class NarrativeResult:
    narrative: dict
    method: str  # "gemini" | "template"
    rejected: list[str] = field(default_factory=list)  # lý do bỏ bản Gemini (nếu có)


Writer = Callable[[dict], dict]


def generate_narrative(kpis: dict, writer: Writer | None = None) -> NarrativeResult:
    facts = build_facts(kpis)
    if writer is not None:
        try:
            cand = writer(facts)
        except Exception as e:  # mạng, hạn mức, JSON sai...: không làm hỏng báo cáo
            return NarrativeResult(template_narrative(facts), "template", [f"Gemini lỗi: {type(e).__name__}"])
        ok, why = verify_narrative(cand, facts)
        if ok:
            return NarrativeResult(clean_narrative(cand), "gemini")
        return NarrativeResult(template_narrative(facts), "template", why)
    return NarrativeResult(template_narrative(facts), "template")
