"""The gate is only trusted if it can BOTH detect signal and refuse noise."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.intel_weighting.claim_features import window_to_season
from scripts.platformkit.intel_weighting.relevance_gate import run_gate


def _synth(n=600, seed=0):
    rng = np.random.default_rng(seed)
    teams = [f"T{i:02d}" for i in range(20)]
    strength = {t: rng.normal() for t in teams}
    home = rng.choice(teams, n)
    away = rng.choice(teams, n)
    ok = home != away
    home, away = home[ok], away[ok]
    # outcome driven by strength diff (base_logit is uninformative -> zeros)
    z = 1.8 * np.array([strength[h] - strength[a] for h, a in zip(home, away)])
    y = (rng.random(len(z)) < 1 / (1 + np.exp(-z))).astype(float)
    df = pd.DataFrame({
        "home_team": home, "away_team": away, "season": "2025-26",
        "home_win": y, "game_id": [f"g{i}" for i in range(len(y))],
    })
    base_logit = np.zeros(len(df))
    mask = np.ones(len(df), dtype=bool)
    return df, base_logit, mask, strength, {t: rng.normal() for t in teams}


def test_gate_detects_planted_signal():
    df, bl, mask, strength, noise = _synth()
    res = run_gate("nba", "fam", "planted", strength, df, bl, mask, "team")
    assert res.verdict == "MATTERS", (res.verdict, res.delta, res.dm_p)
    assert res.delta > 0 and res.delta_trunc80 > 0


def test_gate_refuses_pure_noise():
    df, bl, mask, strength, noise = _synth()
    res = run_gate("nba", "fam", "noise", noise, df, bl, mask, "team")
    assert res.verdict == "NULL", (res.verdict, res.delta, res.dm_p)


def test_untestable_when_too_few_oos():
    df, bl, mask, strength, _ = _synth(n=120)  # 0.4*~114 test < 60 -> UNTESTABLE
    res = run_gate("nba", "fam", "planted", strength, df, bl, mask, "team")
    assert res.verdict == "UNTESTABLE"


def test_window_to_season_rejects_splits():
    assert window_to_season("season_2024_25") == "2024-25"
    assert window_to_season("season_2024_25_home") is None
    assert window_to_season("career_to_date") is None
    assert window_to_season("2024-25") == "2024-25"
