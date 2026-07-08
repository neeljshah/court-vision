"""Per-file tests for domains.basketball_wnba.lineup_stints.

Synthetic 1-period mini-game: HOME starts h1..h5, subs h5->h6 mid-period,
then game ends. AWAY has zero substitutions all game (single whole-game
stint). Score deltas are chosen so pts_for/pts_against are easy to hand-check.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_lineup_stints.py -q
"""
from __future__ import annotations

from domains.basketball_wnba.lineup_stints import build_all_stints, reconstruct_game_stints

HOME_ID, AWAY_ID = 100, 200


def _player(pid, starter):
    return {"personId": pid, "starter": "1" if starter else "0", "name": f"P{pid}"}


def _box_game():
    return {
        "homeTeam": {"teamId": HOME_ID,
                     "players": [_player(p, True) for p in ("h1", "h2", "h3", "h4", "h5")]
                     + [_player("h6", False)]},
        "awayTeam": {"teamId": AWAY_ID,
                     "players": [_player(p, True) for p in ("a1", "a2", "a3", "a4", "a5")]},
    }


def _action(period, clock, sh, sa, **kw):
    row = {"period": period, "clock": clock, "scoreHome": sh, "scoreAway": sa}
    row.update(kw)
    return row


def _pbp_game():
    actions = [
        _action(1, "PT10M00.00S", "0", "0", actionType="period", subType="start"),
        _action(1, "PT08M00.00S", "5", "2", actionType="2pt", subType="Jump Shot", teamId=HOME_ID),
        _action(1, "PT06M00.00S", "5", "2", actionType="substitution", subType="out",
                teamId=HOME_ID, personId="h5"),
        _action(1, "PT06M00.00S", "5", "2", actionType="substitution", subType="in",
                teamId=HOME_ID, personId="h6"),
        _action(1, "PT02M00.00S", "9", "4", actionType="2pt", subType="Jump Shot", teamId=HOME_ID),
        _action(1, "PT00M00.00S", "9", "6", actionType="game", subType="end"),
    ]
    return {"actions": actions}


def test_reconstruct_two_stints_for_home_one_for_away():
    stints = reconstruct_game_stints("g1", _box_game(), _pbp_game())
    home_stints = [s for s in stints if s.side == "home"]
    away_stints = [s for s in stints if s.side == "away"]

    assert len(home_stints) == 2
    assert len(away_stints) == 1

    first, second = home_stints
    assert first.lineup == ("h1", "h2", "h3", "h4", "h5")
    assert second.lineup == ("h1", "h2", "h3", "h4", "h6")

    # period length 10min = 600s; sub at elapsed 240s (10:00 -> 06:00 remaining)
    assert abs(first.elapsed_start_sec - 0.0) < 1e-6
    assert abs(first.elapsed_end_sec - 240.0) < 1e-6
    assert abs(first.minutes - 4.0) < 1e-6
    assert first.pts_for == 5.0 and first.pts_against == 2.0

    assert abs(second.elapsed_end_sec - 600.0) < 1e-6
    assert second.pts_for == 4.0 and second.pts_against == 4.0

    away_only = away_stints[0]
    assert away_only.lineup == ("a1", "a2", "a3", "a4", "a5")
    assert away_only.pts_for == 6.0 and away_only.pts_against == 9.0


def test_missing_starters_drops_that_side():
    box = _box_game()
    box["homeTeam"]["players"] = [_player("h1", True)]  # only 1 starter -- honest gap
    stints = reconstruct_game_stints("g2", box, _pbp_game())
    assert all(s.side != "home" for s in stints)
    assert any(s.side == "away" for s in stints)


def test_build_all_stints_empty_when_no_backfill(monkeypatch, tmp_path):
    import domains.basketball_wnba.atlas_extract_common as common_mod
    monkeypatch.setattr(common_mod, "BACKFILL_DIR", tmp_path)
    assert build_all_stints() == []
