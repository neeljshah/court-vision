"""tests/test_w035_snap_bonus.py — W-035: SnapshotEnricher for in_bonus / team_fouls_period.

Validates:
  1.  FLAG OFF — snapshot returned byte-identical (no new keys).
  2.  FLAG ON, empty PBP — team_fouls=0, in_bonus=False.
  3.  5th team foul flips in_bonus — exactly at BONUS_FOULS=5.
  4.  4th team foul does NOT flip in_bonus.
  5.  As-of-invariance — future foul events do not change result at T.
  6.  Period reset — team fouls reset to 0 at period boundary.
  7.  Offensive foul NOT counted toward team fouls.
  8.  Technical foul NOT counted toward team fouls.
  9.  Snapshot root keys attached (home/away_team_fouls_period, home/away_in_bonus,
       snap_margin, snap_clock_remaining_sec).
 10.  Player rows receive per-player fields (team_fouls_period, in_bonus,
       snap_margin, snap_clock_remaining_sec).
 11.  Non-destructive — existing snapshot root keys not overwritten.
 12.  Non-destructive — existing player row keys not overwritten.
 13.  Running Tn (Pk.Tn) count used authoritatively (takes max, not +1 each time).
 14.  Away team foul count tracked independently from home.
 15.  Unknown team player gets team_fouls=0, in_bonus=False.
 16.  ISO clock format events parsed correctly.
 17.  MM:SS clock format events parsed correctly.
 18.  snap_margin computed from home_score / away_score.
 19.  snap_clock_remaining_sec from snapshot clock field.
 20.  in_bonus correct for both home and away players in same snapshot.
 21.  Flagrant foul counts toward team fouls (same as personal).
 22.  None pbp_events defaults correctly.
 23.  Replay: 5 fouls in Q1, verify bonus; then Q2 snapshot — bonus reset to False.

All tests offline — no network calls, no filesystem access.
"""
from __future__ import annotations

import copy
import importlib
import os
import sys
from typing import Any, Dict, List, Optional

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)


# ---------------------------------------------------------------------------
# Module import helper (patches the module-level flag at import time)
# ---------------------------------------------------------------------------

def _import_enricher(*, flag_on: bool):
    """Import snapshot_bonus_enricher with CV_SNAP_BONUS patched to flag_on."""
    old = os.environ.get("CV_SNAP_BONUS")
    os.environ["CV_SNAP_BONUS"] = "1" if flag_on else "0"
    try:
        import src.ingame.snapshot_bonus_enricher as mod
        importlib.reload(mod)
        return mod
    finally:
        if old is None:
            os.environ.pop("CV_SNAP_BONUS", None)
        else:
            os.environ["CV_SNAP_BONUS"] = old


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _player(pid: int, name: str, team: str) -> Dict[str, Any]:
    return {
        "player_id": pid,
        "name": name,
        "team": team,
        "mp": 0.0,
        "pts": 0,
        "reb": 0,
        "ast": 0,
        "pf": 0,
    }


def _snap(
    period: int = 1,
    clock: str = "12:00",
    home: str = "HOM",
    away: str = "AWY",
    home_score: int = 0,
    away_score: int = 0,
    players: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "period": period,
        "clock": clock,
        "home_team": home,
        "away_team": away,
        "home_score": home_score,
        "away_score": away_score,
        "players": players or [],
    }


