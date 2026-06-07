"""Tests for src.loop.atlas_features -- the leak-safe atlas -> model feature bridge.

Covers:
  * flattening of nested JSON sub-fields into ``atlas_<section>__<path>`` leaves,
  * leak-safety: store reads never return future records; parquet fallback drops
    rows stamped after the requested as_of,
  * the prop-feature-matrix join helper (per-row as-of, gap-fill vs overwrite),
  * feature-name discovery from the materialised parquet schema.

Uses a temporary PointInTimeStore so it never touches live data/cache/loop_store/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.loop import atlas_features as af  # noqa: E402
from src.loop.store import PointInTimeStore  # noqa: E402


@pytest.fixture()
def store(tmp_path) -> PointInTimeStore:
    """An isolated point-in-time store seeded with two as_of versions of a section."""
    s = PointInTimeStore(store_dir=tmp_path / "loop_store", autoload=False)
    # player 999: usage_role known at 2026-01-01, refreshed (higher) at 2026-03-01
    s.write_atlas("player", 999, "usage_role", "2026-01-01",
                  {"usage_rate": 0.25, "creator_role": "secondary",
                   "_cv_fields": {"cv_iso_freq": {"value": None}}},
                  {"source": "test", "n": 30, "confidence": "high",
                   "as_of": "2026-01-01"})
    s.write_atlas("player", 999, "usage_role", "2026-03-01",
                  {"usage_rate": 0.31, "creator_role": "primary",
                   "nested": {"deep_val": 1.5, "_note": "DEFER skip me"}},
                  {"source": "test", "n": 40, "confidence": "high",
                   "as_of": "2026-03-01"})
    return s


def test_flatten_numeric_and_categorical():
    out: dict = {}
    af._flatten(
        {"a": 1.5, "b": {"c": 2, "_note": "skip"}, "lst": [1, 2],
         "flag": True, "empty": "", "_priv": 9, "name": "primary"},
        "", out)
    assert out["a"] == 1.5
    assert out["b.c"] == 2.0
    assert out["flag"] == 1            # bool -> int
    assert out["name"] == "primary"    # categorical kept
    assert "b._note" not in out        # DEFER underscore key skipped
    assert "lst" not in out            # lists dropped
    assert "empty" not in out          # whitespace-only string dropped
    assert "_priv" not in out          # underscore-prefixed key skipped


def test_feature_row_leak_safe_picks_freshest_at_or_before(store):
    # as-of 2026-02-01 -> only the 2026-01-01 record is visible
    early = af.atlas_feature_row(999, "2026-02-01", entity_type="player",
                                 sections=["usage_role"], store=store)
    assert early["atlas_usage_role__usage_rate"] == 0.25
    assert early["atlas_usage_role__creator_role"] == "secondary"

    # as-of 2026-04-01 -> the refreshed 2026-03-01 record wins
    late = af.atlas_feature_row(999, "2026-04-01", entity_type="player",
                                sections=["usage_role"], store=store)
    assert late["atlas_usage_role__usage_rate"] == 0.31
    assert late["atlas_usage_role__creator_role"] == "primary"
    assert late["atlas_usage_role__nested.deep_val"] == 1.5
    # DEFER note + null CV slot must never appear as features
    assert not any("_note" in k or "_cv_fields" in k for k in late)


def test_feature_row_before_any_record_is_empty(store):
    out = af.atlas_feature_row(999, "2025-12-01", entity_type="player",
                               sections=["usage_role"], store=store)
    assert out == {}


def test_feature_row_unknown_entity_is_empty(store):
    out = af.atlas_feature_row(123456, "2026-12-01", entity_type="player",
                               sections=["usage_role"], store=store)
    assert out == {}


def test_parquet_fallback_leak_guard(tmp_path, monkeypatch):
    # Build a fake disjoint parquet stamped in the FUTURE; reading it as-of an
    # earlier date must drop the row (no look-ahead leak).
    df = pd.DataFrame([{
        "player_id": 555, "usage_rate": 0.4,
        "n": 25, "confidence": "high", "as_of": "2026-06-01",
    }])
    pq = tmp_path / "atlas_player_usage_role.parquet"
    df.to_parquet(pq, index=False)
    monkeypatch.setattr(af, "CACHE", tmp_path)
    af._load_parquet.cache_clear()

    # empty store so we exercise the parquet fallback path
    empty_store = PointInTimeStore(store_dir=tmp_path / "empty_store", autoload=False)

    # as-of BEFORE the parquet's as_of -> leak guard drops it
    before = af.atlas_feature_row(555, "2026-05-01", entity_type="player",
                                  sections=["usage_role"], store=empty_store)
    assert before == {}

    # as-of AT/AFTER the parquet's as_of -> value is exposed
    after = af.atlas_feature_row(555, "2026-06-15", entity_type="player",
                                 sections=["usage_role"], store=empty_store)
    assert after["atlas_usage_role__usage_rate"] == 0.4
    af._load_parquet.cache_clear()


def test_join_atlas_features_per_row_asof_and_gapfill(store):
    rows = [
        {"player_id": 999, "date": "2026-02-01", "usage_rate": 9.9},  # pre-existing key
        {"player_id": 999, "date": "2026-04-01"},
        {"player_id": 999},  # missing date -> untouched
    ]
    out = af.join_atlas_features(rows, entity_type="player", sections=["usage_role"],
                                 store=store)
    # row 0: early as-of value, but pre-existing key preserved (gap-fill default)
    assert out[0]["usage_rate"] == 9.9
    assert out[0]["atlas_usage_role__usage_rate"] == 0.25
    # row 1: late as-of value
    assert out[1]["atlas_usage_role__usage_rate"] == 0.31
    # row 2: no date -> no atlas keys added
    assert not any(k.startswith("atlas_") for k in out[2])


def test_join_overwrite_true_replaces_collisions(store):
    rows = [{"player_id": 999, "date": "2026-04-01",
             "atlas_usage_role__usage_rate": -1.0}]
    out = af.join_atlas_features(rows, sections=["usage_role"], store=store,
                                 overwrite=True)
    assert out[0]["atlas_usage_role__usage_rate"] == 0.31


def test_feature_names_from_parquet_schema(tmp_path, monkeypatch):
    df = pd.DataFrame([{
        "player_id": 7, "usage_rate": 0.3, "creator_role": "primary",
        "n": 20, "confidence": "high", "as_of": "2026-01-01",
    }])
    (tmp_path / "atlas_player_usage_role.parquet").parent.mkdir(
        parents=True, exist_ok=True)
    df.to_parquet(tmp_path / "atlas_player_usage_role.parquet", index=False)
    monkeypatch.setattr(af, "CACHE", tmp_path)
    af._load_parquet.cache_clear()

    numeric = af.atlas_feature_names("player", sections=["usage_role"],
                                     numeric_only=True)
    assert "atlas_usage_role__usage_rate" in numeric
    assert "atlas_usage_role__creator_role" not in numeric  # categorical dropped

    withcat = af.atlas_feature_names("player", sections=["usage_role"],
                                     numeric_only=False)
    assert "atlas_usage_role__creator_role" in withcat
    af._load_parquet.cache_clear()
