"""market_coverage.book_builder -- enumerate+price the WHOLE book from one SampleBook.

The pure enumeration+pricing layer (consumed by coverage.py, which runs the real sim
and attaches the thinness/validatable honesty tags). Enumerates EVERY imaginable bet
across the categories the prompt names:
  player-props-core   : every-stat over/under tiers (pts/reb/ast/fg3m/stl/blk) at alt lines
  player-props-combos : same-player cross-stat combos (PR, PRA, etc.) + DD/TD/5x5
  team-quarter-half   : team totals, quarter/half sides + totals (when columns present)
  game-scenario-longshot : blowout / shootout / OT / +10000 burst scenarios
  sgp-correlation     : correlated multi-leg parlays (joint vs independent lift)
  ingame-micro        : rest-of-game / next-bucket micro markets (when an in-game book is passed)

All markets read off the SAME (n_sims, K) matrix -> internally consistent by construction. The
sim PRICES every market; the LLM authors no number. PRICING != EDGE (edge_finder.py gates that).

Stdlib + numpy. <=300 LOC. Per-file test: tests/test_book_builder.py.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np

from scripts.platformkit.market_coverage.markets import (
    Leg, Market, SampleBook, at_least_k_of, price_joint, price_single, side_win,
    spread_cover, stat_over, stat_under, sum_over,
)

CORE_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk")
DD_STATS = ("pts", "reb", "ast", "stl", "blk")


def _players(book: SampleBook) -> List[str]:
    """Distinct player ids present as 'pid|stat' columns."""
    seen: List[str] = []
    for c in book.cols:
        if "|" in c:
            pid = c.split("|", 1)[0]
            if pid not in seen:
                seen.append(pid)
    return seen


def _alt_lines(book: SampleBook, col: str, n: int = 3) -> List[float]:
    """Alt lines bracketing the median: median +/- integer steps (the prop ladder)."""
    x = book.col(col)
    med = float(np.median(x))
    sd = max(1.0, float(np.std(x)))
    step = max(1.0, round(sd / 2.0))
    base = round(med - 0.5) + 0.5
    return [base + step * k for k in range(-(n // 2), n - n // 2)]


def build_player_props_core(book: SampleBook) -> List[Market]:
    out: List[Market] = []
    for pid in _players(book):
        for stat in CORE_STATS:
            col = f"{pid}|{stat}"
            if col not in book.cols:
                continue
            for line in _alt_lines(book, col):
                for over_ in (True, False):
                    name = f"{pid} {stat} {'O' if over_ else 'U'}{line:g}"
                    pred = (stat_over if over_ else stat_under)(book, col, line)
                    out.append(Market(name, [Leg(name, pred)], kind="single"))
    return out


def build_player_props_combos(book: SampleBook) -> List[Market]:
    """Same-player cross-stat sums (PR/PA/RA/PRA) + double/triple-double + 5x5."""
    out: List[Market] = []
    for pid in _players(book):
        have = [st for st in DD_STATS if f"{pid}|{st}" in book.cols]
        # PRA-style sums
        for combo in (("pts", "reb"), ("pts", "ast"), ("reb", "ast"), ("pts", "reb", "ast")):
            cols = [f"{pid}|{st}" for st in combo]
            if not all(c in book.cols for c in cols):
                continue
            line = round(float(np.median(book.col(cols[0]) * 0 + sum(book.col(c) for c in cols)))) + 0.5
            nm = f"{pid} {'+'.join(combo)} O{line:g}"
            out.append(Market(nm, [Leg(nm, sum_over(book, cols, line))], kind="combo"))
        # double-double / triple-double / 5x5
        names = [f"{pid}|{st}" for st in have]
        if len(have) >= 2:
            nm = f"{pid} double_double"
            out.append(Market(nm, [Leg(nm, at_least_k_of(book, names, 10, 2))], kind="combo"))
        if len(have) >= 3:
            nm = f"{pid} triple_double"
            out.append(Market(nm, [Leg(nm, at_least_k_of(book, names, 10, 3))], kind="longshot"))
        if len(have) == 5:
            nm = f"{pid} 5x5"
            out.append(Market(nm, [Leg(nm, at_least_k_of(book, names, 5, 5))], kind="longshot"))
    return out


def build_team_quarter_half(book: SampleBook) -> List[Market]:
    """Mainline side/spread/total + team totals + any quarter/half score columns present."""
    out: List[Market] = []
    if "home_score" in book.cols and "away_score" in book.cols:
        out.append(_mkt("home_ml", side_win(book, "home_score", "away_score"), "team"))
        for ln in (-6.5, -3.5, -1.5, 1.5, 3.5, 6.5):
            out.append(_mkt(f"home_spread {ln:+g}", spread_cover(book, "home_score", "away_score", ln), "team"))
        tot = float(np.median(book.col("home_score") + book.col("away_score")))
        for ln in (tot - 6, tot - 2, tot + 2, tot + 6):
            ln = round(ln) + 0.5
            out.append(_mkt(f"game_total O{ln:g}", sum_over(book, ["home_score", "away_score"], ln), "team"))
        for side in ("home", "away"):
            t = float(np.median(book.col(f"{side}_score")))
            for ln in (t - 4, t + 4):
                ln = round(ln) + 0.5
                out.append(_mkt(f"{side}_team_total O{ln:g}", stat_over(book, f"{side}_score", ln), "team"))
    # quarter / half columns: any 'home_q1' style segment cols
    for seg in ("q1", "q2", "q3", "q4", "h1", "h2"):
        hk, ak = f"home_{seg}", f"away_{seg}"
        if hk in book.cols and ak in book.cols:
            out.append(_mkt(f"{seg}_home_ml", side_win(book, hk, ak), "quarter"))
            t = float(np.median(book.col(hk) + book.col(ak)))
            ln = round(t) + 0.5
            out.append(_mkt(f"{seg}_total O{ln:g}", sum_over(book, [hk, ak], ln), "quarter"))
    return out


def build_game_scenario_longshot(book: SampleBook) -> List[Market]:
    """Blowout / shootout / rockfight / OT / star-burst longshots."""
    out: List[Market] = []
    if "home_score" in book.cols and "away_score" in book.cols:
        h, a = book.col("home_score"), book.col("away_score")
        out.append(_mkt("blowout_20+", lambda s, ih=book.cols["home_score"], ia=book.cols["away_score"]:
                        np.abs(s[:, ih] - s[:, ia]) >= 20, "scenario"))
        tot_hi = float(np.quantile(h + a, 0.85))
        out.append(_mkt(f"shootout_{round(tot_hi)}+", sum_over(book, ["home_score", "away_score"], round(tot_hi)), "scenario"))
        tot_lo = float(np.quantile(h + a, 0.15))
        ilo = round(tot_lo)
        out.append(_mkt(f"rockfight_under_{ilo}", lambda s, ih=book.cols["home_score"], ia=book.cols["away_score"], L=ilo:
                        s[:, ih] + s[:, ia] < L, "scenario"))
        out.append(_mkt("overtime", lambda s, ih=book.cols["home_score"], ia=book.cols["away_score"]:
                        np.abs(s[:, ih] - s[:, ia]) <= 0, "scenario"))
    # +10000 star burst: any player hits a far-tail pts line
    for pid in _players(book):
        col = f"{pid}|pts"
        if col in book.cols:
            burst = float(np.quantile(book.col(col), 0.995)) + 5
            nm = f"{pid} 50+_burst" if burst >= 50 else f"{pid} {round(burst)}+_pts_longshot"
            out.append(Market(nm, [Leg(nm, stat_over(book, col, burst))], kind="longshot"))
    return out


def build_sgp_correlation(book: SampleBook, max_parlays: int = 30, seed: int = 0) -> List[Market]:
    """Correlated multi-leg parlays: same-player (+corr), teammates (-corr), cross-team."""
    out: List[Market] = []
    rng = np.random.default_rng(seed)
    players = _players(book)
    if len(players) < 2:
        return out
    for _ in range(max_parlays):
        k = int(rng.integers(2, 4))
        legs: List[Leg] = []
        for _ in range(k):
            pid = players[int(rng.integers(0, len(players)))]
            stat = CORE_STATS[int(rng.integers(0, 3))]  # pts/reb/ast
            col = f"{pid}|{stat}"
            if col not in book.cols:
                continue
            line = float(np.median(book.col(col)))
            legs.append(Leg(f"{pid} {stat} O{line:g}", stat_over(book, col, line)))
        if len(legs) >= 2:
            out.append(Market(" + ".join(l.name for l in legs), legs, kind="sgp"))
    return out


def build_ingame_micro(book: SampleBook) -> List[Market]:
    """Rest-of-game micro markets -- only meaningful when `book` is an in-game (RoG) SampleBook.
    Same shapes as core/team but flagged ingame so the gate scopes them to the live regime."""
    mk = build_team_quarter_half(book) + build_player_props_core(book)
    for m in mk:
        m.kind = "ingame"
    return mk


CATEGORIES = {
    "player-props-core": build_player_props_core,
    "player-props-combos": build_player_props_combos,
    "team-quarter-half": build_team_quarter_half,
    "game-scenario-longshot": build_game_scenario_longshot,
    "sgp-correlation": build_sgp_correlation,
    "ingame-micro": build_ingame_micro,
}


def build_full_book(book: SampleBook, categories: Optional[Sequence[str]] = None) -> Dict[str, dict]:
    """Build + PRICE the whole book. Returns name -> priced dict (single or joint)."""
    cats = list(categories) if categories else [c for c in CATEGORIES if c != "ingame-micro"]
    priced: Dict[str, dict] = {}
    for cat in cats:
        for m in CATEGORIES[cat](book):
            if m.kind in ("sgp",) and len(m.legs) >= 2:
                rec = price_joint(book, m.legs)
                rec["category"] = cat
                priced[m.name] = rec
            else:
                rec = price_single(book, m.legs[0])
                rec["category"] = cat
                rec["kind"] = m.kind
                priced[m.name] = rec
    return priced


def _mkt(name: str, pred, kind: str) -> Market:
    return Market(name, [Leg(name, pred)], kind=kind)
