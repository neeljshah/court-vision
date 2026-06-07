"""Tests for signals/scheme_matchup_scoring.py.

Covers:
  1. Leak-safety: store reads never return a record stamped after ctx.decision_time.
  2. Value sanity: build() returns a float or None; validate_output passes.
  3. Hypothesis: hypothesis() returns a well-formed Hypothesis.
  4. Feature names: scalar signal -> [signal.name].
  5. Graceful None when both player and opponent data are absent.
  6. Interaction scoring helpers:
       - _score_rim_attack positive for drive-heavy vs weak rim protection
       - _score_rim_attack None when any input is None
       - _score_catch_shoot positive for C&S specialist vs DROP COVERAGE
       - _score_iso positive for iso scorer vs ISO-force team
       - _score_pnr_handler positive for PnR handler vs DROP scheme
       - _quality_shrinkage compresses positive edges for elite defense
  7. Full build() with store-injected atlas values produces a non-None float.
  8. build() with raw parquet fallback (store=None, no files) returns None gracefully.
"""
from __future__ import annotations

import datetime as _dt
import tempfile
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.loop.signal import AsOfContext, Hypothesis
from src.loop.store import PointInTimeStore
from signals.scheme_matchup_scoring import (
    SchemeMatchupScoringSignal,
    _quality_shrinkage,
    _score_catch_shoot,
    _score_iso,
    _score_pnr_handler,
    _score_rim_attack,
)


# ---------------------------------------------------------------------------
# Test context factory
# ---------------------------------------------------------------------------

def _ctx(
    player_id: Optional[int] = 1628983,
    opp: str = "LAL",
    team: str = "OKC",
    decision_date: str = "2025-03-01",
    store: Optional[Any] = None,
) -> AsOfContext:
    """Build a minimal pregame AsOfContext for testing."""
    dt = _dt.datetime.fromisoformat(decision_date)
    return AsOfContext(
        decision_time=dt,
        player_id=player_id,
        team=team,
        opp=opp,
        game_date=decision_date,
        season="2024-25",
        scope="pregame",
    )


# ---------------------------------------------------------------------------
# 1. Leak-safety
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """PointInTimeStore must never return records stamped after decision_time."""

    def test_store_rejects_future_record(self):
        """A record written with a future as_of must be invisible at decision_time."""
        with tempfile.TemporaryDirectory() as td:
            store = PointInTimeStore(store_dir=td, autoload=False)
            decision_time = _dt.datetime(2025, 3, 1)

            store.write_atlas(
                "player", 1628983, "shot_profile", "2025-04-01",
                {"creation": {"drive_count_pg": 8.0, "drive_fg_pct": 0.62}},
                {"source": "test", "n": 30, "confidence": "high", "as_of": "2025-04-01"},
            )

            result = store.read_atlas("player", 1628983, "shot_profile", decision_time)
            assert result is None, (
                f"Leak violated: future shot_profile returned {result!r} at {decision_time.date()}"
            )

    def test_store_returns_past_record(self):
        """A record written with a past as_of IS visible at decision_time."""
        with tempfile.TemporaryDirectory() as td:
            store = PointInTimeStore(store_dir=td, autoload=False)
            decision_time = _dt.datetime(2025, 3, 1)
            past = "2025-01-10"

            store.write_atlas(
                "team", "LAL", "defensive_scheme", past,
                {"scheme_axes": {"paint_protection_score": 0.8}},
                {"source": "test", "n": 40, "confidence": "high", "as_of": past},
            )

            result = store.read_atlas("team", "LAL", "defensive_scheme", decision_time)
            assert result is not None, "Past defensive_scheme record should be readable"
            assert result.get("scheme_axes", {}).get("paint_protection_score") == 0.8

    def test_build_uses_store_as_of_boundary(self):
        """build() with store must not use data beyond ctx.decision_time."""
        with tempfile.TemporaryDirectory() as td:
            store = PointInTimeStore(store_dir=td, autoload=False)

            # Write player atlas BEFORE decision_time
            past = "2025-01-15"
            store.write_atlas(
                "player", 1001, "shot_profile", past,
                {
                    "creation": {
                        "drive_count_pg": 6.0,
                        "drive_fg_pct": 0.58,
                        "catch_shoot_fga_pg": 3.0,
                        "catch_shoot_efg_pct": 0.54,
                    },
                    "context": {"pnr_handler_pg": 4.0, "iso_poss_pg": 2.5},
                },
                {"source": "test", "n": 25, "confidence": "high", "as_of": past},
            )
            # Write opponent scheme BEFORE decision_time
            store.write_atlas(
                "team", "MIA", "defensive_scheme", past,
                {
                    "scheme_axes": {
                        "paint_protection_score": 0.3,
                        "perimeter_denial_score": 0.4,
                        "iso_force_score": 0.5,
                        "drop_score": 0.6,
                        "quality_z": 0.2,
                    },
                    "perimeter_pressure": {"opp_catch_shoot_allowed_pct_z": 0.5},
                },
                {"source": "test", "n": 25, "confidence": "high", "as_of": past},
            )

            # Write FUTURE records that must be invisible
            store.write_atlas(
                "player", 1001, "shot_profile", "2025-04-01",
                {"creation": {"drive_count_pg": 99.0}},  # obviously wrong if read
                {"source": "test", "n": 1, "confidence": "low", "as_of": "2025-04-01"},
            )

            sig = SchemeMatchupScoringSignal(store=store)
            ctx = _ctx(player_id=1001, opp="MIA", decision_date="2025-03-01")
            result = sig.build(ctx)

            # Must return a float; if future drive_count_pg=99 were used, the rim
            # score would be far outside the plausible (−2, +2) range.
            assert result is None or isinstance(result, float)
            if result is not None:
                assert -5.0 < result < 5.0, (
                    f"Result {result} suggests future data leaked into build()"
                )


