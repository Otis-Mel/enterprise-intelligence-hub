"""Demo chạy trọn luồng với server thật: tạo phòng ban/người dùng -> upload -> chuẩn hóa -> duyệt -> commit vào tasks,
rồi thử Gemini THẬT trên báo cáo văn bản tự do (nếu đã cấu hình GEMINI_API_KEY).

Cách chạy (không cần Docker, dùng SQLite):
  Terminal 1 (trong backend/):   DATABASE_URL=sqlite:///./demo.db uvicorn app.main:app
  Terminal 2 (trong backend/):   python -m app.scripts.demo_flow
Chạy lại từ đầu: dừng server, xóa file demo.db, bật lại server.
"""
import argparse
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.scripts.generate_sample_data import OWNERS
from app.scripts.generate_sample_data import main as generate

PM_PASS = "DemoPass123!"


class Api:
    def __init__(self, base: str):
        self.c = httpx.Client(base_url=base.rstrip("/") + "/api/v1", timeout=180)
        self.token: str | None = None

    def call(self, method: str, path: str, ok=(200, 201, 202), **kw):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        r = self.c.request(method, path, headers=headers, **kw)
        if r.status_code not in ok:
            print(f"\n[LỖI] {method} {path} -> {r.status_code}\n{r.text[:600]}")
            raise SystemExit(1)
        return r

    def login(self, email: str, password: str):
        r = self.call("POST", "/auth/login", data={"username": email, "password": password})
        self.token = r.json()["access_token"]


def step(msg: str):
    print(f"\n=== {msg}")


