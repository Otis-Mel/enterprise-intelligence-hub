"""Sinh báo cáo văn bản tự do KHÓ hơn bộ chuẩn: câu viết nhiều kiểu, thứ tự các thành phần bị xáo, ngày nhiều định dạng.

Mục đích: bộ chuẩn (generate_sample_data) dùng một mẫu câu cố định nên bộ trích xuất bằng luật (PatternExtractor) đọc được
hết, không chứng minh được giá trị của Gemini. Bộ này cố ý làm luật hỏng để so sánh công bằng.
Đáp án (ground truth) vẫn do code sinh, nên đo được chính xác. Dữ liệu là tổng hợp (synthetic).
"""
import random
from datetime import date
from pathlib import Path

from app.scripts.generate_sample_data import TITLES, _strip_internal, make_records

STATUS_PHRASES = {
    "DONE": ["đã xong", "đã hoàn tất và bàn giao", "xong rồi"],
    "IN_PROGRESS": ["đang triển khai", "đang làm dở"],
    "BLOCKED": ["đang bị kẹt", "bị vướng, chưa tiến được"],
    "TODO": ["chưa khởi động", "chưa làm"],
    "CANCELLED": ["đã hủy bỏ", "không triển khai nữa"],
}
OWNER_PHRASES = ["{o} phụ trách", "giao cho {o}", "{o} đang lo phần này", "người thực hiện là {o}"]
PROGRESS_PHRASES = ["tiến độ {p}%", "đã làm được {p}%"]
OPENERS = ["Hạng mục {t}: ", "Về {t}, ", "{t} - ", "Công việc \"{t}\": "]


def _due_phrase(d: date, rng: random.Random) -> str:
    return rng.choice([
        f"hạn {d:%d/%m/%Y}",
        f"deadline {d:%d-%m-%Y}",
        f"hạn chót {d:%d/%m/%Y}",
        f"cần xong trước ngày {d.day} tháng {d.month} năm {d.year}",
    ])


def hard_sentence(rec: dict, rng: random.Random) -> str:
    st = rec["status_normalized"]
    if st == "UNKNOWN":
        st = rec["status_normalized"] = "IN_PROGRESS"
    clauses = [rng.choice(STATUS_PHRASES[st])]
    if rec["owner"]:
        clauses.append(rng.choice(OWNER_PHRASES).format(o=rec["owner"]))
    if rec["due_date"]:
        clauses.append(_due_phrase(date.fromisoformat(rec["due_date"]), rng))
    if rec["progress"] is not None and st in ("IN_PROGRESS", "BLOCKED"):
        clauses.append(rng.choice(PROGRESS_PHRASES).format(p=rec["progress"]))
    rng.shuffle(clauses)
    return rng.choice(OPENERS).format(t=rec["title"]) + ", ".join(clauses) + "."


def write_hard_reports(out: Path, rng: random.Random, count: int = 6) -> dict:
    from docx import Document

    (out / "hard_reports").mkdir(parents=True, exist_ok=True)
    result = {}
    for i in range(1, count + 1):
        dept = rng.choice(list(TITLES))
        recs = make_records(dept, f"H{i:02d}", rng.randint(4, 6), rng)
        sentences = [hard_sentence(r, rng) for r in recs]
        truth = [{**_strip_internal(r), "evidence": s} for r, s in zip(recs, sentences)]
        name = f"hard_reports/hard_{i:02d}_{dept.lower()}.docx"
        doc = Document()
        doc.add_heading(f"Tổng hợp công việc phòng {dept}", level=1)
        doc.add_paragraph("Gửi anh/chị cập nhật nhanh tình hình các đầu việc:")
        for s in sentences:
            doc.add_paragraph(s)
        doc.save(out / name)
        result[name] = {"kind": "free_text", "department": dept, "records": truth}
    return result
