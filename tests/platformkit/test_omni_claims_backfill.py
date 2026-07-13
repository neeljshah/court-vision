"""tests.platformkit.test_omni_claims_backfill -- P2-BF backfill tests."""
from __future__ import annotations

import json
import pathlib
import tempfile

import pandas as pd
import pytest

from scripts.platformkit.omni.claims_backfill import (
    _verdict_to_lifecycle, _infer_season, backfill_registry, backfill_signal_test_log,
)
from scripts.platformkit.omni.claims_ledger import query, rebuild_parquet


def test_verdict_to_lifecycle():
    """Test verdict string -> lifecycle mapping."""
    assert _verdict_to_lifecycle("VALIDATED") == ("accepted", True)
    assert _verdict_to_lifecycle("REJECTED") == ("rejected", False)
    assert _verdict_to_lifecycle("rejected") == ("rejected", False)
    assert _verdict_to_lifecycle("rejected-redundant-with-poss_dur") == ("rejected", False)
    assert _verdict_to_lifecycle("rejected-null") == ("rejected", False)
    assert _verdict_to_lifecycle(None) == (None, None)
    assert _verdict_to_lifecycle("UNKNOWN_VERDICT") == (None, None)


def test_infer_season():
    """Test season inference from asof date."""
    assert _infer_season("2026-06-05") == "2025-26"  # June = month 6, so 2026-1=2025
    assert _infer_season("2026-04-03") == "2025-26"  # April = month 4, so 2026-1=2025
    assert _infer_season("2026-01-15") == "2025-26"  # Jan = month 1, so 2026-1=2025
    assert _infer_season("2026-12-31") == "2026-27"  # Dec = month 12, so 2026-(2026+1)=2026-27
    assert _infer_season("invalid") == "unknown"


def test_registry_backfill_synthetic(tmp_path):
    """Test backfill_registry with a synthetic registry.parquet."""
    # Create a minimal synthetic registry parquet
    registry_path = tmp_path / "data" / "registry"
    registry_path.mkdir(parents=True)

    df_synthetic = pd.DataFrame({
        "name": ["test_signal_1", "test_signal_2", "test_signal_bad"],
        "grain": ["player-game", "possession", "lineup"],
        "target": ["pts", "margin", "ppp"],
        "metric": ["points", "margin_diff", "ppp"],
        "n": [100, 200, 150],
        "base_err": [0.5, 0.3, 0.4],
        "full_err": [0.45, 0.28, 0.39],
        "oos_rel": [0.1, 0.05, 0.025],
        "split_half": [True, False, True],
        "ortho": [0.8, 0.9, 0.7],
        "verdict": ["VALIDATED", "REJECTED", "UNKNOWN_VERDICT"],
        "reason": ["good signal", "redundant", "bad signal"],
        "asof": ["2026-06-05", "2026-04-03", "2026-06-10"],
        "note": ["test 1", "test 2", "test 3"],
    })
    (registry_path / "signal_lab_registry.parquet").write_bytes(df_synthetic.to_parquet())

    # Create claims dir
    claims_path = tmp_path / "data" / "omni" / "claims"
    claims_path.mkdir(parents=True)

    # Run backfill with synthetic registry path
    results = backfill_registry(claims_path, registry_path / "signal_lab_registry.parquet")

    # Verify: 2 added (VALIDATED, REJECTED), 1 failed (UNKNOWN_VERDICT), 0 skipped
    assert results["added"] == 2, f"Expected 2 added, got {results}"
    assert results["failed"] == 1, f"Expected 1 failed (unknown verdict), got {results}"
    assert results["skipped"] == 0, f"Expected 0 skipped, got {results}"

    # Verify the claims in the ledger
    df_claims = rebuild_parquet(claims_path)
    assert len(df_claims) == 2, f"Expected 2 claims, got {len(df_claims)}"

    # Verify VALIDATED -> accepted, REJECTED -> rejected
    accepted = df_claims[df_claims["lifecycle"] == "accepted"]
    rejected = df_claims[df_claims["lifecycle"] == "rejected"]
    assert len(accepted) == 1, f"Expected 1 accepted, got {len(accepted)}"
    assert len(rejected) == 1, f"Expected 1 rejected, got {len(rejected)}"

    # Verify types
    effect_claims = df_claims[df_claims["type"] == "effect"]
    negative_claims = df_claims[df_claims["type"] == "negative"]
    assert len(effect_claims) == 1, f"Expected 1 effect, got {len(effect_claims)}"
    assert len(negative_claims) == 1, f"Expected 1 negative, got {len(negative_claims)}"


