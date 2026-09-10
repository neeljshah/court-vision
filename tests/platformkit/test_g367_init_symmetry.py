"""Focused prepare-time checks for G367's sealed, additive helpers."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from scripts.platformkit.tracking import g334_seal
from scripts.platformkit.tracking import g367_orient as orient
from scripts.platformkit.tracking import g367_search as search
from scripts.platformkit.tracking import g367_symmetry as symmetry
from scripts.platformkit.tracking.g334_court_template import TEMPLATE_POINTS


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/tracking/g367_init_symmetry_2026-09-09/g367_prereg_2026-09-09.md"


def test_mirrored_exact_solution_has_zero_modulo_gap() -> None:
    truth = np.array([[12.0, 0.0, 100.0], [0.0, 12.0, 80.0], [0.0, 0.0, 1.0]])
    mirrored = symmetry.compose(truth, symmetry.MIRROR_X)
    result = symmetry.recovery_modulo_symmetry(truth, mirrored, TEMPLATE_POINTS)
    assert result["labelled_gap_px"] > 1.0
    assert result["modulo_gap_px"] < 1e-8
    assert result["attaining_element"] == "mirror_x"


def test_equivalence_uses_the_sealed_group() -> None:
    first = np.array([[10.0, 0.0, 100.0], [0.0, 10.0, 50.0], [0.0, 0.0, 1.0]])
    assert symmetry.equivalent(first, symmetry.compose(first, symmetry.MIRROR_X), TEMPLATE_POINTS, 2.0)


def test_margin_inside_sealed_band_is_ambiguous() -> None:
    assert search.selectability(search.AMBIG_BAND) == "AMBIGUOUS"
    assert search.selectability(None) == "AMBIGUOUS"


def test_section_selection_is_round_robin_and_capped() -> None:
    rows = [{"section": "v%d_s%d" % (game, section), "game": "g%d" % game,
             "video_id": "v%d" % game, "offset_s": str(section), "bytes": "1", "sha256": "a"}
            for game in range(12) for section in range(3)]
    selected = orient.select_sections(rows)
    assert len(selected) == orient.SECTIONS_TARGET
    assert all(sum(row["game"] == game for row in selected) <= orient.MAX_PER_GAME
               for game in {row["game"] for row in selected})


def test_sheet_builder_has_no_annotation_or_cue_import() -> None:
    source = Path(orient.__file__).read_text(encoding="utf-8")
    assert "put" + "Text" not in source
    assert "g367_" + "cues" not in source


def test_existing_prereg_seal_holds() -> None:
    assert g334_seal.verify_seal(PREREG)
