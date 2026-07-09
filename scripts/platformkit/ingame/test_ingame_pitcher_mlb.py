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
            "numberOfPitches": pitches, "battersFaced": bf}}}}, "pitchers": [pid]},
        "away": {"players": {}, "pitchers": []}}}


def test_full_pitcher_batter_fields():
    d = P.pitcher_batter_fields(_linescore(), _boxscore())
    assert d["pitcher"] == "Foster Griffin"
    assert d["batter"] == "Gunnar Henderson"
    assert d["pitch_count"] == 87
    assert d["batters_faced"] == 19
    assert d["tto"] == 3           # 19 faced -> the 20th batter is 3rd time through
    # IDENTITY: ids come from the SAME person dicts as the names above (no extra fetch).
    assert d["pitcher_id"] == 656492
    assert d["batter_id"] == 683002
    # bullpen_used: the defending (home, in this fixture) side's boxscore.teams.pitchers.
    assert d["bullpen_used"] == [656492]


def test_ondeck_id_from_offense_block():
    ls = _linescore()
    ls["offense"]["onDeck"] = {"fullName": "Adley Rutschman", "id": 700000}
    d = P.pitcher_batter_fields(ls, _boxscore())
    assert d["ondeck_id"] == 700000


def test_ondeck_absent_never_fabricated():
    # No onDeck key on the offense block -> honest absence, not a fabricated id.
    d = P.pitcher_batter_fields(_linescore(), _boxscore())
    assert "ondeck_id" not in d


def test_names_without_boxscore():
    # No boxscore -> names+ids flow, but NO fabricated pitch_count / tto / bullpen_used.
    d = P.pitcher_batter_fields(_linescore(), None)
    assert d["pitcher"] == "Foster Griffin" and d["batter"] == "Gunnar Henderson"
    assert d["pitcher_id"] == 656492 and d["batter_id"] == 683002
    assert "pitch_count" not in d and "tto" not in d and "bullpen_used" not in d


def test_pitcher_on_away_side_is_found():
    box = {"teams": {"home": {"players": {}}, "away": {
        "players": {"ID111": {"stats": {"pitching": {
            "numberOfPitches": 42, "battersFaced": 9}}}},
        "pitchers": [222, 111]}}}
    ls = _linescore(pitcher="Some Reliever", pid=111)
    d = P.pitcher_batter_fields(ls, box)
    assert d["pitch_count"] == 42 and d["tto"] == 2
    # bullpen_used resolves to the AWAY side's list (the side pid=111 was actually found on).
    assert d["bullpen_used"] == [222, 111]


def test_bullpen_used_absent_or_unreadable_never_fabricated():
    # boxscore has the player but no "pitchers" list at all -> honest absence (pitch_count
    # still resolves -- the two reads are independent).
    box = {"teams": {"home": {"players": {
        "ID656492": {"stats": {"pitching": {"numberOfPitches": 87, "battersFaced": 19}}}}},
        "away": {"players": {}}}}
    d = P.pitcher_batter_fields(_linescore(), box)
    assert d["pitch_count"] == 87
    assert "bullpen_used" not in d
    # pid never resolves to any side (unknown pid) -> bullpen lookup also absent.
    box2 = {"teams": {"home": {"players": {}}, "away": {"players": {}}}}
    d2 = P.pitcher_batter_fields(_linescore(pid=999999), box2)
    assert "bullpen_used" not in d2 and "pitch_count" not in d2


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
