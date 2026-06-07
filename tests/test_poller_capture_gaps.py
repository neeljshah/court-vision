"""tests/test_poller_capture_gaps.py — CV_POLLER_CAPTURE_GAPS umbrella flag.

Tests the single-flag rotation-model data prerequisite gate added to
scripts/live_game_poll.py.

Coverage:
  (a) FLAG OFF — byte-identical: emitted player record has EXACTLY the same
      keys as the baseline (no new keys added, regardless of payload).
  (b) FLAG ON — new keys present and correctly parsed on every player row:
      fga, fg3a, fgm, fta, ftm, oreb, dreb, oncourt, plus_minus,
      and is_starter correctly parsed (string "0" → False fix active).
  (c) MIN parser edge cases — "MM:SS", "PT14M30.00S", plain float, None,
      "", "0:00" all produce the right float.
  (d) Missing-field safety — payload lacking oncourt / plus_minus still
      works (no crash; fields default to 0 / False).
  (e) Umbrella independence — individual sub-flags (CV_SNAP_FF, etc.) can
      still be set independently of the umbrella.
  (f) Baseline keys unaffected when ON — existing stats not clobbered.

All tests are OFFLINE — no network calls, no filesystem I/O.
"""
from __future__ import annotations

import importlib
import os
import sys
from typing import Any, Dict, List, Optional

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)


# ─────────────────────────────────────────────────────────────────────────────
# Module-reload helper
# ─────────────────────────────────────────────────────────────────────────────

def _import_lgp(*, capture_gaps: bool,
                snap_ff: Optional[bool] = None,
                snap_oncourt: Optional[bool] = None):
    """Import (reload) live_game_poll with controlled flag state.

    capture_gaps controls CV_POLLER_CAPTURE_GAPS.
    snap_ff / snap_oncourt can override individual sub-flags for the
    sub-flag independence test.

    After each call the module is reloaded under the requested env state.
    The finally block restores the environment but does NOT re-reload the
    module — the returned lgp object retains the requested state for the
    duration of the test.  The module is left in that state; callers that
    need a known-clean state (e.g. TestByteIdenticalOffProof) must call
    _import_lgp(capture_gaps=False) as a last step.
    """
    saved = {
        "CV_POLLER_CAPTURE_GAPS": os.environ.get("CV_POLLER_CAPTURE_GAPS"),
        "CV_SNAP_FF":             os.environ.get("CV_SNAP_FF"),
        "CV_SNAP_ONCOURT":        os.environ.get("CV_SNAP_ONCOURT"),
        "CV_SNAP_REBSPLIT":       os.environ.get("CV_SNAP_REBSPLIT"),
        "CV_SNAP_STARTER_FIX":    os.environ.get("CV_SNAP_STARTER_FIX"),
        "CV_SNAP_PLUS_MINUS":     os.environ.get("CV_SNAP_PLUS_MINUS"),
        "CV_INGAME_LIVE_USAGE":   os.environ.get("CV_INGAME_LIVE_USAGE"),
        "CV_MARGIN_SERIES":       os.environ.get("CV_MARGIN_SERIES"),
    }
    try:
        os.environ["CV_POLLER_CAPTURE_GAPS"] = "1" if capture_gaps else "0"
        # Silence adjacent flags so only the umbrella (or explicit overrides) matter.
        for k in ("CV_SNAP_FF", "CV_SNAP_ONCOURT", "CV_SNAP_REBSPLIT",
                  "CV_SNAP_STARTER_FIX", "CV_SNAP_PLUS_MINUS",
                  "CV_INGAME_LIVE_USAGE", "CV_MARGIN_SERIES"):
            os.environ[k] = "0"
        if snap_ff is not None:
            os.environ["CV_SNAP_FF"] = "1" if snap_ff else "0"
        if snap_oncourt is not None:
            os.environ["CV_SNAP_ONCOURT"] = "1" if snap_oncourt else "0"

        import scripts.live_game_poll as lgp
        importlib.reload(lgp)
        return lgp
    finally:
        # Restore original env variables so later imports see the right defaults.
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _reset_lgp_to_baseline():
    """Reload live_game_poll with ALL flags OFF, restoring the module-level
    bool variables to the default (False) state.  Call at end of any test
    that reloads with flags ON to prevent cross-test contamination.
    """
    for k in ("CV_POLLER_CAPTURE_GAPS", "CV_SNAP_FF", "CV_SNAP_ONCOURT",
              "CV_SNAP_REBSPLIT", "CV_SNAP_STARTER_FIX", "CV_SNAP_PLUS_MINUS",
              "CV_INGAME_LIVE_USAGE", "CV_MARGIN_SERIES"):
        os.environ[k] = "0"
    import scripts.live_game_poll as lgp
    importlib.reload(lgp)
    # Clean up: remove the env vars we just set so they don't affect test_live_game_poll.py.
    for k in ("CV_POLLER_CAPTURE_GAPS", "CV_SNAP_FF", "CV_SNAP_ONCOURT",
              "CV_SNAP_REBSPLIT", "CV_SNAP_STARTER_FIX", "CV_SNAP_PLUS_MINUS",
              "CV_INGAME_LIVE_USAGE", "CV_MARGIN_SERIES"):
        os.environ.pop(k, None)


