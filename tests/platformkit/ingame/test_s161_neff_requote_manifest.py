"""Focused integrity checks for the S161 n_eff re-quote evidence archive."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HOLDING = ROOT / "docs/evidence/harness/neff_requote_2026-09-04"
MANIFEST = HOLDING / "manifest.csv"
SOURCE_ARTIFACTS = HOLDING / "source_artifacts.csv"
DIRECT = HOLDING / "direct_requotes.csv"
INVENTORY = HOLDING / "source_inventory.csv"
S196_IDS = {
    "S87b_S80_embargo1_precise", "S87b_S80_embargo0", "S87b_S80_embargo1_rounded",
    "S137_S102", "S137_S82_before", "S137_S82_after", "S137_S87_before", "S137_S87_after",
    "S137_S112_nba_before", "S137_S112_nba_after", "S137_S112_mlb_before", "S137_S112_mlb_after",
    "S137_S114_before", "S137_S114_after", "S137_S116_before", "S137_S116_after",
    "S137_S119_before", "S137_S119_after", "S137_S121_before", "S137_S121_after",
    "S137_S102_recap", "S137_S103", "S137_S115",
}
S119_SOURCE = "data/cache/eval_gate/s119_real_game_series_2026-09-03.csv"


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


def test_s196_direct_requotes_preserve_source_provenance_and_file_counts() -> None:
    with MANIFEST.open(newline="", encoding="utf-8") as stream:
        manifest = {row["readout_id"]: row for row in csv.DictReader(stream)}
    with DIRECT.open(newline="", encoding="utf-8") as stream:
        direct = list(csv.DictReader(stream))
    with INVENTORY.open(newline="", encoding="utf-8") as stream:
        inventory = {row["source_path"]: row for row in csv.DictReader(stream)}

    assert {row["readout_id"] for row in direct} == S196_IDS
    assert all(manifest[readout_id]["status"] == "RE-QUOTED" for readout_id in S196_IDS)
    assert all(manifest[readout_id]["source_path"] == row["source_path"] for readout_id, row in
               ((row["readout_id"], row) for row in direct))
    for row in direct:
        source = ROOT / row["source_path"]
        assert source.exists()
        assert _sha256(source) == row["source_sha256"]
        assert int(row["source_row_count"]) == int(row["source_file_rows"])
        assert int(row["source_file_rows"]) >= int(row["n_ticks"])
        assert inventory[row["source_path"]]["row_count"] == row["source_file_rows"]

    s119_ids = ["S137_S119_before", "S137_S119_after", "S137_S121_before", "S137_S121_after"]
    s119 = {row["readout_id"]: row for row in direct if row["readout_id"] in s119_ids}
    assert set(s119) == set(s119_ids)
    assert all(row["source_path"] == S119_SOURCE for row in s119.values())
    assert [int(s119[key]["n_ticks"]) for key in s119_ids] == [15702, 15702, 15528, 15162]
    assert [int(s119[key]["n_games"]) for key in s119_ids] == [88, 76, 76, 73]
