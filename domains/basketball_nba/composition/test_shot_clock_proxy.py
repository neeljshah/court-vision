"""Per-file test for domains.basketball_nba.composition.shot_clock_proxy --
run with: python -m pytest domains/basketball_nba/composition/test_shot_clock_proxy.py -q
(never bare pytest -- see bash-cwd-prefix rule)."""
from __future__ import annotations

from domains.basketball_nba.composition.shot_clock_proxy import (
    _PBP_DIR, build_shot_clock_frame, cdn_semantic_agreement, resolve_segments, validate_distribution,
)

TEAM_A, TEAM_B = 111, 222
_FIXTURE = _PBP_DIR / "0022500003.json"  # a real CDN-native game (has `possession`)


def _clock(remaining_s: float) -> str:
    m, s = divmod(remaining_s, 60.0)
    return f"PT{int(m)}M{s:05.2f}S"


def _shot(num, team, elapsed, made=True, kind="2pt"):
    return {"actionNumber": num, "period": 1, "clock": _clock(720.0 - elapsed), "teamId": team,
            "actionType": kind, "subType": "Jump Shot", "shotResult": "Made" if made else "Missed",
            "description": f"team{team} shot"}


def _reb(num, team, elapsed, kind="defensive"):
    return {"actionNumber": num, "period": 1, "clock": _clock(720.0 - elapsed), "teamId": team,
            "actionType": "rebound", "subType": kind, "shotResult": None,
            "description": f"team{team} {kind} rebound"}


def _foul(num, team, elapsed):
    return {"actionNumber": num, "period": 1, "clock": _clock(720.0 - elapsed), "teamId": team,
            "actionType": "foul", "subType": "personal", "shotResult": None, "description": "foul"}


def test_made_shot_flips_possession_for_the_next_row_only():
    """Regression test for the row-ordering bug this module shipped with: a
    made shot's OWN row must still read as the shooter's team (matches the
    real CDN `possession` field's convention); only the FOLLOWING row should
    show the flip to the other team."""
    actions = [
        _shot(1, TEAM_A, elapsed=5.0, made=True),   # A makes -- flips for what's AFTER this row
        _foul(2, TEAM_B, elapsed=5.0),               # non-anchor row right after the make
        _shot(3, TEAM_B, elapsed=8.0, made=False),  # B's own shot attempt (direct read)
    ]
    seg = {r["action_number"]: r for r in resolve_segments(actions, mode="semantic")}
    assert seg[1]["seg_team"] == TEAM_A   # the make's own row still reads as A
    assert seg[2]["seg_team"] == TEAM_B   # the flip took effect starting with the NEXT row
    assert seg[3]["seg_team"] == TEAM_B


def test_offensive_rebound_does_not_change_team_defensive_rebound_does():
    actions = [
        _shot(1, TEAM_A, elapsed=5.0, made=False),
        _reb(2, TEAM_A, elapsed=6.0, kind="offensive"),   # same team -- no team change
        _shot(3, TEAM_A, elapsed=10.0, made=False),
        _reb(4, TEAM_B, elapsed=11.0, kind="defensive"),  # team change -- new segment
    ]
    seg = {r["action_number"]: r for r in resolve_segments(actions, mode="semantic")}
    assert seg[2]["seg_team"] == TEAM_A
    assert seg[2]["seg_start_s"] == seg[1]["seg_start_s"]  # ORB does not restart the segment (v1 proxy limit)
    assert seg[4]["seg_team"] == TEAM_B
    assert seg[4]["seg_start_s"] == 11.0


def test_period_boundary_resets_to_unknown():
    actions = [
        _shot(1, TEAM_A, elapsed=5.0, made=True),
        {**_shot(2, TEAM_B, elapsed=3.0, made=False), "period": 2},
    ]
    seg = {r["action_number"]: r for r in resolve_segments(actions, mode="semantic")}
    assert seg[2]["seg_team"] == TEAM_B  # resolved by its own direct-read anchor
    assert seg[2]["seg_start_s"] == 3.0  # fresh segment at the period boundary, not carried from period 1


def test_cdn_semantic_agreement_on_real_fixture_clears_90pct():
    result = cdn_semantic_agreement(limit=1)
    assert result["n_games"] == 1
    assert result["n_compared"] > 400
    assert result["agreement_pct"] > 0.90


def test_shot_clock_frame_distribution_on_real_fixture_is_sane():
    df = build_shot_clock_frame(limit=3)
    dist = validate_distribution(df)
    assert dist["n"] > 100
    assert 0.0 <= dist["mean"] <= 24.0
    assert (df["shot_clock_proxy"] >= 0.0).all()
    assert (df["shot_clock_proxy"] <= 24.0).all()
    assert dist["pct_negative"] < 0.10  # the task's own broken-inference bar


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
