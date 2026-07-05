"""Per-file tests for claims_validator's write_summary() numpy-safety.

Regression coverage for the honest catch: a MISMATCH first_divergence block
can carry a raw numpy scalar (e.g. recomputed_id straight off an int64
entity_key column) and write_summary()'s json.dump used to crash TypeError
persisting it. Fixed via a numpy-safe default= encoder at the json.dump site
only -- no verdict-logic change.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/intel_validation/test_claims_validator.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.platformkit.intel_validation.claims_validator import (
    ValidationSummary,
    validate_claim,
    write_summary,
)


def _make_parquet(tmp_path: Path, name: str, rows: list[dict]) -> str:
    p = tmp_path / name
    pd.DataFrame(rows).to_parquet(p)
    return str(p)


def test_write_summary_persists_mismatch_with_numpy_int64_id(tmp_path):
    """int64 player_id source column -> recomputed_id in first_divergence is
    a raw np.int64. Before the fix, json.dump(payload) here raised
    TypeError: Object of type int64 is not JSON serializable."""
    rows = [
        {"player_id": 101, "player_name": "Alpha", "fg3_pct": 0.45, "fg3a": 300},
        {"player_id": 102, "player_name": "Bravo", "fg3_pct": 0.40, "fg3a": 250},
    ]
    src = _make_parquet(tmp_path, "shooting.parquet", rows)
    claim = {
        "claim_id": "top_fg3pct",
        "kind": "ranking",
        "question": "Who leads in 3pt%?",
        "criteria": {
            "metric": "fg3_pct", "formula": "fg3_pct", "window": "season",
            "min_sample": {"fg3a": 100}, "direction": "desc",
        },
        # PLANT: rank 1 claimed as player 102 despite 101 actually leading --
        # forces a MISMATCH first_divergence carrying recomputed_id=101 (np.int64).
        "ranking": [{"rank": 1, "player_id": 102, "player_name": "Bravo", "value": 0.40, "n": 250}],
        "source_files": [src],
        "computed_at": "2026-07-05T00:00:00+00:00",
        "n_considered": 2,
        "n_excluded_below_floor": 0,
        "caveats": [],
    }
    verdict = validate_claim(claim)
    assert verdict.verdict == "MISMATCH"
    recomputed_id = verdict.first_divergence["recomputed"]["player_id"]
    assert isinstance(recomputed_id, (np.integer,))  # confirms this test exercises the real numpy path

    summary = ValidationSummary(generated_at="2026-07-05T00:00:00+00:00")
    summary.n_claims = 1
    summary.n_mismatch = 1
    summary.details.append({
        "claim_id": verdict.claim_id,
        "verdict": verdict.verdict,
        "reason": verdict.reason,
        "first_divergence": verdict.first_divergence,
    })

    out_path = tmp_path / "out.json"
    write_summary(summary, out_path)  # must not raise

    payload = json.loads(out_path.read_text(encoding="ascii"))
    detail = payload["details"][0]
    assert detail["verdict"] == "MISMATCH"
    # numpy int64 round-tripped to a plain JSON int, value preserved exactly
    assert detail["first_divergence"]["recomputed"]["player_id"] == 101
    assert isinstance(detail["first_divergence"]["recomputed"]["player_id"], int)


def test_write_summary_persists_mismatch_with_numpy_float64_value(tmp_path):
    """A MISMATCH on a plain-value miscompare (not an id miscompare) also
    carries a numpy float64 for the recomputed value in some column dtypes;
    confirms the same default= hook round-trips floats too."""
    rows = [
        {"player_id": "1", "player_name": "A", "pts": np.float64(30.0), "reb": np.float64(10.0), "gp": 60},
        {"player_id": "2", "player_name": "B", "pts": np.float64(20.0), "reb": np.float64(5.0), "gp": 55},
    ]
    src = _make_parquet(tmp_path, "combo.parquet", rows)
    claim = {
        "claim_id": "pts_plus_reb",
        "kind": "ranking",
        "question": "Who has the highest pts+reb?",
        "criteria": {
            "metric": "pts_plus_reb", "formula": "pts + reb", "window": "season",
            "min_sample": {"gp": 10}, "direction": "desc",
        },
        # PLANT: claimed value inflated beyond tolerance -> MISMATCH on value, not id.
        "ranking": [{"rank": 1, "player_id": "1", "player_name": "A", "value": 999.0, "n": 60}],
        "source_files": [src],
        "computed_at": "2026-07-05T00:00:00+00:00",
        "n_considered": 2,
        "n_excluded_below_floor": 0,
        "caveats": [],
    }
    verdict = validate_claim(claim)
    assert verdict.verdict == "MISMATCH"

    summary = ValidationSummary(generated_at="2026-07-05T00:00:00+00:00")
    summary.n_claims = 1
    summary.n_mismatch = 1
    summary.details.append({
        "claim_id": verdict.claim_id, "verdict": verdict.verdict,
        "reason": verdict.reason, "first_divergence": verdict.first_divergence,
    })

    out_path = tmp_path / "out.json"
    write_summary(summary, out_path)  # must not raise

    payload = json.loads(out_path.read_text(encoding="ascii"))
    assert payload["details"][0]["first_divergence"]["recomputed"]["value"] == 40.0
