"""Per-file test for scripts.platformkit.gate_run_mlb_sp_fatigue_kprop.

Asserts the two load-bearing properties:
  1. HONEST on the REAL on-disk reality: run() returns INSUFFICIENT_DATA with explicit
     reason codes and ZERO per-start label coverage -- the leak-free per-start K LABEL
     is unbuildable on-disk (2026-only K source, no SP identity), so the gate cannot
     run. NOT 0-filled, NOT a forced SHIP.
  2. The GATE MACHINERY is real + UNWEAKENED: on a SYNTHETIC labelled corpus the
     walk-forward scorer, clustered-DM, degenerate-base guard, and cross-corpus verdict
     all run, and a PLANTED-NULL pure-noise feature REJECTS through the IDENTICAL gate
     (proves the gate CAN fail a signal). Also: a feature that is the label-with-noise
     (an oracle) is detected as feat_better, proving the scorer can also PASS a real one.
Run ONLY this file:
  python -m pytest scripts/platformkit/test_gate_run_mlb_sp_fatigue_kprop.py -q
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.platformkit import gate_run_mlb_sp_fatigue_kprop as G

_REPO = Path(__file__).resolve().parents[2]


def _synthetic_labelled(season: int, n: int = 240, seed: int = 1) -> pd.DataFrame:
    """A labelled per-start corpus matching the builder's column contract so the gate
    machinery can be exercised. label_k depends on the BASE (so the base is skillful)
    plus mild noise; the profile feats are near-noise (expected REJECT/PARTIAL)."""
    rng = np.random.default_rng(seed)
    teams = [f"T{i:02d}" for i in range(12)]
    rows = []
    for k in range(n):
        team = teams[k % len(teams)]
        base = 5.0 + rng.normal(0, 1.0)            # recent-K-rate prior
        label = base + rng.normal(0, 1.2)          # label tracks base + noise -> skillful base
        rows.append({
            "game_id": f"G{k:04d}", "date": pd.Timestamp("2022-04-01") + pd.Timedelta(days=k),
            "season": season, "pitch_team": team, "pitch_side": "home",
            G._BASE_COL: base, G._LABEL_COL: max(0.0, label),
            "prof_mean_early_velo": rng.normal(93, 1),
            "prof_velo_decline_slope": rng.normal(0, 0.05),
            "prof_pitch_mix_entropy": rng.normal(1.0, 0.1),
            "prof_frac_breaking": rng.normal(0.3, 0.05),
            "prof_n_pitches": rng.normal(90, 8),
            "prof_n_prior": 3,
        })
    df = pd.DataFrame(rows)
    rng2 = np.random.default_rng(seed + season)
    df[G._NULL_FEAT] = rng2.standard_normal(len(df))
    return df


# --------------------------------------------------------------------------- #
# 1. HONEST on the real on-disk corpora.
# --------------------------------------------------------------------------- #
def test_run_real_insufficient_data_honest():
    res = G.run(eps=0.05, seed=0)
    assert res["verdict"] == "INSUFFICIENT_DATA"
    # explicit reason codes, not a silent / fabricated pass.
    assert res.get("reasons"), "must surface reason codes"
    assert any(r in ("NO_SEASON_OVERLAP", "NO_SP_IDENTITY", "NO_LEAKFREE_K_LABEL",
                     "NO_K_SOURCE") for r in res["reasons"])
    # ZERO per-start label coverage in both corpora -> nothing 0-filled into a win.
    assert res["n_starts_with_label"][2022] == 0
    assert res["n_starts_with_label"][2023] == 0
    # no $/edge field anywhere; vs-close stays UNPROVEN.
    assert "UNPROVEN" in res["vs_close"]
    assert "edge" not in str(res).lower() or "not a market edge" in res["vs_close"].lower()


def test_load_corpus_returns_none_without_label():
    frame, status = G.load_corpus(2022, seed=0)
    # real 2022 has a profile but NO leak-free label -> frame is None, status carries reasons.
    assert frame is None
    assert status.get("status") == "INSUFFICIENT_DATA"
    assert status.get("reasons")


# --------------------------------------------------------------------------- #
# 2. Gate machinery is real + unweakened (synthetic labelled corpus).
# --------------------------------------------------------------------------- #
def test_scorer_runs_and_base_is_skillful():
    df = _synthetic_labelled(2022)
    base = G.score_corpus(df, [G._BASE_COL])
    assert base["scored"]
    # base tracks the label -> pinball beats a constant-mean baseline (skillful, not degenerate).
    g = G.gate_corpus(df, [G._NULL_FEAT], eps=0.05)
    assert g["scored"]
    assert g["base_bss"] > G._MIN_BSS
    assert not g["degenerate"]


def test_planted_null_rejects_through_identical_gate():
    """Cross-corpus planted-null MUST reject -> the gate can fail a worthless signal."""
    c22 = _synthetic_labelled(2022, seed=1)
    c23 = _synthetic_labelled(2023, seed=2)
    null = G.gate_both(c22, c23, [G._NULL_FEAT], eps=0.05)
    assert null["verdict"] in ("REJECT", "PARTIAL", "INVALID_BASE")


def test_oracle_feature_is_detected_better():
    """A label-correlated feature must register as feat_better in >=1 dir -> scorer can
    PASS a real signal (proves the REJECT of noise is not a stuck 'always reject')."""
    df = _synthetic_labelled(2022, seed=5)
    rng = np.random.default_rng(7)
    df["prof_oracle"] = df[G._LABEL_COL].to_numpy() + rng.normal(0, 0.4, len(df))
    g = G.gate_corpus(df, ["prof_oracle"], eps=0.05)
    assert g["scored"]
    assert g["feat_better"]  # lowers pinball AND brier vs base-only


def test_profile_verdict_is_reject_leaning_on_noise_profile():
    """With near-noise profile feats, the cross-corpus profile verdict must NOT be SHIP."""
    c22 = _synthetic_labelled(2022, seed=11)
    c23 = _synthetic_labelled(2023, seed=12)
    prof = G.gate_both(c22, c23, list(G._PROFILE_FEATS), eps=0.05)
    assert prof["verdict"] in ("REJECT", "PARTIAL", "INVALID_BASE", "INSUFFICIENT_DATA")
