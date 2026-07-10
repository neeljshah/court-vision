"""Per-file test for knowledge.validate_ingame_state. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/knowledge/test_validate_ingame_state.py -q
"""
from __future__ import annotations

from domains.soccer.knowledge import validate_ingame_state as vis


def test_verdict_nan_p_is_not_testable_never_misclassified():
    """Failure mode: a NaN p-value (degenerate/empty comparison) must verdict
    NOT_TESTABLE, never get compared against ALPHA and silently pass/fail."""
    assert vis._verdict(float("nan"), 0.5, 0.05) == "NOT_TESTABLE"
    assert vis._verdict(0.001, 0.5, 0.05) == "CONFIRMED_LOCAL"
    assert vis._verdict(0.5, 0.5, 0.05) == "NULL_LOCAL"


def _facts():
    return {
        "teams": ["A", "B"], "match_len": 90.0,
        "shots": [("A", 10.0, False, "Open Play"), ("A", 50.0, True, "Open Play"),
                  ("B", 30.0, True, "Corner"), ("B", 70.0, False, "Open Play")],
        "goals": [(50.0, "A"), (30.0, "B")],
        "red_cards": [(40.0, "B")],
        "subs": {"A": 60.0, "B": 20.0},
    }


def test_accumulate_happy_path_populates_every_bucket():
    acc = {k: [] for k in ("redcard_before", "redcard_after", "leading_rate", "tied_rate",
                           "sub_before", "sub_after", "openplay_goal", "setpiece_goal")}
    vis._accumulate(_facts(), acc)
    assert len(acc["redcard_before"]) == 1 and len(acc["redcard_after"]) == 1
    assert len(acc["sub_before"]) == 2 and len(acc["sub_after"]) == 2
    assert len(acc["openplay_goal"]) == 3 and len(acc["setpiece_goal"]) == 1


def test_run_writes_four_edge_free_rows(tmp_path, monkeypatch):
    """Failure mode: run() iterates matches and accumulates in a shared dict
    -- a bad match file must not sink the whole ledger write. Wiring-only
    check: the 4 declared hypothesis rows land, edge-claim-free."""
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vis, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vis, "iter_all_event_files",
                        lambda: iter([("m1", []), ("m2", []), ("m3", [])]))
    monkeypatch.setattr(vis, "extract_match_facts", lambda events: _facts())
    rows = vis.run()
    assert len(rows) == 4
    assert all(r["edge_claimed"] is False and r["sport"] == "soccer" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 4
