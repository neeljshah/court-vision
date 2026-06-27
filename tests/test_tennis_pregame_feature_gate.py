"""Per-file test for tennis pregame feature builder + gate.

Run ONLY this file (never the full suite):
  python -m pytest tests/test_tennis_pregame_feature_gate.py -q
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from domains.tennis.pregame_features import (
    build_features, elo_logit, FEATURE_COLS, _games_in_score,
)
from domains.tennis.pregame_feature_gate import (
    gate_feature_on_corpus, gate_feature, _bss,
)


def _toy_corpus(n: int = 80, seed: int = 0) -> pd.DataFrame:
    """Synthetic chronological corpus with a stable-orientation winner label."""
    rng = np.random.default_rng(seed)
    rows = []
    base = dt.date(2018, 1, 1)
    players = list(range(1, 13))
    strength = {p: rng.normal(0, 1) for p in players}
    for i in range(n):
        a, b = rng.choice(players, size=2, replace=False)
        p1, p2 = (int(a), int(b)) if a < b else (int(b), int(a))
        pw = 1.0 / (1.0 + np.exp(-(strength[p1] - strength[p2])))
        winner = 1 if rng.random() < pw else 2
        rows.append({
            "event_id": f"E{i}", "date": base + dt.timedelta(days=i * 3),
            "tour": "atp", "tourney_id": "T", "round": "R32", "match_num": i,
            "p1_id": p1, "p2_id": p2, "winner": winner,
            "surface": "Hard", "best_of": 3, "score": "6-3 6-4",
        })
    # ensure test rows exist beyond 2022 split used by gate
    df = pd.DataFrame(rows)
    df.loc[df.index[-30:], "date"] = [dt.date(2023, 1, 1) + dt.timedelta(days=k)
                                      for k in range(30)]
    return df


def test_games_in_score_counts():
    assert _games_in_score("6-3 6-4") == 19
    assert _games_in_score("") == 0
    assert _games_in_score(None) == 0


def test_build_features_columns_present_and_finite():
    df = build_features(_toy_corpus())
    for c in FEATURE_COLS + ("win_prob_p1", "p1_elo", "p2_elo"):
        assert c in df.columns, c
    feats = df[list(FEATURE_COLS)].to_numpy(dtype=float)
    assert np.isfinite(feats).all()


def test_features_leakfree_first_row_is_neutral():
    """First match: no prior data -> recent_form/h2h must be 0 (neutral)."""
    df = build_features(_toy_corpus())
    assert abs(float(df["recent_form_diff"].iloc[0])) < 1e-12
    assert abs(float(df["h2h_diff"].iloc[0])) < 1e-12


def test_elo_logit_matches_winprob():
    df = build_features(_toy_corpus())
    lg = elo_logit(df)
    p = 1.0 / (1.0 + np.exp(-lg))
    assert np.allclose(p, df["win_prob_p1"].to_numpy(dtype=float), atol=1e-6)


def test_gate_runs_and_reports_brier_and_guard():
    df = build_features(_toy_corpus(n=120, seed=3))
    r = gate_feature_on_corpus(df, "recent_form_diff")
    assert {"brier_base", "brier_feat", "brier_delta", "dm_p",
            "feat_better", "base_degenerate"} <= set(r)
    assert r["n_test"] > 0
    assert 0.0 <= r["brier_base"] <= 1.0


def test_cross_corpus_verdict_is_one_of_known():
    a = build_features(_toy_corpus(n=120, seed=1))
    b = build_features(_toy_corpus(n=120, seed=2))
    v = gate_feature(a, b, "h2h_diff")
    assert v["verdict"] in {"SHIP", "PARTIAL", "REJECT", "INVALID_BASE"}


def test_bss_of_perfect_vs_constant():
    y = np.array([1.0, 0.0, 1.0, 0.0])
    p_good = np.array([0.9, 0.1, 0.9, 0.1])
    assert _bss(p_good, y) > 0.0
