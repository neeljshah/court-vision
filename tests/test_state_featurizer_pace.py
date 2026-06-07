"""Tests for the POSSESSION / PACE-STATE features in state_featurizer.py.

These features (possession counts, sec-per-possession, time-since-last-FG,
pace-vs-prior, run-state, bonus/foul-state, expected-possessions-remaining) let
the projection update BETWEEN scoring events toward true per-second. The hard
requirement (SPEC Section 7): every pace-state value at event E must be a pure
function of events <= E -- i.e. TRUNCATION INVARIANT. We assert that here in
addition to face-validity of each new column, and we exercise the per-second
``advance_to_time`` interpolation.

Run: python -m pytest tests/test_state_featurizer_pace.py -q
"""
import os
import sys

sys.path.insert(0, ".")
os.environ.setdefault("NBA_OFFLINE", "1")

import pytest  # noqa: E402

from src.ingame import state_featurizer as sf  # noqa: E402


# ---------------------------------------------------------------------------
# Scripted PBP with possession-ending events, fouls, and a scoring run.
# ---------------------------------------------------------------------------
def _events():
    # HOME=BOS scores first (left). Sequence designed to exercise:
    #   made FG (poss end), miss+def rebound (poss end), turnover (poss end),
    #   FT trip "2 of 2" (poss end), team fouls building to bonus, a home run.
    return [
        {"period": 1, "game_clock_sec": 0, "event_type": 0,
         "event_desc": "Start of 1st Period", "player_name": "",
         "team_abbrev": "", "score": "0-0", "score_margin": "0"},
        # BOS made 2 @ 24s  -> home poss +1
        {"period": 1, "game_clock_sec": 24, "event_type": 1,
         "event_desc": "Tatum Jump Shot (2 PTS)", "player_name": "Tatum",
         "team_abbrev": "BOS", "score": "2-0", "score_margin": "2"},
        # PHI miss @ 48s, BOS defensive rebound -> away poss +1
        {"period": 1, "game_clock_sec": 48, "event_type": 2,
         "event_desc": "MISS Embiid 18' Jumper", "player_name": "Embiid",
         "team_abbrev": "PHI", "score": "2-0", "score_margin": "2"},
        {"period": 1, "game_clock_sec": 50, "event_type": 4,
         "event_desc": "Smart REBOUND (Off:0 Def:1)", "player_name": "Smart",
         "team_abbrev": "BOS", "score": "2-0", "score_margin": "2"},
        # BOS made 3 @ 72s -> home poss +1 (home run building)
        {"period": 1, "game_clock_sec": 72, "event_type": 1,
         "event_desc": "Tatum 26' 3PT Jump Shot (5 PTS) (Smart 1 AST)",
         "player_name": "Tatum", "team_abbrev": "BOS",
         "score": "5-0", "score_margin": "5"},
        # PHI turnover @ 90s -> away poss +1
        {"period": 1, "game_clock_sec": 90, "event_type": 5,
         "event_desc": "Maxey Bad Pass Turnover (P1.T1)", "player_name": "Maxey",
         "team_abbrev": "PHI", "score": "5-0", "score_margin": "5"},
        # PHI fouls accumulate toward bonus (team fouls T2..T5)
        {"period": 1, "game_clock_sec": 100, "event_type": 6,
         "event_desc": "Harris Personal Foul (P1.T2)", "player_name": "Harris",
         "team_abbrev": "PHI", "score": "5-0", "score_margin": "5"},
        {"period": 1, "game_clock_sec": 110, "event_type": 6,
         "event_desc": "Harris Personal Foul (P2.T3)", "player_name": "Harris",
         "team_abbrev": "PHI", "score": "5-0", "score_margin": "5"},
        {"period": 1, "game_clock_sec": 120, "event_type": 6,
         "event_desc": "Embiid Personal Foul (P1.T4)", "player_name": "Embiid",
         "team_abbrev": "PHI", "score": "5-0", "score_margin": "5"},
        {"period": 1, "game_clock_sec": 130, "event_type": 6,
         "event_desc": "Embiid Personal Foul (P2.T5)", "player_name": "Embiid",
         "team_abbrev": "PHI", "score": "5-0", "score_margin": "5"},
        # BOS shoots the bonus: FT 1 of 2 (no poss end), FT 2 of 2 (poss end)
        {"period": 1, "game_clock_sec": 131, "event_type": 3,
         "event_desc": "Tatum Free Throw 1 of 2 (6 PTS)", "player_name": "Tatum",
         "team_abbrev": "BOS", "score": "6-0", "score_margin": "6"},
        {"period": 1, "game_clock_sec": 132, "event_type": 3,
         "event_desc": "Tatum Free Throw 2 of 2 (7 PTS)", "player_name": "Tatum",
         "team_abbrev": "BOS", "score": "7-0", "score_margin": "7"},
        # End game (period 4 marker so total length resolves to 48 min)
        {"period": 4, "game_clock_sec": 720, "event_type": 13,
         "event_desc": "End of 4th Period", "player_name": "",
         "team_abbrev": "", "score": "7-0", "score_margin": "7"},
    ]


