"""Per-file test for prop_best_exec -- cross-book shop + devig fair expected-CLV
gate + circuit breaker at prop placement. UNITS only.

Run ONLY this file (the full suite freezes the box):
    python -m pytest tests/platformkit/bestbets/test_prop_best_exec.py -q
"""
from __future__ import annotations

from scripts.platformkit.bestbets import prop_best_exec as X
from scripts.platformkit.odds_provider.prop_base import PropLine


def _line(book, over=None, under=None, player="Aaron Judge", stat="Hits", line=1.5):
    return PropLine(sport="mlb", event_id="1", match="NYY @ BOS", player=player,
                    team=None, stat=stat, line=line, over_price=over, under_price=under,
                    payout_type="sportsbook" if (over or under) else "dfs_pickem",
                    source=book, as_of="2026-07-15T00:00:00Z")


class _FakeProvider:
    name = "fake"

    def __init__(self, rows):
        self._rows = rows

    def fetch_props(self, sport):
        return self._rows


def _edge(side="over", player="Aaron Judge", stat="Hits", line=1.5):
    return {"side": side, "best_side": side, "player": player, "stat": stat, "line": line}


# (a) shopped best price is picked across books -----------------------------

def test_shop_prop_picks_best_price_across_books():
    rows = [
        _line("dk", over=1.80, under=1.95),
        _line("mgm", over=2.05, under=1.85),  # best OVER price
    ]
    shopped = X.shop_prop(_edge(), "mlb", providers=[_FakeProvider(rows)])
    assert shopped is not None
    assert shopped["taken_price"] == 2.05 and shopped["taken_book"] == "mgm"
    assert shopped["opp_price"] == 1.95 and shopped["opp_book"] == "dk"
    assert len(shopped["all_books"]) == 2


# (b) below-threshold expected CLV blocks ------------------------------------

def test_below_threshold_expected_clv_blocks():
    # near-even two-way pair -> fair ~0.5; taken price barely above fair -> < 1% edge.
    rows = [_line("dk", over=1.99, under=2.01)]
    g = X.fair_and_gate(1.99, 2.01, threshold_pct=1.0)
    assert g["passed"] is False
    dec = X.decide(_edge(), "mlb", [], "2026-07-15T12:00:00Z",
                   providers=[_FakeProvider(rows)])
    assert dec["place"] is False
    assert dec["exec_log"]["expected_clv_pct"] is not None


# (c) one-sided market fails closed ------------------------------------------

def test_one_sided_market_fails_closed():
    rows = [_line("dk", over=2.10, under=None)]
    shopped = X.shop_prop(_edge(), "mlb", providers=[_FakeProvider(rows)])
    assert shopped is not None and shopped["opp_price"] is None
    g = X.fair_and_gate(shopped["taken_price"], shopped["opp_price"])
    assert g["passed"] is False and g["reason"] == "no_two_way"
    dec = X.decide(_edge(), "mlb", [], "2026-07-15T12:00:00Z",
                   providers=[_FakeProvider(rows)])
    assert dec["place"] is False and dec["reason"] == "no_two_way"


# (d) breaker CAPPED blocks past cap ------------------------------------------

def test_breaker_capped_blocks_past_cap():
    rows = [_line("dk", over=2.30, under=1.85)]  # clears the CLV gate comfortably
    now = "2026-07-15T12:00:00Z"
    # rolling CLV negative -> CAPPED; 5 prop placements already made today -> cap reached.
    ledger_rows = [
        {"market_type": "prop", "ts": "2026-07-10T00:00:00Z", "clv_pct": -5.0},
    ] + [
        {"market_type": "prop", "ts": "2026-07-15T01:00:00Z"} for _ in range(5)
    ]
    dec = X.decide(_edge(), "mlb", ledger_rows, now, providers=[_FakeProvider(rows)])
    assert dec["place"] is False
    assert dec["exec_log"]["breaker_state"] == "CAPPED"


# (e) ledger row carries exec_gate/signal_ts/latency --------------------------

def test_gate_and_stamp_stamps_ledger_fields():
    # gate_and_stamp's decide() defaults providers=None (real-provider fallback) --
    # stub shop_prop so the test never touches the network.
    import scripts.platformkit.bestbets.prop_best_exec as mod
    orig_shop = mod.shop_prop
    mod.shop_prop = lambda edge, sport, providers=None: {
        "side": "over", "taken_price": 2.05, "taken_book": "mgm",
        "opp_price": 2.10, "opp_book": "dk", "payout_type": "sportsbook",
        "as_of": "2026-07-15T00:10:00Z", "all_books": [],
    }
    p = {"market": "prop|Aaron Judge|Hits|1.5|over", "taken_book": "dk", "taken_decimal": 1.80}
    edge = _edge()
    edge["as_of"] = "2026-07-15T00:00:00Z"
    try:
        out = X.gate_and_stamp(p, edge, "mlb", [])
    finally:
        mod.shop_prop = orig_shop
    assert out is not None
    assert out["taken_book"] == "mgm" and out["taken_decimal"] == 2.05
    assert "exec_gate" in out and out["exec_gate"]["book"] == "mgm"
    assert out["signal_ts"] == "2026-07-15T00:00:00Z"
    assert out["placement_latency_ms"] is not None
    # LEVER 1 (prop-side stamp, EXECUTION_BACKLOG.md #1/#5): quote_age_s present.
    assert "quote_age_s" in out
    assert isinstance(out["quote_age_s"], float)


# (f) LEVER 1 prop-side stamp: quote_age_s = now - shopped quote's as_of --------

def test_quote_age_s_matches_formula():
    assert X._quote_age_s("2026-07-15T00:00:00+00:00", "2026-07-15T00:00:10+00:00") == 10.0
    assert X._quote_age_s("2026-07-15T00:00:00Z", "2026-07-15T00:01:00Z") == 60.0


def test_quote_age_s_honest_none_on_bad_input():
    assert X._quote_age_s(None, "2026-07-15T00:00:00Z") is None
    assert X._quote_age_s("not-a-timestamp", "2026-07-15T00:00:00Z") is None


if __name__ == "__main__":
    test_shop_prop_picks_best_price_across_books()
    test_below_threshold_expected_clv_blocks()
    test_one_sided_market_fails_closed()
    test_breaker_capped_blocks_past_cap()
    test_gate_and_stamp_stamps_ledger_fields()
    test_quote_age_s_matches_formula()
    test_quote_age_s_honest_none_on_bad_input()
    print("test_prop_best_exec self-checks OK")
