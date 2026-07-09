"""Per-file test for scripts.platformkit.interaction_factory.replicate_tennis_2026.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/interaction_factory/test_replicate_tennis_2026.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from scripts.platformkit.interaction_factory import replicate_tennis_2026 as REPL


def _ledger_rows():
    return [
        {"candidate_id": "tennis_match_asof_self_cross::diff_1st_in_asof__x__diff_ace_rate_asof",
         "template_id": "tennis_match_asof_self_cross", "verdict": "SURVIVES_PREREG_PROVISIONAL",
         "attr_a": "diff_1st_in_asof", "attr_b": "diff_ace_rate_asof",
         "effect": -0.0261, "p": 0.0113, "n": 29181},
        {"candidate_id": "tennis_match_asof_self_cross::diff_1st_in_asof__x__diff_ace_rate_asof",
         "template_id": "tennis_match_asof_self_cross", "verdict": "REPLICATION_BLOCKED",
         "attr_a": "diff_1st_in_asof", "attr_b": "diff_ace_rate_asof",
         "corpus": "unbuildable", "effect": None, "n": 0,
         "replication_of": "tennis_match_asof_self_cross::diff_1st_in_asof__x__diff_ace_rate_asof"},
    ]


def test_tennis_blocked_rows_picks_the_latest_unbuildable_row():
    blocked = REPL._tennis_blocked_rows(_ledger_rows())
    assert len(blocked) == 1
    assert blocked[0]["verdict"] == "REPLICATION_BLOCKED"


def test_by_id_lookup_uses_discovery_row_not_the_blocked_row(tmp_path, monkeypatch):
    """Regression: an earlier version keyed by_id off the LAST row seen per
    candidate_id, which picked up the REPLICATION_BLOCKED row (effect=None) and
    crashed verdict_for's `> 0` comparison. by_id must resolve to the ORIGINAL
    SURVIVES_PREREG_PROVISIONAL row."""
    ledger = tmp_path / "ledger.jsonl"
    with open(ledger, "w", encoding="ascii") as f:
        for r in _ledger_rows():
            f.write(json.dumps(r) + "\n")

    fake_frame = pd.DataFrame({
        "y": [float(i % 2) for i in range(400)],
        "asof__diff_1st_in_asof": [((i * 37) % 97) / 97.0 for i in range(400)],
        "asof__diff_ace_rate_asof": [((i * 53) % 89) / 89.0 for i in range(400)],
        "tourney_id": (["t1", "t2", "t3", "t4", "t5", "t6"] * 100)[:400],
    })
    monkeypatch.setattr(REPL, "_build_2026_frame", lambda attrs: fake_frame)
    monkeypatch.setattr(REPL, "_upsert_verdicts", lambda v: None)
    monkeypatch.setattr(REPL, "_queue_promotion", lambda row, b0: None)

    out = REPL.replicate(ledger_path=ledger)
    assert len(out) == 1
    assert out[0]["discovery_effect"] == -0.0261  # from the SURVIVES row, not None
    assert out[0]["verdict"] in ("REPLICATED", "FAILED_REPLICATION_POWER_ANNOTATED", "KILLED", "STILL_BLOCKED")


def test_still_blocked_when_fit_returns_none(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    with open(ledger, "w", encoding="ascii") as f:
        for r in _ledger_rows():
            f.write(json.dumps(r) + "\n")

    monkeypatch.setattr(REPL, "_build_2026_frame", lambda attrs: pd.DataFrame({
        "y": [], "asof__diff_1st_in_asof": [], "asof__diff_ace_rate_asof": [], "tourney_id": [],
    }))
    monkeypatch.setattr(REPL, "_upsert_verdicts", lambda v: None)
    monkeypatch.setattr(REPL, "_queue_promotion", lambda row, b0: None)

    out = REPL.replicate(ledger_path=ledger)
    assert len(out) == 1
    assert out[0]["verdict"] == "STILL_BLOCKED"
    assert out[0]["effect"] is None and out[0]["n"] == 0
