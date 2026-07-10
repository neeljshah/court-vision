"""Per-file test for scripts.platformkit.interaction_factory.replicate_tennis_knowledge_2026.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/interaction_factory/test_replicate_tennis_knowledge_2026.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from scripts.platformkit.interaction_factory import replicate_tennis_knowledge_2026 as REPL


def _ledger_rows():
    return [
        {"candidate_id": "tennis_match_asof_self_cross::avg_games_per_set_asof_diff__x__diff_break_pct_asof::src=knowledge",
         "template_id": "tennis_match_asof_self_cross", "hypothesis_source": "knowledge",
         "verdict": "SURVIVES_PREREG_PROVISIONAL",
         "attr_a": "avg_games_per_set_asof_diff", "attr_b": "diff_break_pct_asof",
         "effect": -0.047896, "p": 0.0, "n": 29155},
        {"candidate_id": "tennis_match_asof_self_cross::avg_games_per_set_asof_diff__x__diff_return_won_asof::src=knowledge",
         "template_id": "tennis_match_asof_self_cross", "hypothesis_source": "knowledge",
         "verdict": "SURVIVES_PREREG_PROVISIONAL",
         "attr_a": "avg_games_per_set_asof_diff", "attr_b": "diff_return_won_asof",
         "effect": -0.040784, "p": 2e-06, "n": 29153},
        # An unrelated blind-search survivor -- must NEVER be picked up here.
        {"candidate_id": "tennis_match_asof_self_cross::diff_2nd_win_asof__x__diff_break_pct_asof",
         "template_id": "tennis_match_asof_self_cross", "hypothesis_source": "blind",
         "verdict": "SURVIVES_PREREG_PROVISIONAL",
         "attr_a": "diff_2nd_win_asof", "attr_b": "diff_break_pct_asof",
         "effect": 0.046411, "p": 0.002354, "n": 29179},
    ]


def test_knowledge_survivors_filters_to_knowledge_source_only():
    rows = REPL._knowledge_survivors(_ledger_rows())
    assert len(rows) == 2
    assert all(r["hypothesis_source"] == "knowledge" for r in rows)


def test_knowledge_survivors_skips_already_replicated_candidates():
    rows = _ledger_rows()
    rows.append({
        "candidate_id": "tennis_match_asof_self_cross::avg_games_per_set_asof_diff__x__diff_break_pct_asof::src=knowledge",
        "template_id": "tennis_match_asof_self_cross", "verdict": "REPLICATED",
        "replication_of": "tennis_match_asof_self_cross::avg_games_per_set_asof_diff__x__diff_break_pct_asof::src=knowledge",
    })
    out = REPL._knowledge_survivors(rows)
    assert len(out) == 1
    assert out[0]["attr_b"] == "diff_return_won_asof"


def test_replicate_appends_one_row_per_survivor(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    with open(ledger, "w", encoding="ascii") as f:
        for r in _ledger_rows():
            f.write(json.dumps(r) + "\n")

    fake_frame = pd.DataFrame({
        "y": [float(i % 2) for i in range(400)],
        "asof__avg_games_per_set_asof_diff": [((i * 37) % 97) / 97.0 - 0.5 for i in range(400)],
        "asof__diff_break_pct_asof": [((i * 53) % 89) / 89.0 - 0.5 for i in range(400)],
        "asof__diff_return_won_asof": [((i * 61) % 83) / 83.0 - 0.5 for i in range(400)],
        "tourney_id": (["t1", "t2", "t3", "t4", "t5", "t6"] * 100)[:400],
    })
    monkeypatch.setattr(REPL, "_build_2026_frame", lambda attrs: fake_frame)
    monkeypatch.setattr(REPL, "_upsert_verdicts", lambda v: None)
    monkeypatch.setattr(REPL, "_queue_promotion", lambda row, b0: None)

    out = REPL.replicate(ledger_path=ledger)
    assert len(out) == 2
    for row in out:
        assert row["verdict"] in ("REPLICATED", "FAILED_REPLICATION_POWER_ANNOTATED", "KILLED", "STILL_BLOCKED")
        assert row["k_declared"] == 2
        assert row["replication_of"].endswith("::src=knowledge")

    # A second run must be a no-op: both candidates are now already replicated.
    out2 = REPL.replicate(ledger_path=ledger)
    assert out2 == []


def test_still_blocked_when_fit_returns_none(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    with open(ledger, "w", encoding="ascii") as f:
        for r in _ledger_rows():
            f.write(json.dumps(r) + "\n")

    monkeypatch.setattr(REPL, "_build_2026_frame", lambda attrs: pd.DataFrame({
        "y": [], "asof__avg_games_per_set_asof_diff": [], "asof__diff_break_pct_asof": [],
        "asof__diff_return_won_asof": [], "tourney_id": [],
    }))
    monkeypatch.setattr(REPL, "_upsert_verdicts", lambda v: None)
    monkeypatch.setattr(REPL, "_queue_promotion", lambda row, b0: None)

    out = REPL.replicate(ledger_path=ledger)
    assert len(out) == 2
    for row in out:
        assert row["verdict"] == "STILL_BLOCKED"
        assert row["effect"] is None and row["n"] == 0
