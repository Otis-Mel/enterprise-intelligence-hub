import os

# Dùng SQLite in-memory cho test; phải set trước khi import app
import tempfile

# Ghim mọi biến mà test phụ thuộc để .env thật của bạn (mật khẩu admin, GEMINI_API_KEY...) không làm test đổi hành vi
# hoặc gọi API thật. Biến môi trường luôn thắng file .env.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["FIRST_ADMIN_EMAIL"] = "admin@example.com"
os.environ["FIRST_ADMIN_PASSWORD"] = "ChangeMe123!"
os.environ["GEMINI_API_KEY"] = ""
os.environ["AUTO_CREATE_TABLES"] = "true"
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="eih-test-storage-")

import pytest


@pytest.fixture()
def client():
    # import muộn để test thuần (parsers...) chạy được khi chưa cài FastAPI/SQLAlchemy
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db import session as session_mod
    from app.db.base import Base

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    session_mod.engine = engine
    session_mod.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    import app.main as main_mod
    from app.db.session import get_db
    import app.models  # noqa: F401

    main_mod.SessionLocal = session_mod.SessionLocal
    Base.metadata.create_all(engine)

    def override_get_db():
        db = session_mod.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    main_mod.app.dependency_overrides[get_db] = override_get_db
    with TestClient(main_mod.app) as c:  # chạy lifespan -> tạo admin đầu tiên
        yield c
    main_mod.app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def login(client, email, password):
    r = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def admin_h(client):
    return login(client, "admin@example.com", "ChangeMe123!")


@pytest.fixture()
def world(client, admin_h):
    """2 phòng ban; Dept A có leader, PM, 2 nhân viên; Dept B có PM + nhân viên."""
    def mk_dept(name):
        r = client.post("/api/v1/departments", json={"name": name}, headers=admin_h)
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def mk_user(email, role, dept):
        r = client.post(
            "/api/v1/users",
            json={"email": email, "full_name": email.split("@")[0], "password": "Passw0rd!!", "role": role, "department_id": dept},
            headers=admin_h,
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    a, b = mk_dept("Dept A"), mk_dept("Dept B")
    ids = {
        "dept_a": a,
        "dept_b": b,
        "leader_a": mk_user("leader_a@x.com", "DEPT_LEADER", a),
        "pm_a": mk_user("pm_a@x.com", "PM", a),
        "emp1": mk_user("emp1@x.com", "EMPLOYEE", a),
        "emp2": mk_user("emp2@x.com", "EMPLOYEE", a),
        "pm_b": mk_user("pm_b@x.com", "PM", b),
        "emp_b": mk_user("emp_b@x.com", "EMPLOYEE", b),
    }
    h = {k: login(client, f"{k}@x.com", "Passw0rd!!") for k in ["leader_a", "pm_a", "emp1", "emp2", "pm_b", "emp_b"]}
    return ids, h
