"""S314 step 1: fail-closed rails on the ESPN core-API PBP backfill.

Run only this file:
    python -m pytest tests/platformkit/test_espn_pbp_backfill.py -q

Covers the two of the five S314 plants that the shipped code can be held to --
WRONG GAME IDS (a non-unique or absent event match must raise, never guess) and
REVERSED CLOCK DIRECTION (ESPN reports seconds REMAINING; the local schema
stores seconds ELAPSED, so a straight copy would invert every anchor).  The
REPEATED CLOCKS plant is covered as source-order preservation.  The CUT and
REPLAY plants belong to the interval-alignment module, which S314 did not reach
(before-condition BLOCKED); see the memo's NOT VERIFIED list.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.platformkit import espn_pbp_backfill as mod  # noqa: E402


def _play(seq, period, remaining, text="x", type_text="Jump Shot",
          scoring=False, home=0, away=0):
    return {
        "sequenceNumber": str(seq),
        "type": {"text": type_text},
        "text": text,
        "scoringPlay": scoring,
        "homeScore": home,
        "awayScore": away,
        "period": {"number": period},
        "clock": {"value": float(remaining)},
        "team": {"$ref": "http://x/teams/6?lang=en"},
        "participants": [{"athlete": {"$ref": "http://x/athletes/99?lang=en"}}],
    }


# ---- PLANT: reversed clock direction -------------------------------------

def test_clock_is_elapsed_not_remaining():
    """ESPN gives REMAINING; the local schema stores ELAPSED. Tip-off is 0."""
    assert mod.elapsed_sec(1, 720.0) == 0        # tip-off
    assert mod.elapsed_sec(1, 699.0) == 21       # 11:39 remaining
    assert mod.elapsed_sec(4, 0.0) == 720        # end of Q4
    assert mod.elapsed_sec(5, 300.0) == 0        # OT is a 5-minute period
    assert mod.elapsed_sec(5, 0.0) == 300


def test_reversed_clock_plant_fails_closed():
    """Feeding ELAPSED where REMAINING is expected must not silently pass.

    A reversed source makes the period run backwards; the emitted rows are then
    non-monotone against source order, which is the detectable signature.
    """
    good = [_play(i, 1, 720.0 - 60 * i) for i in range(1, 6)]
    reversed_src = [_play(i, 1, 60 * i) for i in range(1, 6)]
    g = [r["game_clock_sec"] for r in mod.to_period_rows(good, {}, {})[1]]
    b = [r["game_clock_sec"] for r in mod.to_period_rows(reversed_src, {}, {})[1]]
    assert g == sorted(g), g
    assert b != sorted(b), "reversed clock went undetected"


# ---- PLANT: repeated clocks ----------------------------------------------

def test_repeated_clocks_keep_source_event_order():
    """Identical clocks are broken by sequenceNumber, never re-sorted by clock."""
    plays = [_play(3, 1, 500.0, text="third"),
             _play(1, 1, 500.0, text="first"),
             _play(2, 1, 500.0, text="second")]
    rows = mod.to_period_rows(plays, {}, {})[1]
    assert [r["event_desc"] for r in rows] == ["first", "second", "third"]
    assert {r["game_clock_sec"] for r in rows} == {220}


# ---- PLANT: wrong game ids -----------------------------------------------

def test_wrong_game_id_no_match_fails_closed(monkeypatch):
    """No event on the date matches -> raise, never fall back to a neighbour."""
    monkeypatch.setattr(mod, "_get", _fake_listing({"1": "TOR @ IND",
                                                    "2": "CLE @ PHI"}))
    with pytest.raises(RuntimeError, match="not unique"):
        mod.resolve_event("20260114", "DAL", "DEN")


def test_wrong_game_id_ambiguous_match_fails_closed(monkeypatch):
    """Two events with the same matchup -> raise, never take the first."""
    monkeypatch.setattr(mod, "_get", _fake_listing({"1": "DEN @ DAL",
                                                    "2": "DEN @ DAL"}))
    with pytest.raises(RuntimeError, match="not unique"):
        mod.resolve_event("20260114", "DAL", "DEN")


def test_correct_game_id_resolves_uniquely(monkeypatch):
    monkeypatch.setattr(mod, "_get", _fake_listing({"1": "TOR @ IND",
                                                    "2": "DEN @ DAL"}))
    event_id, seen = mod.resolve_event("20260114", "DAL", "DEN")
    assert event_id == "2"
    assert len(seen) == 2


def test_tricode_alias_resolves_espn_spelling(monkeypatch):
    """GSW/GS, NOP/NO, NYK/NY, SAS/SA, UTA/UTAH, WAS/WSH must all join."""
    monkeypatch.setattr(mod, "_get", _fake_listing({"9": "GS @ DAL"}))
    assert mod.resolve_event("20260122", "DAL", "GSW")[0] == "9"
    for nba, espn in (("NOP", "NO"), ("NYK", "NY"), ("SAS", "SA"),
                      ("UTA", "UTAH"), ("WAS", "WSH")):
        assert mod._tok(nba) == espn


def _fake_listing(id_to_shortname):
    """Stand in for _get over the events listing + per-event refs."""
    def fake(url, *a, **k):
        if "/events?dates=" in url:
            return {"items": [{"$ref": "ref://%s" % i} for i in id_to_shortname]}
        eid = url.split("://", 1)[1]
        return {"id": eid, "shortName": id_to_shortname[eid]}
    return fake


# ---- additive-only rail ---------------------------------------------------

def test_write_refuses_to_overwrite(tmp_path):
    """The corpus store is append-only: an existing period file is never lost."""
    rows = {1: [{"period": 1, "game_clock_sec": 0}]}
    mod.write_periods("0022500575", rows, str(tmp_path))
    written = tmp_path / "pbp_0022500575_p1.json"
    assert json.loads(written.read_text())[0]["period"] == 1
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        mod.write_periods("0022500575", rows, str(tmp_path))


# ---- schema parity with the existing writer -------------------------------

def test_row_schema_matches_local_pbp_writer():
    """Byte-for-byte the key set scripts/fetch_pbp_backfill_fast.py emits."""
    expected = {"period", "game_clock_sec", "event_type", "event_desc",
                "player_name", "team_abbrev", "score", "score_margin"}
    rows = mod.to_period_rows([_play(1, 1, 700.0, home=10, away=7)],
                              {"99": "Gordon"}, {"6": "DEN"})[1]
    assert set(rows[0]) == expected
    assert rows[0]["score"] == "10-7"        # home-away, as the local writer
    assert rows[0]["score_margin"] == "3"
    assert rows[0]["player_name"] == "Gordon"
    assert rows[0]["team_abbrev"] == "DEN"


def test_event_type_mapping():
    assert mod.event_type_of("Defensive Rebound", "x rebound", False) == 4
    assert mod.event_type_of("Free Throw", "makes free throw", True) == 3
    assert mod.event_type_of("Personal Foul", "foul on x", False) == 6
    assert mod.event_type_of("Jump Shot", "makes jump shot", True) == 1
    assert mod.event_type_of("Jump Shot", "misses jump shot", False) == 2
    assert mod.event_type_of("End Period", "end period", False) == 13
    assert mod.event_type_of("Unknown", "something else", False) == 0
