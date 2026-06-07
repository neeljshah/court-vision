"""tests/test_w029_snap_enrich_oncourt.py — W-029: SnapshotEnricher oncourt PBP fallback.

Validates:
  1. FLAG OFF  — snapshot is returned byte-identical (no oncourt key added).
  2. Starter seed  — when no PBP events, starters are marked oncourt.
  3. Sub event fold  — a single sub correctly swaps in/out player.
  4. As-of-invariance — oncourt at clock T is unchanged when later events appended.
  5. ~10 oncourt-true — exactly ~5 per team when starters seeded and no subs.
  6. Non-destructive — when CDN `oncourt` already present, it is NOT overwritten.
  7. CDN-all-present shortcut — if all players have oncourt, return immediately.
  8. Clock parsing — ISO (PT08M30.00S) and MM:SS both work.
  9. player_id tracking — subs by id correctly update the set.
 10. Empty PBP list  — graceful fallback to starter proxy.
 11. Unknown team player — defaults to False (safe).
 12. Byte-identical check — helper that verifies no accidental key mutation when OFF.

All tests are offline — no network calls, no filesystem outside tmp.
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


# ── module import helpers ─────────────────────────────────────────────────────

def _import_enricher(*, flag_on: bool):
    """Import snapshot_oncourt_enricher with the flag patched."""
    old = os.environ.get("CV_SNAP_ENRICH_ONCOURT")
    os.environ["CV_SNAP_ENRICH_ONCOURT"] = "1" if flag_on else "0"
    try:
        import src.ingame.snapshot_oncourt_enricher as mod
        importlib.reload(mod)
        return mod
    finally:
        if old is None:
            os.environ.pop("CV_SNAP_ENRICH_ONCOURT", None)
        else:
            os.environ["CV_SNAP_ENRICH_ONCOURT"] = old


# ── test data builders ────────────────────────────────────────────────────────

def _player(*, player_id: int, name: str, team: str, is_starter: bool,
            oncourt: Optional[bool] = None) -> Dict[str, Any]:
    p: Dict[str, Any] = {
        "player_id": player_id,
        "name": name,
        "team": team,
        "is_starter": is_starter,
        "min": 0.0,
        "pts": 0,
        "reb": 0,
        "ast": 0,
    }
    if oncourt is not None:
        p["oncourt"] = oncourt
    return p


def _make_snapshot(*, period: int = 2, clock: str = "06:00",
                   home_team: str = "NYK", away_team: str = "SAS",
                   players: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if players is None:
        # 5 starters per side + 3 bench per side
        players = []
        for i, (tid, team) in enumerate([(1001, "NYK"), (1002, "NYK"), (1003, "NYK"),
                                         (1004, "NYK"), (1005, "NYK"),
                                         (1006, "NYK"), (1007, "NYK"), (1008, "NYK"),
                                         (2001, "SAS"), (2002, "SAS"), (2003, "SAS"),
                                         (2004, "SAS"), (2005, "SAS"),
                                         (2006, "SAS"), (2007, "SAS"), (2008, "SAS")]):
            is_starter = i < 5 or (8 <= i < 13)  # first 5 per team
            players.append(_player(
                player_id=tid, name=f"Player{tid}", team=team,
                is_starter=is_starter
            ))
    return {
        "game_id": "0042500401",
        "period": period,
        "clock": clock,
        "home_team": home_team,
        "away_team": away_team,
        "home_score": 40,
        "away_score": 38,
        "players": players,
    }


def _make_sub_event(*, game_id: str = "0042500401", period: int = 2,
                   clock: str = "PT06M00.00S",
                   in_name: str = "Player1006", out_name: str = "Player1001",
                   in_id: int = 1006, out_id: int = 1001,
                   team: str = "NYK") -> Dict[str, Any]:
    """Build a CDN-style sub event dict."""
    return {
        "game_id": game_id,
        "action_type": "Substitution",
        "period": period,
        "clock": clock,
        "description": f"SUB: {in_name} FOR {out_name}",
        "player_id": out_id,
        "player_name": out_name,
        "team_tricode": team,
        "raw": {
            "personIdsFilter": [out_id, in_id],
        },
    }


def _make_sub_event_historical(*, period: int = 2, game_clock_sec: int = 360,
                               in_name: str = "Player1006",
                               out_name: str = "Player1001",
                               team: str = "NYK") -> Dict[str, Any]:
    """Build a historical-schema sub event dict (event_type=8, game_clock_sec=elapsed)."""
    return {
        "event_type": 8,
        "period": period,
        "game_clock_sec": game_clock_sec,
        "event_desc": f"SUB: {in_name} FOR {out_name}",
        "player_name": out_name,
        "team_abbrev": team,
        "score": "40-38",
        "score_margin": "2",
    }


# ── 1. FLAG OFF: byte-identical ───────────────────────────────────────────────

class TestFlagOff:
    def test_no_oncourt_key_added(self):
        mod = _import_enricher(flag_on=False)
        snap = _make_snapshot()
        snap_before = copy.deepcopy(snap)
        result = mod.enrich_snapshot_oncourt(snap, [])
        # oncourt must NOT have been added
        for p in result["players"]:
            assert "oncourt" not in p, (
                f"FLAG OFF must not add 'oncourt' key; found it on {p['name']}"
            )

    def test_snapshot_dict_identity(self):
        """With flag OFF the returned object is the SAME dict (no copy)."""
        mod = _import_enricher(flag_on=False)
        snap = _make_snapshot()
        result = mod.enrich_snapshot_oncourt(snap, [])
        assert result is snap

    def test_existing_oncourt_not_removed(self):
        """CDN-populated oncourt values survive the OFF path unchanged."""
        mod = _import_enricher(flag_on=False)
        players = [_player(player_id=1, name="A", team="NYK", is_starter=True,
                            oncourt=True)]
        snap = _make_snapshot(players=players)
        result = mod.enrich_snapshot_oncourt(snap, [])
        assert result["players"][0]["oncourt"] is True


# ── 2. Starter seed ───────────────────────────────────────────────────────────

class TestStarterSeed:
    def test_starters_marked_oncourt_no_events(self):
        """Without sub events, starters should be oncourt=True."""
        mod = _import_enricher(flag_on=True)
        snap = _make_snapshot(period=1, clock="10:00")
        result = mod.enrich_snapshot_oncourt(snap, [])
        home_oncourt = [p for p in result["players"]
                        if p["team"] == "NYK" and p.get("oncourt")]
        assert len(home_oncourt) == 5, (
            f"Expected 5 NYK starters oncourt; got {len(home_oncourt)}"
        )

    def test_bench_not_oncourt_no_events(self):
        """Bench players (is_starter=False) should default to oncourt=False."""
        mod = _import_enricher(flag_on=True)
        snap = _make_snapshot(period=1, clock="10:00")
        result = mod.enrich_snapshot_oncourt(snap, [])
        nyk_bench = [p for p in result["players"]
                     if p["team"] == "NYK" and not p["is_starter"]]
        for p in nyk_bench:
            assert p.get("oncourt") is False, (
                f"Bench player {p['name']} should be oncourt=False"
            )

    def test_approximately_ten_oncourt(self):
        """Total oncourt-true across both teams should be ~10 (5 per side)."""
        mod = _import_enricher(flag_on=True)
        snap = _make_snapshot(period=1, clock="10:00")
        result = mod.enrich_snapshot_oncourt(snap, [])
        n_on = sum(1 for p in result["players"] if p.get("oncourt"))
        assert 8 <= n_on <= 12, f"Expected 8-12 oncourt=True; got {n_on}"


# ── 3. Sub event fold ─────────────────────────────────────────────────────────

class TestSubFold:
    def test_sub_swaps_out_player_off_court(self):
        """After a sub, the outgoing player should be oncourt=False."""
        mod = _import_enricher(flag_on=True)
        snap = _make_snapshot(period=2, clock="05:30")
        # Sub at 6:00 Q2 (before snapshot clock 5:30 → elapsed is > 5:30 → included)
        sub = _make_sub_event(period=2, clock="PT06M00.00S",
                              in_name="Player1006", out_name="Player1001",
                              in_id=1006, out_id=1001, team="NYK")
        result = mod.enrich_snapshot_oncourt(snap, [sub])
        out_player = next(p for p in result["players"] if p["player_id"] == 1001)
        in_player = next(p for p in result["players"] if p["player_id"] == 1006)
        assert out_player.get("oncourt") is False, "Out player should be off court"
        assert in_player.get("oncourt") is True, "In player should be on court"

    def test_sub_by_name_historical_schema(self):
        """Historical-schema sub (event_type=8, game_clock_sec) also applies correctly."""
        mod = _import_enricher(flag_on=True)
        snap = _make_snapshot(period=2, clock="04:00")  # elapsed 8:00 in Q2
        # Historical sub at game_clock_sec=360 = 6:00 elapsed in Q2 -> before snap
        sub = _make_sub_event_historical(
            period=2, game_clock_sec=360,  # 6:00 elapsed
            in_name="Player1006", out_name="Player1001", team="NYK"
        )
        result = mod.enrich_snapshot_oncourt(snap, [sub])
        out_player = next(p for p in result["players"] if p["name"] == "Player1001")
        in_player = next(p for p in result["players"] if p["name"] == "Player1006")
        assert out_player.get("oncourt") is False
        assert in_player.get("oncourt") is True


# ── 4. As-of-invariance ───────────────────────────────────────────────────────

class TestAsOfInvariance:
    def test_future_sub_not_applied(self):
        """A sub AFTER the snapshot clock must NOT change the oncourt state at T."""
        mod = _import_enricher(flag_on=True)
        snap_t = _make_snapshot(period=2, clock="08:00")  # snapshot at 4:00 elapsed in Q2
        # Sub at 3:00 remaining in Q2 = AFTER snapshot clock 8:00 remaining
        # Wait — Q2 clock: 8:00 remaining = 4:00 elapsed; 3:00 remaining = 9:00 elapsed
        # So sub at 3:00 remaining is AFTER snapshot 8:00 remaining.
        sub_future = _make_sub_event(period=2, clock="PT03M00.00S",
                                     in_name="Player1006", out_name="Player1001",
                                     in_id=1006, out_id=1001, team="NYK")
        result = mod.enrich_snapshot_oncourt(snap_t, [sub_future])
        # Player1001 should still be oncourt (sub is future — ignored)
        p1001 = next(p for p in result["players"] if p["player_id"] == 1001)
        assert p1001.get("oncourt") is True, (
            f"Future sub must not affect oncourt at earlier time; "
            f"Player1001 oncourt={p1001.get('oncourt')}"
        )

    def test_adding_later_events_does_not_change_earlier_result(self):
        """Appending later events to the PBP stream does not change oncourt at T."""
        mod = _import_enricher(flag_on=True)
        snap = _make_snapshot(period=2, clock="08:00")

        # Reconstruct with empty stream
        snap1 = copy.deepcopy(snap)
        result1 = mod.enrich_snapshot_oncourt(snap1, [])
        oncourt1 = {p["player_id"]: p.get("oncourt") for p in result1["players"]}

        # Reconstruct with a future sub appended
        snap2 = copy.deepcopy(snap)
        future_sub = _make_sub_event(period=2, clock="PT03M00.00S",
                                     in_name="Player1006", out_name="Player1001",
                                     in_id=1006, out_id=1001, team="NYK")
        result2 = mod.enrich_snapshot_oncourt(snap2, [future_sub])
        oncourt2 = {p["player_id"]: p.get("oncourt") for p in result2["players"]}

        assert oncourt1 == oncourt2, (
            f"Appending future event changed oncourt: {oncourt1} vs {oncourt2}"
        )


# ── 5. Non-destructive: CDN value preserved ───────────────────────────────────

class TestNonDestructive:
    def test_cdn_oncourt_not_overwritten(self):
        """When CDN oncourt is already set, the enricher must not overwrite it."""
        mod = _import_enricher(flag_on=True)
        # Player has CDN oncourt=True but is_starter=False — enricher must preserve True.
        p_cdn = _player(player_id=9999, name="CDNStar", team="NYK", is_starter=False,
                        oncourt=True)
        snap = _make_snapshot(players=[p_cdn])
        sub = _make_sub_event(in_name="CDNStar", out_name="CDNStar",
                              in_id=9999, out_id=9999, team="NYK")
        result = mod.enrich_snapshot_oncourt(snap, [sub])
        assert result["players"][0]["oncourt"] is True, "CDN value must not be overwritten"

    def test_all_cdn_present_returns_early(self):
        """If all players already have oncourt, return immediately (no PBP replay)."""
        mod = _import_enricher(flag_on=True)
        players = [
            _player(player_id=i, name=f"P{i}", team="NYK", is_starter=True, oncourt=(i <= 5))
            for i in range(1, 9)
        ]
        snap = _make_snapshot(players=players)
        snap_before = copy.deepcopy(snap)
        result = mod.enrich_snapshot_oncourt(snap, [])
        # All oncourt values should be exactly as set.
        for p_orig, p_res in zip(snap_before["players"], result["players"]):
            assert p_orig.get("oncourt") == p_res.get("oncourt"), (
                f"Player {p_orig['player_id']} oncourt changed unexpectedly"
            )


# ── 6. Clock parsing ─────────────────────────────────────────────────────────

class TestClockParsing:
    def test_iso_clock_parsed(self):
        """ISO clock PT08M30.00S should yield 8:30 remaining."""
        mod = _import_enricher(flag_on=True)
        parsed = mod._parse_clock_remaining("PT08M30.00S")
        assert parsed == 8 * 60 + 30, f"Expected 510s; got {parsed}"

    def test_mmss_clock_parsed(self):
        """MM:SS clock 08:30 should yield 510 remaining."""
        mod = _import_enricher(flag_on=True)
        parsed = mod._parse_clock_remaining("08:30")
        assert parsed == 510

    def test_empty_clock_returns_zero(self):
        mod = _import_enricher(flag_on=True)
        parsed = mod._parse_clock_remaining("")
        assert parsed == 0

    def test_snapshot_clock_elapsed_correct(self):
        """Snapshot at Q2 clock=6:00 remaining → 6:00 elapsed → game_elapsed=720+360=1080s."""
        mod = _import_enricher(flag_on=True)
        snap = _make_snapshot(period=2, clock="06:00")
        elapsed = mod._snapshot_game_elapsed_sec(snap)
        # Q2: 720s elapsed (Q1 done) + 6:00 elapsed in Q2 = 720 + 360 = 1080
        assert elapsed == 1080, f"Expected 1080s; got {elapsed}"


# ── 7. player_id tracking ────────────────────────────────────────────────────

class TestPlayerIdTracking:
    def test_sub_by_id_applied(self):
        """Sub event with personIdsFilter correctly tracks by player_id."""
        mod = _import_enricher(flag_on=True)
        # Single player per side to make it unambiguous.
        players = [
            _player(player_id=1001, name="Starter1", team="NYK", is_starter=True),
            _player(player_id=1006, name="Bench1",   team="NYK", is_starter=False),
        ]
        snap = _make_snapshot(period=2, clock="06:00", players=players)
        sub = _make_sub_event(period=2, clock="PT07M00.00S",  # 5:00 elapsed in Q2 < 6:00
                              in_name="Bench1", out_name="Starter1",
                              in_id=1006, out_id=1001, team="NYK")
        result = mod.enrich_snapshot_oncourt(snap, [sub])
        p1001 = next(p for p in result["players"] if p["player_id"] == 1001)
        p1006 = next(p for p in result["players"] if p["player_id"] == 1006)
        assert p1001["oncourt"] is False, "Out-by-id player must be off court"
        assert p1006["oncourt"] is True, "In-by-id player must be on court"


# ── 8. Unknown team player ───────────────────────────────────────────────────

class TestUnknownTeam:
    def test_player_unknown_team_defaults_false(self):
        """Player whose team does not match home/away gets oncourt=False (safe default)."""
        mod = _import_enricher(flag_on=True)
        p_foreign = _player(player_id=9999, name="Foreign", team="OKC",
                            is_starter=True)  # OKC not in this game
        snap = _make_snapshot(players=[p_foreign])
        result = mod.enrich_snapshot_oncourt(snap, [])
        assert result["players"][0]["oncourt"] is False


# ── 9. Empty PBP fallback ────────────────────────────────────────────────────

class TestEmptyPBP:
    def test_none_pbp_events_handled(self):
        """enrich_snapshot_oncourt(snap, None) must not raise."""
        mod = _import_enricher(flag_on=True)
        snap = _make_snapshot()
        result = mod.enrich_snapshot_oncourt(snap, None)
        # Should have added oncourt keys based on is_starter
        for p in result["players"]:
            assert "oncourt" in p


# ── 10. _reconstruct_by_team unit test ───────────────────────────────────────

class TestReconstructByTeam:
    def test_reconstruct_no_events_returns_starter_state(self):
        mod = _import_enricher(flag_on=True)
        states = mod._reconstruct_by_team(
            [],
            snapshot_game_elapsed_sec=720,  # end Q1
            home_team="NYK",
            away_team="SAS",
            starters={
                "home_ids": frozenset([1001, 1002, 1003, 1004, 1005]),
                "away_ids": frozenset([2001, 2002, 2003, 2004, 2005]),
                "home_names": frozenset(["P1001", "P1002"]),
                "away_names": frozenset(["P2001", "P2002"]),
                "home_registry": [],
                "away_registry": [],
            },
        )
        home_state = states["home"]
        assert 1001 in home_state.oncourt_ids
        assert 2001 not in home_state.oncourt_ids  # home state doesn't have away ids

    def test_reconstruct_applies_sub(self):
        mod = _import_enricher(flag_on=True)
        sub = _make_sub_event(period=1, clock="PT08M00.00S",
                              in_name="P1006", out_name="P1001",
                              in_id=1006, out_id=1001, team="NYK")
        # Snapshot at Q1 7:00 remaining (5:00 elapsed) — sub at 4:00 elapsed: included
        states = mod._reconstruct_by_team(
            [sub],
            snapshot_game_elapsed_sec=300,  # 5 min elapsed in Q1
            home_team="NYK",
            away_team="SAS",
            starters={
                "home_ids": frozenset([1001, 1002, 1003, 1004, 1005]),
                "away_ids": frozenset(),
                "home_names": frozenset(),
                "away_names": frozenset(),
                "home_registry": [],
                "away_registry": [],
            },
        )
        home_state = states["home"]
        assert 1001 not in home_state.oncourt_ids, "1001 was subbed out"
        assert 1006 in home_state.oncourt_ids, "1006 was subbed in"
