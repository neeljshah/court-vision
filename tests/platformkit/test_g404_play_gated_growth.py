"""G404 prepare rails: ordering, raw-state preservation, and fixed outcome rules."""

from pathlib import Path

import pytest

from scripts.platformkit.tracking.g404_prepare import (
    assert_disjoint,
    audit_draw,
    draw_games,
    even_indices,
    exclude_audit_context,
    planned_key_set,
    prereg_seal_is_valid,
)
from scripts.platformkit.tracking.g404_score import (
    cohen_kappa,
    reliability_pass,
    stage_verdict,
    usable_box,
    yield_is_complete,
)

PREREG = (Path(__file__).resolve().parents[2] / "docs" / "evidence" / "tracking"
          / "g404_play_gated_ball_growth_stage2_2026-09-11" / "prereg.md")


def row(game: str, point: int, admitted: str = "1") -> dict[str, str]:
    return {"frame_key": game + "_" + str(point), "canonical_game": game,
            "pts": str(point), "source_sha256": "d" + game, "gate_admitted": admitted}


def test_seal_matches_lf_normalized_prereg_file():
    assert prereg_seal_is_valid(PREREG)


def test_audit_draw_is_even_and_precedes_audit_context_exclusion():
    rows = [row("g%02d" % game, point, "1" if point < 40 else "0")
            for game in range(30) for point in range(80)]
    admitted = audit_draw(rows, True)
    excluded = audit_draw(rows, False)
    assert len(admitted) == len(excluded) == 30
    remaining = exclude_audit_context(rows, admitted + excluded)
    assert not {item["frame_key"] for item in admitted + excluded}.intersection(
        item["frame_key"] for item in remaining)
    indices = even_indices(151, 30)
    assert indices[0] == 0 and indices[-1] == 150
    assert indices != list(range(30))


def test_draw_has_300_keys_after_gate_audit_exclusion():
    rows = [row("g%02d" % game, point) for game in range(31) for point in range(100)]
    audit = audit_draw(rows, True) + audit_draw([dict(item, gate_admitted="0") for item in rows], False)
    drawn = draw_games(exclude_audit_context(rows, audit))
    assert len(drawn) == 300
    assert len(planned_key_set(drawn)) == 300


def test_invalid_box_preserves_a_valid_visible_state():
    invalid = {"state": "VISIBLE", "box_w": "0", "box_h": "8"}
    assert invalid["state"] == "VISIBLE"
    assert not usable_box(invalid)


def test_incomplete_or_undefined_kappa_never_passes():
    perfect = [("VISIBLE", "VISIBLE")] * 30
    assert cohen_kappa(perfect) is None
    assert not reliability_pass([perfect] * 10, perfect * 10)
    assert not reliability_pass([[("VISIBLE", "VISIBLE")] * 29] * 10, perfect * 10)


def test_yield_requires_every_planned_frame_and_no_implicit_reference_promotion():
    planned = {"f%03d" % index for index in range(300)}
    rows = [{"frame_key": key, "state": "ABSENT"} for key in sorted(planned)]
    assert yield_is_complete(planned, rows)
    assert not yield_is_complete(planned, rows[:-1])
    assert stage_verdict(True, True, True, True, True, True, 121) == "DONE"


def test_canonical_game_overlap_is_rejected_before_draw():
    with pytest.raises(ValueError, match="canonical-game overlap"):
        assert_disjoint(["new-game", "shared-game"], ["shared-game"])


# --- measured-stage rails (added by the finisher for what this row actually measured) ---

import csv
import json

from scripts.platformkit.tracking.g404_census import apply_exclusions, canonical
from scripts.platformkit.tracking.g404_audit import even_indices as audit_even_indices
from scripts.platformkit.tracking.g404_audit import stratum_rows
from scripts.platformkit.tracking.g404_finish import joint
from scripts.platformkit.tracking.g404_q6_scan import NUMERIC_PATTERNS, SUFFIXES
from scripts.platformkit.tracking.g404_score import gate_audit_pass

EVIDENCE = PREREG.parent


def census_row(video_id: str, title: str, competition: str = "bcl") -> dict:
    return {"video_id": video_id, "competition": competition, "title": title,
            "canonical_game": canonical(title, competition), "source_digest": "d" + video_id,
            "probe_status": "ok", "duration_s": "130.0", "eligibility": "ELIGIBLE",
            "exclusion_reason": ""}


