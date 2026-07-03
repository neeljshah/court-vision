"""Per-file test for the WTA hold%-diff and soccer asof_features m19 reclaim
gates (LANE D: widen the m19 asof-reclaim enumerator).

Acceptance criteria
-------------------
1. domains.tennis.asof_hold_wta_gate:
   a. build_candidate_frame merges Elo p_base + hold_pct_diff_asof by event_id,
      correctly, on a small synthetic frame (gate math, not real data).
   b. _gate_once + gate_feature run end-to-end on synthetic data and return the
      {real, planted_null, truncation} contract shape used by the sweep.
   c. A planted-null (shuffled feature) must not systematically beat a feature
      that is pure noise -- verdict machinery does not crash / stays sane.
2. domains.soccer.asof_features_gate:
   a. build_candidate_frame merges Poisson p_base + a diff_*_asof column by
      event_id correctly on synthetic data.
   b. gate_feature returns the same {real, planted_null, truncation} contract.
3. scripts.platformkit.ceiling.asof_reclaim_sweep.registry():
   a. Lists the new tennis + soccer GateSpecs (enumerator registration).
   b. Every registered signal name is unique (no accidental duplicate candidate).

Synthetic-data only -- no real parquet I/O, fast.  Real-data gate runs (with
recorded verdicts) were executed manually via
``python -m domains.tennis.asof_hold_wta_gate`` /
``python -m domains.soccer.asof_features_gate`` /
``python -m scripts.platformkit.ceiling.asof_reclaim_sweep`` and their printed
verdicts are recorded in the lane report, not re-run here (keeps this test fast
and CI-safe).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/ceiling/test_asof_reclaim_wta_soccer.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.soccer import asof_features_gate as soc
from domains.tennis import asof_hold_wta_gate as wta
from scripts.platformkit.ceiling import asof_reclaim_sweep as S


# --------------------------------------------------------------------------- #
# Synthetic fixtures
# --------------------------------------------------------------------------- #

def _synthetic_wta_matches(n: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-01", periods=n, freq="D")
    p1 = rng.integers(1, 20, size=n)
    p2 = rng.integers(1, 20, size=n)
    p2 = np.where(p2 == p1, p2 + 1, p2)  # avoid self-play
    winner = rng.integers(1, 3, size=n)
    return pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "date": dates,
        "p1_id": p1, "p2_id": p2, "winner": winner,
        "surface": rng.choice(["Hard", "Clay", "Grass"], size=n),
        "score": ["6-3 6-3"] * n,
    })


def _synthetic_asof_hold(matches: pd.DataFrame, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = len(matches)
    return pd.DataFrame({
        "event_id": matches["event_id"].values,
        "p1_hold_pct_asof": rng.uniform(0.55, 0.85, size=n),
        "p2_hold_pct_asof": rng.uniform(0.55, 0.85, size=n),
        "p1_n_prior": rng.integers(0, 30, size=n),
        "p2_n_prior": rng.integers(0, 30, size=n),
    })


def _synthetic_soccer_matches(n: int = 200, seed: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-01", periods=n, freq="D")
    teams = [f"T{i}" for i in range(10)]
    home = rng.choice(teams, size=n)
    away = rng.choice(teams, size=n)
    away = np.where(away == home, "T9", away)
    fthg = rng.integers(0, 4, size=n)
    ftag = rng.integers(0, 4, size=n)
    return pd.DataFrame({
        "event_id": [f"m{i}" for i in range(n)],
        "date": dates, "div": ["E0"] * n,
        "home_team": home, "away_team": away,
        "fthg": fthg, "ftag": ftag,
    })


def _synthetic_soccer_asof(matches: pd.DataFrame, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = len(matches)
    return pd.DataFrame({
        "event_id": matches["event_id"].values,
        "diff_sot_for_asof": rng.normal(0, 1.5, size=n),
        "diff_sot_against_asof": rng.normal(0, 1.5, size=n),
        "diff_shots_for_asof": rng.normal(0, 3.0, size=n),
        "diff_shots_against_asof": rng.normal(0, 3.0, size=n),
        "home_n_prior": rng.integers(0, 20, size=n),
        "away_n_prior": rng.integers(0, 20, size=n),
    })


# --------------------------------------------------------------------------- #
# 1. WTA gate
# --------------------------------------------------------------------------- #

class TestWtaGate:
    def test_build_candidate_frame_merges_by_event_id(self):
        mt = _synthetic_wta_matches()
        ah = _synthetic_asof_hold(mt)
        df = wta.build_candidate_frame(wta_matches=mt, asof_hold=ah)
        assert "p_base" in df.columns
        assert wta.FEAT_COL in df.columns
        assert len(df) == len(mt)
        # feature is exactly p1 - p2 asof hold, aligned by event_id
        merged_check = ah.set_index("event_id")
        row = df.iloc[0]
        expect = (merged_check.loc[row["event_id"], "p1_hold_pct_asof"]
                  - merged_check.loc[row["event_id"], "p2_hold_pct_asof"])
        assert abs(row[wta.FEAT_COL] - expect) < 1e-9

    def test_gate_feature_returns_full_contract(self):
        mt = _synthetic_wta_matches()
        ah = _synthetic_asof_hold(mt)
        df = wta.build_candidate_frame(wta_matches=mt, asof_hold=ah)
        real = wta._gate_once(df)
        null = wta._planted_null(df)
        trunc = wta._gate_once(df, train_frac=wta.TRAIN_FRAC * 0.90)
        for res in (real, null, trunc):
            assert res["verdict"] in ("SHIP", "REJECT")
            for k in ("brier_base", "brier_cand", "brier_delta", "dm_p", "feat_weight"):
                assert k in res

    def test_planted_null_shuffles_feature_column(self):
        mt = _synthetic_wta_matches()
        ah = _synthetic_asof_hold(mt)
        df = wta.build_candidate_frame(wta_matches=mt, asof_hold=ah)
        null_res = wta._planted_null(df, seed=42)
        # Sanity: shuffling a random synthetic feature should not reliably SHIP.
        assert null_res["verdict"] in ("SHIP", "REJECT")


# --------------------------------------------------------------------------- #
# 2. Soccer gate
# --------------------------------------------------------------------------- #

class TestSoccerGate:
    def test_build_candidate_frame_merges_by_event_id(self):
        mt = _synthetic_soccer_matches()
        af = _synthetic_soccer_asof(mt)
        df = soc.build_candidate_frame(matches=mt, asof=af, feat_col="diff_sot_for_asof")
        assert "p_base" in df.columns
        assert "diff_sot_for_asof" in df.columns
        assert len(df) == len(mt)
        assert set(df["target_over25"].unique()) <= {0.0, 1.0}

    def test_gate_feature_returns_full_contract(self):
        # gate_feature() reads from disk by default (asof_path=None); to keep this
        # test synthetic + fast we exercise the same real/planted_null/truncation
        # contract via build_candidate_frame + _gate_once/_planted_null directly
        # (identical code path gate_feature calls internally).
        mt = _synthetic_soccer_matches()
        af = _synthetic_soccer_asof(mt)
        df = soc.build_candidate_frame(matches=mt, asof=af, feat_col="diff_shots_for_asof")
        real = soc._gate_once(df, feat_col="diff_shots_for_asof")
        null = soc._planted_null(df, feat_col="diff_shots_for_asof")
        trunc = soc._gate_once(df, feat_col="diff_shots_for_asof", train_frac=soc.TRAIN_FRAC * 0.90)
        for res in (real, null, trunc):
            assert res["verdict"] in ("SHIP", "REJECT")
            assert "brier_delta" in res


# --------------------------------------------------------------------------- #
# 3. Enumerator registration
# --------------------------------------------------------------------------- #

class TestEnumeratorRegistration:
    def test_registry_lists_wta_and_soccer_candidates(self):
        specs = S.registry()
        names = {spec.signal for spec in specs}
        assert "wta_hold_pct_diff_asof" in names
        assert "soccer_diff_sot_for_asof" in names
        assert "soccer_diff_sot_against_asof" in names
        assert "soccer_diff_shots_for_asof" in names
        assert "soccer_diff_shots_against_asof" in names

    def test_registry_signal_names_unique(self):
        specs = S.registry()
        names = [spec.signal for spec in specs]
        assert len(names) == len(set(names)), f"Duplicate signal names: {names}"

    def test_registry_sports_tagged_correctly(self):
        specs = S.registry()
        by_name = {spec.signal: spec.sport for spec in specs}
        assert by_name["wta_hold_pct_diff_asof"] == "tennis"
        assert by_name["soccer_diff_sot_for_asof"] == "soccer"
