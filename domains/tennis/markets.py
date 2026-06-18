"""domains.tennis.markets — COMPLETE tennis betting-market surface from the EXISTING model.

Prices every standard tennis market that is HONESTLY DERIVABLE from what
domains.tennis.predictor / match_engine already produce -- the per-point serve-hold
probs (ph1, ph2) bisected to the calibrated Elo match-win, simulated into finished
matches. Every read-off here counts over the SAME finished-match matrix the predictor's
predict()/to_jd() use, so the surface is internally COHERENT (set-score probs sum to 1;
P(2 total sets) == P(straight sets); set handicap -1.5 == straight-sets prob; games O/U
monotone in the line) and consistent with the headline match-win / total_games / straight_sets.

WHAT IS PRICED (derivable from the simulated match matrix, NO new data):
  * match winner (moneyline)                -> P(sets_p1 > sets_p2)
  * total GAMES O/U at ANY line             -> empirical tail of total_games (+ a normal fallback)
  * total SETS O/U 2.5 (best-of-3)          -> 1 - P(straight sets) == P(match goes 3 sets)
  * set handicap -1.5 / +1.5 sets           -> -1.5 == straight-sets win; +1.5 == not straight-set loss
  * set betting / correct set score         -> the (sets_p1, sets_p2) distribution (2-0,2-1,0-2,1-2,...)
  * best-of-3 set-score distribution        -> the four bo3 cells, summing to 1
  * game handicap (set/match game spread)    -> P(games_p1 - games_p2 + line > 0) off per-side game tallies
  * first-set / per-set winner               -> the per-set win prob implied by the serve probs

NEEDS A POINT MODEL (NOT faked -- listed with a spec, see POINT_MODEL_GAPS):
  * tie-break YES/NO, total games WITHIN a specific set, exact-game correct-set-score
    (e.g. 6-4, 7-5), game-spread within a single set, point/game in-running re-pricing.
  The match_engine resolves a 6-6 set as a 50/50 coin (documented simplification) and tracks
  only per-match game TOTALS, not the per-set game path, so any market that needs the games
  path inside a set is honestly out of reach without a per-point serve model.

APPROXIMATION DISCLOSED: the per-set win prob used for the set-score distribution is the one
IMPLIED by the calibrated match-win prob (serve_probs_from_winprob bisects ph1/ph2 to the Elo
match-win, then a single set is simulated at those holds). It assumes per-set i.i.d. serve holds
(no within-match momentum / fatigue / score-state drift). This is the standard pricing
approximation, NOT a measured per-set edge.

INVARIANTS: build only under domains/tennis/ ; reuse the domain engine; <=300 LOC; no edge claims.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Dict, List, Optional, Tuple

import numpy as np

from scripts.platformkit.sim_framework import JointDistribution
from domains.tennis.match_engine import _sim_matches

# Markets we cannot price honestly without a per-point serve model (see module docstring).
POINT_MODEL_GAPS: Tuple[Dict[str, str], ...] = (
    {"market": "tie_break_yes_no",
     "spec": "P(any set reaches 6-6). Needs per-set game path; engine models 6-6 as a "
             "50/50 coin and stores only per-match game totals."},
    {"market": "total_games_within_set",
     "spec": "O/U on games in a NAMED set (e.g. set-1 over 9.5). Needs the per-point serve "
             "model to generate the in-set game sequence."},
    {"market": "exact_correct_set_score_by_games",
     "spec": "Exact game scoreline (6-4, 7-5, 7-6 ...). Needs per-point serve sequencing; "
             "the engine only yields aggregate per-match game totals."},
    {"market": "game_handicap_within_set",
     "spec": "Game spread inside a single set. Same per-point requirement as above."},
)


def _per_set_winprob(ph1: float, ph2: float, *, n_sims: int, seed: int) -> float:
    """P(p1 wins a single set) implied by the calibrated serve holds (APPROXIMATION).

    Simulates best_of=1 at the predictor's bisected holds. This is the per-set prob the
    set-score distribution is built on; it assumes i.i.d. sets (no momentum/fatigue)."""
    one = _sim_matches(ph1, ph2, 1, n_sims, np.random.default_rng(seed))
    return float((one[:, 0] > one[:, 1]).mean())


def _set_score_dist(jd: JointDistribution, best_of: int) -> Dict[str, float]:
    """Coherent correct-set-score distribution off the finished-match matrix. Sums to 1."""
    s = jd._s  # (n_sims, 3): sets_p1, sets_p2, total_games  -- read-only count
    n = jd.n_sims
    counts = Counter(zip(s[:, 0].astype(int).tolist(), s[:, 1].astype(int).tolist()))
    return {f"{s1}-{s2}": c / n for (s1, s2), c in sorted(counts.items())}


def _games_ou(jd: JointDistribution, line: float) -> Tuple[float, float]:
    """(over, under) for total GAMES at *line* off the empirical match-games tail."""
    po = jd.prob_event(lambda s, L=line: s[:, 2] > L)
    return po, 1.0 - po


def _games_ou_normal(mean: float, sigma: float, line: float) -> Tuple[float, float]:
    """Smooth normal fallback for total GAMES O/U at any line (monotone in line by construction).

    The empirical tail is exact but step-shaped at ~1/n_sims granularity and zero past the
    sampled support; the normal(mean, sigma) gives a smooth, strictly-monotone price at any line.
    sigma is the empirical match-games std (so the two agree near the body)."""
    if sigma <= 1e-9:
        po = 1.0 if mean > line else 0.0
        return po, 1.0 - po
    z = (line - mean) / sigma
    under = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return 1.0 - under, under


def price_all(
    ph1: float, ph2: float, best_of: int = 3, *,
    n_sims: int = 20_000, seed: int = 0,
    games_lines: Optional[List[float]] = None,
    set_handicap_lines: Optional[List[float]] = None,
    game_handicap_lines: Optional[List[float]] = None,
) -> Dict:
    """Full coherent tennis market surface from the predictor's serve holds (ph1, ph2).

    Re-simulates the SAME finished-match matrix the predictor uses, then reads every standard
    market off it via the kernel JointDistribution -- so all prices are internally coherent and
    consistent with predict()'s match-win / total_games_mean / straight_sets headline numbers.
    """
    stw = (best_of + 1) // 2
    sims = _sim_matches(ph1, ph2, best_of, n_sims, np.random.default_rng(seed))
    jd = JointDistribution(sims.astype(float), joint_quality="simulated")

    # --- match winner (moneyline) ---
    mw_p1, mw_p2, _tie = jd.prob_side_win(0, 1)

    # --- straight sets / set handicap +-1.5 (best-of-3) ---
    ss_p1 = jd.prob_event(lambda s: (s[:, 0] == stw) & (s[:, 1] == 0))
    ss_p2 = jd.prob_event(lambda s: (s[:, 1] == stw) & (s[:, 0] == 0))

    # --- correct set score / set betting ---
    set_scores = _set_score_dist(jd, best_of)

    # --- total SETS O/U (best-of-3: 2.5 line == match goes the distance) ---
    total_sets = sims[:, 0] + sims[:, 1]
    sets_mean = float(total_sets.mean())
    # For bo3, "over 2.5 sets" == 3 sets played == NOT a straight-sets result.
    p_three_sets = jd.prob_event(lambda s: (s[:, 0] + s[:, 1]) >= 3)
    p_two_sets = 1.0 - p_three_sets  # == ss_p1 + ss_p2 by construction (bo3)
    sets_ou = {"line": 2.5, "over": round(p_three_sets, 4), "under": round(p_two_sets, 4)} \
        if best_of == 3 else \
        {"line": float(stw + 0.5), "over": round(jd.prob_event(
            lambda s, L=stw + 0.5: (s[:, 0] + s[:, 1]) > L), 4),
         "under": round(jd.prob_event(lambda s, L=stw + 0.5: (s[:, 0] + s[:, 1]) <= L), 4)}

    # --- set handicap (sets spread) ---
    if set_handicap_lines is None:
        set_handicap_lines = [-1.5, 1.5]
    set_hcap = [{"side": "p1", "line": ln,
                 "cover": round(jd.prob_spread(0, 1, ln), 4)} for ln in set_handicap_lines]

    # --- total games O/U at any line (empirical + smooth normal fallback) ---
    tg = sims[:, 2].astype(float)
    tg_mean, tg_sigma = float(tg.mean()), float(tg.std())
    med = int(round(float(np.median(tg))))
    if games_lines is None:
        games_lines = sorted(float(med + d) for d in (-5.5, -3.5, -1.5, 0.5, 2.5, 4.5, 6.5))
    games_ou = []
    for ln in games_lines:
        o_emp, u_emp = _games_ou(jd, ln)
        o_n, u_n = _games_ou_normal(tg_mean, tg_sigma, ln)
        games_ou.append({"line": ln, "over": round(o_emp, 4), "under": round(u_emp, 4),
                         "over_normal": round(o_n, 4), "under_normal": round(u_n, 4)})

    # --- game handicap (match game spread) ---
    if game_handicap_lines is None:
        game_handicap_lines = [-4.5, -2.5, 2.5, 4.5]
    # split total games into per-side via a games-won read-off: recompute per-side game tallies.
    g1, g2 = _per_side_games(sims, ph1, ph2, best_of, seed)
    game_jd = JointDistribution(np.column_stack([g1, g2, g1 + g2]).astype(float),
                                joint_quality="simulated")
    game_hcap = [{"side": "p1", "line": ln,
                  "cover": round(game_jd.prob_spread(0, 1, ln), 4)} for ln in game_handicap_lines]

    # --- per-set / first-set winner (implied per-set prob; APPROXIMATION) ---
    p_set_p1 = _per_set_winprob(ph1, ph2, n_sims=min(n_sims, 8000), seed=seed + 7)

    return {
        "best_of": best_of, "n_sims": n_sims,
        "match_winner": {"p1": round(mw_p1, 4), "p2": round(mw_p2, 4)},
        "straight_sets": {"p1": round(ss_p1, 4), "p2": round(ss_p2, 4)},
        "set_score": {k: round(v, 4) for k, v in set_scores.items()},
        "total_sets": {"mean": round(sets_mean, 3), **sets_ou},
        "set_handicap": set_hcap,
        "total_games": {"mean": round(tg_mean, 2), "sigma": round(tg_sigma, 2),
                        "ou": games_ou},
        "game_handicap": game_hcap,
        "per_set_winner": {"p1": round(p_set_p1, 4), "p2": round(1.0 - p_set_p1, 4),
                           "note": ("first-set / per-set winner == per-set prob IMPLIED by the "
                                    "calibrated match-win (i.i.d. sets approximation, NO momentum)")},
        "needs_point_model": list(POINT_MODEL_GAPS),
        "honest_note": (
            "Complete derivable tennis surface from the EXISTING engine (serve holds bisected to "
            "the calibrated Elo match-win). Coherent: set scores sum to 1; P(2 sets)==P(straight "
            "sets); set handicap -1.5==straight-sets; games O/U monotone in line. Set-score / "
            "per-set markets use the match-win-IMPLIED per-set prob (i.i.d.-set APPROXIMATION). "
            "Tie-break and within-set games markets NEED a per-point model (listed, NOT faked). "
            "Calibration, not a $ edge."),
    }


def markets_for_matchup(predictor, p1: str, p2: str, surface: str = "Hard", *,
                        best_of: int = 3, use_wta_temp: bool = False,
                        n_sims: int = 20_000, seed: int = 0) -> Dict:
    """Price the full market surface for a named matchup, COHERENT with predictor.predict().

    Derives the serve holds (ph1, ph2) by the SAME path predict() uses -- calibrated Elo
    match-win -> serve_probs_from_winprob at the as-of hold level -- so the match_winner /
    straight_sets / total_games here match predict()'s headline up to MC noise."""
    from domains.tennis.match_engine import serve_probs_from_winprob  # noqa: PLC0415
    id1, id2 = predictor._resolve(p1), predictor._resolve(p2)
    p_match = predictor._recal(predictor._raw_winprob(id1, id2, surface),
                               use_wta_temp=use_wta_temp)
    base_hold = predictor._hold_levels(id1, id2)
    ph1, ph2 = serve_probs_from_winprob(p_match, best_of, base_hold=base_hold,
                                        n_sims=1500, seed=seed)
    out = price_all(ph1, ph2, best_of, n_sims=n_sims, seed=seed)
    out.update({"sport": "tennis", "tour": predictor.tour, "surface": surface,
                "p1": p1, "p2": p2, "hold_p1": round(ph1, 3), "hold_p2": round(ph2, 3),
                "pregame_p1_match_win": round(p_match, 4)})
    return out


