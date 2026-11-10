"""Đánh giá pipeline chuẩn hóa so với ground_truth.json (đáp án do script sinh dữ liệu tạo ra).

Mỗi giá trị dự đoán thuộc một trong 4 nhóm:
  correct      - đúng đáp án
  routed       - hệ thống KHÔNG tự quyết mà đưa vào hàng chờ duyệt (UNKNOWN / ngày mơ hồ...) khi đáp án có giá trị
  wrong        - sai im lặng (có giá trị nhưng sai, hoặc bỏ sót mà không cảnh báo)
  false_fill   - đáp án trống nhưng hệ thống điền giá trị (bịa)
Chỉ số quan trọng nhất là SILENT ERRORS = wrong + false_fill: lỗi mà con người không có cơ hội chặn.

Lưu ý khi diễn giải: dữ liệu và đáp án đều do cùng một tác giả sinh ra, nên kết quả chứng minh pipeline xử lý đúng các
kiểu lỗi đã biết, KHÔNG chứng minh khả năng tổng quát hóa lên dữ liệu thật. Với dữ liệu thật cần tự gán nhãn một mẫu.

Chạy:  python -m app.scripts.evaluate_normalization [--data DIR] [--seed 42] [--json out.json]
"""
import argparse
import json
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from app.scripts.generate_sample_data import main as generate
from app.services.extraction.pattern import PatternExtractor
from app.services.mapping.pipeline import NormalizedItem, normalize_items
from app.services.parsers import parse_file

TABLE_FIELDS = ("external_id", "title", "owner", "status", "priority", "progress", "due_date")
TEXT_FIELDS = ("title", "owner", "status", "due_date", "progress")  # chỉ những trường thực sự có trong câu báo cáo
NO_VALUE = object()


def _nfc(s):
    return None if s is None else unicodedata.normalize("NFC", " ".join(str(s).split()))


def _outcome(pred, truth, routed: bool) -> str:
    if truth is None:
        return "correct" if pred is None else "false_fill"
    if pred == truth:
        return "correct"
    if pred is None and routed:
        return "routed"
    return "wrong"


def _compare(it: NormalizedItem, t: dict, fields) -> dict[str, str]:
    out = {}
    for f in fields:
        if f == "external_id":
            out[f] = _outcome(it.external_id, _nfc(t["external_id"]), False)
        elif f == "title":
            out[f] = _outcome(_nfc(it.title), _nfc(t["title"]), False)
        elif f == "owner":
            out[f] = _outcome(it.assignee_raw, _nfc(t["owner"]), False)
        elif f == "status":
            pred = it.status.value
            truth = t["status_normalized"]
            out[f] = "correct" if pred == truth else ("routed" if pred == "UNKNOWN" else "wrong")
        elif f == "priority":
            pred, truth = it.priority.value, t["priority_normalized"]
            out[f] = "correct" if pred == truth else ("routed" if pred == "UNKNOWN" else "wrong")
        elif f == "progress":
            truth = None if t["progress"] is None else float(t["progress"])
            out[f] = _outcome(it.progress, truth, "progress" in it.flags)
        elif f == "due_date":
            pred = it.due_date.isoformat() if it.due_date else None
            out[f] = _outcome(pred, t["due_date"], "due_date" in it.flags)
    return out


