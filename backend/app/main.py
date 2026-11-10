from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from sqlalchemy import select

from app.api.v1 import admin, auth, dashboard, files, reports, review, work
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Organization, Role, User


def bootstrap_first_admin() -> None:
    """Tạo organization + admin đầu tiên nếu DB còn trống (đổi mật khẩu ngay sau khi đăng nhập)."""
    s = get_settings()
    with SessionLocal() as db:
        if db.scalar(select(User.id).limit(1)):
            return
        org = Organization(name="My Company")
        db.add(org)
        db.flush()
        db.add(
            User(
                organization_id=org.id,
                email=s.first_admin_email,
                full_name="System Admin",
                password_hash=hash_password(s.first_admin_password),
                role=Role.ADMIN,
            )
        )
        db.commit()


def create_tables_for_dev() -> None:
    """Dev/MVP: tạo bảng nếu chưa có. Production sẽ thay bằng Alembic migration (AUTO_CREATE_TABLES=false)."""
    from app.db import session as session_mod
    from app.db.base import Base
    import app.models  # noqa: F401  (đăng ký toàn bộ model vào metadata)

    Base.metadata.create_all(session_mod.engine)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if get_settings().auto_create_tables:
        create_tables_for_dev()
    bootstrap_first_admin()
    yield


app = FastAPI(title=get_settings().app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth.router, admin.router, work.router, files.router, review.router, dashboard.router, reports.router):
    app.include_router(r, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}


# ---- Giao diện web (thư mục frontend/, HTML+CSS+JS thuần, không cần build) ----
_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_CSP = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"


@app.middleware("http")
async def frontend_security_headers(request, call_next):
    resp = await call_next(request)
    if request.url.path.startswith("/app"):
        resp.headers["Content-Security-Policy"] = _CSP  # nội dung import là dữ liệu không tin cậy: chặn script/style nội tuyến
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Cache-Control"] = "no-cache"
    return resp


if _FRONTEND.is_dir():
    app.mount("/app", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/app/")
