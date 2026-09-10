"""G371 truth-free class selection over the sealed G367 enumeration.

This module intentionally imports G367's candidate enumerator but never its
``search`` route: that route selects the minimum labelled modulo residual.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from scripts.platformkit.tracking import g362_fit_validate as fv
from scripts.platformkit.tracking import g362_strokes as st
from scripts.platformkit.tracking import g365_refine_b as rb
from scripts.platformkit.tracking.g334_court_line_calibration import ARM_A
from scripts.platformkit.tracking.g334_court_template import TEMPLATE_POINTS
from scripts.platformkit.tracking.g367_search import _candidates
from scripts.platformkit.tracking.g367_symmetry import (
    GROUP, compose, equivalent, recovery_modulo_symmetry,
)

SYM_EQ_PX = 2.0
MARGIN_EPSILON = 1e-12
ACCEPT_MARGIN = 0.10
MODULO_FORM = "form_two"
ORIENTATION_UNKNOWN = "UNKNOWN"
CANDIDATE_COLUMNS = (
    "symmetry_class,objective_j,source_element,enumeration_rank,"
    "candidate_hypotheses_count,deduplicated_symmetry_images_count"
)
SELECTED_COLUMNS = (
    "geometry_status,orientation_status,winner_objective_j,runner_up_objective_j,margin,"
    "labelled_gap_px,modulo_gap_px,modulo_form,attaining_element"
)


@dataclass(frozen=True)
class ScoredCandidate:
    """One refined candidate and its FIT-only objective."""

    matrix: np.ndarray
    objective: float
    source_element: str
    enumeration_rank: int


@dataclass(frozen=True)
class Selection:
    """Truth-free class winner, distinct runner-up, and declared outcome."""

    winner: ScoredCandidate | None
    runner_up: ScoredCandidate | None
    margin: float | None
    geometry_status: str
    orientation_status: str = ORIENTATION_UNKNOWN


def _matrix_key(matrix: np.ndarray) -> tuple:
    return tuple(np.round(np.asarray(matrix, dtype=float).ravel(), 9))


def _rank_key(candidate: ScoredCandidate) -> tuple:
    return (-candidate.objective, candidate.enumeration_rank, candidate.source_element,
            _matrix_key(candidate.matrix))


def _unique_ranked(candidates: list[ScoredCandidate]) -> list[ScoredCandidate]:
    """Deduplicate cloned images before classing; ordering is stable under permutation."""
    unique: dict[tuple, ScoredCandidate] = {}
    for item in candidates:
        key = _matrix_key(item.matrix)
        prior = unique.get(key)
        if prior is None or _rank_key(item) < _rank_key(prior):
            unique[key] = item
    return sorted(unique.values(), key=_rank_key)


def _classes(ranked: list[ScoredCandidate]) -> list[list[ScoredCandidate]]:
    """Cluster symmetry-equivalent candidates using the sealed 720p template rail."""
    groups: list[list[ScoredCandidate]] = []
    for item in ranked:
        matched = next((group for group in groups
                        if equivalent(item.matrix, group[0].matrix, TEMPLATE_POINTS, SYM_EQ_PX)), None)
        if matched is None:
            groups.append([item])
        else:
            matched.append(item)
    return groups


def select_from_scored(candidates: list[ScoredCandidate]) -> Selection:
    """Select strictly from FIT-only scores; this function accepts no truth homography."""
    ranked = _unique_ranked(candidates)
    classes = _classes(ranked)
    if not classes:
        return Selection(None, None, None, "NO_CANDIDATES")
    winner = classes[0][0]
    runner_up = next((group[0] for group in classes[1:]), None)
    if runner_up is None:
        return Selection(winner, None, None, "NO_DISTINCT_RUNNER_UP")
    margin = (winner.objective - runner_up.objective) / max(abs(winner.objective), MARGIN_EPSILON)
    status = "ACCEPT" if margin >= ACCEPT_MARGIN else "REFUSED_MARGIN"
    return Selection(winner, runner_up, float(margin), status)


def _lengths(strokes: list) -> np.ndarray:
    from scripts.platformkit.tracking import g365_sweep_b as sb
    return sb.support_lengths(strokes)


def score_frame(frame: np.ndarray) -> tuple[list[ScoredCandidate], dict]:
    """Refine the sealed G367 candidates and score them only on FIT strokes."""
    ranked, hypotheses, images, fit_strokes, field = _candidates(frame)
    supports, lengths = st.support_array(fit_strokes), _lengths(fit_strokes)
    scored = []
    for rank, (_score, source, matrix) in enumerate(ranked, start=1):
        refined, _stats = rb.refine_b(matrix, supports, lengths)
        objective, _n = fv.whole_template_score(refined, field, ARM_A)
        scored.append(ScoredCandidate(refined, float(objective), source, rank))
    return scored, {"candidate_hypotheses_count": int(hypotheses),
                    "deduplicated_symmetry_images_count": int(images),
                    "refined_hypotheses_count": len(scored)}


def heldout_status(matrix: np.ndarray, frame: np.ndarray) -> str:
    """Apply G362's unchanged validation decision after, never during, selection."""
    strokes = st.extract_strokes(frame)
    _fit, validation = st.partition(strokes)
    supports = st.support_array(validation)
    if not len(supports) or len(st.families_of(validation)) < fv.MIN_VAL_FAMILIES:
        return "NO_VALIDATION"
    forward, inverse, _inside, _outside = fv.bidirectional(matrix, supports, frame.shape)
    return "VALID" if max(float(np.median(forward)), float(np.median(inverse))) <= fv.MAX_MEDIAN_PX else "REFUSED_VALIDATION"


