"""Per-file tests for quote_freshness (offline, synthetic rows only).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_quote_freshness.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import quote_freshness as qf


def _rows(probs):
    return [{"market_prob": p, "ts": "t%d" % i} for i, p in enumerate(probs)]


def test_first_tick_always_fresh():
    rows = _rows([0.55])
    assert qf.freshness_mask(rows) == [True]


def test_alternating_all_fresh():
    rows = _rows([0.5, 0.6, 0.5, 0.6, 0.5])
    assert qf.freshness_mask(rows) == [True, True, True, True, True]


def test_dedup_run_is_stale_after_first():
    # first tick fresh, then 4 repeats of the same quote -> stale, then a real move.
    rows = _rows([0.55, 0.55, 0.55, 0.55, 0.55, 0.60])
    mask = qf.freshness_mask(rows)
    assert mask == [True, False, False, False, False, True]


def test_empty_rows_empty_mask():
    assert qf.freshness_mask([]) == []


def test_missing_prob_field_is_conservatively_stale_not_first():
    rows = [{"market_prob": 0.5}, {"market_prob": None}, {"market_prob": 0.5}]
    mask = qf.freshness_mask(rows)
    assert mask[0] is True  # first tick
    assert mask[1] is False  # missing -> cannot confirm a move -> stale
    assert mask[2] is False  # 0.5 == 0.5 (prev was None from missing tick's cur)


def test_epsilon_tolerance_treats_float_noise_as_stale():
    rows = _rows([0.550000001, 0.550000002])
    mask = qf.freshness_mask(rows)
    assert mask == [True, False]


def test_filter_fresh_returns_only_fresh_rows_in_order():
    rows = _rows([0.5, 0.5, 0.6, 0.6, 0.7])
    fresh = qf.filter_fresh(rows)
    assert [r["market_prob"] for r in fresh] == [0.5, 0.6, 0.7]


def test_freshness_share_counts_and_ratio():
    rows = _rows([0.5, 0.5, 0.5, 0.6])
    out = qf.freshness_share(rows)
    assert out["n_ticks"] == 4
    assert out["n_fresh_ticks"] == 2  # tick0 (first) + tick3 (moved)
    assert out["fresh_share"] == 0.5


def test_freshness_share_empty_is_none_not_zero():
    out = qf.freshness_share([])
    assert out["n_ticks"] == 0
    assert out["n_fresh_ticks"] == 0
    assert out["fresh_share"] is None


def test_longest_stale_run_matches_wave6_style_measurement():
    # tick0 fresh, then a 5-run of stale, one fresh move, a 2-run of stale.
    rows = _rows([0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.7, 0.7, 0.7])
    assert qf.longest_stale_run(rows) == 5


def test_longest_stale_run_all_fresh_is_zero():
    rows = _rows([0.5, 0.6, 0.7])
    assert qf.longest_stale_run(rows) == 0


def test_custom_prob_field():
    rows = [{"my_field": 0.1}, {"my_field": 0.1}, {"my_field": 0.2}]
    mask = qf.freshness_mask(rows, prob_field="my_field")
    assert mask == [True, False, True]