def test_idempotency(tmp_path):
    """Test that running backfill twice adds 0 rows on the second run."""
    # Create synthetic registry
    registry_path = tmp_path / "data" / "registry"
    registry_path.mkdir(parents=True)

    df_synthetic = pd.DataFrame({
        "name": ["test_signal"],
        "grain": ["player-game"],
        "target": ["pts"],
        "metric": ["points"],
        "n": [100],
        "base_err": [0.5],
        "full_err": [0.45],
        "oos_rel": [0.1],
        "split_half": [True],
        "ortho": [0.8],
        "verdict": ["VALIDATED"],
        "reason": ["good signal"],
        "asof": ["2026-06-05"],
        "note": ["test"],
    })
    (registry_path / "signal_lab_registry.parquet").write_bytes(df_synthetic.to_parquet())

    claims_path = tmp_path / "data" / "omni" / "claims"
    claims_path.mkdir(parents=True)

    # First run
    results1 = backfill_registry(claims_path, registry_path / "signal_lab_registry.parquet")
    assert results1["added"] == 1

    journal_path = claims_path / "journal.jsonl"
    with open(journal_path, encoding="ascii") as f:
        lines1 = f.readlines()

    # Second run (idempotent)
    results2 = backfill_registry(claims_path, registry_path / "signal_lab_registry.parquet")
    assert results2["added"] == 0, f"Second run should add 0, got {results2}"
    assert results2["skipped"] == 1, f"Second run should skip 1, got {results2}"

    with open(journal_path, encoding="ascii") as f:
        lines2 = f.readlines()

    # Journal should not grow
    assert len(lines1) == len(lines2), f"Journal grew on second run: {len(lines1)} -> {len(lines2)}"


def test_signal_test_log_backfill_synthetic(tmp_path):
    """Test backfill_signal_test_log with synthetic test_log parquets."""
    # Create synthetic signal_test_log files
    test_log_path = tmp_path / "data" / "registry" / "signal_test_log"
    test_log_path.mkdir(parents=True)

    df_synthetic = pd.DataFrame({
        "hash": ["fam_clock_test", "fam_score_test"],
        "family_key": ["fam_transition_clock", "fam_score_state"],
        "definition": ["fastbreak+early_clock", "garbage+is_clutch"],
        "p": [0.9, 0.4],
        "batch_id": ["aspect_sweep", "aspect_sweep"],
        "asof": ["2026-06-08", "2026-06-08"],
        "verdict": ["rejected-redundant-with-poss_dur", "rejected-null"],
    })
    (test_log_path / "part-000000-test.parquet").write_bytes(df_synthetic.to_parquet())

    claims_path = tmp_path / "data" / "omni" / "claims"
    claims_path.mkdir(parents=True)

    # Run backfill with synthetic test_log path
    results = backfill_signal_test_log(claims_path, test_log_path)

    # Verify: 2 added, 0 failed, 0 skipped
    assert results["added"] == 2, f"Expected 2 added, got {results}"
    assert results["failed"] == 0, f"Expected 0 failed, got {results}"
    assert results["skipped"] == 0, f"Expected 0 skipped, got {results}"

    # Verify the claims in the ledger
    df_claims = rebuild_parquet(claims_path)
    assert len(df_claims) == 2, f"Expected 2 claims, got {len(df_claims)}"

    # All should be rejected/negative type
    assert (df_claims["lifecycle"] == "rejected").all(), "All test_log claims should be rejected"
    assert (df_claims["type"] == "negative").all(), "All test_log claims should be negative type"


def test_unknown_verdicts_skipped(tmp_path):
    """Test that unknown verdict strings are skipped with counted warning, never guessed."""
    registry_path = tmp_path / "data" / "registry"
    registry_path.mkdir(parents=True)

    df_synthetic = pd.DataFrame({
        "name": ["unknown_1", "unknown_2", "valid_1"],
        "grain": ["player-game", "possession", "team-game"],
        "target": ["pts", "margin", "ppp"],
        "metric": ["points", "margin", "ppp"],
        "n": [100, 200, 150],
        "base_err": [0.5, 0.3, 0.4],
        "full_err": [0.45, 0.28, 0.39],
        "oos_rel": [0.1, 0.05, 0.025],
        "split_half": [True, False, True],
        "ortho": [0.8, 0.9, 0.7],
        "verdict": ["WEIRD_VERDICT", None, "VALIDATED"],
        "reason": ["weird", "null", "good"],
        "asof": ["2026-06-05", "2026-04-03", "2026-06-10"],
        "note": ["test", "test", "test"],
    })
    (registry_path / "signal_lab_registry.parquet").write_bytes(df_synthetic.to_parquet())

    claims_path = tmp_path / "data" / "omni" / "claims"
    claims_path.mkdir(parents=True)

    results = backfill_registry(claims_path, registry_path / "signal_lab_registry.parquet")

    # 1 valid, 2 unknown verdicts
    assert results["added"] == 1, f"Expected 1 added, got {results}"
    assert results["failed"] == 2, f"Expected 2 failed (unknown verdicts), got {results}"
    assert results["skipped"] == 0, f"Expected 0 skipped, got {results}"