def evaluate(data_dir: Path) -> dict:
    truth = json.loads((data_dir / "ground_truth.json").read_text(encoding="utf-8"))
    fields: dict[str, Counter] = defaultdict(Counter)
    per_file: dict[str, dict] = {}
    dup = Counter()
    items_tp = items_pred = items_truth = 0

    for name, f in truth["files"].items():
        doc = parse_file(data_dir / name, Path(name).suffix)
        res = normalize_items(doc.records, extractor=PatternExtractor())
        fc: dict[str, Counter] = defaultdict(Counter)

        if f["kind"] == "table":
            exp = {r["row_ref"]: r for r in f["records"]}
            got = {i.row_ref: i for i in res.items}
            items_truth += len(exp)
            items_pred += len(got)
            items_tp += len(set(exp) & set(got))
            for ref, t in exp.items():
                it = got.get(ref)
                if it is None:
                    for fld in TABLE_FIELDS:
                        fc[fld]["wrong"] += 1
                    continue
                if t["external_id"] is None and it.external_id is None:
                    cmp = _compare(it, t, [x for x in TABLE_FIELDS if x != "external_id"])
                else:
                    cmp = _compare(it, t, TABLE_FIELDS)
                for fld, o in cmp.items():
                    fc[fld][o] += 1
            # trùng lặp
            truth_dups = {r["row_ref"] for r in f["records"] if r.get("is_duplicate_of")}
            pred_dups = {i.row_ref for i in res.items if i.duplicate_of}
            dup["tp"] += len(truth_dups & pred_dups)
            dup["fp"] += len(pred_dups - truth_dups)
            dup["fn"] += len(truth_dups - pred_dups)
        else:  # văn bản tự do: khớp theo tiêu đề
            exp = {_nfc(r["title"]): r for r in f["records"]}
            got = {_nfc(i.title): i for i in res.items}
            items_truth += len(exp)
            items_pred += len(got)
            items_tp += len(set(exp) & set(got))
            for title, t in exp.items():
                it = got.get(title)
                if it is None:
                    continue
                flds = [x for x in TEXT_FIELDS if x != "progress" or t["status_normalized"] in ("IN_PROGRESS", "BLOCKED")]
                for fld, o in _compare(it, t, flds).items():
                    fc[fld][o] += 1

        per_file[name] = {k: dict(v) for k, v in fc.items()}
        for k, v in fc.items():
            fields[k].update(v)

    def prf(tp, fp, fn):
        p = tp / (tp + fp) if tp + fp else 1.0
        r = tp / (tp + fn) if tp + fn else 1.0
        return round(p, 4), round(r, 4)

    summary = {}
    for fld, c in fields.items():
        total = sum(c.values())
        summary[fld] = {
            "total": total,
            **{k: c.get(k, 0) for k in ("correct", "routed", "wrong", "false_fill")},
            "accuracy": round(c["correct"] / total, 4) if total else None,
            "silent_errors": c.get("wrong", 0) + c.get("false_fill", 0),
        }
    dp, dr = prf(dup["tp"], dup["fp"], dup["fn"])
    ip, ir = prf(items_tp, items_pred - items_tp, items_truth - items_tp)
    return {
        "fields": summary,
        "duplicates": {"precision": dp, "recall": dr, **{k: dup[k] for k in ("tp", "fp", "fn")}},
        "records": {"precision": ip, "recall": ir, "truth": items_truth, "predicted": items_pred},
        "per_file": per_file,
    }


def to_markdown(r: dict) -> str:
    lines = ["| Trường | Mẫu | Đúng | Chuyển duyệt | Sai im lặng | Bịa | Accuracy |", "|---|---|---|---|---|---|---|"]
    for fld, s in sorted(r["fields"].items()):
        lines.append(f"| {fld} | {s['total']} | {s['correct']} | {s['routed']} | {s['wrong']} | {s['false_fill']} | {s['accuracy']:.1%} |")
    d, rec = r["duplicates"], r["records"]
    lines += ["", f"Phát hiện trùng: precision {d['precision']:.1%}, recall {d['recall']:.1%} (TP {d['tp']}, FP {d['fp']}, FN {d['fn']})",
              f"Trích xuất bản ghi: precision {rec['precision']:.1%}, recall {rec['recall']:.1%} ({rec['predicted']} dự đoán / {rec['truth']} đáp án)"]
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="thư mục chứa ground_truth.json; bỏ trống = tự sinh vào thư mục tạm")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--json", help="ghi báo cáo JSON ra file")
    a = ap.parse_args()
    d = Path(a.data) if a.data else Path(tempfile.mkdtemp(prefix="eih-eval-"))
    if not a.data:
        generate(str(d), a.seed)
    rep = evaluate(d)
    print(to_markdown(rep))
    if a.json:
        Path(a.json).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
