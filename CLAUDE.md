# Quy tắc làm việc với AI trong repo này

Enterprise Intelligence Hub (EIH): nhập file, chuẩn hóa, kiểm tra, duyệt, theo dõi, phân tích, báo cáo. Rules-first: quy tắc và code quyết định dữ liệu chuẩn, Gemini chỉ gợi ý hoặc diễn đạt.

## Bốn nguyên tắc

1. **Nghĩ trước khi code.** Nói ra cách hiểu và giả định trước khi làm. Thiếu thông tin thì hỏi lại, không tự chọn im lặng.
2. **Đơn giản trước.** Không biến một yêu cầu nhỏ thành interface, factory hay file cấu hình mới.
3. **Chỉ sửa đúng chỗ cần sửa.** Đổi logic vài dòng thì diff vài dòng. Không refactor lan sang file không liên quan.
4. **Mục tiêu phải kiểm chứng được.** Mỗi việc có tiêu chí thành công cụ thể, thường là một test, và chạy test trước khi báo xong.

## Cách làm một việc

1. Hiểu: đọc code liên quan, chưa sửa.
2. Kế hoạch: liệt kê file dự kiến sửa, chờ người duyệt.
3. Làm: từng mẩu nhỏ, thử ngay sau mỗi mẩu.
4. Kiểm: `cd backend && pytest -q`. Test đỏ thì sửa code, không sửa test cho khớp.
5. Review độc lập: chạy review trong một phiên Claude riêng, phiên đó không viết code, rồi mới gộp.

## Vùng rủi ro

- **Xanh, AI tự chạy:** tài liệu, unit test, giao diện tĩnh, refactor hàm nhỏ.
- **Vàng, người đọc từng dòng:** logic chuẩn hóa và kiểm tra, KPI, phân quyền, schema DB, hợp đồng API, export.
- **Đỏ, người tự làm:** khóa API và `SECRET_KEY`, dữ liệu thật của công ty, thao tác xóa không hoàn tác, mật khẩu tài khoản.

## Ràng buộc của dự án

- Code sạch, không comment giải thích. Lý do và quyết định nằm trong `docs/adr/`.
- Gemini không bao giờ ghi dữ liệu chuẩn. Mọi con số trong báo cáo phải nằm trong số liệu đã tính, nếu không thì dùng bản template.
- Giá trị mơ hồ để trống và gắn cờ, không đoán.
- Việc ngoài phạm vi vai trò trả về 404.
- Không đổi bảng cũ khi chưa có Alembic. Chỉ thêm bảng mới.
- Không dán, in hay commit khóa API. Bí mật chỉ nằm trong `.env`. Dữ liệu mẫu phải ghi rõ là dữ liệu tổng hợp.
- Trước khi đẩy lên GitHub: đổi hoặc bỏ mật khẩu demo, kiểm tra `.env` và `*.db` đã bị ignore.

## Ghi chép

- Quyết định kiến trúc: `docs/adr/`.
- Bài học từ lỗi đã gặp: `docs/lessons.md`. Đọc trước khi làm việc tương tự, thêm mục mới sau mỗi sự cố.
