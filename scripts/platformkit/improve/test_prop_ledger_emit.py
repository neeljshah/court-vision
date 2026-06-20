"""Per-file test for scripts.platformkit.improve.prop_ledger_emit (SI-04).

Acceptance criteria:
  - MF1 sentinel absent -> NO_CANDIDATE status for every stat
  - Thin stat (< MIN_PROP_N settled rows) -> INSUFFICIENT_DATA
  - Sentinel present + enough data + candidate built -> SHIP or HOLD
  - build_prop_recency_candidate returns None -> NO_CANDIDATE
  - market key is always "prop:<stat>" (lowercase)
  - no $ / roi / pnl / profit key in any output
  - vs_close = "UNPROVEN" always

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/improve/test_prop_ledger_emit.py -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

import numpy as np
import pytest

from scripts.platformkit.improve.prop_ledger_emit import (
    emit_prop_stats,
    MIN_PROP_N,
    CALIBRATION_NOTE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)


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
            "Banned key %r found%s" % (k, (" in " + context) if context else "")
        )


def _make_candidate(n: int = 20) -> Dict[str, Any]:
    """Synthetic candidate dict matching the shape build_prop_recency_candidate returns."""
    rng = np.random.default_rng(0)
    y = (rng.random(n) > 0.5).astype(float).tolist()
    base = np.clip(rng.random(n), 0.1, 0.9).tolist()
    # Candidate slightly better (closer to y)
    cand = [
        float(np.clip(b + 0.06 * (yy - 0.5), 0.01, 0.99))
        for b, yy in zip(base, y)
    ]
    return {
        "base_preds": base,
        "cand_preds": cand,
        "y": y,
        "kind": "prob",
        "fold_results": [{"delta": 0.005, "metric": "brier", "fold_id": 0}],
        "corpora": [],
        "oos_improves": True,
        "n_clean": n,
        "n_quarantined": 0,
        "name": "test_prop_cand",
        "note": "calibration, not edge",
        "vs_close": "UNPROVEN",
        "payload": {
            "family": "platt_prop_recency",
            "a": 1.02,
            "b": -0.01,
            "half_life_days": 30.0,
            "stat": "pts",
            "n_obs": n,
            "note": "calibration, not edge",
        },
    }


# ---------------------------------------------------------------------------
# Class 1: NO_CANDIDATE when sentinel absent (MF1 kill-switch)
# ---------------------------------------------------------------------------


class TestNoCandidateWhenSentinelAbsent:
    """With pipeline sentinel absent, every stat must get NO_CANDIDATE status."""

    def test_single_stat_no_candidate(self, tmp_path: Path) -> None:
        """MF1: build_prop_recency_candidate returns None -> NO_CANDIDATE."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=None,
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=[{"ts": "t", "p0": 0.5, "outcome": 1, "stat": "pts", "player": "x"}] * MIN_PROP_N,
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        assert len(rows) == 1
        assert rows[0]["status"] == "NO_CANDIDATE", (
            "Expected NO_CANDIDATE when sentinel absent (build returns None); got %r"
            % rows[0]["status"]
        )
        _assert_no_banned_keys(rows[0], "single stat no candidate")

    def test_multiple_stats_all_no_candidate(self, tmp_path: Path) -> None:
        """Multiple stats, all returning None -> all NO_CANDIDATE."""
        ledger = tmp_path / "ledger.jsonl"
        settled = [{"ts": "t", "p0": 0.5, "outcome": 1, "stat": "pts", "player": "x"}] * MIN_PROP_N
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=None,
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=settled,
        ):
            rows = emit_prop_stats("nba", ["pts", "reb", "ast"], ledger_path=ledger)
        assert len(rows) == 3
        for row in rows:
            assert row["status"] == "NO_CANDIDATE", (
                "Expected NO_CANDIDATE; got %r for stat=%r" % (row["status"], row["market"])
            )
        _assert_no_banned_keys(rows, "multiple stats no candidate")

    def test_no_candidate_has_reason(self, tmp_path: Path) -> None:
        """NO_CANDIDATE row must carry a reason string."""
        ledger = tmp_path / "ledger.jsonl"
        settled = [{"ts": "t", "p0": 0.5, "outcome": 0, "stat": "reb", "player": "x"}] * MIN_PROP_N
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=None,
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=settled,
        ):
            rows = emit_prop_stats("nba", ["reb"], ledger_path=ledger)
        reason = rows[0].get("reason", "")
        assert isinstance(reason, str) and len(reason) > 5, (
            "NO_CANDIDATE row must have a non-empty reason; got %r" % reason
        )


