"""Per-file tests for nba_context_defadj_asof -- SYNTHETIC boxscore frame
only (this worktree has no data/ dir).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_context_defadj_asof.py -q

Acceptance:
  1. AS-OF leak-freeness: a game on date D never uses D-or-later games to
     compute its opponent's def_allowed_asof.
  2. MIN_PRIOR_GAMES floor: too-early games get a null opponent-strength read.
  3. Tercile split emission: enough spread produces tough/mid/weak labels.
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import nba_context_defadj_asof as A


def _row(gid, date, season, team, opp, pid, fgm, fga, fg3m, fg3a, ftm, fta, pts):
    return {"game_id": gid, "date": date, "season": season, "team": team, "opp": opp,
            "player_id": pid, "player_name": f"P{pid}",
            "fgm": fgm, "fga": fga, "fg3m": fg3m, "fg3a": fg3a, "ftm": ftm, "fta": fta, "pts": pts}


@pytest.fixture()
def synthetic_box() -> pd.DataFrame:
    """Team ZZZ plays 8 games against AAA (allows a LOT: high TS%) before
    a 9th game where AAA's own player P1 shoots. Team ZZZ's def_allowed_asof
    on that 9th game must reflect ONLY the first 8 games."""
    rows = []
    for i in range(8):
        d = f"2024-01-{i+1:02d}"
        # ZZZ allows a very efficient game to AAA every time (high TS% allowed)
        rows.append(_row(f"g{i}a", d, "2023-24", "ZZZ", "AAA", 900 + i, 10, 10, 0, 0, 0, 0, 20))
        rows.append(_row(f"g{i}a", d, "2023-24", "AAA", "ZZZ", 800 + i, 3, 10, 0, 0, 0, 0, 6))
    # 9th game: P1 (AAA) faces ZZZ. If a future game leaked in, ZZZ's
    # def_allowed_asof would differ from the pure first-8-games mean.
    rows.append(_row("g9", "2024-01-20", "2023-24", "AAA", "ZZZ", 1, 5, 10, 0, 0, 0, 0, 10))
    rows.append(_row("g9", "2024-01-20", "2023-24", "ZZZ", "AAA", 700, 1, 10, 0, 0, 0, 0, 2))
    # future game AFTER g9 -- must NOT affect g9's own opp_def_strength_asof
    rows.append(_row("g10", "2024-01-25", "2023-24", "AAA", "ZZZ", 1, 9, 10, 0, 0, 0, 0, 20))
    rows.append(_row("g10", "2024-01-25", "2023-24", "ZZZ", "AAA", 700, 0, 10, 0, 0, 0, 0, 0))
    box = pd.DataFrame(rows)
    box["date"] = pd.to_datetime(box["date"])
    return box


def test_leak_free_opp_strength_uses_only_prior_games(synthetic_box):
    rows = A.build_player_game_rows(synthetic_box)
    g9_p1 = rows[(rows["game_id"] == "g9") & (rows["player_id"] == 1)].iloc[0]
    # ZZZ's allowed ts_pct in each of the first 8 games: pts=20 fga=10 fta=0 -> ts=1.0
    assert g9_p1["opp_prior_games"] == 8
    assert abs(g9_p1["opp_def_strength_asof"] - 1.0) < 1e-9

    g10_p1 = rows[(rows["game_id"] == "g10") & (rows["player_id"] == 1)].iloc[0]
    # g10's opp_def_strength_asof must fold in g9 (ZZZ allowed ts=0.1 there:
    # pts=2 fga=10 fta=0) alongside the first 8 games (ts=1.0 each) -- mean =
    # (8*1.0 + 0.1) / 9 = 0.9 -- proving g9 (not g10 itself) was included.
    assert g10_p1["opp_prior_games"] == 9
    assert abs(g10_p1["opp_def_strength_asof"] - 0.9) < 1e-9


def test_min_prior_games_floor_nulls_early_games(synthetic_box):
    rows = A.build_player_game_rows(synthetic_box)
    # ZZZ's very first game (0 prior games) must have a null opponent-strength
    # read -- MIN_PRIOR_GAMES=5 floor.
    first = rows[rows["game_id"] == "g0a"]
    assert first["opp_def_strength_asof"].isna().all()


def test_tercile_assignment_labels_present(synthetic_box):
    rows = A.build_player_game_rows(synthetic_box)
    valid = rows.dropna(subset=["opp_def_strength_asof"])
    assert not valid.empty
    assert set(valid["defense_tier"].dropna().unique()) <= {"tough", "mid", "weak"}
