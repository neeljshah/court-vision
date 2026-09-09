"""G362: registration that can refuse. Synthetic only -- no broadcast frame is opened here.

Run alone:
    python3 -m pytest tests/platformkit/test_g362_registration_refusal.py -q -p no:cacheprovider
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from domains.basketball.tracking.line_calibration import ObservedSegment
from scripts.platformkit.tracking import g362_fit_validate as fv
from scripts.platformkit.tracking import g362_strokes as st
from scripts.platformkit.tracking import g362_synth as synth
from scripts.platformkit.tracking.g334_court_template import TEMPLATE_POINTS
from scripts.platformkit.tracking.g334_seal import SEAL_PREFIX, scan_text, seal_hex

PREREG = (Path(__file__).resolve().parents[2] / "docs" / "evidence" / "tracking"
          / "g362_registration_refusal_2026-09-09" / "g362_prereg_2026-09-09.md")


def _segment(x1, y1, x2, y2):
    return ObservedSegment(endpoints=(x1, y1, x2, y2))


@pytest.fixture(scope="module")
def court_decision():
    return synth.known_matrix(), fv.decide(synth.render_court())


def test_known_h_recovery_accepts_the_true_court_and_lands_near_the_truth(court_decision):
    """The DETECTED-line path recovers the fixture's known H and the cascade ACCEPTS it.

    The sealed BUILD-GATE bar is 1.0 px and this box does NOT meet it: the builder measured
    1.6516 px here, and 1.33 to 1.89 px on three further synthetic view geometries, so the bar is
    reported unmet rather than lowered (Q3) and the verdict is PARTIAL on that clause. What this test
    pins is the behaviour the rest of the row depends on -- a true court is accepted, and the fit
    lands inside the sealed 8 px held-out residual bar rather than somewhere else on the frame.
    """
    truth, decision = court_decision
    assert decision.state == fv.STATE_VALID, (decision.state, decision.reason)
    gap = synth.reprojection_median(truth, decision.image_matrix, TEMPLATE_POINTS)
    assert np.isfinite(gap) and gap <= fv.MAX_MEDIAN_PX, gap


def test_the_build_gate_verdict_is_the_sealed_bar_comparison(tmp_path):
    """Q3: the gate's exit code is the 1.0 px comparison, whatever this box measures."""
    import json

    from scripts.platformkit.tracking import g362_controls as ctl

    assert ctl.KNOWN_H_BAR_PX == 1.0
    code = ctl.known_h(tmp_path)
    payload = json.loads((tmp_path / "known_h.json").read_text(encoding="ascii"))
    met = (payload["state"] == fv.STATE_VALID
           and payload["reprojection_median_px"] <= ctl.KNOWN_H_BAR_PX)
    assert (code == 0) == met
    assert payload["verdict"] == ("PASS" if met else "PARTIAL")


def test_accept_is_judged_on_strokes_the_fit_never_saw(court_decision):
    """The accept carries held-out evidence: two families and at least 30 held-out supports."""
    _truth, decision = court_decision
    assert decision.n_val_families >= fv.MIN_VAL_FAMILIES
    assert decision.n_val_points >= fv.MIN_VAL_POINTS
    assert max(decision.forward_median, decision.inverse_median) <= fv.MAX_MEDIAN_PX


