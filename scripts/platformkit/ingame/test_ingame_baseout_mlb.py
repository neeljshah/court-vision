"""Per-file test for the deep MLB base-out / run-expectancy extractor.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/ingame/test_ingame_baseout_mlb.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import ingame_baseout_mlb as B


def _ev(outs, on1=False, on2=False, on3=False, balls=None, strikes=None, nested=False):
    sit = {"outs": outs, "onFirst": on1, "onSecond": on2, "onThird": on3}
    if balls is not None:
        sit["balls"] = balls
    if strikes is not None:
        sit["strikes"] = strikes
    return {"competitions": [{"situation": sit}]} if nested else {"situation": sit}


def test_bases_empty_re24():
    bo = B.parse_baseout(_ev(0))
    assert bo["base_state"] == 0 and bo["base_label"] == "---"
    assert bo["outs"] == 0 and bo["base_out_state"] == 0
    assert bo["run_expectancy"] == 0.481           # standard empty/0-out RE


def test_bases_loaded_two_out():
    bo = B.parse_baseout(_ev(2, on1=True, on2=True, on3=True))
    assert bo["base_state"] == 7 and bo["base_label"] == "123"
    assert bo["base_out_state"] == 7 * 3 + 2
    assert bo["run_expectancy"] == 0.752


def test_runner_object_counts_as_occupied_and_nested():
    # ESPN sometimes gives a runner/athlete object instead of True; nested under competitions
    bo = B.parse_baseout(_ev(1, on2={"athlete": {"id": "1"}}, nested=True))
    assert bo["on_second"] is True and bo["base_state"] == 2
    assert bo["run_expectancy"] == 0.664


def test_count_field():
    bo = B.parse_baseout(_ev(1, balls=2, strikes=1))
    assert bo["balls"] == 2 and bo["strikes"] == 1


def test_no_situation_returns_empty():
    assert B.parse_baseout({}) == {}
    assert B.parse_baseout({"situation": {}}) == {}
    assert B.parse_baseout({"situation": {"onFirst": True}}) == {}  # no outs -> not real


def test_three_outs_skipped():
    assert B.parse_baseout(_ev(3, on1=True)) == {}   # inning-over transient, skipped


def test_summary_fields_mlb_only():
    ev = _ev(1, on1=True, balls=3, strikes=2)
    f = B.baseout_summary_fields("mlb", ev)
    assert f["outs"] == 1 and f["base"] == 1 and f["bos"] == 4
    assert f["re"] == 0.509 and f["count"] == "3-2"
    # non-MLB sports get nothing (additive, sport-scoped)
    assert B.baseout_summary_fields("nba", ev) == {}
    assert B.baseout_summary_fields("soccer", ev) == {}
