"""scripts.platformkit.pm_trading.cross_venue_arb -- PAPER cross-venue price-
discrepancy lane.

THE GAP: existing arb tooling compares books WITHIN one feed type -- arb_panel /
arb_emitter_daemon are cross-BOOK (sportsbook vs sportsbook) player-prop scans.
Nothing compares a GAME-moneyline price quoted on one VENUE (Kalshi exchange)
against the SAME game quoted on a different VENUE (a sportsbook, via the
devigged consensus already captured in line_history) net of each venue's real
fee schedule. This module closes that gap using ONLY already-collected data:
data/cache/line_history/<sport>/<date>.jsonl (freshest row per book/side).

MATCHING: reuses pm_game_placer._name_matches (the Kalshi-city -> full-team-name
bridge already proven against the same landmine) -- no new matcher written.
FEES: reuses econ.cost_model.kalshi_fee_per_contract / polymarket_fee (6.1,
web-verified). Sportsbook/ESPN legs carry vig already embedded in the quoted
price -- no separate fee model needed for those venues (ponytail: the price IS
the cost for a vig-priced book).

DETECTION: for a two-way game market quoted on >=2 venues, buying the cheaper
YES-equivalent side on venue A and the cheaper NO-equivalent (opposite side) on
venue B locks a sure profit iff (1/dec_A_side + 1/dec_B_other_side) < 1, after
subtracting each venue's own round-trip fee (in probability-units, via
cost_model.breakeven_edge_prob). This is classic two-way-book arbitrage; no
new math, only the venue-vs-venue join and the fee subtraction are new.

HONEST RAILS (binding): quotes are the freshest CACHED line_history rows, which
may be stale or non-executable by the time this runs -- rows older than
max_age_sec are skipped (fail-closed). No depth data is collected upstream, so
size is fixed at 1 unit/leg and any depth signal present is honored as a cap.
Every written row carries edge_claimed=False, executed=False, channel="paper",
is_pm/is_arb tagging, and market_type="arb" so it is analyzable separately from
directional paper bets. NEVER a dollar/pnl/roi field. Real money stays denied.

Library only -- CLI/daemon loop lives in run_cross_venue_arb.py (LOC split):
    python -m scripts.platformkit.pm_trading.run_cross_venue_arb --sport mlb
    python -m scripts.platformkit.pm_trading.run_cross_venue_arb --sport mlb --place
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.econ.cost_model import breakeven_edge_prob
from scripts.platformkit.pm_trading.pm_game_placer import _name_matches

_REPO = Path(__file__).resolve().parents[3]
_LINE_HISTORY_DIR = _REPO / "data" / "cache" / "line_history"

DEFAULT_SPORTS = ("mlb", "wnba")  # two-way-market sports only -- soccer's moneyline
# is inherently 3-way (draw exists) and the cached line_history feed does not
# reliably carry a draw row for every book (some books' snapshots silently omit
# it), so the "no draw key present" guard below cannot detect a draw that is
# missing from the SOURCE data -- comparing those books' home/away as if they
# were a clean two-way market would invent fake locked profit. Do not add
# soccer/soccer_intl back to this default without a verified per-book draw row.
DEFAULT_MAX_AGE_SEC = 120.0
DEFAULT_STAKE_UNITS = 1.0
DEFAULT_MIN_LOCKED_PROB = 0.003  # 0.3pp min guaranteed edge after fees -- skip noise

HONEST_NOTE = (
    "Paper cross-venue price-discrepancy lane. Quotes are cached line_history "
    "snapshots, possibly stale/non-executable. UNITS not $. edge_claimed=False, "
    "executed=False, channel=paper. Real-money DENY."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _parse_captured_at(v: Any) -> Optional[datetime]:
    if not v:
        return None
    try:
        s = str(v).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def load_quotes(sport: str, date_key: Optional[str] = None,
                path_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read one sport-day of line_history moneyline rows. [] on any read error."""
    d = path_dir if path_dir is not None else _LINE_HISTORY_DIR
    dk = date_key or _today_key()
    p = d / sport / ("%s.jsonl" % dk)
    if not p.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("market_type") not in (None, "moneyline"):
                    continue
                out.append(row)
    except OSError:
        return []
    return out


