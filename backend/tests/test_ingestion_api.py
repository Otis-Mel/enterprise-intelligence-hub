"""Test upload + import qua API (cần FastAPI/SQLAlchemy). Kiểm: phân quyền file, chống file giả, khử trùng,
import idempotent, raw record giữ nguyên giá trị gốc."""
import json
from pathlib import Path

import pytest

from app.scripts.generate_sample_data import main as generate


@pytest.fixture(scope="module")
def sample_dir(tmp_path_factory):
    root = tmp_path_factory.mktemp("gen_api")
    generate(str(root), seed=42)
    return root


def _upload(client, h, path: Path, name: str | None = None):
    with open(path, "rb") as f:
        return client.post("/api/v1/files/upload", files={"file": (name or path.name, f)}, headers=h)


def _import(client, h, file_id):
    return client.post("/api/v1/imports", json={"file_id": file_id}, headers=h)


def test_upload_and_import_csv(client, world, sample_dir):
    ids, h = world
    r = _upload(client, h["emp1"], sample_dir / "it_backlog.csv")
    assert r.status_code == 201, r.text
    fid = r.json()["id"]
    assert r.json()["processing_status"] == "UPLOADED" and r.json()["duplicate"] is False

    job = _import(client, h["emp1"], fid)
    assert job.status_code == 202, job.text
    jid = job.json()["id"]

    # TestClient chạy xong background task trước khi trả response -> job đã hoàn tất
    done = client.get(f"/api/v1/imports/{jid}", headers=h["emp1"]).json()
    truth = json.loads((sample_dir / "ground_truth.json").read_text(encoding="utf-8"))
    n_expected = len(truth["files"]["it_backlog.csv"]["records"])
    assert done["status"] == "NEEDS_MAPPING", done
    assert done["records_read"] == done["records_created"] == n_expected

    raw = client.get(f"/api/v1/imports/{jid}/raw?limit=5", headers=h["emp1"]).json()
    assert len(raw) == 5 and "summary" in raw[0]["payload"]  # giá trị gốc, chưa chuẩn hóa


def test_import_is_idempotent(client, world, sample_dir):
    ids, h = world
    fid = _upload(client, h["emp1"], sample_dir / "marketing_cong_viec.xlsx").json()["id"]
    j1 = _import(client, h["emp1"], fid)
    j2 = _import(client, h["emp1"], fid)
    assert j1.json()["id"] == j2.json()["id"] and j2.status_code == 200  # không tạo job/bản ghi trùng
    total = len(client.get(f"/api/v1/imports/{j1.json()['id']}/raw?limit=200", headers=h["emp1"]).json())
    assert total == 60


def test_duplicate_upload_same_department_returns_original(client, world, sample_dir):
    ids, h = world
    a = _upload(client, h["emp1"], sample_dir / "it_backlog.csv")
    b = _upload(client, h["emp2"], sample_dir / "it_backlog.csv")  # cùng phòng ban A
    assert a.status_code == 201 and b.status_code == 200
    assert b.json()["duplicate"] is True and b.json()["id"] == a.json()["id"]


def test_same_file_other_department_is_independent(client, world, sample_dir):
    """Không lộ file của phòng ban khác: upload cùng nội dung ở phòng B tạo bản ghi riêng, không báo 'trùng'."""
    ids, h = world
    a = _upload(client, h["emp1"], sample_dir / "it_backlog.csv")
    b = _upload(client, h["emp_b"], sample_dir / "it_backlog.csv")
    assert b.status_code == 201 and b.json()["duplicate"] is False and b.json()["id"] != a.json()["id"]


def test_cross_department_cannot_see_or_import(client, world, sample_dir):
    ids, h = world
    fid = _upload(client, h["emp1"], sample_dir / "it_backlog.csv").json()["id"]
    jid = _import(client, h["emp1"], fid).json()["id"]
    for who in ("emp_b", "pm_b"):
        assert client.get("/api/v1/files", headers=h[who]).json() == []
        assert _import(client, h[who], fid).status_code == 404
        assert client.get(f"/api/v1/imports/{jid}", headers=h[who]).status_code == 404
        assert client.get(f"/api/v1/imports/{jid}/raw", headers=h[who]).status_code == 404
    # Leader cùng phòng ban thấy; nhân viên khác cùng phòng ban thì không
    assert len(client.get("/api/v1/files", headers=h["leader_a"]).json()) == 1
    assert client.get("/api/v1/files", headers=h["emp2"]).json() == []


def test_admin_cannot_upload_or_see_files(client, world, admin_h, sample_dir):
    ids, h = world
    assert _upload(client, admin_h, sample_dir / "it_backlog.csv").status_code == 403
    _upload(client, h["emp1"], sample_dir / "it_backlog.csv")
    assert client.get("/api/v1/files", headers=admin_h).json() == []


def test_rejects_bad_files(client, world, tmp_path):
    ids, h = world
    exe = tmp_path / "evil.exe"
    exe.write_bytes(b"MZ")
    assert _upload(client, h["emp1"], exe).status_code == 415

    fake = tmp_path / "fake.xlsx"
    fake.write_text("không phải excel")
    assert _upload(client, h["emp1"], fake).status_code == 422

    empty = tmp_path / "empty.csv"
    empty.write_bytes(b"")
    assert _upload(client, h["emp1"], empty).status_code == 422


def test_path_traversal_filename_is_neutralized(client, world, sample_dir):
    ids, h = world
    r = _upload(client, h["emp1"], sample_dir / "it_backlog.csv", name="../../../etc/passwd.csv")
    assert r.status_code == 201
    assert r.json()["file_name"] == "passwd.csv"


def test_corrupt_file_marks_job_failed_with_clean_message(client, world, tmp_path):
    ids, h = world
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"PK\x03\x04" + b"garbage" * 50)  # qua kiểm tra đầu file nhưng parse hỏng
    fid = _upload(client, h["emp1"], bad).json()["id"]
    job = _import(client, h["emp1"], fid).json()
    done = client.get(f"/api/v1/imports/{job['id']}", headers=h["emp1"]).json()
    assert done["status"] == "FAILED" and done["error_summary"]
    assert "Traceback" not in done["error_summary"]


def test_free_text_report_import(client, world, sample_dir):
    ids, h = world
    fid = _upload(client, h["pm_a"], sample_dir / "reports" / "bao_cao_02_it.pdf").json()["id"]
    job = _import(client, h["pm_a"], fid).json()
    done = client.get(f"/api/v1/imports/{job['id']}", headers=h["pm_a"]).json()
    assert done["status"] == "NEEDS_MAPPING" and done["records_created"] >= 1
