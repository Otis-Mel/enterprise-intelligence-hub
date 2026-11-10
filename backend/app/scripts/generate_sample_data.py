"""Sinh dữ liệu GIẢ (synthetic) để phát triển và đánh giá EIH.

Tạo file Excel/CSV/DOCX/PDF có lỗi cố ý (header khác nhau, trạng thái lộn xộn, ngày nhiều định dạng,
task trùng, thiếu owner/deadline) và file ground_truth.json (đáp án) để đo độ chính xác ở Phase 3+.

Chạy:  python -m app.scripts.generate_sample_data [--out DIR] [--seed 42]
Toàn bộ dữ liệu là tổng hợp ngẫu nhiên, không chứa thông tin thật.
"""
import argparse
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------- từ vựng
OWNERS = [
    "Nguyễn Văn An", "Trần Thị Bình", "Lê Minh Châu", "Phạm Quốc Dũng", "Hoàng Thu Hà",
    "Vũ Đức Huy", "Đặng Mỹ Linh", "Bùi Thanh Nam", "Ngô Khánh Ly", "Đỗ Gia Phúc",
]

TITLES = {
    "Marketing": [
        "Thiết kế landing page chiến dịch", "Viết bài blog SEO", "Chạy quảng cáo Facebook",
        "Lên kế hoạch nội dung tháng", "Phân tích đối thủ", "Chụp ảnh sản phẩm",
        "Báo cáo hiệu quả chiến dịch", "Tổ chức webinar khách hàng", "Cập nhật bộ nhận diện",
        "Soạn email marketing", "Khảo sát khách hàng", "Làm video giới thiệu",
    ],
    "IT": [
        "Fix login timeout bug", "Migrate database to PostgreSQL 16", "Set up CI pipeline",
        "Review pull requests backlog", "Upgrade API gateway", "Write unit tests for billing",
        "Implement SSO integration", "Optimize slow report query", "Rotate API credentials",
        "Document deployment runbook", "Add audit logging", "Investigate memory leak",
    ],
    "Operations": [
        "Update vendor contracts", "Audit inventory Q4", "Train new warehouse staff",
        "Negotiate shipping rates", "Reconcile monthly invoices", "Renew office lease",
        "Prepare safety inspection", "Map supplier risks", "Standardize packing process",
        "Review returns policy", "Plan holiday staffing", "Fix ERP export",
    ],
}

# giá trị nguồn -> status chuẩn (đáp án). UNKNOWN = cố ý mơ hồ, phải đưa vào review.
STATUS_VARIANTS = {
    "TODO": ["Chưa làm", "Mới", "To Do", "Backlog", "Not started", "todo"],
    "IN_PROGRESS": ["Đang làm", "Đang thực hiện", "In Progress", "WIP", "doing"],
    "BLOCKED": ["Vướng", "Bị chặn", "Blocked", "On hold"],
    "DONE": ["Hoàn thành", "Xong", "Done", "Completed", "Closed"],
    "CANCELLED": ["Hủy", "Cancelled", "Won't Fix"],
    "UNKNOWN": ["pending review", "TBD", "?"],
}
STATUS_WEIGHTS = {"TODO": 18, "IN_PROGRESS": 30, "BLOCKED": 8, "DONE": 30, "CANCELLED": 4, "UNKNOWN": 4}

PRIORITY_VARIANTS = {
    "HIGH": ["Cao", "High", "P1"],
    "MEDIUM": ["Trung bình", "Medium", "P2"],
    "LOW": ["Thấp", "Low", "P3"],
}

STATUS_PHRASE_VN = {
    "TODO": "chưa bắt đầu", "IN_PROGRESS": "đang thực hiện", "BLOCKED": "đang bị vướng",
    "DONE": "đã hoàn thành", "CANCELLED": "đã hủy",
}

DUE_START, DUE_END = date(2026, 9, 15), date(2026, 12, 31)


# ---------------------------------------------------------------- sinh bản ghi
def _progress_for(status: str, rng: random.Random):
    if status == "DONE":
        return 100
    if status == "TODO":
        return rng.choice([0, 0, None])
    if status == "IN_PROGRESS":
        return rng.choice([rng.randrange(5, 96, 5), None]) if rng.random() < 0.1 else rng.randrange(5, 96, 5)
    if status == "BLOCKED":
        return rng.randrange(5, 80, 5)
    return rng.choice([None, rng.randrange(0, 60, 10)])  # CANCELLED / UNKNOWN


