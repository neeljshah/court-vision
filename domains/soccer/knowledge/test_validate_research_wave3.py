"""Per-file test for knowledge.validate_research_wave3. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/knowledge/test_validate_research_wave3.py -q
"""
from __future__ import annotations

from domains.soccer.knowledge import validate_research_wave3 as vw3


def test_verdict_nan_p_is_not_testable_never_misclassified():
    """Failure mode: a NaN p-value (degenerate/empty comparison) must verdict
    NOT_TESTABLE, never get compared against ALPHA and silently pass/fail."""
    assert vw3._verdict(float("nan"), 0.5, 0.03) == "NOT_TESTABLE"
    assert vw3._verdict(0.001, 0.5, 0.03) == "CONFIRMED_LOCAL"
    assert vw3._verdict(0.5, 0.5, 0.03) == "NULL_LOCAL"
    assert vw3._verdict(0.001, 0.01, 0.03) == "NULL_LOCAL"  # significant but below effect bar


def _shot(team, poss, xg, is_goal, play_pattern="Regular Play", loc=(60.0, 40.0)):
    return {
        "type": {"name": "Shot"}, "team": {"name": team}, "possession": poss,
        "play_pattern": {"name": play_pattern}, "location": list(loc),
        "shot": {"statsbomb_xg": xg, "outcome": {"name": "Goal" if is_goal else "Saved"}},
    }


def _def_action(team, loc):
    return {"type": {"name": "Pressure"}, "team": {"name": team}, "location": list(loc)}


def _events():
    return [
        # team A: possession 1 = a 2-shot rebound cluster (no goal) -> cluster gap = 0.6-0=0.6
        _shot("A", 1, 0.4, False), _shot("A", 1, 0.2, False),
        # team A: possession 2 = single shot, goal -> single gap = 0.5-1=-0.5
        _shot("A", 2, 0.5, True),
        # team A: possession 3 = counterattack single shot, no goal -> single gap = 0.1-0=0.1
        _shot("A", 3, 0.1, False, play_pattern="From Counter"),
        # team B: single shot each, tied gaps
        _shot("B", 4, 0.3, False), _shot("B", 5, 0.2, True),
        # defensive actions for the block-depth proxy (team A presses high -> small proxy gap)
        _def_action("A", (70.0, 40.0)), _def_action("B", (30.0, 40.0)),
    ]


def test_match_clusters_splits_2plus_shot_possessions_from_singles():
    cluster_gaps, single_gaps = vw3._match_clusters(_events())
    assert len(cluster_gaps) == 1  # team A possession 1 (2 shots)
    assert abs(cluster_gaps[0] - 0.6) < 1e-9
    assert len(single_gaps) == 4  # A poss 2, A poss 3, B poss 4, B poss 5


def test_counter_share_counts_from_counter_tag_only():
    counts = vw3._counter_share(_events())
    assert counts["A"] == (1, 4)  # 1 of 4 team-A shots tagged From Counter
    assert counts["B"] == (0, 2)


def test_accumulate_wires_both_hypotheses_from_one_event_pass():
    acc = {k: [] for k in ("cluster_gap", "single_gap", "block_proxy", "counter_share")}
    vw3._accumulate(_events(), acc)
    assert len(acc["cluster_gap"]) == 1
    assert len(acc["single_gap"]) == 4
    assert len(acc["block_proxy"]) == 2  # both teams have def+shot actions
    assert len(acc["counter_share"]) == 2


def test_run_writes_two_edge_free_rows(tmp_path, monkeypatch):
    """Failure mode: run() iterates matches and accumulates in a shared dict
    -- a bad match file must not sink the whole ledger write. Wiring-only
    check: the 2 declared hypothesis rows land, edge-claim-free."""
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vw3, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vw3, "iter_all_event_files",
                         lambda: iter([("m1", _events()), ("m2", _events()), ("m3", _events())]))
    rows = vw3.run()
    assert len(rows) == 2
    assert all(r["edge_claimed"] is False and r["sport"] == "soccer" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 2


def test_run_split_half_writes_four_rows_two_per_half(tmp_path, monkeypatch):
    """Failure mode: an even/odd split that silently drops one half would
    leave an affirmative verdict backed by only one group. Wiring-only check:
    both hypotheses land twice (once per half=A/B), edge-claim-free."""
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vw3, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vw3, "iter_all_event_files",
                         lambda: iter([("m1", _events()), ("m2", _events()),
                                       ("m3", _events()), ("m4", _events())]))
    rows = vw3.run_split_half()
    assert len(rows) == 4
    assert {r["hypothesis"] for r in rows} == {
        "xg_rebound_cluster_calibration__split_A", "xg_rebound_cluster_calibration__split_B",
        "block_depth_counterattack_share__split_A", "block_depth_counterattack_share__split_B"}
    assert all(r["edge_claimed"] is False for r in rows)