def _foul_event(
    *,
    team: str,
    pid: int,
    name: str,
    period: int,
    clock_remaining_sec: int,
    player_pf: int,
    team_fouls: int,
    description_override: Optional[str] = None,
    is_offensive: bool = False,
    is_technical: bool = False,
) -> Dict[str, Any]:
    """Build a personal foul event in live CDN format."""
    mins = clock_remaining_sec // 60
    secs = clock_remaining_sec % 60
    clock_iso = f"PT{mins:02d}M{secs:02d}.00S"
    if description_override is not None:
        desc = description_override
    elif is_offensive:
        desc = f"Offensive foul: {name} (P{player_pf}.T{team_fouls})"
    elif is_technical:
        desc = f"T.FOUL: {name} (P{player_pf}.T{team_fouls})"
    else:
        desc = f"Personal foul: {name} (P{player_pf}.T{team_fouls})"
    ev: Dict[str, Any] = {
        "period": period,
        "clock": clock_iso,
        "event_type": 6,
        "action_type": "Foul",
        "team_tricode": team,
        "player_id": pid,
        "player_name": name,
        "description": desc,
    }
    if is_offensive:
        ev["offensive_foul"] = True
    if is_technical:
        ev["technical"] = True
    return ev


def _foul_event_mmss(
    *,
    team: str,
    pid: int,
    name: str,
    period: int,
    clock_mmss: str,
    player_pf: int,
    team_fouls: int,
) -> Dict[str, Any]:
    """Build a foul event with MM:SS clock format."""
    desc = f"Personal foul: {name} (P{player_pf}.T{team_fouls})"
    return {
        "period": period,
        "clock": clock_mmss,
        "event_type": 6,
        "action_type": "Foul",
        "team_tricode": team,
        "player_id": pid,
        "player_name": name,
        "description": desc,
    }


def _end_period_event(period: int) -> Dict[str, Any]:
    return {
        "period": period,
        "clock": "PT00M00.00S",
        "event_type": 13,
        "action_type": "Period",
        "description": f"End Period {period}",
    }


def _make_5_fouls(team: str, period: int) -> List[Dict[str, Any]]:
    """Build 5 personal foul events for a team in a period (fouls 1..5 at spread clocks).

    All fouls are placed in the first 5 minutes of the period (remaining=700..500),
    so a snapshot at 4:00 remaining (240 sec) or less will have all 5 in the past.
    """
    events = []
    for i in range(1, 6):
        # fouls at remaining=700, 640, 580, 520, 460 (all in first ~4.3 min)
        remaining = 700 - (i - 1) * 60
        events.append(_foul_event(
            team=team, pid=100 + i, name=f"Player{i}", period=period,
            clock_remaining_sec=remaining, player_pf=1, team_fouls=i,
        ))
    return events


# ---------------------------------------------------------------------------
# Tests: FLAG OFF
# ---------------------------------------------------------------------------

class TestFlagOff:
    def test_snapshot_returned_unchanged(self):
        mod = _import_enricher(flag_on=False)
        snap = _snap(period=1, players=[_player(1, "Smith", "HOM")])
        before = copy.deepcopy(snap)
        result = mod.enrich_snapshot_bonus(snap, pbp_events=[])
        assert result is snap
        assert result == before

    def test_no_new_keys_added_to_snapshot(self):
        mod = _import_enricher(flag_on=False)
        snap = _snap(period=1)
        before_keys = frozenset(snap.keys())
        mod.enrich_snapshot_bonus(snap, pbp_events=[])
        assert frozenset(snap.keys()) == before_keys

    def test_no_new_keys_added_to_player_rows(self):
        mod = _import_enricher(flag_on=False)
        p = _player(1, "Jones", "HOM")
        snap = _snap(players=[p])
        before_player_keys = frozenset(p.keys())
        mod.enrich_snapshot_bonus(snap, pbp_events=[])
        assert frozenset(snap["players"][0].keys()) == before_player_keys


# ---------------------------------------------------------------------------
# Tests: FLAG ON, empty PBP
# ---------------------------------------------------------------------------

