"""Giao diện extractor + kiểm tra 'grounding' (chống LLM bịa).

Mọi mục do extractor (kể cả LLM) trả về phải:
  1. có `evidence` là câu trích NGUYÊN VĂN có thật trong văn bản nguồn,
  2. có tiêu đề nằm trong evidence,
  3. mỗi trường khác (người phụ trách, hạn, trạng thái, tiến độ) nếu có phải xuất hiện trong evidence, nếu không bị bỏ (None).
Không đạt (1)/(2) -> loại hẳn mục đó. Nhờ vậy LLM không thể đưa vào hệ thống một task không có trong văn bản.
"""
from dataclasses import dataclass, field
from typing import Protocol

from app.services.mapping.normalizers import clean_text, fold

FIELDS = ("title", "assignee", "status", "due_date", "progress")
MIN_EVIDENCE_CHARS = 8


class ExtractionError(Exception):
    """Lỗi extractor với thông điệp an toàn (không chứa API key hay nội dung nhạy cảm)."""


class Extractor(Protocol):
    name: str

    def extract(self, text: str) -> list[dict]: ...


@dataclass
class GroundingReport:
    kept: list[dict] = field(default_factory=list)
    rejected_no_evidence: int = 0
    fields_dropped: int = 0  # số giá trị bị bỏ vì không có trong evidence


def _squash(s: str) -> str:
    return " ".join(clean_text(s).split()) if clean_text(s) else ""


def ground_items(items: list, source_text: str) -> GroundingReport:
    report = GroundingReport()
    haystack = _squash(source_text)
    for it in items:
        if not isinstance(it, dict):
            report.rejected_no_evidence += 1
            continue
        evidence = _squash(it.get("evidence") or "")
        title = clean_text(it.get("title"))
        if len(evidence) < MIN_EVIDENCE_CHARS or evidence not in haystack or not title or fold(title) not in fold(evidence):
            report.rejected_no_evidence += 1
            continue
        out = {"title": title, "evidence": evidence}
        ev_folded = fold(evidence)
        for f in FIELDS[1:]:
            val = it.get(f)
            val = clean_text(val) if val is not None else None
            if val is None:
                out[f] = None
            elif fold(val) and fold(val) in ev_folded:
                out[f] = val
            else:
                out[f] = None
                report.fields_dropped += 1
        report.kept.append(out)
    return report
