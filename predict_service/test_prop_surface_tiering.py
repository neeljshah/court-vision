"""Per-file test: predict_service.prop_surface_tiering.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/test_prop_surface_tiering.py -q

Acceptance criteria (P2-8):
  1. Priced rows sorted by (tier, confidence) descending.
  2. UNAVAILABLE response passes through unchanged.
  3. No $ field present on any returned row.
  4. tier=None rows sink below tiered rows.
  5. Empty rows -> empty list.
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from predict_service.prop_surface_tiering import tier_and_sort, apply_tiering_to_response


def _row(player="A", stat="pts", p_over=0.55, confidence="recency_gaussian",
         edge_vs_market=0.05):
    """Minimal PlayerPropRow -- no $ field."""
    return {
        "player": player, "stat": stat, "line": 20.5, "book": "test",
        "p_over": p_over,
        "p_under": (1.0 - p_over) if p_over is not None else None,
        "proj_mean": 22.0, "proj_sigma": 4.0,
        "edge_vs_market": edge_vs_market,
        "tier": None, "confidence": confidence, "clv_is_proxy": True,
        "date": "2026-06-20", "sport": "nba", "honest_note": "test",
    }


def _proven_cal(stat="pts"):
    return {stat: {"bss": 0.10, "n": 200, "brier": 0.22, "ece": 0.02}}


# 1. Empty input
def test_empty_rows_returns_empty():
    assert tier_and_sort([], calibration={}) == []


# 2. tier=None sinks below tiered rows
def test_tier_none_sinks_below_tiered():
    unpriced = _row(player="U", p_over=None, confidence=None)
    priced = _row(player="P", p_over=0.6)
    result = tier_and_sort([unpriced, priced], calibration={})
    assert result[0]["player"] == "P"
    assert result[1]["tier"] is None


# 3. CALIBRATION_PROVEN outranks MODEL_VIEW
def test_proven_outranks_model_view():
    calibration = _proven_cal("pts")
    pts = _row(player="PTS", stat="pts", p_over=0.55, edge_vs_market=0.02)
    reb = _row(player="REB", stat="reb", p_over=0.60, edge_vs_market=0.10)
    result = tier_and_sort([reb, pts], calibration=calibration)
    assert result[0]["player"] == "PTS"
    assert result[0]["tier"] == "CALIBRATION_PROVEN"
    assert result[1]["tier"] == "MODEL_VIEW"


# 4. recency_gaussian confidence beats None within same tier
def test_confidence_rank_within_same_tier():
    rows = [
        _row(player="NoConf", stat="reb", confidence=None, edge_vs_market=0.01),
        _row(player="WithConf", stat="pts", confidence="recency_gaussian", edge_vs_market=0.01),
    ]
    result = tier_and_sort(rows, calibration={})
    assert result[0]["player"] == "WithConf"


# 5. Higher |edge_vs_market| wins within same tier+confidence
def test_higher_abs_edge_wins_same_tier_and_conf():
    rows = [
        _row(player="Low", stat="pts", edge_vs_market=0.01),
        _row(player="High", stat="reb", edge_vs_market=0.08),
    ]
    result = tier_and_sort(rows, calibration={})
    assert result[0]["player"] == "High"


# 6. Negative edge uses abs value for ranking
def test_negative_edge_uses_abs_for_rank():
    rows = [
        _row(player="Small", stat="reb", edge_vs_market=0.02),
        _row(player="Neg",   stat="pts", edge_vs_market=-0.10),
    ]
    result = tier_and_sort(rows, calibration={})
    assert result[0]["player"] == "Neg"


# 7. No $ field on any returned row
def test_no_dollar_field_on_output():
    rows = [_row(player="P1", stat="ast"), _row(player="P2", stat="pts")]
    result = tier_and_sort(rows, calibration=_proven_cal("ast"))
    banned = {"pnl", "roi", "dollar", "profit", "expected_value_usd"}
    for r in result:
        assert not banned.intersection(set(r.keys())), (
            f"Banned key found in {r}")


# 8. UNAVAILABLE response passes through unchanged
def test_unavailable_passthrough():
    import copy
    body = {
        "status": "UNAVAILABLE", "sport": "nba", "reason": "offseason",
        "rows": [], "count": 0, "edge_claimed": False,
        "clv_is_proxy": True, "honest_note": "NBA offseason",
    }
    original = copy.deepcopy(body)
    result = apply_tiering_to_response(body, calibration={})
    assert result is body
    assert result["status"] == "UNAVAILABLE"
    assert result["rows"] == []


# 9. apply_tiering_to_response on ok status applies sort
def test_apply_ok_sorts_rows():
    calibration = _proven_cal("ast")
    body = {
        "status": "ok", "sport": "nba",
        "rows": [
            _row(player="REB", stat="reb", edge_vs_market=0.09),
            _row(player="AST", stat="ast", edge_vs_market=0.02),
        ],
        "count": 2, "edge_claimed": False, "clv_is_proxy": True,
        "honest_note": "test",
    }
    result = apply_tiering_to_response(body, calibration=calibration)
    assert result["rows"][0]["player"] == "AST"
    assert result["rows"][0]["tier"] == "CALIBRATION_PROVEN"
    assert result["rows"][1]["tier"] == "MODEL_VIEW"
    assert result["count"] == 2


# 10. Full 5-row mix: tier ordering is stable across all buckets
def test_multi_row_tier_ordering():
    calibration = {
        "ast": {"bss": 0.12, "n": 150, "brier": 0.21, "ece": 0.01},
        "blk": {"bss": 0.08, "n": 120, "brier": 0.23, "ece": 0.02},
    }
    rows = [
        _row("MV",       "pts",  p_over=0.55, edge_vs_market=0.07),
        _row("AST_P",    "ast",  p_over=0.62, edge_vs_market=0.03),
        _row("BLK_P",    "blk",  p_over=0.58, edge_vs_market=0.11),
        _row("REB_NC",   "reb",  p_over=0.50, edge_vs_market=0.05, confidence=None),
        _row("UNPRICED", "stl",  p_over=None, edge_vs_market=None, confidence=None),
    ]
    result = tier_and_sort(rows, calibration=calibration)
    assert len(result) == 5
    tiers = [r["tier"] for r in result]
    proven_idx = [i for i, t in enumerate(tiers) if t == "CALIBRATION_PROVEN"]
    mv_idx = [i for i, t in enumerate(tiers) if t == "MODEL_VIEW"]
    none_idx = [i for i, t in enumerate(tiers) if t is None]
    assert all(p < m for p in proven_idx for m in mv_idx)
    assert all(m < n for m in mv_idx for n in none_idx)
    # BLK_P has higher |edge| (0.11) -> leads proven
    proven_players = [r["player"] for r in result if r["tier"] == "CALIBRATION_PROVEN"]
    assert proven_players[0] == "BLK_P"
    assert result[-1]["player"] == "UNPRICED"


# 11. edge_claimed never set True on rows
def test_edge_claimed_not_true_on_rows():
    rows = [_row(player="P", stat="pts", p_over=0.6)]
    result = tier_and_sort(rows, calibration=_proven_cal("pts"))
    for r in result:
        assert r.get("edge_claimed") is not True


if __name__ == "__main__":
    tests = [
        test_empty_rows_returns_empty,
        test_tier_none_sinks_below_tiered,
        test_proven_outranks_model_view,
        test_confidence_rank_within_same_tier,
        test_higher_abs_edge_wins_same_tier_and_conf,
        test_negative_edge_uses_abs_for_rank,
        test_no_dollar_field_on_output,
        test_unavailable_passthrough,
        test_apply_ok_sorts_rows,
        test_multi_row_tier_ordering,
        test_edge_claimed_not_true_on_rows,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
