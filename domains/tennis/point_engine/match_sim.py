"""domains.tennis.point_engine.match_sim -- MC chain from the POINT atomic unit
to GAME -> SET -> MATCH, given a `prob_fn(server_id, score_bucket, set_bucket)
-> P(server wins this point)` callable (either PointModel.prob or a naive
constant-rate wrapper -- same interface, so panels compare apples to apples).

Standard tennis scoring rules: game = first to >=4 points, margin>=2; set = first
to 6 games margin>=2, else a tiebreak at 6-6 (first to >=7 points margin>=2); match
= best_of 3 or 5 sets. Server alternates every game; tiebreak server rotation
follows the real 1-then-2-then-2... rule.

TIEBREAK SIMPLIFICATION (declared): tiebreak points look up the model at the
"deuce" score_bucket (18-all-style max-pressure proxy) rather than a dedicated
7-point tiebreak state space -- a deliberate v1 simplification (real tiebreak
score states are a disjoint, much sparser corpus). Upgrade path: a dedicated
tiebreak state table if this proxy is shown to miss.

INVARIANTS: domains-only; ASCII; numpy; <=300 LOC.
Tests: python -m pytest domains/tennis/point_engine/test_match_sim.py -q
"""
from __future__ import annotations

from typing import Callable, Tuple

import numpy as np

from domains.tennis.point_engine.corpus import score_bucket, set_bucket

ProbFn = Callable[[str, int, int], float]
DEUCE_BUCKET = 16


def play_game(server_id: str, prob_fn: ProbFn, set_bucket_ix: int, rng: np.random.Generator) -> bool:
    """Simulate one game point-by-point. Returns True if the server wins the game."""
    sp = rp = 0
    while True:
        sb = score_bucket(min(sp, 4), min(rp, 4))
        p = prob_fn(server_id, sb, set_bucket_ix)
        if rng.random() < p:
            sp += 1
        else:
            rp += 1
        if sp >= 4 and sp - rp >= 2:
            return True
        if rp >= 4 and rp - sp >= 2:
            return False


def _tb_server(k: int, first: str, other: str) -> str:
    """Tiebreak serving order: point 0 = first; then 2-on, alternating."""
    if k == 0:
        return first
    block = (k - 1) // 2
    return other if block % 2 == 0 else first


def play_tiebreak(p1_id: str, p2_id: str, first_server: str, prob_fn: ProbFn,
                   set_bucket_ix: int, rng: np.random.Generator) -> bool:
    """Returns True if p1 wins the tiebreak."""
    other = p2_id if first_server == p1_id else p1_id
    s1 = s2 = 0
    k = 0
    while True:
        server = _tb_server(k, first_server, other)
        p = prob_fn(server, DEUCE_BUCKET, set_bucket_ix)
        server_won = rng.random() < p
        if (server == p1_id) == server_won:
            s1 += 1
        else:
            s2 += 1
        if s1 >= 7 and s1 - s2 >= 2:
            return True
        if s2 >= 7 and s2 - s1 >= 2:
            return False
        k += 1


def play_set(p1_id: str, p2_id: str, first_server: str, prob_fn: ProbFn,
             set_no: int, rng: np.random.Generator) -> Tuple[int, int, str]:
    """Returns (games_p1, games_p2, next_set_first_server)."""
    g1 = g2 = 0
    server = first_server
    sb_ix = set_bucket(set_no)
    while True:
        server_wins = play_game(server, prob_fn, sb_ix, rng)
        if server == p1_id:
            g1 += (1 if server_wins else 0)
            g2 += (0 if server_wins else 1)
        else:
            g2 += (1 if server_wins else 0)
            g1 += (0 if server_wins else 1)
        server = p2_id if server == p1_id else p1_id   # alternates every game
        if g1 >= 6 and g1 - g2 >= 2:
            return g1, g2, server
        if g2 >= 6 and g2 - g1 >= 2:
            return g1, g2, server
        if g1 == 6 and g2 == 6:
            p1_wins_tb = play_tiebreak(p1_id, p2_id, server, prob_fn, sb_ix, rng)
            return (7, 6, server) if p1_wins_tb else (6, 7, server)


def play_match(p1_id: str, p2_id: str, best_of: int, first_server_id: str,
               prob_fn: ProbFn, rng: np.random.Generator) -> Tuple[int, int, int]:
    """Returns (total_games_p1, total_games_p2, p1_sets_won)."""
    sets_to_win = best_of // 2 + 1
    s1 = s2 = 0
    tg1 = tg2 = 0
    server = first_server_id
    set_no = 1
    while s1 < sets_to_win and s2 < sets_to_win:
        g1, g2, server = play_set(p1_id, p2_id, server, prob_fn, set_no, rng)
        tg1 += g1; tg2 += g2
        if g1 > g2:
            s1 += 1
        else:
            s2 += 1
        set_no += 1
    return tg1, tg2, s1


def simulate_match_ensemble(p1_id: str, p2_id: str, best_of: int, first_server_id: str,
                            prob_fn: ProbFn, n: int, seed: int) -> Tuple[np.ndarray, np.ndarray, float]:
    """n MC replicates -> (margin array [tg_p1-tg_p2], total-games array, P(p1 wins match))."""
    rng = np.random.default_rng(seed)
    margins = np.empty(n); totals = np.empty(n); p1_wins = 0
    sets_to_win = best_of // 2 + 1
    for i in range(n):
        tg1, tg2, s1 = play_match(p1_id, p2_id, best_of, first_server_id, prob_fn, rng)
        margins[i] = tg1 - tg2
        totals[i] = tg1 + tg2
        p1_wins += int(s1 >= sets_to_win)
    return margins, totals, p1_wins / n


__all__ = ["play_game", "play_tiebreak", "play_set", "play_match",
           "simulate_match_ensemble", "DEUCE_BUCKET"]
