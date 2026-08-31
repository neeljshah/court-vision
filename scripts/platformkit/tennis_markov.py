"""Research-use tennis Markov pricing backbone.

The game formula follows O'Malley's deuce geometric closure. Sets use
game-level dynamic programming and a tiebreak recursion; matches are the
best-of-three binomial composition of independent identically priced sets.
``importance`` is a normalized finite-difference point sensitivity. The
small correction ``p_effective = p - kappa * importance`` is a Klaassen-
Magnus-style small-effect stress adjustment, not a calibrated edge claim.

Optional calibration reads local Sackmann match CSVs only. Those data are
research-use licensed; users must check the original Sackmann terms before
redistribution or production use. No network fetch is attempted.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

import numpy as np

State = Tuple[int, int, int, int, int, int, str]


def _p(value: float) -> float:
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError("serve probabilities must be in [0, 1]")
    return value


def game_win_prob(p_serve: float) -> float:
    """Return the server's probability of winning a game (O'Malley)."""
    p, q = _p(p_serve), 1.0 - _p(p_serve)
    pre_deuce = p**4 * (1.0 + 4.0 * q + 10.0 * q**2)
    deuce = 20.0 * p**3 * q**3 * p**2 / (p**2 + q**2)
    return float(pre_deuce + deuce)


def _game_from_points(a: int, b: int, p: float) -> float:
    """Price a game from a normalized 0/15/30/40/advantage score."""
    @lru_cache(maxsize=None)
    def rec(x: int, y: int) -> float:
        if x >= 4 and x - y >= 2:
            return 1.0
        if y >= 4 and y - x >= 2:
            return 0.0
        if x >= 3 and y >= 3:
            deuce = p * p / (p * p + (1.0 - p) ** 2)
            if x == y:
                return deuce
            return p + (1.0 - p) * deuce if x > y else p * deuce
        return p * rec(x + 1, y) + (1.0 - p) * rec(x, y + 1)
    return float(rec(int(a), int(b)))


def _tb_server(first: str, point_index: int) -> str:
    if point_index == 0:
        return first
    return ("B" if first == "A" else "A") if ((point_index - 1) // 2) % 2 == 0 else first


def _tiebreak_prob(a: int, b: int, first: str, p_a: float, p_b: float) -> float:
    """Price a tiebreak, including the two-point geometric closure at 6-all."""
    @lru_cache(maxsize=None)
    def rec(x: int, y: int) -> float:
        if x >= 7 and x - y >= 2:
            return 1.0
        if y >= 7 and y - x >= 2:
            return 0.0
        if x == y and x >= 6:
            n = x + y
            first_point = p_a if _tb_server(first, n) == "A" else 1.0 - p_b
            second_point = p_a if _tb_server(first, n + 1) == "A" else 1.0 - p_b
            cycle = first_point * (1.0 - second_point) + (1.0 - first_point) * second_point
            return float(first_point * second_point / (1.0 - cycle))
        n = x + y
        point = p_a if _tb_server(first, n) == "A" else 1.0 - p_b
        return point * rec(x + 1, y) + (1.0 - point) * rec(x, y + 1)
    return float(rec(int(a), int(b)))


def set_win_prob(p_serve_A: float, p_serve_B: float, first_server: str = "A") -> float:
    """Return A's set probability, starting with ``first_server`` serving."""
    p_a, p_b = _p(p_serve_A), _p(p_serve_B)
    if first_server not in ("A", "B"):
        raise ValueError("first_server must be 'A' or 'B'")
    hold_a, hold_b = game_win_prob(p_a), game_win_prob(p_b)

    @lru_cache(maxsize=None)
    def rec(a: int, b: int, server: str) -> float:
        if a >= 6 and a - b >= 2:
            return 1.0
        if b >= 6 and b - a >= 2:
            return 0.0
        if a == b == 6:
            return _tiebreak_prob(0, 0, server, p_a, p_b)
        game = hold_a if server == "A" else 1.0 - hold_b
        other = "B" if server == "A" else "A"
        return game * rec(a + 1, b, other) + (1.0 - game) * rec(a, b + 1, other)
    return float(rec(0, 0, first_server))


def match_win_prob(p_serve_A: float, p_serve_B: float, first_server: str = "A") -> float:
    """Return A's best-of-three match probability from the set price."""
    s = set_win_prob(p_serve_A, p_serve_B, first_server)
    return float(s * s * (3.0 - 2.0 * s))


