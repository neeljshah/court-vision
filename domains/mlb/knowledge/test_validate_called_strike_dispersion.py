"""Per-file test for knowledge.validate_called_strike_dispersion. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/knowledge/test_validate_called_strike_dispersion.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.knowledge import validate_called_strike_dispersion as vcs


def _synthetic_pitch_df(n_games=40, seed=7, dispersed=True) -> pd.DataFrame:
    """One row per taken borderline pitch, plus enough non-borderline/swing
    rows mixed in to exercise the zone/description filter. Each game gets a
    per-game called-strike rate drawn from a Beta (dispersed=True, real
    game-to-game variation) or a fixed rate (dispersed=False, pure binomial
    noise) so the two self-check branches have real signal either way."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        n = 60
        rate = rng.beta(2, 20) if dispersed else 0.10
        n_calls = rng.binomial(n, rate)
        for i in range(n):
            desc = "called_strike" if i < n_calls else "ball"
            rows.append({"game_pk": g, "zone": 12, "description": desc,
                         "home_team": "A", "away_team": "B",
                         "post_home_score": 3, "post_away_score": 2})
        # non-borderline/non-taken noise the filter must drop
        rows.append({"game_pk": g, "zone": 5, "description": "hit_into_play",
                     "home_team": "A", "away_team": "B",
                     "post_home_score": 3, "post_away_score": 2})
    return pd.DataFrame(rows)


def test_per_game_frame_drops_non_edge_and_non_taken_rows():
    df = _synthetic_pitch_df(n_games=3)
    g = vcs.per_game_frame(df)
    assert set(g["game_pk"]) == {0, 1, 2}
    assert (g["n"] == 60).all()  # the extra hit_into_play/zone-5 row per game is excluded


def test_dispersion_confirmed_local_on_real_dispersion():
    df = _synthetic_pitch_df(n_games=80, dispersed=True)
    g = vcs.per_game_frame(df)
    r = vcs.called_strike_dispersion_exceeds_binomial_noise(g)
    assert set(r) >= {"hypothesis", "verdict", "phi", "p", "n"}
    assert r["verdict"] == "CONFIRMED_LOCAL"
    assert r["phi"] > vcs.PHI_THRESHOLD


def test_dispersion_null_local_on_fixed_rate():
    df = _synthetic_pitch_df(n_games=80, dispersed=False)
    g = vcs.per_game_frame(df)
    r = vcs.called_strike_dispersion_exceeds_binomial_noise(g)
    assert r["verdict"] == "NULL_LOCAL"


def test_deviation_relates_to_total_runs_not_testable_below_min_games():
    g = vcs.per_game_frame(_synthetic_pitch_df(n_games=2))
    r = vcs.called_strike_deviation_relates_to_total_runs(g)
    assert r["verdict"] == "NOT_TESTABLE" and r["p"] is None


def test_run_writes_two_edge_free_rows(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vcs, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vcs, "load_season", lambda season=2025: _synthetic_pitch_df(n_games=40))
    rows = vcs.run()
    assert len(rows) == 2
    assert all(r["edge_claimed"] is False and r["sport"] == "mlb" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 2
