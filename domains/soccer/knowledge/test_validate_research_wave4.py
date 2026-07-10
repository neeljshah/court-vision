"""Per-file test for knowledge.validate_research_wave4. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/knowledge/test_validate_research_wave4.py -q
"""
from __future__ import annotations

from domains.soccer.knowledge import validate_research_wave4 as vw4


def test_verdict_nan_p_is_not_testable_never_misclassified():
    """Failure mode: a NaN p-value (fewer than 5 common teams) must verdict
    NOT_TESTABLE, never get compared against ALPHA and silently pass/fail."""
    assert vw4._verdict(float("nan"), 0.5) == "NOT_TESTABLE"
    assert vw4._verdict(0.001, 0.5) == "CONFIRMED_LOCAL"
    assert vw4._verdict(0.5, 0.5) == "NULL_LOCAL"
    assert vw4._verdict(0.001, 0.05) == "NULL_LOCAL"  # significant but below effect bar


def _shot(team, xg, shot_type="Corner"):
    return {"type": {"name": "Shot"}, "team": {"name": team},
            "shot": {"statsbomb_xg": xg, "type": {"name": shot_type}}}


def test_setpiece_xg_by_team_filters_to_corner_and_free_kick_only():
    events = [_shot("A", 0.1, "Corner"), _shot("A", 0.2, "Free Kick"),
              _shot("A", 0.9, "Open Play"), _shot("B", 0.3, "Corner")]
    out = vw4._setpiece_xg_by_team(events)
    assert out["A"] == [0.1, 0.2]  # Open Play excluded
    assert out["B"] == [0.3]


def test_persistence_requires_min_shots_per_half_in_both_halves():
    """Failure mode: a team with plenty of shots in half A but under the
    floor in half B must NOT be counted -- would silently overweight sparse
    teams. min-n floor mirrors #5/#35's split-half designs (>=10/half)."""
    half_a = {"A": [0.1] * 12, "B": [0.2] * 3}  # B under floor in half A
    half_b = {"A": [0.15] * 12, "B": [0.25] * 12}
    r, p, n = vw4._persistence(half_a, half_b)
    assert n == 1  # only team A clears the floor in BOTH halves


def test_persistence_returns_nan_below_five_common_teams():
    half_a = {"A": [0.1] * 12, "B": [0.2] * 12}
    half_b = {"A": [0.15] * 12}  # B missing from half_b -> only 1 common team
    r, p, n = vw4._persistence(half_a, half_b)
    assert p != p  # NaN
    assert n == 1


def test_run_writes_two_edge_free_rows(tmp_path, monkeypatch):
    """Wiring-only check: both split methods (date, index) land as separate
    rows, edge-claim-free, without touching the real StatsBomb corpus."""
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vw4, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vw4, "setpiece_xg_persistence_by_date",
                         lambda: vw4._row("setpiece_xg_persistence__by_date", 0,
                                           float("nan"), float("nan"), "stub"))
    monkeypatch.setattr(vw4, "setpiece_xg_persistence_by_index",
                         lambda: vw4._row("setpiece_xg_persistence__by_index", 0,
                                           float("nan"), float("nan"), "stub"))
    rows = vw4.run()
    assert len(rows) == 2
    assert {r["hypothesis"] for r in rows} == {
        "setpiece_xg_persistence__by_date", "setpiece_xg_persistence__by_index"}
    assert all(r["edge_claimed"] is False and r["sport"] == "soccer" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 2
