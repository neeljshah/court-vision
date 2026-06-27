r"""tests/platformkit/improve/test_per_market_ledger.py

Acceptance tests for SI-01 per-market recalibration ledger.

Contract verified:
  A. 3-market settled batch -> 3 ledger rows (one per market).
  B. A market under MIN_MARKET_N -> status INSUFFICIENT_DATA.
  C. No key matching /(\$|roi|pnl|profit)/ in ANY row (including nested).

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/improve/test_per_market_ledger.py -q
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.platformkit.improve.per_market_ledger import (
    MIN_MARKET_N,
    CALIBRATION_NOTE,
    PerMarketLedger,
    grade_market_segment,
    record_per_market,
    segment_by_market,
    _assert_no_banned_keys,
    _all_keys,
)
from scripts.platformkit.improve._market_metrics import (
    BRIER_IMPROVE_TOL,
    BRIER_REGRESS_TOL,
    verdict_from_readout,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BANNED_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)


def _make_row(p: float, y: int, market: str, p_close: float | None = None) -> dict:
    """Build a minimal settled row."""
    row = {"p_raw": p, "y": y, "market": market}
    if p_close is not None:
        row["p_close"] = p_close
    return row


def _make_market_rows(n: int, market: str, *, p_val: float = 0.55, y_val: int = 1) -> List[dict]:
    """n identical rows for a market (deterministic)."""
    return [_make_row(p_val, y_val % 2 if i % 2 == 0 else (1 - y_val % 2), market)
            for i in range(n)]


def _make_market_rows_with_close(
    n: int, market: str, *, p_val: float = 0.55, p_close: float = 0.50
) -> List[dict]:
    """n rows with a close price -- alternating outcomes for a realistic base rate."""
    return [
        _make_row(p_val, i % 2, market, p_close=p_close)
        for i in range(n)
    ]


def _no_banned_keys_in_rows(rows: List[dict]) -> bool:
    """True if no banned key found recursively in any row."""
    for row in rows:
        for k in _all_keys(row):
            if BANNED_RE.search(k):
                return False
    return True


# ---------------------------------------------------------------------------
# A: 3-market settled batch -> 3 ledger rows
# ---------------------------------------------------------------------------

class TestThreeMarketBatch:
    """SI-01 acceptance A: 3 distinct markets each above MIN_MARKET_N -> 3 rows."""

    def _build_batch(self) -> List[dict]:
        n = MIN_MARKET_N + 5  # comfortably above threshold
        return (
            _make_market_rows(n, "nba:moneyline")
            + _make_market_rows(n, "mlb:totals")
            + _make_market_rows(n, "prop:pts")
        )

    def test_record_batch_returns_three_rows(self, tmp_path: Path) -> None:
        ledger = PerMarketLedger(tmp_path / "ledger.jsonl")
        rows = ledger.record_batch(self._build_batch())
        assert len(rows) == 3, f"expected 3 ledger rows, got {len(rows)}: {[r['market'] for r in rows]}"

    def test_markets_are_distinct(self, tmp_path: Path) -> None:
        ledger = PerMarketLedger(tmp_path / "ledger.jsonl")
        rows = ledger.record_batch(self._build_batch())
        markets = {r["market"] for r in rows}
        assert markets == {"nba:moneyline", "mlb:totals", "prop:pts"}

    def test_rows_persisted_to_jsonl(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        ledger = PerMarketLedger(path)
        ledger.record_batch(self._build_batch())
        written = [json.loads(l) for l in path.read_text(encoding="utf-8").strip().splitlines()]
        assert len(written) == 3

    def test_each_row_has_status(self, tmp_path: Path) -> None:
        ledger = PerMarketLedger(tmp_path / "ledger.jsonl")
        rows = ledger.record_batch(self._build_batch())
        valid_statuses = {"SHIP", "HOLD", "REJECT", "INSUFFICIENT_DATA"}
        for row in rows:
            assert row.get("status") in valid_statuses, f"bad status in row: {row}"

    def test_above_min_n_rows_have_readout(self, tmp_path: Path) -> None:
        ledger = PerMarketLedger(tmp_path / "ledger.jsonl")
        rows = ledger.record_batch(self._build_batch())
        for row in rows:
            if row["status"] != "INSUFFICIENT_DATA":
                assert "readout" in row, f"missing readout in row: {row}"
                assert "raw_brier" in row["readout"]
                assert "n" in row["readout"]

    def test_note_present_in_each_row(self, tmp_path: Path) -> None:
        ledger = PerMarketLedger(tmp_path / "ledger.jsonl")
        rows = ledger.record_batch(self._build_batch())
        for row in rows:
            assert "note" in row
            assert "calibration" in row["note"].lower()

    def test_rows_for_market_roundtrip(self, tmp_path: Path) -> None:
        ledger = PerMarketLedger(tmp_path / "ledger.jsonl")
        ledger.record_batch(self._build_batch())
        nba_rows = ledger.rows_for_market("nba:moneyline")
        assert len(nba_rows) == 1
        assert nba_rows[0]["market"] == "nba:moneyline"

    def test_bss_computed_when_close_present(self, tmp_path: Path) -> None:
        n = MIN_MARKET_N + 5
        batch = _make_market_rows_with_close(n, "nba:moneyline")
        ledger = PerMarketLedger(tmp_path / "ledger.jsonl")
        rows = ledger.record_batch(batch)
        nba_row = next(r for r in rows if r["market"] == "nba:moneyline")
        assert nba_row["status"] != "INSUFFICIENT_DATA"
        assert nba_row["readout"]["n_with_close"] > 0
        assert nba_row["readout"]["bss_vs_close"] is not None


# ---------------------------------------------------------------------------
# B: under-min-N market -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------

class TestInsufficientData:
    """SI-01 acceptance B: market under MIN_MARKET_N -> status INSUFFICIENT_DATA."""

    def test_under_min_n_returns_insufficient_data(self) -> None:
        n = MIN_MARKET_N - 1
        rows = _make_market_rows(n, "nba:moneyline")
        row = grade_market_segment("nba:moneyline", rows)
        assert row["status"] == "INSUFFICIENT_DATA", f"expected INSUFFICIENT_DATA, got {row['status']}"

    def test_insufficient_data_includes_n(self) -> None:
        n = MIN_MARKET_N - 5
        rows = _make_market_rows(n, "prop:ast")
        row = grade_market_segment("prop:ast", rows)
        assert row["n"] == n

    def test_insufficient_data_no_fabricated_readout(self) -> None:
        rows = _make_market_rows(MIN_MARKET_N - 1, "soccer:totals")
        row = grade_market_segment("soccer:totals", rows)
        assert "readout" not in row, "INSUFFICIENT_DATA row must not contain a readout"

    def test_zero_rows_is_insufficient(self) -> None:
        row = grade_market_segment("nba:moneyline", [])
        assert row["status"] == "INSUFFICIENT_DATA"

    def test_exactly_min_n_not_insufficient(self) -> None:
        rows = _make_market_rows(MIN_MARKET_N, "nba:moneyline")
        row = grade_market_segment("nba:moneyline", rows)
        assert row["status"] != "INSUFFICIENT_DATA", (
            f"exactly MIN_MARKET_N={MIN_MARKET_N} should not be INSUFFICIENT_DATA"
        )

    def test_mixed_batch_thin_market_is_insufficient(self, tmp_path: Path) -> None:
        """A batch where one market is thin: that market -> INSUFFICIENT_DATA."""
        n_full = MIN_MARKET_N + 10
        n_thin = MIN_MARKET_N - 1
        batch = (
            _make_market_rows(n_full, "nba:moneyline")
            + _make_market_rows(n_thin, "nba:props")
        )
        ledger = PerMarketLedger(tmp_path / "ledger.jsonl")
        rows = ledger.record_batch(batch)
        row_by_market = {r["market"]: r for r in rows}
        assert row_by_market["nba:moneyline"]["status"] != "INSUFFICIENT_DATA"
        assert row_by_market["nba:props"]["status"] == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# C: no banned $ / roi / pnl / profit key anywhere
# ---------------------------------------------------------------------------

class TestNoBannedKeys:
    """SI-01 acceptance C: no key matching the banned pattern in any row."""

    def test_no_banned_keys_in_normal_row(self) -> None:
        n = MIN_MARKET_N + 10
        rows = _make_market_rows_with_close(n, "nba:moneyline")
        row = grade_market_segment("nba:moneyline", rows)
        keys = _all_keys(row)
        for k in keys:
            assert not BANNED_RE.search(k), f"banned key found: '{k}'"

    def test_no_banned_keys_in_insufficient_data_row(self) -> None:
        rows = _make_market_rows(MIN_MARKET_N - 1, "mlb:totals")
        row = grade_market_segment("mlb:totals", rows)
        for k in _all_keys(row):
            assert not BANNED_RE.search(k), f"banned key found: '{k}'"

    def test_no_banned_keys_in_batch(self, tmp_path: Path) -> None:
        n = MIN_MARKET_N + 5
        batch = (
            _make_market_rows(n, "nba:moneyline")
            + _make_market_rows(n, "mlb:totals")
            + _make_market_rows(MIN_MARKET_N - 1, "prop:reb")  # thin -> INSUFFICIENT_DATA
        )
        ledger = PerMarketLedger(tmp_path / "ledger.jsonl")
        ledger_rows = ledger.record_batch(batch)
        assert _no_banned_keys_in_rows(ledger_rows), "banned key found in batch ledger rows"

    def test_assert_no_banned_keys_raises_on_dollar(self) -> None:
        with pytest.raises(ValueError, match="Banned key"):
            _assert_no_banned_keys({"market": "nba", "$edge": 0.1})

    def test_assert_no_banned_keys_raises_on_roi(self) -> None:
        with pytest.raises(ValueError, match="Banned key"):
            _assert_no_banned_keys({"market": "nba", "roi": 0.05})

    def test_assert_no_banned_keys_raises_on_pnl(self) -> None:
        with pytest.raises(ValueError, match="Banned key"):
            _assert_no_banned_keys({"market": "nba", "pnl_units": 3.0})

    def test_assert_no_banned_keys_raises_on_profit(self) -> None:
        with pytest.raises(ValueError, match="Banned key"):
            _assert_no_banned_keys({"readout": {"profit_calc": 42}})

    def test_assert_no_banned_keys_passes_clean_row(self) -> None:
        _assert_no_banned_keys({
            "ts": "2026-06-19T00:00:00Z",
            "market": "nba:moneyline",
            "status": "HOLD",
            "note": "calibration != edge",
            "readout": {"n": 45, "raw_brier": 0.23},
        })


# ---------------------------------------------------------------------------
# Additional: segment_by_market
# ---------------------------------------------------------------------------

class TestSegmentByMarket:
    def test_segments_distinct_markets(self) -> None:
        batch = (
            _make_market_rows(5, "nba:moneyline")
            + _make_market_rows(3, "mlb:totals")
        )
        groups = segment_by_market(batch)
        assert set(groups.keys()) == {"nba:moneyline", "mlb:totals"}
        assert len(groups["nba:moneyline"]) == 5
        assert len(groups["mlb:totals"]) == 3

    def test_infers_market_from_sport_field(self) -> None:
        """Row with no 'market' key but 'sport' field -> sport name used as key."""
        batch = [{"p_raw": 0.55, "y": 1, "sport": "tennis"} for _ in range(3)]
        groups = segment_by_market(batch)
        assert "tennis" in groups

    def test_infers_market_from_sport_and_bet_type(self) -> None:
        batch = [
            {"p_raw": 0.55, "y": 1, "sport": "nba", "bet_type": "moneyline"}
        ] * 3
        groups = segment_by_market(batch)
        assert "nba:moneyline" in groups


# ---------------------------------------------------------------------------
# Additional: latest_row_per_market + multi-batch append
# ---------------------------------------------------------------------------

class TestLatestRowAndMultiBatch:
    def test_latest_row_per_market_returns_last_written(self, tmp_path: Path) -> None:
        n = MIN_MARKET_N + 5
        ledger = PerMarketLedger(tmp_path / "ledger.jsonl")
        ledger.record_batch(_make_market_rows(n, "nba:moneyline"), ts="2026-06-18T00:00:00Z")
        ledger.record_batch(_make_market_rows(n, "nba:moneyline"), ts="2026-06-19T00:00:00Z")
        latest = ledger.latest_row_per_market()
        assert latest["nba:moneyline"]["ts"] == "2026-06-19T00:00:00Z"

    def test_multi_batch_accumulates_rows(self, tmp_path: Path) -> None:
        n = MIN_MARKET_N + 5
        ledger = PerMarketLedger(tmp_path / "ledger.jsonl")
        ledger.record_batch(_make_market_rows(n, "nba:moneyline"), ts="2026-06-18T00:00:00Z")
        ledger.record_batch(_make_market_rows(n, "mlb:totals"), ts="2026-06-19T00:00:00Z")
        all_rows = ledger.all_rows()
        assert len(all_rows) == 2

    def test_record_per_market_convenience_fn(self, tmp_path: Path) -> None:
        n = MIN_MARKET_N + 5
        path = tmp_path / "ledger.jsonl"
        batch = _make_market_rows(n, "nba:moneyline")
        rows = record_per_market(batch, ledger_path=path)
        assert len(rows) == 1
        assert rows[0]["market"] == "nba:moneyline"


# ---------------------------------------------------------------------------
# D: controlled verdict direction tests
# ---------------------------------------------------------------------------

class TestVerdictThresholds:
    """SI-01 controlled BSS threshold: SHIP when p_raw beats close, REJECT when worse.

    Uses grade_market_segment (not _verdict_from_readout directly) so we verify
    the full path from settled rows -> status, not just the helper in isolation.
    """

    def _make_bss_rows(
        self,
        n: int,
        market: str,
        p_raw: float,
        p_close: float,
    ) -> List[dict]:
        """Alternating outcomes so base_rate ~0.5, isolating the BSS signal."""
        return [_make_row(p_raw, i % 2, market, p_close=p_close) for i in range(n)]

    def test_clearly_better_than_close_ships(self) -> None:
        """p_raw clearly closer to truth than p_close -> SHIP."""
        n = MIN_MARKET_N + 50
        market = "nba:moneyline"
        # Alternate y in {0,1} -- p_raw=0.6 when y=1, 0.4 when y=0: well calibrated.
        # p_close=0.5 always: no information vs outcomes.
        rows = []
        for i in range(n):
            y = i % 2
            p_raw = 0.8 if y == 1 else 0.2  # strong signal, beats naive 0.5
            rows.append(_make_row(p_raw, y, market, p_close=0.5))
        row = grade_market_segment(market, rows)
        assert row["status"] == "SHIP", (
            f"expected SHIP (p_raw tracks outcome, p_close=0.5); got {row['status']}; "
            f"bss={row['readout'].get('bss_vs_close')}"
        )

    def test_clearly_worse_than_close_rejects(self) -> None:
        """p_raw anti-correlated with outcome, p_close neutral -> REJECT."""
        n = MIN_MARKET_N + 50
        market = "nba:moneyline"
        rows = []
        for i in range(n):
            y = i % 2
            p_raw = 0.2 if y == 1 else 0.8  # wrong direction vs outcome
            rows.append(_make_row(p_raw, y, market, p_close=0.5))
        row = grade_market_segment(market, rows)
        assert row["status"] == "REJECT", (
            f"expected REJECT (p_raw anti-correlated, p_close=0.5); got {row['status']}; "
            f"bss={row['readout'].get('bss_vs_close')}"
        )

    def test_no_close_price_defaults_hold(self) -> None:
        """When no p_close is provided verdict_from_readout must return HOLD."""
        readout = {"n": 50, "bss_vs_close": None, "n_with_close": 0}
        assert verdict_from_readout(readout) == "HOLD"

    def test_bss_just_above_improve_tol_ships(self) -> None:
        """BSS just above BRIER_IMPROVE_TOL -> SHIP (boundary check)."""
        readout = {"bss_vs_close": BRIER_IMPROVE_TOL + 1e-6}
        assert verdict_from_readout(readout) == "SHIP"

    def test_bss_just_below_regress_tol_rejects(self) -> None:
        """BSS just below -BRIER_REGRESS_TOL -> REJECT (boundary check)."""
        readout = {"bss_vs_close": -(BRIER_REGRESS_TOL + 1e-6)}
        assert verdict_from_readout(readout) == "REJECT"

    def test_bss_zero_holds(self) -> None:
        """BSS = 0 (exactly at close) -> HOLD."""
        readout = {"bss_vs_close": 0.0}
        assert verdict_from_readout(readout) == "HOLD"
