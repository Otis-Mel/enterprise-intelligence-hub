"""Test API dashboard: số liệu đúng và chỉ tính trong phạm vi quyền của người xem. (cần FastAPI/SQLAlchemy)"""


def _project(client, h, dept):
    r = client.post("/api/v1/projects", json={"name": "Dự án A", "department_id": dept}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _task(client, h, pid, **kw):
    r = client.post("/api/v1/tasks", json={"project_id": pid, "title": kw.pop("title", "T"), **kw}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_summary_counts_and_scope(client, world):
    ids, h = world
    pid = _project(client, h["pm_a"], ids["dept_a"])
    _task(client, h["pm_a"], pid, title="quá hạn", status_normalized="IN_PROGRESS", due_date="2026-10-01", assignee_id=ids["emp1"])
    _task(client, h["pm_a"], pid, title="xong", status_normalized="DONE", due_date="2026-09-01", assignee_id=ids["emp1"])
    _task(client, h["pm_a"], pid, title="bị chặn", status_normalized="BLOCKED", assignee_id=ids["emp2"])
    _task(client, h["pm_a"], pid, title="thiếu hết")

    s = client.get("/api/v1/dashboard/summary", params={"as_of": "2026-11-01"}, headers=h["leader_a"]).json()
    assert s["total"] == 4 and s["overdue"] == 1 and s["blocked"] == 1 and s["missing_assignee"] == 1
    assert s["overdue_tasks"][0]["title"] == "quá hạn" and s["overdue_tasks"][0]["days_overdue"] == 31
    assert s["by_project"][0]["name"] == "Dự án A"

    # nhân viên chỉ thấy số liệu của task được giao cho mình
    e = client.get("/api/v1/dashboard/summary", params={"as_of": "2026-11-01"}, headers=h["emp1"]).json()
    assert e["total"] == 2 and e["blocked"] == 0

    # phòng ban khác và admin không thấy gì
    assert client.get("/api/v1/dashboard/summary", headers=h["pm_b"]).json()["total"] == 0
    assert client.get("/api/v1/dashboard/summary", headers=h["emp_b"]).json()["total"] == 0


def test_admin_sees_zero(client, world, admin_h):
    ids, h = world
    pid = _project(client, h["pm_a"], ids["dept_a"])
    _task(client, h["pm_a"], pid)
    assert client.get("/api/v1/dashboard/summary", headers=admin_h).json()["total"] == 0


def test_requires_auth(client):
    assert client.get("/api/v1/dashboard/summary").status_code == 401


def test_directory_same_department_only_no_email(client, world, admin_h):
    ids, h = world
    people = client.get("/api/v1/directory", headers=h["emp1"]).json()
    names = {p["full_name"] for p in people}
    assert {"emp1", "emp2", "pm_a", "leader_a"} <= names and "emp_b" not in names and "pm_b" not in names
    assert all(set(p) == {"id", "full_name"} for p in people)
    assert client.get("/api/v1/directory", headers=admin_h).json() == []
    assert client.get("/api/v1/directory").status_code == 401


def test_import_list_scope_and_names(client, world, tmp_path):
    ids, h = world
    p = tmp_path / "x.csv"
    p.write_text("Task,Status\nA,Done\n", encoding="utf-8")
    with open(p, "rb") as f:
        fid = client.post("/api/v1/files/upload", files={"file": ("x.csv", f)}, headers=h["emp1"]).json()["id"]
    jid = client.post("/api/v1/imports", json={"file_id": fid}, headers=h["emp1"]).json()["id"]

    mine = client.get("/api/v1/imports", headers=h["emp1"]).json()
    assert len(mine) == 1 and mine[0]["job_id"] == jid and mine[0]["file_name"] == "x.csv"
    assert len(client.get("/api/v1/imports", headers=h["pm_a"]).json()) == 1       # PM thấy file cả phòng ban
    assert client.get("/api/v1/imports", headers=h["emp2"]).json() == []            # đồng nghiệp thì không
    assert client.get("/api/v1/imports", headers=h["pm_b"]).json() == []            # phòng khác thì không


def test_pending_review_counts_waiting_records(client, world, tmp_path):
    ids, h = world
    p = tmp_path / "y.csv"
    p.write_text("Task,Status\nA,Done\nB,lạ\n", encoding="utf-8")
    with open(p, "rb") as f:
        fid = client.post("/api/v1/files/upload", files={"file": ("y.csv", f)}, headers=h["emp1"]).json()["id"]
    jid = client.post("/api/v1/imports", json={"file_id": fid}, headers=h["emp1"]).json()["id"]
    assert client.post(f"/api/v1/imports/{jid}/normalize", json={}, headers=h["emp1"]).status_code == 200
    assert client.get("/api/v1/dashboard/summary", headers=h["emp1"]).json()["pending_review"] == 2
    assert client.get("/api/v1/dashboard/summary", headers=h["pm_b"]).json()["pending_review"] == 0


def test_frontend_served_with_security_headers(client):
    r = client.get("/app/", follow_redirects=True)
    assert r.status_code == 200
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp
    assert client.get("/", follow_redirects=False).status_code in (302, 307)
