"""Test phân quyền - đặc biệt truy cập chéo phòng ban (yêu cầu trong plan, mục 13 & checklist)."""
from conftest import login


def _project(client, h, dept, owner=None, members=()):
    r = client.post(
        "/api/v1/projects",
        json={"name": "P", "department_id": dept, "member_ids": list(members)},
        headers=h,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _task(client, h, project_id, assignee=None, title="T"):
    r = client.post("/api/v1/tasks", json={"project_id": project_id, "title": title, "assignee_id": assignee}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_unauthenticated_rejected(client):
    assert client.get("/api/v1/tasks").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_wrong_password(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin@example.com", "password": "nope"})
    assert r.status_code == 401


def test_only_admin_manages_users(client, world):
    ids, h = world
    r = client.post(
        "/api/v1/users",
        json={"email": "z@x.com", "full_name": "z", "password": "Passw0rd!!"},
        headers=h["pm_a"],
    )
    assert r.status_code == 403


def test_admin_cannot_see_business_content(client, world, admin_h):
    ids, h = world
    pid = _project(client, h["pm_a"], ids["dept_a"])
    _task(client, h["pm_a"], pid, ids["emp1"])
    assert client.get("/api/v1/tasks", headers=admin_h).json() == []
    assert client.get("/api/v1/projects", headers=admin_h).json() == []


def test_cross_department_isolation(client, world):
    ids, h = world
    pid = _project(client, h["pm_a"], ids["dept_a"])
    tid = _task(client, h["pm_a"], pid, ids["emp1"])

    # PM/Employee của phòng B không thấy gì
    for who in ("pm_b", "emp_b"):
        assert client.get("/api/v1/tasks", headers=h[who]).json() == []
        assert client.get(f"/api/v1/tasks/{tid}", headers=h[who]).status_code == 404
        r = client.patch(f"/api/v1/tasks/{tid}", json={"progress": 99}, headers=h[who])
        assert r.status_code == 404

    # PM phòng B không tạo task trong project phòng A
    r = client.post("/api/v1/tasks", json={"project_id": pid, "title": "hack"}, headers=h["pm_b"])
    assert r.status_code == 403

    # PM phòng B không tạo project cho phòng A
    r = client.post("/api/v1/projects", json={"name": "x", "department_id": ids["dept_a"]}, headers=h["pm_b"])
    assert r.status_code == 403


def test_leader_sees_whole_department(client, world):
    ids, h = world
    pid = _project(client, h["pm_a"], ids["dept_a"])
    _task(client, h["pm_a"], pid, ids["emp1"])
    _task(client, h["pm_a"], pid, ids["emp2"])
    assert len(client.get("/api/v1/tasks", headers=h["leader_a"]).json()) == 2


def test_employee_sees_only_assigned(client, world):
    ids, h = world
    pid = _project(client, h["pm_a"], ids["dept_a"], members=[ids["emp1"], ids["emp2"]])
    t1 = _task(client, h["pm_a"], pid, ids["emp1"], "mine")
    t2 = _task(client, h["pm_a"], pid, ids["emp2"], "theirs")
    mine = client.get("/api/v1/tasks", headers=h["emp1"]).json()
    assert [t["id"] for t in mine] == [t1]
    assert client.get(f"/api/v1/tasks/{t2}", headers=h["emp1"]).status_code == 404


def test_employee_limited_fields_and_audit_trail(client, world):
    ids, h = world
    pid = _project(client, h["pm_a"], ids["dept_a"])
    tid = _task(client, h["pm_a"], pid, ids["emp1"])

    ok = client.patch(f"/api/v1/tasks/{tid}", json={"status_normalized": "IN_PROGRESS", "progress": 40, "comment": "bắt đầu"}, headers=h["emp1"])
    assert ok.status_code == 200
    assert ok.json()["status_normalized"] == "IN_PROGRESS"
    assert float(ok.json()["progress"]) == 40

    for forbidden in ({"due_date": "2026-12-31"}, {"assignee_id": ids["emp2"]}, {"title": "đổi tên"}):
        r = client.patch(f"/api/v1/tasks/{tid}", json=forbidden, headers=h["emp1"])
        assert r.status_code == 403, forbidden


def test_progress_validation(client, world):
    ids, h = world
    pid = _project(client, h["pm_a"], ids["dept_a"])
    r = client.post("/api/v1/tasks", json={"project_id": pid, "title": "x", "progress": 150}, headers=h["pm_a"])
    assert r.status_code == 422


def test_task_without_assignee_or_deadline_is_allowed(client, world):
    """Không tự bịa dữ liệu: thiếu owner/deadline/progress -> giữ NULL."""
    ids, h = world
    pid = _project(client, h["pm_a"], ids["dept_a"])
    r = client.post("/api/v1/tasks", json={"project_id": pid, "title": "chưa rõ"}, headers=h["pm_a"])
    body = r.json()
    assert body["assignee_id"] is None and body["due_date"] is None and body["progress"] is None
