"""P0.4 — GameState.apply_event correctness + the leak-free truncation-invariance gate.

Truncation-invariance (ARCHITECTURE §3 gate 1, RED-B Attack 8): the state after applying
events[0:k] must be IDENTICAL whether or not events[k:] exist — i.e. apply_event uses only the
current event + current state, with no lookahead. This is the in-game leak guarantee.
"""
import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from ingame.game_state import GameState, STAT_COLS  # noqa: E402


def _make_snap():
    """Fresh base snapshot: home {1,2 on court, 5 bench}, away {3,4 on court}, all stats zero."""
    def player(pid, team, on):
        d = {"player_id": pid, "team": team, "on_court": on, "min_so_far": 0.0, "pf": 0}
        d.update({s: 0.0 for s in STAT_COLS})
        return d
    return {
        "game_id": "0042500401", "home_team": "NYK", "away_team": "SAS",
        "period": 1, "home_score": 0, "away_score": 0,
        "players": [player(1, "home", True), player(2, "home", True),
                    player(5, "home", False), player(3, "away", True), player(4, "away", True)],
    }


EVENTS = [
    {"type": "made_fg", "team": "home", "pid": 1, "pts": 2, "period": 1, "clock_remaining_sec": 700, "home_score": 2, "away_score": 0},
    {"type": "made_fg", "team": "away", "pid": 3, "pts": 3, "fg3": True, "period": 1, "clock_remaining_sec": 680, "home_score": 2, "away_score": 3},
    {"type": "miss_fg", "team": "home", "pid": 2, "fg3": True, "period": 1, "clock_remaining_sec": 660},
    {"type": "reb", "team": "away", "pid": 4, "period": 1, "clock_remaining_sec": 658},
    {"type": "made_fg", "team": "home", "pid": 2, "pts": 2, "assist_pid": 1, "period": 1, "clock_remaining_sec": 640, "home_score": 4, "away_score": 3},
    {"type": "ft", "team": "away", "pid": 3, "pts": 1, "period": 1, "clock_remaining_sec": 620, "home_score": 4, "away_score": 4},
    {"type": "foul", "team": "home", "pid": 1, "period": 1, "clock_remaining_sec": 600},
    {"type": "foul", "team": "home", "pid": 2, "period": 1, "clock_remaining_sec": 580},
    {"type": "tov", "team": "away", "pid": 4, "period": 1, "clock_remaining_sec": 560},
    {"type": "sub", "team": "home", "sub_out": 1, "sub_in": 5, "period": 1, "clock_remaining_sec": 540},
    {"type": "end_period", "period": 1, "clock_remaining_sec": 0},
    {"type": "made_fg", "team": "away", "pid": 3, "pts": 2, "period": 2, "clock_remaining_sec": 710, "home_score": 4, "away_score": 6},
]


def _fingerprint(gs) -> tuple:
    return (
        gs.home_score, gs.away_score, gs.period,
        gs.home_fgm, gs.home_fga, gs.home_ftm, gs.home_fg3a,
        gs.away_fgm, gs.away_fga, gs.away_ftm, gs.away_fg3a,
        gs.home_team_fouls_period, gs.away_team_fouls_period,
        gs.home_in_bonus, gs.away_in_bonus, gs.score_margin,
        tuple(round(float(x), 4) for x in gs.cur.flatten().tolist()),
        tuple(round(float(x), 4) for x in gs.min_so_far.tolist()),
        tuple(int(x) for x in gs.pf.tolist()),
        tuple(bool(x) for x in gs.on_court.tolist()),
        tuple(gs.players[p].available for p in sorted(gs.players)),
    )


def _replay(k):
    gs = GameState.from_snapshot(_make_snap())
    for ev in EVENTS[:k]:
        gs.apply_event(copy.deepcopy(ev))
    return gs


def test_truncation_invariance():
    # incremental: one fingerprint after each event
    gs = GameState.from_snapshot(_make_snap())
    incremental = [_fingerprint(gs)]
    for ev in EVENTS:
        gs.apply_event(copy.deepcopy(ev))
        incremental.append(_fingerprint(gs))
    # truncated: a fresh replay of events[0:k] must match the incremental state at k
    for k in range(len(EVENTS) + 1):
        assert _replay(k) and _fingerprint(_replay(k)) == incremental[k], f"leak at k={k}"


def test_scoring_and_four_factors():
    gs = _replay(2)  # two made FGs: home 2pt, away 3pt(fg3)
    assert (gs.home_score, gs.away_score) == (2, 3)
    assert gs.home_fgm == 1 and gs.home_fga == 1
    assert gs.away_fgm == 1 and gs.away_fg3a == 1
    i3 = gs.pid_index[3]
    assert gs.cur[i3, STAT_COLS.index("fg3m")] == 1.0
    assert gs.cur[i3, STAT_COLS.index("pts")] == 3.0


def test_assist_credited_to_passer():
    gs = _replay(5)  # event 5 is a made_fg by pid2 assisted by pid1
    assert gs.cur[gs.pid_index[1], STAT_COLS.index("ast")] == 1.0


def test_changed_pids_returns_touched_players():
    gs = GameState.from_snapshot(_make_snap())
    changed = gs.apply_event({"type": "made_fg", "team": "home", "pid": 2, "pts": 2, "assist_pid": 1,
                              "period": 1, "clock_remaining_sec": 640})
    assert set(changed) == {1, 2}  # scorer + assister


def test_bonus_and_foul_out():
    gs = GameState.from_snapshot(_make_snap())
    for _ in range(5):
        gs.apply_event({"type": "foul", "team": "away", "pid": 3, "period": 1, "clock_remaining_sec": 600})
    assert gs.away_team_fouls_period == 5 and gs.away_in_bonus is True
    assert gs.players[3].available is True  # 5 personal fouls, still in
    gs.apply_event({"type": "foul", "team": "away", "pid": 3, "period": 1, "clock_remaining_sec": 590})
    assert gs.players[3].available is False  # 6th foul -> fouled out


def test_sub_flips_on_court():
    gs = _replay(10)  # after the sub_out:1 / sub_in:5
    assert gs.on_court[gs.pid_index[1]] == False  # noqa: E712
    assert gs.on_court[gs.pid_index[5]] == True   # noqa: E712


def test_end_period_resets_team_fouls():
    gs = _replay(11)  # after end_period
    assert gs.home_team_fouls_period == 0 and gs.away_team_fouls_period == 0
    assert gs.home_in_bonus is False and gs.away_in_bonus is False


def test_unknown_event_is_noop():
    gs = GameState.from_snapshot(_make_snap())
    before = _fingerprint(gs)
    assert gs.apply_event({"type": "jump_ball", "period": 1}) == []
    assert _fingerprint(gs) == before


def test_snapshot_roundtrip_preserves_stats():
    gs = _replay(6)
    gs2 = GameState.from_snapshot(gs.to_snapshot())
    assert (gs2.home_score, gs2.away_score) == (gs.home_score, gs.away_score)
    for pid in gs.players:
        for s in STAT_COLS:
            assert gs2.cur[gs2.pid_index[pid], STAT_COLS.index(s)] == \
                   gs.cur[gs.pid_index[pid], STAT_COLS.index(s)]