class TestFlagOnEmptyPBP:
    def test_team_fouls_default_zero(self):
        mod = _import_enricher(flag_on=True)
        snap = _snap(period=1)
        mod.enrich_snapshot_bonus(snap, pbp_events=[])
        assert snap["home_team_fouls_period"] == 0
        assert snap["away_team_fouls_period"] == 0

    def test_in_bonus_default_false(self):
        mod = _import_enricher(flag_on=True)
        snap = _snap(period=1)
        mod.enrich_snapshot_bonus(snap, pbp_events=[])
        assert snap["home_in_bonus"] is False
        assert snap["away_in_bonus"] is False

    def test_snap_margin_computed(self):
        mod = _import_enricher(flag_on=True)
        snap = _snap(period=2, home_score=55, away_score=48)
        mod.enrich_snapshot_bonus(snap, pbp_events=[])
        assert snap["snap_margin"] == pytest.approx(7.0)

    def test_snap_clock_remaining_sec_computed(self):
        mod = _import_enricher(flag_on=True)
        snap = _snap(period=2, clock="06:30")
        mod.enrich_snapshot_bonus(snap, pbp_events=[])
        assert snap["snap_clock_remaining_sec"] == pytest.approx(390.0)

    def test_player_fields_attached(self):
        mod = _import_enricher(flag_on=True)
        snap = _snap(period=1, players=[_player(1, "Smith", "HOM")])
        mod.enrich_snapshot_bonus(snap, pbp_events=[])
        p = snap["players"][0]
        assert "team_fouls_period" in p
        assert "in_bonus" in p
        assert "snap_margin" in p
        assert "snap_clock_remaining_sec" in p

    def test_none_pbp_events_defaults_correctly(self):
        mod = _import_enricher(flag_on=True)
        snap = _snap(period=1, players=[_player(1, "Smith", "HOM")])
        mod.enrich_snapshot_bonus(snap, pbp_events=None)
        assert snap["home_team_fouls_period"] == 0
        assert snap["home_in_bonus"] is False


# ---------------------------------------------------------------------------
# Tests: Bonus flip at 5th foul
# ---------------------------------------------------------------------------

class TestBonusFlip:
    def test_5th_foul_flips_in_bonus(self):
        """Exactly 5 fouls by away team → home team in bonus."""
        mod = _import_enricher(flag_on=True)
        events = _make_5_fouls(team="AWY", period=1)
        # Snapshot after all 5 fouls (5th at remaining=460, snapshot at remaining=200)
        snap = _snap(period=1, clock="03:00")
        mod.enrich_snapshot_bonus(snap, pbp_events=events)
        assert snap["away_team_fouls_period"] == 5
        assert snap["home_in_bonus"] is True

    def test_4th_foul_does_not_flip_in_bonus(self):
        """Only 4 fouls: still NOT in bonus."""
        mod = _import_enricher(flag_on=True)
        events = _make_5_fouls(team="AWY", period=1)[:4]  # only first 4
        # 4th foul is at remaining=520; snapshot after at remaining=200
        snap = _snap(period=1, clock="03:00")
        mod.enrich_snapshot_bonus(snap, pbp_events=events)
        assert snap["away_team_fouls_period"] == 4
        assert snap["home_in_bonus"] is False

    def test_home_team_fouls_put_away_in_bonus(self):
        """5 fouls by home team → away team in bonus."""
        mod = _import_enricher(flag_on=True)
        events = _make_5_fouls(team="HOM", period=1)
        snap = _snap(period=1, clock="03:00")
        mod.enrich_snapshot_bonus(snap, pbp_events=events)
        assert snap["home_team_fouls_period"] == 5
        assert snap["away_in_bonus"] is True

    def test_bonus_per_player_correct(self):
        """Home player is in_bonus when away team has 5 fouls."""
        mod = _import_enricher(flag_on=True)
        events = _make_5_fouls(team="AWY", period=1)
        home_p = _player(1, "HomePlayer", "HOM")
        away_p = _player(2, "AwayPlayer", "AWY")
        snap = _snap(period=1, clock="03:00",
                     home="HOM", away="AWY",
                     players=[home_p, away_p])
        mod.enrich_snapshot_bonus(snap, pbp_events=events)
        # Home player in bonus (away has 5 fouls)
        assert snap["players"][0]["in_bonus"] is True
        # Away player NOT in bonus (home has 0 fouls)
        assert snap["players"][1]["in_bonus"] is False

    def test_running_tn_count_used_authoritatively(self):
        """If foul desc carries (Pk.Tn), use Tn as running count not +1 each time."""
        mod = _import_enricher(flag_on=True)
        # Send 3 fouls but with Tn=5 in the last event (authoritative jump)
        events = [
            _foul_event(team="HOM", pid=1, name="A", period=1,
                        clock_remaining_sec=600, player_pf=1, team_fouls=1),
            _foul_event(team="HOM", pid=2, name="B", period=1,
                        clock_remaining_sec=500, player_pf=2, team_fouls=2),
            # Tn says team is at 5 already (e.g. flagrant counted elsewhere)
            _foul_event(team="HOM", pid=3, name="C", period=1,
                        clock_remaining_sec=400, player_pf=1, team_fouls=5),
        ]
        snap = _snap(period=1, clock="06:00")
        mod.enrich_snapshot_bonus(snap, pbp_events=events)
        # Running Tn max should give 5
        assert snap["home_team_fouls_period"] == 5
        assert snap["away_in_bonus"] is True


