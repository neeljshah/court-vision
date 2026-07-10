"""Per-file test for the entry-timing study -- synthetic data, tmp_path only.
Covers: order-time prob_at (no lookahead), stale-repeat window filter,
consensus median across books, drift math on a constructed path, entry-CLV
sign convention, and policy tier logic.
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/entry_timing/test_entry_timing.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.execution.entry_timing import assemble as asm
from scripts.platformkit.execution.entry_timing import study as st
from scripts.platformkit.execution.entry_timing.cli import derive_policy, nearest_horizon

COMMENCE = "2026-07-08T23:00:00+00:00"
T0 = asm.parse_ts(COMMENCE)


def quote(t_s, prob, book="b1", market="moneyline", gid="g1", side="home"):
    from datetime import datetime, timezone
    cap = datetime.fromtimestamp(t_s, tz=timezone.utc).isoformat()
    return {"sport": "x", "game_id": gid, "market_type": market, "side": side,
            "line": None, "odds": 2.0, "book": book, "devigged_prob": prob,
            "captured_at": cap, "commence_time": COMMENCE}


def write_feed(tmp_path, rows):
    d = tmp_path / "x"
    d.mkdir()
    with open(d / "2026-07-08.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return tmp_path


def test_prob_at_never_looks_forward():
    ticks = [(10.0, 0.5), (20.0, 0.6)]
    assert asm.prob_at(ticks, 9) is None
    assert asm.prob_at(ticks, 10) == 0.5
    assert asm.prob_at(ticks, 19.9) == 0.5
    assert asm.prob_at(ticks, 25) == 0.6


def test_stale_repeat_and_consensus(tmp_path):
    rows = [
        quote(T0 - 7200, 0.40, book="b1"), quote(T0 - 7200, 0.50, book="b2"),
        quote(T0 - 7200, 0.60, book="b3"),          # median 0.50
        quote(T0 - 600, 0.55),
        quote(T0 + 86400 * 20, 0.99),               # stale repeat -> dropped
        quote(T0 - 86400 * 3, 0.10),                # outside lookback -> dropped
    ]
    root = write_feed(tmp_path, rows)
    paths = asm.assemble_line_history("x", root=root)
    p = paths[("g1", "moneyline", "home")]
    probs = [pr for _, pr in p["ticks"]]
    assert probs == [0.50, 0.55]                    # consensus + window filter
    assert asm.close_prob(p) == 0.55


def test_drift_decomposition_math():
    # path: T-24h 0.50 -> T-1h 0.55 -> close 0.60 ; move continues upward
    ticks = [(T0 - 86400, 0.50), (T0 - 3600, 0.55), (T0 - 60, 0.60)]
    paths = {("g1", "moneyline", "home"): {
        "game_id": "g1", "market_type": "moneyline", "side": "home",
        "line": None, "commence": T0, "ticks": ticks}}
    rows = {r["horizon"]: r for r in st.drift_decomposition(paths)}
    assert rows["T-24h"]["mean_abs_move_pp"] == 10.0
    assert rows["T-24h"]["signed_continuation_pp"] == 10.0   # toward close dir
    assert rows["T-1h"]["mean_abs_move_pp"] == 5.0
    assert rows["T-1h"]["label"] == "UNDERPOWERED"            # n=1


def test_entry_clv_sign_and_left_on_table(tmp_path):
    ticks = [(T0 - 86400, 0.50), (T0 - 3600, 0.55), (T0 - 60, 0.60)]
    paths = {("e1", "moneyline", "home"): {
        "game_id": "e1", "market_type": "moneyline", "side": "home",
        "line": None, "commence": T0, "ticks": ticks}}
    from datetime import datetime, timezone
    entry_ts = datetime.fromtimestamp(T0 - 3600, tz=timezone.utc).isoformat()
    ledger = tmp_path / "led.jsonl"
    ledger.write_text(json.dumps({
        "ts": entry_ts, "sport": "x", "market_type": "moneyline", "side": "home",
        "event_id": "e1", "taken_book": "bk"}) + "\n", encoding="utf-8")
    out = st.entry_clv(paths, "x", ledger=ledger)
    assert out["n"] == 1
    assert out["label"] == "UNDERPOWERED"
    # entered at 0.55, close 0.60 -> beat close by +5pp; best grid prob 0.50
    assert abs(out["mean_clv_pp"] - 5.0) < 1e-9
    assert abs(out["mean_left_on_table_pp"] - 5.0) < 1e-9
    assert out["best_horizon_histogram"] == {"T-24h": 1}


def test_policy_tiers_and_defaults():
    drift_big = [{"horizon": "T-1h", "n": 500}]
    ll = {"horizons": [{"horizon": "T-1h", "n": 44,
                        "delta_model_minus_market": 0.01, "delta_ci95": [-0.01, 0.03]}],
          "horizons_model_beats_market": []}
    pol = derive_policy(drift_big, {"n": 0}, ll)
    assert pol["entry_horizon"] == "last_pregame_tick"
    assert pol["confidence"] == "HIGH" and pol["provisional"] is False
    pol2 = derive_policy([{"horizon": "T-1h", "n": 10}], None, None)
    assert pol2["confidence"] == "LOW" and pol2["provisional"] is True
    ll_beats = dict(ll, horizons_model_beats_market=["T-12h"])
    assert derive_policy(drift_big, None, ll_beats)["entry_horizon"] == "T-12h"
    assert nearest_horizon(11.0) == "T-12h"
    assert nearest_horizon(0.4) == "T-30m"
