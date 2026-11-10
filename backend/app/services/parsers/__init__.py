"""Chọn parser theo loại file + kiểm tra an toàn (magic bytes, zip bomb)."""
import zipfile
from pathlib import Path

from app.services.parsers.base import MAX_UNCOMPRESSED_BYTES, ParsedDocument, ParseError
from app.services.parsers.documents import parse_docx, parse_pdf, parse_txt
from app.services.parsers.tabular import parse_csv, parse_xlsx

PARSERS = {".csv": parse_csv, ".xlsx": parse_xlsx, ".docx": parse_docx, ".pdf": parse_pdf, ".txt": parse_txt}
SUPPORTED_EXTENSIONS = frozenset(PARSERS)


def sniff_matches_extension(path: Path, ext: str) -> bool:
    """Nội dung file phải khớp đuôi file (chặn file giả mạo đổi đuôi)."""
    with open(path, "rb") as f:
        head = f.read(8192)
    if ext in (".xlsx", ".docx"):
        return head.startswith(b"PK\x03\x04")
    if ext == ".pdf":
        return b"%PDF-" in head[:1024]
    if ext in (".csv", ".txt"):
        return b"\x00" not in head or head[:2] in (b"\xff\xfe", b"\xfe\xff")
    return False


def _check_zip_safe(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_UNCOMPRESSED_BYTES:
                raise ParseError("File nén quá lớn sau khi giải nén.")
    except zipfile.BadZipFile as e:
        raise ParseError("File hỏng hoặc không đúng định dạng.") from e


def parse_file(path: Path, ext: str) -> ParsedDocument:
    ext = ext.lower()
    if ext not in PARSERS:
        raise ParseError(f"Định dạng '{ext}' chưa được hỗ trợ.")
    if not sniff_matches_extension(path, ext):
        raise ParseError("Nội dung file không khớp với đuôi file.")
    if ext in (".xlsx", ".docx"):
        _check_zip_safe(path)
    return PARSERS[ext](path)
