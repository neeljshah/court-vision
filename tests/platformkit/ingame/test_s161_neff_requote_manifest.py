"""Focused integrity checks for the S161 n_eff re-quote evidence archive."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HOLDING = ROOT / "docs/evidence/harness/neff_requote_2026-09-04"
MANIFEST = HOLDING / "manifest.csv"
SOURCE_ARTIFACTS = HOLDING / "source_artifacts.csv"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_s161_manifest_has_all_positions_and_copied_tables_match() -> None:
    with MANIFEST.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) == 45
    assert all(row["status"] in {"RE-QUOTED", "LOST", "RE-LABELLED"} for row in rows)
    assert all(row["selection_rule"] for row in rows)
    # S161 verifier correction: the spec permits LOST rows when the source is truly absent; require a named path instead
    assert all(row.get("source_path") for row in rows if row["status"] == "LOST")

    with SOURCE_ARTIFACTS.open(newline="", encoding="utf-8") as stream:
        artifacts = list(csv.DictReader(stream))

    assert len(artifacts) == 11
    for artifact in artifacts:
        if artifact["artifact_type"] != "COPIED":
            continue
        source = ROOT / artifact["source_path"]
        copied = HOLDING / artifact["artifact_path"]
        assert copied.exists()
        assert _sha256(source) == artifact["sha256"]
        assert _sha256(copied) == artifact["sha256"]

    source_units = ROOT / "data/cache/ingame_grade_joined/mlb"
    copied_units = HOLDING / "S87_mlb_units"
    source_names = sorted(path.name for path in source_units.glob("*.jsonl"))
    copied_names = sorted(path.name for path in copied_units.glob("*.jsonl"))
    assert copied_names == source_names
    assert all(
        _sha256(source_units / name) == _sha256(copied_units / name)
        for name in source_names
    )
