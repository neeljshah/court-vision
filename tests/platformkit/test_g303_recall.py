"""G303 per-file test: synthetic boxes exercise the footpoint, matching and CI rules,
and the sealed settings (frame indices, tolerances, conf, denominators) are pinned."""
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.platformkit.tracking.g298_compare import exact_mcnemar, read_csv
from scripts.platformkit.tracking.g303_overlay import positions
from scripts.platformkit.tracking.g303_recall_vs_resolution import (
    ARM_CONF, ARM_IMGSZ, ARMS, PRIMARY, REGISTERED_CONF, TOLERANCES, assign,
    foot, score_arm)
from scripts.platformkit.tracking.g303_report import bootstrap_ci, score, score_basis

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "evidence" / "tracking"
FRAMES_CSV = EVIDENCE / "g296a_located_players_artifact" / "frames.csv"
GROUND_TRUTH = EVIDENCE / "g296_ground_truth_2026-09-07.csv"
PASS_A = EVIDENCE / "g296a_located_players_artifact" / "located_players.csv"
PASS_B = EVIDENCE / "g296b_located_players_artifact" / "located_players.csv"
ARTIFACT = EVIDENCE / "g303_artifact"
# The fix-1b candidate the verifier REJECTed on B2 -- its committed g303_report.json is the
# pre-alias reference every existing field must still reproduce byte-for-byte.
PRE_ALIAS_SHA = "61fa77b38a4cb0ec86c1d9d956d7eb8204fef481"
# Fix 1d added seven legacy cost aliases to entry["arms"][arm]; this full fixture carries
# every meta[arm] key those aliases can read, for tests that check the alias VALUES.
META = {arm: {"imgsz": 640, "conf": 0.3, "conf_source": "registered", "total_detections": 0,
              "detections_per_frame": 0.0, "ms_per_frame": 0.0, "peak_vram_mib": 0.0,
              "pose_served_frames": [], "errors": 0} for arm in ARMS}
# Fix 1e (B2 CORRECTION 1): the pre-31a legacy CLI/META contract -- only imgsz/conf/conf_source
# per arm. score_basis must still succeed on this minimal shape (`.get(key, None)` reads).
LEGACY_META = {arm: {"imgsz": 640, "conf": 0.3, "conf_source": "registered"} for arm in ARMS}


def _artifact_copy(tmp_path):
    """Copy the committed arm outputs into tmp_path so score() can regenerate a report
    without touching the sealed docs/evidence/tracking/g303_artifact/ directory."""
    for name in ("g303_detect.json", *(f"{a}.csv" for a in ARMS)):
        shutil.copy(ARTIFACT / name, tmp_path / name)
    return tmp_path


def test_footpoint_is_bottom_centre_and_carries_the_crop_offset_back():
    # A box in a TOPCUT-cropped 1020-high frame maps back into native 1080 coordinates.
    assert foot([100, 10, 200, 500], 1920, 1020, 60) == (150, 560)
    # y2 past the fed frame height is clipped BEFORE the offset is added back.
    assert foot([0, 0, 40, 5000], 1920, 1020, 60) == (20, 1080)
    # Integer truncation matches production: 100.9 and 201.9 truncate to 100 and 201.
    assert foot([100.9, 0.0, 201.9, 300.9], 1920, 1020, 0) == (150, 300)


def test_one_to_one_refuses_to_let_one_detection_claim_two_ground_truth_points():
    truth = [(100.0, 100.0), (110.0, 100.0)]
    one_box = [(105.0, 100.0)]
    # The nearest rule would call both found; the sealed one-to-one rule allows one.
    assert sum(assign(truth, one_box, 50)) == 1
    assert sum(assign(truth, [(100.0, 100.0), (110.0, 100.0)], 50)) == 2


def test_assignment_respects_the_tolerance_and_the_empty_cases():
    truth = [(0.0, 0.0)]
    assert assign(truth, [(0.0, 60.0)], 50) == [False]
    assert assign(truth, [(0.0, 60.0)], 100) == [True]
    assert assign(truth, [], 100) == [False]
    assert assign([], [(0.0, 0.0)], 100) == []


def test_box_spam_cannot_inflate_one_to_one_recall_but_does_move_the_nearest_rule():
    by_frame = {7: [(500.0, 500.0), (900.0, 500.0)]}
    spam = {7: [(500.0 + i, 500.0 + i) for i in range(40)]}
    scored = score_arm(by_frame, spam, [7])
    # Forty boxes clustered on one player still match exactly one point one-to-one.
    assert scored["hits"][50][7] == 1
    # The G298-comparable nearest rule is reported separately and is not the headline.
    assert sum(scored["nearest_rule"][50]) == 1
    assert scored["median_nearest_px"] is not None
    lean = score_arm(by_frame, {7: [(500.0, 505.0), (900.0, 505.0)]}, [7])
    assert lean["hits"][50][7] == 2
    assert lean["one_to_one"][50] == [True, True]


