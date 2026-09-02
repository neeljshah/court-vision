"""Per-file test for scripts.platformkit.eval_gate.s93_mlb_every_tick (S93 premise census).

Covers the three things the CLOSED AT LIMIT verdict rests on: the moneyline/outcome filter
that produces the event denominator, the on-disk ticker census (both sources, and the
joined store winning a tie), and the 1/sqrt(n_clusters) arithmetic that says how many game
clusters the 0.002 half-width needs.
python -m pytest tests/platformkit/ingame/test_s93_mlb_every_tick.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s93_mlb_every_tick as S


def _prices():
    return pd.DataFrame([
        {"venue": "kalshi", "game_date": "2026-06-20", "event_key": "A",
         "market_type": "moneyline", "result_where_known": "home"},
        {"venue": "kalshi", "game_date": "2026-06-20", "event_key": "A",
         "market_type": "moneyline", "result_where_known": "home"},
        {"venue": "polymarket", "game_date": "2023-04-01", "event_key": "B",
         "market_type": "moneyline", "result_where_known": "away"},
        {"venue": "kalshi", "game_date": "2026-06-21", "event_key": "C",
         "market_type": "moneyline", "result_where_known": None},      # no outcome -> dropped
        {"venue": "kalshi", "game_date": "2026-06-21", "event_key": "D",
         "market_type": "total", "result_where_known": "yes"},         # not moneyline -> dropped
    ])


def test_moneyline_events_keeps_only_settled_moneyline():
    events = S.moneyline_events(_prices())
    assert list(events.index) == ["A", "B"]
    assert int(events.at["A", "n_ticks"]) == 2
    assert events.at["B", "venue"] == "polymarket"


def test_state_bearing_tickers_reads_both_sources_and_prefers_the_joined_store(tmp_path):
    joined, espn = tmp_path / "joined", tmp_path / "espn"
    joined.mkdir(), espn.mkdir()
    (joined / "A.jsonl").write_text("{}\n", encoding="ascii")
    (espn / "1_series.json").write_text(json.dumps({"event_id": "1", "capture_name": "A"}), "ascii")
    (espn / "2_series.json").write_text(json.dumps({"event_id": "2", "capture_name": "Z"}), "ascii")
    (espn / "3_series.json").write_text("not json", encoding="ascii")   # unreadable != bad
    found = S.state_bearing_tickers(joined, espn)
    assert found == {"A": "ingame_grade_joined", "Z": "espn_wp_series"}


def test_clusters_for_half_width_is_the_inverse_square_law():
    assert S.clusters_for_half_width(41, 0.004, 0.002) == 164          # halve the width, 4x the n
    assert S.clusters_for_half_width(41, 0.002, 0.002) == 41
    with pytest.raises(ValueError):
        S.clusters_for_half_width(41, 0.005, 0.0)


def test_census_reports_the_share_and_closes_at_limit_when_the_reach_is_short():
    events = S.moneyline_events(_prices())
    report = S.census(events, {"A": "ingame_grade_joined"}, n_raw_state_games=7)
    rec, res = report["reconstructable"], report["resolution"]
    assert rec["n_events"] == 1 and rec["share"] == 0.5
    assert rec["capture_window"] == ["2026-06-20", "2026-06-20"]
    assert rec["n_events_outside_window_no_state_possible"] == 1      # the 2023 polymarket event
    assert res["bar"] == 0.004 and res["target_half_width"] == 0.002  # Q3: bars unmoved
    assert res["screen_clusters_needed"] == 289 and not res["resolvable"]
    assert report["verdict"] == "CLOSED AT LIMIT"
    assert report["edge_claimed"] is False
    assert report["state_sources"]["n_espn_keyed_unbridged"] == 7