# ---------------------------------------------------------------------------
# Tests: As-of-invariance
# ---------------------------------------------------------------------------

class TestAsOfInvariance:
    def test_future_foul_does_not_change_result(self):
        """A foul after the snapshot clock must not alter the enriched values."""
        mod = _import_enricher(flag_on=True)
        early_foul = _foul_event(
            team="AWY", pid=10, name="Jones", period=1,
            clock_remaining_sec=600, player_pf=1, team_fouls=1,
        )
        future_foul = _foul_event(
            team="AWY", pid=11, name="Smith", period=1,
            # This is at 5:00 remaining = 420 sec elapsed; snapshot at 6:00 = 360 elapsed
            clock_remaining_sec=300, player_pf=2, team_fouls=2,
        )
        # Snapshot at 6:00 remaining = 360 elapsed (well before future_foul at 300 remaining)
        snap1 = _snap(period=1, clock="06:00")
        snap2 = copy.deepcopy(snap1)

        mod.enrich_snapshot_bonus(snap1, pbp_events=[early_foul])
        fouls_without_future = snap1["away_team_fouls_period"]

        mod.enrich_snapshot_bonus(snap2, pbp_events=[early_foul, future_foul])
        fouls_with_future = snap2["away_team_fouls_period"]

        assert fouls_without_future == fouls_with_future, (
            f"as-of-invariance violated: fouls changed from {fouls_without_future} to "
            f"{fouls_with_future} when future event added"
        )

    def test_future_5th_foul_does_not_flip_bonus(self):
        """4 fouls at snapshot time; 5th foul is in the future. Bonus must be False."""
        mod = _import_enricher(flag_on=True)
        # First 4 fouls at remaining=700..520 (elapsed=20..200)
        events_before = _make_5_fouls(team="AWY", period=1)[:4]
        # 5th foul at clock=300 remaining (elapsed=420) — AFTER snapshot at 400 remaining (elapsed=320)
        future_5th = _foul_event(
            team="AWY", pid=99, name="Future", period=1,
            clock_remaining_sec=300, player_pf=3, team_fouls=5,
        )
        # Snapshot at 400 remaining (elapsed=320) — all 4 early fouls in the past,
        # future_5th at 300 remaining (elapsed=420) is in the future.
        snap = _snap(period=1, clock="06:40")  # 400 remaining => elapsed=320
        mod.enrich_snapshot_bonus(snap, pbp_events=events_before + [future_5th])
        # Only 4 fouls counted; 5th is future (elapsed=420 > snapshot elapsed=320)
        assert snap["away_team_fouls_period"] == 4
        assert snap["home_in_bonus"] is False


