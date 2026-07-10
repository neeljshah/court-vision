"""Per-file regression test for validate_store.validate_and_write.

Covers the recurring crash: a MISMATCH first_divergence block can carry a raw
numpy scalar id (e.g. recomputed_id off an int64 entity_key column straight
from a pandas source frame). validate_store.py used to hand-roll its own
`out.write_text(json.dumps(asdict(summary), indent=1))` instead of reusing
claims_validator.write_summary's numpy-safe json.dump (_json_numpy_default),
so it crashed TypeError: Object of type int64 is not JSON serializable and
left `<stem>_validation.json` stale forever (the .jsonl kept refreshing from
its own producer, but the paired validation never re-wrote).

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/intel_validation/test_validate_store.py -q
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd

from scripts.platformkit.intel_validation.validate_store import validate_and_write


def test_validate_and_write_survives_numpy_int64_mismatch_id(tmp_path):
    """int64 player_id source column + a planted MISMATCH -> first_divergence
    carries a raw np.int64 recomputed id. Before the fix this raised
    TypeError inside validate_and_write and never wrote the validation.json."""
    rows = [
        {"player_id": 101, "player_name": "Alpha", "fg3_pct": 0.45, "fg3a": 300},
        {"player_id": 102, "player_name": "Bravo", "fg3_pct": 0.40, "fg3a": 250},
    ]
    src = tmp_path / "shooting.parquet"
    pd.DataFrame(rows).to_parquet(src)

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
        "source_files": [str(src)],
        "computed_at": "2026-07-05T00:00:00+00:00",
        "n_considered": 2,
        "n_excluded_below_floor": 0,
        "caveats": [],
    }
    jsonl_path = tmp_path / "fake_store.jsonl"
    jsonl_path.write_text(json.dumps(claim) + "\n", encoding="ascii")

    # mtime ordering matches the real watermark rule (validation must land
    # strictly after the store it validates).
    time.sleep(0.05)

    result = validate_and_write(str(jsonl_path))  # must not raise

    out_path = jsonl_path.with_name("fake_store_validation.json")
    assert out_path.exists()
    assert result["out"] == str(out_path)
    assert result["n_mismatch"] == 1

    assert out_path.stat().st_mtime >= jsonl_path.stat().st_mtime  # freshness watermark holds

    payload = json.loads(out_path.read_text(encoding="ascii"))
    detail = payload["details"][0]
    assert detail["verdict"] == "MISMATCH"
    # numpy int64 round-tripped to a plain JSON int, value preserved exactly
    recomputed_id = detail["first_divergence"]["recomputed"]["player_id"]
    assert recomputed_id == 101
    assert isinstance(recomputed_id, int)

    # no orphaned tmp artifact from this write path
    assert list(tmp_path.glob("*.tmp*")) == []
