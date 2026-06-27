"""Per-file tests for the ingest manifest provenance contract (core + NBA).

Covers structural validation, pregame_corpora leak filtering, validate_against_
inventory on synthetic census, and a GUARDED check of NBA_MANIFEST against the REAL
data_registry census (ties Phase 0 + Phase 1 on live data).

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/platformkit/test_ingest_manifest.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.ingest_manifest_core import (
    LEAK_IN_GAME,
    LEAK_POST_GAME,
    LEAK_PRE_GAME,
    LEAK_REFERENCE,
    IngestManifest,
    IngestSource,
)
from domains.basketball_nba.ingest_manifest import NBA_MANIFEST


def test_nba_manifest_is_structurally_valid():
    assert NBA_MANIFEST.validate() == []


def test_bad_leak_class_duplicate_and_sla_detected():
    bad = IngestManifest("x", (
        IngestSource("a", "not_a_class"),
        IngestSource("b", LEAK_PRE_GAME, sla_minutes=0),
        IngestSource("b", LEAK_PRE_GAME),  # duplicate corpus
    ))
    errs = bad.validate()
    assert any("bad leak_class" in e for e in errs)
    assert any("sla_minutes must be > 0" in e for e in errs)
    assert any("duplicate corpus" in e for e in errs)


def test_pregame_corpora_excludes_in_and_post_game():
    m = IngestManifest("x", (
        IngestSource("sched", LEAK_PRE_GAME),
        IngestSource("surface", LEAK_REFERENCE),
        IngestSource("ls", LEAK_IN_GAME),
        IngestSource("box", LEAK_POST_GAME),
    ))
    assert set(m.pregame_corpora()) == {"sched", "surface"}


def test_validate_against_inventory_flags_absent_and_empty():
    inv = {"rows": [
        {"sport": "x", "name": "sched", "is_empty": False},
        {"sport": "x", "name": "odds", "is_empty": True},      # present but empty
        # "box" entirely absent
        {"sport": "other", "name": "box", "is_empty": False},  # wrong sport -> ignored
    ]}
    m = IngestManifest("x", (
        IngestSource("sched", LEAK_PRE_GAME),
        IngestSource("odds", LEAK_PRE_GAME),
        IngestSource("box", LEAK_POST_GAME),
    ))
    errs = m.validate_against_inventory(inv)
    assert any("odds" in e and "0-row" in e for e in errs)
    assert any("box" in e and "absent" in e for e in errs)
    assert not any("sched" in e for e in errs)


def test_nba_manifest_against_real_census():
    """All NBA-declared sources exist and are non-empty in the live census."""
    try:
        from data_registry.inventory import build_inventory  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"data_registry unavailable: {exc}")
    inv = build_inventory(sports=["basketball_nba"])
    if inv["n_corpora"] == 0:
        pytest.skip("no NBA corpora on disk")
    errs = NBA_MANIFEST.validate_against_inventory(inv)
    assert errs == [], f"manifest/census mismatch: {errs}"
