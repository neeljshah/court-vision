"""Per-file test for knowledge.validate_research_wave2. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/knowledge/test_validate_research_wave2.py -q
"""
from __future__ import annotations

from domains.soccer.knowledge import validate_research_wave2 as vw2


def test_verdict_nan_p_is_not_testable_never_misclassified():
    """Failure mode: a NaN p-value (degenerate/empty comparison) must verdict
    NOT_TESTABLE, never get compared against ALPHA and silently pass/fail."""
    assert vw2._verdict(float("nan"), 0.5) == "NOT_TESTABLE"
    assert vw2._verdict(0.001, 0.5) == "CONFIRMED_LOCAL"
    assert vw2._verdict(0.5, 0.5) == "NULL_LOCAL"


def _facts():
    return {
        "teams": ["A", "B"], "match_len": 90.0,
        "shots": [("A", 5.0, False, "Open Play"), ("A", 55.0, True, "Open Play"),
                  ("A", 65.0, False, "Open Play"), ("B", 20.0, True, "Corner"),
                  ("B", 82.0, False, "Open Play")],
        "goals": [(20.0, "B")],
        "red_cards": [],
        # team A subs early (sub_t=50<=60), team B subs late (sub_t=80>=75)
        "subs": {"A": 50.0, "B": 80.0},
    }


def test_accumulate_buckets_early_late_subs_and_trailing_state():
    acc = {k: [] for k in ("early_shift", "late_shift", "trailing_rate", "tied_rate")}
    vw2._accumulate(_facts(), acc)
    assert len(acc["early_shift"]) == 1  # team A, sub_t=50<=60
    assert len(acc["late_shift"]) == 1  # team B, sub_t=80>=75, w_after=min(15,10)=10>=10
    # team A trails 0-20 (B up 1-0), tied nowhere after until match end wait:
    # A: diff_x = -1 for [0,20) (A trailing), 0 for [20,90) (tied) -> only trailing>=5, tied dur=70>=5
    assert len(acc["trailing_rate"]) == 1
    assert len(acc["tied_rate"]) == 1


def test_run_writes_two_edge_free_rows(tmp_path, monkeypatch):
    """Failure mode: run() iterates matches and accumulates in a shared dict
    -- a bad match file must not sink the whole ledger write. Wiring-only
    check: the 2 declared hypothesis rows land, edge-claim-free."""
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vw2, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vw2, "iter_all_event_files",
                        lambda: iter([("m1", []), ("m2", []), ("m3", [])]))
    monkeypatch.setattr(vw2, "extract_match_facts", lambda events: _facts())
    rows = vw2.run()
    assert len(rows) == 2
    assert all(r["edge_claimed"] is False and r["sport"] == "soccer" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 2


def test_run_split_half_writes_four_rows_two_per_half(tmp_path, monkeypatch):
    """Failure mode: an even/odd split that silently drops one half would
    leave an affirmative verdict backed by only one group. Wiring-only check:
    both hypotheses land twice (once per half=A/B), edge-claim-free."""
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vw2, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vw2, "iter_all_event_files",
                        lambda: iter([("m1", []), ("m2", []), ("m3", []), ("m4", [])]))
    monkeypatch.setattr(vw2, "extract_match_facts", lambda events: _facts())
    rows = vw2.run_split_half()
    assert len(rows) == 4
    assert {r["hypothesis"] for r in rows} == {
        "substitution_timing_moderates_shift__split_A", "substitution_timing_moderates_shift__split_B",
        "trailing_team_shot_rate__split_A", "trailing_team_shot_rate__split_B"}
    assert all(r["edge_claimed"] is False for r in rows)