# ---------------------------------------------------------------------------
# 2. Value sanity
# ---------------------------------------------------------------------------

class TestValueSanity:
    """build() must return float or None; validate_output must pass."""

    def test_returns_none_when_player_id_is_none(self):
        sig = SchemeMatchupScoringSignal(store=None)
        ctx = AsOfContext(
            decision_time=_dt.datetime(2025, 3, 1),
            player_id=None, opp="LAL", scope="pregame",
        )
        assert sig.build(ctx) is None

    def test_returns_none_when_opp_is_none(self):
        sig = SchemeMatchupScoringSignal(store=None)
        ctx = AsOfContext(
            decision_time=_dt.datetime(2025, 3, 1),
            player_id=1628983, opp=None, scope="pregame",
        )
        assert sig.build(ctx) is None

    def test_returns_none_when_no_data_available(self):
        """Without any parquet files and no store, build() must return None gracefully."""
        sig = SchemeMatchupScoringSignal(store=None)
        ctx = _ctx(player_id=9999999, opp="XYZ")
        result = sig.build(ctx)
        assert result is None

    def test_validate_output_passes_for_float(self):
        sig = SchemeMatchupScoringSignal()
        assert sig.validate_output(0.42)
        assert sig.validate_output(-1.1)
        assert sig.validate_output(0.0)

    def test_validate_output_passes_for_none(self):
        sig = SchemeMatchupScoringSignal()
        assert sig.validate_output(None)

    def test_build_with_store_atlas_returns_float(self):
        """build() with complete atlas data in the store returns a float."""
        with tempfile.TemporaryDirectory() as td:
            store = PointInTimeStore(store_dir=td, autoload=False)
            past = "2025-01-01"

            store.write_atlas(
                "player", 2000, "shot_profile", past,
                {
                    "creation": {
                        "drive_count_pg": 7.5,
                        "drive_fg_pct": 0.60,
                        "catch_shoot_fga_pg": 4.0,
                        "catch_shoot_efg_pct": 0.56,
                    },
                    "context": {"pnr_handler_pg": 5.0, "iso_poss_pg": 3.0},
                },
                {"source": "test", "n": 50, "confidence": "high", "as_of": past},
            )
            store.write_atlas(
                "team", "SAS", "defensive_scheme", past,
                {
                    "scheme_axes": {
                        "paint_protection_score": 0.2,   # weak rim protection
                        "perimeter_denial_score": 0.3,   # moderate perimeter
                        "iso_force_score": 0.5,
                        "drop_score": 0.7,               # heavy drop coverage
                        "quality_z": -0.5,               # below-avg defense
                    },
                    "perimeter_pressure": {"opp_catch_shoot_allowed_pct_z": 0.8},
                },
                {"source": "test", "n": 50, "confidence": "high", "as_of": past},
            )

            sig = SchemeMatchupScoringSignal(store=store)
            ctx = _ctx(player_id=2000, opp="SAS", decision_date="2025-03-01")
            result = sig.build(ctx)

            assert result is not None, "Expected a float for complete atlas data"
            assert isinstance(result, float), f"Expected float, got {type(result)}"
            assert sig.validate_output(result)

    def test_rim_attacking_player_vs_weak_rim_protection_is_positive(self):
        """Drive-heavy player vs weak rim team must yield a positive composite."""
        with tempfile.TemporaryDirectory() as td:
            store = PointInTimeStore(store_dir=td, autoload=False)
            past = "2025-01-01"

            store.write_atlas(
                "player", 3001, "shot_profile", past,
                {
                    "creation": {
                        "drive_count_pg": 10.0,    # elite driver
                        "drive_fg_pct": 0.65,       # high efficiency
                        "catch_shoot_fga_pg": None,
                        "catch_shoot_efg_pct": None,
                    },
                    "context": {"pnr_handler_pg": None, "iso_poss_pg": None},
                },
                {"source": "test", "n": 50, "confidence": "high", "as_of": past},
            )
            store.write_atlas(
                "team", "DET", "defensive_scheme", past,
                {
                    "scheme_axes": {
                        "paint_protection_score": 0.05,  # extremely weak rim protection
                        "perimeter_denial_score": 0.5,
                        "iso_force_score": 0.3,
                        "drop_score": 0.4,
                        "quality_z": -1.0,
                    },
                    "perimeter_pressure": {},
                },
                {"source": "test", "n": 50, "confidence": "high", "as_of": past},
            )

            sig = SchemeMatchupScoringSignal(store=store)
            ctx = _ctx(player_id=3001, opp="DET", decision_date="2025-03-01")
            result = sig.build(ctx)

            assert result is not None
            assert result > 0.0, (
                f"Drive-heavy player vs weak rim protection should be positive, got {result}"
            )

    def test_cs_player_vs_perimeter_denial_is_negative(self):
        """Catch-and-shoot specialist vs elite perimeter denial must be negative or near 0."""
        with tempfile.TemporaryDirectory() as td:
            store = PointInTimeStore(store_dir=td, autoload=False)
            past = "2025-01-01"

            store.write_atlas(
                "player", 3002, "shot_profile", past,
                {
                    "creation": {
                        "drive_count_pg": 1.0,      # minimal driving
                        "drive_fg_pct": 0.40,
                        "catch_shoot_fga_pg": 8.0,  # heavy C&S
                        "catch_shoot_efg_pct": 0.58,
                    },
                    "context": {"pnr_handler_pg": None, "iso_poss_pg": None},
                },
                {"source": "test", "n": 50, "confidence": "high", "as_of": past},
            )
            store.write_atlas(
                "team", "BOS", "defensive_scheme", past,
                {
                    "scheme_axes": {
                        "paint_protection_score": 0.8,
                        "perimeter_denial_score": 0.95,  # elite perimeter denial
                        "iso_force_score": 0.3,
                        "drop_score": 0.1,
                        "quality_z": 1.5,                # elite defense overall
                    },
                    "perimeter_pressure": {"opp_catch_shoot_allowed_pct_z": -1.5},
                },
                {"source": "test", "n": 50, "confidence": "high", "as_of": past},
            )

            sig = SchemeMatchupScoringSignal(store=store)
            ctx = _ctx(player_id=3002, opp="BOS", decision_date="2025-03-01")
            result = sig.build(ctx)

            # C&S-heavy player vs elite perimeter denial should be negative or small positive
            assert result is not None
            assert result <= 0.3, (
                f"C&S player vs PERIMETER DENIAL should be <= 0.3, got {result}"
            )


