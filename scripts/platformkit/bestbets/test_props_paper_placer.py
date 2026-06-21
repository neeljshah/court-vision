"""Per-file test for props_paper_placer -- paper-place PRICED player props into the
unified clv_ledger, honestly + idempotently, UNITS only.

Run ONLY this file (the full suite freezes the box):
    python -m pytest scripts/platformkit/bestbets/test_props_paper_placer.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.bestbets import props_paper_placer as P


# A priced board edge: model 0.66 over a fair-0.55 line -> the OVER side has EV.
def _priced_edge(player="Aaron Judge", stat="hits", line=1.5, p_over=0.66,
                 ev_over=0.12, ev_under=-0.10, fair_over=0.55, fair_under=0.45,
                 reliable=True, ev_flag="ok", match="NYY @ BOS"):
    return {"edge_basis": "ev_vs_priced", "best_side": "over", "side": "over",
            "model_p_over": p_over, "ev_over": ev_over, "ev_under": ev_under,
            "fair_over": fair_over, "fair_under": fair_under, "player": player,
            "stat": stat, "line": line, "source": "underdog", "match": match,
            "reliable": reliable, "ev_flag": ev_flag, "tier": "B"}


def _board(edges):
    def _fn(sport):
        return {"status": "ok", "edges": edges}
    return _fn


def test_placement_from_priced_edge_over_side():
    p = P.placement_from_edge(_priced_edge(), "mlb")
    assert p is not None
    assert p["prop_side"] == "over" and p["ledger_side"] == "home"
    assert p["model_prob"] == 0.66
    # raw taken decimal reconstructed from ev_over + model_prob = (0.12+1)/0.66
    assert abs(p["taken_decimal"] - (1.12 / 0.66)) < 1e-4
    assert p["tier"] in ("A", "B", "C")
    assert p["flat_unit"] == 1.0
    assert p["market"].startswith("prop|Aaron Judge|hits|1.5|over")
    assert "$" not in json.dumps(p) or "edge_claimed" in p  # no $ value field


def test_model_only_edge_is_skipped():
    e = _priced_edge()
    e["edge_basis"] = "model_view"  # no price
    assert P.placement_from_edge(e, "mlb") is None


def test_below_floor_is_skipped():
    # tiny EV below the proxy-adjusted C floor (0.02 + 0.01) -> no tier -> no bet
    e = _priced_edge(ev_over=0.005)
    assert P.placement_from_edge(e, "mlb") is None


def test_unreliable_edge_not_placed():
    out = P.run(("mlb",), board_fn=_board([_priced_edge(reliable=False)]),
                place=False)
    assert out["n_edges"] == 0 and out["n_placed"] == 0  # filtered pre-placement


def test_run_places_into_ledger_units_only(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    out = P.run(("mlb",), ledger_path=ledger, board_fn=_board([_priced_edge()]),
                place=True)
    assert out["n_placed"] == 1
    rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 1
    r = rows[0]
    assert r["market_type"] == "prop" and r["status"] == "open"
    assert r["executed"] is False and r["is_pm"] is False
    assert r["stake_units"] == 1.0 and r["clv_is_proxy"] is True
    # no dollar/pnl/roi/bare-stake key anywhere on the row
    banned = {"dollar", "dollars", "pnl", "roi", "profit", "stake"}
    assert banned.isdisjoint(set(r.keys()))


def test_run_is_idempotent(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    board = _board([_priced_edge()])
    P.run(("mlb",), ledger_path=ledger, board_fn=board, place=True)
    out2 = P.run(("mlb",), ledger_path=ledger, board_fn=board, place=True)
    assert out2["n_placed"] == 0 and out2["n_dup_skipped"] == 1  # dedup by bet_id
    rows = [l for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 1  # no duplicate row


def test_max_per_sport_caps_placement_highest_ev_first(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    edges = [_priced_edge(player="P1", ev_over=0.20),
             _priced_edge(player="P2", ev_over=0.15),
             _priced_edge(player="P3", ev_over=0.10)]
    out = P.run(("mlb",), ledger_path=ledger, board_fn=_board(edges),
                place=True, max_per_sport=2)
    assert out["n_placed"] == 2 and out["n_capped"] == 1
    rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    placed_players = {r["prop_player"] for r in rows}
    assert placed_players == {"P1", "P2"}  # highest-EV two placed, P3 capped


def test_under_side_maps_to_away():
    e = _priced_edge(p_over=0.30, ev_over=-0.15, ev_under=0.14)
    e["best_side"] = "under"
    p = P.placement_from_edge(e, "mlb")
    assert p is not None
    assert p["prop_side"] == "under" and p["ledger_side"] == "away"
    assert p["model_prob"] == 0.70  # 1 - 0.30
