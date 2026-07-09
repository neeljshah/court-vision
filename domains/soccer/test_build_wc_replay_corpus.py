"""Per-file test: domains.soccer.build_wc_replay_corpus + wc_ticker_map.

Covers: (1) ticker name matching incl. +/-1 day date-bucket fallback, (2) merge_asof
as-of no-leak (a candle before a goal's wallclock must never see that goal), (3) 3-way
outcome labeling from the settled Kalshi result field. No network (getter is a stub /
_KALSHI_DIR is monkeypatched to tmp_path); no writes outside tmp_path.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_build_wc_replay_corpus.py -q
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from domains.soccer import build_wc_replay_corpus as m
from domains.soccer.wc_ticker_map import build_ticker_index, datecode, match_event_any


def _touch(d, name):
    (d / name).write_text("{}", encoding="utf-8")


def test_ticker_matching(tmp_path):
    for code in ("MEX", "RSA", "TIE"):
        _touch(tmp_path, "KXWCGAME-26JUN11MEXRSA-%s.jsonl" % code)
    idx = build_ticker_index(tmp_path)
    assert match_event_any(date(2026, 6, 11), "MEX", "RSA", idx) == "KXWCGAME-26JUN11MEXRSA"
    assert match_event_any(date(2026, 6, 11), "RSA", "MEX", idx) == "KXWCGAME-26JUN11MEXRSA"
    # no candidate for an unrelated pair
    assert match_event_any(date(2026, 6, 11), "USA", "ENG", idx) is None


def test_ticker_matching_date_bucket_fallback(tmp_path):
    """Kalshi's ticker date can be 1 day off ESPN's UTC kickoff date (late-night kickoff
    bucketed differently) -- match_event_any must try +/-1 day, never guess beyond that."""
    _touch(tmp_path, "KXWCGAME-26JUN12KORCZE-KOR.jsonl")
    _touch(tmp_path, "KXWCGAME-26JUN12KORCZE-CZE.jsonl")
    _touch(tmp_path, "KXWCGAME-26JUN12KORCZE-TIE.jsonl")
    idx = build_ticker_index(tmp_path)
    espn_kickoff_date = date(2026, 6, 11)  # ticker says JUN12, ESPN UTC date is JUN11
    assert match_event_any(espn_kickoff_date, "KOR", "CZE", idx) == "KXWCGAME-26JUN12KORCZE"
    # 2+ days off is not a supported bucket skew -- must stay unmatched, never guessed
    assert match_event_any(date(2026, 6, 9), "KOR", "CZE", idx) is None


def _payload_one_goal(minute: float, home_id="1", away_id="2"):
    return {
        "header": {"competitions": [{"date": "2026-06-11T19:00Z", "competitors": [
            {"homeAway": "home", "team": {"id": home_id, "displayName": "Mexico", "abbreviation": "MEX"}},
            {"homeAway": "away", "team": {"id": away_id, "displayName": "South Africa", "abbreviation": "RSA"}},
        ]}]},
        "keyEvents": [{"scoringPlay": True, "clock": {"value": minute * 60.0}, "team": {"id": home_id}}],
    }


def test_asof_no_leak(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_KALSHI_DIR", tmp_path)
    kickoff_ts = 1000000000
    goal_minute = 50.0
    payload = _payload_one_goal(goal_minute)

    def candle(ts_offset_min, prob):
        return {"ts": _iso(kickoff_ts + ts_offset_min * 60), "prob": prob, "traded": True}

    home_doc = {"result": "yes", "candles": [
        candle(10, 0.4), candle(49, 0.42), candle(51, 0.55), candle(80, 0.7)]}
    away_doc = {"result": "no", "candles": []}
    tie_doc = {"result": "no", "candles": []}
    (tmp_path / "KXWCGAME-26JUN11MEXRSA-MEX.jsonl").write_text(json.dumps(home_doc), encoding="utf-8")
    (tmp_path / "KXWCGAME-26JUN11MEXRSA-RSA.jsonl").write_text(json.dumps(away_doc), encoding="utf-8")
    (tmp_path / "KXWCGAME-26JUN11MEXRSA-TIE.jsonl").write_text(json.dumps(tie_doc), encoding="utf-8")

    rows = m.build_game_rows("KXWCGAME-26JUN11MEXRSA", "MEX", "RSA", payload, "1",
                             kickoff_ts, hg_final=1, ag_final=0)
    assert len(rows) == 4
    by_minute = {r["minute"]: r for r in rows}
    # strictly BEFORE the goal's wallclock minute -> still 0-0 (no leak)
    assert by_minute[10.0]["score_home"] == 0
    assert by_minute[49.0]["score_home"] == 0
    # AT/AFTER the goal's wallclock minute -> reflects it
    assert by_minute[51.0]["score_home"] == 1
    assert by_minute[80.0]["score_home"] == 1
    assert all(r["outcome"] == "home_win" for r in rows)
    assert all(r["margin"] == r["score_home"] - r["score_away"] for r in rows)


def test_outcome_labeling_three_way(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_KALSHI_DIR", tmp_path)
    kickoff_ts = 1000000000
    payload = {"header": {"competitions": [{"date": "2026-06-11T19:00Z", "competitors": []}]},
              "keyEvents": []}

    def write(event, home_result, away_result, tie_result):
        for code, res in (("MEX", home_result), ("RSA", away_result), ("TIE", tie_result)):
            doc = {"result": res, "candles": [{"ts": _iso(kickoff_ts + 60), "prob": 0.5, "traded": True}]}
            (tmp_path / ("%s-%s.jsonl" % (event, code))).write_text(json.dumps(doc), encoding="utf-8")

    for event, results, expected in (
        ("E1", ("yes", "no", "no"), "home_win"),
        ("E2", ("no", "yes", "no"), "away_win"),
        ("E3", ("no", "no", "yes"), "draw"),
    ):
        write(event, *results)
        rows = m.build_game_rows(event, "MEX", "RSA", payload, "1", kickoff_ts,
                                 hg_final=0, ag_final=0)
        assert rows, "expected rows for %s" % event
        assert all(r["outcome"] == expected for r in rows)

    # unsettled (all 'no') -- never guess an outcome
    write("E4", "no", "no", "no")
    rows = m.build_game_rows("E4", "MEX", "RSA", payload, "1", kickoff_ts, hg_final=0, ag_final=0)
    assert rows == []


def _iso(epoch_s: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch_s, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