# ---------------------------------------------------------------------------
# Class 2: INSUFFICIENT_DATA for thin stats
# ---------------------------------------------------------------------------


class TestInsufficientDataThinStat:
    """Fewer than MIN_PROP_N settled observations -> INSUFFICIENT_DATA."""

    def test_zero_settled_rows_insufficient(self, tmp_path: Path) -> None:
        """load_prop_settled returning [] -> INSUFFICIENT_DATA."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=[],
        ):
            rows = emit_prop_stats("nba", ["blk"], ledger_path=ledger)
        assert rows[0]["status"] == "INSUFFICIENT_DATA"
        assert rows[0].get("n", 0) == 0
        _assert_no_banned_keys(rows[0], "zero settled insufficient")

    def test_below_min_n_insufficient(self, tmp_path: Path) -> None:
        """load_prop_settled returning MIN_PROP_N-1 rows -> INSUFFICIENT_DATA."""
        ledger = tmp_path / "ledger.jsonl"
        thin = [{"ts": "t", "p0": 0.5, "outcome": 1, "stat": "stl", "player": "x"}] * (MIN_PROP_N - 1)
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=thin,
        ):
            rows = emit_prop_stats("nba", ["stl"], ledger_path=ledger)
        assert rows[0]["status"] == "INSUFFICIENT_DATA"
        _assert_no_banned_keys(rows[0], "below min_n insufficient")

    def test_insufficient_carries_min_n(self, tmp_path: Path) -> None:
        """INSUFFICIENT_DATA row must carry min_n=MIN_PROP_N."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=[],
        ):
            rows = emit_prop_stats("nba", ["to"], ledger_path=ledger)
        assert rows[0].get("min_n") == MIN_PROP_N

    def test_insufficient_has_reason(self, tmp_path: Path) -> None:
        """INSUFFICIENT_DATA row must carry a reason string."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=[],
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        reason = rows[0].get("reason", "")
        assert isinstance(reason, str) and len(reason) > 5, (
            "INSUFFICIENT_DATA row must have a reason; got %r" % reason
        )


# ---------------------------------------------------------------------------
# Class 3: SHIP / HOLD with a real candidate
# ---------------------------------------------------------------------------


class TestShipHoldWithCandidate:
    """When sentinel present and candidate built -> SHIP or HOLD, not INSUFFICIENT_DATA."""

    def test_good_candidate_ship_or_hold(self, tmp_path: Path) -> None:
        """A well-formed candidate with improving Brier must produce SHIP or HOLD."""
        ledger = tmp_path / "ledger.jsonl"
        cand = _make_candidate(n=MIN_PROP_N + 5)
        settled = [{"ts": "t", "p0": 0.5, "outcome": 1, "stat": "pts", "player": "x"}] * (MIN_PROP_N + 5)
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=cand,
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=settled,
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        assert rows[0]["status"] in {"SHIP", "HOLD"}, (
            "Expected SHIP or HOLD with good candidate; got %r" % rows[0]["status"]
        )
        _assert_no_banned_keys(rows[0], "good candidate row")

    def test_improving_candidate_emits_ship(self, tmp_path: Path) -> None:
        """Candidate with brier_improves=True and positive delta -> status SHIP."""
        ledger = tmp_path / "ledger.jsonl"
        n = MIN_PROP_N + 10
        # Craft y, base, cand so that brier(cand, y) < brier(base, y)
        y = ([1.0] * (n // 2)) + ([0.0] * (n // 2))
        base = [0.5] * n                          # Brier = 0.25
        cand = [0.85] * (n // 2) + [0.15] * (n // 2)  # lower Brier
        cand_dict = {
            **_make_candidate(n),
            "base_preds": base,
            "cand_preds": cand,
            "y": y,
            "oos_improves": True,
            "n_clean": n,
        }
        settled = [{"ts": "t", "p0": 0.5, "outcome": 1, "stat": "pts", "player": "x"}] * n
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=cand_dict,
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=settled,
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        assert rows[0]["status"] == "SHIP", (
            "Expected SHIP for improving candidate; got %r" % rows[0]["status"]
        )

    def test_readout_in_ship_row(self, tmp_path: Path) -> None:
        """SHIP / HOLD rows must carry a readout dict."""
        ledger = tmp_path / "ledger.jsonl"
        n = MIN_PROP_N + 5
        cand = _make_candidate(n)
        settled = [{"ts": "t", "p0": 0.5, "outcome": 1, "stat": "pts", "player": "x"}] * n
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=cand,
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=settled,
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        assert "readout" in rows[0], "SHIP/HOLD row must carry readout"
        assert isinstance(rows[0]["readout"], dict)
        _assert_no_banned_keys(rows[0], "readout in ship row")

    def test_ship_row_written_to_ledger(self, tmp_path: Path) -> None:
        """Emitted rows must be appended to the ledger JSONL file."""
        ledger = tmp_path / "ledger.jsonl"
        n = MIN_PROP_N + 5
        cand = _make_candidate(n)
        settled = [{"ts": "t", "p0": 0.5, "outcome": 1, "stat": "pts", "player": "x"}] * n
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=cand,
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=settled,
        ):
            emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        assert ledger.exists(), "Ledger file must be created after emit"
        written = [
            json.loads(line)
            for line in ledger.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(written) == 1
        _assert_no_banned_keys(written[0], "ledger row on disk")


# ---------------------------------------------------------------------------
# Class 4: market key format
# ---------------------------------------------------------------------------


class TestMarketKeyFormat:
    """market key must always be 'prop:<stat>' (lowercase)."""

    def test_market_key_pts(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=[],
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        assert rows[0]["market"] == "prop:pts"

    def test_market_key_reb(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=[],
        ):
            rows = emit_prop_stats("nba", ["reb"], ledger_path=ledger)
        assert rows[0]["market"] == "prop:reb"

    def test_market_key_uppercase_stat_lowercased(self, tmp_path: Path) -> None:
        """Stat name passed in uppercase must still produce lowercase market key."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=[],
        ):
            rows = emit_prop_stats("nba", ["AST"], ledger_path=ledger)
        assert rows[0]["market"] == "prop:ast", (
            "Expected lowercase market key; got %r" % rows[0]["market"]
        )

    def test_one_row_per_stat(self, tmp_path: Path) -> None:
        """emit_prop_stats must return exactly one row per stat requested."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=[],
        ):
            rows = emit_prop_stats("nba", ["pts", "reb", "ast", "blk", "stl"], ledger_path=ledger)
        assert len(rows) == 5, "Expected 5 rows for 5 stats; got %d" % len(rows)
        markets = [r["market"] for r in rows]
        assert markets == ["prop:pts", "prop:reb", "prop:ast", "prop:blk", "prop:stl"]


# ---------------------------------------------------------------------------
# Class 5: No banned keys + vs_close contract
# ---------------------------------------------------------------------------


class TestContractGuarantees:
    """No $/roi/pnl/profit keys; vs_close=UNPROVEN; calibration note present."""

    def test_no_candidate_no_banned_keys(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=None,
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=[{"ts": "t", "p0": 0.5, "outcome": 1, "stat": "pts", "player": "x"}] * MIN_PROP_N,
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        _assert_no_banned_keys(rows, "no candidate rows")

    def test_insufficient_no_banned_keys(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=[],
        ):
            rows = emit_prop_stats("nba", ["pts", "reb"], ledger_path=ledger)
        _assert_no_banned_keys(rows, "insufficient rows")

    def test_vs_close_always_unproven(self, tmp_path: Path) -> None:
        """vs_close must be UNPROVEN on every row regardless of status."""
        ledger = tmp_path / "ledger.jsonl"
        n = MIN_PROP_N + 5
        cand = _make_candidate(n)
        settled = [{"ts": "t", "p0": 0.5, "outcome": 1, "stat": "pts", "player": "x"}] * n
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.build_prop_recency_candidate",
            return_value=cand,
        ), mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=settled,
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        for row in rows:
            assert row.get("vs_close") == "UNPROVEN", (
                "vs_close must be UNPROVEN; got %r" % row.get("vs_close")
            )

    def test_calibration_note_in_all_rows(self, tmp_path: Path) -> None:
        """Every row must carry the calibration note field."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            return_value=[],
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        for row in rows:
            assert "note" in row
            assert "calibration" in row["note"].lower()

    def test_empty_stat_list_returns_empty(self, tmp_path: Path) -> None:
        """No stats requested -> empty list returned, no crash."""
        ledger = tmp_path / "ledger.jsonl"
        rows = emit_prop_stats("nba", [], ledger_path=ledger)
        assert rows == []

    def test_exception_in_grade_produces_insufficient(self, tmp_path: Path) -> None:
        """If load_prop_settled raises, the row must be INSUFFICIENT_DATA, not raise."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.prop_ledger_emit.load_prop_settled",
            side_effect=RuntimeError("disk error"),
        ):
            rows = emit_prop_stats("nba", ["pts"], ledger_path=ledger)
        assert len(rows) == 1
        assert rows[0]["status"] == "INSUFFICIENT_DATA"
        _assert_no_banned_keys(rows[0], "exception row")
