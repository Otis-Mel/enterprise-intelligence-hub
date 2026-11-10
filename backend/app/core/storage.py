"""Lưu file gốc. Đường dẫn do hệ thống tự sinh (UUID), không bao giờ dùng tên file người dùng đặt."""
from pathlib import Path

from app.core.config import get_settings


def storage_root() -> Path:
    root = Path(get_settings().storage_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_key(storage_key: str) -> Path:
    """Chuyển storage_key -> đường dẫn tuyệt đối, chặn path traversal."""
    root = storage_root()
    p = (root / storage_key).resolve()
    if root not in p.parents:
        raise ValueError("Invalid storage key")
    return p