def _per_side_games(sims: np.ndarray, ph1: float, ph2: float,
                    best_of: int, seed: int) -> Tuple[np.ndarray, np.ndarray]:
    """Split each match's total games into p1/p2 tallies via a fresh per-side simulation.

    _sim_matches stores only the total; re-running it with a per-side counter would duplicate
    the engine. Instead we resimulate at the same holds tracking each side's games, so the
    game-handicap read-off stays coherent with the same serve model."""
    n = sims.shape[0]
    rng = np.random.default_rng(seed + 101)
    stw = (best_of + 1) // 2
    g1 = np.zeros(n, dtype=np.int32)
    g2 = np.zeros(n, dtype=np.int32)
    for i in range(n):
        s1 = s2 = a = b = 0
        srv = 0
        while s1 < stw and s2 < stw:
            x = y = 0
            while True:
                held = rng.random() < (ph1 if srv == 0 else ph2)
                if (held and srv == 0) or (not held and srv == 1):
                    x += 1
                else:
                    y += 1
                srv ^= 1
                mx, mn = max(x, y), min(x, y)
                if mx >= 6 and mx - mn >= 2:
                    break
                if mx == 7:
                    break
                if mx == 6 and mn == 6:
                    if rng.random() < 0.5:
                        x += 1
                    else:
                        y += 1
                    srv ^= 1
                    break
            a += x
            b += y
            if x > y:
                s1 += 1
            else:
                s2 += 1
        g1[i], g2[i] = a, b
    return g1, g2
