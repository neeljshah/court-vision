"""Per-file test for ingame_pitcher_mlb -- deep pitcher/batter/pitch-count/TTO (MLB).

OFFLINE + pure: linescore + boxscore are literal dicts in the real statsapi shape.  Covers
the TTO boundary (the 'third time through the order' zone), the boxscore pitch-count read,
names-without-boxscore, and the honest empty cases.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/ingame/test_ingame_pitcher_mlb.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import ingame_pitcher_mlb as P


def test_tto_boundaries():
    assert P.tto_for(0) == 1       # first batter -> first time through
    assert P.tto_for(8) == 1       # 9th batter still first time
    assert P.tto_for(9) == 2       # 10th batter -> second time
    assert P.tto_for(18) == 3      # 19th batter -> third time through (the penalty zone)
    assert P.tto_for(None) is None
    assert P.tto_for(-1) is None
    assert P.tto_for("x") is None


def _linescore(batter="Gunnar Henderson", pitcher="Foster Griffin", pid=656492):
    return {
        "offense": {"batter": {"fullName": batter, "id": 683002}},
        "defense": {"pitcher": {"fullName": pitcher, "id": pid}},
    }


def _boxscore(pid=656492, pitches=87, bf=19):
    return {"teams": {"home": {"players": {
        "ID%s" % pid: {"stats": {"pitching": {
            "numberOfPitches": pitches, "battersFaced": bf}}}}}, "away": {"players": {}}}}


def test_full_pitcher_batter_fields():
    d = P.pitcher_batter_fields(_linescore(), _boxscore())
    assert d["pitcher"] == "Foster Griffin"
    assert d["batter"] == "Gunnar Henderson"
    assert d["pitch_count"] == 87
    assert d["batters_faced"] == 19
    assert d["tto"] == 3           # 19 faced -> the 20th batter is 3rd time through


def test_names_without_boxscore():
    # No boxscore -> names flow, but NO fabricated pitch_count / tto.
    d = P.pitcher_batter_fields(_linescore(), None)
    assert d["pitcher"] == "Foster Griffin" and d["batter"] == "Gunnar Henderson"
    assert "pitch_count" not in d and "tto" not in d


def test_pitcher_on_away_side_is_found():
    box = {"teams": {"home": {"players": {}}, "away": {"players": {
        "ID111": {"stats": {"pitching": {"numberOfPitches": 42, "battersFaced": 9}}}}}}}
    ls = _linescore(pitcher="Some Reliever", pid=111)
    d = P.pitcher_batter_fields(ls, box)
    assert d["pitch_count"] == 42 and d["tto"] == 2


def test_pitchesThrown_fallback():
    box = {"teams": {"home": {"players": {
        "ID656492": {"stats": {"pitching": {"pitchesThrown": 55, "battersFaced": 12}}}}},
        "away": {"players": {}}}}
    d = P.pitcher_batter_fields(_linescore(), box)
    assert d["pitch_count"] == 55 and d["tto"] == 2


def test_empty_linescore_returns_empty():
    assert P.pitcher_batter_fields({}, _boxscore()) == {}
    assert P.pitcher_batter_fields(None, None) == {}


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    sys.exit(0)
