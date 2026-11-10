"""Test bộ đo trích xuất: bộ khó làm luật hỏng; bộ đo nhận đúng khi extractor trả đúng, và tách lỗi cắt hậu tố '#N'. (hàm thuần)"""
import random
from pathlib import Path

from app.scripts.evaluate_extraction import evaluate_set
from app.scripts.hard_reports import write_hard_reports
from app.services.extraction.pattern import PatternExtractor


def _build(tmp_path: Path):
    truth = write_hard_reports(tmp_path, random.Random(7), 3)
    return truth


def test_hard_reports_are_deterministic_and_grounded(tmp_path):
    t1 = write_hard_reports(tmp_path / "a", random.Random(7), 2) if (tmp_path / "a").mkdir() is None else None
    t2 = write_hard_reports(tmp_path / "b", random.Random(7), 2) if (tmp_path / "b").mkdir() is None else None
    assert t1 == t2
    for f in t1.values():
        for r in f["records"]:
            assert r["title"] in r["evidence"]                         # tiêu đề nằm trong câu: Gemini có thể trích đúng
            if r["owner"]:
                assert r["owner"] in r["evidence"]


def test_pattern_extractor_fails_on_hard_set(tmp_path):
    truth = _build(tmp_path)
    r = evaluate_set(tmp_path, truth, PatternExtractor())
    assert r["records"]["recall"] == 0.0                              # luật chỉ hiểu mẫu câu cố định


class OracleExtractor:
    """Giả lập 'Gemini hoàn hảo': trả đúng đáp án, nhưng cắt hậu tố ' #N' khỏi tên như Gemini thật đã làm."""
    name = "oracle"

    def __init__(self, truth):
        self.recs = [r for f in truth.values() for r in f["records"]]

    def extract(self, text):
        import re
        out = []
        for r in self.recs:
            if r["evidence"] in text:
                m = re.search(r"\d{1,2}/\d{1,2}/\d{4}|\d{1,2}-\d{1,2}-\d{4}|\d{1,2} tháng \d{1,2} năm \d{4}", r["evidence"])
                out.append({"title": re.sub(r"\s*#\d+$", "", r["title"]), "assignee": r["owner"], "status": None,
                            "due_date": m and m[0], "progress": None, "evidence": r["evidence"]})  # ngày chép NGUYÊN VĂN như Gemini
        return out


def test_evaluator_separates_suffix_loss_from_real_title_errors(tmp_path):
    truth = _build(tmp_path)
    r = evaluate_set(tmp_path, truth, OracleExtractor(truth))
    assert r["records"]["recall"] == 1.0 and r["records"]["precision"] == 1.0
    assert r["fields"]["title_lenient"]["accuracy"] == 1.0            # đúng khi bỏ qua hậu tố
    assert r["fields"]["title"]["accuracy"] == 0.0                    # nhưng tên đầy đủ thì sai (đúng như đo thực tế)
    assert r["fields"]["owner"]["accuracy"] == 1.0
    d = r["fields"]["due_date"]
    assert d["wrong"] == 0 and d["false_fill"] == 0                    # ngày mơ hồ (vd 11-10-2026) chuyển duyệt, không đoán
