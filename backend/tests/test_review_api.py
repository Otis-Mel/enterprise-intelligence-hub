"""Test luồng Phase 3 qua API: upload -> import -> normalize -> sửa/duyệt -> commit vào tasks. (cần FastAPI/SQLAlchemy)"""
from pathlib import Path

import pytest

from app.scripts.generate_sample_data import main as generate


@pytest.fixture(scope="module")
def sample_dir(tmp_path_factory):
    root = tmp_path_factory.mktemp("gen_review")
    generate(str(root), seed=42)
    return root


def _upload(client, h, path: Path):
    with open(path, "rb") as f:
        r = client.post("/api/v1/files/upload", files={"file": (path.name, f)}, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _job(client, h, file_id) -> str:
    r = client.post("/api/v1/imports", json={"file_id": file_id}, headers=h)
    assert r.status_code in (200, 202), r.text
    return r.json()["id"]


def _normalize(client, h, job, **body):
    r = client.post(f"/api/v1/imports/{job}/normalize", json=body, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _records(client, h, job, **params):
    r = client.get(f"/api/v1/imports/{job}/records", params={"limit": 500, **params}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def project(client, world):
    ids, h = world
    r = client.post("/api/v1/projects", json={"name": "Dự án IT", "department_id": ids["dept_a"]}, headers=h["pm_a"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture()
def owners_a(client, world, admin_h):
    """Tạo người dùng phòng A trùng tên với người phụ trách trong dữ liệu mẫu.
    Hệ thống chỉ khớp người phụ trách khi tên trùng CHÍNH XÁC với một user; không có user thì bản ghi luôn cần người xem."""
    from app.scripts.generate_sample_data import OWNERS

    ids, _ = world
    for i, name in enumerate(OWNERS):
        r = client.post("/api/v1/users", headers=admin_h, json={
            "email": f"owner{i}@x.com", "full_name": name, "password": "Passw0rd!!", "role": "EMPLOYEE", "department_id": ids["dept_a"]})
        assert r.status_code == 201, r.text


def _prepare(client, world, sample_dir, file="it_backlog.csv", who="emp1"):
    ids, h = world
    job = _job(client, h[who], _upload(client, h[who], sample_dir / file))
    return job


def test_normalize_summary_counts_and_issue_codes(client, world, sample_dir):
    ids, h = world
    job = _prepare(client, world, sample_dir)
    s = _normalize(client, h["emp1"], job)
    assert s["total"] == 85 and s["file_status"] == "NEEDS_REVIEW"  # 80 task + 5 dòng trùng
    assert s["issue_counts"]["DUPLICATE_IN_FILE"] == 5
    assert sum(s["by_review_status"].values()) == 85 and set(s["by_review_status"]) <= {"CLEAN", "PENDING"}
    # idempotent: gọi lại không tạo thêm
    again = _normalize(client, h["emp1"], job)
    assert again["total"] == 85 and again["note"]


def test_ambiguous_and_unknown_values_land_in_review_not_clean(client, world, sample_dir, tmp_path):
    ids, h = world
    p = tmp_path / "amb.csv"
    p.write_text("Task,Status,Due\nA,Đang xử lý,03/04/2026\nB,Done,2026-11-02\n", encoding="utf-8")
    job = _job(client, h["emp1"], _upload(client, h["emp1"], p))
    _normalize(client, h["emp1"], job)
    a, b = _records(client, h["emp1"], job)
    assert a["review_status"] == "PENDING" and a["due_date"] is None and a["status_normalized"] == "UNKNOWN"
    assert {i["code"] for i in a["issues"]} >= {"UNKNOWN_STATUS", "AMBIGUOUS_DATE"}
    assert b["due_date"] == "2026-11-02" and "AMBIGUOUS_DATE" not in {i["code"] for i in b["issues"]}


def test_forced_date_order_changes_result(client, world, tmp_path):
    ids, h = world
    p = tmp_path / "d.csv"
    p.write_text("Task,Due\nA,03/04/2026\n", encoding="utf-8")
    job = _job(client, h["emp1"], _upload(client, h["emp1"], p))
    _normalize(client, h["emp1"], job, date_order="MDY")
    assert _records(client, h["emp1"], job)[0]["due_date"] == "2026-03-04"


def test_unmapped_columns_reported_and_override_applies(client, world, tmp_path):
    ids, h = world
    p = tmp_path / "u.csv"
    p.write_text("Việc cần làm,Ai làm\nA,Nguyen\n", encoding="utf-8")
    job = _job(client, h["emp1"], _upload(client, h["emp1"], p))
    s = _normalize(client, h["emp1"], job)
    assert s["unmapped_headers"][""] == ["Việc cần làm", "Ai làm"]
    assert _records(client, h["emp1"], job)[0]["issues"][0]["code"] == "MISSING_TITLE"
    _normalize(client, h["emp1"], job, force=True, column_mapping={"Việc cần làm": "title", "Ai làm": "assignee"})
    r = _records(client, h["emp1"], job)[0]
    assert r["title"] == "A" and r["assignee_raw"] == "Nguyen"


def test_invalid_column_mapping_target_rejected(client, world, sample_dir):
    ids, h = world
    job = _prepare(client, world, sample_dir)
    r = client.post(f"/api/v1/imports/{job}/normalize", json={"column_mapping": {"x": "password"}}, headers=h["emp1"])
    assert r.status_code == 422


def test_use_llm_without_key_gives_clear_error(client, world, sample_dir):
    ids, h = world
    job = _prepare(client, world, sample_dir)
    r = client.post(f"/api/v1/imports/{job}/normalize", json={"use_llm": True}, headers=h["emp1"])
    assert r.status_code == 422 and "GEMINI_API_KEY" in r.json()["detail"]


def test_only_managers_can_review_and_commit(client, world, sample_dir, project):
    ids, h = world
    job = _prepare(client, world, sample_dir)
    _normalize(client, h["emp1"], job)
    rec = _records(client, h["emp1"], job)[0]
    assert client.patch(f"/api/v1/normalized-records/{rec['id']}", json={"decision": "APPROVE"}, headers=h["emp1"]).status_code == 403
    assert client.post(f"/api/v1/imports/{job}/approve-clean", headers=h["emp1"]).status_code == 403
    assert client.post(f"/api/v1/imports/{job}/commit", json={"project_id": project}, headers=h["emp1"]).status_code == 403


def test_cross_department_cannot_touch_records(client, world, sample_dir, project):
    ids, h = world
    job = _prepare(client, world, sample_dir)
    _normalize(client, h["emp1"], job)
    rec = _records(client, h["emp1"], job)[0]
    assert client.patch(f"/api/v1/normalized-records/{rec['id']}", json={"decision": "APPROVE"}, headers=h["pm_b"]).status_code == 404
    assert client.get(f"/api/v1/imports/{job}/records", headers=h["pm_b"]).status_code == 404
    assert client.post(f"/api/v1/imports/{job}/normalize", json={}, headers=h["emp_b"]).status_code == 404
    assert client.post(f"/api/v1/imports/{job}/commit", json={"project_id": project}, headers=h["pm_b"]).status_code == 404


def test_approval_requires_fixing_errors_and_edit_clears_warnings(client, world, tmp_path):
    ids, h = world
    p = tmp_path / "e.csv"
    p.write_text("Task,Status,Due\n,Done,03/04/2026\n", encoding="utf-8")
    job = _job(client, h["emp1"], _upload(client, h["emp1"], p))
    _normalize(client, h["emp1"], job)
    rec = _records(client, h["emp1"], job)[0]
    url = f"/api/v1/normalized-records/{rec['id']}"
    r = client.patch(url, json={"decision": "APPROVE"}, headers=h["pm_a"])
    assert r.status_code == 422  # thiếu tên công việc -> lỗi bắt buộc
    r = client.patch(url, json={"title": "Họp khách", "due_date": "2026-04-03", "decision": "APPROVE"}, headers=h["pm_a"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["review_status"] == "APPROVED" and body["edited"] is True
    assert "AMBIGUOUS_DATE" not in {i["code"] for i in body["issues"]}  # người đã quyết ngày -> hết mơ hồ
    assert {i["code"] for i in body["issues"]} == {"MISSING_ASSIGNEE"}  # cảnh báo còn lại được chấp nhận có chủ ý


def test_assignee_must_be_same_department(client, world, tmp_path):
    ids, h = world
    p = tmp_path / "a.csv"
    p.write_text("Task,Priority\nA,High\n", encoding="utf-8")  # cần >= 2 cột để nhận ra dòng tiêu đề
    job = _job(client, h["emp1"], _upload(client, h["emp1"], p))
    _normalize(client, h["emp1"], job)
    rec = _records(client, h["emp1"], job)[0]
    url = f"/api/v1/normalized-records/{rec['id']}"
    assert client.patch(url, json={"assignee_id": ids["emp_b"]}, headers=h["pm_a"]).status_code == 422
    ok = client.patch(url, json={"assignee_id": ids["emp2"]}, headers=h["pm_a"])
    assert ok.status_code == 200 and ok.json()["assignee_id"] == ids["emp2"]
    assert "MISSING_ASSIGNEE" not in {i["code"] for i in ok.json()["issues"]}


def test_assignee_matched_only_on_exact_name(client, world, tmp_path):
    ids, h = world
    p = tmp_path / "n.csv"  # tên user trong world: 'emp1' (full_name = phần trước @)
    p.write_text("Task,Owner\nA,emp1\nB,Emp1 \nC,emp\n", encoding="utf-8")
    job = _job(client, h["emp1"], _upload(client, h["emp1"], p))
    _normalize(client, h["emp1"], job)
    a, b, c = _records(client, h["emp1"], job)
    assert a["assignee_id"] == ids["emp1"] and b["assignee_id"] == ids["emp1"]  # khác hoa/thường & khoảng trắng: vẫn là cùng tên
    assert c["assignee_id"] is None and "ASSIGNEE_NOT_FOUND" in {i["code"] for i in c["issues"]}  # gần giống thì KHÔNG đoán


def test_full_flow_commit_creates_tasks_and_is_idempotent(client, world, sample_dir, project, owners_a):
    ids, h = world
    job = _prepare(client, world, sample_dir, file="marketing_cong_viec.xlsx")
    s = _normalize(client, h["emp1"], job)
    assert s["total"] == 60

    # chưa duyệt gì -> không commit được
    assert client.post(f"/api/v1/imports/{job}/commit", json={"project_id": project}, headers=h["pm_a"]).status_code == 409

    n = client.post(f"/api/v1/imports/{job}/approve-clean", headers=h["pm_a"]).json()["approved"]
    assert n == s["by_review_status"]["CLEAN"] and n > 0

    c1 = client.post(f"/api/v1/imports/{job}/commit", json={"project_id": project}, headers=h["pm_a"])
    assert c1.status_code == 200, c1.text
    assert c1.json()["created"] == n and c1.json()["updated"] == 0

    tasks = client.get("/api/v1/tasks", headers=h["leader_a"]).json()
    assert len(tasks) == n
    t = tasks[0]
    assert t["source_system"].startswith("file:") and t["external_id"].startswith("MKT-")
    assert t["status_original"] and t["status_normalized"] != "UNKNOWN"  # giữ cả giá trị gốc lẫn chuẩn hóa

    # bản ghi đã IMPORTED: không sửa được nữa; commit lần 2 không còn gì để làm
    rec = next(r for r in _records(client, h["pm_a"], job) if r["review_status"] == "IMPORTED")
    assert client.patch(f"/api/v1/normalized-records/{rec['id']}", json={"title": "x"}, headers=h["pm_a"]).status_code == 409
    assert client.post(f"/api/v1/imports/{job}/commit", json={"project_id": project}, headers=h["pm_a"]).status_code == 409
    assert len(client.get("/api/v1/tasks", headers=h["leader_a"]).json()) == n


def test_commit_rejects_project_of_other_department(client, world, sample_dir):
    ids, h = world
    other = client.post("/api/v1/projects", json={"name": "B", "department_id": ids["dept_b"]}, headers=h["pm_b"]).json()["id"]
    job = _prepare(client, world, sample_dir)
    _normalize(client, h["emp1"], job)
    client.post(f"/api/v1/imports/{job}/approve-clean", headers=h["pm_a"])
    assert client.post(f"/api/v1/imports/{job}/commit", json={"project_id": other}, headers=h["pm_a"]).status_code == 403


def test_rejected_and_pending_records_never_reach_tasks(client, world, sample_dir, project, owners_a):
    ids, h = world
    job = _prepare(client, world, sample_dir)
    _normalize(client, h["emp1"], job)
    recs = _records(client, h["emp1"], job)
    clean = [r for r in recs if r["review_status"] == "CLEAN"]
    assert clean, "cần có bản ghi sạch để kiểm thử"
    client.post(f"/api/v1/imports/{job}/approve-clean", headers=h["pm_a"])
    victim = clean[0]["id"]
    assert client.patch(f"/api/v1/normalized-records/{victim}", json={"decision": "REJECT"}, headers=h["pm_a"]).status_code == 200
    out = client.post(f"/api/v1/imports/{job}/commit", json={"project_id": project}, headers=h["pm_a"]).json()
    assert out["created"] == len(clean) - 1  # bị từ chối + còn PENDING -> không vào tasks


def test_text_report_flow_with_evidence(client, world, sample_dir):
    ids, h = world
    job = _prepare(client, world, sample_dir, file="reports/bao_cao_02_it.pdf", who="pm_a")
    s = _normalize(client, h["pm_a"], job)
    assert s["total"] >= 3
    recs = _records(client, h["pm_a"], job)
    assert all(r["evidence"] and r["extraction_method"] == "pattern" and "#" in r["row_ref"] for r in recs)


def test_summary_endpoint_matches(client, world, sample_dir):
    ids, h = world
    job = _prepare(client, world, sample_dir)
    s = _normalize(client, h["emp1"], job)
    assert client.get(f"/api/v1/imports/{job}/summary", headers=h["emp1"]).json()["total"] == s["total"]
