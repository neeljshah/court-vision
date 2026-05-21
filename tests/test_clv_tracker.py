"""tests/test_clv_tracker.py — Tests for src/validation/clv_tracker.py.

Covers: positive CLV, negative CLV, zero CLV (closing == taken),
vig-stripped closing line, decimal odds, implied-prob format.
"""
from __future__ import annotations

import math
import pytest

from src.validation.clv_tracker import (
    CLVResult,
    american_to_prob,
    compute_clv,
    compute_clv_novig,
    decimal_to_prob,
    vig_strip,
)


# ── american_to_prob ──────────────────────────────────────────────────────────

class TestAmericanToProb:
    def test_standard_favorite(self):
        prob = american_to_prob(-110)
        assert math.isclose(prob, 110 / 210, rel_tol=1e-9)

    def test_standard_underdog(self):
        prob = american_to_prob(+150)
        assert math.isclose(prob, 100 / 250, rel_tol=1e-9)

    def test_even_money(self):
        prob = american_to_prob(+100)
        assert math.isclose(prob, 0.5, rel_tol=1e-9)

    def test_heavy_favorite(self):
        prob = american_to_prob(-300)
        assert math.isclose(prob, 300 / 400, rel_tol=1e-9)


# ── decimal_to_prob ───────────────────────────────────────────────────────────

class TestDecimalToProb:
    def test_standard(self):
        # -110 American ≈ 1.909 decimal
        prob = decimal_to_prob(1.909)
        assert math.isclose(prob, 1 / 1.909, rel_tol=1e-6)

    def test_invalid_zero(self):
        with pytest.raises(ValueError):
            decimal_to_prob(0.0)

    def test_invalid_negative(self):
        with pytest.raises(ValueError):
            decimal_to_prob(-1.5)


# ── vig_strip ─────────────────────────────────────────────────────────────────

class TestVigStrip:
    def test_symmetric_market(self):
        # Both sides at -110: raw prob = 110/210 ≈ 0.5238 each
        raw = american_to_prob(-110)
        a, b = vig_strip(raw, raw)
        assert math.isclose(a, 0.5, rel_tol=1e-6)
        assert math.isclose(b, 0.5, rel_tol=1e-6)
        assert math.isclose(a + b, 1.0, rel_tol=1e-9)

    def test_asymmetric_market(self):
        raw_a = american_to_prob(-130)
        raw_b = american_to_prob(+115)
        a, b = vig_strip(raw_a, raw_b)
        assert math.isclose(a + b, 1.0, rel_tol=1e-9)
        assert a > b  # favourite has higher probability


# ── compute_clv (American) ────────────────────────────────────────────────────

class TestComputeCLV:
    def test_positive_clv(self):
        """Bet taken at -110, closes at -120: taken is better value → positive CLV."""
        r = compute_clv(-110, -120, 100.0)
        assert isinstance(r, CLVResult)
        assert r.clv_pct > 0, f"Expected positive CLV, got {r.clv_pct}"
        assert r.ev_delta_usd > 0

    def test_negative_clv(self):
        """Bet taken at -120, closes at -110: line moved against us → negative CLV."""
        r = compute_clv(-120, -110, 100.0)
        assert r.clv_pct < 0, f"Expected negative CLV, got {r.clv_pct}"
        assert r.ev_delta_usd < 0

    def test_zero_clv(self):
        """Closing line equals taken odds → CLV = 0.0."""
        r = compute_clv(-110, -110, 50.0)
        assert r.clv_pct == 0.0
        assert r.ev_delta_usd == 0.0
        assert r.stake == 50.0

    def test_stake_scaling(self):
        """ev_delta_usd scales linearly with stake."""
        r1 = compute_clv(-110, -120, 100.0)
        r2 = compute_clv(-110, -120, 200.0)
        assert math.isclose(r2.ev_delta_usd, 2 * r1.ev_delta_usd, rel_tol=1e-3)

    def test_invalid_stake(self):
        with pytest.raises(ValueError, match="stake must be positive"):
            compute_clv(-110, -120, 0.0)

    def test_decimal_format(self):
        """Decimal odds input: 1.909 ≈ -110 American."""
        r = compute_clv(1.909, 1.818, 100.0, fmt="decimal")
        # 1.818 ≈ -122: line shortened → positive CLV
        assert r.clv_pct > 0

    def test_prob_format_positive(self):
        """Implied-prob: taken at 0.52, closes at 0.55 → positive CLV.

        A higher closing implied-prob means the market moved to price the
        outcome more likely after we bet it — we got in at a better (lower)
        prob, i.e. better odds than close.
        """
        r = compute_clv(0.52, 0.55, 100.0, fmt="prob")
        assert r.clv_pct > 0

    def test_prob_format_negative(self):
        """Implied-prob: taken at 0.55, closes at 0.50 → negative CLV.

        Market moved to price the outcome less likely — we paid too much
        relative to where it settled.
        """
        r = compute_clv(0.55, 0.50, 100.0, fmt="prob")
        assert r.clv_pct < 0

    def test_invalid_prob_out_of_range(self):
        with pytest.raises(ValueError):
            compute_clv(1.2, 0.5, 100.0, fmt="prob")


