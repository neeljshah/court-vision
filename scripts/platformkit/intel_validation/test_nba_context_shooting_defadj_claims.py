"""Per-file tests for nba_context_shooting_defadj_claims -- SYNTHETIC 2-season
boxscore frame only (this worktree has no data/ dir).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_context_shooting_defadj_claims.py -q

Acceptance:
  1. MIN-floor skip: a below-floor player never appears; never an empty
     ranking is emitted (build_all_claims filters/prints SKIP honestly).
  2. defadj_ts_pct claim validates end-to-end via claims_validator.
  3. Honest caveats + edge_claimed False.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import nba_context_defadj_asof as asof
from scripts.platformkit.intel_validation import nba_context_shooting_defadj_claims as C


def _game_rows(gid, date, season, team, opp, player_start_id, n_players, per_player_stats):
    """per_player_stats: list of (fgm, fga, fg3m, fg3a, ftm, fta, pts) for team's players."""
    rows = []
    for i, stats in enumerate(per_player_stats):
        fgm, fga, fg3m, fg3a, ftm, fta, pts = stats
        rows.append({"game_id": gid, "date": date, "season": season, "team": team, "opp": opp,
                     "player_id": player_start_id + i, "player_name": f"P{player_start_id + i}",
                     "fgm": fgm, "fga": fga, "fg3m": fg3m, "fg3a": fg3a, "ftm": ftm, "fta": fta, "pts": pts})
    return rows


@pytest.fixture()
def synthetic_box(monkeypatch, tmp_path):
    """30 games for player 1 (AAA), alternating opponents ZZZ (weak D, high
    allowed-TS ~0.75) and YYY (tough D, low allowed-TS ~0.3) so a clean global
    tercile split emerges on both sides of the MIN_GAMES_TERCILE=5 floor.
    Player 1 shoots the same efficient line every game, clearing
    games>=20/fga>=200. A second player (2) plays only 5 games (below the
    games floor)."""
    rows = []
    for i in range(30):
        date = pd.Timestamp("2024-10-01") + pd.Timedelta(days=i * 3)
        opp = "ZZZ" if i % 2 == 0 else "YYY"
        # player 1: 10 fga, 5 fgm, 0 threes, 2 fta, 12 pts -> ts_pct=0.6 every game
        rows += _game_rows(f"g{i}", date, "2024-25", "AAA", opp, 1, 1, [(5, 10, 0, 0, 2, 2, 12)])
        if opp == "ZZZ":
            rows += _game_rows(f"g{i}", date, "2024-25", "ZZZ", "AAA", 700, 1, [(7, 10, 0, 0, 1, 1, 15)])
        else:
            rows += _game_rows(f"g{i}", date, "2024-25", "YYY", "AAA", 750, 1, [(3, 10, 0, 0, 0, 0, 6)])
    # below-floor player: only 5 games
    for i in range(5):
        date = pd.Timestamp("2024-10-01") + pd.Timedelta(days=i * 3)
        rows += _game_rows(f"h{i}", date, "2024-25", "AAA", "ZZZ", 2, 1, [(4, 8, 0, 0, 1, 1, 9)])
        rows += _game_rows(f"h{i}", date, "2024-25", "ZZZ", "AAA", 800, 1, [(5, 10, 0, 0, 0, 0, 10)])
    box = pd.DataFrame(rows)
    box["date"] = pd.to_datetime(box["date"])

    claims_dir = tmp_path / "intel_claims"
    claims_dir.mkdir(parents=True)
    monkeypatch.setattr(C, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(C, "_OUT_DIR", claims_dir)
    monkeypatch.setattr(C, "_CLAIMS_OUT", claims_dir / "nba_context_shooting_defadj_claims.jsonl")
    # axis 2/3 atlas files absent in this fixture -- their build_claims() must
    # skip honestly rather than error.
    return box


def test_below_floor_player_excluded_no_empty_ranking(synthetic_box):
    table = C.player_season_table("2024-25", synthetic_box)
    claim = C.build_defadj_ts_claim("2024-25", table)
    ranked_ids = {r["player_id"] for r in claim["ranking"]}
    assert 1 in ranked_ids  # 25 games, fga=250 -- clears the floor
    assert 2 not in ranked_ids  # only 5 games -- below MIN_GAMES=20
    assert claim["n_excluded_below_floor"] >= 1
    assert claim["ranking"], "must never emit an empty ranking"


def test_tercile_gap_claim_has_ranking(synthetic_box):
    table = C.player_season_table("2024-25", synthetic_box)
    claim = C.build_tercile_gap_ts_claim("2024-25", table)
    # player 1 clears n_tough/n_weak>=5 given 25 games split across 3 terciles
    assert claim["ranking"]
    assert claim["criteria"]["entity_key"] == "player_id"


def test_validator_verifies_defadj_ts_claim_end_to_end(synthetic_box):
    table = C.player_season_table("2024-25", synthetic_box)
    claim = C.build_defadj_ts_claim("2024-25", table)
    import scripts.platformkit.intel_validation.claims_validator as cv_mod
    orig_root = cv_mod.REPO_ROOT
    cv_mod.REPO_ROOT = C.REPO_ROOT
    try:
        verdict = claims_validator.validate_claim(claim)
    finally:
        cv_mod.REPO_ROOT = orig_root
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_honest_caveats_and_edge_claimed_false(synthetic_box):
    table = C.player_season_table("2024-25", synthetic_box)
    claim = C.build_defadj_ts_claim("2024-25", table)
    assert claim["edge_claimed"] is False
    blob = json.dumps([claim["caveats"], claim["question"]]).lower()
    for word in ("roi", "pnl", "$", "bankroll"):
        assert word not in blob
    assert "descriptive" in blob
    assert "floor" in blob


def test_build_all_claims_skips_missing_atlas_axes_honestly(synthetic_box, capsys, monkeypatch):
    monkeypatch.setattr(C.asof, "load_raw_boxscores", lambda: synthetic_box)
    claims = C.build_all_claims()
    captured = capsys.readouterr()
    assert "SKIP" in captured.out  # axis2/axis3 atlas files absent in this fixture
    assert all(c["ranking"] for c in claims)  # never an empty ranking survives
