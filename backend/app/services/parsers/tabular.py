"""Parser cho CSV và Excel.

Giữ nguyên giá trị gốc (chỉ strip khoảng trắng, chuyển ô ngày thật sang chuỗi ISO).
Không chuẩn hóa trạng thái/ngày/người phụ trách ở đây - việc đó thuộc Phase 3 (có review).
"""
import csv
import io
import unicodedata
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from app.services.parsers.base import MAX_ROWS, ParsedDocument, ParsedRecord, ParseError

HEADER_SCAN_ROWS = 15


def safe_value(v):
    """Giá trị JSON-safe. Ô ngày thật -> ISO ('2026-10-16T00:00:00') nên phân biệt được với ngày dạng text."""
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v
    if isinstance(v, (float, Decimal)):
        f = float(v)
        if f != f:  # NaN
            return None
        return int(f) if f.is_integer() else f
    # NFC: file Windows cũ (cp1258) cho dấu tiếng Việt dạng tổ hợp; chuẩn hóa để so khớp tên/trạng thái không bị lệch
    s = unicodedata.normalize("NFC", str(v)).strip()
    return s or None


def _looks_numeric(s: str) -> bool:
    try:
        float(s.replace(",", ".").rstrip("%").strip())
        return True
    except ValueError:
        return False


def _is_text_cell(v) -> bool:
    return isinstance(v, str) and v.strip() != "" and not _looks_numeric(v)


def find_header_index(rows: list[list]) -> int | None:
    """Dòng header = dòng (trong ~15 dòng đầu) có nhiều ô chữ nhất; hòa thì lấy dòng đầu.
    Bỏ qua được banner/tiêu đề phía trên (chỉ có 1 ô)."""
    best, best_score = None, 1  # cần >= 2 ô chữ
    for i, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        score = sum(1 for v in row if _is_text_cell(v))
        if score > best_score:
            best, best_score = i, score
    return best


def make_headers(row: list) -> list[str]:
    seen: dict[str, int] = {}
    headers = []
    for j, v in enumerate(row):
        name = str(v).strip() if v is not None else ""
        if not name:
            name = f"col_{j + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        headers.append(name)
    return headers


def build_records(numbered_rows: list[tuple[int, list]], prefix: str = "") -> tuple[list[ParsedRecord], dict, list[str]]:
    """numbered_rows: [(số dòng vật lý trong file, [giá trị ô...])]."""
    warnings: list[str] = []
    rows = [(n, r) for n, r in numbered_rows if any(c is not None for c in r)]
    if not rows:
        return [], {"headers": [], "header_row": None}, ["Không có dữ liệu"]

    idx = find_header_index([r for _, r in rows])
    if idx is None:
        width = max(len(r) for _, r in rows)
        headers = [f"col_{j + 1}" for j in range(width)]
        data = rows
        header_row = None
        warnings.append("Không xác định được dòng tiêu đề; dùng tên cột tạm col_1, col_2...")
    else:
        header_row = rows[idx][0]
        headers = make_headers(rows[idx][1])
        data = rows[idx + 1 :]

    if len(data) > MAX_ROWS:
        raise ParseError(f"File có quá nhiều dòng (giới hạn {MAX_ROWS}).")

    records = []
    for n, row in data:
        payload = {}
        for j, val in enumerate(row):
            name = headers[j] if j < len(headers) else f"col_{j + 1}"
            if val is None and name.startswith("col_"):
                continue  # bỏ cột trống không có tiêu đề
            payload[name] = val
        for name in headers[len(row) :]:
            if not name.startswith("col_"):
                payload[name] = None
        records.append(ParsedRecord(row_ref=f"{prefix}R{n}", kind="row", payload=payload))
    return records, {"headers": headers, "header_row": header_row}, warnings


# ------------------------------------------------------------------ CSV
def _decode(data: bytes, warnings: list[str]) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    try:
        text = data.decode("cp1258")
        warnings.append("File không phải UTF-8; đã đọc bằng cp1258 (tiếng Việt Windows). Hãy kiểm tra dấu.")
        return text
    except UnicodeDecodeError:
        warnings.append("File không phải UTF-8; đã đọc bằng latin-1, có thể sai dấu tiếng Việt.")
        return data.decode("latin-1")


def _detect_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:20])
    counts = {d: sample.count(d) for d in (",", ";", "\t", "|")}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def parse_csv(path: Path) -> ParsedDocument:
    doc = ParsedDocument(file_type="csv")
    text = _decode(path.read_bytes(), doc.warnings)
    delim = _detect_delimiter(text)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delim)
    numbered = []
    try:
        for row in reader:
            numbered.append((reader.line_num, [safe_value(c) for c in row]))
            if len(numbered) > MAX_ROWS + HEADER_SCAN_ROWS + 5:
                raise ParseError(f"File có quá nhiều dòng (giới hạn {MAX_ROWS}).")
    except csv.Error as e:
        raise ParseError(f"CSV không hợp lệ: {e}") from e
    records, meta, warns = build_records(numbered)
    doc.records, doc.meta, doc.warnings = records, {**meta, "delimiter": delim}, doc.warnings + warns
    return doc


# ------------------------------------------------------------------ Excel
def parse_xlsx(path: Path) -> ParsedDocument:
    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException

    doc = ParsedDocument(file_type="xlsx")
    try:
        wb = load_workbook(path, data_only=True)  # data_only: lấy giá trị đã tính của công thức
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as e:
        raise ParseError("Không đọc được file Excel (file hỏng hoặc không đúng định dạng .xlsx).") from e

    sheets_meta = []
    total = 0
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            doc.warnings.append(f"Bỏ qua sheet ẩn '{ws.title}'.")
            continue
        numbered = [
            (n, [safe_value(c) for c in row])
            for n, row in enumerate(ws.iter_rows(values_only=True), start=1)
        ]
        records, meta, warns = build_records(numbered, prefix=f"{ws.title}!")
        total += len(records)
        if total > MAX_ROWS:
            raise ParseError(f"File có quá nhiều dòng (giới hạn {MAX_ROWS}).")
        doc.records.extend(records)
        doc.warnings.extend(f"[{ws.title}] {w}" for w in warns)
        sheets_meta.append({"sheet": ws.title, **meta, "rows": len(records)})
    doc.meta = {"sheets": sheets_meta}
    return doc