# ---------------------------------------------------------------------------
# Tests: Period reset
# ---------------------------------------------------------------------------

class TestPeriodReset:
    def test_fouls_reset_on_period_change(self):
        """5 fouls in Q1; snapshot in Q2 with 0 fouls → bonus should be False."""
        mod = _import_enricher(flag_on=True)
        # 5 fouls in Q1
        events = _make_5_fouls(team="AWY", period=1)
        # Add an end-of-Q1 event and a Q2 foul (1 foul)
        events.append(_end_period_event(period=1))
        events.append(_foul_event(
            team="AWY", pid=200, name="Q2Player", period=2,
            clock_remaining_sec=600, player_pf=1, team_fouls=1,
        ))
        # Snapshot at Q2 start
        snap = _snap(period=2, clock="10:00")
        mod.enrich_snapshot_bonus(snap, pbp_events=events)
        # Only 1 foul counted in Q2 (reset at period change)
        assert snap["away_team_fouls_period"] == 1
        assert snap["home_in_bonus"] is False

    def test_q1_bonus_clears_in_q2_snapshot(self):
        """Bonus earned in Q1 does not carry over to Q2 snapshot."""
        mod = _import_enricher(flag_on=True)
        q1_fouls = _make_5_fouls(team="AWY", period=1)
        q1_fouls.append(_end_period_event(period=1))
        # Q2 snapshot with no Q2 fouls yet
        snap = _snap(period=2, clock="12:00")
        mod.enrich_snapshot_bonus(snap, pbp_events=q1_fouls)
        assert snap["home_in_bonus"] is False
        assert snap["away_team_fouls_period"] == 0


# ---------------------------------------------------------------------------
# Tests: Offensive and technical fouls skipped
# ---------------------------------------------------------------------------

class TestFoulExclusions:
    def test_offensive_foul_not_counted(self):
        """Offensive fouls do not advance team toward bonus."""
        mod = _import_enricher(flag_on=True)
        events = [
            _foul_event(team="HOM", pid=1, name="A", period=1,
                        clock_remaining_sec=600, player_pf=1, team_fouls=1,
                        is_offensive=True),
        ]
        snap = _snap(period=1, clock="06:00")
        mod.enrich_snapshot_bonus(snap, pbp_events=events)
        assert snap["home_team_fouls_period"] == 0

    def test_technical_foul_not_counted(self):
        """Technical fouls do not advance team toward bonus."""
        mod = _import_enricher(flag_on=True)
        events = [
            _foul_event(team="HOM", pid=1, name="A", period=1,
                        clock_remaining_sec=600, player_pf=1, team_fouls=1,
                        is_technical=True),
        ]
        snap = _snap(period=1, clock="06:00")
        mod.enrich_snapshot_bonus(snap, pbp_events=events)
        assert snap["home_team_fouls_period"] == 0

    def test_offensive_in_description_not_counted(self):
        """Description-based offensive foul detection via 'OFFENSIVE' keyword."""
        mod = _import_enricher(flag_on=True)
        events = [
            _foul_event(team="HOM", pid=1, name="A", period=1,
                        clock_remaining_sec=600, player_pf=1, team_fouls=1,
                        description_override="Offensive foul: A (P1.T1)"),
        ]
        snap = _snap(period=1, clock="06:00")
        mod.enrich_snapshot_bonus(snap, pbp_events=events)
        assert snap["home_team_fouls_period"] == 0

    def test_personal_and_offensive_mix(self):
        """4 personal + 1 offensive = 4 team fouls (not 5; bonus NOT reached)."""
        mod = _import_enricher(flag_on=True)
        events = [
            _foul_event(team="AWY", pid=1, name="A", period=1,
                        clock_remaining_sec=650, player_pf=1, team_fouls=1),
            _foul_event(team="AWY", pid=2, name="B", period=1,
                        clock_remaining_sec=600, player_pf=1, team_fouls=2),
            _foul_event(team="AWY", pid=3, name="C", period=1,
                        clock_remaining_sec=550, player_pf=1, team_fouls=3),
            _foul_event(team="AWY", pid=4, name="D", period=1,
                        clock_remaining_sec=500, player_pf=1, team_fouls=4),
            # Offensive foul — should not count
            _foul_event(team="AWY", pid=5, name="E", period=1,
                        clock_remaining_sec=450, player_pf=2, team_fouls=4,
                        is_offensive=True),
        ]
        snap = _snap(period=1, clock="06:00")
        mod.enrich_snapshot_bonus(snap, pbp_events=events)
        assert snap["away_team_fouls_period"] == 4
        assert snap["home_in_bonus"] is False

    def test_flagrant_foul_counts_toward_bonus(self):
        """Flagrant fouls (not offensive/technical) DO count toward team fouls."""
        mod = _import_enricher(flag_on=True)
        events = [
            # 4 personal fouls
            *_make_5_fouls(team="AWY", period=1)[:4],
            # 5th: flagrant (no offensive/technical qualifier)
            _foul_event(team="AWY", pid=99, name="FlagrantPlayer", period=1,
                        clock_remaining_sec=200, player_pf=2, team_fouls=5,
                        description_override="Flagrant foul 1: FlagrantPlayer (P2.T5)"),
        ]
        snap = _snap(period=1, clock="02:30")
        mod.enrich_snapshot_bonus(snap, pbp_events=events)
        assert snap["away_team_fouls_period"] == 5
        assert snap["home_in_bonus"] is True


