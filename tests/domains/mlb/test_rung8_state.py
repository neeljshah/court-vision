"""Per-file test for domains.mlb.ingame.rung8_state.rung8_state.

Hand-verification: game_pk 822710's reconstructed pitcher-change sequence must match
the REAL boxscore pitcher order recorded in
data/domains/mlb/gumbo_live/_poller_state.json (snapshot.liveData.boxscore.teams.
{home,away}.pitchers), inspected directly for this test:
  home pitchers (in order): [656492, 687377, 664875]
  away pitchers (in order): [681293, 695001, 663878, 664299]

Run: python -m pytest tests/domains/mlb/test_rung8_state.py -q
"""
from __future__ import annotations

from domains.mlb.ingame.rung8_state.rung8_state import (
    load_game_ticks,
    pitcher_change_sequence,
    reconstruct_bullpen_state,
)

GAME_PK = 822710
EXPECTED_HOME = [656492, 687377, 664875]
EXPECTED_AWAY = [681293, 695001, 663878, 664299]


def test_reconstructed_sequence_matches_real_boxscore():
    ticks = load_game_ticks(GAME_PK)
    assert len(ticks) > 0, "game_pk 822710 must have GUMBO ticks on disk"

    state = reconstruct_bullpen_state(ticks)

    home_seq = pitcher_change_sequence(state, "home")
    away_seq = pitcher_change_sequence(state, "away")

    assert home_seq == EXPECTED_HOME, f"home pitcher sequence mismatch: {home_seq}"
    assert away_seq == EXPECTED_AWAY, f"away pitcher sequence mismatch: {away_seq}"

    # relievers_used_so_far must end at len(sequence) - 1 for each side (0 = still starter).
    final_home = state[state["pitching_side"] == "home"].iloc[-1]
    final_away = state[state["pitching_side"] == "away"].iloc[-1]
    assert final_home["relievers_used_so_far"] == len(EXPECTED_HOME) - 1
    assert final_away["relievers_used_so_far"] == len(EXPECTED_AWAY) - 1

    # pitch count must reset to 0 (or near it) on every pitcher change -- sanity check
    # that pitcher_pitches is per-pitcher, not cumulative team-wide. Must compare
    # WITHIN a side (home/away ticks interleave in the globally ts-sorted frame, so a
    # global shift(1) would flag every alternation as a false "change").
    for side in ("home", "away"):
        sub = state[state["pitching_side"] == side].sort_values("captured_at").reset_index(drop=True)
        changed = sub["current_pitcher_id"] != sub["current_pitcher_id"].shift(1)
        changed.iloc[0] = False  # first row is not a real "change"
        assert (sub.loc[changed, "current_pitcher_pitches"] <= 2).all(), (
            f"{side}: pitch count should reset near 0 at every pitcher change"
        )


if __name__ == "__main__":
    test_reconstructed_sequence_matches_real_boxscore()
    print("OK: rung8_state reconstruction matches real boxscore pitcher order")