def test_amendment_a1_seal_matches_its_lf_normalized_file():
    assert prereg_seal_is_valid(EVIDENCE / "amendment_A1.md")


def test_census_names_old_identity_and_alternate_upload_exclusions():
    rows = [census_row("new1", "team a vs team b"), census_row("old1", "team c vs team d"),
            census_row("dup1", "team a vs team b"), census_row("blank", "")]
    apply_exclusions(rows, {"old1"})
    reasons = {row["video_id"]: row["exclusion_reason"] for row in rows}
    assert "OLD_IDENTITY_OVERLAP" in reasons["old1"]
    assert "UNRESOLVED_GAME_IDENTITY" in reasons["blank"]
    shared = [reasons["new1"], reasons["dup1"]]
    assert sum(1 for reason in shared if reason.startswith("ALTERNATE_UPLOAD_OF_")) == 1
    assert sum(1 for reason in shared if reason == "") == 1
    assert sum(1 for row in rows if row["eligibility"] == "ELIGIBLE") == 1


def test_gate_audit_draw_is_even_over_the_whole_stratum():
    rows = [{"gate_admitted": "1" if index % 2 else "0", "canonical_game": "g",
             "pts": str(index), "pixel_sha256": "p%03d" % index} for index in range(400)]
    admitted = stratum_rows(rows, True)
    assert len(admitted) == 200
    indices = audit_even_indices(len(admitted), 30)
    assert indices[0] == 0 and indices[-1] == len(admitted) - 1
    assert len(set(indices)) == 30


def test_single_reviewer_can_never_satisfy_the_joint_gate_bar():
    assert joint("PLAY") == "SINGLE_REVIEWER_NO_JOINT_LABEL"
    assert joint("PLAY", "PLAY") == "PLAY"
    assert joint("PLAY", "NONPLAY") == "DISAGREEMENT"
    assert not gate_audit_pass([("PLAY", "NOT REACHED")] * 30,
                               [("NONPLAY", "NOT REACHED")] * 30)
    assert gate_audit_pass([("PLAY", "PLAY")] * 30, [("NONPLAY", "NONPLAY")] * 30)


def test_delivered_gate_audit_reproduces_the_memo_counts_and_partial_verdict():
    with (EVIDENCE / "gate_audit.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = json.loads((EVIDENCE / "summary.json").read_text(encoding="ascii"))
    admitted = [row for row in rows if row["stratum"] == "ADMITTED"]
    excluded = [row for row in rows if row["stratum"] == "EXCLUDED"]
    assert len(admitted) == len(excluded) == 30
    assert sum(1 for row in admitted if row["claude_label"] == "PLAY") == 26
    assert sum(1 for row in excluded if row["claude_label"] == "NONPLAY") == 25
    assert summary["admitted_bar_reachable"] is False
    assert summary["gate_audit_pass"] is False
    assert summary["eligible_new_games"] < summary["required_new_games"]
    assert summary["verdict"] == "PARTIAL"
    assert stage_verdict(False, False, False, False, False, False, None) == "PARTIAL"


def test_q6_receipt_has_complete_manifest_and_no_literal_restricted_constant():
    scanner = Path("scripts/platformkit/tracking/g404_q6_scan.py")
    source = scanner.read_text(encoding="utf-8")
    assert all(pattern not in source for pattern in NUMERIC_PATTERNS)
    receipt = json.loads((EVIDENCE / "q6_scan.json").read_text(encoding="ascii"))
    repository = Path(__file__).resolve().parents[2]
    expected = {path.resolve().relative_to(repository).as_posix() for path in EVIDENCE.rglob("*")
                if path.is_file() and (path.suffix.lower() in SUFFIXES or
                                       path.name == "SHA256SUMS")}
    expected.update({"docs/evidence/tracking/g404_play_gated_ball_growth_stage2_2026-09-11.md",
                     "scripts/platformkit/tracking/g404_finish.py",
                     Path(__file__).resolve().relative_to(repository).as_posix()})
    expected.add(scanner.as_posix())
    assert receipt["claim_context_hits"] == 0
    assert set(receipt["path_manifest"]) == expected
