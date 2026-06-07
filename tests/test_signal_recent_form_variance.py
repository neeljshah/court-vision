"""tests/test_signal_recent_form_variance.py — Unit tests for RecentFormVariance signal.

Covers:
  1. Leak-safety: build() must NEVER read data stamped after ctx.decision_time.
     The cv_consistency_kelly parquet is filtered with asof_date < decision_time;
     the store atlas read uses as_of=ctx.decision_time (enforced by the store).
  2. Value-sanity: sigma_mult in [0.5, 2.5], cv_consistency_z is a float,
     coverage_weight in [0, 1].
  3. Missing player → neutral (sigma_mult=1.0, z=0.0, weight~0.0).
  4. No player_id → None.
  5. hypothesis() returns correct target="sigma", scope="both", name.
  6. feature_names() matches emits.
  7. Atlas inflation path: a player with low interval_coverage gets a higher
     sigma_mult (tested via the store injection).
  8. Coverage weight monotonicity: more CV games → higher weight.
"""
from __future__ import annotations

import datetime as _dt
import math
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pandas as pd
import pytest

# Ensure repo root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from signals.recent_form_variance import (
    RecentFormVariance,
    _coverage_weight_from_n,
    _shrink_to_league_prior,
    _SIGMA_MULT_MIN,
    _SIGMA_MULT_MAX,
)
from src.loop.signal import AsOfContext, Hypothesis, Verdict, TARGETS, SCOPES
from src.loop.store import PointInTimeStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(
    player_id: Optional[int] = 1628983,
    decision_time: Optional[_dt.datetime] = None,
    stat: Optional[str] = "pts",
    game_date: str = "2026-05-30",
    store: Optional[PointInTimeStore] = None,
) -> AsOfContext:
    """Build a minimal pregame AsOfContext."""
    if decision_time is None:
        decision_time = _dt.datetime(2026, 5, 30, 12, 0, 0)
    return AsOfContext(
        decision_time=decision_time,
        player_id=player_id,
        team="OKC",
        opp="DAL",
        game_id="0022400001",
        game_date=game_date,
        season="2025-26",
        is_home=True,
        scope="pregame",
        extra={"stat": stat} if stat else {},
    )


def _make_empty_df() -> pd.DataFrame:
    return pd.DataFrame()


def _make_conf_df(player_id: int, overall_mult: float, n_cv: int = 5) -> pd.DataFrame:
    """Return a minimal per_player_confidence DataFrame for one player."""
    return pd.DataFrame([{
        "player_id": player_id,
        "player_name": "Test Player",
        "n_cv_games": n_cv,
        "cv_volatility_mean": 2.0,
        "cv_volatility_std": 1.0,
        "n_games_stat": 50,
        "pts_cv": 0.35,
        "pts_confidence_mult": overall_mult,
        "reb_cv": 0.50,
        "reb_confidence_mult": overall_mult * 0.9,
        "ast_cv": 0.40,
        "ast_confidence_mult": overall_mult,
        "fg3m_cv": 0.55,
        "fg3m_confidence_mult": overall_mult,
        "stl_cv": 0.70,
        "stl_confidence_mult": overall_mult,
        "blk_cv": 0.80,
        "blk_confidence_mult": overall_mult,
        "tov_cv": 0.45,
        "tov_confidence_mult": overall_mult,
        "overall_confidence_mult": overall_mult,
        "segment": "medium",
    }])