def make_records(dept: str, prefix: str, n: int, rng: random.Random, allow_unknown=True) -> list[dict]:
    statuses = list(STATUS_WEIGHTS)
    weights = [STATUS_WEIGHTS[s] if allow_unknown or s != "UNKNOWN" else 0 for s in statuses]
    recs = []
    for i in range(1, n + 1):
        status = rng.choices(statuses, weights)[0]
        prio = rng.choice(list(PRIORITY_VARIANTS))
        due = None if rng.random() < 0.10 else DUE_START + timedelta(days=rng.randrange((DUE_END - DUE_START).days))
        recs.append(
            {
                "external_id": f"{prefix}-{i:03d}",
                "title": f"{rng.choice(TITLES[dept])} #{i}",
                "owner": None if rng.random() < 0.10 else rng.choice(OWNERS),
                "department": dept,
                "status_normalized": status,
                "status_raw": rng.choice(STATUS_VARIANTS[status]),
                "priority_normalized": prio,
                "priority_raw": rng.choice(PRIORITY_VARIANTS[prio]),
                "progress": _progress_for(status, rng),
                "due_date": due.isoformat() if due else None,
            }
        )
    return recs


def _strip_internal(r: dict) -> dict:
    return {k: v for k, v in r.items() if k not in ("status_raw", "priority_raw")}


# ---------------------------------------------------------------- xuất file bảng
def write_marketing_xlsx(path: Path, recs: list[dict], rng: random.Random) -> list[dict]:
    """Excel tiếng Việt, có dòng banner phía trên header; ngày hỗn hợp (ô ngày thật + text dd/mm/yyyy)."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Công việc"
    ws["A1"] = "BÁO CÁO CÔNG VIỆC PHÒNG MARKETING - THÁNG 11/2026"
    ws.append([])
    header = ["Mã CV", "Tên công việc", "Người phụ trách", "Trạng thái", "Mức ưu tiên", "Tiến độ (%)", "Hạn chót"]
    ws.append(header)  # dòng 3
    truth = []
    for r in recs:
        d = date.fromisoformat(r["due_date"]) if r["due_date"] else None
        if d is None:
            due_cell = None
        elif rng.random() < 0.7:
            due_cell = datetime(d.year, d.month, d.day)
        else:
            due_cell = d.strftime("%d/%m/%Y")
        ws.append([r["external_id"], r["title"], r["owner"], r["status_raw"], r["priority_raw"], r["progress"], due_cell])
        truth.append({**_strip_internal(r), "row_ref": f"{ws.title}!R{ws.max_row}"})
    wb.save(path)
    return truth


def write_it_csv(path: Path, recs: list[dict], rng: random.Random) -> list[dict]:
    """CSV tiếng Anh, ngày ISO, có dòng trùng lặp hoàn toàn (cố ý)."""
    import csv

    truth, rows = [], []
    for r in recs:
        rows.append([r["external_id"], r["title"], r["owner"] or "", r["status_raw"], r["priority_raw"],
                     "" if r["progress"] is None else r["progress"], r["due_date"] or ""])
    dup_idx = rng.sample(range(len(rows)), 5)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "summary", "assignee", "status", "priority", "progress", "due_date"])
        line = 1
        for i, row in enumerate(rows):
            w.writerow(row)
            line += 1
            truth.append({**_strip_internal(recs[i]), "row_ref": f"R{line}"})
            if i in dup_idx:
                w.writerow(row)
                line += 1
                truth.append({**_strip_internal(recs[i]), "row_ref": f"R{line}", "is_duplicate_of": recs[i]["external_id"]})
    return truth


def write_ops_xlsx(path: Path, recs: list[dict], rng: random.Random) -> list[dict]:
    """Excel kiểu Mỹ: header ngắn khác tên, ngày text MM/DD/YYYY (mơ hồ!), % dạng chuỗi, cột Notes thừa."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Tasks"
    ws.append(["Task", "Owner", "State", "Pri", "%", "Due", "Notes"])
    truth = []
    for r in recs:
        d = date.fromisoformat(r["due_date"]) if r["due_date"] else None
        pct = r["progress"]
        pct_cell = None if pct is None else (f"{pct}%" if rng.random() < 0.5 else pct)
        ws.append([r["title"], r["owner"], r["status_raw"], r["priority_raw"], pct_cell,
                   d.strftime("%m/%d/%Y") if d else None, rng.choice(["", "", "see email", "waiting vendor", "FYI"])])
        truth.append({**_strip_internal(r), "external_id": None, "row_ref": f"{ws.title}!R{ws.max_row}"})
    wb.save(path)
    return truth


