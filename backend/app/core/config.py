from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND = Path(__file__).resolve().parents[2]  # .../backend
_ROOT = _BACKEND.parent  # thư mục gốc project (nơi đặt .env theo README)


class Settings(BaseSettings):
    # Đọc .env ở thư mục gốc và/hoặc backend/, không phụ thuộc thư mục đang đứng khi chạy lệnh.
    # File sau ghi đè file trước; biến môi trường luôn thắng file.
    model_config = SettingsConfigDict(env_file=(_ROOT / ".env", _BACKEND / ".env"), extra="ignore")

    app_name: str = "Enterprise Intelligence Hub"
    database_url: str = "postgresql+psycopg2://eih:eih@localhost:5432/eih"

    auto_create_tables: bool = True  # dev: tạo bảng khi khởi động; production: false + Alembic

    # Auth
    secret_key: str = "change-me-in-env"
    access_token_expire_minutes: int = 60 * 8
    jwt_algorithm: str = "HS256"

    # Lưu file gốc (dev: thư mục local; production: S3/MinIO)
    storage_dir: str = "./storage"
    max_upload_mb: int = 25

    # LLM (dùng từ Phase 2 trở đi; key CHỈ nằm trong .env, không commit)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # Bootstrap admin đầu tiên
    first_admin_email: str = "admin@example.com"
    first_admin_password: str = "ChangeMe123!"


@lru_cache
def get_settings() -> Settings:
    return Settings()
