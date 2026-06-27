"""Per-file test for scripts.platformkit.improve.prop_ledger_emit (SI-04).

Acceptance criteria (from BACKLOG.md SI-04):
  - 2-stat batch -> 2 graded rows, market="prop:<stat>" for each.
  - sentinel absent -> NO_CANDIDATE status.
  - thin stat (< MIN_PROP_N) -> INSUFFICIENT_DATA.
  - no $/roi/pnl/profit key in any output row.
  - flag stays OFF (no flag flip in the module).
  - vs_close = "UNPROVEN" always.
  - status in {"SHIP","HOLD","REJECT","INSUFFICIENT_DATA","NO_CANDIDATE"}.
  - rows appended to ledger JSONL.
  - note field carries calibration note.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/improve/test_prop_ledger_emit.py -q
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest import mock

import numpy as np
import pytest

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve.prop_ledger_emit import (
    emit_prop_stats,
    MIN_PROP_N,
    CALIBRATION_NOTE,
    _brier_readout,
    _grade_prop_stat,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)

_VALID_STATUSES = {"SHIP", "HOLD", "REJECT", "INSUFFICIENT_DATA", "NO_CANDIDATE"}


def _all_keys(obj: Any) -> List[str]:
    keys: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_all_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_all_keys(item))
    return keys


def _assert_no_banned_keys(obj: Any, context: str = "") -> None:
    for k in _all_keys(obj):
        assert not _BANNED_KEY_RE.search(k), (
            "Banned key %r found%s" % (k, (" in %s" % context) if context else "")
        )


def _make_candidate(
    n: int = 20, brier_delta: float = 0.01, stat: str = "pts"
) -> Dict[str, Any]:
    """Synthetic candidate matching build_prop_recency_candidate output shape."""
    rng = np.random.default_rng(42)
    y = (rng.random(n) > 0.5).astype(float).tolist()
    base = np.clip(rng.random(n), 0.1, 0.9).tolist()
    # Nudge candidate toward y to ensure brier_delta > 0 when brier_delta param > 0.
    cand = [min(max(b + 0.04 * (yy - 0.5), 0.01), 0.99) for b, yy in zip(base, y)]
    return {
        "base_preds": base,
        "cand_preds": cand,
        "y": y,
        "kind": "prob",
        "fold_results": [{"delta": brier_delta, "metric": "brier", "fold_id": 0}],
        "corpora": [],
        "oos_improves": brier_delta > 0.0,
        "n_clean": n,
        "n_quarantined": 0,
        "stat": stat,
        "name": "test_prop_cand",
        "note": "calibration, not edge",
        "vs_close": "UNPROVEN",
        "payload": {
            "family": "platt_prop_recency",
            "a": 1.02,
            "b": -0.01,
            "half_life_days": 30.0,
            "stat": stat,
            "n_obs": n,
            "note": "calibration, not edge",
        },
    }


def _make_settled_rows(n: int = 20, stat: str = "pts", sport: str = "nba") -> List[Dict]:
    """Synthetic settled prop rows passable to load_prop_settled."""
    rows = []
    for i in range(n):
        rows.append({
            "sport": sport,
            "stat": stat,
            "player": "P%d" % i,
            "p0": 0.45 + 0.04 * (i % 5),
            "outcome": i % 2,
            "ts": "2026-01-%02dT00:00:00+00:00" % ((i % 28) + 1),
        })
    return rows


# ---------------------------------------------------------------------------
# Class 1: 2-stat batch produces 2 rows with correct market keys
# ---------------------------------------------------------------------------


class TestTwoStatBatch:
    """2-stat batch -> 2 graded rows, each with market='prop:<stat>'."""

    def test_two_stats_two_rows(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            side_effect=[_make_candidate(n=20, stat="pts"),
                         _make_candidate(n=20, stat="reb")],
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=_make_settled_rows(n=20),
        ):
            rows = emit_prop_stats("nba", ["pts", "reb"], ledger_path=ledger)
        assert len(rows) == 2, "Expected 2 rows for 2 stats; got %d" % len(rows)

    def test_market_key_format(self, tmp_path: Path) -> None:
        """Each row must carry market='prop:<stat>'."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            side_effect=[_make_candidate(n=20, stat="pts"),
                         _make_candidate(n=20, stat="ast")],
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=_make_settled_rows(n=20),
        ):
            rows = emit_prop_stats("nba", ["pts", "ast"], ledger_path=ledger)
        markets = {r["market"] for r in rows}
        assert "prop:pts" in markets, "Expected market='prop:pts'"
        assert "prop:ast" in markets, "Expected market='prop:ast'"

    def test_two_rows_written_to_ledger(self, tmp_path: Path) -> None:
        """Both rows must be appended to the ledger JSONL."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            side_effect=[_make_candidate(n=20, stat="pts"),
                         _make_candidate(n=20, stat="reb")],
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=_make_settled_rows(n=20),
        ):
            emit_prop_stats("nba", ["pts", "reb"], ledger_path=ledger)
        assert ledger.exists(), "Ledger file must be created"
        written = [
            json.loads(line)
            for line in ledger.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(written) == 2, "Expected 2 rows in ledger; got %d" % len(written)

    def test_returned_rows_match_ledger(self, tmp_path: Path) -> None:
        """Rows returned must match those written to disk."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=_make_candidate(n=20, stat="pts"),
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=_make_settled_rows(n=20),
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        disk = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(disk) == 1
        assert disk[0]["market"] == rows[0]["market"]
        assert disk[0]["status"] == rows[0]["status"]


