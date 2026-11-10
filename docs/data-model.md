# Data model & status mapping (Phase 0)

## Luồng dữ liệu: Raw → Normalized → Canonical
- **Raw**: dữ liệu gốc, chỉ append (Phase 2).
- **Normalized**: đã map sang schema chung, chưa được duyệt (Phase 3).
- **Canonical**: dữ liệu chính thức cho dashboard/KPI/report. Hiện là bảng `tasks`.

## Canonical task (đã cài ở `backend/app/models/core.py`)
| Field | Quy tắc |
|---|---|
| `assignee_id` | NULL nếu chưa xác định — không tự đoán |
| `due_date`, `start_date` | NULL nếu thiếu — không tự đặt deadline |
| `progress` | 0–100 hoặc NULL — không tự suy ra |
| `status_original` / `status_normalized` | giữ cả giá trị gốc và giá trị chuẩn hóa |
| `source_system` + `external_id` | unique → import idempotent |

## Status mapping đề xuất (cần bạn xác nhận với dữ liệu thực tế)
| Giá trị nguồn (ví dụ) | `status_normalized` |
|---|---|
| todo, to do, backlog, chưa làm, mới, open, not started | TODO |
| doing, in progress, đang làm, đang thực hiện, wip | IN_PROGRESS |
| blocked, vướng, tạm dừng do phụ thuộc, on hold | BLOCKED |
| done, completed, hoàn thành, xong, closed | DONE |
| cancelled, hủy, bỏ | CANCELLED |
| (không khớp quy tắc nào) | UNKNOWN → đưa vào hàng chờ review |

Giá trị lạ **không** được đoán: chuyển UNKNOWN và để người có quyền duyệt (Phase 3).

## Phân quyền
| Vai trò | Projects | Tasks | Quản trị |
|---|---|---|---|
| ADMIN | không xem nội dung | không xem nội dung | users, departments |
| DEPT_LEADER | cả phòng ban | cả phòng ban (sửa đầy đủ) | — |
| PM | project mình phụ trách | tasks trong project đó (sửa đầy đủ) | — |
| EMPLOYEE | project là thành viên | chỉ task được giao; chỉ sửa `status`, `progress` | — |

File upload: nhân viên thấy file mình tải lên; PM và Dept Leader thấy file cả phòng ban và là người duyệt/commit dữ liệu import; Admin không thấy.

Truy cập ngoài phạm vi trả về **404** (không lộ việc bản ghi tồn tại).

## Câu hỏi cần chốt (mục 16 của plan)
1. Ngành/quy mô doanh nghiệp pilot, số phòng ban, số người dùng.
2. Nguồn dữ liệu đầu tiên: Excel, Google Sheets, Jira, Trello?
3. 3–5 KPI + công thức (đề xuất: % task DONE, số task quá hạn, số task BLOCKED, task stale > N ngày, tỷ lệ task thiếu owner/deadline).
4. Ai duyệt dữ liệu import, ai duyệt báo cáo chính thức?
5. Có dữ liệu nhạy cảm (khách hàng, nhân sự, tài chính) không?

## Hàng chờ duyệt (Phase 3)
`normalized_records` nằm giữa `raw_records` và `tasks`. Mỗi bản ghi giữ giá trị gốc (`raw`), giá trị chuẩn hóa, cờ mơ hồ (`field_flags`), danh sách vấn đề (`issues`) và trạng thái duyệt: PENDING (có cảnh báo) / CLEAN (không vấn đề) / APPROVED / REJECTED / IMPORTED.
- Lỗi `error` (thiếu tên công việc) chặn việc duyệt; cảnh báo `warning` người duyệt được chấp nhận có chủ ý.
- Sau khi người duyệt sửa một trường, vấn đề liên quan tự biến mất (validate chạy lại trên trạng thái hiện tại).
