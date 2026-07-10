"""Per-file test for knowledge.validate_rotation_pace. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/knowledge/test_validate_rotation_pace.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.basketball_nba.knowledge import _data as kd
from domains.basketball_nba.knowledge import validate_rotation_pace as vrp


def _synthetic_pbox(n_games: int = 60, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    teams = [f"T{i}" for i in range(6)]
    rows = []
    start = pd.Timestamp("2024-01-01")
    for g in range(n_games):
        date = start + pd.Timedelta(days=g)
        gid = "g%03d" % g
        home, away = rng.choice(teams, size=2, replace=False)
        for team, is_home in ((home, 1), (away, 0)):
            n_rotation = rng.integers(7, 11)  # players with min>=5
            for p in range(n_rotation):
                rows.append({"game_id": gid, "team": team, "date": date, "season": "2023-24",
                             "is_home": is_home, "min": float(rng.uniform(6, 34)),
                             "pts": float(rng.uniform(2, 20)),
                             "fga": float(rng.uniform(4, 16))})
    return pd.DataFrame(rows)


def test_rotation_size_stability_vs_net_rating_happy_path():
    pbox = _synthetic_pbox()
    tg = kd.team_game_frame(pbox)
    r = vrp.rotation_size_stability_vs_net_rating(pbox, tg)
    assert set(r) >= {"hypothesis", "n", "effect", "p", "verdict", "note"}
    assert r["verdict"] in {"CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE"}
    assert r["n"] > 0


def test_rotation_size_persists_split_half_happy_path():
    pbox = _synthetic_pbox(n_games=80)
    r = vrp.rotation_size_persists_split_half(pbox)
    assert r["verdict"] in {"CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE"}
    assert r["n"] > 0


def test_pace_mismatch_variance_happy_path():
    pbox = _synthetic_pbox(n_games=90)
    tg = kd.team_game_frame(pbox)
    r = vrp.pace_mismatch_variance(pbox, tg)
    assert r["verdict"] in {"CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE"}
    assert r["n"] > 0


def test_run_writes_edge_free_rows_and_skips_no_ft_rate_crash(tmp_path, monkeypatch):
    """Failure mode: ft_rate_environment_wins reads FOUR_FACTOR_PATH straight
    off disk -- if that sidecar is stale/missing-columns, run() must not
    silently write a half-populated ledger; here we point it at a small
    synthetic parquet and confirm all 4 rows land with edge_claimed False."""
    pbox = _synthetic_pbox(n_games=60)
    tg = kd.team_game_frame(pbox)
    ff_path = tmp_path / "four_factor_env.parquet"
    winpct = tg.groupby("team")["win"].mean().reset_index()
    winpct["fta_rate_off"] = np.linspace(0.2, 0.4, len(winpct))
    winpct[["team", "fta_rate_off"]].to_parquet(ff_path)

    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vrp, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vrp, "FOUR_FACTOR_PATH", ff_path)
    monkeypatch.setattr(vrp, "load_player_boxscores", lambda: pbox)

    rows = vrp.run()
    assert len(rows) == 4
    assert all(r["edge_claimed"] is False and r["sport"] == "basketball_nba" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 4
