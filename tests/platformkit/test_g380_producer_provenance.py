"""G380 controls for the proposed producer provenance fields and their receipt.

Fix 1b (test infra): this file writes nothing and reads no temp directory. The
verifier's first two runs of attempt 1 produced 16 setup errors from blocked temp
access, so the two tests that needed a scratch file now use a committed fixture
and a file that already exists. Nothing here depends on `--basetemp` at all.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.platformkit.tracking import g380_controls
from scripts.platformkit.tracking import g380_provenance as prov
from scripts.platformkit.tracking import g380_report
from scripts.platformkit.tracking import g380_trace_sections as trace_sections
from scripts.platformkit.tracking.g380_patch import EDITS, FILES
from scripts.platformkit.tracking.g380_producer_trace import stamp_row, trace_rows
from scripts.platformkit.tracking.g380_tick_receipt import (
    receipt_for_attempts,
    receipt_matches_trace,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/tracking/g380_producer_provenance_2026-09-10"
PREREG = EVIDENCE / "prereg.md"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "g380_sample.trace"
ATTEMPTS = Path(__file__).resolve().parent / "fixtures" / "g380_attempts.trace"


@pytest.mark.parametrize(("branch", "expected"), [
    ("fresh_detection", "DETECTION"), ("coast", "PREDICTION"),
    ("clamp", "CLAMP"), ("subpixel_hold", "SUBPIXEL"),
    ("id_merge", "PREDICTION"),
])
def test_every_construct_branch_stamps_its_expected_label(branch: str, expected: str) -> None:
    stamped = stamp_row({"frame": 12}, branch, "fixture:%s" % branch, "event-12")
    assert stamped["position_source"] == expected
    assert stamped["source_branch"] == "fixture:%s" % branch
    assert stamped["matched_event_id"] == ("event-12" if expected == "DETECTION" else "")


def test_missing_event_is_unknown_not_dropped() -> None:
    trace = trace_rows([{"branch": "missing_event", "source_branch": "fixture:missing",
                         "row": {"frame": 9}}])
    assert trace == [{"frame": 9, "position_source": "UNKNOWN",
                      "source_branch": "fixture:missing", "matched_event_id": ""}]


def test_receipt_equals_independent_trace_fixture() -> None:
    receipt = receipt_for_attempts([9, 3, 9, 15], attempted_frames_capped=4)
    assert receipt_matches_trace(receipt, [15, 3, 9, 9])


@pytest.mark.parametrize("name", ["prereg.md",
                                  "g380_prereg_amendment_A1_2026-09-10.md",
                                  "g380_prereg_amendment_A2_2026-09-11.md",
                                  "g380_prereg_amendment_A3_2026-09-11.md"])
def test_every_sealed_preregistration_file_verifies(name: str) -> None:
    """A sealed file is never edited, so its seal must still cover its own bytes."""
    path = EVIDENCE / name
    data = path.read_bytes().replace(b"\r\n", b"\n")
    actual = hashlib.sha256(data[:data.index(b"SEAL sha256 ")]).hexdigest()
    expected = next(line.removeprefix("SEAL sha256 ")
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.startswith("SEAL sha256 "))
    assert actual == expected


def test_amendment_a2_restores_the_unconditional_overlay_bar() -> None:
    """A1 weakened the sealed eye bar with ` where they occur`; A2 withdraws that."""
    sealed = PREREG.read_text(encoding="utf-8")
    a2 = (EVIDENCE / "g380_prereg_amendment_A2_2026-09-11.md").read_text(encoding="utf-8")
    bar = "The 30 source-coloured overlays must be evenly spaced and include HELD and CLAMP."
    assert bar in sealed and bar in a2
    assert "WITHDRAWN" in a2 and "where they occur" in a2


def test_a_tick_no_branch_wrote_is_held_and_an_unseen_slot_is_unknown() -> None:
    store = {}
    prov.stamp(store, 2, 10, "DETECTION", "b")
    assert prov.label_for(store, 2, 10) == ("DETECTION", "b", "")
    assert prov.label_for(store, 2, 11)[0] == "HELD"
    assert prov.label_for(store, 7, 11) == ("UNKNOWN", "", "")
    assert prov.label_for({}, 2, 10) == ("UNKNOWN", "", "")


def test_a_detection_row_names_the_box_it_was_matched_to() -> None:
    store = {}
    prov.stamp(store, 1, 42, "DETECTION", "b", prov.event_id(42, (3, 4, 5, 6)))
    assert prov.label_for(store, 1, 42)[2] == "42_3_4_5_6"
    assert prov.event_id(42, None) == ""
    assert prov.label_for(store, 1, 43)[2] == ""


def test_a_merged_out_row_drops_its_stamp_but_never_its_slot() -> None:
    store = {}
    prov.stamp(store, 0, 5, "DETECTION", "b")
    prov.drop(store, 0, 5)
    assert prov.label_for(store, 0, 5)[0] == "HELD"


def test_subpixel_only_upgrades_a_fresh_write_that_did_not_move() -> None:
    assert prov.resolve_emitted("DETECTION", "b", (4, 5), (4, 5))[0] == "SUBPIXEL"
    assert prov.resolve_emitted("PREDICTION", "b", (4, 5), (4, 5))[0] == "SUBPIXEL"
    assert prov.resolve_emitted("CLAMP", "b", (4, 5), (4, 5))[0] == "CLAMP"
    assert prov.resolve_emitted("DETECTION", "b", (4, 5), (4, 6))[0] == "DETECTION"
    assert prov.resolve_emitted("DETECTION", "b", None, (4, 5))[0] == "DETECTION"


def test_an_unknown_label_is_refused_and_the_store_stays_bounded() -> None:
    with pytest.raises(ValueError):
        prov.stamp({}, 1, 1, "GUESS", "b")
    store = {}
    for tick in range(4000):
        prov.stamp(store, tick % 12, tick, "DETECTION", "b")
    assert len(store) <= 6000


def test_bind_is_idempotent_and_never_raises_on_a_missing_source() -> None:
    """Stats an existing file instead of writing one: no temp directory is touched."""
    video = Path(__file__).resolve()
    first = prov.bind_attempt("g1", video, video.parent)
    assert first == prov.bind_attempt("g1", video, video.parent)
    assert first["receipt_path"].endswith("evaluated_tick_receipt.json")
    absent = prov.bind_attempt("g2", video.parent / "gone.mp4", video.parent)
    assert absent["attempt_id"] == "" and absent["bind_error"]


def test_every_proposed_edit_targets_a_producer_file_and_is_purely_additive() -> None:
    assert {rel for rel, _, _ in EDITS} <= set(FILES)
    for rel, anchor, replacement in EDITS:
        kept = {line.strip() for line in replacement.splitlines() if line.strip()}
        for line in anchor.splitlines():
            if line.strip():
                assert line.strip() in kept, (rel, line.strip()[:60])
        assert len(replacement) > len(anchor), (rel, anchor[:40])


def test_the_independent_trace_is_read_back_one_row_per_emitted_row() -> None:
    rows = g380_report._trace_rows(FIXTURE)
    assert [row["trace_final_label"] for row in rows] == ["SUBPIXEL", "HELD"]
    assert rows[0]["frame"] == 7


def test_the_trace_diff_models_a_dropped_stamp_as_held() -> None:
    """The hook records `drop`; without it a merged-out row looks like a mismatch."""
    rows, summary = g380_controls.trace_diff(FIXTURE)
    assert summary["agreement"] == 1.0
    assert [row["expected_from_stamps"] for row in rows] == ["DETECTION", "HELD"]


def test_the_attempt_trace_counts_every_evaluated_tick_not_only_emitting_ones() -> None:
    """A3: a tick that passed the gate and emitted no player row is still an attempt."""
    assert trace_sections.attempt_ticks(ATTEMPTS) == [7, 8, 9]
    assert {row["frame"] for row in g380_report._trace_rows(ATTEMPTS)} == {7}
    assert trace_sections.attempt_ticks(ATTEMPTS.parent / "absent.trace") == []


def test_note_attempt_records_each_tick_once_and_tolerates_no_store() -> None:
    store = set()
    prov.note_attempt(store, 5)
    prov.note_attempt(store, 5)
    prov.note_attempt(store, "6")
    assert store == {5, 6}
    prov.note_attempt(None, 5)


def test_the_receipt_is_written_from_the_attempt_set_not_the_cleared_buffer() -> None:
    """The `predictions` buffer is cleared every 3000 frames, so a run longer than
    the flush interval would drop evaluated tick ids out of its own receipt."""
    text = "".join(replacement for _, _, replacement in EDITS)
    assert "_g380.note_attempt(_g380_ticks, frame_idx)" in text
    assert '"evaluated_tick_ids": sorted(_g380_ticks)' in text
    assert "for item in predictions" not in text


def test_the_coast_scene_frame_is_textured_and_deterministic() -> None:
    """A flat frame gives optical flow no gradient, so the coast control would
    silently never enter the branch it claims to force."""
    first, second = g380_controls.scene_image(64, 64), g380_controls.scene_image(64, 64)
    assert (first == second).all()
    assert first.std() > 10.0
    assert set(g380_controls.COAST_BOXES) == {0, 1}
