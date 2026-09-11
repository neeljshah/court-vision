"""Prepare-only tests for the fixed G394 negative-design rails."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g394_prepare import (
    EXPECTED_BINDING,
    FROZEN_BARS,
    all_planned_states,
    assert_launch_not_spent,
    assert_split_isolation,
    binding_counts,
    check_binding,
    crop_transform,
    evenly_select,
    rect_contains,
    verify_preregistration,
)
from scripts.platformkit.tracking.g394_q6_scan import scan


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/tracking"
G389 = EVIDENCE / "g389_ball_reference_completion_2026-09-11"
PREREG = EVIDENCE / "g394_ball_person_negatives_2026-09-11/preregistration.md"


def _rows(name: str) -> list[dict[str, str]]:
    with (G389 / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_prereg_seal_reads_file_and_normalizes_crlf(tmp_path: Path):
    raw = PREREG.read_bytes().replace(b"\r\n", b"\n")
    crlf_copy = tmp_path / "preregistration.md"
    crlf_copy.write_bytes(raw.replace(b"\n", b"\r\n"))
    assert verify_preregistration(PREREG) == verify_preregistration(crlf_copy)


def test_binding_full_join_reproduces_the_fixed_dispatch_counts():
    counts = binding_counts(_rows("dev_boxes_v3.csv"), _rows("reference_v3.csv"),
                            _rows("frames_v3.csv"))
    assert counts == EXPECTED_BINDING
    check_binding(counts)
    with pytest.raises(ValueError, match="binding-counts-changed"):
        check_binding({**counts, "dev_boxes": 529})


def test_crop_transform_clips_and_pads_without_changing_the_native_source():
    assert crop_transform(10.0, 10.0, 100, 100) == {
        "source_left": 0, "source_top": 0, "source_right": 100, "source_bottom": 100,
        "dest_left": 150, "dest_top": 150, "dest_right": 250, "dest_bottom": 250,
        "crop_size": 320,
    }
    assert rect_contains(10.0, 10.0, {"x": 10, "y": 10, "width": 0, "height": 0})
    assert not rect_contains(9.9, 10.0, {"x": 10, "y": 10, "width": 2, "height": 2})


def test_even_selection_is_sorted_bounded_and_includes_both_endpoints():
    rows = [{"frame_key": "k%03d" % index, "game": "g", "section": "s",
             "frame_index": str(index)} for index in range(121)]
    selected = evenly_select(list(reversed(rows)))
    assert len(selected) == 120
    assert selected[0]["frame_key"] == "k000"
    assert selected[-1]["frame_key"] == "k120"
    assert len({row["frame_key"] for row in selected}) == 120


def test_heldout_game_or_context_overlap_is_refused():
    development = [{"game": "dev_game", "section": "dev_section"}]
    assert_split_isolation(development, [{"game": "held_game", "section": "held_section"}])
    with pytest.raises(ValueError, match="heldout-game-or-context-overlap"):
        assert_split_isolation(development, [{"game": "dev_game", "section": "held_section"}])
    with pytest.raises(ValueError, match="heldout-game-or-context-overlap"):
        assert_split_isolation(development, [{"game": "held_game", "section": "dev_section"}])


def test_missing_key_stays_in_the_fixed_heldout_denominator():
    keys = ["k%03d" % index for index in range(FROZEN_BARS["heldout_states"])]
    records = all_planned_states(keys, [{"frame_key": keys[0], "status": "OBSERVED"}])
    assert len(records) == 549
    assert records[0]["status"] == "OBSERVED"
    assert records[-1] == {"frame_key": keys[-1], "status": "MISSING_INFERENCE"}


def test_spent_token_restart_is_refused_and_original_bars_are_fixed():
    assert_launch_not_spent({"training_charged": False}, "training")
    with pytest.raises(ValueError, match="spent-token-restart-refused"):
        assert_launch_not_spent({"candidate_inference_charged": True}, "candidate_inference")
    assert FROZEN_BARS == {
        "c0_min": 0.25, "precision_wilson_lower_min": 0.90,
        "all_fp_per_absent_max": 0.01, "heldout_states": 549,
        "visible_states": 302, "absent_states": 188, "unknown_states": 59,
        "candidate_conf": 0.05,
    }


def test_two_rater_acceptance_rule_excludes_without_replacement():
    from scripts.platformkit.tracking.g394_audit import adjudicate, verdict

    no_ball = {"ball_state": "NO_BALL_VISIBLE", "uncertainty": "LOW"}
    assert verdict(no_ball, no_ball) == (1, "")
    assert verdict(no_ball, None)[0] == 0
    assert verdict({"ball_state": "BALL_AT_MARKER", "uncertainty": "LOW"}, no_ball)[0] == 0
    assert verdict(no_ball, {"ball_state": "NO_BALL_VISIBLE", "uncertainty": "HIGH"})[0] == 0
    manifest = [{"packet_id": "G394-000-" + "0" * 16, "frame_key": "k0", "game": "g",
                 "section": "s", "frame_index": "1", "call_cx": "1", "call_cy": "2",
                 "crop_sha256": "d"}]
    ratings = [{"packet_id": manifest[0]["packet_id"], "rater": rater,
                "ball_state": "BALL_AT_MARKER", "uncertainty": "LOW"}
               for rater in ("terra", "sol")]
    _agreement, accepted, counts = adjudicate(manifest, ratings)
    assert accepted == [] and counts["excluded"] == 1 and counts["selected"] == 1


def test_landed_audit_and_scored_result_match_the_memo():
    evidence = EVIDENCE / "g394_ball_person_negatives_2026-09-11"
    counts = json.loads((evidence / "audit_counts.json").read_text(encoding="utf-8"))
    assert (counts["accepted"], counts["accepted_games"], counts["excluded"]) == (49, 15, 6)
    assert counts["accepted_unique_frames"] == counts["accepted"]
    summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
    a10 = summary["arms"]["A10"]
    assert (a10["tp"], a10["fp"], a10["n_visible"] - a10["tp"]) == (84, 156, 218)
    assert a10["n_frames"] == FROZEN_BARS["heldout_states"]
    assert not any(summary["bars"]["A10"][name]
                   for name in ("c0_met", "precision_met", "all_fp_met"))


def test_q6_scan_covers_every_g394_text_artifact():
    evidence = EVIDENCE / "g394_ball_person_negatives_2026-09-11"
    exts = {".csv", ".json", ".md", ".txt", ".yaml"}
    paths = sorted(p for p in evidence.rglob("*") if p.is_file() and p.suffix in exts)
    paths += sorted((ROOT / "scripts/platformkit/tracking").glob("g394_*.py"))
    paths += [EVIDENCE / "g394_ball_person_negatives_2026-09-11.md", Path(__file__)]
    assert len(paths) > 40
    assert scan(paths) == {}