def _make_consistency_df(
    player_id: int,
    asof_date: str,
    z: float,
    n_games: int = 7,
) -> pd.DataFrame:
    """Return a minimal cv_consistency_kelly DataFrame for one player."""
    return pd.DataFrame([{
        "player_id": player_id,
        "asof_date": pd.to_datetime(asof_date).date(),
        "n_cv_games_in_window": n_games,
        "cv_consistency_z": z,
        "cv_consistency_mult": 1.0 + z * 0.1,
        **{f"dim_{d}_cv": 0.5 for d in [
            "shots_per_possession", "paint_dwell_pct", "play_type_drive_pct",
            "play_type_isolation_pct", "play_type_post_pct", "play_type_transition_pct",
            "shot_zone_3pt_pct", "shot_zone_mid_range_pct", "shot_zone_paint_pct",
            "contested_shot_rate", "catch_shoot_pct", "avg_defender_distance",
            "avg_spacing", "avg_dribble_count", "possession_duration_avg",
            "avg_shot_clock_at_shot",
        ]},
        **{f"dim_{d}_z": z for d in [
            "shots_per_possession", "paint_dwell_pct", "play_type_drive_pct",
        ]},
    }])


# ---------------------------------------------------------------------------
# 1. Leak-safety assertions
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build() must NEVER consume data stamped after ctx.decision_time."""

    def test_future_consistency_record_is_invisible(self, tmp_path: Path) -> None:
        """A cv_consistency_kelly row dated TOMORROW must be invisible at TODAY.

        We patch the parquet loader to return a DataFrame containing one FUTURE
        row (asof_date = 2026-05-31) and verify that the signal does NOT see
        that row when decision_time = 2026-05-30.
        """
        player_id = 1234567
        today = _dt.datetime(2026, 5, 30, 10, 0, 0)
        tomorrow = "2026-05-31"

        # Build a consistency df with only a FUTURE row
        future_df = _make_consistency_df(player_id, tomorrow, z=5.0, n_games=7)
        future_df["asof_date"] = pd.to_datetime(future_df["asof_date"]).dt.date

        with patch("signals.recent_form_variance._load_cv_consistency",
                   return_value=future_df):
            with patch("signals.recent_form_variance._load_per_player_confidence",
                       return_value=_make_empty_df()):
                signal = RecentFormVariance()
                ctx = _make_ctx(player_id=player_id, decision_time=today)
                result = signal.build(ctx)

        assert result is not None, "Signal should produce output even with no CV data"
        # cv_consistency_z MUST NOT be 5.0 (the future row's value)
        assert result["cv_consistency_z"] != 5.0, (
            "Leak detected: signal read a cv_consistency row stamped AFTER "
            "ctx.decision_time.  Leak-safety contract violated."
        )
        # Neutral z when no past data is available
        assert result["cv_consistency_z"] == 0.0, (
            f"Expected neutral z=0.0, got {result['cv_consistency_z']}"
        )

    def test_past_consistency_record_is_visible(self, tmp_path: Path) -> None:
        """A row dated BEFORE decision_time MUST be visible."""
        player_id = 9876543
        today = _dt.datetime(2026, 5, 30, 10, 0, 0)
        yesterday = "2026-05-29"

        past_df = _make_consistency_df(player_id, yesterday, z=1.5, n_games=7)
        past_df["asof_date"] = pd.to_datetime(past_df["asof_date"]).dt.date

        with patch("signals.recent_form_variance._load_cv_consistency",
                   return_value=past_df):
            with patch("signals.recent_form_variance._load_per_player_confidence",
                       return_value=_make_empty_df()):
                signal = RecentFormVariance()
                ctx = _make_ctx(player_id=player_id, decision_time=today)
                result = signal.build(ctx)

        assert result is not None
        # Should see z = 1.5 from yesterday's row
        assert abs(result["cv_consistency_z"] - 1.5) < 1e-6, (
            f"Expected cv_consistency_z=1.5 from past row, got {result['cv_consistency_z']}"
        )

    def test_store_future_atlas_not_leaked(self, tmp_path: Path) -> None:
        """A prop_calibration atlas record stamped in the future must not affect sigma_mult.

        The store.read contract guarantees this; we verify that the signal
        correctly passes ctx.decision_time as the as_of argument.
        """
        store = PointInTimeStore(store_dir=tmp_path / "store", autoload=False)
        player_id = 1111111
        today = _dt.datetime(2026, 5, 30, 12, 0, 0)
        future_iso = "2026-06-01"

        # Write a FUTURE atlas record with extreme under-coverage (should inflate sigma)
        store.write_atlas(
            "player", player_id, "prop_calibration", future_iso,
            {"pts": {"n": 100, "interval_coverage": 0.10, "interval_nominal": 0.90}},
            provenance={"source": "test", "n": 100, "confidence": "high",
                        "as_of": future_iso},
        )

        with patch("signals.recent_form_variance._load_per_player_confidence",
                   return_value=_make_conf_df(player_id, overall_mult=1.0)):
            with patch("signals.recent_form_variance._load_cv_consistency",
                       return_value=_make_empty_df()):
                signal = RecentFormVariance(store=store)
                ctx = _make_ctx(player_id=player_id, decision_time=today, stat="pts")
                result = signal.build(ctx)

        assert result is not None
        # sigma_mult must NOT be inflated by the future record
        # (the leak-free store read with as_of=today should return None for the future record)
        # Since no past record exists, inflate path is skipped; sigma_mult stays near 1.0
        assert result["sigma_mult"] <= 1.5, (
            f"Future atlas record leaked: sigma_mult={result['sigma_mult']:.4f} "
            "is abnormally high (future coverage record was read)"
        )


# ---------------------------------------------------------------------------
# 2. Value-sanity assertions
# ---------------------------------------------------------------------------

class TestValueSanity:
    """Output values must be in basketball-plausible ranges."""

    def test_sigma_mult_in_valid_range(self) -> None:
        """sigma_mult must always be in [_SIGMA_MULT_MIN, _SIGMA_MULT_MAX]."""
        player_id = 201935

        conf_df = _make_conf_df(player_id, overall_mult=1.4, n_cv=7)
        consistency_df = _make_consistency_df(player_id, "2026-05-29", z=0.5)
        consistency_df["asof_date"] = pd.to_datetime(
            consistency_df["asof_date"]
        ).dt.date

        with patch("signals.recent_form_variance._load_per_player_confidence",
                   return_value=conf_df):
            with patch("signals.recent_form_variance._load_cv_consistency",
                       return_value=consistency_df):
                signal = RecentFormVariance()
                ctx = _make_ctx(player_id=player_id, stat="pts")
                result = signal.build(ctx)

        assert result is not None
        assert _SIGMA_MULT_MIN <= result["sigma_mult"] <= _SIGMA_MULT_MAX, (
            f"sigma_mult={result['sigma_mult']:.4f} outside [{_SIGMA_MULT_MIN}, {_SIGMA_MULT_MAX}]"
        )

    def test_coverage_weight_in_unit_interval(self) -> None:
        """coverage_weight must be in [0, 1]."""
        for n in (0, 1, 3, 7, 20):
            w = _coverage_weight_from_n(n)
            assert 0.0 <= w <= 1.0, f"coverage_weight={w} out of [0,1] for n={n}"

    def test_cv_consistency_z_is_float(self) -> None:
        """cv_consistency_z must be a finite float."""
        signal = RecentFormVariance()
        with patch("signals.recent_form_variance._load_per_player_confidence",
                   return_value=_make_empty_df()):
            with patch("signals.recent_form_variance._load_cv_consistency",
                       return_value=_make_empty_df()):
                ctx = _make_ctx(player_id=99999)
                result = signal.build(ctx)
        assert result is not None
        z = result["cv_consistency_z"]
        assert isinstance(z, float), f"cv_consistency_z should be float, got {type(z)}"
        assert math.isfinite(z), f"cv_consistency_z should be finite, got {z}"

    def test_missing_player_neutral_sigma(self) -> None:
        """An uncovered player (not in either parquet) gets sigma_mult≈1.0."""
        signal = RecentFormVariance()
        with patch("signals.recent_form_variance._load_per_player_confidence",
                   return_value=_make_empty_df()):
            with patch("signals.recent_form_variance._load_cv_consistency",
                       return_value=_make_empty_df()):
                ctx = _make_ctx(player_id=99999999)
                result = signal.build(ctx)
        assert result is not None
        # coverage_weight=0 → sigma_mult shrunk fully to prior 1.0
        assert abs(result["sigma_mult"] - 1.0) < 1e-9, (
            f"Uncovered player should have sigma_mult=1.0, got {result['sigma_mult']}"
        )
        assert result["coverage_weight"] == 0.0, (
            f"Uncovered player should have coverage_weight=0.0, got {result['coverage_weight']}"
        )

    def test_no_player_id_returns_none(self) -> None:
        """build() must return None when player_id is None."""
        signal = RecentFormVariance()
        ctx = _make_ctx(player_id=None)
        assert signal.build(ctx) is None

    def test_validate_output_passes(self) -> None:
        """validate_output must accept the dict returned by build."""
        signal = RecentFormVariance()
        with patch("signals.recent_form_variance._load_per_player_confidence",
                   return_value=_make_empty_df()):
            with patch("signals.recent_form_variance._load_cv_consistency",
                       return_value=_make_empty_df()):
                ctx = _make_ctx(player_id=1)
                result = signal.build(ctx)
        assert result is None or signal.validate_output(result), (
            f"validate_output rejected the dict: {result}"
        )


# ---------------------------------------------------------------------------
# 3. Directional / monotonicity assertions
# ---------------------------------------------------------------------------

class TestDirectional:
    """Signal values must move in the correct basketball direction."""

    def test_high_mult_player_wider_than_low(self) -> None:
        """A player with overall_confidence_mult=1.5 should get a higher sigma_mult
        than one with overall_confidence_mult=0.8 (both at full coverage_weight)."""
        player_id_high = 111
        player_id_low = 222
        conf_high = _make_conf_df(player_id_high, overall_mult=1.5, n_cv=10)
        conf_low = _make_conf_df(player_id_low, overall_mult=0.8, n_cv=10)
        conf_combined = pd.concat([conf_high, conf_low], ignore_index=True)

        with patch("signals.recent_form_variance._load_per_player_confidence",
                   return_value=conf_combined):
            with patch("signals.recent_form_variance._load_cv_consistency",
                       return_value=_make_empty_df()):
                signal = RecentFormVariance()
                ctx_high = _make_ctx(player_id=player_id_high)
                ctx_low = _make_ctx(player_id=player_id_low)
                res_high = signal.build(ctx_high)
                res_low = signal.build(ctx_low)

        assert res_high is not None and res_low is not None
        assert res_high["sigma_mult"] > res_low["sigma_mult"], (
            f"High-mult player should have wider sigma: "
            f"{res_high['sigma_mult']:.4f} vs {res_low['sigma_mult']:.4f}"
        )

    def test_more_cv_games_higher_coverage_weight(self) -> None:
        """Monotonicity: more CV games → higher coverage_weight."""
        weights = [_coverage_weight_from_n(n) for n in range(0, 12)]
        for i in range(1, len(weights)):
            assert weights[i] >= weights[i - 1], (
                f"coverage_weight not monotone: w[{i}]={weights[i]:.3f} "
                f"< w[{i-1}]={weights[i-1]:.3f}"
            )

    def test_shrinkage_toward_prior(self) -> None:
        """_shrink_to_league_prior: at weight=0 returns 1.0; at weight=1 returns mult."""
        assert abs(_shrink_to_league_prior(2.0, 0.0) - 1.0) < 1e-9
        assert abs(_shrink_to_league_prior(2.0, 1.0) - 2.0) < 1e-9
        half = _shrink_to_league_prior(2.0, 0.5)
        assert abs(half - 1.5) < 1e-9  # 0.5 * 2.0 + 0.5 * 1.0

    def test_atlas_inflation_increases_sigma_mult(self, tmp_path: Path) -> None:
        """A player with low interval_coverage in the prop_calibration atlas
        should receive a higher sigma_mult than one with good coverage."""
        store = PointInTimeStore(store_dir=tmp_path / "store", autoload=False)
        player_id = 5555555
        yesterday = "2026-05-29"
        today = _dt.datetime(2026, 5, 30, 12, 0, 0)

        # Write a PAST atlas record with severe under-coverage (0.70 vs 0.90 nominal)
        store.write_atlas(
            "player", player_id, "prop_calibration", yesterday,
            {"pts": {"n": 50, "interval_coverage": 0.70, "interval_nominal": 0.90}},
            provenance={"source": "test", "n": 50, "confidence": "high",
                        "as_of": yesterday},
        )

        conf_df = _make_conf_df(player_id, overall_mult=1.0, n_cv=7)
        with patch("signals.recent_form_variance._load_per_player_confidence",
                   return_value=conf_df):
            with patch("signals.recent_form_variance._load_cv_consistency",
                       return_value=_make_empty_df()):
                signal_with_store = RecentFormVariance(store=store)
                signal_no_store = RecentFormVariance(store=None)
                ctx = _make_ctx(player_id=player_id, decision_time=today, stat="pts")
                res_with = signal_with_store.build(ctx)
                res_without = signal_no_store.build(ctx)

        assert res_with is not None and res_without is not None
        assert res_with["sigma_mult"] >= res_without["sigma_mult"], (
            f"Atlas inflation should widen sigma_mult: "
            f"with={res_with['sigma_mult']:.4f} vs without={res_without['sigma_mult']:.4f}"
        )


# ---------------------------------------------------------------------------
# 4. Hypothesis and metadata
# ---------------------------------------------------------------------------

class TestMetadata:
    """Signal metadata must satisfy the Signal contract."""

    def test_hypothesis_returns_correct_fields(self) -> None:
        h = RecentFormVariance().hypothesis()
        assert isinstance(h, Hypothesis)
        assert h.name == "recent_form_variance"
        assert h.target == "sigma"
        assert h.scope == "both"

    def test_expected_verdict_is_variance_only(self) -> None:
        h = RecentFormVariance().hypothesis()
        assert h.expected_verdict in (
            Verdict.VARIANCE_ONLY, "VARIANCE_ONLY"
        ), f"Expected VARIANCE_ONLY, got {h.expected_verdict!r}"

    def test_target_and_scope_in_allowed_sets(self) -> None:
        s = RecentFormVariance()
        assert s.target in TARGETS, f"target={s.target!r} not in TARGETS"
        assert s.scope in SCOPES, f"scope={s.scope!r} not in SCOPES"

    def test_feature_names_match_emits(self) -> None:
        s = RecentFormVariance()
        expected = [f"recent_form_variance__{k}" for k in s.emits]
        assert s.feature_names() == expected, (
            f"feature_names()={s.feature_names()} != {expected}"
        )

    def test_reads_atlas_includes_prop_calibration(self) -> None:
        s = RecentFormVariance()
        assert "prop_calibration" in s.reads_atlas


# ---------------------------------------------------------------------------
# 5. Helper function unit tests
# ---------------------------------------------------------------------------

class TestHelpers:
    """Smoke tests for pure helper functions."""

    def test_coverage_weight_zero_games(self) -> None:
        assert _coverage_weight_from_n(0) == 0.0

    def test_coverage_weight_saturates(self) -> None:
        assert _coverage_weight_from_n(7) == 1.0
        assert _coverage_weight_from_n(100) == 1.0

    def test_coverage_weight_at_anchor_points(self) -> None:
        assert abs(_coverage_weight_from_n(1) - 0.20) < 1e-9
        assert abs(_coverage_weight_from_n(3) - 0.50) < 1e-9
        assert abs(_coverage_weight_from_n(7) - 1.00) < 1e-9

    def test_shrink_clamps_to_min(self) -> None:
        # Even if mult is very low, clamp to _SIGMA_MULT_MIN at weight=1
        clamped = _shrink_to_league_prior(0.01, 1.0)
        assert clamped == _SIGMA_MULT_MIN

    def test_shrink_clamps_to_max(self) -> None:
        clamped = _shrink_to_league_prior(999.0, 1.0)
        assert clamped == _SIGMA_MULT_MAX