# ---------------------------------------------------------------- báo cáo văn bản tự do
def report_lines(recs: list[dict], rng: random.Random):
    lines, truth = [], []
    for r in recs:
        st = r["status_normalized"]
        if st == "UNKNOWN":
            st = "IN_PROGRESS"
            r["status_normalized"] = st
        parts = [f"{r['title']}"]
        if r["owner"]:
            parts.append(f"do {r['owner']} phụ trách")
        if r["due_date"]:
            parts.append("hạn " + date.fromisoformat(r["due_date"]).strftime("%d/%m/%Y"))
        parts.append(STATUS_PHRASE_VN[st])
        if r["progress"] is not None and st not in ("DONE", "TODO", "CANCELLED"):
            parts.append(f"tiến độ {r['progress']}%")
        sentence = "- " + ", ".join(parts) + "."
        lines.append(sentence)
        truth.append({**_strip_internal(r), "evidence": sentence})
    return lines, truth


def find_vietnamese_font() -> str:
    """Tìm font TrueType có đủ dấu tiếng Việt trên Linux/macOS/Windows. Có thể ép bằng biến môi trường EIH_FONT."""
    import os

    candidates = [
        os.environ.get("EIH_FONT", ""),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
        "/Library/Fonts/Arial Unicode.ttf",  # macOS
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",  # Windows
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    raise SystemExit(
        "Không tìm thấy font TrueType hỗ trợ tiếng Việt. Đặt biến môi trường EIH_FONT trỏ tới một file .ttf "
        "(ví dụ: EIH_FONT='/System/Library/Fonts/Supplemental/Arial.ttf')."
    )


def write_reports(out: Path, rng: random.Random, count=10) -> dict:
    from docx import Document
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font = find_vietnamese_font()
    pdfmetrics.registerFont(TTFont("DejaVu", font))

    result = {}
    (out / "reports").mkdir(exist_ok=True)
    for i in range(1, count + 1):
        dept = rng.choice(list(TITLES))
        recs = make_records(dept, f"W{i:02d}", rng.randint(3, 5), rng)
        lines, truth = report_lines(recs, rng)
        week = f"Tuần {rng.randint(40, 46)}/2026"
        header = f"Báo cáo {week} - Phòng {dept}"
        intro = "Kính gửi anh/chị, dưới đây là tình hình công việc trong tuần:"
        use_pdf = i % 2 == 0
        name = f"reports/bao_cao_{i:02d}_{dept.lower()}." + ("pdf" if use_pdf else "docx")
        if use_pdf:
            c = canvas.Canvas(str(out / name), pagesize=A4)
            y = 800
            c.setFont("DejaVu", 14); c.drawString(50, y, header); y -= 30
            c.setFont("DejaVu", 10); c.drawString(50, y, intro); y -= 24
            for ln in lines:
                c.drawString(50, y, ln); y -= 20
            c.save()
        else:
            doc = Document()
            doc.add_heading(header, level=1)
            doc.add_paragraph(intro)
            for ln in lines:
                doc.add_paragraph(ln)
            doc.save(out / name)
        result[name] = {"kind": "free_text", "department": dept, "records": truth}
    return result


# ---------------------------------------------------------------- main
def main(out_dir: str, seed: int) -> None:
    rng = random.Random(seed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    marketing = make_records("Marketing", "MKT", 60, rng)
    it = make_records("IT", "IT", 80, rng)
    ops = make_records("Operations", "OPS", 50, rng)

    truth = {
        "_note": "Dữ liệu tổng hợp ngẫu nhiên (synthetic). ops_tasks_us_dates.xlsx dùng ngày MM/DD/YYYY (mơ hồ).",
        "seed": seed,
        "files": {
            "marketing_cong_viec.xlsx": {"kind": "table", "department": "Marketing",
                                         "records": write_marketing_xlsx(out / "marketing_cong_viec.xlsx", marketing, rng)},
            "it_backlog.csv": {"kind": "table", "department": "IT",
                               "records": write_it_csv(out / "it_backlog.csv", it, rng)},
            "ops_tasks_us_dates.xlsx": {"kind": "table", "department": "Operations",
                                        "records": write_ops_xlsx(out / "ops_tasks_us_dates.xlsx", ops, rng)},
        },
    }
    truth["files"].update(write_reports(out, rng))
    (out / "ground_truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(f["records"]) for f in truth["files"].values())
    print(f"OK: {len(truth['files'])} files, {total} ground-truth records -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../docs/sample_data/generated")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    main(a.out, a.seed)
