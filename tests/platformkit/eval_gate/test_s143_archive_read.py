"""S143: an archived cluster id containing '#' must survive the read in every requote reader.

Run: python -m pytest tests/platformkit/eval_gate/test_s143_archive_read.py -q
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.platformkit.eval_gate.archive_read import read_series

_MODULES = ("s106_requote.py", "s121_requote.py", "tick_informative.py")
_SRC = Path(__file__).resolve().parents[3] / "scripts" / "platformkit" / "eval_gate"

_ROWS = "cluster,y,loss\nmlb:KXMLBGAME-26JUL051230NYMATL#1,0.0,0.25\nmlb:KXMLBGAME-26JUL051230NYMATL#2,1.0,0.5\n"


def test_hash_in_a_cluster_id_survives_the_read(tmp_path):
    """The S143 defect itself: comment='#' truncated the row and NaN'd every loss."""
    path = tmp_path / "series.csv"
    path.write_text(_ROWS, encoding="utf-8")
    frame = read_series(path)
    assert list(frame.columns) == ["cluster", "y", "loss"]
    assert frame["loss"].isna().sum() == 0
    assert frame["cluster"].nunique() == 2
    assert frame["cluster"].iloc[0].endswith("#1")
    # the old behaviour, kept here as the contrast this test exists to prevent
    assert pd.read_csv(path, comment="#")["loss"].isna().all()


def test_a_leading_prereg_seal_line_is_still_skipped(tmp_path):
    """Two archives carry a `# prereg_sha256=... k_launch=...` HEADER; only leading '#' skips."""
    path = tmp_path / "sealed.csv"
    path.write_text("# prereg_sha256=abc k_launch=18\n" + _ROWS, encoding="utf-8")
    frame = read_series(path)
    assert list(frame.columns) == ["cluster", "y", "loss"]
    assert len(frame) == 2 and frame["loss"].isna().sum() == 0
    assert frame["cluster"].iloc[1].endswith("#2")


def test_no_requote_reader_reads_an_archive_with_comment_hash():
    """A5: the three readers named by S143 must route archive reads through read_series."""
    for name in _MODULES:
        assert 'comment="#"' not in (_SRC / name).read_text(encoding="utf-8"), name
