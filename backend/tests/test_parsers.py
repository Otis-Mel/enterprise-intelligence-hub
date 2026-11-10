"""Test parser so với ground truth do script sinh dữ liệu tạo ra (mục 13 của plan: parse thành công theo định dạng,
đúng số dòng/trang, đúng giá trị gốc). Không cần DB hay FastAPI."""
import json
import re
import unicodedata
from pathlib import Path

import pytest

from app.scripts.generate_sample_data import main as generate
from app.services.parsers import parse_file, sniff_matches_extension
from app.services.parsers.base import ParseError

TABLE_COLS = {  # file -> (cột tiêu đề công việc, cột người phụ trách)
    "marketing_cong_viec.xlsx": ("Tên công việc", "Người phụ trách"),
    "it_backlog.csv": ("summary", "assignee"),
    "ops_tasks_us_dates.xlsx": ("Task", "Owner"),
}


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    root = tmp_path_factory.mktemp("gen")
    generate(str(root), seed=42)
    return root, json.loads((root / "ground_truth.json").read_text(encoding="utf-8"))


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", " ".join(s.split()))


@pytest.mark.parametrize("name", list(TABLE_COLS))
def test_table_files_match_ground_truth(data, name):
    root, truth = data
    tcol, ocol = TABLE_COLS[name]
    doc = parse_file(root / name, Path(name).suffix)
    got = {r.row_ref: r.payload for r in doc.records}
    expected = {r["row_ref"]: r for r in truth["files"][name]["records"]}

    assert len(doc.records) == len(expected), "số dòng parse được phải bằng số dòng thật (kể cả dòng trùng)"
    assert set(got) == set(expected), "row_ref phải khớp vị trí dòng trong file"
    for ref, e in expected.items():
        assert got[ref][tcol] == e["title"], ref
        assert got[ref].get(ocol) == e["owner"], ref  # thiếu owner -> None, không bịa


def test_header_detected_below_banner(data):
    root, _ = data
    doc = parse_file(root / "marketing_cong_viec.xlsx", ".xlsx")
    sheet = doc.meta["sheets"][0]
    assert sheet["header_row"] == 3 and sheet["headers"][0] == "Mã CV"


def test_raw_values_are_preserved_not_normalized(data):
    """Parser giữ nguyên giá trị gốc: trạng thái/ngày mơ hồ chưa bị chuẩn hóa."""
    root, truth = data
    doc = parse_file(root / "ops_tasks_us_dates.xlsx", ".xlsx")
    exp = {r["row_ref"]: r for r in truth["files"]["ops_tasks_us_dates.xlsx"]["records"]}
    first_with_due = next(r for r in doc.records if r.payload["Due"])
    assert "/" in first_with_due.payload["Due"]  # vẫn là text MM/DD/YYYY
    assert first_with_due.payload["State"] in {  # chưa bị đổi sang enum
        "To Do", "Not started", "Backlog", "todo", "In Progress", "WIP", "doing", "Blocked", "On hold",
        "Done", "Completed", "Closed", "Cancelled", "Won't Fix", "pending review", "TBD", "?",
        "Chưa làm", "Mới", "Đang làm", "Đang thực hiện", "Vướng", "Bị chặn", "Hoàn thành", "Xong", "Hủy",
    }
    assert first_with_due.row_ref in exp


def test_excel_real_dates_become_iso(data):
    root, _ = data
    doc = parse_file(root / "marketing_cong_viec.xlsx", ".xlsx")
    dues = [r.payload["Hạn chót"] for r in doc.records if r.payload["Hạn chót"]]
    assert any("T00:00:00" in d for d in dues), "ô ngày thật -> ISO"
    assert any("/" in d for d in dues), "ô text dd/mm/yyyy giữ nguyên"


