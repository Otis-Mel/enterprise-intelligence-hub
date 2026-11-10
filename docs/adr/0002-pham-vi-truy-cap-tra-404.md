# ADR 0002: Phân quyền theo phạm vi, việc ngoài phạm vi trả 404

Trạng thái: chấp nhận

## Bối cảnh
Hệ thống có nhiều phòng ban và vai trò. Trả 403 cho tài nguyên của người khác tiết lộ rằng tài nguyên đó tồn tại.

## Quyết định
Vai trò: ADMIN (không thấy nội dung nghiệp vụ), EXECUTIVE (chỉ đọc toàn tổ chức, chỉ báo cáo đã publish), DEPT_LEADER (phòng ban, duy nhất được publish báo cáo), PM (dự án của mình), EMPLOYEE (task được giao, upload). Truy vấn luôn lọc theo phạm vi của người dùng, nên tài nguyên ngoài phạm vi trả 404. Hành động quan trọng ghi vào `AuditLog`.

## Hệ quả
- Không lộ sự tồn tại của dữ liệu ngoài phạm vi.
- Mọi endpoint mới phải đi qua bộ lọc phạm vi, và có test trong `test_rbac.py`.
