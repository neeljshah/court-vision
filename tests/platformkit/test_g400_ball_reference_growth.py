"""Prepare-only contract rails for G400 reference growth."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.platformkit.tracking.g400_prepare import (
    GAMES,
    PLANNED_STATES,
    assert_disjoint,
    assert_frozen_draw,
    cohen_kappa,
    draw_games,
    make_batch_plan,
    native_roundtrip,
    stage_verdict,
    validate_completed_answers,
    validate_state_rows,
    verify_preregistration,
)
from scripts.platformkit.tracking.g400_q6_scan import scan


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/tracking/g400_ball_reference_growth_stage1_2026-09-11"
PREREG = EVIDENCE / "prereg.md"


def _population(count: int = GAMES) -> list[dict[str, str]]:
    return [{"competition": "C%02d" % (index % 2), "canonical_game": "G%03d" % index,
             "source_digest": "%064x" % index, "eligibility": "ELIGIBLE"}
            for index in range(count)]


def _states() -> list[dict[str, str]]:
    return [{"frame_key": "G%03d-F%02d" % (game, frame),
             "canonical_game": "G%03d" % game, "status": "PLANNED", "label": ""}
            for game in range(GAMES) for frame in range(10)]


def test_prereg_seal_reads_the_file_and_normalizes_crlf(tmp_path: Path):
    raw = PREREG.read_bytes().replace(b"\r\n", b"\n")
    copied = tmp_path / "prereg.md"
    copied.write_bytes(raw.replace(b"\n", b"\r\n"))
    assert verify_preregistration(PREREG) == verify_preregistration(copied)


def test_even_draw_is_frozen_and_refuses_post_draw_substitution():
    population = _population(59)
    selected = draw_games(population)
    assert len(selected) == GAMES
    assert_frozen_draw(population, selected)
    altered = [dict(row) for row in selected]
    altered[-1] = dict(population[-1])
    with pytest.raises(ValueError, match="post-draw-substitution"):
        assert_frozen_draw(population, altered)
    with pytest.raises(ValueError, match="insufficient-eligible-games"):
        draw_games(_population(29))


def test_overlap_and_ten_round_batch_plan_are_rejected_or_complete():
    new = [{"canonical_game": "N", "source_digest": "a", "context_identity": "n"}]
    old = [{"canonical_game": "O", "source_digest": "b", "context_identity": "o"}]
    assert_disjoint(new, old)
    with pytest.raises(ValueError, match="old-game-or-context-overlap-canonical_game"):
        assert_disjoint(new, old + [{"canonical_game": "N", "source_digest": "c", "context_identity": "p"}])
    plan = make_batch_plan(_states())
    assert len(plan) == PLANNED_STATES
    assert {row["round"] for row in plan} == set(range(1, 11))
    assert all(len({row["canonical_game"] for row in plan if row["round"] == round_id}) == GAMES
               for round_id in range(1, 11))


def test_unknown_is_reviewed_not_unvisited_and_completed_answers_do_not_duplicate():
    states = _states()
    states[0] = {**states[0], "status": "REVIEWED", "label": "UNKNOWN"}
    states[1] = {**states[1], "status": "UNVISITED", "label": ""}
    assert validate_state_rows(states)["UNVISITED"] == 1
    invalid = [dict(row) for row in states]
    invalid[1]["label"] = "UNKNOWN"
    with pytest.raises(ValueError, match="unvisited-cannot-have-label"):
        validate_state_rows(invalid)
    answers = [{"rater": "terra", "frame_key": "k1", "label": "UNKNOWN"},
               {"rater": "sol", "frame_key": "k1", "label": "VISIBLE"}]
    validate_completed_answers(answers)
    with pytest.raises(ValueError, match="duplicate-completed-answer"):
        validate_completed_answers(answers + [answers[0]])


def test_undefined_kappa_native_scale_and_whole_stage_yield_lock():
    assert cohen_kappa(["VISIBLE"] * 30, ["VISIBLE"] * 30) is None
    assert cohen_kappa(["VISIBLE", "ABSENT"], ["VISIBLE", "ABSENT"]) == pytest.approx(1.0)
    assert native_roundtrip(1536.25, 1080) == pytest.approx(1536.25)
    states = _states()
    assert stage_verdict(states, 120) == "CLOSED AT LIMIT"
    assert stage_verdict(states, 121) == "NEXT-STAGE-PROPOSAL-ONLY"
    with pytest.raises(ValueError, match="whole-stage-denominator-required"):
        stage_verdict(states[:-1], 0)


def test_q6_scan_covers_current_g400_prepare_artifacts():
    paths = [PREREG, ROOT / "docs/evidence/tracking/g400_ball_reference_growth_stage1_2026-09-11.md",
             ROOT / "scripts/platformkit/tracking/g400_prepare.py",
             ROOT / "scripts/platformkit/tracking/g400_q6_scan.py", Path(__file__)]
    assert scan(paths) == {}


def test_census_canonical_key_and_named_exclusions():
    from scripts.platformkit.tracking.g400_census import apply_exclusions, canonical

    assert canonical("Duke vs. UNC (2.7.26)", "ncaa") == "ncaa|duke vs unc 2 7 26"
    assert canonical("", "nba") == ""
    census = [
        {"video_id": "new1", "competition": "nba", "canonical_game": "nba|a b",
         "source_digest": "0" * 64, "probe_status": "ok", "duration_s": 130.0,
         "eligibility": "ELIGIBLE", "exclusion_reason": ""},
        {"video_id": "alt1", "competition": "nba", "canonical_game": "nba|a b",
         "source_digest": "1" * 64, "probe_status": "ok", "duration_s": 130.0,
         "eligibility": "ELIGIBLE", "exclusion_reason": ""},
        {"video_id": "old1", "competition": "nba", "canonical_game": "nba|c d",
         "source_digest": "2" * 64, "probe_status": "ok", "duration_s": 130.0,
         "eligibility": "ELIGIBLE", "exclusion_reason": ""},
        {"video_id": "short", "competition": "nba", "canonical_game": "nba|e f",
         "source_digest": "3" * 64, "probe_status": "ok", "duration_s": 4.0,
         "eligibility": "ELIGIBLE", "exclusion_reason": ""},
        {"video_id": "blind", "competition": "nba", "canonical_game": "",
         "source_digest": "4" * 64, "probe_status": "ok", "duration_s": 130.0,
         "eligibility": "ELIGIBLE", "exclusion_reason": ""}]
    apply_exclusions(census, {"old1"})
    reason = {row["video_id"]: row["exclusion_reason"] for row in census}
    assert reason["new1"] == ""
    assert reason["alt1"] == "ALTERNATE_UPLOAD_OF_new1"
    assert reason["old1"] == "OLD_IDENTITY_OVERLAP"
    assert reason["short"] == "SPAN_TOO_SHORT_FOR_TEN_TARGETS"
    assert reason["blind"] == "UNRESOLVED_GAME_IDENTITY"


def test_interior_targets_are_k_over_eleven_with_earlier_tie():
    from scripts.platformkit.tracking.g400_frames import choose_targets

    schedule = [round(index / 30.0, 6) for index in range(0, 30 * 130)]
    chosen = choose_targets(schedule)
    assert len(chosen) == 10
    assert [row[0] for row in chosen] == list(range(1, 11))
    span = schedule[-1] - schedule[0]
    for k, want, got in chosen:
        assert abs(want - schedule[0] - span * k / 11.0) < 1e-9
        assert abs(got - want) <= 1.0 / 30.0
    picked = [row[2] for row in chosen]
    assert all(b - a >= 1.0 for a, b in zip(picked, picked[1:]))
    assert choose_targets([0.0, 1.0]) == []


def test_rater_parser_validates_each_box_against_its_own_native_size(tmp_path: Path):
    from scripts.platformkit.tracking.g400_rate import parse_batch

    wanted = {"a" * 12: {"frame_key": "a" * 64, "width": "1280", "height": "720"},
              "b" * 12: {"frame_key": "b" * 64, "width": "1920", "height": "1080"},
              "c" * 12: {"frame_key": "c" * 64, "width": "1280", "height": "720"}}
    raw = tmp_path / "batch.txt"
    raw.write_text("\n".join((
        "a" * 12 + ",VISIBLE,100,100,20,20,in play",
        "b" * 12 + ",VISIBLE,1900,1060,40,40,out of frame",
        "c" * 12 + ",UNKNOWN,,,,,blurred",
        "c" * 12 + ",VISIBLE,10,10,5,5,duplicate answer")), encoding="ascii")
    rows = parse_batch(raw, "terra", 3, wanted)
    assert [row["frame_key"] for row in rows] == ["a" * 64, "c" * 64]
    assert rows[0]["cx"] == 110.0 and rows[0]["round"] == 3
    assert rows[1]["label"] == "UNKNOWN" and rows[1]["cx"] == ""


def test_transform_controls_roundtrip_exactly_on_both_native_heights():
    from scripts.platformkit.tracking.g400_prepare import native_roundtrip, native_to_720p

    for height in (720, 1080):
        for value in (0.5, 123.75, 1079.5 if height == 1080 else 719.5):
            assert native_roundtrip(value, height) == pytest.approx(value, abs=1e-9)
    assert native_to_720p(540.0, 1080) == pytest.approx(360.0)
    assert native_to_720p(360.0, 720) == pytest.approx(360.0)
    with pytest.raises(ValueError, match="invalid-source-height"):
        native_to_720p(1.0, 0)


def test_measured_g400_artifacts_hold_their_binding_shape():
    import csv as _csv
    import json as _json
    from scripts.platformkit.tracking.g400_controls import _conflict_rows

    manifest = list(_csv.DictReader(
        (EVIDENCE / "native_manifest.csv").open(encoding="ascii", newline="")))
    plan = list(_csv.DictReader(
        (EVIDENCE / "batch_plan.csv").open(encoding="ascii", newline="")))
    draw = list(_csv.DictReader((EVIDENCE / "draw.csv").open(encoding="ascii", newline="")))
    assert len(manifest) == PLANNED_STATES and len(plan) == PLANNED_STATES
    assert len(draw) == GAMES
    assert len({row["frame_key"] for row in manifest}) == PLANNED_STATES
    assert all(row["sheet_scale"] == "1.0" for row in manifest)
    assert {row["frame_key"] for row in plan} == {row["frame_key"] for row in manifest}
    old_games = {row["game"] for row in _csv.DictReader(
        (ROOT / "docs/evidence/tracking/g389_ball_reference_completion_2026-09-11"
         / "frames_v3.csv").open(encoding="utf-8", newline=""))}
    assert not old_games & {row["video_id"] for row in draw}
    for round_id in range(1, 11):
        members = [row for row in plan if int(row["round"]) == round_id]
        assert len({row["video_id"] for row in members}) == GAMES
    conflicts = list(_csv.DictReader(
        (EVIDENCE / "conflict_index.csv").open(encoding="ascii", newline="")))
    assert all(row["position"] for row in conflicts)
    assert all(row["reason"] for row in conflicts)  # fix 1c: reason maps from adjudication_reason
    kappa = list(_csv.DictReader((EVIDENCE / "kappa.csv").open(encoding="ascii", newline="")))
    for row in kappa:  # fix 1c: below the sealed n the verdict is INCOMPLETE, never PASS
        need = 300 if row["round"] == "POOLED" else 30
        if row["paired_n"].isdigit() and int(row["paired_n"]) < need:
            assert row["verdict"] == "INCOMPLETE"
    assert all(row["crop_centre_x"] for row in conflicts)
    assert all(row["crop_centre_y"] for row in conflicts)
    assert len(_conflict_rows(EVIDENCE)) == len(conflicts)
    q6 = _json.loads((EVIDENCE / "q6_scan.json").read_text(encoding="ascii"))
    assert all(isinstance(hits, list) for hits in q6["findings"].values())
    assert set(q6["findings"]) == set(q6["findings_classified"])


def test_measured_stage_tables_agree_with_the_sealed_gates():
    import csv as _csv
    import json as _json

    kappa = list(_csv.DictReader((EVIDENCE / "kappa.csv").open(encoding="ascii", newline="")))
    rounds = [row for row in kappa if row["round"] != "POOLED"]
    pooled = next(row for row in kappa if row["round"] == "POOLED")
    assert len(rounds) == 10
    assert [row["verdict"] for row in rounds].count("FAIL") == 1
    assert float(pooled["kappa"]) >= 0.60 and int(pooled["paired_n"]) == 299
    ratings = list(_csv.DictReader((EVIDENCE / "ratings.csv").open(encoding="ascii", newline="")))
    resolved = {row["frame_key"] for row in
                _csv.DictReader((EVIDENCE / "resolutions.csv").open(encoding="ascii", newline=""))}
    assert len(ratings) == PLANNED_STATES
    assert all(row["frame_key"] in resolved
               for row in ratings if row["needs_adjudication"] == "1")
    new_boxes = list(_csv.DictReader((EVIDENCE / "new_boxes.csv").open(encoding="ascii", newline="")))
    yields = {row["metric"]: row["value"] for row in
              _csv.DictReader((EVIDENCE / "yield.csv").open(encoding="ascii", newline=""))}
    assert int(yields["accepted_audited_new_boxes"]) == len(new_boxes)
    assert float(yields["stage_yield"]) == pytest.approx(len(new_boxes) / PLANNED_STATES, abs=1e-4)
    assert yields["route_verdict"] == stage_verdict(
        [{"frame_key": row["frame_key"], "canonical_game": row["canonical_game"],
          "status": "REVIEWED" if row["terra_label"] and row["sol_label"] else "UNVISITED",
          "label": row["terra_label"] if row["terra_label"] and row["sol_label"] else ""}
         for row in ratings], len(new_boxes))
    old = list(_csv.DictReader(
        (ROOT / "docs/evidence/tracking/g389_ball_reference_completion_2026-09-11"
         / "dev_boxes_v3.csv").open(encoding="utf-8", newline="")))
    reference = list(_csv.DictReader((EVIDENCE / "reference.csv").open(encoding="ascii", newline="")))
    assert len(old) == 530 and reference[:530] == old
    assert len(reference) == 530 + len(new_boxes)
    controls = list(_csv.DictReader((EVIDENCE / "transform_controls.csv").open(encoding="ascii", newline="")))
    assert len(controls) == 30
    assert sum(int(row["roundtrip_exact"]) for row in controls) == 30
    assert sum(int(row["centre_rule_match"]) for row in controls) == 30
    assert sum(int(row["false_positive"]) for row in controls) == 0
    assert _json.loads((EVIDENCE / "repeats.json").read_text(encoding="ascii"))["identical"] is True
    assert _json.loads((EVIDENCE / "q6_scan.json").read_text(encoding="ascii"))["non_opaque_hits"] == 0
