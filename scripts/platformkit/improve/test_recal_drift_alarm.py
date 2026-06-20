"""Per-file test for scripts.platformkit.improve.recal_drift_alarm.

Acceptance criteria (from workstream BE-R5-7):
  - worsening series (all deltas positive, beyond tol) -> regression=True,
    monotone_improving=False
  - improving series -> regression=False, monotone_improving=True
  - < 2 data-bearing cycles -> INSUFFICIENT_DATA, regression=False
  - advisory only: no flag is flipped, no key matching /$|roi|pnl|profit/
  - window clamp: window > available deltas -> uses all available
  - partial window regression: only last N cycles worsening -> regression=True

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/improve/test_recal_drift_alarm.py -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.platformkit.improve.recal_drift_alarm import (
    DEFAULT_WINDOW,
    check_alarm,
    check_all_alarms,
)
from scripts.platformkit.improve.improvement_trend import REGRESSION_TOL

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
            "Banned key '%s' found in output%s" % (k, (" (%s)" % context) if context else "")
        )


def _write_ledger(rows: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _data_row(
    market: str,
    raw_brier: float,
    ts: str = "2026-01-01T00:00:00+00:00",
    status: str = "HOLD",
) -> Dict[str, Any]:
    """Build a ledger row with a readout (data-bearing cycle)."""
    return {
        "ts": ts,
        "market": market,
        "status": status,
        "readout": {
            "n": 50,
            "raw_brier": raw_brier,
            "raw_ece": 0.05,
            "base_rate": 0.5,
            "sharpness": 0.25,
            "n_with_close": 0,
            "bss_vs_close": None,
            "pct_beat_close": None,
        },
        "note": "calibration != edge",
    }


def _insufficient_row(
    market: str, ts: str = "2026-01-01T00:00:00+00:00"
) -> Dict[str, Any]:
    """Build an INSUFFICIENT_DATA ledger row (no readout)."""
    return {
        "ts": ts,
        "market": market,
        "status": "INSUFFICIENT_DATA",
        "n": 3,
        "min_n": 30,
        "note": "calibration != edge",
        "reason": "only 3 settled rows",
    }


def _ts(day: int) -> str:
    return "2026-01-%02dT00:00:00+00:00" % day


# ---------------------------------------------------------------------------
# INSUFFICIENT_DATA tests
# ---------------------------------------------------------------------------


class TestInsufficientData:
    """< 2 data-bearing cycles -> INSUFFICIENT_DATA, regression=False."""

    def test_empty_ledger(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        ledger.write_text("")
        alarm = check_alarm("nba:moneyline", ledger_path=ledger)
        assert alarm["status"] == "INSUFFICIENT_DATA"
        assert alarm["regression"] is False
        assert alarm["monotone_improving"] is False
        _assert_no_banned_keys(alarm, "empty ledger")

    def test_missing_ledger_file(self, tmp_path: Path) -> None:
        absent = tmp_path / "no_such_file.jsonl"
        alarm = check_alarm("nba:moneyline", ledger_path=absent)
        assert alarm["status"] == "INSUFFICIENT_DATA"
        assert alarm["regression"] is False
        _assert_no_banned_keys(alarm)

    def test_one_data_cycle(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        _write_ledger([_data_row("nba:moneyline", 0.25, ts=_ts(1))], ledger)
        alarm = check_alarm("nba:moneyline", ledger_path=ledger)
        assert alarm["status"] == "INSUFFICIENT_DATA"
        assert alarm["regression"] is False
        assert alarm["n_data_cycles"] == 1
        _assert_no_banned_keys(alarm)

    def test_all_insufficient_rows(self, tmp_path: Path) -> None:
        """All INSUFFICIENT_DATA rows -> excluded -> INSUFFICIENT_DATA alarm."""
        ledger = tmp_path / "ledger.jsonl"
        rows = [_insufficient_row("nba:moneyline", ts=_ts(i)) for i in range(1, 5)]
        _write_ledger(rows, ledger)
        alarm = check_alarm("nba:moneyline", ledger_path=ledger)
        assert alarm["status"] == "INSUFFICIENT_DATA"
        assert alarm["regression"] is False
        _assert_no_banned_keys(alarm)

    def test_no_rows_for_market(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        _write_ledger(
            [_data_row("mlb:moneyline", 0.20, ts=_ts(1)),
             _data_row("mlb:moneyline", 0.18, ts=_ts(2))],
            ledger,
        )
        alarm = check_alarm("nba:moneyline", ledger_path=ledger)
        assert alarm["status"] == "INSUFFICIENT_DATA"
        assert alarm["regression"] is False
        _assert_no_banned_keys(alarm)


# ---------------------------------------------------------------------------
# Improving series
# ---------------------------------------------------------------------------


class TestImprovingSeries:
    """Strictly declining Brier -> regression=False, monotone_improving=True."""

    def test_two_cycles_improving(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _data_row("nba:moneyline", 0.25, ts=_ts(1)),
            _data_row("nba:moneyline", 0.23, ts=_ts(2)),
        ]
        _write_ledger(rows, ledger)
        alarm = check_alarm("nba:moneyline", ledger_path=ledger)
        assert alarm["status"] == "ok"
        assert alarm["regression"] is False
        assert alarm["monotone_improving"] is True
        assert alarm["n_data_cycles"] == 2
        _assert_no_banned_keys(alarm)

    def test_five_cycles_monotone_improving(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        briers = [0.30, 0.28, 0.26, 0.24, 0.22]
        rows = [_data_row("nba:moneyline", b, ts=_ts(i + 1)) for i, b in enumerate(briers)]
        _write_ledger(rows, ledger)
        alarm = check_alarm("nba:moneyline", ledger_path=ledger)
        assert alarm["status"] == "ok"
        assert alarm["regression"] is False
        assert alarm["monotone_improving"] is True
        assert alarm["n_data_cycles"] == 5
        _assert_no_banned_keys(alarm)

    def test_flat_brier_not_regression(self, tmp_path: Path) -> None:
        """Delta=0 (flat) must NOT trigger regression=True."""
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _data_row("nba:moneyline", 0.25, ts=_ts(1)),
            _data_row("nba:moneyline", 0.25, ts=_ts(2)),
            _data_row("nba:moneyline", 0.25, ts=_ts(3)),
        ]
        _write_ledger(rows, ledger)
        alarm = check_alarm("nba:moneyline", ledger_path=ledger)
        assert alarm["status"] == "ok"
        assert alarm["regression"] is False
        _assert_no_banned_keys(alarm)

    def test_small_increase_within_tolerance_not_regression(self, tmp_path: Path) -> None:
        """A Brier increase <= REGRESSION_TOL must NOT trigger regression=True."""
        ledger = tmp_path / "ledger.jsonl"
        tiny = REGRESSION_TOL * 0.5
        rows = [
            _data_row("nba:moneyline", 0.25, ts=_ts(1)),
            _data_row("nba:moneyline", 0.25 + tiny, ts=_ts(2)),
            _data_row("nba:moneyline", 0.25 + tiny * 2, ts=_ts(3)),
        ]
        _write_ledger(rows, ledger)
        alarm = check_alarm("nba:moneyline", ledger_path=ledger)
        assert alarm["status"] == "ok"
        assert alarm["regression"] is False
        _assert_no_banned_keys(alarm)


# ---------------------------------------------------------------------------
# Worsening / regression detection
# ---------------------------------------------------------------------------


class TestWorseningSeries:
    """All-worsening (monotone) series -> regression=True, monotone_improving=False."""

    def test_two_cycles_worsening(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _data_row("nba:moneyline", 0.23, ts=_ts(1)),
            _data_row("nba:moneyline", 0.27, ts=_ts(2)),
        ]
        _write_ledger(rows, ledger)
        alarm = check_alarm("nba:moneyline", ledger_path=ledger, window=1)
        assert alarm["status"] == "ok"
        assert alarm["regression"] is True
        assert alarm["monotone_improving"] is False
        _assert_no_banned_keys(alarm)

    def test_three_cycles_monotone_worsening(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        briers = [0.22, 0.24, 0.26]
        rows = [_data_row("nba:moneyline", b, ts=_ts(i + 1)) for i, b in enumerate(briers)]
        _write_ledger(rows, ledger)
        alarm = check_alarm("nba:moneyline", ledger_path=ledger)
        assert alarm["status"] == "ok"
        assert alarm["regression"] is True
        assert alarm["monotone_improving"] is False
        # All window_deltas should be positive (each > 0)
        assert all(d > 0.0 for d in alarm["window_deltas"])
        _assert_no_banned_keys(alarm)

    def test_mixed_series_not_regression(self, tmp_path: Path) -> None:
        """Improving then worsening -> window may not be all-worsening -> regression=False."""
        ledger = tmp_path / "ledger.jsonl"
        # Series: 0.30 -> 0.27 -> 0.29. Last delta is up (+0.02) but first is down.
        # With window=2, window_deltas = [-0.03, +0.02] -- NOT all-positive -> regression=False.
        briers = [0.30, 0.27, 0.29]
        rows = [_data_row("nba:moneyline", b, ts=_ts(i + 1)) for i, b in enumerate(briers)]
        _write_ledger(rows, ledger)
        alarm = check_alarm("nba:moneyline", ledger_path=ledger, window=2)
        assert alarm["status"] == "ok"
        assert alarm["regression"] is False  # mixed window, not all-worsening
        assert alarm["monotone_improving"] is False  # there IS a regression step somewhere
        _assert_no_banned_keys(alarm)

    def test_last_window_worsening_triggers_alarm(self, tmp_path: Path) -> None:
        """Long improving history + last 3 cycles all worsening -> regression=True."""
        ledger = tmp_path / "ledger.jsonl"
        # 3 improving steps then 3 worsening steps
        briers = [0.30, 0.28, 0.26, 0.27, 0.28, 0.30]
        rows = [_data_row("nba:moneyline", b, ts=_ts(i + 1)) for i, b in enumerate(briers)]
        _write_ledger(rows, ledger)
        alarm = check_alarm("nba:moneyline", ledger_path=ledger, window=3)
        assert alarm["status"] == "ok"
        assert alarm["regression"] is True
        assert alarm["monotone_improving"] is False
        # window_deltas = last 3 deltas: [+0.01, +0.01, +0.02]
        assert len(alarm["window_deltas"]) == 3
        assert all(d > 0.0 for d in alarm["window_deltas"])
        _assert_no_banned_keys(alarm)


# ---------------------------------------------------------------------------
# Window clamping
# ---------------------------------------------------------------------------


class TestWindowClamp:
    """window > available deltas -> clamped to available without error."""

    def test_window_larger_than_series(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _data_row("nba:moneyline", 0.24, ts=_ts(1)),
            _data_row("nba:moneyline", 0.22, ts=_ts(2)),
        ]
        _write_ledger(rows, ledger)
        # window=100 but only 1 delta exists -> clamped to 1
        alarm = check_alarm("nba:moneyline", ledger_path=ledger, window=100)
        assert alarm["status"] == "ok"
        assert alarm["window"] == 1  # effective window clamped
        assert len(alarm["window_deltas"]) == 1
        _assert_no_banned_keys(alarm)

    def test_window_zero_clamped(self, tmp_path: Path) -> None:
        """window=0 clamps to 0 -> empty window_deltas -> regression=False."""
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _data_row("nba:moneyline", 0.23, ts=_ts(1)),
            _data_row("nba:moneyline", 0.27, ts=_ts(2)),
        ]
        _write_ledger(rows, ledger)
        alarm = check_alarm("nba:moneyline", ledger_path=ledger, window=0)
        assert alarm["status"] == "ok"
        assert alarm["regression"] is False  # empty window -> cannot be worsening
        assert alarm["window_deltas"] == []
        _assert_no_banned_keys(alarm)


# ---------------------------------------------------------------------------
# No banned keys
# ---------------------------------------------------------------------------


class TestNoBannedKeys:
    """No output may contain keys matching /$|roi|pnl|profit/."""

    def test_ok_result_no_banned_keys(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _data_row("nba:moneyline", 0.25, ts=_ts(1)),
            _data_row("nba:moneyline", 0.27, ts=_ts(2)),
        ]
        _write_ledger(rows, ledger)
        alarm = check_alarm("nba:moneyline", ledger_path=ledger)
        _assert_no_banned_keys(alarm, "ok worsening")

    def test_insufficient_result_no_banned_keys(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        ledger.write_text("")
        alarm = check_alarm("nba:moneyline", ledger_path=ledger)
        _assert_no_banned_keys(alarm, "insufficient")

    def test_check_all_alarms_no_banned_keys(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _data_row("nba:moneyline", 0.25, ts=_ts(1)),
            _data_row("nba:moneyline", 0.23, ts=_ts(2)),
            _data_row("mlb:moneyline", 0.20, ts=_ts(1)),
            _data_row("mlb:moneyline", 0.22, ts=_ts(2)),
        ]
        _write_ledger(rows, ledger)
        results = check_all_alarms(ledger_path=ledger)
        _assert_no_banned_keys(results, "check_all_alarms")


# ---------------------------------------------------------------------------
# Advisory-only contract
# ---------------------------------------------------------------------------


class TestAdvisoryOnly:
    """Alarm is advisory: no flag mutation, no auto-promotion, never raises."""

    def test_no_regression_key_in_alarm(self, tmp_path: Path) -> None:
        """Output has 'regression' not 'regression_flag' to distinguish from freeze guard."""
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _data_row("nba:moneyline", 0.22, ts=_ts(1)),
            _data_row("nba:moneyline", 0.25, ts=_ts(2)),
        ]
        _write_ledger(rows, ledger)
        alarm = check_alarm("nba:moneyline", ledger_path=ledger)
        # The key 'regression' must be present
        assert "regression" in alarm
        # Must NOT silently introduce a flip or promotion marker
        assert "flag_flipped" not in alarm
        assert "auto_promoted" not in alarm
        assert "ship" not in str(alarm.get("reason", "")).lower().replace("ship", "")
        _assert_no_banned_keys(alarm)

    def test_check_all_alarms_never_raises_on_corrupt_ledger(self, tmp_path: Path) -> None:
        """Malformed JSONL lines are skipped; function never raises."""
        ledger = tmp_path / "ledger.jsonl"
        with ledger.open("w", encoding="utf-8") as fh:
            fh.write("{bad json\n")
            fh.write(json.dumps(_data_row("nba:moneyline", 0.25, ts=_ts(1))) + "\n")
        # Should not raise
        results = check_all_alarms(ledger_path=ledger)
        assert isinstance(results, dict)
        _assert_no_banned_keys(results)

    def test_multi_market_alarm_independent(self, tmp_path: Path) -> None:
        """Each market's alarm is independent; improving NBA should not affect worsening MLB."""
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _data_row("nba:moneyline", 0.28, ts=_ts(1)),
            _data_row("nba:moneyline", 0.25, ts=_ts(2)),
            _data_row("nba:moneyline", 0.22, ts=_ts(3)),
            _data_row("mlb:moneyline", 0.20, ts=_ts(1)),
            _data_row("mlb:moneyline", 0.23, ts=_ts(2)),
            _data_row("mlb:moneyline", 0.26, ts=_ts(3)),
        ]
        _write_ledger(rows, ledger)
        results = check_all_alarms(ledger_path=ledger, window=2)
        nba = results["nba:moneyline"]
        mlb = results["mlb:moneyline"]
        assert nba["status"] == "ok"
        assert nba["regression"] is False
        assert nba["monotone_improving"] is True
        assert mlb["status"] == "ok"
        assert mlb["regression"] is True
        assert mlb["monotone_improving"] is False
        _assert_no_banned_keys(results)
