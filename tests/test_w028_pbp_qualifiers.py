"""tests/test_w028_pbp_qualifiers.py — W-028: PBP qualifier promotion.

Validates:
  1. FLAG OFF  — _event_from_play() output is byte-identical to the pre-qualifier
                 schema (no new keys added).
  2. FLAG ON   — first-class qualifier fields present and correctly populated.
  3. Qualifier types: offensive_foul, technical, flagrant, and_1, fastbreak,
     ejection all parse correctly from CDN subType / qualifiers.
  4. state_featurizer.normalize_event() forwards qualifier booleans when flag ON
     (no-op / False defaults for historical events that lack the fields).
  5. EVT_FOUL accumulation in featurize_game: when flag ON, offensive fouls and
     technical fouls do NOT increment the team's bonus-foul count; personal fouls
     and flagrants DO (byte-identical when flag OFF).
  6. Byte-identical guard: featurize_game team_fouls_period is identical between
     flag-OFF and flag-ON when all raw events lack qualifier fields (historical
     path).

All tests are offline — no network calls, no filesystem outside tmp.
"""
from __future__ import annotations

import importlib
import os
import sys
from typing import Any, Dict, List

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_play(*, action_type: str = "Foul", sub_type: str = "",
               qualifiers: List[str] | None = None, action_number: int = 1,
               period: int = 1, clock: str = "PT10M00S",
               player_id: int = 1001, player_name: str = "Player",
               team_id: int = 1, team_tricode: str = "LAL",
               score_home: str = "0", score_away: str = "0") -> Dict[str, Any]:
    """Build a minimal CDN PBP play dict."""
    play: Dict[str, Any] = {
        "actionNumber": action_number,
        "actionType": action_type,
        "subType": sub_type,
        "period": period,
        "clock": clock,
        "description": f"{action_type} {sub_type}",
        "personId": player_id,
        "playerName": player_name,
        "teamId": team_id,
        "teamTricode": team_tricode,
        "scoreHome": score_home,
        "scoreAway": score_away,
    }
    if qualifiers is not None:
        play["qualifiers"] = qualifiers
    return play


_BASELINE_KEYS = frozenset({
    "game_id", "action_number", "period", "clock", "description",
    "player_id", "player_name", "team_id", "team_tricode",
    "score_home", "score_away", "raw",
})

_QUALIFIER_EXTRA_KEYS = frozenset({
    "sub_type", "qualifiers", "shot_action_number", "possession",
    "in_penalty", "and_1", "fastbreak", "offensive_foul", "technical",
    "flagrant", "ejection",
})


def _import_event_from_play(*, flag_on: bool):
    """Import _event_from_play with the flag patched to flag_on.

    Re-imports the module with a temporary env-var set so the module-level
    constant is correctly initialised for the test.
    """
    old = os.environ.get("CV_PBP_QUALIFIERS")
    os.environ["CV_PBP_QUALIFIERS"] = "1" if flag_on else "0"
    try:
        import scripts.pbp_poller as mod
        importlib.reload(mod)
        return mod._event_from_play, mod
    finally:
        if old is None:
            os.environ.pop("CV_PBP_QUALIFIERS", None)
        else:
            os.environ["CV_PBP_QUALIFIERS"] = old


def _import_featurizer(*, flag_on: bool):
    """Import state_featurizer with CV_PBP_QUALIFIERS patched."""
    old = os.environ.get("CV_PBP_QUALIFIERS")
    os.environ["CV_PBP_QUALIFIERS"] = "1" if flag_on else "0"
    try:
        import src.ingame.state_featurizer as mod
        importlib.reload(mod)
        return mod
    finally:
        if old is None:
            os.environ.pop("CV_PBP_QUALIFIERS", None)
        else:
            os.environ["CV_PBP_QUALIFIERS"] = old


# ── 1. FLAG OFF: byte-identical schema ───────────────────────────────────────

class TestFlagOff:
    def test_event_keys_unchanged_no_qualifier_keys(self):
        efp, _ = _import_event_from_play(flag_on=False)
        play = _make_play(action_type="Foul", sub_type="technical")
        ev = efp("0042500401", play)
        assert set(ev.keys()) == _BASELINE_KEYS, (
            f"FLAG OFF must not add qualifier keys; got extra: "
            f"{set(ev.keys()) - _BASELINE_KEYS}"
        )

    def test_event_raw_field_is_original_play(self):
        efp, _ = _import_event_from_play(flag_on=False)
        play = _make_play(action_type="Made Shot")
        ev = efp("0042500401", play)
        assert ev["raw"] is play

    def test_event_values_correct_baseline(self):
        efp, _ = _import_event_from_play(flag_on=False)
        play = _make_play(action_number=42, period=3, clock="PT05M00S",
                          team_tricode="OKC")
        ev = efp("0042500401", play)
        assert ev["game_id"] == "0042500401"
        assert ev["action_number"] == 42
        assert ev["period"] == 3
        assert ev["team_tricode"] == "OKC"