# ─────────────────────────────────────────────────────────────────────────────
# Autouse teardown: restore module state after every test in this file
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _restore_lgp_after_test():
    """Autouse fixture: after every test in this file, reload live_game_poll
    with all flags OFF so that subsequent tests (including those in other files
    collected in the same pytest session) see the clean baseline module state.
    """
    yield
    _reset_lgp_to_baseline()


# ─────────────────────────────────────────────────────────────────────────────
# Fixture builders
# ─────────────────────────────────────────────────────────────────────────────

_BASELINE_PLAYER_KEYS = frozenset({
    "player_id", "name", "team", "min",
    "pts", "reb", "ast", "fg3m",
    "stl", "blk", "tov", "pf", "is_starter",
})

_GAP_EXTRA_KEYS = frozenset({
    "fga", "fgm", "fg3a", "fta", "ftm",  # CV_SNAP_FF
    "oreb", "dreb",                        # CV_SNAP_REBSPLIT
    "oncourt",                             # CV_SNAP_ONCOURT
    "plus_minus",                          # CV_SNAP_PLUS_MINUS
})


def _player_full(name: str, *, pid: int = 1001, team: str = "LAL",
                 min_: str = "14:30",
                 pts: int = 12, reb: int = 4, ast: int = 3, fg3m: int = 2,
                 stl: int = 1, blk: int = 0, tov: int = 1, pf: int = 2,
                 starter: Any = "1",
                 fga: int = 10, fgm: int = 5, fg3a: int = 4,
                 fta: int = 3, ftm: int = 2,
                 oreb: int = 1, dreb: int = 3,
                 oncourt: bool = True,
                 plus_minus: int = 5) -> Dict[str, Any]:
    """Full CDN player entry including all gap fields."""
    return {
        "personId":  pid,
        "name":      name,
        "starter":   starter,     # CDN sends string "1" or "0"
        "oncourt":   oncourt,
        "statistics": {
            "minutes":                  f"PT{min_.split(':')[0]}M{min_.split(':')[1]}.00S",
            "points":                   pts,
            "reboundsTotal":            reb,
            "reboundsOffensive":        oreb,
            "reboundsDefensive":        dreb,
            "assists":                  ast,
            "threePointersMade":        fg3m,
            "steals":                   stl,
            "blocks":                   blk,
            "turnovers":                tov,
            "foulsPersonal":            pf,
            "fieldGoalsAttempted":      fga,
            "fieldGoalsMade":           fgm,
            "threePointersAttempted":   fg3a,
            "freeThrowsAttempted":      fta,
            "freeThrowsMade":           ftm,
            "plusMinusPoints":          plus_minus,
        },
    }


def _player_minimal(name: str, *, pid: int = 1001, team: str = "LAL",
                    min_: str = "14:30", pts: int = 12,
                    starter: Any = "1") -> Dict[str, Any]:
    """Minimal CDN player entry — no gap fields at all (missing-field test)."""
    return {
        "personId": pid,
        "name":     name,
        "starter":  starter,
        "statistics": {
            "minutes":   f"PT{min_.split(':')[0]}M{min_.split(':')[1]}.00S",
            "points":    pts,
            "reboundsTotal": 0,
            "assists":   0,
            "threePointersMade": 0,
            "steals":    0,
            "blocks":    0,
            "turnovers": 0,
            "foulsPersonal": 0,
        },
    }


