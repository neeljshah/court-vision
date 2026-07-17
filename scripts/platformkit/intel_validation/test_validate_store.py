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

from scripts.platformkit.intel_validation.validate_store import (
    _NOT_RANKING_CLAIM_STORES,
    validate_and_write,
)


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


def test_validate_and_write_skips_known_ledger_stores(tmp_path):
    """Rigor-sweep fix (2026-07-17): claim_weights/false_discovery_ledger/
    gate_verdict_claims/ingame_distributional_crps_ledger/
    interaction_factory_ledger/prereg_hypothesis_ledger are audit/verdict
    LEDGERS, not ranking claims -- no criteria.formula by design. Before
    this fix, validate_and_write ran them through the ranking recompute
    anyway and wrote a `<stem>_validation.json` claiming every row
    "UNVERIFIABLE -- criteria.formula missing" (a validator/store category
    mismatch, not a real gap). Now it skips them and writes nothing."""
    for stem in _NOT_RANKING_CLAIM_STORES:
        ledger_row = {"sport": "mlb", "verdict": "UNTESTABLE", "note": "no formula by design"}
        jsonl_path = tmp_path / f"{stem}.jsonl"
        jsonl_path.write_text(json.dumps(ledger_row) + "\n", encoding="ascii")

        result = validate_and_write(str(jsonl_path))

        assert result["skipped"] is True
        assert result["store"] == jsonl_path.name
        out_path = jsonl_path.with_name(f"{stem}_validation.json")
        assert not out_path.exists(), f"{stem}: must not write a misleading validation sidecar"


def test_validate_and_write_still_validates_a_real_ranking_store_by_stem_lookup(tmp_path, monkeypatch):
    """A stem NOT in the skip-list is unaffected -- exercises the
    `CLAIMS_DIR / f"{stem}.jsonl"` branch (no suffix passed), the same call
    shape run_validate_new_stores/the CLI use for every legitimate store."""
    import scripts.platformkit.intel_validation.validate_store as vs

    rows = [{"player_id": 1, "fg3_pct": 0.5, "fg3a": 200}]
    src = tmp_path / "shooting.parquet"
    pd.DataFrame(rows).to_parquet(src)
    claim = {
        "claim_id": "c1", "kind": "ranking", "question": "?",
        "criteria": {"metric": "fg3_pct", "formula": "fg3_pct", "window": "season",
                     "min_sample": {"fg3a": 100}, "direction": "desc"},
        "ranking": [{"rank": 1, "player_id": 1, "value": 0.5, "n": 200}],
        "source_files": [str(src)], "computed_at": "2026-07-05T00:00:00+00:00",
        "n_considered": 1, "n_excluded_below_floor": 0, "caveats": [],
    }
    monkeypatch.setattr(vs, "CLAIMS_DIR", tmp_path)
    (tmp_path / "not_a_ledger.jsonl").write_text(json.dumps(claim) + "\n", encoding="ascii")

    result = validate_and_write("not_a_ledger")  # no suffix -> CLAIMS_DIR lookup branch

    assert "skipped" not in result
    assert result["n_verified"] == 1