# ── 2. FLAG ON: first-class qualifier fields present ─────────────────────────

class TestFlagOn:
    def test_all_qualifier_keys_present(self):
        efp, _ = _import_event_from_play(flag_on=True)
        play = _make_play(action_type="Foul", sub_type="personal",
                          qualifiers=["inpenalty"])
        ev = efp("0042500401", play)
        assert _QUALIFIER_EXTRA_KEYS.issubset(set(ev.keys())), (
            f"Missing qualifier keys: {_QUALIFIER_EXTRA_KEYS - set(ev.keys())}"
        )

    def test_baseline_keys_still_present(self):
        efp, _ = _import_event_from_play(flag_on=True)
        play = _make_play()
        ev = efp("0042500401", play)
        assert _BASELINE_KEYS.issubset(set(ev.keys()))

    def test_sub_type_lowercased(self):
        efp, _ = _import_event_from_play(flag_on=True)
        play = _make_play(sub_type="Technical")
        ev = efp("0042500401", play)
        assert ev["sub_type"] == "technical"

    def test_qualifiers_list_lowercased(self):
        efp, _ = _import_event_from_play(flag_on=True)
        play = _make_play(qualifiers=["FastBreak", "InPenalty"])
        ev = efp("0042500401", play)
        assert "fastbreak" in ev["qualifiers"]
        assert "inpenalty" in ev["qualifiers"]

    def test_qualifiers_none_becomes_empty_list(self):
        efp, _ = _import_event_from_play(flag_on=True)
        play = _make_play()  # no qualifiers key
        ev = efp("0042500401", play)
        assert ev["qualifiers"] == []


# ── 3. Per-qualifier boolean flags ───────────────────────────────────────────

class TestQualifierBooleans:
    def test_in_penalty_true(self):
        efp, _ = _import_event_from_play(flag_on=True)
        ev = efp("gid", _make_play(qualifiers=["inpenalty"]))
        assert ev["in_penalty"] is True

    def test_in_penalty_false(self):
        efp, _ = _import_event_from_play(flag_on=True)
        ev = efp("gid", _make_play(qualifiers=[]))
        assert ev["in_penalty"] is False

    def test_and1_via_qualifier(self):
        efp, _ = _import_event_from_play(flag_on=True)
        ev = efp("gid", _make_play(qualifiers=["and1"]))
        assert ev["and_1"] is True

    def test_fastbreak_via_qualifier(self):
        efp, _ = _import_event_from_play(flag_on=True)
        ev = efp("gid", _make_play(qualifiers=["fastbreak"]))
        assert ev["fastbreak"] is True

    def test_fastbreak_via_sub_type(self):
        efp, _ = _import_event_from_play(flag_on=True)
        ev = efp("gid", _make_play(sub_type="fastbreak"))
        assert ev["fastbreak"] is True

    def test_offensive_foul_sub_type(self):
        efp, _ = _import_event_from_play(flag_on=True)
        ev = efp("gid", _make_play(action_type="Foul", sub_type="offensive"))
        assert ev["offensive_foul"] is True
        assert ev["technical"] is False

    def test_technical_foul_sub_type(self):
        efp, _ = _import_event_from_play(flag_on=True)
        ev = efp("gid", _make_play(action_type="Foul", sub_type="technical"))
        assert ev["technical"] is True
        assert ev["offensive_foul"] is False

    def test_flagrant1_sub_type(self):
        efp, _ = _import_event_from_play(flag_on=True)
        ev = efp("gid", _make_play(action_type="Foul", sub_type="flagrant 1"))
        assert ev["flagrant"] is True
        assert ev["ejection"] is False  # flagrant 1 alone no ejection

    def test_flagrant2_implies_ejection(self):
        efp, _ = _import_event_from_play(flag_on=True)
        ev = efp("gid", _make_play(action_type="Foul", sub_type="flagrant 2"))
        assert ev["flagrant"] is True
        assert ev["ejection"] is True

    def test_ejection_action_type(self):
        efp, _ = _import_event_from_play(flag_on=True)
        ev = efp("gid", _make_play(action_type="ejection"))
        assert ev["ejection"] is True

    def test_ejection_via_qualifier(self):
        efp, _ = _import_event_from_play(flag_on=True)
        ev = efp("gid", _make_play(qualifiers=["ejection"]))
        assert ev["ejection"] is True

    def test_personal_foul_all_false(self):
        """A plain personal foul has all qualifier booleans False."""
        efp, _ = _import_event_from_play(flag_on=True)
        ev = efp("gid", _make_play(action_type="Foul", sub_type="personal",
                                   qualifiers=[]))
        assert ev["offensive_foul"] is False
        assert ev["technical"] is False
        assert ev["flagrant"] is False
        assert ev["ejection"] is False
        assert ev["and_1"] is False
        assert ev["in_penalty"] is False


