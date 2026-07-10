"""Per-file test for knowledge.validate_ppda_shot_quality. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/knowledge/test_validate_ppda_shot_quality.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.soccer.knowledge import validate_ppda_shot_quality as vps


def _ev(team, etype, period, xg=None):
    e = {"team": {"name": team}, "type": {"name": etype}, "period": period}
    if etype == "Shot":
        e["shot"] = {"statsbomb_xg": xg}
    return e


def _synthetic_match(n_opp_passes_h1=30, n_def_actions_h1=5, n_opp_shots_h2=4, opp_xg_h2=0.4):
    events = []
    # team A presses in half 1, team B builds up
    events += [_ev("B", "Pass", 1) for _ in range(n_opp_passes_h1)]
    events += [_ev("A", "Pressure", 1) for _ in range(n_def_actions_h1)]
    # symmetric so team B also gets a row (A's passes / B's def actions)
    events += [_ev("A", "Pass", 1) for _ in range(n_opp_passes_h1)]
    events += [_ev("B", "Pressure", 1) for _ in range(n_def_actions_h1)]
    # half 2: B takes shots (conceded by A)
    events += [_ev("B", "Shot", 2, xg=opp_xg_h2 / n_opp_shots_h2) for _ in range(n_opp_shots_h2)]
    events += [_ev("A", "Shot", 2, xg=opp_xg_h2 / n_opp_shots_h2) for _ in range(n_opp_shots_h2)]
    return events


def test_match_rows_computes_forward_ppda_and_conceded_xg_per_shot():
    rows = vps.match_rows(_synthetic_match())
    assert len(rows) == 2  # one row per team
    for ppda, xg_per_shot in rows:
        assert ppda == 30 / 5
        assert abs(xg_per_shot - 0.1) < 1e-9


def test_match_rows_skips_below_threshold_or_zero_shots():
    rows = vps.match_rows(_synthetic_match(n_opp_passes_h1=5))  # below MIN passes=20
    assert rows == []


def test_match_rows_skips_matches_without_exactly_two_teams():
    events = [_ev("A", "Pass", 1)]
    assert vps.match_rows(events) == []


def test_corpus_test_not_testable_when_below_min_n():
    r = vps._corpus_test([(1.0, 0.1)] * 5, "A")
    assert r["verdict"] == "NOT_TESTABLE" and r["p"] is None


def test_combine_confirms_only_with_two_same_direction_significant_corpora():
    rows = [
        {"verdict": "CONFIRMED_LOCAL", "p": 0.001, "effect": 0.2, "n": 100},
        {"verdict": "CONFIRMED_LOCAL", "p": 0.002, "effect": 0.15, "n": 100},
    ]
    assert vps._combine(rows)["verdict"] == "CONFIRMED_LOCAL"


def test_combine_never_confirms_on_opposite_sign_significant_corpora():
    """Failure mode this guards: two significant but opposite-sign corpora
    must never be mislabeled CONFIRMED -- that would be masking a sign flip,
    not real cross-competition-group replication."""
    rows = [
        {"verdict": "CONFIRMED_LOCAL", "p": 0.001, "effect": 0.2, "n": 100},
        {"verdict": "CONFIRMED_LOCAL", "p": 0.002, "effect": -0.15, "n": 100},
    ]
    assert vps._combine(rows)["verdict"] == "NULL_LOCAL"


def test_run_writes_three_edge_free_rows(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vps, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vps, "load_match_meta",
                         lambda: pd.DataFrame({"corpus": ["A", "B"], "match_id": [1, 2]}))
    monkeypatch.setattr(vps, "load_events", lambda mid: _synthetic_match())
    rows = vps.run()
    assert len(rows) == 3  # 2 corpora + 1 combined
    assert all(r["edge_claimed"] is False and r["sport"] == "soccer" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 3
