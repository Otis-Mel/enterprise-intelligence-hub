"""Kiểu dữ liệu dùng chung cho parser. Parser KHÔNG đoán nghĩa: chỉ đọc đúng những gì có trong file."""
from dataclasses import dataclass, field

MAX_ROWS = 50_000
MAX_PDF_PAGES = 500
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # chống zip bomb cho xlsx/docx


class ParseError(Exception):
    """Lỗi parse có thông điệp an toàn để hiển thị cho người dùng."""


@dataclass
class ParsedRecord:
    row_ref: str  # vị trí trong file nguồn: "Sheet!R12", "R5", "P3", "page2"...
    kind: str  # "row" (dòng bảng) | "text" (khối văn bản)
    payload: dict


@dataclass
class ParsedDocument:
    file_type: str
    records: list[ParsedRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    needs_ocr: bool = False
    meta: dict = field(default_factory=dict)
