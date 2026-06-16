"""market_coverage.markets -- EVERY-MARKET pricer off ONE joint sample matrix.

THESIS (the honest edge lane): liquid mainlines are razor-efficient -- the sim MATCHES them.
EXTREME / OBSCURE / PROP / DEEP-COMBO (SGP) / IN-GAME MICRO markets are thinly policed -> that
thin tail is where being the smartest *can* pay. This module PRICES any imaginable bet as a
function of the SAME (n_sims, K) correlated samples, so all markets are internally consistent
and every parlay preserves the joint correlation that pricing-legs-as-independent destroys.

REUSE READ-ONLY: the joint-counting pattern from src/sim/sgp_from_sim.py and
sim_framework.JointDistribution. The sim PRICES every number; the LLM authors NONE. No src/ edits.

HONEST RAILS: a price is a price, not an edge. edge = sim_prob vs a book's devigged prob, which
needs CAPTURED prices (mostly absent offline for obscure markets) + forward CLV. Whether a price
BEATS the (often soft/thin) close is a GATE question (edge_finder.py), not a counting one. No $.

Stdlib + numpy. <=300 LOC. Per-file test: test_markets.py (colocated).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Sequence

import numpy as np

Predicate = Callable[[np.ndarray], np.ndarray]


# ---------------------------------------------------------------------------
# Sample container: a coherent (n_sims, K) matrix + a name->column index map.
# This is the universal substrate -- player props use per-(pid,stat) columns,
# team/game markets use team-score columns, all from ONE simulated matrix.
# ---------------------------------------------------------------------------
@dataclass
class SampleBook:
    """Wraps a coherent joint sample matrix with named columns.

    samples : (n_sims, K) float array -- one row = one internally-consistent simulated game.
    cols    : name -> column index (e.g. "home_score", "lebron|pts", "curry|fg3m").
    joint_quality : 'simulated'|'copula' allow joint reads; 'independent' REFUSES them
                    (pricing correlated legs independently mis-prices them -- the kernel boundary).
    """

    samples: np.ndarray
    cols: Dict[str, int]
    joint_quality: str = "simulated"

    def __post_init__(self) -> None:
        s = np.asarray(self.samples, dtype=float)
        if s.ndim != 2:
            raise ValueError(f"samples must be 2-D (n_sims, K); got {s.shape}")
        if self.joint_quality not in ("simulated", "copula", "independent"):
            raise ValueError(f"bad joint_quality {self.joint_quality!r}")
        self.samples = s
        self.n_sims, self.K = s.shape

    def col(self, name: str) -> np.ndarray:
        if name not in self.cols:
            raise KeyError(f"no column {name!r} (have {sorted(self.cols)[:6]}...)")
        return self.samples[:, self.cols[name]]

    # -- universal read-off -------------------------------------------------
    def prob(self, predicate: Predicate) -> float:
        """P(predicate) -- mean of a boolean mask over the coherent sims."""
        return float(np.asarray(predicate(self.samples), dtype=float).mean())


# ---------------------------------------------------------------------------
# Leg / Market: a named predicate. joint legs preserve correlation by counting
# over the SAME rows (never the independence product).
# ---------------------------------------------------------------------------
@dataclass
class Leg:
    name: str
    predicate: Predicate

    def hit(self, book: SampleBook) -> np.ndarray:
        return np.asarray(self.predicate(book.samples), dtype=bool)


@dataclass
class Market:
    """One priced market: a name, its joint legs, and the calibration tier honesty tag."""

    name: str
    legs: List[Leg]
    kind: str = "single"          # single|combo|sgp|team|quarter|scenario|longshot|ingame
    tier: str = "TRUSTWORTHY"     # honesty tag (see _tier)
    meta: Dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Taxonomy: the 7 enumerated market families. Every Market.kind maps into one.
# ---------------------------------------------------------------------------
# The 7 enumerated families. (core=single-stat tiers; combos=same-player cross-stat;
# team-quarter-half=team/period totals+winners; scenario-longshot=blowout/OT/any-N+/+10000;
# sgp=multi-leg joint LIFT; mlb-soccer-tennis=generic over/under; ingame-micro=live derivatives.)
FAMILIES = (
    "player-props-core", "player-props-combos", "team-quarter-half",
    "game-scenario-longshot", "sgp-correlation", "mlb-soccer-tennis", "ingame-micro",
)
_KIND_FAMILY = {
    "single": "player-props-core", "combo": "player-props-combos",
    "team": "team-quarter-half", "quarter": "team-quarter-half",
    "scenario": "game-scenario-longshot", "longshot": "game-scenario-longshot",
    "sgp": "sgp-correlation", "generic": "mlb-soccer-tennis", "ingame": "ingame-micro",
}


def family_of(market: "Market") -> str:
    """Map a Market.kind to one of the 7 enumerated FAMILIES."""
    return _KIND_FAMILY.get(market.kind, "player-props-core")


# ---------------------------------------------------------------------------
# Leg-builder factories -- every imaginable bet shape as a predicate.
# ---------------------------------------------------------------------------
def stat_over(book: SampleBook, name: str, line: float) -> Predicate:
    i = book.cols[name]
    return lambda s, i=i, line=line: s[:, i] > line

def stat_under(book: SampleBook, name: str, line: float) -> Predicate:
    i = book.cols[name]
    return lambda s, i=i, line=line: s[:, i] < line

def sum_over(book: SampleBook, names: Sequence[str], line: float) -> Predicate:
    idx = [book.cols[n] for n in names]
    return lambda s, idx=idx, line=line: s[:, idx].sum(axis=1) > line

def side_win(book: SampleBook, a: str, b: str) -> Predicate:
    ia, ib = book.cols[a], book.cols[b]
    return lambda s, ia=ia, ib=ib: s[:, ia] > s[:, ib]

def spread_cover(book: SampleBook, a: str, b: str, line: float) -> Predicate:
    ia, ib = book.cols[a], book.cols[b]
    return lambda s, ia=ia, ib=ib, line=line: s[:, ia] - s[:, ib] + line > 0

def at_least_k_of(book: SampleBook, names: Sequence[str], thresh: float, k: int) -> Predicate:
    """At least k of the named stats reach `thresh` (double/triple-double, 5x5)."""
    idx = [book.cols[n] for n in names]
    return lambda s, idx=idx, t=thresh, k=k: (s[:, idx] >= t).sum(axis=1) >= k


# Pricing: single + joint (SGP). joint = fraction of sims where ALL legs hit (correlation
# preserved); independent = product of marginals (the book's naive leg-by-leg price);
# lift = joint/independent surfaces where independence is wrong.
def price_single(book: SampleBook, leg: Leg) -> Dict:
    p = float(leg.hit(book).mean())
    return {"name": leg.name, "prob": p, "fair_decimal": _fair_dec(p), "tier": _tier(leg.name, p)}


def price_joint(book: SampleBook, legs: Sequence[Leg]) -> Dict:
    """Coherent multi-leg (SGP) price. REFUSES an 'independent' book -- pricing correlated
    legs as independent systematically mis-prices them (the kernel boundary)."""
    if not legs:
        raise ValueError("legs must be non-empty")
    if book.joint_quality not in ("simulated", "copula"):
        raise ValueError(
            f"price_joint refused: joint_quality={book.joint_quality!r}; independent samples "
            "mis-price correlated legs (see sgp_from_sim.py)."
        )
    hits = np.ones(book.n_sims, dtype=bool)
    indep = 1.0
    for lg in legs:
        h = lg.hit(book)
        hits &= h
        indep *= float(h.mean())
    joint = float(hits.mean())
    lift = joint / indep if indep > 1e-9 else float("nan")
    sign = "positive" if lift > 1.02 else ("negative" if lift < 0.98 else "~independent")
    return {
        "names": [lg.name for lg in legs],
        "joint": joint, "independent": indep, "lift": lift, "correlation_sign": sign,
        "fair_decimal_joint": _fair_dec(joint), "fair_decimal_independent": _fair_dec(indep),
        "tier": "JOINT_PENDING",
        "note": "lift=correlation structure; not a market-beating claim; SGP price capture blocked",
    }


def _fair_dec(p: float) -> float:
    return (1.0 / p) if p > 1e-9 else float("inf")


def _tier(market: str, p: float) -> str:
    """Honesty tag mirroring market_intelligence._tier (READ-ONLY pattern, reimplemented
    minimally here so we never import the human-gated module)."""
    m = market.lower()
    if "over" in m and ("team_total" in m or "game_total" in m):
        return "TOTAL_BIASED"
    if "triple_double" in m or "5x5" in m or "50+" in m or p < 0.06:
        return "LONGSHOT"
    if p < 0.13:
        return "TAIL_APPROX"
    return "TRUSTWORTHY"


# Column conventions for build_menu (the sim/adapter fills a SampleBook): player stats
# f"{pid}|{stat}" (e.g. "203999|pts"); team "home_score"/"away_score"; periods (opt)
# "home_q1".."home_q4"/"home_h1"/"home_h2" (+away_*); generic (other sports) bare names.
# build_menu enumerates EVERY market across the 7 FAMILIES off ONE book (pure count, no edge).
_CORE = {"pts": (10, 15, 20, 25, 30, 35, 40, 50), "reb": (6, 8, 10, 12, 15), "ast": (5, 8, 10, 12), "fg3m": (2, 3, 4, 5, 6)}
_DD = ("pts", "reb", "ast", "stl", "blk")


def _pids(book: SampleBook) -> List[str]:
    seen = []
    for c in book.cols:
        if "|" in c and c.split("|", 1)[0] not in seen:
            seen.append(c.split("|", 1)[0])
    return seen

def _has(book: SampleBook, name: str) -> bool:
    return name in book.cols

def _market(book, name, leg, kind):
    return Market(name, [leg], kind=kind, tier=_tier(name, float(leg.hit(book).mean())))


def build_menu(book: SampleBook, *, live: bool = False) -> List[Market]:
    """Enumerate EVERY priceable market off one coherent SampleBook (all 7 families).

    Each Market is a named predicate list; price it with price_single / price_joint.
    `live=True` relabels every kind to 'ingame' (rest-of-game samples -> ingame-micro).
    """
    out: List[Market] = []
    for pid in _pids(book):
        # 1. player-props-core (single-stat tiers + PRA)
        for stat, tiers in _CORE.items():
            col = f"{pid}|{stat}"
            if not _has(book, col):
                continue
            for t in tiers:
                out.append(_market(book, f"{pid}|{stat}_{t}+", Leg(col, stat_over(book, col, t - 0.5)), "single"))
        pra_cols = [f"{pid}|{s}" for s in ("pts", "reb", "ast") if _has(book, f"{pid}|{s}")]
        if len(pra_cols) == 3:
            for t in (25, 30, 35, 40, 45):
                out.append(_market(book, f"{pid}|PRA_{t}+", Leg(f"{pid}|PRA", sum_over(book, pra_cols, t - 0.5)), "single"))
        # 2. player-props-combos (same-player cross-stat -> JOINT_PENDING)
        if len(pra_cols) == 3:
            p, r, a = (f"{pid}|pts", f"{pid}|reb", f"{pid}|ast")
            ip, ir, ia = book.cols[p], book.cols[r], book.cols[a]
            out.append(Market(f"{pid}|25pts&10reb", [Leg("c", lambda s, ip=ip, ir=ir: (s[:, ip] >= 25) & (s[:, ir] >= 10))], "combo", "JOINT_PENDING"))
            out.append(Market(f"{pid}|20/10/5", [Leg("c", lambda s, ip=ip, ir=ir, ia=ia: (s[:, ip] >= 20) & (s[:, ir] >= 10) & (s[:, ia] >= 5))], "combo", "JOINT_PENDING"))
        dd_cols = [f"{pid}|{s}" for s in _DD if _has(book, f"{pid}|{s}")]
        if len(dd_cols) >= 3:
            out.append(Market(f"{pid}|double_double", [Leg("dd", at_least_k_of(book, dd_cols, 10, 2))], "combo", "JOINT_PENDING"))
            out.append(Market(f"{pid}|triple_double", [Leg("td", at_least_k_of(book, dd_cols, 10, 3))], "combo", "LONGSHOT"))
        if len(dd_cols) == 5:
            out.append(Market(f"{pid}|5x5", [Leg("5x5", at_least_k_of(book, dd_cols, 5, 5))], "combo", "LONGSHOT"))
    # 3. team-quarter-half + 4. game-scenario-longshot
    if _has(book, "home_score") and _has(book, "away_score"):
        out += _team_and_scenarios(book)
    # 6. mlb-soccer-tennis: any bare generic column gets a median over/under
    for c in book.cols:
        if "|" not in c and c not in _TEAM_COLS:
            ln = float(np.median(book.col(c)))
            out.append(_market(book, f"{c}_o{ln:.2f}", Leg(c, stat_over(book, c, ln)), "generic"))
    if live:  # 7. ingame-micro: same numbers, relabel family
        out = [Market(m.name, m.legs, "ingame", m.tier, m.meta) for m in out]
    return out


_TEAM_COLS = {"home_score", "away_score"} | {f"{s}_{q}" for s in ("home", "away")
              for q in ("q1", "q2", "q3", "q4", "h1", "h2")}


def _team_and_scenarios(book: SampleBook) -> List[Market]:
    h, a = book.col("home_score"), book.col("away_score")
    ih, ia = book.cols["home_score"], book.cols["away_score"]
    out: List[Market] = []
    for who, col in (("home", "home_score"), ("away", "away_score")):
        ln = float(np.median(book.col(col)))
        out.append(Market(f"{who}_team_total_over_{ln:.1f}", [Leg("tt", stat_over(book, col, ln))], "team", "TOTAL_BIASED", {"line": ln}))
    gln = float(np.median(h + a))
    out.append(Market(f"game_total_over_{gln:.1f}", [Leg("gt", lambda s, ih=ih, ia=ia, ln=gln: s[:, ih] + s[:, ia] > ln)], "team", "TOTAL_BIASED", {"line": gln}))
    sp = float(np.median(h - a))
    out.append(Market("home_spread", [Leg("sp", spread_cover(book, "home_score", "away_score", -sp))], "team", _tier("home_spread", 0.5), {"line": sp}))
    out.append(Market("home_ml", [Leg("ml", side_win(book, "home_score", "away_score"))], "team", _tier("home_ml", float((h > a).mean()))))
    # period (quarter / half) totals + winners when present
    for q in ("q1", "q2", "q3", "q4", "h1", "h2"):
        hc, ac = f"home_{q}", f"away_{q}"
        if not (_has(book, hc) and _has(book, ac)):
            continue
        ph, pa = book.cols[hc], book.cols[ac]
        ln = float(np.median(book.col(hc) + book.col(ac)))
        out.append(Market(f"{q}_total_over_{ln:.1f}", [Leg("qt", lambda s, ph=ph, pa=pa, ln=ln: s[:, ph] + s[:, pa] > ln)], "quarter", "TOTAL_BIASED", {"line": ln}))
        out.append(Market(f"home_wins_{q}", [Leg("qw", lambda s, ph=ph, pa=pa: s[:, ph] > s[:, pa])], "quarter", _tier(q, 0.5)))
    # scenarios + any-explosion longshots (read off the SAME rows -> correlation exact)
    im, it = book.cols["home_score"], book.cols["away_score"]
    scen = [("blowout_15+", lambda s: np.abs(s[:, im] - s[:, it]) >= 15),
            ("blowout_20+", lambda s: np.abs(s[:, im] - s[:, it]) >= 20),
            ("nailbiter_within3", lambda s: np.abs(s[:, im] - s[:, it]) <= 3),
            ("OT_within2", lambda s: np.abs(s[:, im] - s[:, it]) <= 2),
            ("shootout_230+", lambda s: s[:, im] + s[:, it] >= 230),
            ("rockfight_under205", lambda s: s[:, im] + s[:, it] < 205)]
    out += [Market(nm, [Leg(nm, pr)], "scenario", _tier(nm, float(np.asarray(pr(book.samples)).mean()))) for nm, pr in scen]
    pcols = [book.cols[c] for c in book.cols if c.endswith("|pts")]
    for tag, thr in (("any_35+_scorer", 35), ("any_40+_scorer", 40), ("any_50+_scorer", 50)) if pcols else ():
        out.append(Market(tag, [Leg(tag, lambda s, idx=pcols, thr=thr: (s[:, idx] >= thr).any(axis=1))],
                          "longshot" if thr >= 40 else "scenario", _tier(tag if thr < 50 else tag + " 50+", 0.05)))
    return out
