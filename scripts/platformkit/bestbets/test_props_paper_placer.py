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


def test_soccer_ungradeable_stat_is_dropped(tmp_path):
    # WC Shots On Target has NO per-player keyless feed -> must not be placed (would pend
    # forever); Shots IS keyless-gradeable (leader) -> placed. mlb is unfiltered.
    board = _board([
        _priced_edge(player="Kylian Mbappe", stat="Shots", line=2.5, match="FRA @ ESP"),
        _priced_edge(player="Kylian Mbappe", stat="Shots On Target", line=1.5,
                     match="FRA @ ESP"),
    ])
    out = P.run(("soccer_intl",), board_fn=board, place=False)
    placed = out["placed_markets"]
    assert any("|Shots|" in m for m in placed)
    assert not any("Shots On Target" in m for m in placed)
    assert out["by_sport"]["soccer_intl"]["placed"] == 1


def test_calibration_only_gates_to_proven_families(tmp_path, monkeypatch):
    # calibration_only must drop a not-proven (sport,stat) and keep a proven one.
    import scripts.platformkit.bestbets.calibration_gate as CG
    monkeypatch.setattr(CG, "proven_families",
                        lambda **k: {"mlb": {"Hits"}})  # only mlb Hits is proven
    board = _board([
        _priced_edge(player="Aaron Judge", stat="Hits", line=1.5),
        _priced_edge(player="Aaron Judge", stat="RBIs", line=0.5),  # not proven -> dropped
    ])
    out = P.run(("mlb",), board_fn=board, place=False, calibration_only=True)
    placed = out["placed_markets"]
    assert any("|Hits|" in m for m in placed)
    assert not any("|RBIs|" in m for m in placed)
    assert out["by_sport"]["mlb"]["placed"] == 1
    # without the gate, BOTH place
    out2 = P.run(("mlb",), board_fn=board, place=False, calibration_only=False)
    assert out2["by_sport"]["mlb"]["placed"] == 2


def test_is_settleable_allowlist():
    assert P._is_settleable("mlb", "anything") is True          # no allowlist -> all pass
    assert P._is_settleable("soccer_intl", "Goals") is True
    assert P._is_settleable("soccer_intl", "Shots") is True     # leader-gradeable
    assert P._is_settleable("soccer_intl", "Shots On Target") is False
    assert P._is_settleable("soccer_intl", "Fouls") is False


def test_below_floor_is_skipped():
    # tiny EV below the proxy-adjusted C floor (0.02 + 0.01) -> no tier -> no bet
    e = _priced_edge(ev_over=0.005)
    assert P.placement_from_edge(e, "mlb") is None


def test_unreliable_edge_not_placed():
    out = P.run(("mlb",), board_fn=_board([_priced_edge(reliable=False)]),
                place=False)
    assert out["n_edges"] == 0 and out["n_placed"] == 0  # filtered pre-placement


def test_min_tier_drops_weaker_props():
    # Discipline floor: a prop weaker than min_tier is skipped (no marginal flood).
    base = P.placement_from_edge(_priced_edge(), "mlb")
    assert base is not None
    tier = base["tier"]
    # its own tier as the floor keeps it; a strictly stronger floor drops it.
    assert P.placement_from_edge(_priced_edge(), "mlb", min_tier=tier) is not None
    if tier in ("B", "C"):
        stronger = "A" if tier == "B" else "B"
        assert P.placement_from_edge(_priced_edge(), "mlb", min_tier=stronger) is None
    # an explicit tier-C edge is dropped by min_tier='B' but kept with no floor.
    c = P.placement_from_edge(_priced_edge(ev_over=0.04), "mlb")
    if c is not None and c["tier"] == "C":
        assert P.placement_from_edge(_priced_edge(ev_over=0.04), "mlb", min_tier="B") is None


def test_run_min_tier_passthrough(tmp_path, monkeypatch):
    # run(min_tier='A') only places tier-A edges; a tier-C edge in the board is dropped.
    monkeypatch.setenv("CV_PROP_BEST_EXEC", "0")
    ledger = tmp_path / "l.jsonl"
    edges = [_priced_edge(player="Strong", ev_over=0.30),   # tier A
             _priced_edge(player="Weak", ev_over=0.04)]      # tier C (if it clears floor)
    out = P.run(("mlb",), board_fn=_board(edges), ledger_path=ledger,
                place=True, min_tier="A")
    assert all(m.startswith("prop|Strong") for m in out["placed_markets"])


def test_run_places_into_ledger_units_only(tmp_path, monkeypatch):
    # legacy single-book write path (no providers injected here) -- best-exec is
    # covered separately in tests/platformkit/bestbets/test_prop_best_exec.py.
    monkeypatch.setenv("CV_PROP_BEST_EXEC", "0")
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


def test_run_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("CV_PROP_BEST_EXEC", "0")
    ledger = tmp_path / "clv_ledger.jsonl"
    board = _board([_priced_edge()])
    P.run(("mlb",), ledger_path=ledger, board_fn=board, place=True)
    out2 = P.run(("mlb",), ledger_path=ledger, board_fn=board, place=True)
    assert out2["n_placed"] == 0 and out2["n_dup_skipped"] == 1  # dedup by bet_id
    rows = [l for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 1  # no duplicate row


def test_max_per_sport_caps_placement_highest_ev_first(tmp_path, monkeypatch):
    monkeypatch.setenv("CV_PROP_BEST_EXEC", "0")
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
