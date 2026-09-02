"""Per-file tests for safe_parquet_write (S95 write guard).

  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/ops/test_safe_parquet_write.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.ops.safe_parquet_write import (
    ShrinkRefused,
    write_parquet_atomic,
)


def _df(n: int) -> pd.DataFrame:
    return pd.DataFrame({"event_id": [str(i) for i in range(n)], "v": list(range(n))})


def test_grow_allowed(tmp_path):
    out = tmp_path / "box.parquet"
    write_parquet_atomic(_df(2), out)
    write_parquet_atomic(_df(5), out)
    assert len(pd.read_parquet(out)) == 5


def test_equal_row_count_allowed(tmp_path):
    """A re-run with corrected values but the same key count must still land."""
    out = tmp_path / "box.parquet"
    write_parquet_atomic(_df(3), out)
    same = _df(3)
    same["v"] = [9, 9, 9]
    write_parquet_atomic(same, out)
    assert list(pd.read_parquet(out)["v"]) == [9, 9, 9]


def test_shrink_refused_and_file_untouched(tmp_path):
    """The S91 shape: a 2-row batch must not replace a 20-row corpus."""
    out = tmp_path / "box.parquet"
    write_parquet_atomic(_df(20), out)
    with pytest.raises(ShrinkRefused):
        write_parquet_atomic(_df(2), out)
    assert len(pd.read_parquet(out)) == 20


def test_shrink_allowed_when_explicit(tmp_path):
    out = tmp_path / "box.parquet"
    write_parquet_atomic(_df(20), out)
    write_parquet_atomic(_df(2), out, allow_shrink=True)
    assert len(pd.read_parquet(out)) == 2


def test_unreadable_existing_raises_and_never_overwrites(tmp_path):
    """A torn/garbage existing file must raise, NOT be silently replaced."""
    out = tmp_path / "box.parquet"
    out.write_bytes(b"not a parquet at all")
    with pytest.raises(Exception) as exc:
        write_parquet_atomic(_df(3), out)
    assert not isinstance(exc.value, ShrinkRefused)  # the footer read raised
    assert out.read_bytes() == b"not a parquet at all"


def test_failed_write_leaves_no_partial_or_temp(tmp_path):
    """A write that blows up mid-serialisation leaves the target and dir clean."""
    out = tmp_path / "box.parquet"
    write_parquet_atomic(_df(4), out)
    bad = _df(9)
    bad["v"] = [{"a": 1}, 2, 3, 4, 5, 6, 7, 8, 9]  # mixed dict/int -> pyarrow raises
    with pytest.raises(Exception):
        write_parquet_atomic(bad, out)
    assert len(pd.read_parquet(out)) == 4
    assert [p.name for p in tmp_path.iterdir()] == ["box.parquet"]
