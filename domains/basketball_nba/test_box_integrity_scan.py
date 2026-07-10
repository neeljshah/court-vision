"""Per-file test for domains.basketball_nba.box_integrity_scan -- synthetic
fixture only, no real parquet reads, no network.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_box_integrity_scan.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.box_integrity_scan import crosscheck_espn, scan_integrity

_COLS = ["event_id", "date", "home_abbr", "away_abbr", "home_score", "away_score",
         "status", "home_reb", "away_reb", "home_paint_pts", "away_paint_pts"]


def _fixture() -> pd.DataFrame:
    return pd.DataFrame([
        # clean row -- never flagged
        ["1", "2024-11-01", "BOS", "TOR", 110.0, 100.0, "STATUS_FINAL", 40.0, 38.0, 44.0, 30.0],
        # (a) impossible tie -- the actual incidental find (0022400230 shape)
        ["2", "2024-11-16", "BOS", "TOR", 114.0, 114.0, None, 40.0, 38.0, 44.0, 30.0],
        # (b) STATUS_FINAL score out of the 50-200 sanity band
        ["3", "2024-11-02", "BOS", "TOR", 20.0, 100.0, "STATUS_FINAL", 40.0, 38.0, 44.0, 30.0],
        # (c) negative box-detail value
        ["4", "2024-11-03", "BOS", "TOR", 110.0, 100.0, "STATUS_FINAL", -3.0, 38.0, 44.0, 30.0],
        # (c) points-subset column exceeds that side's own total score
        ["5", "2024-11-04", "BOS", "TOR", 90.0, 100.0, "STATUS_FINAL", 40.0, 38.0, 200.0, 30.0],
        # postponed placeholder -- 0-0 must NOT trip the tie criterion
        ["6", "2024-11-05", "BOS", "TOR", 0.0, 0.0, "STATUS_POSTPONED", None, None, None, None],
    ], columns=_COLS)


def test_clean_row_not_flagged():
    flags = scan_integrity(_fixture(), "test")
    ids = {f["event_id"] for f in flags}
    assert "1" not in ids


def test_postponed_placeholder_not_flagged():
    flags = scan_integrity(_fixture(), "test")
    ids = {f["event_id"] for f in flags}
    assert "6" not in ids


def test_tied_score_flagged():
    flags = scan_integrity(_fixture(), "test")
    f = next(x for x in flags if x["event_id"] == "2")
    assert "tied_score" in f["reasons"]
    assert f["source"] == "test"


def test_score_out_of_range_only_on_final():
    flags = scan_integrity(_fixture(), "test")
    f = next(x for x in flags if x["event_id"] == "3")
    assert "score_out_of_range" in f["reasons"]


def test_negative_boxdetail_flagged():
    flags = scan_integrity(_fixture(), "test")
    f = next(x for x in flags if x["event_id"] == "4")
    assert any(r.startswith("negative:home_reb") for r in f["reasons"])


def test_exceeds_total_flagged():
    flags = scan_integrity(_fixture(), "test")
    f = next(x for x in flags if x["event_id"] == "5")
    assert any(r.startswith("exceeds_total:home_paint_pts") for r in f["reasons"])


def test_flag_count_matches_expected():
    flags = scan_integrity(_fixture(), "test")
    assert len(flags) == 4  # ids 2,3,4,5 -- not 1 (clean) or 6 (postponed)


# ---------------------------------------------------------------------------
# crosscheck_espn -- mocked http_get, no network
# ---------------------------------------------------------------------------

def _summary_payload(home_score: str, away_score: str) -> dict:
    return {
        "header": {"competitions": [{
            "status": {"type": {"name": "STATUS_FINAL"}},
            "competitors": [
                {"homeAway": "home", "team": {"abbreviation": "BOS"}, "score": home_score},
                {"homeAway": "away", "team": {"abbreviation": "TOR"}, "score": away_score},
            ],
        }]},
        "boxscore": {"teams": [
            {"homeAway": "home", "team": {"abbreviation": "BOS"}, "statistics": []},
            {"homeAway": "away", "team": {"abbreviation": "TOR"}, "statistics": []},
        ]},
    }


def test_crosscheck_our_capture_corrupted():
    """Fresh ESPN score DIFFERS from what we stored -> our capture was wrong."""
    flag = {"event_id": "2", "date": "2024-11-16", "home_abbr": "BOS",
            "away_abbr": "TOR", "home_score": 114.0, "away_score": 114.0}

    def fake_get(url: str) -> dict:
        if "scoreboard" in url:
            return {"events": [{"id": "999", "name": "BOS at TOR"}]}
        return _summary_payload("112", "108")  # fresh score, not a tie

    out = crosscheck_espn([flag], http_get=fake_get)
    assert out[0]["classification"] == "our-capture-corrupted"


def test_crosscheck_source_was_wrong():
    """Fresh ESPN score MATCHES what we stored -> the anomaly is upstream."""
    flag = {"event_id": "2", "date": "2024-11-16", "home_abbr": "BOS",
            "away_abbr": "TOR", "home_score": 114.0, "away_score": 114.0}

    def fake_get(url: str) -> dict:
        if "scoreboard" in url:
            return {"events": [{"id": "999", "name": "BOS at TOR"}]}
        return _summary_payload("114", "114")

    out = crosscheck_espn([flag], http_get=fake_get)
    assert out[0]["classification"] == "source-was-wrong"


def test_crosscheck_unresolved_no_match():
    flag = {"event_id": "2", "date": "2024-11-16", "home_abbr": "BOS",
            "away_abbr": "TOR", "home_score": 114.0, "away_score": 114.0}

    def fake_get(url: str) -> dict:
        return {"events": []} if "scoreboard" in url else {}

    out = crosscheck_espn([flag], http_get=fake_get)
    assert out[0]["classification"] == "unresolved"
