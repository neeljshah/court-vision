"""Construct and arithmetic tests for the G401 duration-cap measurement."""
import subprocess
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g393_parser_harness import extract_build_command
from scripts.platformkit.tracking.g401_census import (
    even_draw,
    parse_rate,
    shadow_population,
    split_name,
    validated_fps,
)
from scripts.platformkit.tracking.g401_measure import (
    paired_caps,
    policy_row,
    policy_totals,
    pts_summary,
)
from scripts.platformkit.tracking.g401_prereg import q6_hit_counts, verify_prereg
from scripts.platformkit.tracking.g401_proposal import (
    build_fixtures,
    fixture_source,
    load_candidate,
    read_parser,
    reader_survey,
)
from scripts.platformkit.tracking.g401_timebase import (
    cap_loss,
    capped_pts_receipt,
    policy_status,
    pts_are_constant_rate,
    validated_frame_cap,
)

EVIDENCE = Path("docs/evidence/tracking/g401_fps_cap_duration_shadow_2026-09-11")
DAEMON = Path("scripts/platformkit/track_daemon.py")
DIFF = EVIDENCE / "PROPOSED_g401_fps_cap.diff"
NTSC_60 = 60000.0 / 1001.0


def _population(count, fps=NTSC_60, span=130.0):
    rows = []
    for index in range(count):
        rows.append({"name": "nba__g%02d_s90.mp4" % index, "competition": "nba",
                     "game": "g%02d" % index, "section": 90,
                     "validated_fps": fps, "fps_basis": "TWO_READER_AGREEMENT",
                     "stream_duration_s": span, "height": 720, "nb_frames": 7800,
                     "bytes": 1, "mtime_epoch": 0, "avg_frame_rate": "x",
                     "r_frame_rate": "y", "width": 1280, "codec": "h264",
                     "format_duration_s": span})
    digests = {row["name"]: "%064d" % index for index, row in enumerate(rows)}
    return rows, digests


# --- sealed cap arithmetic -------------------------------------------------

def test_rational_fps_rounding_and_unknown_fallback() -> None:
    assert validated_frame_cap(29.97, pts_valid=True) == (2997, "VALIDATED_FPS")
    assert validated_frame_cap(59.94, pts_valid=True) == (5994, "VALIDATED_FPS")
    assert validated_frame_cap(NTSC_60, pts_valid=True) == (5995, "VALIDATED_FPS")
    assert validated_frame_cap(60.0, pts_valid=True) == (6000, "VALIDATED_FPS")
    assert validated_frame_cap(None, pts_valid=False) == (3000, "UNKNOWN")


def test_short_source_eof_has_no_cap_loss() -> None:
    pts = [index / 30.0 for index in range(90)]
    receipt = capped_pts_receipt(pts, start_index=0, frame_cap=3000, fps=30.0)
    assert receipt["status"] == "EOF"
    assert receipt["admitted_count"] == 90
    assert cap_loss(receipt) == 0.0


def test_irregular_pts_rejects_validated_fps() -> None:
    assert not pts_are_constant_rate([0.0, 1 / 60, 2 / 60 + 0.01], 60.0)
    assert validated_frame_cap(60.0, pts_valid=False) == (3000, "UNKNOWN")


def test_first_excluded_frame_and_60fps_extent() -> None:
    pts = [index / 60.0 for index in range(7000)]
    receipt = capped_pts_receipt(pts, start_index=0, frame_cap=6000, fps=60.0)
    assert receipt["first_excluded_index"] == 6000
    assert receipt["first_excluded_pts"] == 100.0
    assert cap_loss(receipt) == 0.0


def test_source_count_is_not_capped_count() -> None:
    receipt = capped_pts_receipt([index / 60.0 for index in range(7000)],
                                 start_index=0, frame_cap=3000, fps=60.0)
    assert receipt["admitted_count"] == 3000
    assert receipt["first_excluded_index"] == 3000
    assert cap_loss(receipt) == 50.0


def test_zero_loss_refuses_unknown() -> None:
    assert policy_status([0.0, None]) == "PARTIAL_UNKNOWN"
    assert policy_status([0.0, 0.0]) == "ZERO_LOSS"
    assert policy_status([0.0, 5.1]) == "POSITIVE_LOSS"


# --- census, readers and the sealed draw -----------------------------------

def test_two_reader_agreement_and_disagreement() -> None:
    assert parse_rate("60000/1001") == pytest.approx(NTSC_60)
    assert parse_rate("0/0") is None
    value, basis = validated_fps("721800000/12042029", "60000/1001")
    assert basis == "TWO_READER_AGREEMENT"
    assert value == pytest.approx(NTSC_60)
    assert validated_fps("30/1", "60000/1001")[1] == "READER_DISAGREEMENT"
    assert validated_fps(None, "60/1")[1] == "UNKNOWN_READER"


