# ADR 0003: Số liệu báo cáo tính bằng code, văn bản được kiểm chứng

Trạng thái: chấp nhận

## Bối cảnh
Báo cáo cần câu chữ dễ đọc, nhưng mô hình ngôn ngữ có thể viết sai hoặc bịa số.

## Quyết định
KPI tính trong `kpis.py` (active, overdue, due_soon, completion, stale). Gemini chỉ nhận số liệu đã tính để diễn đạt. `verify_narrative` từ chối toàn bộ văn bản nếu có số không nằm trong số liệu đã tính, và hệ thống dùng `template_narrative`. Báo cáo ở trạng thái nháp cho tới khi Leader publish.

## Hệ quả
- Không có con số nào trong báo cáo mà code chưa tính.
- Đổi lại, văn bản đôi khi khô hơn khi Gemini bị từ chối.
