"""tests/conformance/nba/test_nba_pbp_mapper.py — NBAPBPEventMapper conformance.

DOMAIN_ADAPTER_SPEC §2(c) TRUNCATION-INVARIANCE INVARIANT
----------------------------------------------------------
For games 0042500401 (G1) and 0042500402 (G2):

  1. SCORE-FOLD INVARIANT: fold (sum ``points`` by side) over ALL
     ``CanonicalEvent`` instances returned by ``iter_game`` must equal the
     cached box-score totals for home and away EXACTLY (integer equality).

  2. PREFIX-CUT INVARIANT: truncate the raw action stream at several offsets;
     the running folded score at each cut must match the action's own
     ``scoreHome``/``scoreAway`` running-score field at that cut point.

Offline only — reads from ``data/cache/team_system/{pbp,box}/``.
No network calls.  Run ONLY this file.

Known gap — G3 NOT CACHED
Game 0042500403 (SAS win 115–111, 2026-06-08) is absent from the local
cache.  Seed the file and mirror the TestScoreFold / TestPrefixCut
parametrization to extend coverage.

Python 3.9 floor.  No cv2/torch.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Tuple

import pytest

# ---------------------------------------------------------------------------
# Project-root path bootstrap (same pattern as other conformance tests)
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_PBP_DIR = _PROJECT_ROOT / "data" / "cache" / "team_system" / "pbp"
_BOX_DIR = _PROJECT_ROOT / "data" / "cache" / "team_system" / "box"

_CACHED_GAMES = ("0042500401", "0042500402")

# Cut-points (action-list indices) for the prefix-cut invariant.
# Five representative slices spread across the game.
_CUT_OFFSETS = (50, 150, 250, 350, 450)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_box_totals(game_id: str) -> Tuple[int, int, int, int]:
    """Return (home_team_id, away_team_id, home_score, away_score)."""
    with open(_BOX_DIR / f"{game_id}.json", encoding="utf-8") as fh:
        box = json.load(fh)
    game = box["game"]
    ht = game["homeTeam"]
    at = game["awayTeam"]
    return int(ht["teamId"]), int(at["teamId"]), int(ht["score"]), int(at["score"])


def _load_actions(game_id: str) -> List[dict]:
    with open(_PBP_DIR / f"{game_id}.json", encoding="utf-8") as fh:
        data = json.load(fh)
    return data["game"]["actions"]


def _fold_score_events(game_id: str):
    """Return (home_folded, away_folded) by summing SCORE CanonicalEvents."""
    from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
    from kernel.config.pbp import CanonicalEventKind

    mapper = NBAPBPEventMapper()
    home_tid, _, _, _ = _load_box_totals(game_id)

    home_pts = 0
    away_pts = 0
    for ev in mapper.iter_game(game_id):
        if ev.kind != CanonicalEventKind.SCORE:
            continue
        if ev.points <= 0:
            continue
        if ev.side == "home":
            home_pts += ev.points
        else:
            away_pts += ev.points
    return home_pts, away_pts


def _prefix_fold(game_id: str, cut: int) -> Tuple[int, int]:
    """Return (home_folded, away_folded) after processing the first *cut* actions."""
    from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
    from kernel.config.pbp import CanonicalEventKind

    _, _, _, _ = _load_box_totals(game_id)  # force home_id resolution via iter
    mapper = NBAPBPEventMapper()

    # We need the box to get home_team_id for the mapper so "side" resolves
    # to "home"/"away" not raw team IDs.  Re-create mapper with home id.
    home_tid, _, _, _ = _load_box_totals(game_id)
    mapper = NBAPBPEventMapper(home_team_id=home_tid)

    actions = _load_actions(game_id)
    home_pts = 0
    away_pts = 0
    for raw in actions[:cut]:
        ev = mapper.to_canonical(raw)
        if ev.kind != CanonicalEventKind.SCORE or ev.points <= 0:
            continue
        if ev.side == "home":
            home_pts += ev.points
        else:
            away_pts += ev.points
    return home_pts, away_pts


def _running_score_at(game_id: str, cut: int) -> Tuple[int, int]:
    """Return the running (scoreHome, scoreAway) from the last action before *cut*."""
    actions = _load_actions(game_id)
    last = actions[min(cut, len(actions)) - 1]
    return int(last["scoreHome"]), int(last["scoreAway"])


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

class TestProtocolConformance:
    """NBAPBPEventMapper satisfies the kernel PBPEventMapper protocol."""

    def test_isinstance_check(self):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
        from kernel.config.pbp import PBPEventMapper

        mapper = NBAPBPEventMapper()
        assert isinstance(mapper, PBPEventMapper), (
            "NBAPBPEventMapper must satisfy the PBPEventMapper runtime-checkable protocol"
        )

    def test_to_canonical_returns_canonical_event(self):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
        from kernel.config.pbp import CanonicalEvent

        mapper = NBAPBPEventMapper()
        # Minimal synthetic action dict
        raw = {
            "actionNumber": 7,
            "period": 1,
            "clock": "PT11M45.00S",
            "actionType": "3pt",
            "subType": "Jump Shot",
            "shotResult": "Made",
            "teamId": 1610612752,
            "personId": 1628973,
            "scoreHome": "0",
            "scoreAway": "3",
            "pointsTotal": 3,
        }
        ev = mapper.to_canonical(raw)
        assert isinstance(ev, CanonicalEvent)

    def test_to_canonical_never_returns_none(self):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper

        mapper = NBAPBPEventMapper()
        weird = {"actionType": "UNKNOWN_TYPE", "period": 1, "clock": "PT05M00.00S"}
        ev = mapper.to_canonical(weird)
        assert ev is not None

    def test_possession_side_method_exists(self):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper

        mapper = NBAPBPEventMapper()
        raw = {"period": 1, "clock": "PT10M00.00S", "actionType": "jumpball",
               "possession": 1610612752, "teamId": 1610612752}
        ev = mapper.to_canonical(raw)
        result = mapper.possession_side(ev)
        # Must return a str or None — never raise
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# Event-kind mapping smoke tests
# ---------------------------------------------------------------------------

class TestEventKindMapping:

    def test_made_2pt_is_score(self):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
        from kernel.config.pbp import CanonicalEventKind

        mapper = NBAPBPEventMapper()
        raw = {"actionType": "2pt", "shotResult": "Made",
               "period": 1, "clock": "PT10M00.00S", "teamId": 1610612759}
        ev = mapper.to_canonical(raw)
        assert ev.kind == CanonicalEventKind.SCORE
        assert ev.points == 2

    def test_made_3pt_is_score_3pts(self):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
        from kernel.config.pbp import CanonicalEventKind

        mapper = NBAPBPEventMapper()
        raw = {"actionType": "3pt", "shotResult": "Made",
               "period": 1, "clock": "PT10M00.00S", "teamId": 1610612752}
        ev = mapper.to_canonical(raw)
        assert ev.kind == CanonicalEventKind.SCORE
        assert ev.points == 3

    def test_made_freethrow_is_score_1pt(self):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
        from kernel.config.pbp import CanonicalEventKind

        mapper = NBAPBPEventMapper()
        raw = {"actionType": "freethrow", "shotResult": "Made",
               "period": 2, "clock": "PT08M00.00S", "teamId": 1610612759}
        ev = mapper.to_canonical(raw)
        assert ev.kind == CanonicalEventKind.SCORE
        assert ev.points == 1

    def test_missed_shot_is_miss(self):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
        from kernel.config.pbp import CanonicalEventKind

        mapper = NBAPBPEventMapper()
        raw = {"actionType": "2pt", "shotResult": "Missed",
               "period": 1, "clock": "PT09M00.00S", "teamId": 1610612759}
        ev = mapper.to_canonical(raw)
        assert ev.kind == CanonicalEventKind.MISS
        assert ev.points == 0

    def test_missed_ft_is_miss_zero_pts(self):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
        from kernel.config.pbp import CanonicalEventKind

        mapper = NBAPBPEventMapper()
        raw = {"actionType": "freethrow", "shotResult": "Missed",
               "period": 3, "clock": "PT05M00.00S", "teamId": 1610612759}
        ev = mapper.to_canonical(raw)
        assert ev.kind == CanonicalEventKind.MISS
        assert ev.points == 0

    def test_turnover_kind(self):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
        from kernel.config.pbp import CanonicalEventKind

        mapper = NBAPBPEventMapper()
        raw = {"actionType": "turnover", "subType": "lost ball",
               "period": 2, "clock": "PT06M00.00S", "teamId": 1610612752}
        ev = mapper.to_canonical(raw)
        assert ev.kind == CanonicalEventKind.TURNOVER

    def test_foul_is_penalty(self):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
        from kernel.config.pbp import CanonicalEventKind

        mapper = NBAPBPEventMapper()
        raw = {"actionType": "foul", "subType": "personal",
               "period": 1, "clock": "PT07M00.00S", "teamId": 1610612759}
        ev = mapper.to_canonical(raw)
        assert ev.kind == CanonicalEventKind.PENALTY

    def test_substitution_kind(self):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
        from kernel.config.pbp import CanonicalEventKind

        mapper = NBAPBPEventMapper()
        raw = {"actionType": "substitution", "subType": "out",
               "period": 2, "clock": "PT04M00.00S",
               "teamId": 1610612752, "personId": 1628973}
        ev = mapper.to_canonical(raw)
        assert ev.kind == CanonicalEventKind.SUBSTITUTION

    def test_period_start_kind(self):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
        from kernel.config.pbp import CanonicalEventKind

        mapper = NBAPBPEventMapper()
        raw = {"actionType": "period", "subType": "start",
               "period": 1, "clock": "PT12M00.00S"}
        ev = mapper.to_canonical(raw)
        assert ev.kind == CanonicalEventKind.PERIOD_START

    def test_timeout_is_stoppage(self):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
        from kernel.config.pbp import CanonicalEventKind

        mapper = NBAPBPEventMapper()
        raw = {"actionType": "timeout", "subType": "full",
               "period": 3, "clock": "PT03M00.00S", "teamId": 1610612752}
        ev = mapper.to_canonical(raw)
        assert ev.kind == CanonicalEventKind.STOPPAGE

    def test_unknown_type_is_other(self):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
        from kernel.config.pbp import CanonicalEventKind

        mapper = NBAPBPEventMapper()
        raw = {"actionType": "weird_future_type",
               "period": 2, "clock": "PT11M00.00S"}
        ev = mapper.to_canonical(raw)
        assert ev.kind == CanonicalEventKind.OTHER

    def test_detail_contains_raw_fields(self):
        """detail must be the full raw action dict."""
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper

        mapper = NBAPBPEventMapper()
        raw = {"actionType": "3pt", "shotResult": "Made",
               "period": 1, "clock": "PT10M00.00S",
               "teamId": 1610612752, "personId": 1628973,
               "shotDistance": 25.95, "assistPersonId": 1626157}
        ev = mapper.to_canonical(raw)
        assert ev.detail["shotDistance"] == 25.95
        assert ev.detail["assistPersonId"] == 1626157

    def test_ts_game_sec_q2(self):
        """Q2 start (PT12M00.00S) → 720 elapsed seconds."""
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper

        mapper = NBAPBPEventMapper()
        raw = {"actionType": "period", "subType": "start",
               "period": 2, "clock": "PT12M00.00S"}
        ev = mapper.to_canonical(raw)
        assert ev.ts_game_sec == pytest.approx(720.0)


# ---------------------------------------------------------------------------
# TRUNCATION-INVARIANCE — §2(c) done criteria
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("game_id", _CACHED_GAMES)
class TestScoreFold:
    """SCORE-FOLD INVARIANT: folded totals == cached box-score totals."""

    def test_home_pts_match_box(self, game_id: str):
        _, _, box_home, _ = _load_box_totals(game_id)
        folded_home, _ = _fold_score_events(game_id)
        assert folded_home == box_home, (
            f"[{game_id}] home folded={folded_home} != box={box_home}"
        )

    def test_away_pts_match_box(self, game_id: str):
        _, _, _, box_away = _load_box_totals(game_id)
        _, folded_away = _fold_score_events(game_id)
        assert folded_away == box_away, (
            f"[{game_id}] away folded={folded_away} != box={box_away}"
        )


@pytest.mark.parametrize("game_id", _CACHED_GAMES)
@pytest.mark.parametrize("cut", _CUT_OFFSETS)
class TestPrefixCut:
    """PREFIX-CUT INVARIANT: running fold == action's running scoreHome/Away."""

    def test_prefix_fold_matches_running_score(self, game_id: str, cut: int):
        actions = _load_actions(game_id)
        if cut > len(actions):
            pytest.skip(f"cut={cut} exceeds {len(actions)} actions for {game_id}")

        folded_home, folded_away = _prefix_fold(game_id, cut)
        run_home, run_away = _running_score_at(game_id, cut)

        assert folded_home == run_home, (
            f"[{game_id} cut={cut}] home folded={folded_home} != running={run_home}"
        )
        assert folded_away == run_away, (
            f"[{game_id} cut={cut}] away folded={folded_away} != running={run_away}"
        )


