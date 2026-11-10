"""Đo bộ trích xuất văn bản tự do (luật Pattern vs Gemini) so với ground truth.

Hai bộ dữ liệu:
  standard - báo cáo mẫu câu cố định (luật đọc được hết, dùng làm đối chứng)
  hard     - báo cáo viết nhiều kiểu (luật dự kiến hỏng); xem hard_reports.py
Khớp bản ghi theo CÂU TRÍCH (evidence), không theo tiêu đề, để lỗi đổi tên không làm mất cả bản ghi.
Nhóm kết quả mỗi trường giống evaluate_normalization: correct / routed (chuyển người duyệt) / wrong / false_fill.
'title_lenient' bỏ hậu tố ' #N' (số thứ tự do script sinh) để tách lỗi tên thật khỏi lỗi cắt hậu tố.

Chạy (Pattern, miễn phí):   python -m app.scripts.evaluate_extraction
Chạy cả Gemini (tốn request): python -m app.scripts.evaluate_extraction --gemini [--max-files 6]
"""
import argparse
import json
import random
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from app.scripts.evaluate_normalization import TEXT_FIELDS, _compare, _nfc, _outcome
from app.scripts.generate_sample_data import main as generate
from app.scripts.hard_reports import write_hard_reports
from app.services.extraction.pattern import PatternExtractor
from app.services.mapping.pipeline import normalize_items
from app.services.parsers import parse_file

_SUFFIX = re.compile(r"\s*#\d+\s*$")


def _key(s: str | None) -> str:
    s = _nfc(s) or ""
    s = re.sub(r"^[-•*\s]+", "", s).rstrip(". ").strip()
    return s.casefold()


def evaluate_set(data_dir: Path, truth_files: dict, extractor, max_files: int | None = None) -> dict:
    fields: dict[str, Counter] = defaultdict(Counter)
    tp = pred_n = truth_n = 0
    unmatched_examples = []
    names = [n for n, f in truth_files.items() if f["kind"] == "free_text"][:max_files]
    for name in names:
        f = truth_files[name]
        doc = parse_file(data_dir / name, Path(name).suffix)
        res = normalize_items(doc.records, extractor=extractor)
        got = {_key(i.evidence): i for i in res.items}
        exp = {_key(r["evidence"]): r for r in f["records"]}
        truth_n += len(exp)
        pred_n += len(got)
        tp += len(set(exp) & set(got))
        for k, t in exp.items():
            it = got.get(k)
            if it is None:
                if len(unmatched_examples) < 3:
                    unmatched_examples.append(t["evidence"])
                continue
            flds = [x for x in TEXT_FIELDS if x != "progress" or t["status_normalized"] in ("IN_PROGRESS", "BLOCKED")]
            for fld, o in _compare(it, t, flds).items():
                fields[fld][o] += 1
            fields["title_lenient"][_outcome(_SUFFIX.sub("", _nfc(it.title) or "") or None, _SUFFIX.sub("", _nfc(t["title"]) or ""), False)] += 1
    summary = {}
    for fld, c in fields.items():
        total = sum(c.values())
        summary[fld] = {"total": total, **{k: c.get(k, 0) for k in ("correct", "routed", "wrong", "false_fill")},
                        "accuracy": round(c["correct"] / total, 4) if total else None}
    extra = pred_n - tp
    return {
        "files": len(names),
        "records": {"truth": truth_n, "predicted": pred_n, "matched": tp,
                    "recall": round(tp / truth_n, 4) if truth_n else None,
                    "precision": round(tp / pred_n, 4) if pred_n else None, "extra_items": extra},
        "fields": summary, "missed_examples": unmatched_examples,
    }


def build_data(seed: int, hard_count: int) -> tuple[Path, dict, dict]:
    d = Path(tempfile.mkdtemp(prefix="eih-extract-"))
    generate(str(d), seed)
    std = json.loads((d / "ground_truth.json").read_text(encoding="utf-8"))["files"]
    hard = write_hard_reports(d, random.Random(seed + 1), hard_count)
    return d, std, hard


def to_markdown(title: str, r: dict) -> str:
    rec = r["records"]
    pct = lambda v: "-" if v is None else f"{v:.1%}"  # noqa: E731  (None khi không dự đoán được bản ghi nào)
    lines = [f"### {title} ({r['files']} file)",
             f"Bản ghi: recall {pct(rec['recall'])}, precision {pct(rec['precision'])} "
             f"(khớp {rec['matched']}/{rec['truth']}, thừa {rec['extra_items']})", "",
             "| Trường | Mẫu | Đúng | Chuyển duyệt | Sai im lặng | Bịa | Accuracy |", "|---|---|---|---|---|---|---|"]
    for fld, s in sorted(r["fields"].items()):
        acc = f"{s['accuracy']:.1%}" if s["accuracy"] is not None else "-"
        lines.append(f"| {fld} | {s['total']} | {s['correct']} | {s['routed']} | {s['wrong']} | {s['false_fill']} | {acc} |")
    if r["missed_examples"]:
        lines += ["", "Ví dụ câu bỏ sót:"] + [f"- {x}" for x in r["missed_examples"]]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--hard-count", type=int, default=6)
    ap.add_argument("--max-files", type=int, default=None, help="giới hạn số file mỗi bộ (để giảm số request Gemini)")
    ap.add_argument("--gemini", action="store_true", help="đo thêm Gemini (cần GEMINI_API_KEY, tốn request)")
    ap.add_argument("--json")
    a = ap.parse_args()

    d, std, hard = build_data(a.seed, a.hard_count)
    extractors = [("Pattern (luật)", PatternExtractor())]
    if a.gemini:
        from app.core.config import get_settings
        from app.services.extraction.gemini import GeminiExtractor
        s = get_settings()
        if not s.gemini_api_key:
            raise SystemExit("Chưa có GEMINI_API_KEY trong .env")
        extractors.append((f"Gemini ({s.gemini_model})", GeminiExtractor(s.gemini_api_key, s.gemini_model)))

    report = {}
    for ename, ex in extractors:
        for sname, tf in (("standard", std), ("hard", hard)):
            r = evaluate_set(d, tf, ex, a.max_files)
            report[f"{ename} | {sname}"] = r
            print(to_markdown(f"{ename} - bộ {sname}", r), "\n")
    print(f"Dữ liệu: {d}\nLưu ý: dữ liệu tổng hợp do cùng tác giả sinh ra; đây là so sánh tương đối giữa hai bộ trích xuất, "
          "không phải độ chính xác trên tài liệu thật.")
    if a.json:
        Path(a.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
