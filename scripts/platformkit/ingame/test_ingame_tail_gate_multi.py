"""Per-file tests for ingame_tail_gate_multi (pre-registered forward-only judging).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_tail_gate_multi.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_tail_gate_multi as gm


def _band(verdict, n_games=30):
    return {"venue_verdict": verdict, "n_games": n_games, "n_ticks": n_games * 5}


def test_confirmed_forward_ships_review(tmp_path):
    def scan_fn(since=None):
        if since is None:
            return {"bands": {}, "n_games_resolved": 0, "n_games_graded": 0}
        return {
            "bands": {"[0.10,0.20)": _band("VENUE_UNDERPRICES"),
                     "[0.65,0.80)": _band("CALIBRATED")},
            "n_games_resolved": 40, "n_games_graded": 40,
        }
    out = tmp_path / "verdict.json"
    headline = gm.run_gate_for_sport("soccer_intl", scan_fn=scan_fn, verdict_out=out)
    assert headline["verdict"] == "SHIP_REVIEW"
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["edge_claimed"] is False
    assert doc["hypotheses"][0]["forward_verdict"] == "CONFIRMED_FORWARD"


def test_all_rejected_forward_rejects(tmp_path):
    def scan_fn(since=None):
        if since is None:
            return {"bands": {}, "n_games_resolved": 0, "n_games_graded": 0}
        return {
            "bands": {"[0.10,0.20)": _band("VENUE_OVERPRICES"),
                     "[0.65,0.80)": _band("VENUE_UNDERPRICES")},
            "n_games_resolved": 40, "n_games_graded": 40,
        }
    out = tmp_path / "verdict.json"
    headline = gm.run_gate_for_sport("soccer_intl", scan_fn=scan_fn, verdict_out=out)
    assert headline["verdict"] == "REJECT"


def test_no_forward_games_pending(tmp_path):
    def scan_fn(since=None):
        return {"bands": {}, "n_games_resolved": 0, "n_games_graded": 0}
    out = tmp_path / "verdict.json"
    headline = gm.run_gate_for_sport("tennis", scan_fn=scan_fn, verdict_out=out)
    assert headline["verdict"] == "PENDING_FORWARD"
    assert headline["n"] == 0


def test_pre_registration_never_scores_discovery_sample(tmp_path):
    """A game before the pre-registration stamp must NEVER appear in the
    forward scan's bands (enforced by ingame_tail_scan_multi's since filter --
    here we simulate the scan_fn honoring 'since' by returning EMPTY forward
    bands even though discovery has a confirmable signal)."""
    calls = []

    def scan_fn(since=None):
        calls.append(since)
        if since is None:
            return {"bands": {"[0.10,0.20)": _band("VENUE_UNDERPRICES")},
                    "n_games_resolved": 50, "n_games_graded": 50}
        # forward (since=pre_registered_at): nothing captured yet
        return {"bands": {}, "n_games_resolved": 0, "n_games_graded": 0}

    out = tmp_path / "verdict.json"
    headline = gm.run_gate_for_sport("tennis", scan_fn=scan_fn, verdict_out=out)
    assert headline["verdict"] == "PENDING_FORWARD"
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["hypotheses"][0]["forward_verdict"] == "INSUFFICIENT_FORWARD"
    assert doc["hypotheses"][0]["discovery_band_reference_only"]["venue_verdict"] == \
        "VENUE_UNDERPRICES"
    # both a discovery (since=None) and a forward (since=stamp) call were made
    assert None in calls and gm.PRE_REGISTERED_AT in calls


def test_run_gate_all_never_raises(monkeypatch):
    def _boom(sport, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(gm, "scan_sport", _boom)
    # run_gate_for_sport wraps scan_sport calls in try/except internally via
    # the default scan_fn lambda, so a raising scan_sport must not propagate.
    headlines = gm.run_gate_all(sports=["tennis"])
    assert headlines[0]["verdict"] == "PENDING_FORWARD"
