# ADR 0004: Commit idempotent và schema chỉ thêm, không sửa bảng cũ

Trạng thái: chấp nhận

## Bối cảnh
Cùng một file có thể được upload lại sau khi sửa. `create_all` của SQLAlchemy không ALTER bảng đã tồn tại, và dự án chưa dùng Alembic.

## Quyết định
Commit vào `tasks` theo khóa `(org, source_system "file:{phòng ban}:{tên file}", external_id hoặc row_ref)`, nên upload lại cùng tên file là cập nhật, không nhân đôi. Upload trùng checksum trong cùng phòng ban bị chặn. Thay đổi schema chỉ thêm bảng mới. Với PostgreSQL, thêm giá trị enum cần `ALTER TYPE` thủ công.

## Hệ quả
- Chạy lại import an toàn.
- Cần chuyển sang Alembic trước khi sửa cột của bảng cũ.
- Cờ trùng task có thể cũ nếu tiêu đề bị sửa khi review.
