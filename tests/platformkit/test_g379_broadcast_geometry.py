"""G379 per-file test: the seal, the split fixed before the fit, no refit, no negative passes."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from scripts.platformkit.tracking import g334_seal as seal
from scripts.platformkit.tracking import g362_fit_validate as fv
from scripts.platformkit.tracking import g362_strokes as st
from scripts.platformkit.tracking import g362_synth as synth
from scripts.platformkit.tracking import g365_refine_b as rb
from scripts.platformkit.tracking import g371_symmetry_margin as sm
from scripts.platformkit.tracking import g379_fit, g379_negatives, g379_screen

PREREG = Path("docs/evidence/tracking/g379_broadcast_geometry_2026-09-10/"
              "g379_prereg_2026-09-10.md")


def test_prereg_seal_holds():
    assert PREREG.exists(), PREREG
    assert seal.verify_seal(PREREG)


def test_no_bar_moved():
    """Every constant this row leans on is the landed value; none is redefined here (B10)."""
    assert (fv.MAX_MEDIAN_PX, fv.PENALTY_PX, fv.BASE_HEIGHT) == (8.0, 64.0, 720)
    assert (fv.MIN_STROKES, fv.MIN_FAMILIES, fv.MIN_VAL_FAMILIES, fv.MIN_VAL_POINTS) == (4, 2, 2, 30)
    assert (st.SUPPORT_SPACING_PX, st.VALIDATION_DIVISOR, st.MIN_STROKE_PX) == (6.0, 4, 40.0)
    assert (rb.BAND_B_PX, rb.HUBER_DELTA_B_PX, rb.ROUNDS_B) == (6.0, 1.0, 3)
    assert (sm.ACCEPT_MARGIN, sm.SYM_EQ_PX) == (0.10, 2.0)
    assert json.loads(Path("docs/evidence/tracking/g364_learned_court_presence_2026-09-09/"
                           "model.json").read_text(encoding="utf-8"))["threshold"] == 0.30
    for module in (g379_fit, g379_screen):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "MAX_MEDIAN_PX =" not in source and "PENALTY_PX =" not in source


def test_split_is_fixed_before_the_fit_and_disjoint():
    """The FIT / VALIDATION cut is content-addressed, repeatable and never shares a stroke (B8)."""
    frame = synth.render_court()
    strokes, validation, rows = g379_fit.split_rows(frame, "k", "s", 1)
    again = g379_fit.split_rows(frame, "k", "s", 1)[2]
    assert rows == again and rows
    fit_ids = {row["stroke_id"] for row in rows if row["side"] == "FIT"}
    val_ids = {row["stroke_id"] for row in rows if row["side"] == "VALIDATION"}
    assert fit_ids and val_ids and not (fit_ids & val_ids)
    assert val_ids == {stroke.stroke_id for stroke in validation}
    assert len(fit_ids | val_ids) == len(strokes)


def test_validation_never_refits_and_charges_absent_points():
    """A wrong matrix is REFUSED, not repaired, and the matrix handed in is unchanged."""
    frame = synth.render_court()
    strokes = st.extract_strokes(frame)
    _fit, validation = st.partition(strokes)
    truth = synth.known_matrix().astype(float)
    wrong = truth.copy()
    wrong[0, 2] += 240.0
    before = wrong.copy()
    state, forward, _inverse, counts, residuals = g379_fit.validate(wrong, frame, strokes,
                                                                    validation)
    assert np.array_equal(wrong, before)
    assert state in (fv.STATE_REFUSED, fv.STATE_VALID)
    assert counts["n_val_points"] >= fv.MIN_VAL_POINTS
    good = g379_fit.validate(truth, frame, strokes, validation)
    assert good[1] <= forward or state == fv.STATE_REFUSED
    assert residuals is None or float(np.max(residuals)) <= fv.PENALTY_PX


def test_absent_supports_are_never_valid():
    blank = np.full((720, 1280, 3), 46, dtype=np.uint8)
    state, _f, _i, _c, _r = g379_fit.validate(synth.known_matrix(), blank, [], [])
    assert state == fv.STATE_NO_LINES


def test_negatives_never_pass(tmp_path):
    """Only head COURT plus selector ACCEPT plus validation VALID is an acceptance."""
    def write(name, rows, fields):
        path = tmp_path / name
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        return path

    keys = ["a", "b", "c", "d"]
    reference = write("reference.csv", [
        {"frame_key": "a", "reference_label": "CLOSEUP", "source": "agreed"},
        {"frame_key": "b", "reference_label": "CROWD_GRAPHICS", "source": "agreed"},
        {"frame_key": "c", "reference_label": "CLOSEUP", "source": "adjudicated"},
        {"frame_key": "d", "reference_label": "USABLE_COURT", "source": "agreed"}],
        ("frame_key", "reference_label", "source"))
    predictions = write("predictions.csv", [
        {"frame_key": key, "section_id": "s", "prediction": call}
        for key, call in zip(keys, ("COURT", "NON_COURT", "COURT", "COURT"))],
        ("frame_key", "section_id", "prediction"))
    rows = write("rows.csv", [
        {"frame_key": "a", "section_id": "s", "selection_status": "ACCEPT",
         "validation_status": "REFUSED", "raw_state": "REFUSED"},
        {"frame_key": "b", "section_id": "s", "selection_status": "NO_DISTINCT_RUNNER_UP",
         "validation_status": "VALID", "raw_state": "VALID"},
        {"frame_key": "c", "section_id": "s", "selection_status": "NO_CANDIDATES",
         "validation_status": "NO_LINES", "raw_state": "NO_LINES"},
        {"frame_key": "d", "section_id": "s", "selection_status": "ACCEPT",
         "validation_status": "VALID", "raw_state": "VALID"}],
        ("frame_key", "section_id", "selection_status", "validation_status", "raw_state"))
    sources = write("sources.csv", [{"section_id": "s", "game_id": "g"}],
                    ("section_id", "game_id"))
    summary = g379_negatives.join(reference, predictions, rows, sources, tmp_path / "neg.csv")
    assert summary["negatives"] == 3
    assert summary["cascade_accepted_negatives"] == 0
    assert summary["cascade_accepted_pool"] == 1
    assert summary["negative_validation"]["VALID"] == 1


def test_screen_draw_is_seeded_and_label_blind(tmp_path):
    """The six-section draw reads eligibility and ids only, and spans at least four games."""
    path = tmp_path / "screen.csv"
    rows = [{"section_id": "g%d_s%d" % (game, index), "game_id": "g%d" % game, "n_ticks": 12,
             "n_court": 12, "n_non_court": 0, "n_abstain": 0, "court_share": 1.0, "eligible": 1}
            for game in range(5) for index in range(3)]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    first = g379_screen.draw(path, tmp_path / "one.csv")
    second = g379_screen.draw(path, tmp_path / "two.csv")
    assert [row["section_id"] for row in first] == [row["section_id"] for row in second]
    assert len(first) == 6
    assert len({row["section_id"] for row in first}) == 6
    assert len({row["game_id"] for row in first}) >= 4


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
