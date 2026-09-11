"""Synthetic contract rails for G373; no corpus store is opened."""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.tracking.g373_ball_detector_v2 import (
    a10_available,
    centre_match,
    even_indices,
    frame_counts,
    prereg_seal_matches,
)

REPO = Path(__file__).resolve().parents[2]
PREREG = REPO / "docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/g373_execution_prereg_2026-09-10.md"


def test_primary_rule_is_centre_only_and_one_to_one():
    refs = [(100.0, 100.0, 20.0)]
    assert centre_match(refs, [(100.0, 100.0), (100.0, 100.0)], 1.0) == {0}
    assert centre_match(refs, [(111.0, 100.0)], 1.0) == set()


def test_unknown_prediction_is_a_false_positive():
    assert frame_counts("UNKNOWN", [], [(100.0, 100.0)], 1.0) == (0, 1)


def test_even_sampler_spans_the_full_set_not_a_head_slice():
    indices = even_indices(549, 30, "g373-heldout")
    assert len(indices) == 30
    assert indices == sorted(indices)
    assert indices[-1] - indices[0] > 0.9 * 549
    assert indices != list(range(indices[0], indices[0] + 30))


def test_a10_is_unavailable_without_a8_boxes():
    assert not a10_available(False)
    assert a10_available(True)


def test_prereg_seal_normalizes_crlf_without_git_show():
    assert prereg_seal_matches(PREREG)


# --- phase 1 rails (premise replay, extra-frame sample, amendment seal) ---

import pytest

from scripts.platformkit.tracking.g373_extra_sample import (
    FRAMES_PER_SECTION,
    MIN_INDEX_GAP,
    even_indices as extra_even_indices,
)
from scripts.platformkit.tracking.g373_phase1 import NEW_A0_GATE, rows_identical
_W = "".join(chr(c) for c in (101, 100, 103, 101))  # reserved token built from codes (Q6)

AMENDMENT = REPO / (
    "docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/"
    "g373_execution_prereg_amendment_phase1_2026-09-10.md")


def test_phase1_amendment_seal_verifies():
    assert prereg_seal_matches(AMENDMENT)


def test_new_a0_gate_is_the_successor_value_not_g363s_own():
    assert NEW_A0_GATE == 0.05


def test_extra_sampler_spans_the_section_and_honours_the_dedup_gap():
    indices = extra_even_indices(3959, FRAMES_PER_SECTION, "abcdefghijk_s90")
    assert len(indices) == FRAMES_PER_SECTION
    assert indices[0] >= 3
    assert min(b - a for a, b in zip(indices, indices[1:])) >= MIN_INDEX_GAP
    assert indices[-1] > 0.9 * 3959
    assert indices != list(range(indices[0], indices[0] + FRAMES_PER_SECTION))


def test_extra_sampler_refuses_a_section_too_short_to_space():
    with pytest.raises(ValueError):
        extra_even_indices(FRAMES_PER_SECTION * (MIN_INDEX_GAP - 1), FRAMES_PER_SECTION, "s")


def test_codex_binary_resolves_from_disk_rather_than_a_pinned_hash(tmp_path, monkeypatch):
    """The Codex app deletes its old hashed bin dir on update; a pinned path then
    fails to spawn and the batch dies silently. Resolve from disk instead."""
    import os
    import time

    from scripts.platformkit.tracking import g373_rate

    for name in ("old", "new"):
        (tmp_path / name).mkdir()
        for required in g373_rate.REQUIRED_CODEX_FILES:
            (tmp_path / name / required).write_text(name, encoding="ascii")
    stale = time.time() - 9999
    os.utime(tmp_path / "old" / "codex.exe", (stale, stale))
    monkeypatch.setattr(g373_rate, "CODEX_BIN_ROOT", str(tmp_path))

    monkeypatch.setattr(g373_rate, "CODEX_PINNED", "gone")
    assert g373_rate.codex_binary() == str(tmp_path / "new" / "codex.exe")

    monkeypatch.setattr(g373_rate, "CODEX_PINNED", "old")
    assert g373_rate.codex_binary() == str(tmp_path / "old" / "codex.exe")

    # A directory holding codex.exe but NOT the image host is a PARTIALLY restored
    # install: it launches, exits 0 and rates nothing. Never select it.
    (tmp_path / "old" / "codex-code-mode-host.exe").unlink()
    assert not g373_rate.complete_install(tmp_path / "old")
    assert g373_rate.codex_binary() == str(tmp_path / "new" / "codex.exe")

    (tmp_path / "new" / "codex-code-mode-host.exe").unlink()
    with pytest.raises(SystemExit):
        g373_rate.codex_binary()