# ---------------------------------------------------------------------------
# Class 2: Sentinel absent -> NO_CANDIDATE
# ---------------------------------------------------------------------------


class TestSentinelAbsent:
    """MF1 kill-switch: sentinel absent -> build returns None -> NO_CANDIDATE row."""

    def test_no_candidate_when_sentinel_absent(self, tmp_path: Path) -> None:
        """build_prop_recency_candidate returns None (sentinel absent) -> NO_CANDIDATE."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=None,
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=_make_settled_rows(n=20),
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        assert len(rows) == 1
        assert rows[0]["status"] == "NO_CANDIDATE", (
            "Sentinel absent (build returns None) -> NO_CANDIDATE; got %r" % rows[0]["status"]
        )
        assert "reason" in rows[0]
        _assert_no_banned_keys(rows[0], "no-candidate row")

    def test_no_candidate_market_key(self, tmp_path: Path) -> None:
        """NO_CANDIDATE row must still carry the correct market key."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=None,
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=_make_settled_rows(n=20),
        ):
            rows = emit_prop_stats("nba", ["ast"], ledger_path=ledger)
        assert rows[0]["market"] == "prop:ast"

    def test_two_stats_both_no_candidate(self, tmp_path: Path) -> None:
        """2-stat batch with sentinel absent -> both rows NO_CANDIDATE."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=None,
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=_make_settled_rows(n=20),
        ):
            rows = emit_prop_stats("nba", ["pts", "reb"], ledger_path=ledger)
        assert len(rows) == 2
        assert all(r["status"] == "NO_CANDIDATE" for r in rows)


# ---------------------------------------------------------------------------
# Class 3: Thin stat -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------


class TestThinStat:
    """Stats with fewer than MIN_PROP_N settled rows -> INSUFFICIENT_DATA."""

    def test_thin_stat_insufficient(self, tmp_path: Path) -> None:
        """load_prop_settled returns fewer than MIN_PROP_N rows -> INSUFFICIENT_DATA."""
        ledger = tmp_path / "ledger.jsonl"
        thin_rows = _make_settled_rows(n=MIN_PROP_N - 1, stat="blk")
        # build should never be called for thin stat, but patch anyway
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=thin_rows,
        ):
            rows = emit_prop_stats("nba", ["blk"], ledger_path=ledger)
        assert len(rows) == 1
        assert rows[0]["status"] == "INSUFFICIENT_DATA", (
            "Thin stat must produce INSUFFICIENT_DATA; got %r" % rows[0]["status"]
        )
        assert rows[0]["n"] == len(thin_rows)
        _assert_no_banned_keys(rows[0], "thin stat row")

    def test_thin_stat_shows_min_n(self, tmp_path: Path) -> None:
        """INSUFFICIENT_DATA row must include min_n threshold."""
        ledger = tmp_path / "ledger.jsonl"
        thin = _make_settled_rows(n=5, stat="stl")
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=thin,
        ):
            rows = emit_prop_stats("nba", ["stl"], ledger_path=ledger)
        assert rows[0].get("min_n") == MIN_PROP_N

    def test_exact_min_n_not_thin(self, tmp_path: Path) -> None:
        """Exactly MIN_PROP_N rows must NOT be INSUFFICIENT_DATA (thin check)."""
        ledger = tmp_path / "ledger.jsonl"
        ok_rows = _make_settled_rows(n=MIN_PROP_N, stat="pts")
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=ok_rows,
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=_make_candidate(n=MIN_PROP_N, stat="pts"),
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        assert rows[0]["status"] != "INSUFFICIENT_DATA", (
            "Exactly MIN_PROP_N rows must not be thin; got %r" % rows[0]["status"]
        )

    def test_mixed_thin_and_ok(self, tmp_path: Path) -> None:
        """2-stat batch: thin stat -> INSUFFICIENT_DATA, ok stat -> graded."""
        ledger = tmp_path / "ledger.jsonl"

        def _load_side_effect(sport, stat=None):
            if stat == "blk":
                return _make_settled_rows(n=3, stat="blk")
            return _make_settled_rows(n=20, stat=str(stat or "pts"))

        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            side_effect=_load_side_effect,
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=_make_candidate(n=20, stat="pts"),
        ):
            rows = emit_prop_stats("nba", ["blk", "pts"], ledger_path=ledger)
        assert len(rows) == 2
        blk_row = next(r for r in rows if r["market"] == "prop:blk")
        pts_row = next(r for r in rows if r["market"] == "prop:pts")
        assert blk_row["status"] == "INSUFFICIENT_DATA"
        assert pts_row["status"] in _VALID_STATUSES - {"INSUFFICIENT_DATA"}


# ---------------------------------------------------------------------------
# Class 4: No $/roi/pnl/profit keys
# ---------------------------------------------------------------------------


class TestNoBannedKeys:
    """No output row may contain a $ / roi / pnl / profit key."""

    def test_ship_row_no_banned_keys(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=_make_candidate(n=20, stat="pts"),
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=_make_settled_rows(n=20),
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        _assert_no_banned_keys(rows, "SHIP row")

    def test_no_candidate_row_no_banned_keys(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=None,
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=_make_settled_rows(n=20),
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        _assert_no_banned_keys(rows, "NO_CANDIDATE row")

    def test_insufficient_row_no_banned_keys(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=[],
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        _assert_no_banned_keys(rows, "INSUFFICIENT_DATA row")

    def test_batch_no_banned_keys(self, tmp_path: Path) -> None:
        """Batch of 2 stats: neither row may have banned keys."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            side_effect=[_make_candidate(n=20, stat="pts"),
                         _make_candidate(n=20, stat="reb")],
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=_make_settled_rows(n=20),
        ):
            rows = emit_prop_stats("nba", ["pts", "reb"], ledger_path=ledger)
        _assert_no_banned_keys(rows, "2-stat batch")


