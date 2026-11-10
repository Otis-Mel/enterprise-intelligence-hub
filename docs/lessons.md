# Bài học từ các lỗi đã gặp

Mỗi mục: lỗi gì, vì sao xảy ra, lần sau làm khác ra sao.

## Session SQLAlchemy không tự flush
- Lỗi: truy vấn ngay sau khi thêm bản ghi không thấy dữ liệu mới.
- Vì sao: session tạo với `autoflush=False`.
- Lần sau: gọi `db.flush()` trước khi truy vấn lại trong cùng giao dịch.

## Đổi bảng cũ không có hiệu lực
- Lỗi: thêm cột vào model nhưng bảng thật không đổi.
- Vì sao: `create_all` chỉ tạo bảng mới, chưa có Alembic.
- Lần sau: chỉ thêm bảng mới. Trên PostgreSQL, thêm giá trị enum bằng `ALTER TYPE` thủ công.

## Test phụ thuộc vào `.env` thật
- Lỗi: test đổi hành vi hoặc có nguy cơ gọi API thật khi `.env` có khóa.
- Vì sao: biến trong `.env` được đọc khi chạy test.
- Lần sau: `conftest.py` ghim mọi biến test cần trước khi import app, biến môi trường luôn thắng `.env`.

## Test API không chạy được trong môi trường bị chặn mạng
- Lỗi: không cài được FastAPI và SQLAlchemy để chạy test API.
- Vì sao: môi trường sandbox chặn pip.
- Lần sau: tách test logic thuần để chạy ở bất cứ đâu, test API chạy trên máy thật và trong CI.

## Dữ liệu demo bị lẫn khi chạy nhiều lần
- Lỗi: `demo_flow` chọn nhầm file báo cáo, hoặc tưởng là trùng.
- Vì sao: file mẫu sinh ngẫu nhiên mỗi lần, và cùng tên file nghĩa là cập nhật chứ không phải trùng.
- Lần sau: chọn file bằng glob, và nhớ quy tắc idempotent trong ADR 0004.

## Gemini đôi khi bỏ hậu tố trong tiêu đề
- Lỗi: tiêu đề "…#1" bị trả về thiếu "#1" trong một lần chạy demo.
- Vì sao: mô hình diễn đạt lại tiêu đề.
- Lần sau: giữ thêm chỉ số `title_lenient` khi đánh giá, và so khớp bằng `evidence`.

## Số liệu đánh giá có giới hạn
- Lỗi: dễ hiểu nhầm 100% là độ chính xác tuyệt đối.
- Vì sao: dữ liệu do chính tác giả sinh ra, 6 file và 26 câu.
- Lần sau: luôn ghi chú đây là so sánh tương đối, không phải độ chính xác trên tài liệu thật.

## Khóa API và mật khẩu demo
- Lỗi: nguy cơ lộ khóa hoặc mật khẩu khi chia sẻ hoặc đẩy lên GitHub.
- Vì sao: khóa nằm trong `.env`, mật khẩu demo nằm trong README và `demo_flow`.
- Lần sau: không dán khóa vào chat hay commit, tạo lại `SECRET_KEY` nếu đã lộ, và đổi mật khẩu demo trước khi push.
