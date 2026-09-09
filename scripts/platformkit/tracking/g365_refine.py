"""G365 joint refinement of a 4-corner homography over every FIT-partition support point.

G362 measured the floor this module attacks: its winning homography comes from ONE
`cv2.getPerspectiveTransform` on four corners intersected from four fitted lines, with no
least-squares refinement over the other detected supports, and it recovers a known H to 1.6516 px
against a 1.0 px bar (`g362_registration_refusal_2026-09-09/known_h.json`). Fed EXACT lines the
same corner solve reprojects the 398-point template at 0.000000 px, so the residue is fitted-line
noise amplified by extrapolation, not the solve and not the detector's integer grid.

What this module adds, and nothing else: starting FROM that 4-corner H, minimise a symmetric
(forward image-pixel plus inverse court-plane) point-to-line residual over the FIT supports only,
under a Huber loss with a sealed delta. The VALIDATION strokes are never read here (contract B8);
they remain the property of `g362_fit_validate.decide`, whose bars this module never touches, never
reads and never re-derives.

Every constant below is sealed in `docs/evidence/tracking/g365_fitter_refinement_2026-09-09/
g365_prereg_2026-09-09.md` section 3 and is not read from anywhere else.
"""
from __future__ import annotations

import math

import cv2
import numpy as np
import scipy
from scipy.optimize import least_squares

from scripts.platformkit.tracking.g334_court_template import HALF_COURT_QUAD, template_polylines

HUBER_DELTA_PX = 2.0
MAX_ITER = 200
TOL = 1e-10
ASSIGN_MAX_PX = 12.0
MIN_ASSIGNED = 12
BIG_PX = 1.0e4
OPTIMISER = "scipy.optimize.least_squares(method=trf, loss=huber)"
# Recorded, not asserted: contract A11 asks which code a number came from, and a solver's version is
# part of that. scipy is present on the pod, so no hand-rolled fallback exists here to drift from it.
VERSIONS = {"numpy": np.__version__, "scipy": scipy.__version__, "cv2": cv2.__version__}


def straight_template_lines() -> list:
    """The nine straight court markings, in feet, as (endpoint, endpoint) pairs.

    The template's three arcs are excluded on purpose: a point-to-LINE residual is defined for a
    straight marking only, and an arc treated as a line would import a bias of its own that would
    then be charged to the refinement.
    """
    return [(np.asarray(line[0], dtype=float), np.asarray(line[-1], dtype=float))
            for line in template_polylines() if len(line) == 2]