# ── 4. normalize_event: qualifier fields forwarded when flag ON ───────────────

class TestNormalizeEventQualifiers:
    def test_flag_off_no_qualifier_keys(self):
        mod = _import_featurizer(flag_on=False)
        raw = {"period": 1, "game_clock_sec": 300, "event_type": 6,
               "event_desc": "FOUL", "sub_type": "technical",
               "offensive_foul": True}
        ev = mod.normalize_event(raw)
        assert "sub_type" not in ev
        assert "offensive_foul" not in ev
        assert "qualifiers" not in ev

    def test_flag_on_forwards_sub_type(self):
        mod = _import_featurizer(flag_on=True)
        raw = {"period": 1, "game_clock_sec": 300, "event_type": 6,
               "event_desc": "FOUL", "sub_type": "technical"}
        ev = mod.normalize_event(raw)
        assert ev["sub_type"] == "technical"

    def test_flag_on_forwards_offensive_foul(self):
        mod = _import_featurizer(flag_on=True)
        raw = {"period": 1, "game_clock_sec": 300, "event_type": 6,
               "event_desc": "OFFENSIVE FOUL", "offensive_foul": True}
        ev = mod.normalize_event(raw)
        assert ev["offensive_foul"] is True

    def test_flag_on_defaults_false_for_missing_qualifier_fields(self):
        """Historical events lack qualifier keys — defaults must be False / empty."""
        mod = _import_featurizer(flag_on=True)
        raw = {"period": 1, "game_clock_sec": 300, "event_type": 6,
               "event_desc": "FOUL"}  # no qualifier keys
        ev = mod.normalize_event(raw)
        assert ev.get("offensive_foul") is False
        assert ev.get("technical") is False
        assert ev.get("flagrant") is False
        assert ev.get("ejection") is False
        assert ev.get("and_1") is False
        assert ev.get("in_penalty") is False
        assert ev.get("qualifiers") == []


# ── 5 & 6. featurize_game: team_fouls_period logic ───────────────────────────

def _minimal_pbp_events(home: str = "LAL", away: str = "OKC") -> List[Dict]:
    """Minimal historical PBP for featurize_game: 3 fouls + 1 made shot."""
    # Historical schema: event_type codes, no qualifier fields.
    return [
        # personal foul (home team, Q1)
        {"period": 1, "game_clock_sec": 300, "event_type": 6,
         "event_desc": "(P1.T1)", "team_abbrev": home,
         "player_name": "James", "score": "0-0", "score_margin": "0"},
        # another personal foul (home team, Q1)
        {"period": 1, "game_clock_sec": 360, "event_type": 6,
         "event_desc": "(P2.T2)", "team_abbrev": home,
         "player_name": "James", "score": "0-0", "score_margin": "0"},
        # made shot (away) for a score
        {"period": 1, "game_clock_sec": 400, "event_type": 1,
         "event_desc": "(2 PTS)", "team_abbrev": away,
         "player_name": "Gilgeous-Alexander",
         "score": "0-2", "score_margin": "-2"},
    ]


def _pbp_with_qualifiers(home: str = "LAL", away: str = "OKC") -> List[Dict]:
    """Live-event style PBP where foul events carry first-class qualifier fields."""
    # These simulate events that have gone through _event_from_play (flag ON)
    # and then normalize_event (flag ON).  The qualifier booleans are present.
    return [
        # personal foul — team foul should count
        {"period": 1, "game_clock_sec": 100, "event_type": 6,
         "event_desc": "(P1.T1)", "team_abbrev": home,
         "player_name": "James", "score": "0-0", "score_margin": "0",
         "offensive_foul": False, "technical": False, "flagrant": False,
         "sub_type": "personal", "qualifiers": []},
        # offensive foul — team foul should NOT count (doesn't accrue to bonus)
        {"period": 1, "game_clock_sec": 200, "event_type": 6,
         "event_desc": "(P1.T1)", "team_abbrev": home,
         "player_name": "Davis", "score": "0-0", "score_margin": "0",
         "offensive_foul": True, "technical": False, "flagrant": False,
         "sub_type": "offensive", "qualifiers": []},
        # technical foul — team foul should NOT count for the bonus
        {"period": 1, "game_clock_sec": 300, "event_type": 6,
         "event_desc": "Technical Foul (P1.T1)", "team_abbrev": home,
         "player_name": "James", "score": "0-0", "score_margin": "0",
         "offensive_foul": False, "technical": True, "flagrant": False,
         "sub_type": "technical", "qualifiers": []},
        # flagrant 1 — should count as team foul
        {"period": 1, "game_clock_sec": 400, "event_type": 6,
         "event_desc": "(P2.T2)", "team_abbrev": home,
         "player_name": "Hachimura", "score": "0-0", "score_margin": "0",
         "offensive_foul": False, "technical": False, "flagrant": True,
         "sub_type": "flagrant 1", "qualifiers": []},
    ]


