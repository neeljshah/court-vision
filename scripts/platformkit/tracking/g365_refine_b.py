"""G365 candidate B: template-guided re-association rounds over candidate A's residual machinery.

Attempt 1 measured why candidate A was rejected, and this module answers exactly those two findings
and nothing else. Its constants are sealed in `docs/evidence/tracking/
g365_fitter_refinement_2026-09-09/g365_prereg_att2_2026-09-09.md` sections 2 and 3.

(1) G3_TIGHT was dragged by FOREIGN supports: 56 of its 678 assigned supports sat more than 3 px
    from EVERY true straight marking, and across candidate A the median forward residual ON THOSE
    supports fell 8.4502 -> 6.0527 px while the clean supports' median rose 0.0000 -> 1.1466 px. A
    correspondence computed ONCE from the 4-corner matrix can never expel them. Candidate B
    RE-GATHERS its supports from the CURRENT projection every round, inside a band narrower than
    candidate A's assignment radius, so a support that is not on a marking leaves the fit.
(2) G2_WIDE was a SYMMETRY-BASIN initialisation: the nine straight markings are exactly invariant
    under the court mirror x -> 50 - x, so its 4-corner winner recovers the court mirrored (469.2083
    px against the truth, 1.9159 px against the truth composed with that mirror). No local
    refinement of a mirror-invariant objective can cross that, which is what `init_fail` names.

The residual itself is IMPORTED from `g365_refine`, never copied: candidate A stays the code it was
when it was measured, and any drift in it would show up in both arms at once.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import least_squares

from scripts.platformkit.tracking import g365_refine as rf
from scripts.platformkit.tracking.g334_court_template import HALF_COURT_QUAD

BAND_B_PX = 6.0
HUBER_DELTA_B_PX = 1.0
ROUNDS_B = 3
CONV_B_PX = 0.01
WEIGHT_CLIP = (0.5, 2.0)
INIT_FAIL_PX = 50.0
INIT_FAIL_STATE = "REFUSED"
OPTIMISER_B = ("scipy.optimize.least_squares(method=trf, loss=huber), "
               "%d template-guided re-association rounds" % ROUNDS_B)


def gather(matrix: np.ndarray, supports: np.ndarray, lines: list,
           band: float = BAND_B_PX) -> np.ndarray:
    """Nearest projected straight marking within `band` for each support, or -1.

    This is candidate A's assignment rule at a NARROWER radius, called once per round instead of
    once per run. Re-cutting the correspondence is the whole point of candidate B, and it stays
    reproducible from the archived inputs because the sequence of matrices is itself a function of
    the starting matrix and the sealed constants alone.
    """
    return rf.assign_supports(matrix, supports, lines, max_px=float(band))


def round_weights(lengths: np.ndarray, keep: np.ndarray) -> np.ndarray:
    """w = L / median(L) over the kept set, clipped to WEIGHT_CLIP. Ones when L is unusable.

    The clip is sealed: it holds the effective robust scale within a factor of 1.42 of the sealed
    f_scale, so the loss does not quietly become a different loss on the longest markings.
    """
    n = int(np.asarray(keep, dtype=bool).sum())
    values = np.asarray(lengths, dtype=float)[np.asarray(keep, dtype=bool)]
    if not len(values) or not np.isfinite(values).all():
        return np.ones(n, dtype=float)
    median = float(np.median(values))
    if not math.isfinite(median) or median <= 0.0:
        return np.ones(n, dtype=float)
    return np.clip(values / median, WEIGHT_CLIP[0], WEIGHT_CLIP[1])


def _weighted_residuals(params, supports, court_a, court_b, court_coef, scale, root_w):
    """Candidate A's residual, imported, with each support's pair scaled by sqrt(w)."""
    residual = rf._residuals(params, supports, court_a, court_b, court_coef, scale)
    return residual * np.concatenate((root_w, root_w))


def _corner_shift(a: np.ndarray, b: np.ndarray) -> float:
    """Largest displacement of the four half-court image corners between two matrices."""
    moved = np.abs(rf.apply_h(a, HALF_COURT_QUAD) - rf.apply_h(b, HALF_COURT_QUAD))
    return float(moved.max()) if np.isfinite(moved).all() else float("inf")


def refine_b(matrix: np.ndarray, fit_supports: np.ndarray, lengths=None, template_lines: list = None,
             delta: float = HUBER_DELTA_B_PX, rounds: int = ROUNDS_B, band: float = BAND_B_PX,
             max_iter: int = rf.MAX_ITER, tol: float = rf.TOL):
    """Refine `matrix` over `fit_supports` ALONE, re-gathering the correspondence each round.

    Returns (matrix, stats). The starting matrix is returned unchanged, with a named status,
    whenever a round cannot be posed; a round whose answer is degenerate returns the PREVIOUS
    round's matrix. Refusing to move is a valid outcome (contract B3).
    """
    lines = rf.straight_template_lines() if template_lines is None else template_lines
    start = np.asarray(matrix, dtype=float)
    start = start / start[2, 2]
    sup = np.asarray(fit_supports, dtype=float).reshape(-1, 2)
    parent = (np.ones(len(sup), dtype=float) if lengths is None
              else np.asarray(lengths, dtype=float).reshape(-1))
    scale = rf.px_per_ft(start)
    stats = {"optimiser": OPTIMISER_B, "huber_delta_px": float(delta), "band_px": float(band),
             "rounds_max": int(rounds), "conv_px": CONV_B_PX, "weight_clip": list(WEIGHT_CLIP),
             "max_iter": int(max_iter), "tol": float(tol), "n_supports": int(len(sup)),
             "n_kept": 0, "n_fev": 0, "rounds_run": 0, "kept_per_round": [], "shift_per_round": [],
             "status": "unrun", "refined": False}
    if len(parent) != len(sup):
        raise ValueError("lengths must carry one entry per support")
    if not math.isfinite(scale) or scale <= 0.0:
        stats["status"] = "bad_scale"
        return start, stats
    stats["px_per_ft"] = float(scale)
    current = start
    for _round in range(int(rounds)):
        index = gather(current, sup, lines, band)
        keep = index >= 0
        stats["kept_per_round"].append(int(keep.sum()))
        if int(keep.sum()) < rf.MIN_ASSIGNED:
            if not stats["refined"]:
                stats["status"] = "too_few_assigned"
                return start, stats
            stats["status"] = "too_few_assigned"
            break
        points, assigned = sup[keep], index[keep]
        court_a = np.asarray([lines[i][0] for i in assigned], dtype=float)
        court_b = np.asarray([lines[i][1] for i in assigned], dtype=float)
        court_coef = rf.line_coefficients(court_a, court_b)
        root_w = np.sqrt(round_weights(parent, keep))
        result = least_squares(_weighted_residuals, current.ravel()[:8], method="trf", loss="huber",
                               f_scale=float(delta), max_nfev=int(max_iter), xtol=tol, ftol=tol,
                               gtol=tol, args=(points, court_a, court_b, court_coef, scale, root_w))
        stats["n_fev"] += int(result.nfev)
        candidate = rf._matrix_of(result.x)
        if not np.isfinite(candidate).all() or abs(float(np.linalg.det(candidate))) < 1e-12:
            stats["status"] = "degenerate"
            return (current if stats["refined"] else start), stats
        candidate = candidate / candidate[2, 2]
        shift = _corner_shift(candidate, current)
        stats["shift_per_round"].append(round(shift, 6))
        stats["n_kept"] = int(keep.sum())
        stats["cost"] = float(result.cost)
        current, stats["rounds_run"] = candidate, stats["rounds_run"] + 1
        stats["status"], stats["refined"] = "ok", True
        if shift <= CONV_B_PX:
            break
    return current, stats


def init_fail(state: str, baseline_gap_px: float, threshold: float = INIT_FAIL_PX) -> bool:
    """The sealed carve-out of amendment section 3: BOTH clauses, never one alone.

    Clause (i) alone would swallow three of attempt 1's four geometries -- G3_TIGHT at 2.0160 px and
    G4_OFF_AXIS at 1.8003 px are also REFUSED and stay fully inside bars 1 and 4. Clause (ii) is what
    keeps the carve-out to a geometry whose initialisation is in a different basin entirely.
    """
    gap = float(baseline_gap_px)
    return str(state) == INIT_FAIL_STATE and math.isfinite(gap) and gap > float(threshold)


def demo() -> None:
    """Self-check: exact stays exact, a foreign support outside the band is expelled, a nudge heals."""
    from scripts.platformkit.tracking import g362_synth as synth

    lines = rf.straight_template_lines()
    truth = synth.known_matrix().astype(float)
    truth = truth / truth[2, 2]
    supports, lengths = [], []
    for start, end in lines:
        pair = rf.apply_h(truth, np.vstack((start, end)))
        run = pair[0] + (pair[1] - pair[0]) * np.linspace(0.0, 1.0, 25)[:, None]
        supports.append(run)
        lengths.append(np.full(len(run), float(np.linalg.norm(pair[1] - pair[0]))))
    supports = np.concatenate(supports, axis=0)
    lengths = np.concatenate(lengths, axis=0)
    exact, stats = refine_b(truth, supports, lengths)
    assert stats["status"] == "ok" and stats["refined"], stats
    assert float(np.abs(rf.apply_h(exact, HALF_COURT_QUAD)
                        - rf.apply_h(truth, HALF_COURT_QUAD)).max()) < 1e-6, stats
    far = supports.copy()
    far[0] = far[0] + np.array([0.0, 40.0])
    index = gather(truth, far, lines)
    assert index[0] == -1, "a support 40 px off every marking must leave the band"
    nudged = truth.copy()
    nudged[0, 2] += 3.0
    moved, moved_stats = refine_b(nudged, supports, lengths)
    before = float(np.abs(rf.apply_h(nudged, HALF_COURT_QUAD)
                          - rf.apply_h(truth, HALF_COURT_QUAD)).max())
    after = float(np.abs(rf.apply_h(moved, HALF_COURT_QUAD)
                         - rf.apply_h(truth, HALF_COURT_QUAD)).max())
    assert after < before, (before, after, moved_stats)
    assert init_fail("REFUSED", 469.2083) and not init_fail("REFUSED", 2.0160)
    assert not init_fail("VALID", 469.2083)
    print("g365_refine_b demo OK")


if __name__ == "__main__":
    demo()