# ── compute_clv_novig ─────────────────────────────────────────────────────────

class TestComputeCLVNoVig:
    def test_vig_stripped_positive(self):
        """Bet taken at -110 on a side that closes -120/-110 (two-sided).
        After vig strip, closing no-vig prob is slightly below raw → CLV positive."""
        r = compute_clv_novig(-110, -120, +110, 100.0)
        # no-vig close prob for -120 side ≈ 0.545; taken prob at -110 ≈ 0.524
        assert isinstance(r, CLVResult)
        assert r.clv_pct > 0

    def test_vig_stripped_symmetric(self):
        """Symmetric market (-110/-110): no-vig prob = 0.5.
        Taken at -110 (prob 0.524) → vs 0.5 → negative CLV (paid vig)."""
        r = compute_clv_novig(-110, -110, -110, 100.0)
        assert r.clv_pct < 0  # we paid vig; closing fair-value is lower

    def test_result_shape(self):
        r = compute_clv_novig(-115, -118, +102, 200.0)
        assert r.stake == 200.0
        assert hasattr(r, "taken_prob")
        assert hasattr(r, "closing_prob")


# ── snapshot integration (build_snapshot) ────────────────────────────────────

class TestBuildSnapshot:
    def _import(self):
        from scripts.snapshot_clv import build_snapshot
        return build_snapshot

    def test_basic_join(self):
        build_snapshot = self._import()
        bets = [
            {"bet_id": "b1", "stake": 100.0,
             "taken_odds": -110.0, "placed_at": "2026-05-20T12:00:00"},
        ]
        clv_entries = [
            {"bet_id": "b1", "closing_line": -120.0},
        ]
        result = build_snapshot(bets, clv_entries, target_date="2026-05-20")
        assert "2026-05-20" in result
        rows = result["2026-05-20"]
        assert len(rows) == 1
        assert rows[0]["clv_pct"] > 0

    def test_missing_closing_line_skipped(self):
        build_snapshot = self._import()
        bets = [
            {"bet_id": "b2", "stake": 50.0,
             "taken_odds": -110.0, "placed_at": "2026-05-20T14:00:00"},
        ]
        result = build_snapshot(bets, [], target_date="2026-05-20")
        assert result == {}

    def test_date_filter(self):
        build_snapshot = self._import()
        bets = [
            {"bet_id": "b3", "stake": 100.0, "taken_odds": -110.0,
             "placed_at": "2026-05-19T10:00:00"},
            {"bet_id": "b4", "stake": 100.0, "taken_odds": -110.0,
             "placed_at": "2026-05-20T10:00:00"},
        ]
        clv_entries = [
            {"bet_id": "b3", "closing_line": -115.0},
            {"bet_id": "b4", "closing_line": -115.0},
        ]
        result = build_snapshot(bets, clv_entries, target_date="2026-05-20")
        assert "2026-05-19" not in result
        assert "2026-05-20" in result

    def test_row_schema(self):
        build_snapshot = self._import()
        bets = [
            {"bet_id": "b5", "stake": 100.0, "taken_odds": -110.0,
             "placed_at": "2026-05-20T08:00:00"},
        ]
        clv_entries = [{"bet_id": "b5", "closing_line": -110.0}]
        result = build_snapshot(bets, clv_entries, target_date="2026-05-20")
        row = result["2026-05-20"][0]
        for key in ("bet_id", "taken_odds", "closing_odds", "clv_pct", "ev_delta_usd"):
            assert key in row, f"Missing key: {key}"
