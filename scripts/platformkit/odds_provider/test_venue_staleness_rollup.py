"""Per-file tests for venue_staleness_rollup.py (workstream R6-7).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/odds_provider/test_venue_staleness_rollup.py -q

Acceptance criteria (R6-7-venue-staleness-rollup):
  1. Two venues, one fresh one stale -> venues dict 2 keys, correct per-venue verdicts.
  2. All stale -> overall="stale" (NEVER "ok"/"fresh"; stale-never-green).
  3. Empty input -> overall="UNAVAILABLE" (not stale, not green).
  4. sidecar_status shape stable: keys ok/status/venues/n_fresh/n_stale.
  5. No $ field, no roi/pnl/profit/edge key anywhere.
  6. rollup_from_arbitrate() matches rollup() for same input.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.platformkit.odds_provider.line_freshness_arbiter import arbitrate
from scripts.platformkit.odds_provider.venue_staleness_rollup import (
    STATUS_FRESH,
    STATUS_STALE,
    STATUS_UNAVAILABLE,
    VenueStalenessResult,
    rollup,
    rollup_from_arbitrate,
    sidecar_status,
)

_T0 = datetime(2026, 6, 18, 20, 0, 0, tzinfo=timezone.utc)


def _ago(seconds: float) -> str:
    return (_T0 - timedelta(seconds=seconds)).isoformat()


# ---------------------------------------------------------------------------
# 1. Two venues, one fresh one stale
# ---------------------------------------------------------------------------

class TestTwoVenuesOneFreshOneStale:
    def test_venues_dict_has_two_keys(self):
        r = rollup({"draftkings": _ago(60), "fanduel": _ago(2000)}, now=_T0)
        assert set(r.venues.keys()) == {"draftkings", "fanduel"}

    def test_fresh_venue_verdict(self):
        r = rollup({"draftkings": _ago(60), "fanduel": _ago(2000)}, now=_T0)
        assert r.venues["draftkings"].status == STATUS_FRESH

    def test_stale_venue_verdict(self):
        r = rollup({"draftkings": _ago(60), "fanduel": _ago(2000)}, now=_T0)
        assert r.venues["fanduel"].status == STATUS_STALE

    def test_overall_is_fresh_when_one_fresh(self):
        r = rollup({"draftkings": _ago(60), "fanduel": _ago(2000)}, now=_T0)
        assert r.overall == STATUS_FRESH

    def test_counts_correct(self):
        r = rollup({"draftkings": _ago(60), "fanduel": _ago(2000)}, now=_T0)
        assert r.n_fresh == 1
        assert r.n_stale == 1

    def test_age_sec_is_approx_correct_for_fresh_venue(self):
        r = rollup({"book_A": _ago(120), "book_B": _ago(1200)}, now=_T0)
        assert r.venues["book_A"].age_sec == pytest.approx(120.0, abs=0.5)

    def test_stale_venue_age_sec_is_set(self):
        r = rollup({"book_A": _ago(120), "book_B": _ago(1200)}, now=_T0)
        assert r.venues["book_B"].age_sec == pytest.approx(1200.0, abs=0.5)


# ---------------------------------------------------------------------------
# 2. All stale -> overall="stale"; stale-never-green
# ---------------------------------------------------------------------------

class TestAllVenuesStale:
    def test_overall_is_stale(self):
        r = rollup({"book_A": _ago(1000), "book_B": _ago(2000)}, now=_T0)
        assert r.overall == STATUS_STALE

    def test_overall_never_fresh_when_all_stale(self):
        r = rollup({"book_A": _ago(5000), "book_B": _ago(9000)}, now=_T0)
        assert r.overall != STATUS_FRESH

    def test_n_fresh_zero_when_all_stale(self):
        r = rollup({"book_A": _ago(1000), "book_B": _ago(2000)}, now=_T0)
        assert r.n_fresh == 0
        assert r.n_stale == 2

    def test_single_stale_venue(self):
        r = rollup({"book_A": _ago(9999)}, now=_T0)
        assert r.overall == STATUS_STALE

    def test_none_ts_only_is_stale_not_unavailable(self):
        """A venue with None ts is present -> overall stale, not UNAVAILABLE."""
        r = rollup({"book_A": None}, now=_T0)
        assert r.overall == STATUS_STALE
        assert r.venues["book_A"].status == STATUS_STALE


# ---------------------------------------------------------------------------
# 3. Empty input -> UNAVAILABLE
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_overall_is_unavailable(self):
        r = rollup({}, now=_T0)
        assert r.overall == STATUS_UNAVAILABLE

    def test_venues_dict_is_empty(self):
        r = rollup({}, now=_T0)
        assert r.venues == {}

    def test_counts_are_zero(self):
        r = rollup({}, now=_T0)
        assert r.n_fresh == 0
        assert r.n_stale == 0

    def test_sidecar_ok_false_when_unavailable(self):
        r = rollup({}, now=_T0)
        assert sidecar_status(r)["ok"] is False


# ---------------------------------------------------------------------------
# 4. sidecar_status shape stable
# ---------------------------------------------------------------------------

class TestSidecarStatusShape:
    REQUIRED = {"ok", "status", "venues", "n_fresh", "n_stale"}

    def test_keys_present_fresh(self):
        assert set(sidecar_status(rollup({"b": _ago(60)}, now=_T0)).keys()) == self.REQUIRED

    def test_keys_present_stale(self):
        assert set(sidecar_status(rollup({"b": _ago(5000)}, now=_T0)).keys()) == self.REQUIRED

    def test_keys_present_empty(self):
        assert set(sidecar_status(rollup({}, now=_T0)).keys()) == self.REQUIRED

    def test_ok_true_only_when_fresh(self):
        assert sidecar_status(rollup({"b": _ago(60)}, now=_T0))["ok"] is True
        assert sidecar_status(rollup({"b": _ago(5000)}, now=_T0))["ok"] is False
        assert sidecar_status(rollup({}, now=_T0))["ok"] is False

    def test_venues_sub_dict_has_status_and_age_keys(self):
        sc = sidecar_status(rollup({"book_A": _ago(60), "book_B": _ago(2000)}, now=_T0))
        for name, data in sc["venues"].items():
            assert "status" in data and "age_sec" in data, f"{name} missing keys"

    def test_status_matches_overall(self):
        r = rollup({"b": _ago(60)}, now=_T0)
        assert sidecar_status(r)["status"] == r.overall

    def test_n_fresh_n_stale_are_ints(self):
        sc = sidecar_status(rollup({"a": _ago(60), "b": _ago(2000)}, now=_T0))
        assert isinstance(sc["n_fresh"], int) and isinstance(sc["n_stale"], int)

    def test_sidecar_never_raises_on_default_result(self):
        sc = sidecar_status(VenueStalenessResult())
        assert sc["ok"] is False and sc["status"] == STATUS_UNAVAILABLE


# ---------------------------------------------------------------------------
# 5. No $ or financial fields
# ---------------------------------------------------------------------------

class TestNoMoneyFields:
    def _sc_str(self, r: VenueStalenessResult) -> str:
        return str(sidecar_status(r)).lower()

    def test_no_dollar_sign(self):
        assert "$" not in self._sc_str(rollup({"b": _ago(60)}, now=_T0))

    def test_no_forbidden_keys(self):
        s = self._sc_str(rollup({"b": _ago(60), "c": _ago(2000)}, now=_T0))
        for kw in ("roi", "pnl", "profit", "bankroll", "stake", "usd"):
            assert kw not in s, f"forbidden key '{kw}' found"


# ---------------------------------------------------------------------------
# 6. rollup_from_arbitrate() consistent with rollup()
# ---------------------------------------------------------------------------

class TestRollupFromArbitrate:
    def test_same_overall_as_rollup(self):
        ts = {"book_A": _ago(60), "book_B": _ago(2000)}
        arb = arbitrate(ts, now=_T0)
        r_arb = rollup_from_arbitrate(arb)
        r_direct = rollup(ts, now=_T0)
        assert r_arb.overall == r_direct.overall

    def test_same_keys_and_counts(self):
        ts = {"book_A": _ago(60), "book_B": _ago(2000)}
        arb = arbitrate(ts, now=_T0)
        r_arb = rollup_from_arbitrate(arb)
        r_direct = rollup(ts, now=_T0)
        assert set(r_arb.venues.keys()) == set(r_direct.venues.keys())
        assert r_arb.n_fresh == r_direct.n_fresh
        assert r_arb.n_stale == r_direct.n_stale

    def test_empty_arbitrate_gives_unavailable(self):
        arb = arbitrate({}, now=_T0)
        r = rollup_from_arbitrate(arb)
        assert r.overall == STATUS_UNAVAILABLE

    def test_all_stale_via_arbitrate(self):
        arb = arbitrate({"a": _ago(3000), "b": _ago(5000)}, now=_T0)
        r = rollup_from_arbitrate(arb)
        assert r.overall == STATUS_STALE and r.n_fresh == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_unparseable_ts_shows_stale_with_none_age(self):
        r = rollup({"book_A": "garbage", "book_B": _ago(60)}, now=_T0)
        assert r.venues["book_A"].status == STATUS_STALE
        assert r.venues["book_A"].age_sec is None

    def test_per_market_sla_total_vs_moneyline(self):
        ts = _ago(1200)  # 20 min old -- fresh for total (30min SLA), stale for ML (15min)
        assert rollup({"b": ts}, now=_T0, market_type="total").overall == STATUS_FRESH
        assert rollup({"b": ts}, now=_T0, market_type="moneyline").overall == STATUS_STALE

    def test_all_fresh_counts(self):
        r = rollup({"a": _ago(30), "b": _ago(120), "c": _ago(300)}, now=_T0)
        assert r.overall == STATUS_FRESH and r.n_fresh == 3 and r.n_stale == 0

    def test_never_raises_on_all_none_ts(self):
        r = rollup({"a": None, "b": None}, now=_T0)
        assert isinstance(r, VenueStalenessResult)
        assert r.overall == STATUS_STALE
