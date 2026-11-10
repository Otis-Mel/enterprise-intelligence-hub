Dữ liệu mẫu là dữ liệu tổng hợp. Tài khoản demo chỉ để chạy cục bộ, không dùng cho môi trường thật.

# Enterprise Intelligence Hub (EIH)

Nền tảng nội bộ hợp nhất dữ liệu công việc từ nhiều nguồn, chuẩn hóa có kiểm duyệt, theo dõi tiến độ và tạo báo cáo có truy vết nguồn. Xem kế hoạch đầy đủ: `Enterprise_Intelligence_Hub_Project_Plan.docx`.

**Luồng MVP:** Import → Normalize → Validate → Approve → Track → Analyze → Report

## Trạng thái triển khai
| Phase | Nội dung | Trạng thái |
|---|---|---|
| 0 | Schema, status mapping, dữ liệu mẫu (`docs/`) | ✅ bản nháp, cần xác nhận với dữ liệu thật |
| 1 | FastAPI + PostgreSQL + JWT + RBAC + Projects/Tasks + audit | ✅ viết xong; test RBAC chạy trên máy bạn |
| 2 | Upload + parser CSV/Excel/DOCX/PDF + raw storage + import job | ✅ parser đã test (16/16); API test chạy trên máy bạn |
| 3 | Chuẩn hóa, validate, phát hiện trùng, hàng chờ duyệt, commit vào tasks, trích xuất Gemini | ✅ logic thuần đã test (83 test); API/DB test chạy trên máy bạn |
| 4 | Dashboard KPI + giao diện web (HTML/JS thuần, không cần Node) | ✅ API test chạy trên máy bạn; giao diện đã kiểm tra bằng trình duyệt với server giả |
| 5a | Báo cáo nháp → duyệt, Gemini viết nhận xét có kiểm tra số liệu | ✅ logic đã test (9); API test chạy trên máy bạn |
| 5b-2 | Đo trích xuất văn bản tự do: luật vs Gemini (`evaluate_extraction`) | ✅ Pattern đã chạy; Gemini chạy trên máy bạn |
| 5b-1 | Cảnh báo (alerts) | ⏳ |
| 6 | Hardening & pilot | ⏳ |

## Chạy thử
```bash
cp .env.example .env            # ở THƯ MỤC GỐC project; điền SECRET_KEY, GEMINI_API_KEY
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest                          # RBAC + ingestion + review API + parsers + normalization (SQLite in-memory)
```
Chạy với PostgreSQL:
```bash
docker compose up -d db
cd backend && uvicorn app.main:app --reload   # tạo admin đầu tiên từ FIRST_ADMIN_*
```
Tài liệu API: http://localhost:8000/docs
Giao diện web: http://localhost:8000/ (tự chuyển tới `/app/`).

## Phase 4: dashboard và giao diện
Giao diện nằm ở `frontend/` (HTML/CSS/JS thuần, không build, **không cần Node**), do FastAPI phục vụ tại `/app`. CSP chặn script/style nội tuyến; mọi dữ liệu import chỉ hiển thị bằng `textContent` (có kiểm tra payload `<img onerror>` hiển thị như chữ).
Màn hình: Tổng quan (KPI, "cần chú ý", theo dự án), Công việc (lọc theo trạng thái/quá hạn), Nhập dữ liệu (upload, theo dõi đọc file), Hàng chờ duyệt (chuẩn hóa, sửa, duyệt/từ chối, duyệt hàng loạt bản ghi sạch, commit vào dự án).

**Định nghĩa KPI** (`services/analytics/kpis.py`): đang làm = không phải DONE/CANCELLED; quá hạn = đang làm và hạn < hôm nay; sắp đến hạn = trong 7 ngày (gồm biên); tỷ lệ hoàn thành = DONE ÷ (tổng − CANCELLED); tiến độ TB bỏ qua việc thiếu tiến độ; stale = đang làm và không cập nhật > 14 ngày. Số liệu chỉ tính trong phạm vi quyền của người xem (Admin thấy 0).


## Phase 5a: báo cáo
`POST /reports` (PM/Dept Leader) tạo **bản nháp**; chỉ Dept Leader `POST /reports/{id}/publish`. Số liệu tính bằng code (cùng hàm với dashboard) và lưu dạng ảnh chụp. Với `use_llm=true`, Gemini chỉ diễn đạt nhận xét; `verify_narrative` dò mọi con số trong câu, số nào không có trong số liệu thì bỏ cả bản Gemini và dùng bản mẫu cố định (`narrative_method` ghi rõ nguồn). Nhân viên chỉ xem báo cáo chính thức của phòng mình.

### Đo trích xuất văn bản tự do (luật vs Gemini)
```bash
cd backend && python -m app.scripts.evaluate_extraction              # chỉ luật, miễn phí
python -m app.scripts.evaluate_extraction --gemini --max-files 6     # thêm Gemini (tốn request)
```
Hai bộ: `standard` (mẫu câu cố định) và `hard` (câu viết nhiều kiểu, thứ tự xáo, ngày nhiều định dạng). Khớp theo câu trích, không theo tiêu đề. Dữ liệu tổng hợp: đây là so sánh tương đối, không phải độ chính xác trên tài liệu thật.

