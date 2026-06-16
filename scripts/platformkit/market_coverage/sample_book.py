"""market_coverage.sample_book -- build a coherent SampleBook from the NBA joint sim.

CONSUMES the possession Monte-Carlo OUTPUT read-only (src.sim.fast_sim /
basketball_sim -- human-gated, never edited). One simulate_game_fast() call yields
thousands of internally-consistent games; we flatten its per-player sample dict into
ONE (n_sims, K) matrix with named columns so markets.SampleBook can price ANY market
off the SAME correlated rows (the joint structure parlays must preserve).

Column naming convention (stable, market builders rely on it):
    "home_score", "away_score"                  team totals (per sim)
    "<pid>|<stat>"                              per-player stat column
plus a friendly index: name_to_pid maps a lowercase player name -> pid so the
enumerators can find "the home star" etc.

A quarter/half synthesizer lives here too: the sim is full-game, so quarter/half
markets are derived by splitting full-game totals on the empirical per-quarter share
with sim-preserved game-to-game variance -- an APPROXIMATION, tagged TAIL_APPROX /
THIN downstream (no real per-quarter sim offline). Honest, not fabricated.

Stdlib + numpy. <=300 LOC. Per-file test: tests/test_market_coverage_sample_book.py.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from scripts.platformkit.market_coverage.markets import SampleBook

# Per-player stats we expose as columns (superset used by the enumerators).
_PLAYER_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "fgm", "fga", "ftm")

# Empirical NBA per-quarter scoring shares (regulation), Q1..Q4. Q4 a touch lower
# (garbage time / slowed pace). Used ONLY to synthesize quarter/half markets.
_QSHARE = (0.252, 0.250, 0.252, 0.246)
_HALF_SHARE = (_QSHARE[0] + _QSHARE[1], _QSHARE[2] + _QSHARE[3])


def _sim_root() -> None:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    src = os.path.join(root, "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def run_nba_sim(home: str, away: str, n_sims: int = 8000, seed: int = 2026,
                state: Optional[Dict[str, Any]] = None) -> Any:
    """Run the joint sim READ-ONLY (pregame, or rest-of-game if `state` given).

    Mirrors scripts/team_system/market_intelligence.rest_of_game for the in-game
    path so we consume the same coherent output. Returns the sim result object.
    """
    _sim_root()
    from sim.basketball_sim import TeamModel        # noqa: E402
    from sim.fast_sim import simulate_game_fast      # noqa: E402

    h = TeamModel.from_cache(home)
    a = TeamModel.from_cache(away)
    res = simulate_game_fast(h, a, n_sims=n_sims, seed=seed, anchor=True, defense=True)
    if state:
        frac = max(0.0, min(1.0, float(state.get("minutes_remaining", 48)) / 48.0))
        cur = state.get("players", {})
        for _pid, d in res.players.items():
            c = cur.get(d["name"], {})
            for stat, arr in d["samples"].items():
                d["samples"][stat] = c.get(stat, 0.0) + np.asarray(arr) * frac
        hs0, as0 = state.get("home_score", 0), state.get("away_score", 0)
        res.home_total = hs0 + np.asarray(res.home_total) * frac
        res.away_total = as0 + np.asarray(res.away_total) * frac
    return res


def book_from_sim(res: Any) -> Tuple[SampleBook, Dict[str, int], Dict[str, List[int]]]:
    """Flatten a sim result into a coherent SampleBook.

    Returns (book, name_to_pid, team_pids) where:
      name_to_pid : lowercase player name -> pid (int)
      team_pids   : "home"/"away" -> [pid,...]  (team membership for parlays)
    """
    home_tri = getattr(res, "home", None) or getattr(res, "home_tri", None)
    away_tri = getattr(res, "away", None) or getattr(res, "away_tri", None)
    players = res.players
    n_sims = int(np.asarray(res.home_total).shape[0])

    cols: Dict[str, int] = {}
    columns: List[np.ndarray] = []

    def _add(name: str, arr: np.ndarray) -> None:
        cols[name] = len(columns)
        columns.append(np.asarray(arr, dtype=float))

    _add("home_score", np.asarray(res.home_total, dtype=float))
    _add("away_score", np.asarray(res.away_total, dtype=float))

    name_to_pid: Dict[str, int] = {}
    team_pids: Dict[str, List[int]] = {"home": [], "away": []}
    for pid, d in players.items():
        nm = str(d["name"]).strip()
        name_to_pid[nm.lower()] = int(pid)
        tri = d.get("team")
        if tri == home_tri:
            team_pids["home"].append(int(pid))
        elif tri == away_tri:
            team_pids["away"].append(int(pid))
        s = d["samples"]
        for stat in _PLAYER_STATS:
            if stat in s:
                _add(f"{pid}|{stat}", np.asarray(s[stat], dtype=float))

    mat = np.column_stack(columns) if columns else np.zeros((n_sims, 0))
    book = SampleBook(samples=mat, cols=cols, joint_quality="simulated")
    return book, name_to_pid, team_pids


def add_period_columns(book: SampleBook) -> SampleBook:
    """Synthesize per-quarter and per-half TEAM-score columns by splitting the
    coherent full-game team scores on the empirical share with preserved relative
    variance. APPROXIMATION (no per-quarter sim offline) -- markets off these are
    tagged THIN/TAIL_APPROX. Returns a NEW SampleBook (original unchanged)."""
    extra: Dict[str, np.ndarray] = {}
    rng = np.random.default_rng(7)
    for side in ("home", "away"):
        full = book.col(f"{side}_score")
        # multiplicative jitter so quarter totals are not a deterministic fraction
        for qi, share in enumerate(_QSHARE, start=1):
            jit = 1.0 + rng.normal(0.0, 0.10, size=full.shape[0])
            extra[f"{side}_q{qi}"] = np.clip(full * share * jit, 0.0, None)
        for hi, share in enumerate(_HALF_SHARE, start=1):
            jit = 1.0 + rng.normal(0.0, 0.07, size=full.shape[0])
            extra[f"{side}_h{hi}"] = np.clip(full * share * jit, 0.0, None)
    cols = dict(book.cols)
    columns = [book.samples[:, i] for i in range(book.K)]
    for name, arr in extra.items():
        cols[name] = len(columns)
        columns.append(arr)
    return SampleBook(samples=np.column_stack(columns), cols=cols,
                      joint_quality=book.joint_quality)


def median_line(book: SampleBook, col_name: str) -> float:
    """The sim's own median for a column -> a ~50/50 reference line for prop O/U."""
    return float(np.median(book.col(col_name)))