def wait_for_import(api: Api, job: str, timeout: int = 120) -> None:
    """POST /imports trả lời ngay rồi đọc file ở nền; phải chờ job đọc xong mới chuẩn hóa được."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = api.call("GET", f"/imports/{job}").json()
        if j["status"] not in ("UPLOADED", "PARSING"):
            if j["status"] == "FAILED":
                print(f"\n[LỖI] Không đọc được file: {j['error_summary']}")
                raise SystemExit(1)
            return
        time.sleep(0.5)
    print("\n[LỖI] Quá thời gian chờ đọc file.")
    raise SystemExit(1)


def upload_import_normalize(api: Api, path: Path, **norm):
    with open(path, "rb") as f:
        up = api.call("POST", "/files/upload", files={"file": (path.name, f)}).json()
    job = api.call("POST", "/imports", json={"file_id": up["id"]}).json()["id"]
    wait_for_import(api, job)
    r = api.c.post(f"/imports/{job}/normalize", json=norm, headers={"Authorization": f"Bearer {api.token}"})
    return job, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    a = ap.parse_args()
    s = get_settings()
    api = Api(a.base)

    try:
        httpx.get(a.base.rstrip("/") + "/health", timeout=5).raise_for_status()
    except httpx.HTTPError:
        print(f"Không kết nối được server tại {a.base}. Hãy bật server ở terminal khác (xem hướng dẫn đầu file).")
        raise SystemExit(1)

    PM_EMAIL = "pm@demo-eih.com"  # cố định: tài khoản demo tạo một lần, các lần chạy sau dùng lại
    seed = int(time.time()) % 100000  # mỗi lần chạy sinh dữ liệu khác để file không bị coi là trùng với lần trước

    step("1. Chuẩn bị phòng ban và người dùng demo")
    api.login(s.first_admin_email, s.first_admin_password)
    existing = api.call("GET", "/users").json()
    pm_row = next((u for u in existing if u["email"] == PM_EMAIL), None)
    if pm_row:
        dept = pm_row["department_id"]
        print(f"Dùng lại tài khoản demo có sẵn: {PM_EMAIL}")
    else:
        dept = api.call("POST", "/departments", json={"name": "Demo IT"}).json()["id"]
        api.call("POST", "/users", json={"email": PM_EMAIL, "full_name": "Demo PM", "password": PM_PASS, "role": "PM", "department_id": dept})
        for i, name in enumerate(OWNERS):  # user trùng tên với người phụ trách trong dữ liệu mẫu để hệ thống khớp được
            api.call("POST", "/users", json={"email": f"owner{i}@demo-eih.com", "full_name": name, "password": PM_PASS,
                                              "role": "EMPLOYEE", "department_id": dept})
        print(f"Đã tạo phòng ban 'Demo IT', 1 PM và {len(OWNERS)} nhân viên.")
    LEADER_EMAIL = "leader@demo-eih.com"  # trưởng phòng: tài khoản duy nhất được duyệt báo cáo chính thức
    if not any(u["email"] == LEADER_EMAIL for u in existing):
        api.call("POST", "/users", json={"email": LEADER_EMAIL, "full_name": "Demo Leader", "password": PM_PASS,
                                          "role": "DEPT_LEADER", "department_id": dept})
        print(f"Đã tạo tài khoản trưởng phòng {LEADER_EMAIL}.")
    print(f"\n>>> ĐĂNG NHẬP GIAO DIỆN (mật khẩu chung: {PM_PASS})")
    print(f"    PM (tạo nháp, duyệt dữ liệu nhập): {PM_EMAIL}")
    print(f"    Trưởng phòng (duyệt báo cáo chính thức): {LEADER_EMAIL}")

    step("2. PM đăng nhập, lấy hoặc tạo project")
    api.login(PM_EMAIL, PM_PASS)
    proj = next((p for p in api.call("GET", "/projects").json() if p["name"] == "Backlog IT"), None)
    project = proj["id"] if proj else api.call("POST", "/projects", json={"name": "Backlog IT", "department_id": dept}).json()["id"]

    data = Path(tempfile.mkdtemp(prefix="eih-demo-"))
    generate(str(data), seed)

    step("3. File bảng: it_backlog.csv (có dòng trùng, thiếu người phụ trách, trạng thái lạ)")
    job, r = upload_import_normalize(api, data / "it_backlog.csv")
    if r.status_code != 200:
        print(f"\n[LỖI] Chuẩn hóa thất bại: HTTP {r.status_code} {r.text[:400]}")
        raise SystemExit(1)
    sm = r.json()
    print(f"Tổng {sm['total']} bản ghi | trạng thái duyệt: {sm['by_review_status']}")
    print(f"Vấn đề phát hiện: {sm['issue_counts']}")
    recs = api.call("GET", f"/imports/{job}/records", params={"only_issues": True, "limit": 3}).json()
    for rec in recs:
        print(f"  - {rec['row_ref']}: {rec['title']!r} -> " + "; ".join(i["message"] for i in rec["issues"]))

    n = api.call("POST", f"/imports/{job}/approve-clean").json()["approved"]
    print(f"PM duyệt hàng loạt {n} bản ghi sạch (bản ghi có cảnh báo vẫn chờ người xem).")
    c = api.call("POST", f"/imports/{job}/commit", json={"project_id": project}).json()
    print(f"Commit vào tasks: tạo {c['created']}, cập nhật {c['updated']}, không đổi {c['unchanged']}.")
    tasks = api.call("GET", "/tasks").json()
    print(f"Hiện có {len(tasks)} task. Theo trạng thái: {dict(Counter(t['status_normalized'] for t in tasks))}")

    step("4. Báo cáo văn bản tự do qua Gemini THẬT")
    if not s.gemini_api_key:
        print("Chưa có GEMINI_API_KEY trong .env (thư mục gốc project) -> bỏ qua bước này.")
        return
    print(f"Model: {s.gemini_model}")
    # tên file báo cáo phụ thuộc seed (phòng ban ngẫu nhiên) nên lấy theo đuôi file thay vì tên cố định
    picks = [sorted((data / "reports").glob(f"*.{ext}"))[0] for ext in ("pdf", "docx")]
    for path in picks:
        name = f"reports/{path.name}"
        job, r = upload_import_normalize(api, data / name, use_llm=True)
        print(f"\n--- {name}")
        if r.status_code != 200:
            print(f"Gemini không chạy được: HTTP {r.status_code} {r.text[:400]}")
            print("Nếu lỗi 404/model: đổi GEMINI_MODEL trong .env sang model đang có trong Google AI Studio.")
            continue
        sm = r.json()
        for w in sm["warnings"]:
            print(f"  [cảnh báo] {w}")
        for rec in api.call("GET", f"/imports/{job}/records").json():
            print(f"  * {rec['title']} | người: {rec['assignee_raw']} | trạng thái: {rec['status_normalized']} | "
                  f"hạn: {rec['due_date']} | tiến độ: {rec['progress']} | cờ: {[i['code'] for i in rec['issues']]}")
            print(f"      bằng chứng: {rec['evidence']}")
    print("\nĐối chiếu kết quả trên với nội dung file gốc (docs/sample_data/generated hoặc thư mục tạm in ở trên).")
    print(f"Thư mục dữ liệu mẫu của lần chạy này: {data}")


if __name__ == "__main__":
    sys.exit(main())
