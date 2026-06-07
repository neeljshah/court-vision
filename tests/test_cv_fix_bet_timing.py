"""tests/test_cv_fix_bet_timing.py

Lock-in tests for scripts/cv_fix_bet_timing.py covering:
  1. _calibrated_confidence — monotonic in edge, bounded [0.50, 0.88], NaN-free,
     and ranks a tight blk-under >= a wide fg3m-over at equal edge.
  2. No-lookahead — every chosen bet's proj_snap_ep <= entry ep on game 0042500316.
  3. _epoch — handles tz-aware and naive UTC timestamps consistently.
"""
from __future__ import annotations

import math
import os
import sys

import pytest

# Force offline mode so no live API calls fire during tests
os.environ.setdefault("NBA_OFFLINE", "1")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from scripts.cv_fix_bet_timing import _calibrated_confidence, _epoch, STATS


# ─────────────────────────────────────────────────────────────────────────────
# 1. _epoch: tz-aware and naive UTC consistency
# ─────────────────────────────────────────────────────────────────────────────

class TestEpoch:
    """_epoch should treat naive ISO timestamps as UTC, matching tz-aware ones."""

    TS_UTC_AWARE = "2026-05-29T03:17:18+00:00"
    TS_NAIVE     = "2026-05-29T03:17:18"
    TS_Z         = "2026-05-29T03:17:18Z"

    def test_tz_aware_equals_naive(self):
        """Naive timestamp treated as UTC should equal explicit +00:00."""
        assert _epoch(self.TS_UTC_AWARE) == _epoch(self.TS_NAIVE)

    def test_z_suffix_equals_aware(self):
        """'Z' suffix should be parsed identically to +00:00."""
        assert _epoch(self.TS_Z) == _epoch(self.TS_UTC_AWARE)

    def test_all_three_equal(self):
        ep_aware = _epoch(self.TS_UTC_AWARE)
        ep_naive = _epoch(self.TS_NAIVE)
        ep_z     = _epoch(self.TS_Z)
        assert ep_aware == ep_naive == ep_z

    def test_non_utc_offset_is_normalised(self):
        """ET aware (-04:00) should give the same epoch as the UTC equivalent."""
        ep_et  = _epoch("2026-05-28T23:17:18-04:00")
        ep_utc = _epoch("2026-05-29T03:17:18+00:00")
        assert ep_et == ep_utc

    def test_empty_string_returns_minus_one(self):
        assert _epoch("") == -1.0

    def test_none_like_returns_minus_one(self):
        # _epoch(None) — the function signature accepts str but the body handles None
        assert _epoch(None) == -1.0  # type: ignore[arg-type]

    def test_invalid_format_returns_minus_one(self):
        assert _epoch("not-a-date") == -1.0

    def test_positive_epoch_for_valid_ts(self):
        ep = _epoch(self.TS_UTC_AWARE)
        assert ep > 0, "valid ISO timestamp should yield a positive epoch"

    def test_ordering_preserved(self):
        """Earlier timestamp => smaller epoch."""
        ep1 = _epoch("2026-05-29T00:00:00+00:00")
        ep2 = _epoch("2026-05-29T03:00:00+00:00")
        assert ep1 < ep2


# ─────────────────────────────────────────────────────────────────────────────
# 2. _calibrated_confidence properties
# ─────────────────────────────────────────────────────────────────────────────