# ---------------------------------------------------------------------------
# Class 5: Honesty rails (vs_close, note, status values)
# ---------------------------------------------------------------------------


class TestHonestyRails:
    """vs_close always UNPROVEN; note present; status from valid set."""

    def test_vs_close_always_unproven(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=_make_candidate(n=20, stat="pts"),
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=_make_settled_rows(n=20),
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        assert rows[0].get("vs_close") == "UNPROVEN", (
            "vs_close must be UNPROVEN; got %r" % rows[0].get("vs_close")
        )

    def test_note_field_present(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=_make_candidate(n=20, stat="pts"),
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=_make_settled_rows(n=20),
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        assert "note" in rows[0]
        assert "calibration" in rows[0]["note"].lower()

    def test_status_from_valid_set(self, tmp_path: Path) -> None:
        """status must be one of the valid values."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            side_effect=[_make_candidate(n=20, stat="pts"),
                         None,
                         _make_candidate(n=3, stat="blk")],
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            side_effect=[
                _make_settled_rows(n=20, stat="pts"),
                _make_settled_rows(n=20, stat="reb"),
                _make_settled_rows(n=3, stat="blk"),
            ],
        ):
            rows = emit_prop_stats("nba", ["pts", "reb", "blk"], ledger_path=ledger)
        for r in rows:
            assert r["status"] in _VALID_STATUSES, (
                "status %r not in valid set %s" % (r["status"], _VALID_STATUSES)
            )

    def test_no_flag_key_in_rows(self, tmp_path: Path) -> None:
        """No 'flag' key that could be ON should appear in output."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=_make_candidate(n=20, stat="pts"),
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=_make_settled_rows(n=20),
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        # no pipeline_enabled flag should be toggled ON by this module
        for k in _all_keys(rows):
            assert "pipeline_enabled" not in k.lower(), "flag key leaked into output"


# ---------------------------------------------------------------------------
# Class 6: Empty / edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Empty stats list and robustness checks."""

    def test_empty_stats_returns_empty(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = emit_prop_stats("nba", [], ledger_path=ledger)
        assert rows == []

    def test_never_raises(self, tmp_path: Path) -> None:
        """emit_prop_stats must never raise, even when build explodes."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            side_effect=RuntimeError("deliberate build failure"),
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=_make_settled_rows(n=20),
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        # must return without raising; row must be INSUFFICIENT_DATA or NO_CANDIDATE
        assert len(rows) == 1
        assert rows[0]["status"] in {"INSUFFICIENT_DATA", "NO_CANDIDATE"}
        _assert_no_banned_keys(rows[0], "build-explodes row")

    def test_load_prop_settled_raises(self, tmp_path: Path) -> None:
        """If load_prop_settled raises, we still get INSUFFICIENT_DATA, not an exception."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            side_effect=IOError("disk error"),
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        assert len(rows) == 1
        assert rows[0]["status"] == "INSUFFICIENT_DATA"

    def test_ledger_dir_created(self, tmp_path: Path) -> None:
        """Ledger parent directory must be created if it does not exist."""
        ledger = tmp_path / "new_subdir" / "ledger.jsonl"
        assert not ledger.parent.exists()
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=[],
        ):
            emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        assert ledger.parent.exists()


# ---------------------------------------------------------------------------
# Class 7: _brier_readout unit tests
# ---------------------------------------------------------------------------


class TestBrierReadout:
    """Unit tests for the internal _brier_readout helper."""

    def test_basic_shape(self) -> None:
        n = 30
        rng = np.random.default_rng(1)
        y = (rng.random(n) > 0.5).astype(float).tolist()
        base = np.clip(rng.random(n), 0.1, 0.9).tolist()
        cand = np.clip(rng.random(n), 0.1, 0.9).tolist()
        out = _brier_readout(base, cand, y)
        assert "n" in out and out["n"] == n
        assert "base_brier" in out
        assert "cand_brier" in out
        assert "brier_delta" in out
        assert isinstance(out["brier_improves"], bool)

    def test_perfect_cand_improves(self) -> None:
        """Candidate perfectly calibrated vs constant 50% base -> improves."""
        y = [1.0] * 20 + [0.0] * 20
        base = [0.5] * 40
        cand = [0.9] * 20 + [0.1] * 20
        out = _brier_readout(base, cand, y)
        assert out["brier_delta"] > 0.0
        assert out["brier_improves"] is True

    def test_bad_cand_does_not_improve(self) -> None:
        """Candidate far from y vs good base -> does not improve."""
        y = [1.0] * 20 + [0.0] * 20
        base = [0.9] * 20 + [0.1] * 20  # good base
        cand = [0.1] * 20 + [0.9] * 20  # bad candidate
        out = _brier_readout(base, cand, y)
        assert out["brier_improves"] is False