## Phase 3: luồng chuẩn hóa và duyệt
```
upload -> POST /imports -> POST /imports/{job}/normalize -> GET /imports/{job}/records
       -> PATCH /normalized-records/{id}  (sửa + APPROVE/REJECT)  |  POST /imports/{job}/approve-clean
       -> POST /imports/{job}/commit {project_id}   (chỉ bản ghi APPROVED mới vào bảng tasks)
```
- **Không đoán**: trạng thái lạ -> `UNKNOWN`; ngày `03/04/2026` mà cả cột không có bằng chứng thứ tự -> để trống + cờ `AMBIGUOUS_DATE`; tiến độ `0.7` -> cờ mơ hồ; tên người phụ trách chỉ khớp user khi trùng chính xác. Tất cả vào hàng chờ duyệt.
- **Thứ tự ngày/tháng theo cả cột**: có giá trị như `25/12` -> DMY; `12/25` -> MDY; mâu thuẫn -> xử lý từng giá trị. Có thể ép bằng `date_order`.
- **Gemini chỉ gợi ý, không tự ghi dữ liệu**: với văn bản tự do (`use_llm=true`), mỗi mục phải kèm câu trích nguyên văn có thật trong tài liệu, tiêu đề phải nằm trong câu đó; mục không đạt bị loại, giá trị không nằm trong câu bị bỏ. Có test mô phỏng prompt injection.
- **Người duyệt**: PM và Dept Leader. Nhân viên chỉ upload và xem hàng chờ của file mình.
- **Commit idempotent**: khóa `(source_system, external_id)`; import lại file cùng tên cập nhật task hiện có và ghi lịch sử thay đổi.

### Đánh giá chất lượng
```bash
cd backend && python -m app.scripts.evaluate_normalization --seed 42
```
In accuracy, số mục chuyển duyệt, **lỗi im lặng** (sai mà không cảnh báo) và precision/recall phát hiện trùng. Trên dữ liệu tổng hợp hiện đạt 0 lỗi im lặng.
**Lưu ý trung thực:** dữ liệu và đáp án cùng một tác giả, nên đây là kiểm tra hồi quy, chưa chứng minh khả năng tổng quát hóa. Test `test_normalization.py` kiểm tra thêm các giá trị chưa từng thấy (phải chuyển duyệt, không đoán). Với dữ liệu thật cần tự gán nhãn một mẫu nhỏ.

### Giới hạn đã biết
- Chưa có OCR cho PDF scan; chưa có gợi ý map người phụ trách hàng loạt (hiện sửa từng bản ghi hoặc tạo user trùng tên).
- Gemini client đã test bằng HTTP giả, **chưa gọi API thật**; chạy thử bằng key của bạn.
- File chỉ có 1 cột không nhận ra được dòng tiêu đề.
- Chưa có Alembic migration (dev dùng `AUTO_CREATE_TABLES=true`).

## Dữ liệu mẫu (synthetic)
Toàn bộ dữ liệu demo là **dữ liệu giả tự sinh**, không chứa thông tin thật:
```bash
cd backend && python -m app.scripts.generate_sample_data --out ../docs/sample_data/generated --seed 42
```
Sinh 13 file (Excel VN có banner, CSV EN có dòng trùng, Excel kiểu Mỹ với ngày MM/DD/YYYY mơ hồ, 5 báo cáo Word + 5 PDF văn bản tự do) cùng `ground_truth.json` (235 bản ghi đáp án) để đo độ chính xác ở Phase 3+.

## Quyết định thiết kế đáng chú ý
- **Parser không đoán nghĩa**: giữ nguyên giá trị gốc; ô ngày thật → ISO, ngày dạng text giữ nguyên (chuẩn hóa ở Phase 3 có review). Chuẩn hóa Unicode NFC cho tiếng Việt.
- **Raw bất biến + idempotent**: `raw_records` unique theo `(file, row_ref)`; import lại không tạo bản ghi trùng.
- **An toàn upload**: allowlist đuôi file, kiểm tra magic bytes, giới hạn dung lượng, chống zip bomb, tên file lưu bằng UUID (chống path traversal).
- **Không lộ thông tin chéo phòng ban**: khử trùng file chỉ trong cùng phòng ban; truy cập ngoài phạm vi trả 404; Admin không xem nội dung nghiệp vụ.
- PDF đọc bằng `pypdf` (thuần Python); tự dùng PyMuPDF nếu đã cài. PDF scan được gắn cờ `needs_ocr` (OCR chưa làm).

> Phase 1–2 dùng `Base.metadata.create_all` khi dev; migration Alembic sẽ thêm khi schema ổn định sau Phase 3.

## Bảo mật
- API key Gemini chỉ đặt trong `.env` (đã nằm trong `.gitignore`).