def select_frame(frame: np.ndarray) -> tuple[Selection, dict]:
    """Run the selector and then attach the separate held-out geometry outcome."""
    candidates, counts = score_frame(frame)
    selection = select_from_scored(candidates)
    status = selection.geometry_status
    if selection.winner is not None and status == "ACCEPT":
        validation = heldout_status(selection.winner.matrix, frame)
        if validation != "VALID":
            selection = Selection(selection.winner, selection.runner_up, selection.margin, validation)
    return selection, counts


def class_rows(candidates: list[ScoredCandidate]) -> list[dict]:
    """Archive-ready FIT-only class records; label gaps are intentionally absent."""
    ranked = _unique_ranked(candidates)
    rows = []
    for class_id, group in enumerate(_classes(ranked)):
        for item in group:
            rows.append({"symmetry_class": class_id, "objective_j": item.objective,
                         "source_element": item.source_element,
                         "enumeration_rank": item.enumeration_rank})
    return rows


def selection_row(selection: Selection, truth: np.ndarray) -> dict:
    """Attach labels only after selection; this is the sole labelled evaluation helper."""
    blank = {"labelled_gap_px": "", "modulo_gap_px": "", "modulo_form": MODULO_FORM,
             "attaining_element": "", "winner_objective_j": "", "runner_up_objective_j": ""}
    row = {**blank, "geometry_status": selection.geometry_status,
           "orientation_status": selection.orientation_status,
           "margin": "" if selection.margin is None else selection.margin}
    if selection.winner is None:
        return row
    score = recovery_modulo_symmetry(truth, selection.winner.matrix, TEMPLATE_POINTS)
    row.update({"winner_objective_j": selection.winner.objective,
                "runner_up_objective_j": "" if selection.runner_up is None else selection.runner_up.objective,
                "labelled_gap_px": score["labelled_gap_px"],
                "modulo_gap_px": score["modulo_gap_px"],
                "attaining_element": score["attaining_element"]})
    return row


def exact_modulo_gap(truth: np.ndarray) -> float:
    """Smoke helper proving imported group arithmetic is callable without selection labels."""
    mirrored = compose(truth, GROUP[1])
    return float(recovery_modulo_symmetry(truth, mirrored, TEMPLATE_POINTS)["modulo_gap_px"])