class TestFeaturizeGameFoulAccumulation:
    def test_flag_off_uses_running_Tn(self):
        """FLAG OFF: uses (Pk.Tn) running team-foul count (existing behaviour)."""
        mod = _import_featurizer(flag_on=False)
        events = _minimal_pbp_events()
        result = mod.featurize_game(
            events, "0022400001", home_team="LAL", away_team="OKC",
            emit_players=False)
        game_rows = result["game"]
        # After the 2nd personal foul row (T2), home_team_fouls_period should be 2.
        last_row = game_rows[-1]
        assert last_row["home_team_fouls_period"] == 2

    def test_flag_off_historical_identical_to_no_qualifier_fields(self):
        """Historical events have no qualifier keys; flag ON path with
        empty defaults must produce the same foul-count as flag OFF."""
        mod_off = _import_featurizer(flag_on=False)
        mod_on = _import_featurizer(flag_on=True)
        events = _minimal_pbp_events()
        rows_off = mod_off.featurize_game(
            events, "0022400001", home_team="LAL", away_team="OKC",
            emit_players=False)["game"]
        rows_on = mod_on.featurize_game(
            events, "0022400001", home_team="LAL", away_team="OKC",
            emit_players=False)["game"]
        fouls_off = rows_off[-1]["home_team_fouls_period"]
        fouls_on = rows_on[-1]["home_team_fouls_period"]
        assert fouls_off == fouls_on, (
            f"Byte-identical-when-OFF violated: flag OFF={fouls_off}, "
            f"flag ON (no qualifier fields)={fouls_on}"
        )

    def test_flag_on_offensive_foul_not_counted(self):
        """FLAG ON: offensive foul does not increment team-foul count."""
        mod = _import_featurizer(flag_on=True)
        events = _pbp_with_qualifiers()
        result = mod.featurize_game(
            events, "0022400001", home_team="LAL", away_team="OKC",
            emit_players=False)
        game_rows = result["game"]
        last_row = game_rows[-1]
        # Events: personal (T1) + offensive (skip) + technical (skip) + flagrant (T2)
        # → team_fouls_period should be 2 (personal + flagrant)
        assert last_row["home_team_fouls_period"] == 2, (
            f"Expected 2 team fouls (personal + flagrant); "
            f"got {last_row['home_team_fouls_period']}"
        )

    def test_flag_on_technical_foul_not_counted(self):
        """FLAG ON: technical foul alone does not count toward bonus."""
        mod = _import_featurizer(flag_on=True)
        events = [
            {"period": 1, "game_clock_sec": 200, "event_type": 6,
             "event_desc": "Technical", "team_abbrev": "LAL",
             "player_name": "James", "score": "0-0", "score_margin": "0",
             "technical": True, "offensive_foul": False, "flagrant": False,
             "sub_type": "technical", "qualifiers": []},
        ]
        result = mod.featurize_game(
            events, "0022400001", home_team="LAL", away_team="OKC",
            emit_players=False)
        last_row = result["game"][-1]
        assert last_row["home_team_fouls_period"] == 0, (
            f"Technical foul must not count toward bonus; "
            f"got {last_row['home_team_fouls_period']}"
        )

    def test_flag_on_personal_foul_counted(self):
        """FLAG ON: plain personal foul still increments team-foul count."""
        mod = _import_featurizer(flag_on=True)
        events = [
            {"period": 1, "game_clock_sec": 200, "event_type": 6,
             "event_desc": "(P1.T1)", "team_abbrev": "LAL",
             "player_name": "James", "score": "0-0", "score_margin": "0",
             "technical": False, "offensive_foul": False, "flagrant": False,
             "sub_type": "personal", "qualifiers": []},
        ]
        result = mod.featurize_game(
            events, "0022400001", home_team="LAL", away_team="OKC",
            emit_players=False)
        last_row = result["game"][-1]
        assert last_row["home_team_fouls_period"] == 1

    def test_game_rows_non_empty(self):
        """featurize_game returns non-empty rows for any of the test inputs."""
        mod = _import_featurizer(flag_on=True)
        events = _pbp_with_qualifiers()
        result = mod.featurize_game(
            events, "0022400001", home_team="LAL", away_team="OKC",
            emit_players=False)
        assert len(result["game"]) > 0