def test_split_name_and_population_floors() -> None:
    assert split_name("ncaa_basketball__s-0Y7aLxXgM_s4830.mp4") == (
        "ncaa_basketball", "s-0Y7aLxXgM", 4830)
    rows, digests = _population(3, span=99.0)
    assert shadow_population(rows, digests) == []
    rows, digests = _population(3, fps=30.0)
    assert shadow_population(rows, digests) == []


def test_even_draw_is_deterministic_without_replacement() -> None:
    rows, digests = _population(89)
    population = shadow_population(rows, digests)
    assert len(population) == 89
    drawn = even_draw(population)
    indices = [item["draw_index"] for item in drawn]
    assert len(set(indices)) == 30
    assert indices == sorted(indices)
    assert indices[0] == 0 and indices[-1] == 88
    assert even_draw(population) == drawn
    short, short_digests = _population(29)
    with pytest.raises(ValueError):
        even_draw(shadow_population(short, short_digests))


# --- window policy arithmetic ----------------------------------------------

def test_policy_row_attributes_cap_eof_failure_and_absent_source() -> None:
    summary = pts_summary([index / 60.0 for index in range(7800)], 60.0)
    assert summary["rate_validated"] and summary["uniform_steps"]
    assert summary["duplicate_pts_steps"] == 0
    assert summary["dropped_frames"] == 0
    dropped = pts_summary([0.0, 1 / 60, 3 / 60, 3 / 60, 4 / 60], 60.0)
    assert dropped["rate_validated"] and not dropped["uniform_steps"]
    assert dropped["dropped_frames"] == 1
    assert dropped["duplicate_pts_steps"] == 1
    assert not pts_summary([0.0, 0.0081, 0.0163], 60.0)["rate_validated"]
    capped = policy_row({"game_id": "a", "status": "tracked", "_last_frame": 2999,
                         "_first_frame": 0, "stride": 6}, summary, 60.0)
    assert capped["attribution"] == "CAP"
    assert capped["cap_limited_span_s"] == pytest.approx(50.0)
    assert capped["loss_s"] == pytest.approx(50.0)
    assert capped["loss_over_decision"] is True
    eof = policy_row({"game_id": "b", "status": "tracked", "_last_frame": 7799,
                      "_first_frame": 0, "stride": 6}, summary, 60.0)
    assert eof["attribution"] == "EOF"
    assert eof["loss_s"] == 0.0
    failed = policy_row({"game_id": "c", "status": "thin", "_last_frame": None,
                         "_first_frame": None, "stride": 6}, summary, 60.0)
    assert failed["attribution"] == "FAILED_ATTEMPT"
    assert failed["loss_s"] is None
    absent = policy_row({"game_id": "d", "status": "tracked", "_last_frame": 10,
                         "_first_frame": 0, "stride": 6}, None, 60.0)
    assert absent["attribution"] == "UNKNOWN"
    assert absent["unknown_reason"] == "source_absent_before_retention"


def test_policy_totals_counts_unknown_separately() -> None:
    rows = [{"loss_s": 0.0, "loss_over_decision": False, "attribution": "EOF"},
            {"loss_s": 40.0, "loss_over_decision": True, "attribution": "CAP"},
            {"loss_s": None, "loss_over_decision": None, "attribution": "UNKNOWN"},
            {"loss_s": 3.0, "loss_over_decision": False, "attribution": "CAP"}]
    totals = policy_totals(rows)
    assert totals["window_sections"] == 4
    assert totals["cap_loss_over_5s_count"] == 1
    assert totals["primary_metric"] == pytest.approx(0.25)
    assert totals["unknown_sections"] == 1
    assert totals["policy_status"] == "POSITIVE_LOSS"
    assert totals["attribution_counts"]["CAP"] == 2
    clean = policy_totals([{"loss_s": 0.0, "loss_over_decision": False,
                            "attribution": "EOF"}])
    assert clean["policy_status"] == "ZERO_LOSS"


def test_paired_arms_reach_target_within_one_native_interval() -> None:
    pts = [index / NTSC_60 for index in range(7800)]
    row = paired_caps("n.mp4", pts, NTSC_60, True)
    assert row["arm_a_frame_cap"] == 3000
    assert row["arm_b_frame_cap"] == 5995
    assert row["arm_a_read_frames"] == 3000
    assert row["arm_b_read_frames"] == 5995
    assert row["source_frame_count"] == 7800
    assert row["arm_b_reaches_target"] is True
    assert row["arm_a_span_s"] < 51.0
    assert row["cap_basis"] == "VALIDATED_FPS"
    invalid = paired_caps("n.mp4", pts, NTSC_60, False)
    assert invalid["cap_basis"] == "UNKNOWN"
    assert invalid["arm_b_frame_cap"] == 3000


