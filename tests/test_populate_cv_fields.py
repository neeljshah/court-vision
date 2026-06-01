"""tests/test_populate_cv_fields.py — Tests for populate_cv_fields.py

Tests:
  (a) idempotency — run populate twice → identical content the 2nd time
  (b) non-cv columns + row count preserved
  (c) a player in the CV file (n_games>=5) gets >=1 non-null slot with
      _cv_meta.confidence in {"med","low"} — never "high"
  (d) a player NOT in the CV file keeps all-null cv_fields and no _cv_meta

Uses tmp copies of real parquets — never mutates the live data files.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
REAL_REBOUNDING = ROOT / "data" / "cache" / "atlas_player_rebounding_profile.parquet"
CV_SRC = ROOT / "data" / "player_cv_per_player.parquet"

# Import the module under test
import sys
sys.path.insert(0, str(ROOT / "scripts" / "intel"))
import populate_cv_fields as pcf  # noqa: E402

AS_OF = "2026-05-31"

# Known CV player with n_games >= 5 (player 202696 confirmed in CV with n_games=5)
# and known-absent player (201142).
CV_PLAYER_ID = 202696
NON_CV_PLAYER_ID = 201142


@pytest.fixture()
def rebounding_tmp(tmp_path: Path) -> Path:
    """Copy the real rebounding_profile parquet to a tmp directory."""
    dst = tmp_path / "atlas_player_rebounding_profile.parquet"
    shutil.copy2(REAL_REBOUNDING, dst)
    return dst


@pytest.fixture()
def cv_lookup() -> dict:
    return pcf._build_cv_lookup(CV_SRC)


# ---------------------------------------------------------------------------
# (b) Non-CV columns and row count preserved
# ---------------------------------------------------------------------------
def test_columns_and_row_count_preserved(rebounding_tmp: Path, cv_lookup: dict) -> None:
    df_before = pd.read_parquet(rebounding_tmp)
    original_cols = list(df_before.columns)
    original_rows = len(df_before)

    result = pcf.populate_parquet(rebounding_tmp, cv_lookup, AS_OF, dry_run=False)

    assert not result.get("skipped"), f"Parquet was skipped: {result}"

    df_after = pd.read_parquet(rebounding_tmp)
    assert list(df_after.columns) == original_cols, "Column set changed!"
    assert len(df_after) == original_rows, "Row count changed!"

    # Non-_cv_fields columns must be byte-identical
    for col in original_cols:
        if col == "_cv_fields":
            continue
        pd.testing.assert_series_equal(
            df_before[col].reset_index(drop=True),
            df_after[col].reset_index(drop=True),
            check_names=False,
            obj=f"Column '{col}' changed",
        )


# ---------------------------------------------------------------------------
# (c) CV player gets >=1 non-null slot and confidence never "high"
# ---------------------------------------------------------------------------
def test_cv_player_gets_filled_slots_not_high_confidence(
    rebounding_tmp: Path, cv_lookup: dict
) -> None:
    assert CV_PLAYER_ID in cv_lookup, f"Player {CV_PLAYER_ID} not in CV lookup"

    pcf.populate_parquet(rebounding_tmp, cv_lookup, AS_OF, dry_run=False)
    df = pd.read_parquet(rebounding_tmp)

    # Player must exist in atlas
    row = df[df["player_id"] == CV_PLAYER_ID]
    assert len(row) == 1, f"Player {CV_PLAYER_ID} not in rebounding_profile atlas"

    cv_fields = json.loads(row.iloc[0]["_cv_fields"])

    # Must have _cv_meta
    assert "_cv_meta" in cv_fields, "_cv_meta not written for CV player"
    meta = cv_fields["_cv_meta"]

    # Confidence must not be "high"
    assert meta["confidence"] != "high", (
        f"confidence='high' is not allowed for CV descriptive fields; got {meta['confidence']}"
    )
    assert meta["confidence"] in {"med", "low"}, (
        f"Unexpected confidence: {meta['confidence']}"
    )

    # At least one slot should be non-null
    filled_slots = meta.get("filled_slots", [])
    assert len(filled_slots) >= 1, (
        f"Expected >=1 filled slot for player {CV_PLAYER_ID}, got 0"
    )
    for slot_name in filled_slots:
        assert slot_name in cv_fields, f"Slot {slot_name} in filled_slots but not in cv_fields"
        assert cv_fields[slot_name]["value"] is not None, (
            f"Slot {slot_name} listed in filled_slots but value is null"
        )


# ---------------------------------------------------------------------------
# (d) Non-CV player keeps all-null cv_fields and no _cv_meta
# ---------------------------------------------------------------------------
def test_non_cv_player_stays_null(rebounding_tmp: Path, cv_lookup: dict) -> None:
    assert NON_CV_PLAYER_ID not in cv_lookup, (
        f"Player {NON_CV_PLAYER_ID} unexpectedly found in CV lookup"
    )

    df = pd.read_parquet(rebounding_tmp)
    row = df[df["player_id"] == NON_CV_PLAYER_ID]
    assert len(row) == 1, f"Player {NON_CV_PLAYER_ID} not in rebounding_profile atlas"

    original_json = row.iloc[0]["_cv_fields"]

    pcf.populate_parquet(rebounding_tmp, cv_lookup, AS_OF, dry_run=False)

    df_after = pd.read_parquet(rebounding_tmp)
    row_after = df_after[df_after["player_id"] == NON_CV_PLAYER_ID]
    new_json = row_after.iloc[0]["_cv_fields"]

    # Must be unchanged
    assert new_json == original_json, (
        f"Non-CV player {NON_CV_PLAYER_ID} had _cv_fields modified"
    )

    parsed = json.loads(new_json)
    # No _cv_meta
    assert "_cv_meta" not in parsed, "_cv_meta should not exist for non-CV player"
    # All values must be null
    for slot_name, slot_meta in parsed.items():
        if slot_name.startswith("_"):
            continue
        assert slot_meta.get("value") is None, (
            f"Slot {slot_name} has non-null value for non-CV player {NON_CV_PLAYER_ID}"
        )


# ---------------------------------------------------------------------------
# (a) Idempotency — running twice produces identical content
# ---------------------------------------------------------------------------
def test_idempotency(rebounding_tmp: Path, cv_lookup: dict) -> None:
    # First run
    pcf.populate_parquet(rebounding_tmp, cv_lookup, AS_OF, dry_run=False)
    df_first = pd.read_parquet(rebounding_tmp)
    first_cv = list(df_first["_cv_fields"])

    # Second run (same as-of date for determinism)
    pcf.populate_parquet(rebounding_tmp, cv_lookup, AS_OF, dry_run=False)
    df_second = pd.read_parquet(rebounding_tmp)
    second_cv = list(df_second["_cv_fields"])

    assert len(first_cv) == len(second_cv)
    for i, (a, b) in enumerate(zip(first_cv, second_cv)):
        # Parse both and compare semantically (key order may differ in JSON)
        pa, pb = json.loads(a), json.loads(b)
        assert pa == pb, f"Row {i} differs between run 1 and run 2:\n  run1={a}\n  run2={b}"

    # Full column equality
    pd.testing.assert_frame_equal(df_first, df_second, check_like=False)
