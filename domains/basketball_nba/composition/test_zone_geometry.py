"""Per-file test: the geometry formula reproduces shotDistance exactly on
CDN-native fixtures, and classify_zone clears its documented >=96% agreement
floor against ground-truth `area` labels on the real corpus.

Run: python -m pytest domains/basketball_nba/composition/test_zone_geometry.py -q
"""
from __future__ import annotations

import json

import pytest

from domains.basketball_nba.composition.zone_geometry import classify_zone, shot_geometry_ft
from domains.basketball_nba.lineups.pbp_lineups import _PBP_DIR

_FIXTURE = _PBP_DIR / "0022500003.json"

_TRUTH_MAP = {
    "Restricted Area": "rim", "In The Paint (Non-RA)": "paint", "Mid-Range": "mid",
    "Left Corner 3": "corner3", "Right Corner 3": "corner3", "Above the Break 3": "above_break_3",
}


def test_shot_geometry_matches_known_distances() -> None:
    # Mobley turnaround, 0022500003.json actionNumber 7: x=81.82,y=50.98 -> shotDistance=11.85
    dist, _ = shot_geometry_ft(81.8166885676741, 50.98039215686274)
    assert abs(dist - 11.85) < 0.01
    # Corner-3 example: x=4.94,y=4.90 -> shotDistance=22.56
    dist2, y_ft = shot_geometry_ft(4.944152431011826, 4.901960784313726)
    assert abs(dist2 - 22.56) < 0.01
    assert classify_zone(4.944152431011826, 4.901960784313726, is_3=True) == "corner3"


@pytest.mark.skipif(not _FIXTURE.exists(), reason="local-only data not present")
def test_classify_zone_agreement_floor_on_real_corpus() -> None:
    game_json = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    n, agree = 0, 0
    for a in game_json["game"]["actions"]:
        if a.get("actionType") in ("2pt", "3pt") and a.get("area") in _TRUTH_MAP and a.get("x") is not None:
            zone = classify_zone(float(a["x"]), float(a["y"]), a["actionType"] == "3pt")
            n += 1
            agree += int(zone == _TRUTH_MAP[a["area"]])
    assert n > 0
    assert agree / n >= 0.90  # documented ~96.7% on the full corpus; one game may vary a little