def apply_h(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Projective map in float64. cv2 is not used here: its float32 costs sub-pixel resolution."""
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    mat = np.asarray(matrix, dtype=float)
    denom = pts @ mat[2, :2] + mat[2, 2]
    denom = np.where(np.abs(denom) > 1e-12, denom, np.nan)
    return np.column_stack(((pts @ mat[0, :2] + mat[0, 2]) / denom,
                            (pts @ mat[1, :2] + mat[1, 2]) / denom))


def line_coefficients(starts: np.ndarray, ends: np.ndarray) -> np.ndarray:
    """(a, b, c) rows with hypot(a, b) == 1 for the line through each pair; NaN when degenerate."""
    ax, ay = starts[:, 0], starts[:, 1]
    bx, by = ends[:, 0], ends[:, 1]
    coef = np.column_stack((ay - by, bx - ax, ax * by - bx * ay))
    norm = np.hypot(coef[:, 0], coef[:, 1])
    return coef / np.where(norm > 0.0, norm, np.nan)[:, None]


def _polygon_area(points: np.ndarray) -> float:
    x, y = points[:, 0], points[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def px_per_ft(matrix: np.ndarray) -> float:
    """One sealed feet-to-pixel weight, from the image area of the half-court quad under `matrix`.

    The two halves of the residual live in different units. Rather than weight them by a per-point
    Jacobian, which would make the objective depend on where the supports happen to fall, the
    inverse half is scaled by ONE number taken from the STARTING homography and then held fixed for
    the whole run, so the objective is the same function at every iteration.
    """
    quad = apply_h(matrix, HALF_COURT_QUAD)
    if not np.isfinite(quad).all():
        return float("nan")
    truth = _polygon_area(np.asarray(HALF_COURT_QUAD, dtype=float))
    if truth <= 0.0:
        return float("nan")
    return math.sqrt(_polygon_area(quad) / truth)


def assign_supports(matrix: np.ndarray, supports: np.ndarray, lines: list,
                    max_px: float = ASSIGN_MAX_PX) -> np.ndarray:
    """Nearest projected straight marking for each support, or -1 when beyond `max_px`.

    The correspondence is computed ONCE, from the starting homography, and then held fixed. A
    correspondence re-cut at every iteration can walk a support into a neighbouring marking, and the
    run then stops being reproducible from the archived inputs alone.
    """
    starts = np.asarray([line[0] for line in lines], dtype=float)
    ends = np.asarray([line[1] for line in lines], dtype=float)
    coef = line_coefficients(apply_h(matrix, starts), apply_h(matrix, ends))
    sup = np.asarray(supports, dtype=float).reshape(-1, 2)
    if not len(sup):
        return np.zeros(0, dtype=int)
    distance = np.abs(sup @ coef[:, :2].T + coef[:, 2])
    distance = np.where(np.isfinite(distance), distance, np.inf)
    best = np.argmin(distance, axis=1)
    keep = distance[np.arange(len(sup)), best] <= max_px
    return np.where(keep, best, -1)


def _matrix_of(params: np.ndarray) -> np.ndarray:
    return np.array([[params[0], params[1], params[2]],
                     [params[3], params[4], params[5]],
                     [params[6], params[7], 1.0]], dtype=float)


def _residuals(params, supports, court_a, court_b, court_coef, scale):
    """Signed symmetric point-to-line residual, in pixels, one forward and one inverse per support.

    Forward: the perpendicular distance in image pixels from the support to the IMAGE of its
    assigned court marking. Inverse: the perpendicular distance in court feet from the support's
    pre-image to that same marking, converted to pixels by the sealed weight. A homography that
    cannot be inverted, or that sends anything to infinity, is charged BIG_PX rather than dropped,
    so no candidate can buy a small residual by discarding its own supports.
    """
    matrix = _matrix_of(params)
    image_coef = line_coefficients(apply_h(matrix, court_a), apply_h(matrix, court_b))
    forward = (supports[:, 0] * image_coef[:, 0] + supports[:, 1] * image_coef[:, 1]
               + image_coef[:, 2])
    try:
        inverse_matrix = np.linalg.inv(matrix)
    except np.linalg.LinAlgError:
        return np.full(2 * len(supports), BIG_PX)
    court = apply_h(inverse_matrix, supports)
    inverse = (court[:, 0] * court_coef[:, 0] + court[:, 1] * court_coef[:, 1]
               + court_coef[:, 2]) * scale
    out = np.concatenate((forward, inverse))
    return np.where(np.isfinite(out), out, BIG_PX)


def refine_homography(matrix: np.ndarray, fit_supports: np.ndarray, template_lines: list = None,
                      delta: float = HUBER_DELTA_PX, max_iter: int = MAX_ITER,
                      tol: float = TOL):
    """Refine `matrix` over `fit_supports` ALONE. Returns (refined matrix, stats).

    The starting matrix is returned unchanged, with a named status, whenever the refinement cannot
    be posed or its answer is degenerate. Refusing to move is a valid outcome here; silently
    returning a matrix that maps the court onto a point is not.
    """
    lines = straight_template_lines() if template_lines is None else template_lines
    start = np.asarray(matrix, dtype=float)
    start = start / start[2, 2]
    sup = np.asarray(fit_supports, dtype=float).reshape(-1, 2)
    index = assign_supports(start, sup, lines)
    keep = index >= 0
    stats = {"optimiser": OPTIMISER, "huber_delta_px": float(delta), "max_iter": int(max_iter),
             "tol": float(tol), "assign_max_px": ASSIGN_MAX_PX, "n_supports": int(len(sup)),
             "n_assigned": int(keep.sum()), "n_fev": 0, "status": "unrun", "refined": False,
             "median_forward_px": float("nan"), "median_inverse_px": float("nan")}
    scale = px_per_ft(start)
    if stats["n_assigned"] < MIN_ASSIGNED or not math.isfinite(scale) or scale <= 0.0:
        stats["status"] = "too_few_assigned" if stats["n_assigned"] < MIN_ASSIGNED else "bad_scale"
        return start, stats
    stats["px_per_ft"] = float(scale)
    sup, index = sup[keep], index[keep]
    court_a = np.asarray([lines[i][0] for i in index], dtype=float)
    court_b = np.asarray([lines[i][1] for i in index], dtype=float)
    court_coef = line_coefficients(court_a, court_b)
    result = least_squares(_residuals, start.ravel()[:8], method="trf", loss="huber",
                           f_scale=float(delta), max_nfev=int(max_iter), xtol=tol, ftol=tol,
                           gtol=tol, args=(sup, court_a, court_b, court_coef, scale))
    stats["n_fev"] = int(result.nfev)
    stats["cost"] = float(result.cost)
    refined = _matrix_of(result.x)
    if not np.isfinite(refined).all() or abs(float(np.linalg.det(refined))) < 1e-12:
        stats["status"] = "degenerate"
        return start, stats
    final = np.abs(np.asarray(result.fun, dtype=float))
    stats["median_forward_px"] = float(np.median(final[:len(sup)]))
    stats["median_inverse_px"] = float(np.median(final[len(sup):]))
    stats["status"] = "ok"
    stats["refined"] = True
    return refined / refined[2, 2], stats


def demo() -> None:
    """Self-check: exact supports leave an exact homography exact, and a shifted start recovers."""
    from scripts.platformkit.tracking import g362_synth as synth

    lines = straight_template_lines()
    assert len(lines) == 9, len(lines)
    truth = synth.known_matrix().astype(float)
    truth = truth / truth[2, 2]
    supports = []
    for start, end in lines:
        pair = apply_h(truth, np.vstack((start, end)))
        supports.append(pair[0] + (pair[1] - pair[0]) * np.linspace(0.0, 1.0, 25)[:, None])
    supports = np.concatenate(supports, axis=0)
    exact, stats = refine_homography(truth, supports)
    assert stats["status"] == "ok" and stats["refined"], stats
    assert float(np.abs(apply_h(exact, HALF_COURT_QUAD)
                        - apply_h(truth, HALF_COURT_QUAD)).max()) < 1e-6
    nudged = truth.copy()
    nudged[0, 2] += 3.0
    moved, moved_stats = refine_homography(nudged, supports)
    before = float(np.abs(apply_h(nudged, HALF_COURT_QUAD) - apply_h(truth, HALF_COURT_QUAD)).max())
    after = float(np.abs(apply_h(moved, HALF_COURT_QUAD) - apply_h(truth, HALF_COURT_QUAD)).max())
    assert after < before, (before, after, moved_stats)
    print("g365_refine demo OK")


if __name__ == "__main__":
    demo()
