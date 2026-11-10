"""Khóa chất lượng pipeline: không có lỗi im lặng trên dữ liệu mẫu và đúng trên mọi seed.

Lưu ý: đây là kiểm tra hồi quy (regression) trên dữ liệu tổng hợp, không phải bằng chứng tổng quát hóa."""
import pytest

from app.scripts.evaluate_normalization import evaluate
from app.scripts.generate_sample_data import main as generate


@pytest.mark.parametrize("seed", [1, 42, 2026])
def test_no_silent_errors_on_synthetic_data(tmp_path, seed):
    generate(str(tmp_path), seed)
    rep = evaluate(tmp_path)
    for fld, s in rep["fields"].items():
        assert s["silent_errors"] == 0, (seed, fld, s)
    assert rep["duplicates"]["recall"] == 1.0 and rep["duplicates"]["precision"] == 1.0
    assert rep["records"]["recall"] == 1.0 and rep["records"]["precision"] == 1.0
