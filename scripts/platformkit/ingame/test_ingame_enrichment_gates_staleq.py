"""Per-file tests for ingame_enrichment_gates_staleq (GATE C: stale-quote
covariate scoreboard spec).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_enrichment_gates_staleq.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_enrichment_gates_staleq as gc


def test_default_rows_stale_quote_is_empty_and_never_raises():
    rows = gc._default_rows_stale_quote()
    assert rows == []


def test_run_gate_c_always_pending(tmp_path):
    """GATE C is a scoreboard comparison, not a SHIP/REJECT gate -- verdict
    is ALWAYS 'PENDING' regardless of row content (see module docstring)."""
    out = tmp_path / "verdict.json"
    doc = gc.run_gate_c(rows_fn=lambda: [], verdict_out=out)
    assert doc["verdict"] == "PENDING"
    assert doc["n_rows"] == 0
    assert doc["edge_claimed"] is False
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk["gate"] == "C_stale_quote_covariate"
    assert on_disk["pre_registered_at"] == gc.GATE_C_PRE_REGISTERED_AT
    assert on_disk["edge_claimed"] is False


def test_scoreboard_rows_pairs_matching_sport_segment():
    raw = {"mlb": {"I1": "BETTER_THAN_VENUE", "I2": "MATCH"}}
    depth = {"mlb": {"I1": "MATCH", "I2": "MATCH"}}
    rows = gc.scoreboard_rows(raw, depth)
    assert len(rows) == 2
    i1 = next(r for r in rows if r["segment"] == "I1")
    assert i1["agree"] is False
    assert i1["flip"] == "BETTER_THAN_VENUE->MATCH"
    i2 = next(r for r in rows if r["segment"] == "I2")
    assert i2["agree"] is True
    assert i2["flip"] is None


def test_scoreboard_rows_skips_segment_absent_from_depth_side():
    raw = {"mlb": {"I1": "MATCH", "I3": "WORSE_THAN_VENUE"}}
    depth = {"mlb": {"I1": "MATCH"}}  # I3 not yet depth-enriched
    rows = gc.scoreboard_rows(raw, depth)
    assert len(rows) == 1
    assert rows[0]["segment"] == "I1"


def test_run_gate_c_with_rows_still_pending_but_counts_disagreements(tmp_path):
    def rows_fn():
        return gc.scoreboard_rows(
            {"mlb": {"I1": "BETTER_THAN_VENUE"}},
            {"mlb": {"I1": "MATCH"}},
        )
    out = tmp_path / "verdict.json"
    doc = gc.run_gate_c(rows_fn=rows_fn, verdict_out=out)
    assert doc["verdict"] == "PENDING"  # never anything but PENDING (measurement-only)
    assert doc["n_rows"] == 1
    assert doc["n_disagree"] == 1


def test_run_gate_c_never_raises_on_bad_rows_fn(tmp_path):
    def bad_rows():
        raise RuntimeError("boom")
    out = tmp_path / "verdict.json"
    doc = gc.run_gate_c(rows_fn=bad_rows, verdict_out=out)
    assert doc["verdict"] == "PENDING"
    assert doc["n_rows"] == 0
