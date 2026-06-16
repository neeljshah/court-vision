"""Per-file test for forward_capture.archive. Run ONLY this file (full suite freezes).

  cd /c/Users/neelj/nba-ai-system && \
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
  scripts/platformkit/forward_capture/tests/test_archive.py -q

Asserts the load-bearing recorder guarantees: APPEND-ONLY (a prior row is never mutated;
movement is recorded by ADDING captured_at rows) and IDEMPOTENT (a re-archived snapshot
collapses to the FIRST copy, keyed on snapshot_sha). All IO goes to a tmp dir, so the real
data/forward_capture/ corpus is never touched.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))

import pytest  # noqa: E402

from scripts.platformkit.forward_capture.schema import (  # noqa: E402
    OddsSnapshot, snapshot_sha)
from scripts.platformkit.forward_capture import archive as A  # noqa: E402


def _snap(side, price, ts, gid="G1", book="mock", market="ml", sport="nba"):
    return OddsSnapshot(book=book, market=market, sport=sport, game_id=gid,
                        side=side, price=price, captured_at=ts)


_OPEN = [
    _snap("home", 1.91, "2026-01-15T17:00:00+00:00"),
    _snap("away", 1.95, "2026-01-15T17:00:00+00:00"),
]
_CLOSE = [
    _snap("home", 1.83, "2026-01-15T23:00:00+00:00"),
    _snap("away", 2.05, "2026-01-15T23:00:00+00:00"),
]


def test_append_writes_rows(tmp_path):
    shas = A.append_snapshots(_OPEN, base_dir=str(tmp_path))
    assert shas == [snapshot_sha(s) for s in _OPEN]
    got = A.read_archive("nba", base_dir=str(tmp_path))
    assert len(got) == 2
    assert {s.side for s in got} == {"home", "away"}


def test_idempotent_reappend_collapses(tmp_path):
    A.append_snapshots(_OPEN, base_dir=str(tmp_path))
    A.append_snapshots(_OPEN, base_dir=str(tmp_path))   # exact re-archive
    A.append_snapshots(_OPEN, base_dir=str(tmp_path))   # and again
    got = A.read_archive("nba", base_dir=str(tmp_path))
    assert len(got) == 2, "re-archiving identical snapshots must collapse to first copy"


def test_append_only_accrues_movement(tmp_path):
    # a LATER captured_at is a NEW row (movement), not an overwrite of the open.
    A.append_snapshots(_OPEN, base_dir=str(tmp_path))
    A.append_snapshots(_CLOSE, base_dir=str(tmp_path))
    got = A.read_archive("nba", base_dir=str(tmp_path))
    assert len(got) == 4, "a later quote must ACCRUE, never overwrite the earlier one"
    caps = sorted({s.captured_at for s in got})
    assert caps == ["2026-01-15T17:00:00+00:00", "2026-01-15T23:00:00+00:00"]


def test_prior_row_is_immutable(tmp_path):
    # the open home price (1.91) survives byte-for-byte after a later close (1.83) lands.
    A.append_snapshots(_OPEN, base_dir=str(tmp_path))
    A.append_snapshots(_CLOSE, base_dir=str(tmp_path))
    got = A.read_archive("nba", base_dir=str(tmp_path))
    opens = [s for s in got if s.captured_at == "2026-01-15T17:00:00+00:00" and s.side == "home"]
    assert len(opens) == 1 and opens[0].price == 1.91


def test_idempotent_across_mixed_batch(tmp_path):
    # a batch that re-includes an already-archived snapshot keeps exactly one of it.
    A.append_snapshots(_OPEN, base_dir=str(tmp_path))
    A.append_snapshots(_OPEN + _CLOSE, base_dir=str(tmp_path))
    got = A.read_archive("nba", base_dir=str(tmp_path))
    assert len(got) == 4


def test_build_all_line_moves_open_close(tmp_path):
    A.append_snapshots(_OPEN + _CLOSE, base_dir=str(tmp_path))
    moves = A.build_all_line_moves("nba", base_dir=str(tmp_path))
    assert len(moves) == 1
    m = moves[0]
    assert m["open_captured_at"] == "2026-01-15T17:00:00+00:00"
    assert m["close_captured_at"] == "2026-01-15T23:00:00+00:00"
    assert m["close_home_price"] == 1.83 and m["close_away_price"] == 2.05
    assert m["devig_close_prob"] is None, "recorder must NEVER author a probability"
    assert m["n_snapshots"] == 4


def test_validate_rejects_dollar_field(tmp_path):
    # a snapshot carrying a banned $/edge field must be refused (honesty rail, in code).
    from scripts.platformkit.forward_capture.schema import validate_snapshot
    bad = _snap("home", 1.91, "2026-01-15T17:00:00+00:00").as_dict()
    bad["edge"] = 0.05
    with pytest.raises(AssertionError):
        validate_snapshot(bad)


def test_archive_dir_is_under_data_forward_capture():
    # the real (non-overridden) store lives under data/forward_capture/ (gitignored, local).
    p = A._store_path("nba", None)
    assert "forward_capture" in str(p).replace("\\", "/")
    assert str(p).replace("\\", "/").split("forward_capture/")[0].endswith("data/")
