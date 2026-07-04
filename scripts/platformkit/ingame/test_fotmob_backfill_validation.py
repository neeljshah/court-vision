"""Per-file tests for fotmob_backfill_validation (LANE 2 item 3: GATE A's
judge run on the backfill-validation corpus, writing a SEPARATE verdict file).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_fotmob_backfill_validation.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import fotmob_backfill_validation as V
from scripts.platformkit.ingame import ingame_enrichment_gates as gate


def _rows(n_games=10, per_game=12, better=False):
    """Synthetic rows shaped like enrichment_rows_soccer.build_rows output,
    all tagged provenance='backfill_validation'."""
    rows = []
    for g in range(n_games):
        y = 1.0 if g % 2 == 0 else 0.0
        for _ in range(per_game):
            mp = 0.5
            ep = (0.5 + 0.3 * (1 if y == 1.0 else -1)) if better else 0.5
            rows.append({"game_id": "game%d" % g, "model_prob": mp,
                        "model_prob_enriched": ep, "y": y,
                        "provenance": "backfill_validation"})
    return rows


def test_run_backfill_validation_writes_separate_file(tmp_path):
    out_path = tmp_path / "enrichment_gate_validation.json"
    doc = V.run_backfill_validation(rows_fn=lambda: _rows(), verdict_out=out_path)
    assert out_path.is_file()
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk["verdict"] == doc["verdict"]
    assert doc["gate"] == "A_soccer_xg_VALIDATION"
    assert doc["provenance"] == "backfill_validation"


def test_run_backfill_validation_never_touches_forward_verdict_filename(tmp_path):
    """The validation output path must NEVER be named enrichment_gate_verdict.json
    (the forward file) -- guards against an accidental path collision."""
    default_path = V._validation_out()
    assert default_path.name == "enrichment_gate_validation.json"
    assert default_path.name != "enrichment_gate_verdict.json"


def test_run_backfill_validation_insufficient_below_min_games(tmp_path):
    out_path = tmp_path / "val.json"
    doc = V.run_backfill_validation(rows_fn=lambda: _rows(n_games=2), verdict_out=out_path)
    assert doc["verdict"] == "INSUFFICIENT_FORWARD"
    assert doc["n_games"] == 2


def test_run_backfill_validation_honesty_fields_present(tmp_path):
    out_path = tmp_path / "val.json"
    doc = V.run_backfill_validation(rows_fn=lambda: _rows(), verdict_out=out_path)
    assert doc["edge_claimed"] is False
    assert "reconstructed" in doc["honest_note"].lower()
    assert "fixed-form" in doc["honest_note"].lower()
    assert "VALIDATION" in doc["hypothesis"] or "validation" in doc["hypothesis"].lower()


def test_run_backfill_validation_drops_non_backfill_provenance_rows(tmp_path):
    """A row that is NOT tagged backfill_validation must never enter this
    validation judge -- guards against accidental pooling with a live row."""
    rows = _rows(n_games=10)
    rows.append({"game_id": "poison", "model_prob": 0.5, "model_prob_enriched": 0.9,
                "y": 1.0, "provenance": "live"})
    out_path = tmp_path / "val.json"
    doc = V.run_backfill_validation(rows_fn=lambda: rows, verdict_out=out_path)
    assert "poison" not in json.dumps(doc)


def test_run_backfill_validation_producer_exception_is_honest_insufficient(tmp_path):
    def boom():
        raise RuntimeError("producer broke")

    out_path = tmp_path / "val.json"
    doc = V.run_backfill_validation(rows_fn=boom, verdict_out=out_path)
    assert doc["verdict"] == "INSUFFICIENT_FORWARD"
    assert doc["n_games"] == 0


def test_run_backfill_validation_never_raises_with_real_default_rows_fn(tmp_path):
    """Exercises the real default rows_fn wiring (enrichment_rows_soccer.
    rows_fn_backfill) against whatever real data currently exists on disk --
    must never raise, output path redirected to tmp_path."""
    out_path = tmp_path / "val.json"
    doc = V.run_backfill_validation(verdict_out=out_path)
    assert isinstance(doc, dict)
    assert "verdict" in doc


def test_judge_enrichment_shared_core_matches_forward_gate_shape(tmp_path):
    """The validation doc's half0/half1 shape matches judge_enrichment's
    contract exactly (shared core with the forward gate, per module docstring)."""
    doc = V.run_backfill_validation(rows_fn=lambda: _rows(), verdict_out=tmp_path / "val.json")
    for half_key in ("half0", "half1"):
        half = doc[half_key]
        assert half is not None
        for key in ("verdict", "n_games", "total_ticks", "brier_baseline",
                    "brier_enriched", "brier_delta", "delta_ci95"):
            assert key in half
