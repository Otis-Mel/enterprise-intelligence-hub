"""Parser cho DOCX, PDF, TXT -> khối văn bản (và bảng trong DOCX)."""
from pathlib import Path

from app.services.parsers.base import MAX_PDF_PAGES, ParsedDocument, ParsedRecord, ParseError
from app.services.parsers.tabular import _decode, build_records, safe_value

MIN_CHARS_PER_PAGE = 30  # dưới ngưỡng này coi như PDF scan (không có text layer)


def parse_docx(path: Path) -> ParsedDocument:
    from docx import Document

    doc = ParsedDocument(file_type="docx")
    try:
        d = Document(str(path))
    except Exception as e:  # python-docx ném nhiều loại lỗi khác nhau
        raise ParseError("Không đọc được file Word (file hỏng hoặc không đúng định dạng .docx).") from e

    for i, p in enumerate(d.paragraphs, start=1):
        text = p.text.strip()
        if text:
            doc.records.append(
                ParsedRecord(row_ref=f"P{i}", kind="text", payload={"text": text, "style": p.style.name if p.style else None})
            )
    for t_i, table in enumerate(d.tables, start=1):
        numbered = [(r_i, [safe_value(c.text) for c in row.cells]) for r_i, row in enumerate(table.rows, start=1)]
        recs, _meta, warns = build_records(numbered, prefix=f"T{t_i}!")
        doc.records.extend(recs)
        doc.warnings.extend(f"[bảng {t_i}] {w}" for w in warns)
    return doc


def parse_pdf(path: Path) -> ParsedDocument:
    doc = ParsedDocument(file_type="pdf")
    pages: list[str] = []
    try:
        try:
            import fitz  # PyMuPDF (theo plan) - dùng nếu đã cài
        except ImportError:
            fitz = None
        if fitz is not None:
            with fitz.open(str(path)) as pdf:
                if pdf.needs_pass:
                    raise ParseError("PDF được bảo vệ bằng mật khẩu.")
                if pdf.page_count > MAX_PDF_PAGES:
                    raise ParseError(f"PDF quá dài (giới hạn {MAX_PDF_PAGES} trang).")
                pages = [pg.get_text() for pg in pdf]
        else:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            if reader.is_encrypted:
                raise ParseError("PDF được bảo vệ bằng mật khẩu.")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise ParseError(f"PDF quá dài (giới hạn {MAX_PDF_PAGES} trang).")
            pages = [pg.extract_text() or "" for pg in reader.pages]
    except ParseError:
        raise
    except Exception as e:
        raise ParseError("Không đọc được file PDF (file hỏng hoặc không đúng định dạng).") from e

    total_chars = 0
    for n, text in enumerate(pages, start=1):
        text = text.strip()
        total_chars += len(text)
        if text:
            doc.records.append(ParsedRecord(row_ref=f"page{n}", kind="text", payload={"text": text}))
    doc.meta = {"pages": len(pages), "chars": total_chars}
    if not pages or total_chars / len(pages) < MIN_CHARS_PER_PAGE:
        doc.needs_ocr = True
        doc.warnings.append("PDF gần như không có text layer (có thể là bản scan) - cần OCR trước khi trích xuất.")
    return doc


def parse_txt(path: Path) -> ParsedDocument:
    doc = ParsedDocument(file_type="txt")
    text = _decode(path.read_bytes(), doc.warnings)
    blocks = [b.strip() for b in text.replace("\r\n", "\n").split("\n\n")]
    for n, b in enumerate((b for b in blocks if b), start=1):
        doc.records.append(ParsedRecord(row_ref=f"B{n}", kind="text", payload={"text": b}))
    return doc
