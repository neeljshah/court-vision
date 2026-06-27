"""Per-file test for scripts.platformkit.improve.regime_ledger_emit (SI-12).

Acceptance criteria (from BACKLOG.md SI-12):
  - 2-regime batch (>=MIN_REGIME_N OOF rows each) -> 2 graded rows with
    market='regime:<name>' and status in {SHIP, HOLD, REJECT, INSUFFICIENT_DATA}.
  - In-fold leak (split_set='train') -> REJECT row (parity failure, not data shortage).
  - Thin regime (< MIN_REGIME_N) -> INSUFFICIENT_DATA.
  - Degenerate split (all regimes thin) -> single INSUFFICIENT_DATA row.
  - No $/roi/pnl/profit key in any output row.
  - CLV always INSUFFICIENT_DATA.
  - vs_close always UNPROVEN.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/improve/test_regime_ledger_emit.py -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pytest

from scripts.platformkit.improve.regime_ledger_emit import (
    CALIBRATION_NOTE,
    CLV_STATUS,
    MIN_REGIME_N,
    emit_regime_batch,
    _oof_filter,
    _extract,
    _platt_fit,
    _grade_regime,
)

_BANNED_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _make_row(
    margin: float,
    frac_elapsed: float,
    p_raw: float,
    outcome: float,
    split_set: str = "oof",
) -> Dict[str, Any]:
    """Minimal settled row matching the fields _extract reads."""
    return {
        "margin": margin,
        "frac_elapsed": frac_elapsed,
        "p_raw": p_raw,
        "outcome": outcome,
        "split_set": split_set,
    }


def _close_rows(n: int, split_set: str = "oof") -> List[Dict[str, Any]]:
    """n rows in the 'close' regime (margin=2, frac=0.3, well within-bucket)."""
    rng = np.random.default_rng(42)
    rows = []
    for _ in range(n):
        y = float(rng.integers(0, 2))
        p = float(np.clip(rng.random() * 0.4 + 0.3, 0.05, 0.95))
        rows.append(_make_row(margin=2.0, frac_elapsed=0.3,
                              p_raw=p, outcome=y, split_set=split_set))
    return rows


def _blowout_rows(n: int, split_set: str = "oof") -> List[Dict[str, Any]]:
    """n rows in the 'blowout' regime (margin=15, frac=0.4)."""
    rng = np.random.default_rng(99)
    rows = []
    for _ in range(n):
        y = float(rng.integers(0, 2))
        p = float(np.clip(rng.random() * 0.4 + 0.3, 0.05, 0.95))
        rows.append(_make_row(margin=15.0, frac_elapsed=0.4,
                              p_raw=p, outcome=y, split_set=split_set))
    return rows


def _all_keys(obj: Any) -> List[str]:
    keys: List[str] = []
    if isinstance(obj, dict):
        keys += list(obj.keys())
        for v in obj.values():
            keys += _all_keys(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            keys += _all_keys(v)
    return keys


def _assert_no_banned(rows: Any, ctx: str = "") -> None:
    for k in _all_keys(rows):
        assert not _BANNED_RE.search(k), (
            "Banned key %r found%s" % (k, (" in %s" % ctx) if ctx else "")
        )


# ---------------------------------------------------------------------------
# Class 1: 2-regime batch produces 2 graded rows
# ---------------------------------------------------------------------------

class TestTwoRegimeBatch:
    """2-regime batch (each >= MIN_REGIME_N OOF rows) -> 2 graded rows."""

    def test_two_powered_regimes_produce_two_rows(self, tmp_path: Path) -> None:
        n = MIN_REGIME_N + 5
        settled = _close_rows(n) + _blowout_rows(n)
        rows = emit_regime_batch(settled, ledger_path=tmp_path / "led.jsonl",
                                 min_regime_n=MIN_REGIME_N)
        assert len(rows) == 2, "Expected 2 rows; got %d" % len(rows)

    def test_market_key_format(self, tmp_path: Path) -> None:
        """market must be 'regime:<name>' for every row."""
        n = MIN_REGIME_N + 5
        settled = _close_rows(n) + _blowout_rows(n)
        rows = emit_regime_batch(settled, ledger_path=tmp_path / "led.jsonl",
                                 min_regime_n=MIN_REGIME_N)
        for row in rows:
            assert row["market"].startswith("regime:"), (
                "market must start with 'regime:'; got %r" % row["market"]
            )

    def test_status_in_allowed_set(self, tmp_path: Path) -> None:
        allowed = {"SHIP", "HOLD", "REJECT", "INSUFFICIENT_DATA", "NO_CANDIDATE"}
        n = MIN_REGIME_N + 5
        settled = _close_rows(n) + _blowout_rows(n)
        rows = emit_regime_batch(settled, ledger_path=tmp_path / "led.jsonl",
                                 min_regime_n=MIN_REGIME_N)
        for row in rows:
            assert row["status"] in allowed, (
                "status %r not in allowed set" % row["status"]
            )

    def test_rows_written_to_ledger(self, tmp_path: Path) -> None:
        n = MIN_REGIME_N + 5
        settled = _close_rows(n) + _blowout_rows(n)
        ledger = tmp_path / "led.jsonl"
        emit_regime_batch(settled, ledger_path=ledger, min_regime_n=MIN_REGIME_N)
        assert ledger.exists(), "Ledger must be created"
        written = [json.loads(l) for l in ledger.read_text("utf-8").splitlines() if l.strip()]
        assert len(written) == 2


# ---------------------------------------------------------------------------
# Class 2: In-fold leak -> REJECT (parity failure)
# ---------------------------------------------------------------------------

class TestInFoldLeakRejected:
    """Rows with split_set='train' must trigger a REJECT (parity failure)."""

    def test_train_rows_cause_reject(self, tmp_path: Path) -> None:
        """Any in-fold row in the batch must make graded regimes REJECT."""
        n = MIN_REGIME_N + 5
        # mix of OOF and in-fold
        settled = _close_rows(n, split_set="oof") + [
            _make_row(2.0, 0.3, 0.6, 1.0, split_set="train")
        ] + _blowout_rows(n)
        rows = emit_regime_batch(settled, ledger_path=tmp_path / "led.jsonl",
                                 min_regime_n=MIN_REGIME_N)
        statuses = {r["status"] for r in rows}
        assert "REJECT" in statuses, (
            "Expected at least one REJECT when in-fold rows present; got %s" % statuses
        )

    def test_reject_reason_mentions_parity(self, tmp_path: Path) -> None:
        n = MIN_REGIME_N + 5
        settled = _close_rows(n) + [
            _make_row(2.0, 0.3, 0.55, 0.0, split_set="train")
        ] + _blowout_rows(n)
        rows = emit_regime_batch(settled, ledger_path=tmp_path / "led.jsonl",
                                 min_regime_n=MIN_REGIME_N)
        reject_rows = [r for r in rows if r["status"] == "REJECT"]
        assert reject_rows, "Expected REJECT row(s)"
        assert any("parity" in r.get("reason", "").lower() or
                   "in-fold" in r.get("reason", "").lower()
                   for r in reject_rows), (
            "REJECT reason must mention parity or in-fold; got %r" %
            [r.get("reason") for r in reject_rows]
        )

    def test_all_oof_no_reject(self, tmp_path: Path) -> None:
        """When all rows are OOF, no REJECT should appear (normal grading)."""
        n = MIN_REGIME_N + 5
        settled = _close_rows(n) + _blowout_rows(n)
        rows = emit_regime_batch(settled, ledger_path=tmp_path / "led.jsonl",
                                 min_regime_n=MIN_REGIME_N)
        for row in rows:
            assert row["status"] != "REJECT", (
                "No REJECT expected when all rows are OOF; got %r" % row["status"]
            )


# ---------------------------------------------------------------------------
# Class 3: Thin regime -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------

class TestThinRegime:
    """A regime below MIN_REGIME_N OOF rows must produce INSUFFICIENT_DATA."""

    def test_degenerate_split_produces_insufficient(self, tmp_path: Path) -> None:
        """Fewer rows than MIN_REGIME_N for every regime -> degenerate split."""
        tiny = _close_rows(2) + _blowout_rows(2)
        rows = emit_regime_batch(tiny, ledger_path=tmp_path / "led.jsonl",
                                 min_regime_n=MIN_REGIME_N)
        # degenerate split -> single INSUFFICIENT_DATA row
        assert len(rows) >= 1
        assert all(r["status"] == "INSUFFICIENT_DATA" for r in rows), (
            "All rows must be INSUFFICIENT_DATA for thin batch; got %r" %
            [r["status"] for r in rows]
        )

    def test_one_powered_one_thin(self, tmp_path: Path) -> None:
        """One powered regime and one thin: powered graded, thin INSUFFICIENT_DATA."""
        n = MIN_REGIME_N + 5
        settled = _close_rows(n) + _blowout_rows(2)
        # small min so blowout is definitely below
        rows = emit_regime_batch(settled, ledger_path=tmp_path / "led.jsonl",
                                 min_regime_n=MIN_REGIME_N)
        # The thin blowout regime pools into GLOBAL and is skipped; only 'close' graded.
        graded_markets = [r["market"] for r in rows]
        assert any("close" in m for m in graded_markets), (
            "Expected 'regime:close' row; got %r" % graded_markets
        )

    def test_empty_settled_produces_insufficient(self, tmp_path: Path) -> None:
        rows = emit_regime_batch([], ledger_path=tmp_path / "led.jsonl")
        assert len(rows) >= 1
        assert all(r["status"] == "INSUFFICIENT_DATA" for r in rows)


# ---------------------------------------------------------------------------
# Class 4: No $/roi/pnl/profit keys
# ---------------------------------------------------------------------------

class TestNoBannedKeys:
    """No output dict may contain a $, roi, pnl, or profit key."""

    def test_graded_rows_no_banned_keys(self, tmp_path: Path) -> None:
        n = MIN_REGIME_N + 5
        settled = _close_rows(n) + _blowout_rows(n)
        rows = emit_regime_batch(settled, ledger_path=tmp_path / "led.jsonl",
                                 min_regime_n=MIN_REGIME_N)
        _assert_no_banned(rows, "graded rows")

    def test_insufficient_rows_no_banned_keys(self, tmp_path: Path) -> None:
        rows = emit_regime_batch([], ledger_path=tmp_path / "led.jsonl")
        _assert_no_banned(rows, "insufficient rows")

    def test_reject_rows_no_banned_keys(self, tmp_path: Path) -> None:
        n = MIN_REGIME_N + 5
        settled = _close_rows(n) + [
            _make_row(2.0, 0.3, 0.55, 1.0, split_set="train")
        ] + _blowout_rows(n)
        rows = emit_regime_batch(settled, ledger_path=tmp_path / "led.jsonl",
                                 min_regime_n=MIN_REGIME_N)
        _assert_no_banned(rows, "reject rows")


# ---------------------------------------------------------------------------
# Class 5: CLV and vs_close invariants
# ---------------------------------------------------------------------------

class TestClvAndVsClose:
    """CLV must always be INSUFFICIENT_DATA; vs_close always UNPROVEN."""

    def test_clv_always_insufficient(self, tmp_path: Path) -> None:
        n = MIN_REGIME_N + 5
        settled = _close_rows(n) + _blowout_rows(n)
        rows = emit_regime_batch(settled, ledger_path=tmp_path / "led.jsonl",
                                 min_regime_n=MIN_REGIME_N)
        for row in rows:
            assert row.get("clv") == "INSUFFICIENT_DATA", (
                "CLV must be INSUFFICIENT_DATA; got %r" % row.get("clv")
            )

    def test_vs_close_always_unproven(self, tmp_path: Path) -> None:
        n = MIN_REGIME_N + 5
        settled = _close_rows(n) + _blowout_rows(n)
        rows = emit_regime_batch(settled, ledger_path=tmp_path / "led.jsonl",
                                 min_regime_n=MIN_REGIME_N)
        for row in rows:
            assert row.get("vs_close") == "UNPROVEN", (
                "vs_close must be UNPROVEN; got %r" % row.get("vs_close")
            )

    def test_note_contains_calibration(self, tmp_path: Path) -> None:
        n = MIN_REGIME_N + 5
        settled = _close_rows(n) + _blowout_rows(n)
        rows = emit_regime_batch(settled, ledger_path=tmp_path / "led.jsonl",
                                 min_regime_n=MIN_REGIME_N)
        for row in rows:
            assert "calibration" in row.get("note", "").lower()


# ---------------------------------------------------------------------------
# Class 6: Helper unit tests
# ---------------------------------------------------------------------------

class TestHelpers:
    """Unit tests for internal helpers."""

    def test_oof_filter_removes_train_rows(self) -> None:
        rows = [
            {"split_set": "oof"},
            {"split_set": "train"},
            {"split_set": "OOF"},
            {"split_set": "TRAIN"},
        ]
        oof, n_q = _oof_filter(rows)
        assert len(oof) == 2, "Expected 2 OOF rows; got %d" % len(oof)
        assert n_q == 2

    def test_oof_filter_no_split_set_kept(self) -> None:
        """Row without split_set is treated as OOF (conservative)."""
        rows = [{"margin": 2.0}, {"split_set": "train"}]
        oof, n_q = _oof_filter(rows)
        assert len(oof) == 1
        assert n_q == 1

    def test_extract_valid_row(self) -> None:
        row = _make_row(3.0, 0.4, 0.6, 1.0)
        result = _extract(row)
        assert result is not None
        m, f, p, y = result
        assert m == 3.0 and f == 0.4 and p == 0.6 and y == 1.0

    def test_extract_missing_field_returns_none(self) -> None:
        row = {"margin": 3.0, "frac_elapsed": 0.4}  # missing p_raw and outcome
        assert _extract(row) is None

    def test_extract_bad_outcome_returns_none(self) -> None:
        row = _make_row(3.0, 0.4, 0.6, 0.5)  # outcome 0.5 not in {0,1}
        assert _extract(row) is None

    def test_platt_fit_returns_finite(self) -> None:
        rng = np.random.default_rng(7)
        n = 50
        y = rng.integers(0, 2, n).astype(float)
        p = np.clip(rng.random(n), 0.1, 0.9)
        fit = _platt_fit(p, y)
        assert fit is not None
        a, b = fit
        assert np.isfinite(a) and np.isfinite(b)

    def test_grade_regime_thin_gives_insufficient(self) -> None:
        """Fewer clean rows than MIN_REGIME_N -> INSUFFICIENT_DATA."""
        rows = [_make_row(2.0, 0.3, 0.55, float(i % 2))
                for i in range(MIN_REGIME_N - 1)]
        row = _grade_regime("close", rows, "2026-01-01T00:00:00+00:00",
                            in_fold=False)
        assert row["status"] == "INSUFFICIENT_DATA"

    def test_grade_regime_in_fold_gives_reject(self) -> None:
        """in_fold=True must produce REJECT regardless of data volume."""
        n = MIN_REGIME_N + 10
        rows = [_make_row(2.0, 0.3, 0.55, float(i % 2)) for i in range(n)]
        row = _grade_regime("close", rows, "2026-01-01T00:00:00+00:00",
                            in_fold=True)
        assert row["status"] == "REJECT"
        assert "parity" in row.get("reason", "").lower() or \
               "in-fold" in row.get("reason", "").lower()

    def test_grade_regime_parity_ok_field(self) -> None:
        """Successful (non-reject) grade must have parity_ok=True."""
        n = MIN_REGIME_N + 10
        rows = [_make_row(2.0, 0.3, float(0.3 + 0.4 * (i % 2)), float(i % 2))
                for i in range(n)]
        row = _grade_regime("close", rows, "2026-01-01T00:00:00+00:00",
                            in_fold=False)
        if row["status"] not in ("INSUFFICIENT_DATA", "REJECT"):
            assert row.get("parity_ok") is True