# --- the proposal itself ----------------------------------------------------

def _candidate_source(tmp_path: Path) -> Path:
    """Apply the committed PROPOSED diff to a scratch copy of the daemon."""
    tree = tmp_path / "scripts" / "platformkit"
    tree.mkdir(parents=True)
    target = tree / "track_daemon.py"
    target.write_bytes(DAEMON.read_bytes().replace(b"\r\n", b"\n"))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "apply", "-p1", str(DIFF.resolve())],
                   cwd=tmp_path, check=True)
    return target


def test_proposed_diff_applies_and_keeps_legacy_argv(tmp_path: Path) -> None:
    candidate_path = _candidate_source(tmp_path)
    legacy = extract_build_command(
        DAEMON.read_text(encoding="utf-8").replace("\r\n", "\n"))
    candidate = load_candidate(candidate_path.read_text(encoding="utf-8"))
    cases = build_fixtures(candidate, legacy,
                           read_parser(Path("scripts/run_clip.py")))
    by_case = {case["case"]: case for case in cases}
    assert len(cases) == 7
    assert all(case["default_argv_matches_legacy"] for case in cases)
    assert all(case["flag_names_added"] == [] for case in cases)
    assert by_case["fps_30"]["candidate_frames"] == "3000"
    assert by_case["fps_60"]["candidate_frames"] == "6000"
    assert by_case["fps_59_94"]["candidate_frames"] == "5995"
    assert by_case["fps_29_97"]["candidate_frames"] == "2998"
    assert by_case["fps_unknown_no_probe"]["receipt"]["cap_basis"] == "UNKNOWN"
    assert by_case["fps_variable_parse_failure"]["candidate_frames"] == "3000"
    assert all(case["parsed_start_frame"] == 0 for case in cases)


def test_fixture_source_and_receipt_shape(tmp_path: Path) -> None:
    assert fixture_source(None, None) is None
    assert fixture_source(60.0, "ok")["source_fps"] == 60.0
    candidate = load_candidate(
        _candidate_source(tmp_path).read_text(encoding="utf-8"))
    receipt = candidate["cap_receipt"](fixture_source(60.0, "ok"))
    assert receipt == {"requested_duration_seconds": 100.0,
                       "requested_frame_cap": 6000, "cap_basis": "VALIDATED_FPS",
                       "legacy_frame_cap": 3000}
    assert candidate["duration_frame_cap"](None) == (3000, "UNKNOWN")


def test_proposal_leaves_the_fixed_daemon_semantics_alone() -> None:
    text = DIFF.read_text(encoding="utf-8")
    assert text.count("+++ b/") == 1
    assert "b/scripts/platformkit/track_daemon.py" in text
    added = "\n".join(line for line in text.splitlines()
                      if line.startswith("+") and not line.startswith("+++"))
    removed = "\n".join(line for line in text.splitlines()
                        if line.startswith("-") and not line.startswith("---"))
    for token in ("_VRAM_FLUSH_INTERVAL", "workers", "stride", "NBA_FRAME_STRIDE",
                  "unified_pipeline", "run_clip.py\"", "--data-dir\""):
        assert token not in removed
    assert "_VRAM_FLUSH_INTERVAL" not in added
    assert "NBA_FRAME_STRIDE" not in added


def test_reader_survey_only_marks_the_daemon_rows() -> None:
    rows = reader_survey(Path("."))
    assert len(rows) > 300
    changed = [row for row in rows if row["changed_by_proposal"]]
    assert {row["path"] for row in changed} == {DAEMON.as_posix()}
    assert {row["token"] for row in changed} == {"build_command", "--frames"}
    assert any(row["token"] == "_VRAM_FLUSH_INTERVAL" for row in rows)


# --- receipts ---------------------------------------------------------------

def test_prereg_file_normalizes_crlf_before_hashing(tmp_path: Path) -> None:
    source = EVIDENCE / "prereg.md"
    assert verify_prereg(source)
    copied = tmp_path / "prereg.md"
    copied.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
    assert verify_prereg(copied)


def test_q6_scan_covers_every_landable_text_artifact() -> None:
    paths = [path for path in sorted(EVIDENCE.rglob("*"))
             if path.is_file() and path.suffix in
             (".csv", ".diff", ".json", ".jsonl", ".md", ".txt")]
    paths.append(Path(
        "docs/evidence/tracking/g401_fps_cap_duration_shadow_2026-09-11.md"))
    paths += sorted(Path("scripts/platformkit/tracking").glob("g401_*.py"))
    paths.append(Path("tests/platformkit/test_g401_fps_cap_duration.py"))
    assert len(paths) > 15
    assert sum(q6_hit_counts(paths).values()) == 0