def _last_game_row():
    res = sf.featurize_game(_events(), "PACEGAME", "BOS", "PHI",
                            emit_players=False,
                            prior_pace={"home": 100.0, "away": 96.0})
    return res["game"]


# ---------------------------------------------------------------------------
# 1. The new columns are present on every game row.
# ---------------------------------------------------------------------------
def test_pace_state_columns_present():
    rows = _last_game_row()
    assert rows
    for col in sf.PACE_STATE_FIELDS:
        assert col in rows[-1], f"missing pace-state column {col}"


# ---------------------------------------------------------------------------
# 2. Possession counting & tempo face-validity.
# ---------------------------------------------------------------------------
def test_possession_counts_and_tempo():
    rows = _last_game_row()
    # use the last in-period-1 row (the FT trip end @132s); the final row is the
    # period-4 End marker (game_rem=0, foul-reset) and is not a mid-game state.
    last = [r for r in rows if r["period"] == 1][-1]
    # Possession-ending events credited: BOS made(24), away-rebound flip(50),
    # BOS made(72), PHI turnover(90), BOS FT 2-of-2(132).
    # home credits: made@24, def-reb@50 (credits shooter=PHI? no: def reb by BOS
    #   credits the side that shot = PHI -> away), made@72, FT trip end@132.
    assert last["home_poss_count"] >= 3
    assert last["away_poss_count"] >= 1
    assert last["total_poss_count"] == last["home_poss_count"] + last["away_poss_count"]
    assert last["sec_per_poss_so_far"] > 0.0
    assert last["poss_per_48_so_far"] > 0.0
    # expected possessions remaining must be positive mid-game with tempo known
    assert last["exp_poss_remaining"] > 0.0
    assert last["exp_home_poss_remaining"] > 0.0


def test_time_since_last_fg_increases_between_fgs():
    rows = _last_game_row()
    # at the FG event itself sec_since_last_fg resets to 0; later non-FG events
    # carry a growing gap.
    fg_rows = [r for r in rows if r["sec_since_last_fg"] == 0]
    assert fg_rows, "expected at least one row at a made-FG (gap 0)"
    # the foul at 100s is 28s after the 72s 3PT -> gap should be 28
    foul100 = [r for r in rows if r["game_elapsed_sec"] == 100]
    assert foul100 and foul100[-1]["sec_since_last_fg"] == 100 - 72


# ---------------------------------------------------------------------------
# 3. Run-state reflects the home scoring run (BOS scored all points).
# ---------------------------------------------------------------------------
def test_run_state_margin():
    rows = _last_game_row()
    last = rows[-1]
    # every scoring event was BOS (home) -> run margins strictly positive
    assert last["run_last10_margin"] > 0
    assert last["run_last5_margin"] > 0


# ---------------------------------------------------------------------------
# 4. Bonus / foul-state: PHI reaches 5 team fouls -> opponent in bonus.
# ---------------------------------------------------------------------------
def test_bonus_state():
    rows = _last_game_row()
    # period-1 in-game state (final row is the period-4 End marker -> fouls reset)
    last = [r for r in rows if r["period"] == 1][-1]
    assert last["away_team_fouls_period"] >= sf.BONUS_FOULS
    assert last["away_in_bonus"] == 1
    # home committed no fouls -> not in bonus
    assert last["home_in_bonus"] == 0


def test_team_fouls_reset_on_new_period():
    # add a period-2 event after the run; period-1 fouls must NOT carry over.
    ev = _events()[:-1] + [
        {"period": 2, "game_clock_sec": 30, "event_type": 1,
         "event_desc": "Maxey Layup (2 PTS)", "player_name": "Maxey",
         "team_abbrev": "PHI", "score": "7-2", "score_margin": "5"},
        {"period": 4, "game_clock_sec": 720, "event_type": 13,
         "event_desc": "End", "player_name": "", "team_abbrev": "",
         "score": "7-2", "score_margin": "5"},
    ]
    res = sf.featurize_game(ev, "P2", "BOS", "PHI", emit_players=False)["game"]
    p2 = [r for r in res if r["period"] == 2]
    assert p2 and p2[0]["away_team_fouls_period"] == 0
    assert p2[0]["away_in_bonus"] == 0