# ---------------------------------------------------------------------------
# Tests: Non-destructive
# ---------------------------------------------------------------------------

class TestNonDestructive:
    def test_existing_snap_root_key_not_overwritten(self):
        mod = _import_enricher(flag_on=True)
        snap = _snap(period=1)
        snap["home_team_fouls_period"] = 99  # pre-existing
        mod.enrich_snapshot_bonus(snap, pbp_events=[])
        assert snap["home_team_fouls_period"] == 99

    def test_existing_player_in_bonus_not_overwritten(self):
        mod = _import_enricher(flag_on=True)
        p = _player(1, "Smith", "HOM")
        p["in_bonus"] = True  # pre-existing value
        snap = _snap(players=[p])
        mod.enrich_snapshot_bonus(snap, pbp_events=[])
        assert snap["players"][0]["in_bonus"] is True

    def test_existing_snap_margin_not_overwritten(self):
        mod = _import_enricher(flag_on=True)
        snap = _snap(period=1, home_score=10, away_score=5)
        snap["snap_margin"] = 999.0  # pre-existing
        mod.enrich_snapshot_bonus(snap, pbp_events=[])
        assert snap["snap_margin"] == 999.0


# ---------------------------------------------------------------------------
# Tests: Clock format parsing
# ---------------------------------------------------------------------------

class TestClockParsing:
    def test_iso_clock_format_event(self):
        """ISO format PT10M00.00S correctly parsed for event timestamp."""
        mod = _import_enricher(flag_on=True)
        ev = _foul_event(team="HOM", pid=1, name="A", period=1,
                         clock_remaining_sec=600,  # 10:00 remaining (elapsed=120)
                         player_pf=1, team_fouls=1)
        # Snapshot at 8:00 remaining (elapsed=240) — event at elapsed=120 is before snapshot
        snap = _snap(period=1, clock="PT08M00.00S")
        mod.enrich_snapshot_bonus(snap, pbp_events=[ev])
        assert snap["home_team_fouls_period"] == 1

    def test_mmss_clock_format_event(self):
        """MM:SS clock format in event correctly parsed."""
        mod = _import_enricher(flag_on=True)
        ev = _foul_event_mmss(team="HOM", pid=1, name="A", period=1,
                              clock_mmss="08:00",  # 8:00 remaining
                              player_pf=1, team_fouls=1)
        # Snapshot at 6:00 remaining
        snap = _snap(period=1, clock="06:00")
        mod.enrich_snapshot_bonus(snap, pbp_events=[ev])
        assert snap["home_team_fouls_period"] == 1

    def test_iso_snap_clock_remaining(self):
        """Snapshot with ISO clock: snap_clock_remaining_sec correct."""
        mod = _import_enricher(flag_on=True)
        snap = _snap(period=3, clock="PT04M30.00S")
        mod.enrich_snapshot_bonus(snap, pbp_events=[])
        assert snap["snap_clock_remaining_sec"] == pytest.approx(270.0)