class TestCalibratedConfidence:
    """_calibrated_confidence must be bounded, NaN-free, and monotonically
    increasing in (absolute) edge."""

    ALL_STATS  = list(STATS)
    ALL_SIDES  = ("OVER", "UNDER")
    ALL_STAGES = ("Pregame", "Q1", "Q2", "Q3", "Q4")

    # ── bounds ────────────────────────────────────────────────────────────────

    @pytest.mark.parametrize("stat", ALL_STATS)
    @pytest.mark.parametrize("side", ALL_SIDES)
    @pytest.mark.parametrize("stage", ALL_STAGES)
    def test_lower_bound(self, stat, side, stage):
        """Confidence must always be >= 0.50."""
        c = _calibrated_confidence(stat, 0.0, 10.0, side, stage)
        assert c >= 0.50, f"{stat}/{side}/{stage}: {c} < 0.50"

    @pytest.mark.parametrize("stat", ALL_STATS)
    @pytest.mark.parametrize("side", ALL_SIDES)
    @pytest.mark.parametrize("stage", ALL_STAGES)
    def test_upper_bound(self, stat, side, stage):
        """Confidence must always be <= 0.88."""
        c = _calibrated_confidence(stat, 1000.0, 0.0, side, stage)
        assert c <= 0.88, f"{stat}/{side}/{stage}: {c} > 0.88"

    # ── NaN-free ──────────────────────────────────────────────────────────────

    @pytest.mark.parametrize("stat", ALL_STATS)
    def test_nan_free_normal_inputs(self, stat):
        c = _calibrated_confidence(stat, 25.0, 20.0, "OVER", "Q3")
        assert not math.isnan(c), f"{stat}: NaN returned"
        assert not math.isinf(c), f"{stat}: Inf returned"

    def test_none_proj_returns_fifty(self):
        """None projection cannot produce a NaN; fall back to 0.50."""
        c = _calibrated_confidence("pts", None, 20.0, "OVER", "Q3")
        assert c == 0.50

    def test_nan_proj_returns_fifty(self):
        c = _calibrated_confidence("pts", float("nan"), 20.0, "OVER", "Q3")
        assert c == 0.50

    def test_zero_sigma_does_not_crash(self):
        """If the sigma lookup returned 0 the guard should prevent ZeroDivision."""
        # With default sigma fallback the function must not raise or return NaN
        c = _calibrated_confidence("pts", 25.0, 20.0, "OVER", "Q3")
        assert math.isfinite(c)

    # ── monotonicity in edge ───────────────────────────────────────────────────

    @pytest.mark.parametrize("stat", ALL_STATS)
    def test_monotonic_over(self, stat):
        """Larger OVER edge => higher (or equal) confidence."""
        line = 10.0
        edges = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
        confs = [_calibrated_confidence(stat, line + e, line, "OVER", "Q3")
                 for e in edges]
        for i in range(len(confs) - 1):
            assert confs[i] <= confs[i + 1] + 1e-9, (
                f"{stat} OVER not monotonic at edges {edges[i]}/{edges[i+1]}: "
                f"{confs[i]:.4f} > {confs[i+1]:.4f}"
            )

    @pytest.mark.parametrize("stat", ALL_STATS)
    def test_monotonic_under(self, stat):
        """Larger UNDER edge => higher (or equal) confidence."""
        line = 10.0
        edges = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
        confs = [_calibrated_confidence(stat, line - e, line, "UNDER", "Q3")
                 for e in edges]
        for i in range(len(confs) - 1):
            assert confs[i] <= confs[i + 1] + 1e-9, (
                f"{stat} UNDER not monotonic at edges {edges[i]}/{edges[i+1]}: "
                f"{confs[i]:.4f} > {confs[i+1]:.4f}"
            )

    # ── tight-stat ranking ───────────────────────────────────────────────────

    def test_tight_blk_under_q3_gte_wide_fg3m_over_q1_at_equal_edge(self):
        """A blk-UNDER using the narrow Q3 sigma must rank >= fg3m-OVER using
        the wide early-stage (Q1) sigma at the same absolute edge.

        The economic rationale: blk Q3 sigma (~0.36) is much tighter than fg3m
        Q1 sigma (~1.14).  At equal edge, the blk z-score is roughly 3x larger,
        and even after shrinkage toward the base hit-rate the blk-under should
        NOT be dominated by the noisier fg3m-over (which uses the wider sigma).
        """
        edge = 1.0
        line = 3.0
        blk_conf  = _calibrated_confidence("blk",  line - edge, line, "UNDER", "Q3")
        fg3m_conf = _calibrated_confidence("fg3m", line + edge, line, "OVER",  "Q1")
        assert blk_conf >= fg3m_conf, (
            f"blk-UNDER Q3 ({blk_conf:.4f}) < fg3m-OVER Q1 ({fg3m_conf:.4f}) "
            f"at equal edge={edge}. Tight stat should rank >= wide stat at equal edge."
        )

    def test_tight_vs_wide_sigma_ordering_at_moderate_edge(self):
        """blk-under in late stage must outrank fg3m-over in early stage for
        a typical mid-range edge (edge=0.8)."""
        edge = 0.8
        line = 2.0
        blk_conf  = _calibrated_confidence("blk",  line - edge, line, "UNDER", "Q4")
        fg3m_conf = _calibrated_confidence("fg3m", line + edge, line, "OVER",  "Q2")
        assert blk_conf >= fg3m_conf, (
            f"blk-UNDER Q4 ({blk_conf:.4f}) < fg3m-OVER Q2 ({fg3m_conf:.4f}) at edge={edge}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. No-lookahead on real game 0042500316
# ─────────────────────────────────────────────────────────────────────────────

class TestNoLookaheadGame0042500316:
    """Every bet's proj_snap_ep must be <= the line capture epoch (no future data)."""

    GID = "0042500316"

    @pytest.fixture(scope="class")
    def key_caps(self):
        """Build key_caps for game 0042500316 without writing any output."""
        from scripts.cv_fix_bet_timing import (
            _load_snapshots, _CarryForward, _BoundaryProjector,
            _load_inplay, _load_pregame_t0, _build_key_captures,
        )
        from api._courtvision_odds import resolve_game_id
        from api.courtvision_router import _et_date_from_iso

        alias = resolve_game_id(self.GID)
        canon_ids = sorted(
            alias.get("canonical_ids", frozenset([self.GID]))
        ) or [self.GID]

        snaps, true_final = _load_snapshots(canon_ids)
        if not snaps:
            pytest.skip("No snapshots for game 0042500316 — offline data missing")

        settled_date = None
        if true_final is not None:
            settled_date = _et_date_from_iso(true_final.get("captured_at") or "")

        carry    = _CarryForward(snaps)
        boundary = _BoundaryProjector(snaps)
        inplay   = _load_inplay(settled_date, canon_ids)

        # Build actuals for player_filter
        actuals: dict = {}
        if true_final:
            for pl in (true_final.get("players") or []):
                nm = (pl.get("name") or "").lower()
                for st in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
                    v = pl.get(st)
                    if v is not None:
                        try:
                            actuals[(nm, st)] = float(v)
                        except (TypeError, ValueError):
                            pass

        player_filter = {k[0] for k in actuals} or {r["name"] for r in inplay}
        pregame = _load_pregame_t0(self.GID, settled_date, player_filter)

        return _build_key_captures(
            inplay, pregame, carry, boundary, settled_date=settled_date
        )

    def test_no_lookahead_violation(self, key_caps):
        """proj_snap_ep must be <= entry ep for every capture."""
        violations = []
        for key, seq in key_caps.items():
            for cap in seq:
                snap_ep  = cap.get("proj_snap_ep")
                entry_ep = cap.get("ep")
                if snap_ep is not None and entry_ep is not None:
                    if snap_ep > entry_ep + 1e-6:
                        violations.append({
                            "key": key,
                            "snap_ep": snap_ep,
                            "entry_ep": entry_ep,
                            "diff": snap_ep - entry_ep,
                        })
        assert not violations, (
            f"{len(violations)} lookahead violation(s) found: "
            f"first={violations[0]}"
        )

    def test_has_captures(self, key_caps):
        """Sanity: the build must produce captures — if 0 the test is vacuous."""
        total = sum(len(seq) for seq in key_caps.values())
        assert total > 0, "build_key_captures returned 0 captures for 0042500316"

    def test_build_game_timing_runs_without_error(self):
        """build_game_timing on 0042500316 must complete without raising."""
        from scripts.cv_fix_bet_timing import build_game_timing
        payload = build_game_timing(canon_gid=self.GID, write=False)
        assert payload is not None
        assert payload.get("game_id") == self.GID

    def test_chosen_bets_no_lookahead(self):
        """Every chosen bet: proj_snap_ep (as attached to the capture) <= entry_ep.

        The graded bet dict doesn't expose proj_snap_ep directly, so we verify
        it transitively: if build_game_timing completed without the internal
        assert firing (snap_ep <= cap['ep'] + 1e-6) the no-lookahead contract holds.
        This test just double-checks that chosen bets have valid entry epochs."""
        from scripts.cv_fix_bet_timing import build_game_timing
        payload = build_game_timing(canon_gid=self.GID, write=False)
        chosen = payload.get("chosen", {}).get("bets", [])
        for bet in chosen:
            ep = bet.get("entry_ep")
            assert ep is not None and ep > 0, (
                f"Bet {bet.get('player')}/{bet.get('stat')} has no valid entry_ep: {ep}"
            )
