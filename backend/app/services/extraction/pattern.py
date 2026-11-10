"""Extractor offline (không cần API key) cho báo cáo viết theo mẫu:

    - <Tên công việc>, do <Người> phụ trách, hạn dd/mm/yyyy, <cụm trạng thái>, tiến độ NN%.

Đây là bản dự phòng khi chưa có Gemini key và là chuẩn để so sánh. Nó CHỈ hiểu mẫu câu này (khớp với dữ liệu
tổng hợp do script sinh ra); báo cáo viết tự do thật cần Gemini. Câu không khớp mẫu bị bỏ qua, không đoán.
"""
import re

_PROGRESS = re.compile(r"^tiến độ\s+(.+)$", re.IGNORECASE)
_ASSIGNEE = re.compile(r"^do\s+(.+?)\s+phụ trách$", re.IGNORECASE)
_DUE = re.compile(r"^hạn\s+(.+)$", re.IGNORECASE)


class PatternExtractor:
    name = "pattern"

    def extract(self, text: str) -> list[dict]:
        items = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("- "):
                continue
            sentence = line
            body = line[2:].rstrip(".").strip()
            parts = [p.strip() for p in body.split(", ")]
            if len(parts) < 2:
                continue
            it = {"title": parts[0], "assignee": None, "status": None, "due_date": None, "progress": None, "evidence": sentence}
            for p in parts[1:]:
                if m := _ASSIGNEE.match(p):
                    it["assignee"] = m[1]
                elif m := _DUE.match(p):
                    it["due_date"] = m[1]
                elif m := _PROGRESS.match(p):
                    it["progress"] = m[1]
                else:
                    it["status"] = p
            items.append(it)
        return items