# ---------------------------------------------------------------------------
# Tests: Both teams tracked independently
# ---------------------------------------------------------------------------

class TestBothTeams:
    def test_home_and_away_tracked_independently(self):
        """Home: 3 fouls, Away: 5 fouls — correct per-team counts."""
        mod = _import_enricher(flag_on=True)
        home_fouls = [
            _foul_event(team="HOM", pid=10 + i, name=f"H{i}", period=1,
                        clock_remaining_sec=700 - i * 50, player_pf=1, team_fouls=i + 1)
            for i in range(3)
        ]
        away_fouls = _make_5_fouls(team="AWY", period=1)
        all_events = home_fouls + away_fouls
        snap = _snap(period=1, clock="04:00")
        mod.enrich_snapshot_bonus(snap, pbp_events=all_events)
        assert snap["home_team_fouls_period"] == 3
        assert snap["away_team_fouls_period"] == 5
        assert snap["home_in_bonus"] is True   # away has 5 fouls
        assert snap["away_in_bonus"] is False  # home has only 3

    def test_unknown_team_player_defaults(self):
        """Player from unknown team gets team_fouls=0, in_bonus=False (regardless of bonus state)."""
        mod = _import_enricher(flag_on=True)
        p = _player(1, "Unknown", "OTH")
        # Use clock=03:00 so all 5 away fouls are in the past
        snap = _snap(period=1, clock="03:00", players=[p])
        mod.enrich_snapshot_bonus(snap, pbp_events=_make_5_fouls(team="AWY", period=1))
        pp = snap["players"][0]
        assert pp["team_fouls_period"] == 0
        assert pp["in_bonus"] is False

    def test_both_teams_in_bonus_simultaneously(self):
        """Both teams can be in bonus simultaneously (each has >=5 fouls)."""
        mod = _import_enricher(flag_on=True)
        home_fouls = _make_5_fouls(team="HOM", period=1)
        away_fouls = _make_5_fouls(team="AWY", period=1)
        snap = _snap(period=1, clock="04:00")
        mod.enrich_snapshot_bonus(snap, pbp_events=home_fouls + away_fouls)
        assert snap["home_in_bonus"] is True
        assert snap["away_in_bonus"] is True


# ---------------------------------------------------------------------------
# Tests: Snap margin
# ---------------------------------------------------------------------------

class TestSnapMargin:
    def test_margin_positive_when_home_leads(self):
        mod = _import_enricher(flag_on=True)
        snap = _snap(period=3, home_score=80, away_score=72)
        mod.enrich_snapshot_bonus(snap, pbp_events=[])
        assert snap["snap_margin"] == pytest.approx(8.0)

    def test_margin_negative_when_away_leads(self):
        mod = _import_enricher(flag_on=True)
        snap = _snap(period=3, home_score=72, away_score=80)
        mod.enrich_snapshot_bonus(snap, pbp_events=[])
        assert snap["snap_margin"] == pytest.approx(-8.0)

    def test_margin_zero_when_tied(self):
        mod = _import_enricher(flag_on=True)
        snap = _snap(period=4, home_score=95, away_score=95)
        mod.enrich_snapshot_bonus(snap, pbp_events=[])
        assert snap["snap_margin"] == pytest.approx(0.0)
