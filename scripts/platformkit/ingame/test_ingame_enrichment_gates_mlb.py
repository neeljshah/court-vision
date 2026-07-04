"""Per-file tests for ingame_enrichment_gates_mlb (GATE B: MLB base-out
conditioning judge).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_enrichment_gates_mlb.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_enrichment_gates_mlb as gb


def _rows_better(n_games: int = 40, ticks_per_game: int = 10):
    rows = []
    for i in range(n_games):
        gid = "mlb_game_%d" % i
        y = 1.0 if i % 2 == 0 else 0.0
        for _t in range(ticks_per_game):
            rows.append({
                "game_id": gid, "y": y,
                "model_prob": 0.5,
                "model_prob_enriched": (0.9 if y == 1.0 else 0.1),
            })
    return rows


def test_default_rows_mlb_baseout_is_empty_and_never_raises():
    """No producer wires base_out-conditioned model_prob_enriched into a
    grade row yet -- honest [] until that lane lands."""
    rows = gb._default_rows_mlb_baseout()
    assert rows == []


def test_run_gate_b_writes_pending_when_no_rows(tmp_path):
    out = tmp_path / "verdict.json"
    doc = gb.run_gate_b(rows_fn=lambda: [], verdict_out=out)
    assert doc["verdict"] == "INSUFFICIENT_FORWARD"
    assert doc["n_games"] == 0
    assert doc["edge_claimed"] is False
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk["gate"] == "B_mlb_baseout"
    assert on_disk["sport"] == "mlb"
    assert on_disk["pre_registered_at"] == gb.GATE_B_PRE_REGISTERED_AT
    assert on_disk["edge_claimed"] is False


def test_run_gate_b_confirmed_with_synthetic_better_rows(tmp_path):
    out = tmp_path / "verdict.json"
    doc = gb.run_gate_b(rows_fn=_rows_better, verdict_out=out)
    assert doc["verdict"] == "BETTER_THAN_BASELINE"
    assert doc["n_games"] > 0


def test_run_gate_b_never_raises_on_bad_rows_fn(tmp_path):
    def bad_rows():
        raise RuntimeError("boom")
    out = tmp_path / "verdict.json"
    doc = gb.run_gate_b(rows_fn=bad_rows, verdict_out=out)
    assert doc["verdict"] == "INSUFFICIENT_FORWARD"
    assert doc["edge_claimed"] is False