def test_partition_reserves_a_quarter_and_fit_never_sees_the_held_out_strokes():
    """>= 25 pct of whole strokes are reserved, and the two sides share no stroke or segment."""
    strokes = st.extract_strokes(synth.render_court())
    fit, validation = st.partition(strokes)
    assert len(strokes) >= fv.MIN_STROKES
    assert len(validation) >= -(-len(strokes) // st.VALIDATION_DIVISOR)
    fit_ids = {stroke.stroke_id for stroke in fit}
    val_ids = {stroke.stroke_id for stroke in validation}
    assert fit_ids and val_ids and not (fit_ids & val_ids)
    fit_segments = {id(segment) for segment in st.segments_of(fit)}
    val_segments = {id(segment) for segment in st.segments_of(validation)}
    assert not (fit_segments & val_segments), "a physical stroke was split across the partition"


def test_partition_is_deterministic_and_content_addressed():
    """The same strokes give the same split, and the ids come from geometry, not from order."""
    strokes = st.extract_strokes(synth.render_court())
    first = [stroke.stroke_id for stroke in st.partition(strokes)[1]]
    second = [stroke.stroke_id for stroke in st.partition(list(reversed(strokes)))[1]]
    assert first == second
    stroke = strokes[0]
    key = st.stroke_key(stroke.line, stroke.extent)
    assert stroke.digest == hashlib.sha256(key.encode("ascii")).hexdigest()


def test_support_density_is_fixed_by_length_alone():
    """Fragmenting one marking into more segments must not change its support count."""
    whole = st.strokes_from_segments([_segment(20.0, 40.0, 620.0, 40.0),
                                      _segment(20.0, 300.0, 620.0, 300.0),
                                      _segment(20.0, 40.0, 20.0, 300.0),
                                      _segment(620.0, 40.0, 620.0, 300.0)])
    split = st.strokes_from_segments([_segment(20.0, 40.0, 320.0, 40.0),
                                      _segment(320.0, 40.0, 620.0, 40.0),
                                      _segment(20.0, 300.0, 620.0, 300.0),
                                      _segment(20.0, 40.0, 20.0, 300.0),
                                      _segment(620.0, 40.0, 620.0, 300.0)])
    by_id = {stroke.stroke_id: len(stroke.supports) for stroke in whole}
    shared = [stroke for stroke in split if stroke.stroke_id in by_id]
    assert shared, "the two fragmentations share no stroke id"
    assert all(len(stroke.supports) == by_id[stroke.stroke_id] for stroke in shared)


def _short_marking_frame():
    """Two orientation families of SHORT markings: enough to fit, too little to validate."""
    import cv2

    image = np.full((720, 1280, 3), synth.FLOOR_VALUE, dtype=np.uint8)
    for x0, y0, x1, y1 in ((200, 200, 260, 200), (200, 400, 260, 400),
                           (600, 200, 600, 260), (900, 200, 900, 260)):
        cv2.line(image, (x0, y0), (x1, y1), (synth.LINE_VALUE,) * 3, 1, cv2.LINE_AA)
    return image


def test_a_frame_with_too_little_held_out_support_returns_no_validation():
    """Absent supports are NO_VALIDATION -- never VALID, and never counted as a refusal either."""
    decision = fv.decide(_short_marking_frame())
    assert decision.state in (fv.STATE_NO_LINES, fv.STATE_NO_VALIDATION), decision.state
    assert not decision.accepted
    if decision.state == fv.STATE_NO_VALIDATION:
        assert (decision.n_val_points < fv.MIN_VAL_POINTS
                or decision.n_val_families < fv.MIN_VAL_FAMILIES)
    assert fv.decide(np.full((720, 1280, 3), synth.FLOOR_VALUE, np.uint8)).state \
        == fv.STATE_NO_LINES


def test_single_family_frame_cannot_validate():
    """One marking family can never satisfy the two-family held-out bar."""
    strokes = st.strokes_from_segments([_segment(20.0, 40.0 + 30.0 * i, 620.0, 40.0 + 30.0 * i)
                                        for i in range(8)])
    _fit, validation = st.partition(strokes)
    assert len(st.families_of(validation)) < fv.MIN_VAL_FAMILIES


def test_crowd_frame_is_refused_or_has_no_lines():
    """A no-marking frame must not come back VALID -- this is the whole point of the row."""
    decision = fv.decide(synth.render_crowd())
    assert decision.state in (fv.STATE_NO_LINES, fv.STATE_REFUSED), decision.state
    assert not decision.accepted


def test_out_of_frame_template_points_are_charged_the_penalty():
    """A fit that throws the court out of the image cannot buy a small forward median."""
    far = synth.known_matrix().copy()
    far[0, 2] += 100000.0
    forward, _inverse, n_in, n_out = fv.bidirectional(far, np.zeros((0, 2), np.float32), (720, 1280))
    assert n_in == 0 and n_out == len(TEMPLATE_POINTS)
    assert float(np.median(forward)) == fv.PENALTY_PX


def test_even_sampling_is_not_a_head_slice():
    from scripts.platformkit.tracking.g362_controls import even_indices

    indices = even_indices(3000, 60)
    assert len(indices) == 60 and indices == sorted(indices)
    assert indices[0] >= 20 and indices[-1] <= 2999
    assert min(np.diff(indices)) >= 45


def test_prereg_seal_holds_over_lf_normalised_bytes_above_the_seal_line():
    """Q1: the seal covers the LF-normalised body and predates every number in the row."""
    assert PREREG.exists(), PREREG.as_posix()
    text = PREREG.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = [line for line in text.split("\n") if line != ""]
    assert lines[-1].startswith(SEAL_PREFIX), lines[-1]
    assert lines[-1][len(SEAL_PREFIX):].strip() == seal_hex(text)


def test_prereg_and_modules_pass_the_vocabulary_scan():
    """Q6: calibration language only, across the prereg and every module this row adds."""
    root = Path(__file__).resolve().parents[2] / "scripts" / "platformkit" / "tracking"
    paths = [PREREG, Path(__file__)] + [root / ("g362_%s.py" % name) for name in
                                        ("strokes", "fit_validate", "controls", "synth")]
    hits = {path.name: scan_text(path.read_text(encoding="utf-8")) for path in paths}
    assert not any(hits.values()), hits


def test_an_unknown_source_is_skipped_and_the_writers_emit_a_header(tmp_path):
    """G361: a section named by game id alone is not a source, and is skipped rather than scored."""
    from scripts.platformkit.tracking import g362_controls as ctl

    sections = tmp_path / "sections.csv"
    sections.write_text("\n".join((
        "key,path,role,video_id,start_s,video_sha256,bytes,width,height",
        "S1,/nowhere/a.mp4,POSITIVE,abcDEF12345,90,00,1,1920,1080",
        "S2,/nowhere/b.mp4,POSITIVE,,0,00,1,1920,1080",
        "S3,/nowhere/c.mp4,NEGATIVE,xyz98765432,10,00,1,1920,1080",
    )) + "\n", encoding="ascii")
    positives = ctl.read_sections(sections, "POSITIVE")
    assert [row["key"] for row in positives] == ["S1"]
    assert [row["key"] for row in ctl.read_sections(sections, "NEGATIVE")] == ["S3"]
    out = tmp_path / "metrics.csv"
    ctl._write(out, ctl.METRIC_COLS, [["S1"] + ["000000"] * 14])
    lines = out.read_text(encoding="ascii").splitlines()
    assert lines[0] == ctl.METRIC_COLS and len(lines) == 2
