"""Test API báo cáo: phân quyền, nháp -> duyệt, ảnh chụp số liệu, kiểm tra số của Gemini. (cần FastAPI/SQLAlchemy)"""


def _seed(client, h, ids):
    pid = client.post("/api/v1/projects", json={"name": "Dự án A", "department_id": ids["dept_a"]}, headers=h["pm_a"]).json()["id"]
    for title, st, due in [("quá hạn", "IN_PROGRESS", "2026-10-01"), ("bị chặn", "BLOCKED", None), ("xong", "DONE", "2026-09-01")]:
        body = {"project_id": pid, "title": title, "status_normalized": st, "assignee_id": ids["emp1"]}
        if due:
            body["due_date"] = due
        assert client.post("/api/v1/tasks", json=body, headers=h["pm_a"]).status_code == 201
    return pid


def _create(client, hdr, **kw):
    return client.post("/api/v1/reports", json={"as_of": "2026-11-01", **kw}, headers=hdr)


def test_create_draft_with_template_and_correct_numbers(client, world):
    ids, h = world
    _seed(client, h, ids)
    r = _create(client, h["pm_a"], title="Tuần 44")
    assert r.status_code == 201, r.text
    rep = r.json()
    assert rep["status"] == "DRAFT" and rep["narrative_method"] == "template" and rep["title"] == "Tuần 44"
    assert rep["kpis"]["total"] == 3 and rep["kpis"]["overdue"] == 1 and rep["kpis"]["blocked"] == 1
    assert any("1 việc đang quá hạn" in s for s in rep["narrative"]["risks"])


def test_only_pm_and_leader_create_and_only_leader_publishes(client, world):
    ids, h = world
    _seed(client, h, ids)
    assert _create(client, h["emp1"]).status_code == 403
    rid = _create(client, h["pm_a"]).json()["id"]
    assert client.post(f"/api/v1/reports/{rid}/publish", headers=h["pm_a"]).status_code == 403
    p = client.post(f"/api/v1/reports/{rid}/publish", headers=h["leader_a"])
    assert p.status_code == 200 and p.json()["status"] == "PUBLISHED" and p.json()["published_at"]
    assert client.post(f"/api/v1/reports/{rid}/publish", headers=h["leader_a"]).status_code == 409
    assert client.delete(f"/api/v1/reports/{rid}", headers=h["leader_a"]).status_code == 409  # đã chính thức: không xóa


def test_visibility_by_role_and_department(client, world, admin_h):
    ids, h = world
    _seed(client, h, ids)
    rid = _create(client, h["pm_a"]).json()["id"]
    # bản nháp: nhân viên, phòng khác, admin đều không thấy (404, không lộ sự tồn tại)
    for who in (h["emp1"], h["pm_b"], h["emp_b"]):
        assert client.get(f"/api/v1/reports/{rid}", headers=who).status_code == 404
        assert client.get("/api/v1/reports", headers=who).json() == []
    assert client.get(f"/api/v1/reports/{rid}", headers=admin_h).status_code == 404
    assert client.get("/api/v1/reports", headers=h["leader_a"]).json()[0]["id"] == rid
    client.post(f"/api/v1/reports/{rid}/publish", headers=h["leader_a"])
    assert client.get(f"/api/v1/reports/{rid}", headers=h["emp1"]).status_code == 200   # chính thức: nhân viên cùng phòng xem được
    assert client.get(f"/api/v1/reports/{rid}", headers=h["emp_b"]).status_code == 404  # phòng khác vẫn không
    assert client.get("/api/v1/reports", headers=admin_h).json() == []


def test_report_is_a_snapshot(client, world):
    ids, h = world
    pid = _seed(client, h, ids)
    rid = _create(client, h["pm_a"]).json()["id"]
    client.post("/api/v1/tasks", json={"project_id": pid, "title": "mới", "status_normalized": "TODO"}, headers=h["pm_a"])
    assert client.get(f"/api/v1/reports/{rid}", headers=h["pm_a"]).json()["kpis"]["total"] == 3


def test_delete_draft_rules(client, world):
    ids, h = world
    _seed(client, h, ids)
    rid = _create(client, h["pm_a"]).json()["id"]
    assert client.delete(f"/api/v1/reports/{rid}", headers=h["emp1"]).status_code == 403
    assert client.delete(f"/api/v1/reports/{rid}", headers=h["pm_a"]).status_code == 204
    assert client.get(f"/api/v1/reports/{rid}", headers=h["pm_a"]).status_code == 404


def test_use_llm_without_key_is_422(client, world):
    ids, h = world
    _seed(client, h, ids)
    assert _create(client, h["pm_a"], use_llm=True).status_code == 422


def _fake_gemini(monkeypatch, narrative):
    import app.api.v1.reports as mod

    class Fake:
        def __init__(self, *a, **k):
            pass

        def write_narrative(self, facts):
            return narrative

    monkeypatch.setattr(mod, "GeminiExtractor", Fake)


def test_gemini_narrative_with_valid_numbers_is_kept(client, world, monkeypatch):
    ids, h = world
    _seed(client, h, ids)
    _fake_gemini(monkeypatch, {"headline": "Có 1 việc quá hạn và 1 việc bị chặn.", "highlights": [], "risks": [], "next_actions": []})
    rep = _create(client, h["pm_a"], use_llm=True).json()
    assert rep["narrative_method"] == "gemini" and rep["narrative"]["headline"].startswith("Có 1 việc")


def test_gemini_narrative_with_invented_number_falls_back(client, world, monkeypatch):
    ids, h = world
    _seed(client, h, ids)
    _fake_gemini(monkeypatch, {"headline": "Có 57 việc quá hạn.", "highlights": [], "risks": [], "next_actions": []})
    rep = _create(client, h["pm_a"], use_llm=True).json()
    assert rep["narrative_method"] == "template" and "57" in rep["narrative_notes"][0]
    assert "57" not in str(rep["narrative"])