def test_q6_scan_finds_a_reserved_word_but_exempts_it_inside_a_path():
    from scripts.platformkit.tracking.g373_q6_scan import patterns, scan_text

    rules = patterns()
    word = "".join(chr(code) for code in (101, 100, 103, 101))
    findings, exempt, _ = scan_text("the ball sits near the " + word + " of the frame", rules)
    assert findings == 1 and exempt == 0
    findings, exempt, _ = scan_text("docs/evidence/tracking/" + word + "_case.csv", rules)
    assert findings == 0 and exempt == 1


def test_q6_reason_normalisation_touches_only_the_free_text():
    from scripts.platformkit.tracking.g373_q6_scan import patterns, scan_text
    from scripts.platformkit.tracking.g373_rate import neutralise

    word = "".join(chr(code) for code in (101, 100, 103, 101))
    cleaned, changed = neutralise("ball near left " + word + " of court")
    assert changed
    assert scan_text(cleaned, patterns())[0] == 0


def _rating(rater, label, x=None, y=None, w=None, h=None, stage="full_frame"):
    box = {"box_x": x, "box_y": y, "box_w": w, "box_h": h}
    centre = {"cx": (x + w / 2.0) if x is not None else "",
              "cy": (y + h / 2.0) if y is not None else ""}
    return {"frame_key": "k", "rater": rater, "label": label, "pass": stage,
            "reason": "", **{key: ("" if value is None else value)
                             for key, value in box.items()}, **centre}


def test_crop_refine_supersedes_that_raters_full_frame_row():
    from scripts.platformkit.tracking.g373_reference_v2 import latest

    rows = [_rating("terra", "VISIBLE", 10, 10, 20, 20),
            _rating("terra", "VISIBLE", 12, 12, 18, 18, stage="crop_refine")]
    assert latest(rows)["box_x"] == 12


def test_usability_bar_is_limit_below_thirty_pairs_however_tight():
    from scripts.platformkit.tracking.g373_reference_v2 import by_frame, pair_diagnostics

    ratings = []
    for index in range(5):
        for rater in ("sol", "terra"):
            row = _rating(rater, "VISIBLE", 100, 100, 40, 40)
            row["frame_key"] = f"k{index}"
            ratings.append(row)
    result = pair_diagnostics([f"k{index}" for index in range(5)], by_frame(ratings))
    assert result["centre_disagreement_native_px"]["p50"] == 0.0
    assert result["bar"]["verdict"] == "LIMIT"


def test_adjudication_queue_flags_disagreement_and_wide_centres():
    from scripts.platformkit.tracking.g373_reference_v2 import adjudication_queue, by_frame

    ratings = [_rating("sol", "VISIBLE", 100, 100, 20, 20),
               _rating("terra", "ABSENT")]
    wide = [dict(_rating("sol", "VISIBLE", 100, 100, 20, 20), frame_key="w"),
            dict(_rating("terra", "VISIBLE", 400, 100, 20, 20), frame_key="w")]
    tight = [dict(_rating("sol", "VISIBLE", 100, 100, 40, 40), frame_key="t"),
             dict(_rating("terra", "VISIBLE", 101, 100, 40, 40), frame_key="t")]
    queue = adjudication_queue(["k", "w", "t"], by_frame(ratings + wide + tight))
    reasons = {row["frame_key"]: row["why"] for row in queue}
    assert reasons["k"] == "LABEL-DISAGREEMENT"
    assert reasons["w"] == "CENTRE-GAP"
    assert "t" not in reasons


def test_census_counts_an_unsettled_frame_rather_than_dropping_it():
    from scripts.platformkit.tracking.g373_reference_v2 import by_frame, census

    scheduled = [{"frame_key": "k", "split": "heldout", "source": "sealed"}]
    rows, summary = census(scheduled, by_frame([_rating("sol", "VISIBLE", 10, 10, 20, 20),
                                                _rating("terra", "ABSENT")]))
    assert rows == []
    assert summary["unsettled_frames"] == 1