# ---------------------------------------------------------------------------
# iter_game smoke: ordering + completeness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("game_id", _CACHED_GAMES)
class TestIterGame:

    def test_yields_events(self, game_id: str):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper

        mapper = NBAPBPEventMapper()
        events = list(mapper.iter_game(game_id))
        assert len(events) > 0, f"iter_game({game_id!r}) yielded no events"

    def test_action_count_matches_raw(self, game_id: str):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper

        mapper = NBAPBPEventMapper()
        events = list(mapper.iter_game(game_id))
        raw_count = len(_load_actions(game_id))
        assert len(events) == raw_count, (
            f"[{game_id}] iter_game yielded {len(events)} events "
            f"but raw PBP has {raw_count} actions"
        )

    def test_ts_game_sec_non_negative(self, game_id: str):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper

        mapper = NBAPBPEventMapper()
        for ev in mapper.iter_game(game_id):
            assert ev.ts_game_sec >= 0.0, (
                f"[{game_id}] negative ts_game_sec={ev.ts_game_sec}"
            )

    def test_score_events_have_positive_points(self, game_id: str):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
        from kernel.config.pbp import CanonicalEventKind

        mapper = NBAPBPEventMapper()
        for ev in mapper.iter_game(game_id):
            if ev.kind == CanonicalEventKind.SCORE:
                assert ev.points > 0, (
                    f"[{game_id}] SCORE event has non-positive points={ev.points}"
                )

    def test_non_score_events_have_zero_points(self, game_id: str):
        from domains.basketball_nba.pbp_mapper import NBAPBPEventMapper
        from kernel.config.pbp import CanonicalEventKind

        mapper = NBAPBPEventMapper()
        for ev in mapper.iter_game(game_id):
            if ev.kind != CanonicalEventKind.SCORE:
                assert ev.points == 0, (
                    f"[{game_id}] non-SCORE {ev.kind} has points={ev.points}"
                )
