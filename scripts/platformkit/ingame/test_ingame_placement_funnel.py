"""Per-file tests for ingame_placement_funnel -- pure/offline (synthetic decisions)."""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from scripts.platformkit.ingame import ingame_placement_funnel as F


def test_all_no_live_state_drops_at_live_state():
    decs = [{"action": None, "reason": "no_live_state"} for _ in range(48)]
    f = F.funnel_from_decisions(decs)
    assert f["stages"]["markets"] == 48
    assert f["stages"]["live_state"] == 0  # none cleared state
    assert f["n_bet"] == 0
    assert f["biggest_dropoff"] == "live_state"
    assert f["dropoff_count"] == 48


def test_mixed_funnel_counts_each_stage():
    decs = [
        {"action": None, "reason": "no_live_state"},   # dies at live_state
        {"action": None, "reason": "no_model_prob"},   # clears live_state, dies model
        {"action": None, "reason": "no_home_leg"},      # clears thru model
        {"action": None, "reason": "below_floor"},      # clears thru priced
        {"action": "bet", "reason": "ok", "tier": "B"}, # full placement
    ]
    f = F.funnel_from_decisions(decs)
    s = f["stages"]
    assert s["markets"] == 5
    assert s["live_state"] == 4   # all but the no_live_state one
    assert s["model_prob"] == 3
    assert s["home_leg"] == 2
    assert s["priced"] == 2       # below_floor cleared priced; the bet did too
    assert s["tier_floor"] == 1   # only the bet cleared the floor
    assert s["bet"] == 1
    assert f["n_bet"] == 1


def test_priced_stage_groups_illiquid_stale_badprice():
    for r in ("bad_price", "illiquid", "stale", "not_justified"):
        f = F.funnel_from_decisions([{"action": None, "reason": r}])
        s = f["stages"]
        # cleared live_state + model_prob + home_leg, fails AT priced
        assert s["home_leg"] == 1 and s["priced"] == 0, r


def test_empty_is_zero_not_error():
    f = F.funnel_from_decisions([])
    assert f["n_markets"] == 0 and f["n_bet"] == 0
    assert f["biggest_dropoff"] in F._STAGES


def test_build_doc_with_injected_poll():
    def _poll(*, sports=()):
        return {"n_live": 2, "as_of": "2026-06-29T23:30:00Z",
                "games": [{"action": None, "reason": "no_live_state"},
                          {"action": "bet", "reason": "ok"}]}
    doc = F.build_doc(("mlb",), poll_fn=_poll)
    assert doc["n_live"] == 2
    assert doc["stages"]["markets"] == 2
    assert doc["n_bet"] == 1
    assert "edge" in doc["note"].lower()


def test_write_doc_atomic(tmp_path):
    doc = F.build_doc(("mlb",), poll_fn=lambda *, sports=(): {"games": []})
    p = tmp_path / "f.json"
    F.write_doc(doc, p)
    back = json.loads(p.read_text(encoding="ascii"))
    assert "stages" in back
    assert not (tmp_path / "f.json.tmp").exists()


def test_run_max_ticks_and_survives_error(tmp_path):
    calls = {"n": 0}

    def _poll(*, sports=()):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("dead poll")  # one bad tick must not stop the loop
        return {"n_live": 1, "games": [{"action": "bet", "reason": "ok"}]}

    n = F.run(interval_sec=0.0, poll_fn=_poll, path=tmp_path / "f.json",
              sleep=lambda _s: None, max_ticks=3)
    assert n == 3
    assert (tmp_path / "f.json").exists()


def test_render_handles_empty_slate():
    doc = F.build_doc(("mlb",), poll_fn=lambda *, sports=(): {"games": [], "n_live": 0})
    out = F.render(doc)
    assert "0 in-game bets is CORRECT" in out
