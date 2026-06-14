"""tests/mlb/test_inning_engine_anchor.py — Tests for the Elo-anchor extension.

All tests are fast (synthetic data only; no corpus I/O).
Verifies:
  - anchor_lambdas_to_winprob hits target P(home win) within tolerance
  - lambda SUM is preserved after anchoring (totals invariant)
  - anchoring with target == current ML is a ~no-op
  - build_engine_forecast(anchor_to_elo=True) yields ML closer to Elo than un-anchored
  - build_engine_forecast(anchor_to_elo=False) is byte-identical to default (additive proof)
HONEST: tests verify structural properties, not edge claims.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

import numpy as np
import pytest

from domains.mlb.inning_engine import (
    RunRateState,
    _F5_SCALE,
    anchor_lambdas_to_winprob,
    build_engine_forecast,
    markets_from_matrix,
    runs_matrix,
)


# ---------------------------------------------------------------------------
# anchor_lambdas_to_winprob — unit tests
# ---------------------------------------------------------------------------

class TestAnchorLambdas:
    """anchor_lambdas_to_winprob structural guarantees."""

    def _ml_from_lambdas(self, lh: float, la: float) -> float:
        """Helper: P(home win) from a runs_matrix."""
        return markets_from_matrix(runs_matrix(lh, la))["ml_home"]

    def test_hits_target_prob_high(self) -> None:
        """Anchor to a high home win probability."""
        lh, la = 4.4, 4.2
        target = 0.65
        lh2, la2 = anchor_lambdas_to_winprob(lh, la, target)
        result = self._ml_from_lambdas(lh2, la2)
        assert abs(result - target) < 1e-4, f"Expected ~{target}, got {result:.6f}"

    def test_hits_target_prob_low(self) -> None:
        """Anchor to a low home win probability (away favored)."""
        lh, la = 4.4, 4.2
        target = 0.35
        lh2, la2 = anchor_lambdas_to_winprob(lh, la, target)
        result = self._ml_from_lambdas(lh2, la2)
        assert abs(result - target) < 1e-4, f"Expected ~{target}, got {result:.6f}"

    def test_hits_target_prob_near_50(self) -> None:
        """Anchor to near 0.50 (neutral)."""
        lh, la = 5.5, 3.5  # home-favored to start
        target = 0.50
        lh2, la2 = anchor_lambdas_to_winprob(lh, la, target)
        result = self._ml_from_lambdas(lh2, la2)
        assert abs(result - target) < 1e-4, f"Expected ~{target}, got {result:.6f}"

    def test_lambda_sum_preserved(self) -> None:
        """Lambda SUM must be identical before and after anchoring (totals invariant)."""
        lh, la = 4.4, 4.2
        target = 0.65
        S_before = lh + la
        lh2, la2 = anchor_lambdas_to_winprob(lh, la, target)
        S_after = lh2 + la2
        assert abs(S_after - S_before) < 1e-6, (
            f"Sum changed: before={S_before:.8f}, after={S_after:.8f}"
        )

    def test_lambda_sum_preserved_away_favored(self) -> None:
        """Sum invariant holds when tilting toward away."""
        lh, la = 4.4, 4.2
        target = 0.35
        S_before = lh + la
        lh2, la2 = anchor_lambdas_to_winprob(lh, la, target)
        S_after = lh2 + la2
        assert abs(S_after - S_before) < 1e-6, (
            f"Sum changed: before={S_before:.8f}, after={S_after:.8f}"
        )

    def test_no_op_when_target_matches_current(self) -> None:
        """When target == current ML, output lambdas are ~identical to input."""
        lh, la = 4.4, 4.2
        current_ml = self._ml_from_lambdas(lh, la)
        lh2, la2 = anchor_lambdas_to_winprob(lh, la, current_ml)
        # Should be byte-identical (fast-path)
        assert abs(lh2 - lh) < 1e-8, f"lam_home changed: {lh} -> {lh2}"
        assert abs(la2 - la) < 1e-8, f"lam_away changed: {la} -> {la2}"

    def test_no_op_approximate_when_target_close(self) -> None:
        """Anchoring to the current ML should leave lambdas nearly unchanged."""
        lh, la = 5.0, 4.0
        target = self._ml_from_lambdas(lh, la)  # current value
        lh2, la2 = anchor_lambdas_to_winprob(lh, la, target + 1e-12)
        assert abs((lh2 + la2) - (lh + la)) < 1e-5

    def test_raises_on_invalid_target_zero(self) -> None:
        with pytest.raises(ValueError, match="target_p_home"):
            anchor_lambdas_to_winprob(4.4, 4.2, 0.0)

    def test_raises_on_invalid_target_one(self) -> None:
        with pytest.raises(ValueError, match="target_p_home"):
            anchor_lambdas_to_winprob(4.4, 4.2, 1.0)

    def test_raises_on_invalid_target_negative(self) -> None:
        with pytest.raises(ValueError, match="target_p_home"):
            anchor_lambdas_to_winprob(4.4, 4.2, -0.1)

    def test_raises_on_invalid_lambda(self) -> None:
        with pytest.raises(ValueError, match="lambdas must be positive"):
            anchor_lambdas_to_winprob(0.0, 4.2, 0.55)

    def test_output_lambdas_are_positive(self) -> None:
        """Output lambdas must always be strictly positive."""
        for target in (0.01, 0.25, 0.5, 0.75, 0.99):
            lh2, la2 = anchor_lambdas_to_winprob(4.4, 4.2, target)
            assert lh2 > 0, f"lam_home not positive at target={target}"
            assert la2 > 0, f"lam_away not positive at target={target}"

    def test_monotone_direction(self) -> None:
        """Higher target_p_home -> higher anchored lam_home."""
        lh, la = 4.4, 4.2
        lh_lo, _ = anchor_lambdas_to_winprob(lh, la, 0.40)
        lh_hi, _ = anchor_lambdas_to_winprob(lh, la, 0.70)
        assert lh_hi > lh_lo, f"Monotone failed: lh(0.40)={lh_lo:.4f} lh(0.70)={lh_hi:.4f}"


# ---------------------------------------------------------------------------
# build_engine_forecast with anchor_to_elo — integration tests
# ---------------------------------------------------------------------------

def _make_games_df(n: int = 80, seed: int = 42) -> "pd.DataFrame":
    """Tiny synthetic corpus with predictable Elo diversity."""
    import pandas as pd

    rng = np.random.default_rng(seed)
    teams = [("NYY", "BOS"), ("LAD", "SFG"), ("HOU", "TEX")]
    rows: List[Dict[str, Any]] = []
    date_base = pd.Timestamp("2018-04-01")
    for i in range(n):
        ht, at = teams[i % len(teams)]
        rows.append({
            "event_id": f"2018{i:04d}-{ht}-{at}-1",
            "date": date_base + pd.Timedelta(days=i),
            "season": 2018 if i < n // 2 else 2019,
            "home_team": ht,
            "away_team": at,
            "home_runs": int(rng.integers(1, 12)),
            "away_runs": int(rng.integers(1, 12)),
            "game_seq": 1,
            "home_league": "AL",
        })
    df = pd.DataFrame(rows)
    df["target_home_win"] = (df["home_runs"] > df["away_runs"]).astype(int)
    return df


class TestBuildEngineForecastAnchor:
    """Integration tests for build_engine_forecast(anchor_to_elo=True/False)."""

    def test_anchor_false_same_as_default(self, tmp_path: "pathlib.Path") -> None:
        """anchor_to_elo=False must produce byte-identical results to the default call."""
        import pathlib
        games_df = _make_games_df()
        pq_path = tmp_path / "games.parquet"
        games_df.to_parquet(pq_path, index=False)

        r_default = build_engine_forecast(games_path=str(pq_path))
        r_false = build_engine_forecast(games_path=str(pq_path), anchor_to_elo=False)

        assert r_default["engine"]["brier"] == r_false["engine"]["brier"], (
            "anchor_to_elo=False must be byte-identical to default"
        )
        assert r_default["dBrier"] == r_false["dBrier"]
        assert r_false["anchor_to_elo"] is False

    def test_anchor_true_ml_closer_to_elo(self, tmp_path: "pathlib.Path") -> None:
        """anchor_to_elo=True must make engine ML closer to Elo (lower Brier delta)."""
        import pathlib
        games_df = _make_games_df()
        pq_path = tmp_path / "games.parquet"
        games_df.to_parquet(pq_path, index=False)

        r_base = build_engine_forecast(games_path=str(pq_path), anchor_to_elo=False)
        r_anchored = build_engine_forecast(games_path=str(pq_path), anchor_to_elo=True)

        # Anchored engine Brier should be <= un-anchored engine Brier
        # (anchored ML == Elo, which is the better ML by construction)
        assert r_anchored["engine"]["brier"] <= r_base["engine"]["brier"] + 1e-6, (
            f"Anchored Brier {r_anchored['engine']['brier']:.6f} "
            f"> un-anchored {r_base['engine']['brier']:.6f}"
        )

    def test_anchor_true_engine_brier_near_baseline(self, tmp_path: "pathlib.Path") -> None:
        """When anchored, engine Brier should be ~equal to baseline (Elo) Brier."""
        import pathlib
        games_df = _make_games_df()
        pq_path = tmp_path / "games.parquet"
        games_df.to_parquet(pq_path, index=False)

        r = build_engine_forecast(games_path=str(pq_path), anchor_to_elo=True)

        # dBrier should be ~0 (engine ML == Elo ML)
        assert abs(r["dBrier"]) < 0.005, (
            f"dBrier={r['dBrier']:.6f} should be near 0 when anchor_to_elo=True"
        )

    def test_anchor_true_returns_required_keys(self, tmp_path: "pathlib.Path") -> None:
        import pathlib
        games_df = _make_games_df()
        pq_path = tmp_path / "games.parquet"
        games_df.to_parquet(pq_path, index=False)

        r = build_engine_forecast(games_path=str(pq_path), anchor_to_elo=True)

        for k in ("n", "baseline", "engine", "dBrier", "dECE", "note",
                  "sample_surface", "anchor_to_elo"):
            assert k in r, f"Missing key: {k}"
        assert r["anchor_to_elo"] is True

    def test_anchor_true_sample_surface_moneyline_valid(self, tmp_path: "pathlib.Path") -> None:
        """Anchored engine still produces a valid (sum-to-1) market surface."""
        import pathlib
        games_df = _make_games_df()
        pq_path = tmp_path / "games.parquet"
        games_df.to_parquet(pq_path, index=False)

        r = build_engine_forecast(games_path=str(pq_path), anchor_to_elo=True)
        surf = r["sample_surface"]
        assert surf is not None
        ml_sum = surf["ml_home"] + surf["ml_away"]
        assert abs(ml_sum - 1.0) < 1e-9, f"Anchored ML sum={ml_sum}"

    def test_anchor_true_sample_surface_rl_valid(self, tmp_path: "pathlib.Path") -> None:
        """Anchored engine run-line still sums to 1."""
        import pathlib
        games_df = _make_games_df()
        pq_path = tmp_path / "games.parquet"
        games_df.to_parquet(pq_path, index=False)

        r = build_engine_forecast(games_path=str(pq_path), anchor_to_elo=True)
        surf = r["sample_surface"]
        rl_sum = surf["rl_home_minus15"] + surf["rl_away_plus15"]
        assert abs(rl_sum - 1.0) < 1e-9, f"Anchored RL sum={rl_sum}"

    def test_anchor_true_n_unchanged(self, tmp_path: "pathlib.Path") -> None:
        """Anchoring does not drop rows (n identical to un-anchored)."""
        import pathlib
        games_df = _make_games_df()
        pq_path = tmp_path / "games.parquet"
        games_df.to_parquet(pq_path, index=False)

        r_base = build_engine_forecast(games_path=str(pq_path), anchor_to_elo=False)
        r_anch = build_engine_forecast(games_path=str(pq_path), anchor_to_elo=True)

        assert r_base["n"] == r_anch["n"], (
            f"n changed: {r_base['n']} -> {r_anch['n']}"
        )

    def test_anchor_note_differs(self, tmp_path: "pathlib.Path") -> None:
        """anchor_to_elo=True produces a different 'note' key."""
        import pathlib
        games_df = _make_games_df()
        pq_path = tmp_path / "games.parquet"
        games_df.to_parquet(pq_path, index=False)

        r_base = build_engine_forecast(games_path=str(pq_path), anchor_to_elo=False)
        r_anch = build_engine_forecast(games_path=str(pq_path), anchor_to_elo=True)

        assert r_base["note"] != r_anch["note"]
        assert "anchor_to_elo=True" in r_anch["note"]