def test_the_flag_vector_is_per_point_so_mcnemar_pairs_the_same_players():
    by_frame = {1: [(10.0, 10.0), (900.0, 900.0)]}
    low = score_arm(by_frame, {1: [(10.0, 12.0)]}, [1])
    high = score_arm(by_frame, {1: [(900.0, 902.0)]}, [1])
    # Same count, different players: an unpaired test would see no change at all.
    assert sum(low["one_to_one"][50]) == sum(high["one_to_one"][50]) == 1
    assert low["one_to_one"][50] == [True, False]
    assert high["one_to_one"][50] == [False, True]
    result = exact_mcnemar(low["one_to_one"][50], high["one_to_one"][50])
    assert result["discordant"] == 2 and result["lost"] == 1 and result["gained"] == 1


def test_bootstrap_is_seeded_paired_and_brackets_the_point_estimate():
    hits, ns = [3, 4, 2, 5], [6, 6, 6, 6]
    first = bootstrap_ci(hits, ns)
    assert first == bootstrap_ci(hits, ns)  # seeded: same interval every run
    point = sum(hits) / sum(ns)
    assert first[0] <= point <= first[1] and 0.0 <= first[0] <= first[1] <= 1.0
    # A paired delta against an arm that finds strictly more is positive throughout.
    better = [h + 1 for h in hits]
    delta = bootstrap_ci(hits, ns, paired=better)
    assert delta[0] > 0.0 and delta[1] <= 1.0
    # Sign convention: delta = R minus P, so the worse arm gives a negative interval.
    assert bootstrap_ci(better, ns, paired=hits)[1] < 0.0


def test_the_registered_settings_are_pinned_and_arm_P22_keeps_the_route_conf():
    # The three REGISTERED tolerances; the rejected candidate's 40 px column is gone.
    assert TOLERANCES == (25, 50, 100)
    assert REGISTERED_CONF == 0.3
    assert all(ARM_CONF[arm] == 0.3 for arm in ("P", "P_repeat", "R", "M"))
    # P22 is the route exactly as it runs: its conf is never overridden by the harness.
    assert ARM_CONF["P22"] is None
    assert ARM_IMGSZ["R"] == 1920 and ARM_IMGSZ["M"] == 1280
    assert ARM_IMGSZ["P"] == ARM_IMGSZ["P_repeat"] == ARM_IMGSZ["P22"]  # the route value


def test_the_24_frame_indices_are_the_sealed_formula():
    ids = [int(r["source_frame"]) for r in read_csv(FRAMES_CSV)]
    assert ids == [round(i * 174429 / 23) for i in range(24)]
    assert len(ids) == len(set(ids)) == 24


def test_the_primary_denominator_is_the_113_adjudicated_points_over_16_frames():
    assert PRIMARY == "adjudicated_113"
    points = [r for r in read_csv(GROUND_TRUTH) if r["source"] != "dropped"]
    assert len(points) == 113
    assert len({int(r["frame_id"]) for r in points}) == 16


def test_every_basis_recomputes_its_own_numerator_instead_of_recycling_the_primary():
    dets = {arm: {1: [(100.0, 100.0)]} for arm in ARMS}
    primary, _, _ = score_basis(PRIMARY, [(1, 100.0, 100.0)], dets, META)
    secondary, _, _ = score_basis("pass_A_131", [(1, 900.0, 900.0)], dets, META)
    assert primary["arms"]["P"]["recall"][50]["matched"] == 1
    assert primary["arms"]["P"]["recall"][50]["denominator"] == 1
    # The secondary is matched against ITS OWN points: 0, never the primary's 1.
    assert secondary["arms"]["P"]["recall"][50]["matched"] == 0
    assert secondary["arms"]["P"]["recall"][50]["denominator"] == 1
    assert "pass_A_131" in secondary["denominator_name"]


def test_score_basis_still_accepts_the_pre_31a_three_key_meta():
    # B2 CORRECTION 1: the legacy three-key META call (imgsz/conf/conf_source only, no cost
    # fields) must not KeyError on the six newer meta[arm] reads fix 1d added.
    dets = {arm: {1: [(100.0, 100.0)]} for arm in ARMS}
    entry, _, _ = score_basis(PRIMARY, [(1, 100.0, 100.0)], dets, LEGACY_META)
    arm_p = entry["arms"]["P"]
    # The legacy fields still compute correctly off the minimal META.
    assert arm_p["imgsz"] == 640 and arm_p["conf"] == 0.3 and arm_p["conf_source"] == "registered"
    assert arm_p["recall"][50]["matched"] == 1 and arm_p["recall"][50]["denominator"] == 1
    # The six new aliases are present but null -- absent metadata, never fabricated.
    for key in ("total_detections_24_frames", "detections_per_frame_24", "ms_per_frame",
                "peak_vram_mib", "pose_served_frames", "downstream_errors"):
        assert arm_p[key] is None, key