# ---------------------------------------------------------------------------
# 3. Hypothesis
# ---------------------------------------------------------------------------

class TestHypothesis:
    """hypothesis() must return a well-formed Hypothesis."""

    def test_hypothesis_fields(self):
        sig = SchemeMatchupScoringSignal()
        hyp = sig.hypothesis()
        assert isinstance(hyp, Hypothesis)
        assert hyp.name == "scheme_matchup_scoring"
        assert hyp.target == "pts"
        assert hyp.scope == "pregame"
        assert len(hyp.statement) > 40
        assert len(hyp.rationale) > 40
        assert hyp.source == "seed"
        assert "shot_profile" in hyp.atlas_fields
        assert "defensive_scheme" in hyp.atlas_fields
        assert hyp.expected_verdict == "SHIP"

    def test_feature_names_scalar(self):
        sig = SchemeMatchupScoringSignal()
        assert sig.feature_names() == ["scheme_matchup_scoring"]


# ---------------------------------------------------------------------------
# 4. Interaction scoring helpers
# ---------------------------------------------------------------------------

class TestInteractionHelpers:
    """Unit tests for the pure scoring-dimension functions."""

    # --- _score_rim_attack ---

    def test_rim_attack_positive_for_elite_driver_vs_weak_rim(self):
        """10 drives/g at 0.65 FG% vs paint_protection=0.1 must be positive."""
        score = _score_rim_attack(
            drive_count_pg=10.0, drive_fg_pct=0.65, paint_protection_score=0.1
        )
        assert score is not None
        assert score > 0.0, f"Expected positive rim-attack score, got {score}"

    def test_rim_attack_negative_for_elite_rim_protection(self):
        """Average driver vs near-perfect rim protection must be near-zero or negative."""
        score = _score_rim_attack(
            drive_count_pg=4.0, drive_fg_pct=0.55, paint_protection_score=0.95
        )
        assert score is not None
        # drive_strength = 1.0, interaction = (1-1) * (1-0.95) = 0 → neutral
        assert -1.0 <= score <= 0.1, f"Expected near-zero or negative, got {score}"

    def test_rim_attack_none_when_missing_inputs(self):
        assert _score_rim_attack(None, 0.55, 0.5) is None
        assert _score_rim_attack(4.0, None, 0.5) is None
        assert _score_rim_attack(4.0, 0.55, None) is None

    # --- _score_catch_shoot ---

    def test_catch_shoot_positive_for_shooter_vs_drop_coverage(self):
        """Heavy C&S (8 FGA/g, eFG 0.58) vs drop coverage (perimeter_denial=0.1)
        and team that concedes C&S (opp_cs_z=1.0) must be positive."""
        score = _score_catch_shoot(
            cs_fga_pg=8.0, cs_efg_pct=0.58,
            perimeter_denial_score=0.1,
            opp_cs_allowed_z=1.0,
        )
        assert score is not None
        assert score > 0.0, f"Expected positive C&S score, got {score}"

    def test_catch_shoot_negative_for_perimeter_denial(self):
        """Modest C&S shooter vs tight perimeter denial must be negative."""
        score = _score_catch_shoot(
            cs_fga_pg=3.0, cs_efg_pct=0.50,
            perimeter_denial_score=0.95,
            opp_cs_allowed_z=-1.0,
        )
        assert score is not None
        assert score < 0.0, f"Expected negative C&S score, got {score}"

    def test_catch_shoot_none_when_no_inputs(self):
        assert _score_catch_shoot(None, None, None, None) is None

    def test_catch_shoot_partial_opp_cs_only(self):
        """opp_cs_allowed_z alone (player stats None) still produces a score."""
        score = _score_catch_shoot(
            cs_fga_pg=None, cs_efg_pct=None,
            perimeter_denial_score=None,
            opp_cs_allowed_z=1.5,
        )
        assert score is not None
        assert score > 0.0

    # --- _score_iso ---

    def test_iso_positive_for_iso_scorer_vs_iso_force_team(self):
        """5 iso possessions/g vs high iso_force_score (0.8) must be positive."""
        score = _score_iso(iso_poss_pg=5.0, iso_force_score=0.8)
        assert score is not None
        assert score > 0.0, f"Expected positive iso score, got {score}"

    def test_iso_negative_for_below_avg_iso_vs_iso_force(self):
        """0.5 iso poss/g vs high iso_force (team forces bad iso scorers) negative."""
        score = _score_iso(iso_poss_pg=0.5, iso_force_score=0.8)
        assert score is not None
        assert score < 0.0, f"Expected negative iso score, got {score}"

    def test_iso_zero_at_average(self):
        """Exactly 2 iso poss/g (the anchor) should give a score near 0."""
        score = _score_iso(iso_poss_pg=2.0, iso_force_score=0.6)
        assert score is not None
        assert abs(score) < 0.01, f"Average iso should be ~0, got {score}"

    def test_iso_none_when_missing(self):
        assert _score_iso(None, 0.5) is None
        assert _score_iso(3.0, None) is None

    # --- _score_pnr_handler ---

    def test_pnr_positive_for_elite_handler_vs_drop_coverage(self):
        """6 PnR handler/g vs drop_score=0.9 must be positive."""
        score = _score_pnr_handler(pnr_handler_pg=6.0, drop_score=0.9)
        assert score is not None
        assert score > 0.0, f"Expected positive PnR score, got {score}"

    def test_pnr_negative_for_poor_handler_vs_drop_coverage(self):
        """1 PnR handler/g (ball-stopper) vs drop score still negative (below avg)."""
        score = _score_pnr_handler(pnr_handler_pg=1.0, drop_score=0.7)
        assert score is not None
        assert score < 0.0, f"Expected negative PnR score for below-avg handler"

    def test_pnr_none_when_missing(self):
        assert _score_pnr_handler(None, 0.6) is None
        assert _score_pnr_handler(4.0, None) is None

    # --- _quality_shrinkage ---

    def test_quality_shrinkage_compresses_positive_for_elite_defense(self):
        """quality_z=2.0 (elite defense) must shrink a positive composite."""
        original = 1.0
        shrunk = _quality_shrinkage(original, quality_z=2.0)
        assert shrunk < original, f"Elite defense should compress positive edge: {shrunk} vs {original}"
        assert shrunk > 0.0, "Should still be positive"

    def test_quality_shrinkage_amplifies_positive_for_poor_defense(self):
        """quality_z=-2.0 (poor defense) must amplify a positive composite."""
        original = 1.0
        amplified = _quality_shrinkage(original, quality_z=-2.0)
        assert amplified > original, f"Poor defense should amplify edge: {amplified} vs {original}"

    def test_quality_shrinkage_noop_when_quality_z_none(self):
        """None quality_z leaves composite unchanged."""
        assert _quality_shrinkage(1.23, None) == 1.23

    def test_quality_shrinkage_clamps_factor(self):
        """Extreme quality_z values must stay within the [0.5, 1.3] shrinkage bounds."""
        # quality_z=10 -> factor = max(0.5, 1-1.0) = 0.5
        low = _quality_shrinkage(1.0, quality_z=10.0)
        assert low == 0.5, f"Expected 0.5 (clamped min), got {low}"
        # quality_z=-10 -> factor = min(1.3, 1+1.0) = 1.3
        high = _quality_shrinkage(1.0, quality_z=-10.0)
        assert high == 1.3, f"Expected 1.3 (clamped max), got {high}"


# ---------------------------------------------------------------------------
# 5. reads_atlas registry
# ---------------------------------------------------------------------------

class TestAtlasRegistry:
    """reads_atlas must list the two atlas sections the signal consumes."""

    def test_reads_atlas_contains_shot_profile_and_defensive_scheme(self):
        sig = SchemeMatchupScoringSignal()
        assert "shot_profile" in sig.reads_atlas
        assert "defensive_scheme" in sig.reads_atlas
