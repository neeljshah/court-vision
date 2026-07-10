"""Per-file test for knowledge.validate_transition_frequency. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/knowledge/test_validate_transition_frequency.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.basketball_nba.knowledge import validate_transition_frequency as vtf


def test_build_team_game_transition_frame_reads_real_pbp_files():
    """Smoke test on real disk data (small limit, matches house convention in
    composition/test_transition_flag.py) -- shape + leak-free column bounds."""
    tg = vtf.build_team_game_transition_frame(limit=20)
    assert len(tg) > 0
    assert set(tg["is_home"].unique()) <= {0, 1}
    assert (tg["transition_rate"] >= 0).all() and (tg["transition_rate"] <= 1).all()
    assert (tg["n_transition"] <= tg["n_shots"]).all()


def _synthetic_team_games(n_games: int = 40, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    teams = [f"T{i}" for i in range(12)]
    start = pd.Timestamp("2025-10-01")
    rows = []
    team_bias = {t: rng.uniform(0.1, 0.3) for t in teams}  # persistent per-team tendency
    for g in range(n_games):
        date = start + pd.Timedelta(days=g)
        home, away = rng.choice(teams, size=2, replace=False)
        for team, opp, is_home in ((home, away, 1), (away, home, 0)):
            rate = float(np.clip(team_bias[team] + rng.normal(0, 0.03), 0.0, 1.0))
            n_shots = int(rng.integers(70, 95))
            margin = (rate - team_bias[opp]) * 100 + rng.normal(0, 8)
            rows.append({"game_id": "g%03d" % g, "team": team, "date": date, "is_home": is_home,
                         "n_shots": n_shots, "n_transition": int(round(rate * n_shots)),
                         "transition_rate": rate, "margin": margin})
    return pd.DataFrame(rows)


def test_add_asof_trailing_rate_is_leak_free():
    tg = _synthetic_team_games()
    d = vtf.add_asof_trailing_rate(tg)
    first_per_team = d.groupby("team")["asof_n_prior"].min()
    assert (first_per_team == 0).all()
    first_rows = d[d["asof_n_prior"] == 0]
    assert first_rows["asof_transition_rate"].isna().all()  # no prior games -> NaN, never leaks current game


def test_split_half_persistence_detects_real_team_tendency():
    tg = _synthetic_team_games(n_games=80)
    r = vtf.transition_rate_split_half_persistence(tg)
    assert r["verdict"] in {"CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE"}
    assert r["n"] > 0
    assert r["verdict"] == "CONFIRMED_LOCAL"  # synthetic teams have a real persistent bias by construction


def test_margin_relation_runs_and_p_is_valid_probability():
    tg = _synthetic_team_games(n_games=80)
    r = vtf.transition_rate_margin_relation(tg)
    assert r["verdict"] in {"CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE"}
    if r["p"] is not None:
        assert 0.0 <= r["p"] <= 1.0


def test_run_writes_edge_free_rows_to_ledger(tmp_path, monkeypatch):
    tg = _synthetic_team_games(n_games=80)
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vtf, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vtf, "build_team_game_transition_frame", lambda: tg)

    rows = vtf.run()
    assert len(rows) == 3
    assert all(r["edge_claimed"] is False and r["sport"] == "basketball_nba" for r in rows)
    combined = [r for r in rows if r["hypothesis"].endswith("__combined")][0]
    assert combined["verdict"] in {"CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE"}
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 3


def test_self_check():
    vtf._self_check()
