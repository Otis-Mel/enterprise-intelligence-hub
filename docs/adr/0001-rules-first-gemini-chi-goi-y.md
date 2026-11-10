# ADR 0001: Rules-first, Gemini chỉ gợi ý hoặc diễn đạt

Trạng thái: chấp nhận

## Bối cảnh
Dữ liệu đầu vào là file của nhiều phòng ban, định dạng và cách viết khác nhau. Một mô hình ngôn ngữ đọc được văn bản tự do nhưng có thể bịa giá trị nghe có vẻ đúng, và kết quả khó tái lập.

## Quyết định
Chuẩn hóa bằng quy tắc xác định (status, ưu tiên, ngày, tiến độ). Gemini chỉ được dùng để trích xuất từ văn bản tự do, bắt buộc kèm `evidence` nguyên văn, và để diễn đạt báo cáo. Mọi đầu ra của Gemini đi qua kiểm tra rồi đến người duyệt, không ghi thẳng vào dữ liệu chuẩn. Có `PatternExtractor` làm phương án dự phòng không cần mạng.

## Hệ quả
- Giá trị mơ hồ để trống và gắn cờ thay vì đoán, nên số bản ghi cần người xem lại cao hơn.
- Đo được chất lượng: `evaluate_extraction.py` so Pattern và Gemini trên bộ dữ liệu tổng hợp, kết quả chỉ mang tính tương đối.
- Hệ thống vẫn chạy khi không có khóa API.