def test_the_eye_check_samples_six_evenly_spaced_frames_and_never_a_head_slice():
    assert positions() == [0, 5, 9, 14, 18, 23]
    assert len(set(positions())) == 6 and max(positions()) == 23


def test_ground_truth_is_optional_again_and_the_legacy_top_level_paths_alias_the_new_ones(tmp_path):
    # The "old way" CLI call the fix-1b REJECT broke: no --ground-truth at all (B2).
    args = SimpleNamespace(ground_truth=None, pass_a=PASS_A, pass_b=PASS_B,
                            output=_artifact_copy(tmp_path))
    report = score(args)
    assert report["bases"][PRIMARY]["denominator_name"].startswith("86 ")  # consensus fallback
    primary = report["bases"][PRIMARY]
    assert report["primary_denominator"] == primary["denominator"]
    assert report["primary_denominator_name"] == primary["denominator_name"]
    assert report["primary_frame_ids"] == primary["frame_ids"]
    assert report["arms"] == primary["arms"]
    assert report["paired_R_vs_P"] == primary["paired_R_vs_P"]
    # CORRECTION 3: the legacy `basis` name reads "consensus" when falling back, matching the
    # e82b702fc snapshot which was itself a no-ground-truth, consensus-basis run.
    assert report["basis"] == "consensus"
    assert report["secondary_denominators"] == {"pass_A_only": 131, "pass_B_only": 130}


def _assert_subset_equal(fresh, before, path="$"):
    """Every path/value inside `before` must exist and match in `fresh`; `fresh` may carry
    ADDITIONAL keys (fix 1d adds legacy per-arm aliases nested inside `bases`, so a blanket
    `==` no longer holds -- but nothing pre-existing may move or change)."""
    if isinstance(before, dict):
        for k, v in before.items():
            assert k in fresh, f"{path}.{k} missing"
            _assert_subset_equal(fresh[k], v, f"{path}.{k}")
    else:
        assert fresh == before, path


def test_report_regeneration_reproduces_every_pre_alias_field_byte_for_byte(tmp_path):
    # Same call the sealed row used (real --ground-truth); adding aliases must move nothing.
    args = SimpleNamespace(ground_truth=GROUND_TRUTH, pass_a=PASS_A, pass_b=PASS_B,
                            output=_artifact_copy(tmp_path))
    score(args)
    # Compare through the SAME json round-trip as the committed file (tolerance keys are
    # ints in the live Python dict but strings once written/read as JSON).
    fresh = json.loads((tmp_path / "g303_report.json").read_text())
    before = json.loads(subprocess.run(
        ["git", "show", f"{PRE_ALIAS_SHA}:docs/evidence/tracking/g303_artifact/g303_report.json"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout)
    for key in ("tolerances_px", "registered_conf", "step0", "sign_convention",
                "arm_P_byte_identical_repeat", "arm_cost"):
        assert fresh[key] == before[key], key
    _assert_subset_equal(fresh["bases"], before["bases"], "bases")


def _walk_legacy_paths(node, prefix=""):
    """Yield every DICT key path in a JSON tree; lists are leaves (existence only, since
    frame/point lists legitimately differ in length between report versions). Does NOT skip
    the "40" branch -- the waiver is asserted explicitly by the caller, not baked in here."""
    if isinstance(node, dict):
        for k, v in node.items():
            path = f"{prefix}.{k}" if prefix else k
            yield path
            yield from _walk_legacy_paths(v, path)


def _path_exists(node, path):
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def test_legacy_schema_paths_present_except_the_rejected_40px_branch_waiver(tmp_path):
    # CORRECTION 3: B2 compatibility must be checked recursively against the ORIGINAL
    # e82b702fc schema, not only against the immediately-prior 61fa77b38 candidate.
    # NEW GAP fix: the ONE named, intentional waiver is the "40" px tolerance branch (B10
    # PASS -- this candidate registers 25/50/100 px only, 40 was dropped). Every OTHER
    # legacy path must still exist; asserted exactly, not silently skipped.
    try:
        raw = subprocess.run(
            ["git", "show", "e82b702fc:docs/evidence/tracking/g303_artifact/g303_report.json"],
            cwd=ROOT, capture_output=True, text=True, check=True, timeout=10).stdout
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pytest.skip("git unavailable")
    legacy = json.loads(raw)
    args = SimpleNamespace(ground_truth=GROUND_TRUTH, pass_a=PASS_A, pass_b=PASS_B,
                            output=_artifact_copy(tmp_path))
    fresh = json.loads(json.dumps(score(args)))  # normalize int tolerance keys to JSON strings
    missing = [p for p in _walk_legacy_paths(legacy) if not _path_exists(fresh, p)]
    waived = [p for p in missing if "40" in p.split(".")]
    assert waived, "expected the 40 px branch to account for at least one missing path"
    assert set(missing) == set(waived), sorted(set(missing) - set(waived))
