"""pregame_ev_engine.py — OddsJam-style multi-book EV+ scanner.

Reads every ``data/lines/<date>_<book>.csv`` for today, devigs the
Pinnacle two-way market to get a "fair" hit probability per
(player, stat, line), then for every OTHER book that offers the
same prop computes ``EV per $1 stake = p_fair * payout - (1 - p_fair)``.

Produces a ranked list of ``bet.recommended``-shaped dicts plus,
per (player, stat, side), the full per-book price grid for the
web dashboard's "all books for this prop" panel.

This is the LINE-SHOPPING bet ranker — no projection model
involved. It's the cleanest pregame edge because Pinnacle's
no-vig price is the de-facto market truth for NBA props.

Two outputs:
  * ``rank_pregame_bets(...)``        → list of bet dicts (top-N by EV)
  * ``book_grid_for(...)``            → list of {book, line, over_price,
                                                  under_price} for the
                                                  why-drawer compare table
"""
from __future__ import annotations

import csv
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.live.time_utils import slate_date

log = logging.getLogger("pregame_ev_engine")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")

# Books we consider trustworthy enough to surface bets from.
# Pinnacle is sharp → used as ground truth for "fair" probability.
# Bovada / FanDuel / PrizePicks / DraftKings → soft books → we look
# for EV+ against the Pinnacle no-vig line.
_SHARP_BOOK = "pin"
_SOFT_BOOKS = ("fd", "bov", "pp", "dk", "mgm", "caesars")

# Three-book consensus requirement. The user only trusts a bet when all three
# of Pinnacle (sharp anchor), Bovada, and FanDuel quote the same (player, stat,
# line) tuple. If only one soft book has the line, treat it as untrusted —
# either a stale quote or a soft-book typo, not a real edge.
_REQUIRED_BOOKS = ("pin", "bov", "fd")

_SUPPORTED_STATS = {"pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "pra",
                    "fg3a", "fga", "fta"}

_EV_FLOOR_DEFAULT = 0.01     # 1% EV minimum to surface


# ── tiny math helpers ──────────────────────────────────────────────────
def american_to_prob(odds: int) -> float:
    """Convert American odds to implied probability (includes vig)."""
    o = float(odds)
    return (100.0 / (o + 100.0)) if o > 0 else (-o / (-o + 100.0))


def american_payout(odds: int) -> float:
    """Profit on a $1 stake."""
    o = int(odds)
    return o / 100.0 if o > 0 else 100.0 / abs(o)


def devig_two_way(over_odds: int, under_odds: int) -> Tuple[float, float]:
    """Strip the vig from a two-way market. Returns (p_over, p_under) summing to 1.0."""
    po = american_to_prob(over_odds)
    pu = american_to_prob(under_odds)
    total = po + pu
    if total <= 0:
        return 0.5, 0.5
    return po / total, pu / total


# ── data types ────────────────────────────────────────────────────────
@dataclass
class _BookOffer:
    book: str
    stat: str
    line: float
    over_price: Optional[int]
    under_price: Optional[int]
    captured_at: str = ""
    game_id: str = ""
    player_id: str = ""
    player_name: str = ""
    team: str = ""


@dataclass
class _PropKey:
    player_name_lower: str
    stat: str
    line: float

    def as_tuple(self) -> Tuple[str, str, float]:
        return self.player_name_lower, self.stat, self.line


