"""Prepare-only rails for G398's fixed paired DEV shadow."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g398_prepare import (
    DEV_KEYS,
    assert_heldout_isolation,
    charge_paired_launch,
    continuation_met,
    frame_flags,
    preserve_planned_keys,
    roundtrip_native,
    validate_dev_inputs,
    verify_preregistration,
)
from scripts.platformkit.tracking.g398_q6_scan import scan


ROOT = Path(__file__).resolve().parents[2]
TRACKING = ROOT / "docs/evidence/tracking"
G389 = TRACKING / "g389_ball_reference_completion_2026-09-11"
G398 = TRACKING / "g398_a8_high_resolution_dev_shadow_2026-09-11"
PREREG = G398 / "preregistration.md"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_prereg_seal_reads_the_file_and_normalizes_crlf(tmp_path: Path):
    raw = PREREG.read_bytes().replace(b"\r\n", b"\n")
    copied = tmp_path / "preregistration.md"
    copied.write_bytes(raw.replace(b"\n", b"\r\n"))
    assert verify_preregistration(PREREG) == verify_preregistration(copied)


def test_full_dev_manifest_and_heldout_context_are_isolated():
    frames = _rows(G389 / "frames_v3.csv")
    reference = _rows(G389 / "reference_v3.csv")
    boxes = _rows(G389 / "dev_boxes_v3.csv")
    assert validate_dev_inputs(frames, reference, boxes) == {
        "dev_keys": 1071, "heldout_keys": 549, "box_keys": 530,
        "box_games": 27, "heldout_games": 32,
    }
    dev = [row for row in frames if row["split"] == "development"]
    heldout = [row for row in frames if row["split"] == "heldout"]
    assert_heldout_isolation(dev, heldout)
    with pytest.raises(ValueError, match="heldout-or-context-overlap-frame_key"):
        assert_heldout_isolation(dev + [heldout[0]], heldout)


def test_unknown_observations_are_false_positives_and_scale_roundtrips():
    assert frame_flags("UNKNOWN", 2, 0) == (0, 2)
    assert frame_flags("ABSENT", 1, 0) == (0, 1)
    assert frame_flags("VISIBLE", 2, 1) == (1, 1)
    with pytest.raises(ValueError, match="nonvisible-match-refused"):
        frame_flags("UNKNOWN", 1, 1)
    assert roundtrip_native(1536.25, 1080) == pytest.approx(1536.25)


def test_missing_keys_stay_in_the_full_dev_denominator():
    keys = ["k%04d" % index for index in range(DEV_KEYS)]
    records = preserve_planned_keys(keys, {keys[0]: {"frame_key": keys[0], "status": "OBSERVED"}})
    assert len(records) == DEV_KEYS
    assert records[0]["status"] == "OBSERVED"
    assert records[-1] == {"frame_key": keys[-1], "status": "MISSING_INFERENCE"}


def test_one_paired_launch_is_immutable_and_dev_ties_fail(tmp_path: Path):
    with pytest.raises(ValueError, match="second-paired-launch-refused"):
        token = tmp_path / "paired_launch.json"
        charge_paired_launch(token, {"a8": "a"})
        charge_paired_launch(token, {"a8": "a"})
    baseline = {"c0": 0.1, "precision_wilson_lo": 0.2, "all_fp_per_absent": 0.3}
    assert not continuation_met(baseline, dict(baseline))
    assert continuation_met(baseline, {"c0": 0.1001, "precision_wilson_lo": 0.2,
                                       "all_fp_per_absent": 0.3})


def test_q6_scan_covers_all_current_g398_text_artifacts():
    paths = sorted(path for path in G398.rglob("*") if path.is_file() and path.suffix in
                   {".csv", ".json", ".md", ".txt", ".yaml"})
    paths += sorted((ROOT / "scripts/platformkit/tracking").glob("g398_*.py"))
    paths += [TRACKING / "g398_a8_high_resolution_dev_shadow_2026-09-11.md", Path(__file__)]
    existing = [path for path in paths if path.exists()]
    assert scan(existing) == {}


def _json(name: str) -> dict:
    return json.loads((G398 / name).read_text(encoding="ascii"))


def test_step0_receipts_reproduce_the_landed_549_counts_and_the_weight_digest():
    assertions = _json("split_assertions.json")
    assert assertions["preregistration_seal"] == verify_preregistration(PREREG)
    assert [assertions[name] for name in ("key_overlap", "game_overlap", "section_overlap")] \
        == [0, 0, 0]
    assert assertions["dev_keys"] == DEV_KEYS and assertions["heldout_keys"] == 549
    assert assertions["heldout_games"] == 32 and assertions["sheets_verified"] == DEV_KEYS
    assert assertions["dev_labels"] == {"VISIBLE": 531, "ABSENT": 425, "UNKNOWN": 115}
    assert assertions["dev_boxes"] == 530 and assertions["dev_box_games"] == 27
    reproduced = assertions["g394_reproduced_counts"]
    assert {arm: value[:3] for arm, value in reproduced.items()} == {
        "A0": [0, 8, 302], "A8": [90, 169, 212], "A10": [84, 156, 218]}
    assert all(value[3] == 549 for value in reproduced.values())
    assert _json("weight_receipts.json")["sha256"] == (
        "0f05a61618687bda2005ce4ac8343c5987f60ba0076245597de59f7380398762")


def test_one_paired_launch_covered_every_dev_key_and_no_heldout_key():
    launch = _json("launch_accounting.json")
    assert launch["paired_launches"] == 1 and launch["state"] == "SPENT_COMPLETE"
    assert launch["bins"] == 30 and launch["dev_keys"] == DEV_KEYS
    assert launch["result"]["gpu_stage_seconds"] <= launch["gpu_stage_deadline_seconds"]
    dev = {row["frame_key"] for row in _rows(G398 / "dev_manifest.csv")}
    held = {row["frame_key"] for row in _rows(G389 / "frames_v3.csv")
            if row["split"] == "heldout"}
    for name, arm, size in (("predictions_960.csv", "A8_IMG960", "960"),
                            ("predictions_1920.csv", "A8_IMG1920", "1920")):
        table = _rows(G398 / name)
        keys = [row["frame_key"] for row in table]
        assert preserve_planned_keys(sorted(dev), {}) and len(keys) == DEV_KEYS
        assert set(keys) == dev and not set(keys) & held
        assert {row["arm"] for row in table} == {arm}
        assert {row["imgsz"] for row in table} == {size}
        assert {row["conf"] for row in table} == {"0.05"}
        silent = [row for row in table if row["tick_history"] == "NO_DETECTION"]
        assert silent and all(row["rank"] != "0" and row["x"] == "" for row in silent)


def test_measured_dev_continuation_fails_and_historical_bars_stay_untested():
    summary = _json("summary.json")
    baseline, candidate = summary["arms"]["A8_IMG960"], summary["arms"]["A8_IMG1920"]
    assert [baseline["tp"], baseline["fp"], baseline["fn"]] == [251, 198, 280]
    assert [candidate["tp"], candidate["fp"], candidate["fn"]] == [121, 310, 410]
    assert baseline["n_dev"] == candidate["n_dev"] == DEV_KEYS
    assert baseline["n_absent"] == candidate["n_absent"] == 425
    assert not continuation_met(baseline, candidate)
    assert summary["continuation_met"] is False
    assert summary["verdict"] == "CLOSED AT LIMIT for this option"
    assert set(summary["continuation_components"].values()) == {False}
    assert summary["historical_bars"] == {"c0_min": 0.25, "precision_wilson_lower_min": 0.90,
                                          "all_fp_per_absent_max": 0.01,
                                          "tested_by_this_row": False}
    assert summary["heldout_inferences"] == 0


def test_paired_records_repeats_and_eye_cards_keep_every_planned_state():
    paired = _rows(G398 / "paired_scores.csv")
    assert len(paired) == DEV_KEYS
    assert sum(1 for row in paired if row["in_dev_boxes"] == "1") == 530
    assert {row["label"] for row in paired} == {"VISIBLE", "ABSENT", "UNKNOWN"}
    repeats = _json("repeats.json")
    assert repeats["identical"] is True
    assert repeats["replay_1"] == repeats["primary"] == repeats["replay_2"]
    cards = _rows(G398 / "eye_index.csv")
    assert len(cards) == 30
    assert {row["label"] for row in cards} == {"VISIBLE", "ABSENT", "UNKNOWN"}
    assert "NO_DETECTION" in {row["case_960"] for row in cards}
    assert all((G398 / "renders" / row["render"]).is_file() for row in cards)