def win_prob(state: State, p_serve_A: float, p_serve_B: float) -> float:
    """Price A from ``(setsA, setsB, gamesA, gamesB, pointsA, pointsB, server)``."""
    p_a, p_b = _p(p_serve_A), _p(p_serve_B)
    if len(state) != 7 or state[-1] not in ("A", "B"):
        raise ValueError("state must be seven values ending in server 'A' or 'B'")
    sa, sb, ga, gb, pa, pb, server = state
    if min(sa, sb, ga, gb, pa, pb) < 0:
        raise ValueError("state scores cannot be negative")
    if sa >= 2:
        return 1.0
    if sb >= 2:
        return 0.0

    @lru_cache(maxsize=None)
    def rec(xsa: int, xsb: int, xga: int, xgb: int, xpa: int, xpb: int, srv: str) -> float:
        if xsa >= 2:
            return 1.0
        if xsb >= 2:
            return 0.0
        if xga == xgb == 6:
            tb = _tiebreak_prob(xpa, xpb, srv, p_a, p_b)
            next_srv = "B" if srv == "A" else "A"
            return tb * rec(xsa + 1, xsb, 0, 0, 0, 0, next_srv) + (1.0 - tb) * rec(xsa, xsb + 1, 0, 0, 0, 0, next_srv)
        if xga >= 6 and xga - xgb >= 2:
            return rec(xsa + 1, xsb, 0, 0, 0, 0, srv)
        if xgb >= 6 and xgb - xga >= 2:
            return rec(xsa, xsb + 1, 0, 0, 0, 0, srv)
        game_p = _game_from_points(xpa, xpb, p_a if srv == "A" else 1.0 - p_b)
        next_srv = "B" if srv == "A" else "A"
        a_next = rec(xsa, xsb, xga + 1, xgb, 0, 0, next_srv)
        b_next = rec(xsa, xsb, xga, xgb + 1, 0, 0, next_srv)
        return game_p * a_next + (1.0 - game_p) * b_next
    return float(rec(int(sa), int(sb), int(ga), int(gb), int(pa), int(pb), server))


def point_importance(state: State, p_serve_A: float, p_serve_B: float) -> float:
    """Return normalized absolute A-point sensitivity at the supplied state."""
    sa, sb, ga, gb, pa, pb, server = state
    if ga == gb == 6:
        a_state = (sa, sb, ga, gb, pa + 1, pb, server)
        b_state = (sa, sb, ga, gb, pa, pb + 1, server)
    else:
        a_state = (sa, sb, ga, gb, pa + 1, pb, server)
        b_state = (sa, sb, ga, gb, pa, pb + 1, server)
    return float(np.clip(abs(win_prob(a_state, p_serve_A, p_serve_B) - win_prob(b_state, p_serve_A, p_serve_B)), 0.0, 1.0))


def effective_serve_probability(p_serve: float, importance: float, kappa: float = 0.005) -> float:
    """Apply the documented small-effect importance correction and clip safely."""
    return float(np.clip(_p(p_serve) - float(kappa) * float(importance), 0.0, 1.0))


importance_correction = effective_serve_probability
p_serve_effective = effective_serve_probability
state_win_prob = win_prob


def _records(frame: Any) -> Iterable[Mapping[str, Any]]:
    if hasattr(frame, "to_dict"):
        return frame.to_dict(orient="records")
    return frame


def _number(row: Mapping[str, Any], *names: str) -> Optional[float]:
    lowered = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        try:
            number = float(value)
            if np.isfinite(number):
                return number
        except (TypeError, ValueError):
            pass
    return None


def calibrate_from_history(matches_df: Any = None) -> Dict[str, Any]:
    """Fit serve-point priors from a frame or a local Sackmann CSV.

    With no argument, the function searches ``data/tennis/*.csv`` and its
    subdirectories. Missing local history is a normal, explicit skip.
    """
    note = "Sackmann data are research-use licensed; verify terms before redistribution."
    if matches_df is None:
        paths = sorted(Path("data/tennis").rglob("*.csv")) if Path("data/tennis").exists() else []
        if not paths:
            return {"status": "skipped", "p_serve_prior": None, "n_service_points": 0,
                    "note": "No local Sackmann CSV under data/tennis; calibration skipped. " + note}
        with paths[0].open(newline="", encoding="utf-8-sig") as handle:
            matches_df = list(csv.DictReader(handle))
    won = attempts = 0.0
    for row in _records(matches_df):
        for prefix in ("w", "l"):
            numerator = _number(row, prefix + "_1stWon")
            second = _number(row, prefix + "_2ndWon")
            service_points = _number(row, prefix + "_svpt", prefix + "_SvPt")
            if numerator is None or second is None or service_points is None or service_points <= 0:
                continue
            won += numerator + second
            attempts += service_points
    if attempts == 0:
        return {"status": "skipped", "p_serve_prior": None, "n_service_points": 0,
                "note": "No usable serve-point columns found; calibration skipped. " + note}
    prior = won / attempts
    return {"status": "ok", "p_serve_prior": prior, "p_serve_A_prior": prior,
            "p_serve_B_prior": prior, "n_service_points": int(attempts), "note": note}