def test_csv_duplicates_are_kept_as_separate_rows(data):
    """Parser không tự khử trùng; việc phát hiện duplicate thuộc Phase 3."""
    root, truth = data
    dups = [r for r in truth["files"]["it_backlog.csv"]["records"] if r.get("is_duplicate_of")]
    assert len(dups) == 5
    doc = parse_file(root / "it_backlog.csv", ".csv")
    ids = [r.payload["id"] for r in doc.records]
    assert len(ids) - len(set(ids)) == 5


def test_free_text_reports_contain_every_evidence_sentence(data):
    root, truth = data
    checked = 0
    for name, f in truth["files"].items():
        if f["kind"] != "free_text":
            continue
        doc = parse_file(root / name, Path(name).suffix)
        assert doc.records and not doc.needs_ocr, name
        text = _nfc(" ".join(r.payload["text"] for r in doc.records))
        for rec in f["records"]:
            assert _nfc(rec["evidence"]) in text, (name, rec["evidence"])
            checked += 1
    assert checked > 20


def test_scanned_pdf_flagged_for_ocr(tmp_path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    p = tmp_path / "scan.pdf"
    c = canvas.Canvas(str(p), pagesize=A4)
    c.rect(50, 50, 200, 200, fill=1)  # chỉ có hình, không có text
    c.save()
    doc = parse_file(p, ".pdf")
    assert doc.needs_ocr is True and doc.warnings


def test_csv_encodings_and_delimiters(tmp_path):
    p = tmp_path / "a.csv"
    p.write_bytes("﻿Tên;Trạng thái\nViệc 1;Đang làm\n".encode("utf-8"))
    doc = parse_file(p, ".csv")
    assert doc.meta["delimiter"] == ";"
    assert doc.records[0].payload == {"Tên": "Việc 1", "Trạng thái": "Đang làm"}

    q = tmp_path / "b.csv"
    # cp1258: chữ có mũ/trăng/râu (â ê ô ă ơ ư) viết sẵn, dấu thanh (sắc/huyền/hỏi/ngã/nặng) là ký tự tổ hợp rời
    # -> parser phải chuẩn hóa lại về NFC
    nfd = unicodedata.normalize("NFD", "Tên,Trạng thái\nViệc 1,Đang làm\n")
    def _to_cp1258_form(m):  # ghép chữ cái với dấu mũ/trăng/râu, để dấu thanh ở dạng rời
        base, marks = m.group(1), m.group(2)
        shape = next((c for c in marks if c in "̛̂̆"), "")
        rest = marks.replace(shape, "") if shape else marks
        return unicodedata.normalize("NFC", base + shape) + rest

    cp1258_style = re.sub(r"([aAeEoOuU])([̀-ͯ]+)", _to_cp1258_form, nfd)
    q.write_bytes(cp1258_style.encode("cp1258"))
    doc = parse_file(q, ".csv")
    assert doc.records[0].payload == {"Tên": "Việc 1", "Trạng thái": "Đang làm"}
    assert any("cp1258" in w for w in doc.warnings)


def test_missing_header_falls_back_with_warning(tmp_path):
    p = tmp_path / "n.csv"
    p.write_text("1,2,3\n4,5,6\n", encoding="utf-8")
    doc = parse_file(p, ".csv")
    assert doc.warnings and "col_1" in doc.records[0].payload


@pytest.mark.parametrize("ext", [".xlsx", ".docx", ".pdf"])
def test_fake_file_rejected(tmp_path, ext):
    p = tmp_path / f"fake{ext}"
    p.write_text("đây chỉ là text, không phải file thật")
    assert sniff_matches_extension(p, ext) is False
    with pytest.raises(ParseError):
        parse_file(p, ext)


def test_corrupt_xlsx_gives_clean_error(tmp_path):
    p = tmp_path / "bad.xlsx"
    p.write_bytes(b"PK\x03\x04" + b"garbage" * 50)
    with pytest.raises(ParseError):
        parse_file(p, ".xlsx")


def test_unsupported_extension():
    with pytest.raises(ParseError):
        parse_file(Path("x.exe"), ".exe")