# ── core loader ──────────────────────────────────────────────────────
def _safe_int(v: Any) -> Optional[int]:
    if v in (None, ""):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _safe_float(v: Any) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_book_offers(date_str: Optional[str] = None,
                     lines_dir: str = LINES_DIR
                     ) -> List[_BookOffer]:
    """Load every line row across every book CSV for ``date_str``.

    Returns a flat list of _BookOffer. Player_name is preserved as-is
    so callers can dedup by lowercased name.
    """
    date_str = date_str or slate_date().isoformat()
    out: List[_BookOffer] = []
    if not os.path.isdir(lines_dir):
        return out
    for fname in sorted(os.listdir(lines_dir)):
        if not fname.startswith(date_str) or not fname.endswith(".csv"):
            continue
        path = os.path.join(lines_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    stat = (row.get("stat") or "").strip().lower()
                    if not stat or stat not in _SUPPORTED_STATS:
                        continue
                    name = (row.get("player_name") or "").strip()
                    if not name:
                        continue
                    line = _safe_float(row.get("line"))
                    if line is None:
                        continue
                    book = (row.get("book") or fname.split("_")[-1].split(".")[0]).strip().lower()
                    out.append(_BookOffer(
                        book=book,
                        stat=stat,
                        line=line,
                        over_price=_safe_int(row.get("over_price")),
                        under_price=_safe_int(row.get("under_price")),
                        captured_at=row.get("captured_at") or "",
                        game_id=row.get("game_id") or "",
                        player_id=str(row.get("player_id") or ""),
                        player_name=name,
                        team=row.get("team") or "",
                    ))
        except (OSError, ValueError) as exc:
            log.warning("load offers from %s failed: %s", fname, exc)
    return out


# Group offers by (player_lower, stat, line). For each book the LATEST
# offer wins (CSV is append-only, last row = most recent).
def _group_latest_by_prop(offers: List[_BookOffer]) -> Dict[Tuple[str, str, float], Dict[str, _BookOffer]]:
    grouped: Dict[Tuple[str, str, float], Dict[str, _BookOffer]] = {}
    for o in offers:
        key = (o.player_name.lower(), o.stat, o.line)
        per_book = grouped.setdefault(key, {})
        # Overwrite — append-only CSV means later row is newer.
        per_book[o.book] = o
    return grouped


# ── ranking ──────────────────────────────────────────────────────────
def rank_pregame_bets(*,
                      date_str: Optional[str] = None,
                      lines_dir: str = LINES_DIR,
                      ev_floor: float = _EV_FLOOR_DEFAULT,
                      top_n: int = 50
                      ) -> List[Dict[str, Any]]:
    """Build a sorted list of EV+ bets vs Pinnacle no-vig consensus.

    Returns at most ``top_n`` bets, sorted by EV descending.
    """
    offers = load_book_offers(date_str=date_str, lines_dir=lines_dir)
    grouped = _group_latest_by_prop(offers)
    bets: List[Dict[str, Any]] = []
    for key, per_book in grouped.items():
        player_lower, stat, line = key
        # Three-book consensus: require Pinnacle + Bovada + FanDuel all
        # quoting the same (player, stat, line). One-book outliers (only
        # Bovada listed, etc.) get dropped as untrusted.
        if not all(b in per_book for b in _REQUIRED_BOOKS):
            continue
        sharp = per_book.get(_SHARP_BOOK)
        if (sharp is None or sharp.over_price is None
                or sharp.under_price is None):
            continue
        p_over_fair, p_under_fair = devig_two_way(
            sharp.over_price, sharp.under_price)
        for book in _SOFT_BOOKS:
            offer = per_book.get(book)
            if offer is None:
                continue
            for side, p_fair, price in (
                ("over", p_over_fair, offer.over_price),
                ("under", p_under_fair, offer.under_price),
            ):
                if price is None:
                    continue
                payout = american_payout(price)
                ev = p_fair * payout - (1.0 - p_fair)
                if ev < ev_floor:
                    continue
                # EV ceiling: real markets never give +50% EV on a real
                # consensus line. Anything above is a market mismatch — e.g.,
                # FD listing a milestone alt-line ("3+ AST" at +880) that
                # gets compared to Pinnacle's main-line fair probability.
                # Drop it instead of surfacing a phantom edge.
                if ev > 0.50:
                    log.debug("drop phantom pregame edge: %s %s %s line=%s "
                              "@ %s %+d ev=%.0f%%",
                              offer.player_name, stat, side, line,
                              book, int(price), ev * 100)
                    continue
                kelly = max(0.0, min(0.25,
                                     (payout * p_fair - (1.0 - p_fair))
                                     / payout))
                tier = ("S" if ev >= 0.08
                        else "A" if ev >= 0.04 else "B")
                bets.append({
                    "game_id": offer.game_id or sharp.game_id,
                    "player_id": offer.player_id or sharp.player_id,
                    "name": offer.player_name or sharp.player_name,
                    "team": offer.team or sharp.team,
                    "stat": stat,
                    "side": side,
                    "line": line,
                    "book": book,
                    "odds": int(price),
                    "ev": ev,
                    "kelly": kelly,
                    "tier": tier,
                    "projected_final": line,   # placeholder; the real model fills in once tipped
                    "current": 0,
                    "delta": 0.0,
                    "p_fair": p_fair,
                    "fair_odds": _prob_to_american(p_fair),
                    "sharp_book": _SHARP_BOOK,
                    "why": (f"{tier}: {offer.player_name} {stat.upper()} "
                            f"{side.upper()} {line} @ {book} {price:+d} | "
                            f"Pinnacle fair {p_fair*100:.1f}% → "
                            f"EV {ev*100:+.1f}%"),
                    "reason": "pregame_line_shop",
                    "source": "pregame_ev",
                })
    bets.sort(key=lambda b: -b["ev"])
    return bets[:top_n]


def book_grid_for(player_name: str, stat: str, line: float,
                  *, date_str: Optional[str] = None,
                  lines_dir: str = LINES_DIR
                  ) -> List[Dict[str, Any]]:
    """All books' offers for one prop. Highlight the best side prices.

    Used by the why drawer's "compare books" panel.
    """
    offers = load_book_offers(date_str=date_str, lines_dir=lines_dir)
    grouped = _group_latest_by_prop(offers)
    per_book = grouped.get((player_name.lower(), stat.lower(), float(line)))
    rows: List[Dict[str, Any]] = []
    if not per_book:
        return rows
    best_over = max((o.over_price for o in per_book.values()
                     if o.over_price is not None), default=None)
    best_under = max((o.under_price for o in per_book.values()
                      if o.under_price is not None), default=None)
    for book, offer in sorted(per_book.items()):
        rows.append({
            "book": book,
            "line": offer.line,
            "over_price": offer.over_price,
            "under_price": offer.under_price,
            "captured_at": offer.captured_at,
            "is_best_over": (offer.over_price == best_over
                             and offer.over_price is not None),
            "is_best_under": (offer.under_price == best_under
                              and offer.under_price is not None),
        })
    return rows


def _prob_to_american(p: float) -> int:
    """Convert fair probability → American odds (rounded)."""
    if p <= 0.0 or p >= 1.0:
        return 0
    dec = 1.0 / p
    if dec >= 2.0:
        return int(round((dec - 1.0) * 100.0))
    return int(round(-100.0 / (dec - 1.0)))