def test_census_refuses_to_average_a_wide_visible_pair():
    from scripts.platformkit.tracking.g373_reference_v2 import by_frame, census

    scheduled = [{"frame_key": "k", "split": "development", "source": "extra"}]
    rows, summary = census(scheduled, by_frame([_rating("sol", "VISIBLE", 100, 100, 20, 20),
                                                _rating("terra", "VISIBLE", 400, 100, 20, 20)]))
    assert rows == []
    assert summary["unsettled_wide_or_boxless_pair"] == 1

    rows, summary = census(scheduled, by_frame([_rating("sol", "VISIBLE", 100, 100, 40, 40),
                                                _rating("terra", "VISIBLE", 101, 100, 40, 40)]))
    assert len(rows) == 1 and rows[0]["decided_by"] == "AGREED"
    assert summary["unsettled_wide_or_boxless_pair"] == 0


def test_rating_parser_refuses_fabricated_and_out_of_frame_boxes():
    from scripts.platformkit.tracking.g373_rate import parse_batch

    path = REPO / "tests" / "platformkit" / "_g373_parse_probe.txt"
    path.write_text("\n".join([
        "aaaaaaaaaaaa,VISIBLE,100,100,20,20,on court",
        "bbbbbbbbbbbb,ABSENT,5,5,5,5,fabricated box",
        f"cccccccccccc,VISIBLE,1910,100,40,20,off the right {_W}",
        "dddddddddddd,UNKNOWN,,,,,unclear",
    ]) + "\n", encoding="ascii")
    try:
        keys = {short: short * 5 for short in
                ("aaaaaaaaaaaa", "bbbbbbbbbbbb", "cccccccccccc", "dddddddddddd")}
        rows = parse_batch(path, "terra", list(keys), keys)
    finally:
        path.unlink()
    assert [row["label"] for row in rows] == ["VISIBLE", "UNKNOWN"]
    assert rows[0]["cx"] == 110.0


def test_short_empty_box_row_survives_but_short_visible_row_does_not():
    from scripts.platformkit.tracking.g373_rate import parse_batch

    path = REPO / "tests" / "platformkit" / "_g373_short_probe.txt"
    path.write_text("\n".join([
        "aaaaaaaaaaaa,ABSENT,,,,bench closeup",
        "bbbbbbbbbbbb,VISIBLE,100,100,20,in play",
    ]) + "\n", encoding="ascii")
    try:
        keys = {"aaaaaaaaaaaa": "a" * 64, "bbbbbbbbbbbb": "b" * 64}
        rows = parse_batch(path, "sol", list(keys), keys)
    finally:
        path.unlink()
    assert [row["label"] for row in rows] == ["ABSENT"]
    assert rows[0]["reason"] == "bench closeup"


def test_a0_repeatability_ignores_number_formatting_not_geometry():
    archived = [{"arm": "A0", "split": "heldout", "frame_key": "k", "rank": "0", "x": "10",
                 "y": "20", "w": "5", "h": "5", "score": "+0.061432000",
                 "tick_history": "OBSERVED", "source": "full"}]
    same = [dict(archived[0], score="0.061432")]
    moved = [dict(archived[0], x="11", score="0.061432")]
    assert rows_identical(archived, same)["rows_identical"]
    assert not rows_identical(archived, moved)["rows_identical"]


def test_q6_redactor_is_idempotent_and_preserves_label_field(tmp_path):
    from scripts.platformkit.tracking.g373_q6_redact import redact

    evidence = tmp_path / "evidence"
    batches = evidence / "raters_v2"
    batches.mkdir(parents=True)
    batch = batches / "sol_batch_01.txt"
    batch.write_bytes(f"key,VISIBLE,1,2,3,4,ball at left {_W}\r\n".encode())
    derived = evidence / "ratings.csv"
    derived.write_bytes(f"label,reason\r\n{_W},VISIBLE ball at right {_W}\r\n".encode())
    manifest = evidence / "q6_redaction_manifest.csv"
    first = redact(evidence, manifest)
    snapshot = {path: path.read_bytes() for path in (batch, derived, manifest)}
    second = redact(evidence, manifest)
    assert len(first) == 2
    assert not second
    assert snapshot == {path: path.read_bytes() for path in snapshot}
    assert batch.read_bytes() == b"key,VISIBLE,1,2,3,4,ball at left border\r\n"
    assert derived.read_bytes() == f"label,reason\r\n{_W},VISIBLE ball at right border\r\n".encode()
