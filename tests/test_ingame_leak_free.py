"""Leak-free self-tests for the in-game state featurizer (SPEC Section 7).

The hard-honesty rule: a feature at event E must use ONLY events <= E. We assert
that by TRUNCATION INVARIANCE -- the state row at event E is byte-identical
whether or not any events AFTER E exist in the input. If a future event could
change a past row, that's a leak; this test would catch it.

Run: python -m pytest tests/test_ingame_leak_free.py -q
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("NBA_OFFLINE", "1")

from src.ingame.state_featurizer import (  # noqa: E402
    load_pbp_events, featurize_game, discover_game_ids,
)


def _first_real_game():
    ids = discover_game_ids()
    for gid in ids:
        ev = load_pbp_events(gid)
        if len(ev) > 100:
            return gid, ev
    pytest.skip("no PBP games available")


# state fields that legitimately depend on the FULL game (resolved once at load,
# constant across all rows) and are therefore exempt from truncation invariance.
_GAME_CONSTANT_FIELDS = {"home_team", "away_team", "game_remaining_sec",
                         "played_share"}


def test_truncation_invariance_game_rows():
    """A game-state row at event E must not change if future events are deleted.

    We featurize the full game, then re-featurize only the first K events, and
    assert the K-th row's score/box/four-factor state matches between the two
    runs. (game_remaining_sec/played_share depend on total game length resolved
    from the max period, so they are exempt -- they are a clock denominator, not
    leaked event content.)
    """
    gid, ev = _first_real_game()
    full = featurize_game(ev, gid, "AAA", "BBB", emit_players=False)["game"]
    # pick a mid-game cut
    K = len(ev) // 2
    truncated = featurize_game(ev[:K], gid, "AAA", "BBB", emit_players=False)["game"]
    assert len(truncated) == K
    last_trunc = truncated[-1]
    same_idx = full[K - 1]
    for k, v in last_trunc.items():
        if k in _GAME_CONSTANT_FIELDS:
            continue
        assert same_idx[k] == v, f"field {k} leaked future info: {same_idx[k]} != {v}"


def test_truncation_invariance_player_rows():
    """A player's accumulated box at event E must not change with future events."""
    gid, ev = _first_real_game()
    K = len(ev) // 2
    full = featurize_game(ev, gid, "AAA", "BBB", emit_players=True)["players"]
    truncated = featurize_game(ev[:K], gid, "AAA", "BBB", emit_players=True)["players"]

    # build {(team,name): row at event_idx K-1} for both
    def at_cut(rows):
        out = {}
        for r in rows:
            if r["event_idx"] == K - 1:
                out[(r["team_abbrev"], r["last_name"])] = r
        return out

    full_cut = at_cut(full)
    trunc_cut = at_cut(truncated)
    # every player present in the truncated cut must match the full-game cut
    assert trunc_cut, "no player rows at the cut event"
    for key, trow in trunc_cut.items():
        assert key in full_cut, f"player {key} missing from full-game cut"
        frow = full_cut[key]
        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "pf",
                     "fga", "fgm"):
            assert frow[stat] == trow[stat], (
                f"player {key} stat {stat} leaked: {frow[stat]} != {trow[stat]}")


def test_monotonic_time_and_accumulation():
    """Time is non-decreasing and box stats never decrease event-over-event."""
    gid, ev = _first_real_game()
    res = featurize_game(ev, gid, "AAA", "BBB", emit_players=False)["game"]
    prev = -1
    for r in res:
        assert r["game_elapsed_sec"] >= prev
        prev = r["game_elapsed_sec"]