# ---------------------------------------------------------------------------
# 5. Pace-vs-prior ratio uses the injected (leak-free) prior pace.
# ---------------------------------------------------------------------------
def test_pace_vs_prior_ratio():
    with_prior = sf.featurize_game(_events(), "PP", "BOS", "PHI",
                                   emit_players=False,
                                   prior_pace={"home": 100.0, "away": 96.0})["game"]
    without = sf.featurize_game(_events(), "PP", "BOS", "PHI",
                                emit_players=False)["game"]
    # with prior supplied the ratio is a finite positive number; without it 0.
    assert with_prior[-1]["pace_vs_prior_ratio"] > 0.0
    assert with_prior[-1]["home_prior_pace"] == 100.0
    assert without[-1]["pace_vs_prior_ratio"] == 0.0
    assert without[-1]["home_prior_pace"] == 0.0


# ---------------------------------------------------------------------------
# 6. LEAK GUARD: every pace-state column is truncation-invariant.
# ---------------------------------------------------------------------------
def test_pace_state_truncation_invariance():
    events = _events()
    full = sf.featurize_game(events, "PACEGAME", "BOS", "PHI",
                             emit_players=False,
                             prior_pace={"home": 100.0, "away": 96.0})["game"]
    # Fields whose value legitimately depends on the resolved TOTAL game length
    # (a game-constant, not leaked event content) are exempt -- same exemption
    # the core leak test uses for played_share / game_remaining_sec.
    clock_denominator_fields = {
        "exp_poss_remaining", "exp_home_poss_remaining", "exp_away_poss_remaining",
    }
    for i in range(1, len(events)):
        trunc = sf.featurize_game(events[: i + 1], "PACEGAME", "BOS", "PHI",
                                  emit_players=False,
                                  prior_pace={"home": 100.0, "away": 96.0})["game"]
        for col in sf.PACE_STATE_FIELDS:
            if col in clock_denominator_fields:
                continue
            assert full[i][col] == trunc[i][col], (
                f"LEAK: pace-state col {col} at event {i} differs full="
                f"{full[i][col]} trunc={trunc[i][col]}"
            )


# ---------------------------------------------------------------------------
# 7. Per-second interpolation: advance_to_time ages only clock-derived fields.
# ---------------------------------------------------------------------------
def test_advance_to_time_is_pure_clock_decay():
    rows = _last_game_row()
    # take an early-game row and roll it forward 30 wall-clock seconds with no
    # new events; counts/score/run must be IDENTICAL, only clock fields move.
    base = [r for r in rows if r["game_elapsed_sec"] == 100][-1]
    adv = sf.advance_to_time(base, base["game_elapsed_sec"] + 30)

    # unchanged (no new events occurred)
    for col in ("home_poss_count", "away_poss_count", "total_poss_count",
                "home_score", "away_score", "run_last10_margin",
                "away_team_fouls_period", "away_in_bonus"):
        assert adv[col] == base[col], f"{col} must not change on pure clock decay"

    # advanced
    assert adv["game_elapsed_sec"] == base["game_elapsed_sec"] + 30
    assert adv["game_remaining_sec"] == base["game_remaining_sec"] - 30
    assert adv["sec_since_last_fg"] == base["sec_since_last_fg"] + 30
    assert adv["sec_since_last_score"] == base["sec_since_last_score"] + 30
    # expected possessions remaining shrinks as the clock runs down
    assert adv["exp_poss_remaining"] <= base["exp_poss_remaining"]


def test_advance_to_time_never_goes_backward():
    rows = _last_game_row()
    base = rows[-1]
    # asking for an earlier time clamps to the row's own time (no negative aging)
    adv = sf.advance_to_time(base, base["game_elapsed_sec"] - 999)
    assert adv["game_elapsed_sec"] == base["game_elapsed_sec"]


# ---------------------------------------------------------------------------
# 8. Real-game smoke (skips cleanly if data absent).
# ---------------------------------------------------------------------------
def _real_game_available(gid="0022200001"):
    return os.path.exists(os.path.join("data", "nba", f"pbp_{gid}_p1.json"))


@pytest.mark.skipif(not _real_game_available(),
                    reason="real PBP data not present")
def test_real_game_pace_state_truncation_invariance():
    gid = "0022200001"
    events = sf.load_pbp_events(gid)
    full = sf.featurize_game(events, gid, "BOS", "PHI", emit_players=False)["game"]
    clock_denominator_fields = {
        "exp_poss_remaining", "exp_home_poss_remaining", "exp_away_poss_remaining",
    }
    for i in (50, 150, 300):
        if i >= len(events):
            continue
        trunc = sf.featurize_game(events[: i + 1], gid, "BOS", "PHI",
                                  emit_players=False)["game"]
        for col in sf.PACE_STATE_FIELDS:
            if col in clock_denominator_fields:
                continue
            assert full[i][col] == trunc[i][col], (
                f"LEAK at event {i} pace col {col}: {full[i][col]} != {trunc[i][col]}"
            )