def _make_payload(players_home: List[Dict], players_away: List[Dict],
                  *, game_id: str = "0042500401", status: int = 2,
                  period: int = 2, clock: str = "PT05M42.00S",
                  home_score: int = 56, away_score: int = 48) -> Dict[str, Any]:
    return {
        "game": {
            "gameId":     game_id,
            "gameStatus": status,
            "period":     period,
            "gameClock":  clock,
            "homeTeam": {
                "teamTricode": "LAL",
                "score":       home_score,
                "players":     players_home,
            },
            "awayTeam": {
                "teamTricode": "DEN",
                "score":       away_score,
                "players":     players_away,
            },
        }
    }


def _full_payload() -> Dict[str, Any]:
    """Payload with all gap fields present."""
    return _make_payload(
        players_home=[
            _player_full("LeBron James",  pid=2544,   min_="22:10",
                         pts=22, reb=8,  ast=9,  fga=16, fgm=9,
                         oreb=2, dreb=6, oncourt=True, plus_minus=8,
                         starter="1"),
            _player_full("Anthony Davis", pid=203076, min_="20:00",
                         pts=18, reb=10, ast=2,  fga=12, fgm=7,
                         oreb=3, dreb=7, oncourt=True, plus_minus=6,
                         starter="1"),
        ],
        players_away=[
            _player_full("Nikola Jokic",   pid=203999, min_="21:30",
                         pts=20, reb=11, ast=8,  fga=14, fgm=8,
                         oreb=4, dreb=7, oncourt=True, plus_minus=-4,
                         starter="1"),
            _player_full("Reggie Jackson", pid=202704, min_="6:15",
                         pts=4,  reb=1,  ast=2,  fga=5,  fgm=2,
                         oreb=0, dreb=1, oncourt=False, plus_minus=-2,
                         starter="0"),
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# (a) FLAG OFF — byte-identical output
# ─────────────────────────────────────────────────────────────────────────────

class TestFlagOff:
    """When CV_POLLER_CAPTURE_GAPS=OFF, output is byte-identical to baseline."""

    def test_player_keys_exactly_baseline_with_full_payload(self):
        """Full CDN payload present but flag OFF: only baseline keys appear."""
        lgp = _import_lgp(capture_gaps=False)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        for p in snap["players"]:
            assert set(p.keys()) == _BASELINE_PLAYER_KEYS, (
                f"Player {p['name']!r} has unexpected keys (flag OFF): "
                f"{set(p.keys()) - _BASELINE_PLAYER_KEYS}"
            )

    def test_no_gap_keys_present(self):
        """None of the gap keys appear when flag is OFF."""
        lgp = _import_lgp(capture_gaps=False)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        for p in snap["players"]:
            for k in _GAP_EXTRA_KEYS:
                assert k not in p, (
                    f"Key {k!r} must NOT appear on {p['name']!r} when flag OFF"
                )

    def test_no_schema_version_key(self):
        """schema_version must not appear in the snapshot when flag OFF."""
        lgp = _import_lgp(capture_gaps=False)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        assert "schema_version" not in snap

    def test_baseline_values_correct(self):
        """Baseline stats (pts, reb, ast, min) parse correctly regardless of flag."""
        lgp = _import_lgp(capture_gaps=False)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        by_name = {p["name"]: p for p in snap["players"]}
        jokic = by_name["Nikola Jokic"]
        assert jokic["pts"] == 20
        assert jokic["reb"] == 11
        assert jokic["ast"] == 8
        assert jokic["min"] == pytest.approx(21.5)   # 21:30


# ─────────────────────────────────────────────────────────────────────────────
# (b) FLAG ON — new keys present and correctly parsed
# ─────────────────────────────────────────────────────────────────────────────

class TestFlagOn:
    """When CV_POLLER_CAPTURE_GAPS=ON, all gap fields are present and correct."""

    def test_all_gap_keys_present_on_every_player(self):
        lgp = _import_lgp(capture_gaps=True)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        for p in snap["players"]:
            for k in _GAP_EXTRA_KEYS:
                assert k in p, (
                    f"Key {k!r} missing on {p['name']!r} when flag ON"
                )

    def test_baseline_keys_still_present(self):
        """Baseline keys are all still present when flag is ON."""
        lgp = _import_lgp(capture_gaps=True)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        for p in snap["players"]:
            missing = _BASELINE_PLAYER_KEYS - set(p.keys())
            assert not missing, (
                f"Player {p['name']!r} missing baseline keys: {missing}"
            )

    def test_fga_fg3a_values_correct(self):
        lgp = _import_lgp(capture_gaps=True)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        by_name = {p["name"]: p for p in snap["players"]}
        assert by_name["LeBron James"]["fga"] == 16
        assert by_name["Nikola Jokic"]["fg3a"] == 4   # from _player_full default fg3a=4

    def test_oreb_dreb_values_correct(self):
        lgp = _import_lgp(capture_gaps=True)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        by_name = {p["name"]: p for p in snap["players"]}
        # LeBron: oreb=2, dreb=6; oreb+dreb == reb
        assert by_name["LeBron James"]["oreb"] == 2
        assert by_name["LeBron James"]["dreb"] == 6
        assert by_name["LeBron James"]["oreb"] + by_name["LeBron James"]["dreb"] == by_name["LeBron James"]["reb"]

    def test_oncourt_values_correct(self):
        lgp = _import_lgp(capture_gaps=True)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        by_name = {p["name"]: p for p in snap["players"]}
        assert by_name["LeBron James"]["oncourt"] is True
        assert by_name["Reggie Jackson"]["oncourt"] is False

    def test_plus_minus_values_correct(self):
        lgp = _import_lgp(capture_gaps=True)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        by_name = {p["name"]: p for p in snap["players"]}
        assert by_name["LeBron James"]["plus_minus"] == 8
        assert by_name["Nikola Jokic"]["plus_minus"] == -4

    def test_is_starter_string_fix_active(self):
        """With flag ON, is_starter parses string '0' correctly as False."""
        lgp = _import_lgp(capture_gaps=True)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        by_name = {p["name"]: p for p in snap["players"]}
        # starter="1" → True
        assert by_name["LeBron James"]["is_starter"] is True
        # starter="0" → False (the string-parse fix)
        assert by_name["Reggie Jackson"]["is_starter"] is False

    def test_oncourt_is_bool_type(self):
        lgp = _import_lgp(capture_gaps=True)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        for p in snap["players"]:
            assert isinstance(p["oncourt"], bool), (
                f"oncourt on {p['name']!r} should be bool, got {type(p['oncourt'])}"
            )

    def test_plus_minus_is_int_type(self):
        lgp = _import_lgp(capture_gaps=True)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        for p in snap["players"]:
            assert isinstance(p["plus_minus"], int), (
                f"plus_minus on {p['name']!r} should be int, got {type(p['plus_minus'])}"
            )

    def test_oreb_plus_dreb_equals_reb_all_players(self):
        """oreb + dreb == reb invariant holds for all players."""
        lgp = _import_lgp(capture_gaps=True)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        for p in snap["players"]:
            assert p["oreb"] + p["dreb"] == p["reb"], (
                f"oreb+dreb != reb for {p['name']!r}: "
                f"{p['oreb']}+{p['dreb']} != {p['reb']}"
            )

    def test_fga_ge_fgm_all_players(self):
        """fga >= fgm (attempted >= made) for all players."""
        lgp = _import_lgp(capture_gaps=True)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        for p in snap["players"]:
            assert p["fga"] >= p["fgm"], (
                f"fga < fgm for {p['name']!r}: {p['fga']} < {p['fgm']}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# (c) MIN parser edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestMinParser:
    """_parse_minutes handles all edge-case formats correctly."""

    def _get_parse_fn(self):
        """Return the _parse_minutes helper from live_game_poll."""
        lgp = _import_lgp(capture_gaps=False)
        return lgp._parse_minutes

    def test_pt_format_full(self):
        """'PT14M30.00S' → 14.5 minutes."""
        fn = self._get_parse_fn()
        assert fn("PT14M30.00S") == pytest.approx(14.5)

    def test_pt_format_zero_seconds(self):
        """'PT10M00.00S' → 10.0 minutes."""
        fn = self._get_parse_fn()
        assert fn("PT10M00.00S") == pytest.approx(10.0)

    def test_mmss_colon_format(self):
        """'14:30' → 14.5 minutes."""
        fn = self._get_parse_fn()
        assert fn("14:30") == pytest.approx(14.5)

    def test_mmss_zero(self):
        """'0:00' → 0.0 minutes."""
        fn = self._get_parse_fn()
        assert fn("0:00") == pytest.approx(0.0)

    def test_plain_float_string(self):
        """'14.5' → 14.5 minutes."""
        fn = self._get_parse_fn()
        assert fn("14.5") == pytest.approx(14.5)

    def test_none_returns_zero(self):
        """None → 0.0 (safe default for absent CDN field)."""
        fn = self._get_parse_fn()
        assert fn(None) == pytest.approx(0.0)

    def test_empty_string_returns_zero(self):
        """'' → 0.0."""
        fn = self._get_parse_fn()
        assert fn("") == pytest.approx(0.0)

    def test_whitespace_string_returns_zero(self):
        """'   ' → 0.0."""
        fn = self._get_parse_fn()
        assert fn("   ") == pytest.approx(0.0)

    def test_integer_zero(self):
        """0 (int) → 0.0."""
        fn = self._get_parse_fn()
        assert fn(0) == pytest.approx(0.0)

    def test_float_value(self):
        """22.3 (float already) → 22.3."""
        fn = self._get_parse_fn()
        assert fn(22.3) == pytest.approx(22.3, rel=0.01)

    def test_pt_format_no_seconds_part(self):
        """'PT12M' (no seconds) → 12.0."""
        fn = self._get_parse_fn()
        assert fn("PT12M") == pytest.approx(12.0)

    def test_parse_returns_float(self):
        """Return type is always float."""
        fn = self._get_parse_fn()
        for v in ("PT5M30.00S", "5:30", "5.5", None, ""):
            result = fn(v)
            assert isinstance(result, float), (
                f"_parse_minutes({v!r}) returned {type(result)}, expected float"
            )


# ─────────────────────────────────────────────────────────────────────────────
# (d) Missing-field safety
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingFieldSafety:
    """Payload lacking gap CDN fields does not crash; all fields default safely."""

    def test_no_crash_on_minimal_payload(self):
        """Minimal payload (no gap CDN fields) with flag ON must not raise."""
        lgp = _import_lgp(capture_gaps=True)
        payload = _make_payload(
            players_home=[_player_minimal("LeBron James", pid=2544, starter="1")],
            players_away=[_player_minimal("Jokic",        pid=203999, starter="1")],
        )
        snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-05T00:00:00+00:00")
        assert len(snap["players"]) == 2

    def test_absent_oncourt_defaults_false(self):
        """When CDN `oncourt` key is absent, defaults to False (not crash)."""
        lgp = _import_lgp(capture_gaps=True)
        payload = _make_payload(
            players_home=[_player_minimal("LeBron", pid=2544)],
            players_away=[],
        )
        snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-05T00:00:00+00:00")
        assert snap["players"][0]["oncourt"] is False

    def test_absent_plus_minus_defaults_zero(self):
        """When CDN `plusMinusPoints` is absent, defaults to 0 (not crash)."""
        lgp = _import_lgp(capture_gaps=True)
        payload = _make_payload(
            players_home=[_player_minimal("LeBron", pid=2544)],
            players_away=[],
        )
        snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-05T00:00:00+00:00")
        assert snap["players"][0]["plus_minus"] == 0

    def test_absent_fga_defaults_zero(self):
        """When CDN four-factor fields absent, fga/fg3a default to 0."""
        lgp = _import_lgp(capture_gaps=True)
        payload = _make_payload(
            players_home=[_player_minimal("LeBron", pid=2544)],
            players_away=[],
        )
        snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-05T00:00:00+00:00")
        for k in ("fga", "fgm", "fg3a", "fta", "ftm"):
            assert snap["players"][0][k] == 0

    def test_absent_oreb_defaults_zero(self):
        """When CDN reboundsOffensive/reboundsDefensive absent, oreb/dreb default 0."""
        lgp = _import_lgp(capture_gaps=True)
        payload = _make_payload(
            players_home=[_player_minimal("LeBron", pid=2544)],
            players_away=[],
        )
        snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-05T00:00:00+00:00")
        assert snap["players"][0]["oreb"] == 0
        assert snap["players"][0]["dreb"] == 0

    def test_all_gap_keys_present_even_when_cdn_absent(self):
        """All gap keys are always present when flag ON, even if CDN omits them."""
        lgp = _import_lgp(capture_gaps=True)
        payload = _make_payload(
            players_home=[_player_minimal("LeBron", pid=2544)],
            players_away=[],
        )
        snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-05T00:00:00+00:00")
        for k in _GAP_EXTRA_KEYS:
            assert k in snap["players"][0], (
                f"Key {k!r} missing even with minimal payload (flag ON)"
            )

    def test_null_plus_minus_in_statistics_handled(self):
        """plusMinusPoints = null in CDN statistics → plus_minus = 0 (no crash)."""
        lgp = _import_lgp(capture_gaps=True)
        p = _player_minimal("TestPlayer", pid=9999)
        p["statistics"]["plusMinusPoints"] = None  # explicit null
        payload = _make_payload(players_home=[p], players_away=[])
        snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-05T00:00:00+00:00")
        assert snap["players"][0]["plus_minus"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# (e) Sub-flag independence
# ─────────────────────────────────────────────────────────────────────────────

class TestSubFlagIndependence:
    """Individual sub-flags still work without the umbrella."""

    def test_cv_snap_ff_on_without_umbrella(self):
        """CV_SNAP_FF=ON (umbrella OFF) → fga/fgm keys present."""
        lgp = _import_lgp(capture_gaps=False, snap_ff=True)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        for p in snap["players"]:
            assert "fga" in p, f"fga missing with CV_SNAP_FF=ON on {p['name']!r}"
        # oncourt should NOT be present (umbrella OFF, CV_SNAP_ONCOURT OFF)
        for p in snap["players"]:
            assert "oncourt" not in p

    def test_cv_snap_oncourt_on_without_umbrella(self):
        """CV_SNAP_ONCOURT=ON (umbrella OFF) → oncourt present, fga absent."""
        lgp = _import_lgp(capture_gaps=False, snap_oncourt=True)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        for p in snap["players"]:
            assert "oncourt" in p
            assert "fga" not in p

    def test_umbrella_does_not_disable_individual_flags(self):
        """Umbrella ON + individual flags ON: combined keys all present."""
        # Both umbrella and sub-flag active — should not conflict.
        lgp = _import_lgp(capture_gaps=True, snap_ff=True)
        snap = lgp.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        for p in snap["players"]:
            for k in ("fga", "oncourt", "oreb", "plus_minus"):
                assert k in p


# ─────────────────────────────────────────────────────────────────────────────
# (f) Byte-identical OFF proof — structural assertion
# ─────────────────────────────────────────────────────────────────────────────

class TestByteIdenticalOffProof:
    """Prove byte-identical-OFF by directly comparing key sets."""

    def test_flag_off_vs_on_key_sets_differ_by_exactly_gap_keys(self):
        """Keys(ON) - Keys(OFF) == _GAP_EXTRA_KEYS union schema_version (exactly).

        Each snapshot is parsed within its own reload context so that the
        module-level flag variables are not clobbered by a second reload.
        """
        # Capture OFF keys first, within the OFF context.
        lgp_off = _import_lgp(capture_gaps=False)
        snap_off = lgp_off.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        off_player_keys = [set(p.keys()) for p in snap_off["players"]]
        off_top_keys = set(snap_off.keys())

        # Capture ON keys next, within the ON context.
        lgp_on = _import_lgp(capture_gaps=True)
        snap_on = lgp_on.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        on_player_keys = [set(p.keys()) for p in snap_on["players"]]
        on_top_keys = set(snap_on.keys())

        # Player-level: ON adds exactly the gap keys, removes nothing.
        for i, (pk_off, pk_on) in enumerate(zip(off_player_keys, on_player_keys)):
            name = snap_on["players"][i]["name"]
            added   = pk_on - pk_off
            removed = pk_off - pk_on
            assert removed == set(), (
                f"FLAG ON removed keys from {name!r}: {removed}"
            )
            assert added == _GAP_EXTRA_KEYS, (
                f"FLAG ON added unexpected keys on {name!r}: "
                f"expected {_GAP_EXTRA_KEYS}, got {added}"
            )

        # Top-level snapshot: ON adds schema_version (from _SNAP_FF being True)
        top_added = on_top_keys - off_top_keys
        assert top_added <= {"schema_version"}, (
            f"FLAG ON added unexpected top-level keys: {top_added}"
        )

    def test_flag_off_baseline_values_identical_to_on_baseline_values(self):
        """Existing stat values (pts, reb, ast, min) are the same with OFF vs ON."""
        lgp_off = _import_lgp(capture_gaps=False)
        lgp_on  = _import_lgp(capture_gaps=True)

        snap_off = lgp_off.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")
        snap_on  = lgp_on.parse_boxscore_payload(
            _full_payload(), captured_at="2026-06-05T00:00:00+00:00")

        by_name_off = {p["name"]: p for p in snap_off["players"]}
        by_name_on  = {p["name"]: p for p in snap_on["players"]}

        for name in by_name_off:
            for k in _BASELINE_PLAYER_KEYS:
                assert by_name_off[name][k] == by_name_on[name][k], (
                    f"Baseline key {k!r} differs for {name!r} "
                    f"OFF={by_name_off[name][k]!r} ON={by_name_on[name][k]!r}"
                )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