def freshest_by_book(quotes: Sequence[Dict[str, Any]]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    """Reduce raw rows -> {(home,away,book): freshest row} keeping only rows with
    a usable side + decimal odds. One row per (matchup,book); side chosen is
    whichever side that book's freshest snapshot happens to carry (paired up in
    find_arbs via the OTHER venue's opposite side)."""
    out: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    # Keep freshest PER (home, away, book, side) first, then group.
    by_side: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    for r in quotes:
        home, away = r.get("home"), r.get("away")
        book, side = r.get("book"), r.get("side")
        odds = r.get("odds")
        if not (home and away and book and side and odds):
            continue
        try:
            if float(odds) <= 1.0:
                continue
        except (TypeError, ValueError):
            continue
        key = (str(home), str(away), str(book), str(side))
        prev = by_side.get(key)
        if prev is None or str(r.get("captured_at", "")) > str(prev.get("captured_at", "")):
            by_side[key] = r
    for (home, away, book, side), row in by_side.items():
        out.setdefault((home, away, book), {})[side] = row  # type: ignore[assignment]
    return out  # type: ignore[return-value]


def _match_matchup_across_books(freshest: Dict[Tuple[str, str, str], Any]
                                 ) -> Dict[Tuple[str, str], Dict[str, Dict[str, Any]]]:
    """Bridge each book's own (home,away) string pair onto ONE canonical matchup
    key using pm_game_placer._name_matches (handles Kalshi city truncation).
    Returns {(canonical_home, canonical_away): {book: {side_role: row}}}."""
    # First pass: pick one "anchor" (home,away) string pair per book cluster --
    # the longest (fullest) name pair seen wins as the canonical label.
    anchors: List[Tuple[str, str]] = sorted(
        {(h, a) for (h, a, _b) in freshest.keys()},
        key=lambda ha: -(len(ha[0]) + len(ha[1])))
    canon_of: Dict[Tuple[str, str], Tuple[str, str]] = {}
    for ha in anchors:
        if ha in canon_of:
            continue
        h, a = ha
        canon_of[ha] = ha
        for other in anchors:
            if other in canon_of:
                continue
            oh, oa = other
            if _name_matches(h, oh) and _name_matches(a, oa):
                canon_of[other] = ha
            elif _name_matches(h, oa) and _name_matches(a, oh):
                # swapped home/away between venues -- still the same game, but
                # side roles will differ; skip auto-merge here (rare, and a
                # false merge would silently flip home/away sides).
                continue
    grouped: Dict[Tuple[str, str], Dict[str, Dict[str, Any]]] = {}
    for (h, a, book), sides_map in freshest.items():
        canon = canon_of.get((h, a), (h, a))
        bucket = grouped.setdefault(canon, {})
        bucket[book] = sides_map
    return grouped


def _implied_dec(row: Dict[str, Any]) -> Optional[float]:
    try:
        v = float(row.get("odds"))
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def _fee_prob(venue: str, price_prob: float) -> float:
    """Round-trip fee in probability units for *venue* at *price_prob* (0 for
    vig-priced sportsbooks -- their fee is already embedded in the price)."""
    v = str(venue).strip().lower()
    if v in ("kalshi", "polymarket"):
        fee = breakeven_edge_prob(v, price_prob)
        return fee if fee is not None else 0.0
    return 0.0


def find_arbs(
    grouped: Dict[Tuple[str, str], Dict[str, Dict[str, Any]]],
    *,
    now: Optional[datetime] = None,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
    min_locked_prob: float = DEFAULT_MIN_LOCKED_PROB,
) -> List[Dict[str, Any]]:
    """Return one row per detected two-venue lock, fee-adjusted, staleness-gated.

    A lock exists when buying side X on venue A + the OPPOSITE side on venue B
    costs, combined, strictly less than 1.0 in implied-probability terms after
    each venue's own round-trip fee is subtracted from its edge.
    """
    now_dt = now or datetime.now(timezone.utc)
    out: List[Dict[str, Any]] = []
    for (home, away), by_book in grouped.items():
        # 3-way markets (soccer draw) are NOT modeled here -- pricing "home" vs
        # "away" while ignoring a "draw" side this SAME book also quotes would
        # silently invent fake locked profit (the draw probability the two-way
        # math never subtracts is real weight, not free money). Drop any book
        # whose snapshot for this game includes a draw/tie side; a book that
        # only ever quotes {home, away} (a genuine two-way market, or a book
        # that happened to snapshot one side) stays eligible.
        two_way_books = {b: sides for b, sides in by_book.items()
                         if not (set(sides.keys()) - {"home", "away"})}
        books = list(two_way_books.keys())
        for i in range(len(books)):
            for j in range(len(books)):
                if i == j:
                    continue
                book_a, book_b = books[i], books[j]
                sides_a, sides_b = two_way_books[book_a], two_way_books[book_b]
                for side_a, row_a in sides_a.items():
                    other_side = "away" if side_a == "home" else (
                        "home" if side_a == "away" else None)
                    if other_side is None:
                        continue
                    row_b = sides_b.get(other_side)
                    if row_b is None:
                        continue
                    ts_a, ts_b = _parse_captured_at(row_a.get("captured_at")), \
                        _parse_captured_at(row_b.get("captured_at"))
                    if ts_a is None or ts_b is None:
                        continue
                    age_a = (now_dt - ts_a).total_seconds()
                    age_b = (now_dt - ts_b).total_seconds()
                    if age_a > max_age_sec or age_b > max_age_sec:
                        continue
                    dec_a, dec_b = _implied_dec(row_a), _implied_dec(row_b)
                    if dec_a is None or dec_b is None:
                        continue
                    p_a, p_b = 1.0 / dec_a, 1.0 / dec_b
                    fee_a, fee_b = _fee_prob(book_a, p_a), _fee_prob(book_b, p_b)
                    locked = 1.0 - (p_a + fee_a) - (p_b + fee_b)
                    if locked < min_locked_prob:
                        continue
                    out.append({
                        "sport": row_a.get("sport") or row_b.get("sport"),
                        "home": home, "away": away,
                        "leg_a": {"venue": str(book_a), "side": side_a,
                                  "decimal": round(dec_a, 6), "fee_prob": round(fee_a, 6),
                                  "captured_at": row_a.get("captured_at"),
                                  "game_id": row_a.get("game_id"), "age_sec": round(age_a, 1)},
                        "leg_b": {"venue": str(book_b), "side": other_side,
                                  "decimal": round(dec_b, 6), "fee_prob": round(fee_b, 6),
                                  "captured_at": row_b.get("captured_at"),
                                  "game_id": row_b.get("game_id"), "age_sec": round(age_b, 1)},
                        "locked_prob": round(locked, 6),
                    })
    # Dedup mirror pairs (A/B and B/A of the same lock): keep the higher-locked copy.
    dedup: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for r in out:
        key = tuple(sorted([
            (r["leg_a"]["venue"], r["leg_a"]["side"]),
            (r["leg_b"]["venue"], r["leg_b"]["side"]),
        ])) + (r["home"], r["away"])
        prev = dedup.get(key)
        if prev is None or r["locked_prob"] > prev["locked_prob"]:
            dedup[key] = r
    return sorted(dedup.values(), key=lambda r: -r["locked_prob"])


def scan(sport: str, *, now: Optional[datetime] = None,
        max_age_sec: float = DEFAULT_MAX_AGE_SEC,
        min_locked_prob: float = DEFAULT_MIN_LOCKED_PROB,
        date_key: Optional[str] = None,
        path_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load today's line_history for *sport* and return detected arb rows."""
    quotes = load_quotes(sport, date_key=date_key, path_dir=path_dir)
    freshest = freshest_by_book(quotes)
    grouped = _match_matchup_across_books(freshest)
    arbs = find_arbs(grouped, now=now, max_age_sec=max_age_sec,
                     min_locked_prob=min_locked_prob)
    for a in arbs:
        a.setdefault("sport", sport)
    return arbs


__all__ = [
    "DEFAULT_SPORTS", "DEFAULT_MAX_AGE_SEC", "DEFAULT_STAKE_UNITS",
    "DEFAULT_MIN_LOCKED_PROB", "HONEST_NOTE",
    "load_quotes", "freshest_by_book", "find_arbs", "scan",
]
