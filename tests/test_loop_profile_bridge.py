"""Tests for src/loop/profile_factory_bridge.py.

Covers:
  - materialise_parquet: writes a disjoint parquet, merge semantics (accumulate-don't-clobber)
  - emit_sec_function: generated source is syntactically valid + callable
  - update_registry: idempotent JSON write, section keyed correctly
  - register_section: full round-trip (parquet + store write + registry, dry_run mode)
  - get_sec_function: compiles + calls the generated sec_ fn
  - _merge_parquet_rows: lower-confidence row is NOT clobbered, newer as_of wins

All tests are self-contained (tmp_path fixtures), do NOT touch the live store or real
data/cache, and do NOT run the full test suite.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import pytest

# --- path bootstrap so we can import from src/loop/ standalone ---------------
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot
from src.loop.profile_factory_bridge import (
    emit_sec_function,
    get_sec_function,
    load_registered_sections,
    materialise_parquet,
    register_section,
    update_registry,
    _merge_parquet_rows,
)


# ---------------------------------------------------------------------------
# Minimal concrete AtlasSection for testing
# ---------------------------------------------------------------------------

class _TestSection(AtlasSection):
    name = "test_section"
    entity = "player"
    source_name = "test.parquet"
    conf_cap = None

    def build(self, entity_id, as_of: datetime) -> Optional[AtlasArtifact]:
        return None  # not exercised in bridge tests

    def validate(self, artifact: AtlasArtifact) -> bool:
        return True

    def cv_fields(self) -> Dict[str, CVSlot]:
        return {
            "defender_distance_dist": CVSlot(
                name="defender_distance_dist",
                dtype="dist",
                description="Distribution of defender distances (ft)",
                unit="ft",
            ),
            "contest_level": CVSlot(
                name="contest_level",
                dtype="float",
                description="Average contest level score",
            ),
        }


def _make_artifact(pid: int, as_of: str = "2026-05-30",
                   confidence: str = "high", n: int = 30) -> AtlasArtifact:
    cv = {
        "defender_distance_dist": CVSlot(
            name="defender_distance_dist", dtype="dist", unit="ft",
            description="Distribution of defender distances (ft)"
        ),
        "contest_level": CVSlot(
            name="contest_level", dtype="float",
            description="Average contest level score"
        ),
    }
    return AtlasArtifact(
        section="test_section",
        entity="player",
        entity_id=pid,
        value=25.5,
        sub_fields={"pts_pg": 25.5, "min_pg": 35.0, "notes": {"trend": "up"}},
        provenance={"source": "test.parquet", "n": n, "confidence": confidence, "as_of": as_of},
        confidence=confidence,
        as_of=as_of,
        cv_fields=cv,
    )


# ---------------------------------------------------------------------------
# Tests: materialise_parquet
# ---------------------------------------------------------------------------

def test_materialise_parquet_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr("src.loop.profile_factory_bridge.CACHE", tmp_path)
    section = _TestSection()
    artifacts = [_make_artifact(1628983), _make_artifact(203076)]
    out_path = materialise_parquet(section, artifacts)
    assert out_path.exists(), "parquet should be written"
    df = pd.read_parquet(out_path)
    assert len(df) == 2
    assert "player_id" in df.columns
    assert set(df["player_id"].tolist()) == {1628983, 203076}


def test_materialise_parquet_has_cv_fields(tmp_path, monkeypatch):
    monkeypatch.setattr("src.loop.profile_factory_bridge.CACHE", tmp_path)
    section = _TestSection()
    art = _make_artifact(1628983)
    materialise_parquet(section, [art])
    df = pd.read_parquet(tmp_path / section.parquet_name())
    assert "_cv_fields" in df.columns
    cv_decoded = json.loads(df.iloc[0]["_cv_fields"])
    assert "defender_distance_dist" in cv_decoded
    assert cv_decoded["defender_distance_dist"]["value"] is None  # reserved, not yet filled


def test_materialise_parquet_dry_run_no_write(tmp_path, monkeypatch):
    monkeypatch.setattr("src.loop.profile_factory_bridge.CACHE", tmp_path)
    section = _TestSection()
    artifacts = [_make_artifact(1628983)]
    out_path = materialise_parquet(section, artifacts, dry_run=True)
    assert not out_path.exists(), "dry_run must not write to disk"


def test_materialise_parquet_accumulate_dont_clobber(tmp_path, monkeypatch):
    """A low-confidence artifact must NOT overwrite an existing high-confidence row."""
    monkeypatch.setattr("src.loop.profile_factory_bridge.CACHE", tmp_path)
    section = _TestSection()
    high_art = _make_artifact(1628983, confidence="high", n=30, as_of="2026-05-01")
    materialise_parquet(section, [high_art])

    # Now try to overwrite with a low-confidence, older-as_of artifact
    low_art = _make_artifact(1628983, confidence="low", n=3, as_of="2025-01-01")
    materialise_parquet(section, [low_art])

    df = pd.read_parquet(tmp_path / section.parquet_name())
    assert len(df) == 1
    assert str(df.iloc[0]["confidence"]) == "high", (
        "high-confidence existing row must survive a low-confidence update with older as_of"
    )


def test_materialise_parquet_newer_as_of_wins(tmp_path, monkeypatch):
    """A newer as_of should replace even if confidence is equal."""
    monkeypatch.setattr("src.loop.profile_factory_bridge.CACHE", tmp_path)
    section = _TestSection()
    old_art = _make_artifact(1628983, confidence="med", n=10, as_of="2025-01-01")
    materialise_parquet(section, [old_art])
    new_art = _make_artifact(1628983, confidence="med", n=10, as_of="2026-05-30")
    materialise_parquet(section, [new_art])
    df = pd.read_parquet(tmp_path / section.parquet_name())
    assert str(df.iloc[0]["as_of"]) == "2026-05-30"


def test_materialise_parquet_preserves_other_entities(tmp_path, monkeypatch):
    """Existing rows for OTHER player_ids are preserved when new artifacts are written."""
    monkeypatch.setattr("src.loop.profile_factory_bridge.CACHE", tmp_path)
    section = _TestSection()
    materialise_parquet(section, [_make_artifact(1628983)])
    materialise_parquet(section, [_make_artifact(203076)])
    df = pd.read_parquet(tmp_path / section.parquet_name())
    assert len(df) == 2


# ---------------------------------------------------------------------------
# Tests: emit_sec_function
# ---------------------------------------------------------------------------

def test_emit_sec_function_valid_syntax():
    section = _TestSection()
    src = emit_sec_function(section)
    assert isinstance(src, str)
    assert "def sec_test_section" in src
    # Must be syntactically valid Python
    compile(src, "<test>", "exec")


def test_emit_sec_function_callable_returns_none_on_missing(tmp_path):
    """Generated fn returns None when the parquet does not exist."""
    section = _TestSection()
    src = emit_sec_function(section)
    ns: dict = {"clean": lambda v: v, "rd": lambda v: v, "conf_from_n": lambda n, cap=None: "low"}
    exec(compile(src, "<test>", "exec"), ns)  # noqa: S102
    fn = ns["sec_test_section"]
    # parquet doesn't exist -> should return None (use nonexistent cache dir)
    result = fn(1628983, {}, _CACHE_DIR=tmp_path / "nonexistent")
    assert result is None


def test_emit_sec_function_callable_returns_data_when_parquet_exists(tmp_path, monkeypatch):
    """Generated fn returns (data, prov) when entity is present in the parquet."""
    monkeypatch.setattr("src.loop.profile_factory_bridge.CACHE", tmp_path)
    section = _TestSection()
    art = _make_artifact(1628983)
    materialise_parquet(section, [art])

    src = emit_sec_function(section)
    ns: dict = {
        "clean": lambda v: v,
        "rd": lambda v: v,
        "conf_from_n": lambda n, cap=None: "high",
    }
    exec(compile(src, "<test>", "exec"), ns)  # noqa: S102
    fn = ns["sec_test_section"]

    # point the function at our tmp parquet via _CACHE_DIR (= tmp_path, where CACHE was monkeypatched)
    result = fn(1628983, {}, _CACHE_DIR=tmp_path)
    assert result is not None
    data, prov = result
    assert isinstance(data, dict)
    assert isinstance(prov, dict)
    assert prov.get("n") is not None


# ---------------------------------------------------------------------------
# Tests: update_registry
# ---------------------------------------------------------------------------

def test_update_registry_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr("src.loop.profile_factory_bridge.REGISTRY", tmp_path / "reg.json")
    manifest = {"section": "test_section", "entity": "player", "parquet": "x.parquet",
                 "sec_fn": "sec_test_section", "n_entities": 2, "cv_fields": [], "as_of": "2026-05-30"}
    update_registry(manifest)
    reg = json.loads((tmp_path / "reg.json").read_text())
    assert "test_section" in reg
    assert reg["test_section"]["n_entities"] == 2


def test_update_registry_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr("src.loop.profile_factory_bridge.REGISTRY", tmp_path / "reg.json")
    manifest = {"section": "test_section", "entity": "player", "parquet": "x.parquet",
                 "sec_fn": "sec_test_section", "n_entities": 5, "cv_fields": [], "as_of": "2026-05-30"}
    update_registry(manifest)
    update_registry(manifest)
    reg = json.loads((tmp_path / "reg.json").read_text())
    assert len(reg) == 1  # no duplicate


def test_update_registry_dry_run_no_write(tmp_path, monkeypatch):
    reg_path = tmp_path / "reg.json"
    monkeypatch.setattr("src.loop.profile_factory_bridge.REGISTRY", reg_path)
    manifest = {"section": "test_section", "entity": "player", "parquet": "x.parquet",
                 "sec_fn": "sec_test_section", "n_entities": 1, "cv_fields": [], "as_of": None}
    update_registry(manifest, dry_run=True)
    assert not reg_path.exists()


# ---------------------------------------------------------------------------
# Tests: register_section (full round-trip)
# ---------------------------------------------------------------------------

def test_register_section_dry_run(tmp_path, monkeypatch):
    monkeypatch.setattr("src.loop.profile_factory_bridge.CACHE", tmp_path)
    monkeypatch.setattr("src.loop.profile_factory_bridge.REGISTRY", tmp_path / "reg.json")
    section = _TestSection()
    artifacts = [_make_artifact(1628983)]
    result = register_section(section, artifacts, dry_run=True)
    assert result["section"] == "test_section"
    assert result["n_entities"] == 1
    assert not (tmp_path / section.parquet_name()).exists(), "dry_run must not write parquet"
    assert not (tmp_path / "reg.json").exists(), "dry_run must not write registry"


def test_register_section_full_writes(tmp_path, monkeypatch):
    monkeypatch.setattr("src.loop.profile_factory_bridge.CACHE", tmp_path)
    monkeypatch.setattr("src.loop.profile_factory_bridge.REGISTRY", tmp_path / "reg.json")
    section = _TestSection()
    artifacts = [_make_artifact(1628983), _make_artifact(203076)]
    result = register_section(section, artifacts)
    assert (tmp_path / section.parquet_name()).exists()
    assert (tmp_path / "reg.json").exists()
    assert result["n_entities"] == 2
    assert result["as_of"] == "2026-05-30"
    assert "defender_distance_dist" in result["cv_fields"]


def test_register_section_writes_to_store(tmp_path, monkeypatch):
    """register_section calls store.write_atlas for each artifact."""
    monkeypatch.setattr("src.loop.profile_factory_bridge.CACHE", tmp_path)
    monkeypatch.setattr("src.loop.profile_factory_bridge.REGISTRY", tmp_path / "reg.json")

    class _MockStore:
        def __init__(self):
            self.calls = []

        def write_atlas(self, entity_type, entity_id, section_name, as_of, data, prov):
            self.calls.append((entity_type, entity_id, section_name, as_of))

    store = _MockStore()
    section = _TestSection()
    artifacts = [_make_artifact(1628983), _make_artifact(203076)]
    register_section(section, artifacts, store=store)
    assert len(store.calls) == 2
    entity_ids = [c[1] for c in store.calls]
    assert 1628983 in entity_ids and 203076 in entity_ids


def test_register_section_empty_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr("src.loop.profile_factory_bridge.CACHE", tmp_path)
    monkeypatch.setattr("src.loop.profile_factory_bridge.REGISTRY", tmp_path / "reg.json")
    section = _TestSection()
    result = register_section(section, [])
    assert result["n_entities"] == 0
    assert result["section"] == "test_section"


# ---------------------------------------------------------------------------
# Tests: get_sec_function
# ---------------------------------------------------------------------------

def test_get_sec_function_returns_none_for_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr("src.loop.profile_factory_bridge.REGISTRY", tmp_path / "reg.json")
    fn = get_sec_function("nonexistent_section")
    assert fn is None


def test_get_sec_function_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("src.loop.profile_factory_bridge.CACHE", tmp_path)
    monkeypatch.setattr("src.loop.profile_factory_bridge.REGISTRY", tmp_path / "reg.json")
    section = _TestSection()
    artifacts = [_make_artifact(1628983)]
    register_section(section, artifacts)
    fn = get_sec_function("test_section")
    assert fn is not None
    # calling with a non-existent pid returns None
    result = fn(9999999, {}, _CACHE_DIR=tmp_path)
    assert result is None
    # calling with the real pid returns (data, prov)
    result = fn(1628983, {}, _CACHE_DIR=tmp_path)
    assert result is not None
    data, prov = result
    assert "_cv_fields" in data
    assert prov["n"] == 30


# ---------------------------------------------------------------------------
# Tests: _merge_parquet_rows helper
# ---------------------------------------------------------------------------

def test_merge_keeps_old_on_lower_conf():
    old = pd.DataFrame([{"player_id": 1, "confidence": "high", "as_of": "2026-01-01", "pts": 25.0}])
    new = pd.DataFrame([{"player_id": 1, "confidence": "low", "as_of": "2025-01-01", "pts": 10.0}])
    merged = _merge_parquet_rows(old, new, "player_id")
    row = merged[merged["player_id"] == 1].iloc[0]
    assert str(row["confidence"]) == "high"
    assert float(row["pts"]) == 25.0


def test_merge_updates_on_newer_as_of():
    old = pd.DataFrame([{"player_id": 1, "confidence": "med", "as_of": "2025-01-01", "pts": 10.0}])
    new = pd.DataFrame([{"player_id": 1, "confidence": "med", "as_of": "2026-05-30", "pts": 25.0}])
    merged = _merge_parquet_rows(old, new, "player_id")
    row = merged[merged["player_id"] == 1].iloc[0]
    assert str(row["as_of"]) == "2026-05-30"


def test_merge_preserves_absent_entities():
    old = pd.DataFrame([
        {"player_id": 1, "confidence": "high", "as_of": "2026-01-01", "pts": 20.0},
        {"player_id": 2, "confidence": "med", "as_of": "2026-01-01", "pts": 15.0},
    ])
    new = pd.DataFrame([{"player_id": 1, "confidence": "high", "as_of": "2026-05-30", "pts": 22.0}])
    merged = _merge_parquet_rows(old, new, "player_id")
    assert len(merged) == 2
    assert 2 in merged["player_id"].tolist()
