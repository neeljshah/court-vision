"""scripts.platformkit.clv.scraped_line_gaps -- find +CLV gaps in OUR OWN scraped
lines (data/cache/line_history/<sport>/<date>.jsonl), all sports, all markets.

This is the honest "use the lines we are getting, find the gaps" lever, generalized
from the NBA per-book edge sheets (cv_dk_edge / build_per_book_edge_audit) to every
sport on the multi-book feed WE scrape -- DraftKings + FanDuel + Pinnacle, on
moneyline / spread / total, already devigged + timestamped. For each (game, market,
line) it takes the BEST book price per side across our books and compares it to the
SHARP fair (Pinnacle anchor, else cross-book median) via the vetted best_price math.
A row appears ONLY where the best price we can actually take beats fair -- a positive
expected-CLV bet. NO OddsAPI, NO live re-fetch: it reads the snapshot already on disk.

Unlike a moneyline-only live scan, this covers SPREAD and TOTAL too (grouped by the
exact line so only like-for-like prices compete), which is where soft books most
often lag the sharp number. The common, honest answer on an efficient slate is an
empty list; +CLV is PROBABILITY space, NOT a $ edge claim.

CLI:
    python -m scripts.platformkit.clv.scraped_line_gaps [--sport mlb] [--date 2026-06-29]
                                                        [--min-clv 0.5]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from scripts.platformkit.clv.best_price import value_bets

LINE_HISTORY = Path(_REPO) / "data" / "cache" / "line_history"
DEFAULT_SPORTS = ("mlb", "nba", "soccer_intl", "soccer", "tennis")
# (market_type -> the two opposing sides we compare). Spread/total are grouped by
# the exact line so only like-for-like quotes ever compete for the best price.
_MARKET_SIDES = {"moneyline": ("home", "away"), "spread": ("home", "away"),
                 "total": ("over", "under")}


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _parse_ts(v: Any) -> float:
    try:
        s = str(v).replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except Exception:  # noqa: BLE001
        return 0.0


def load_rows(sport: str, date: str, *, base: Optional[Path] = None
              ) -> List[Dict[str, Any]]:
    """Read the day's scraped line_history rows for one sport (never raises)."""
    root = Path(base) if base is not None else LINE_HISTORY
    p = root / sport / ("%s.jsonl" % date)
    if not p.exists():
        return []
    out: List[Dict[str, Any]] = []
    for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:  # noqa: BLE001 -- one bad line never sinks the read
            continue
    return out


def _latest_per_quote(rows: Sequence[Dict[str, Any]]
                      ) -> Dict[Tuple[Any, ...], Dict[str, Any]]:
    """Keep only the freshest row per (game, market, line, side, book) by captured_at
    -- the current state of each quote, not its whole intraday history."""
    best: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for r in rows:
        mt = r.get("market_type")
        if mt not in _MARKET_SIDES:
            continue
        key = (r.get("game_id"), mt, r.get("line"), r.get("side"), r.get("book"))
        ts = _parse_ts(r.get("captured_at"))
        cur = best.get(key)
        if cur is None or ts >= _parse_ts(cur.get("captured_at")):
            best[key] = r
    return best


# A gap is only REAL if the competing book quotes are CONTEMPORANEOUS. A book quote
# stale by more than this (vs the freshest quote in the same game/market/line) is
# DROPPED before pricing -- otherwise a 30-min-old soft line manufactures a fake
# "edge" against a fresh one (the classic stale-quote mirage; both sides show +CLV).
DEFAULT_MAX_STALE_SEC = 600.0


def build_games(rows: Sequence[Dict[str, Any]], *,
                max_stale_sec: float = DEFAULT_MAX_STALE_SEC) -> List[Dict[str, Any]]:
    """Group the freshest quotes into value_bets() input, one entry per
    (game, market, line) carrying {book: {side: decimal}} for the two sides.

    Freshness gate: within each (game, market, line), the newest quote sets the
    reference time and any book quote older than ``max_stale_sec`` behind it is
    dropped -- so only contemporaneous prices ever compete for the best line."""
    latest = _latest_per_quote(rows)
    groups: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    # First pass: bucket the freshest quotes and find each group's reference time.
    buckets: Dict[Tuple[Any, ...], List[Tuple[str, str, float, float]]] = {}
    ref_ts: Dict[Tuple[Any, ...], float] = {}
    for (game_id, mt, line, side, book), r in latest.items():
        sides = _MARKET_SIDES[mt]
        if side not in sides:
            continue
        try:
            dec = float(r.get("odds"))
        except (TypeError, ValueError):
            continue
        if dec <= 1.0:
            continue
        gk = (game_id, mt, line)
        ts = _parse_ts(r.get("captured_at"))
        buckets.setdefault(gk, []).append((book, side, dec, ts))
        if ts > ref_ts.get(gk, 0.0):
            ref_ts[gk] = ts
            g = groups.get(gk)
            tag = mt if mt == "moneyline" else "%s %s" % (mt, line)
            label = "%s@%s %s" % (r.get("away"), r.get("home"), tag)
            if g is None:
                groups[gk] = {"matchup": label, "side_a": sides[0],
                              "side_b": sides[1], "market": mt, "line": line,
                              "book_prices": {}}
    # Second pass: keep only quotes fresh vs the group's reference time.
    for gk, quotes in buckets.items():
        ref = ref_ts.get(gk, 0.0)
        bp = groups[gk]["book_prices"]
        for book, side, dec, ts in quotes:
            if ref - ts > max_stale_sec:
                continue  # stale quote -- cannot define a real gap
            bp.setdefault(book, {})[side] = dec
    return list(groups.values())


def find_gaps(sport: str, date: Optional[str] = None, *, min_clv_pct: float = 0.5,
              max_stale_sec: float = DEFAULT_MAX_STALE_SEC,
              base: Optional[Path] = None) -> Dict[str, Any]:
    """Find +CLV line-shop gaps in our scraped feed for one sport/day."""
    d = date or _today()
    rows = load_rows(sport, d, base=base)
    games = build_games(rows, max_stale_sec=max_stale_sec)
    vb = value_bets(games, min_clv_pct=min_clv_pct)
    # re-attach market/line context (value_bets only echoes matchup+side).
    by_matchup = {g["matchup"]: g for g in games}
    for v in vb:
        ctx = by_matchup.get(v.get("matchup")) or {}
        v["sport"] = sport
        v["market"] = ctx.get("market")
        v["line"] = ctx.get("line")
    n_books = [len(g["book_prices"]) for g in games]
    shoppable = sum(1 for n in n_books if n >= 2)
    return {"sport": sport, "date": d, "rows": len(rows), "groups": len(games),
            "shoppable": shoppable, "max_books": max(n_books) if n_books else 0,
            "gaps": vb}


def scan(sports: Sequence[str] = DEFAULT_SPORTS, date: Optional[str] = None, *,
         min_clv_pct: float = 0.5, max_stale_sec: float = DEFAULT_MAX_STALE_SEC,
         base: Optional[Path] = None) -> Dict[str, Any]:
    by_sport = {s: find_gaps(s, date, min_clv_pct=min_clv_pct,
                             max_stale_sec=max_stale_sec, base=base)
                for s in sports}
    total = sum(len(b["gaps"]) for b in by_sport.values())
    return {"date": date or _today(), "min_clv_pct": min_clv_pct,
            "total_gaps": total, "by_sport": by_sport}


def render(res: Dict[str, Any]) -> str:
    L: List[str] = ["=" * 78,
                    "SCRAPED-LINE +CLV GAPS -- best of OUR books vs sharp fair",
                    "(our DK/FD/Pinnacle feed; ML+spread+total; min CLV >= %.2f%%)"
                    % res["min_clv_pct"], "=" * 78]
    for sport, b in res["by_sport"].items():
        L.append("%-12s %d rows -> %d groups (%d shoppable >=2 books, max %d) "
                 "-> %d +CLV gap(s)"
                 % (sport, b["rows"], b["groups"], b["shoppable"],
                    b["max_books"], len(b["gaps"])))
        for v in b["gaps"]:
            L.append("   %-30s %-5s best %.2f @%-14s vs fair %.3f (%s) +CLV %.2f%%"
                     % (v.get("matchup"), v.get("side"), v.get("best_price"),
                        v.get("best_book"), v.get("fair_prob"),
                        v.get("fair_source"), v.get("expected_clv_pct")))
    L.append("-" * 78)
    if res["total_gaps"] == 0:
        L.append("No +CLV gap in our scraped lines right now -- efficient across our "
                 "books. Honest empty > a fabricated edge. (More books = wider "
                 "best-of-N; that is the data lever, not a smarter model.)")
    else:
        L.append("%d +CLV gap(s): take the BEST price shown on OUR feed; CLV settles "
                 "it." % res["total_gaps"])
    L.append("=" * 78)
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="find +CLV gaps in our scraped lines")
    p.add_argument("--sport", default=None, help="one sport (default: all)")
    p.add_argument("--date", default=None, help="YYYY-MM-DD (default: today UTC)")
    p.add_argument("--min-clv", type=float, default=0.5, help="min expected CLV %%")
    p.add_argument("--max-stale", type=float, default=DEFAULT_MAX_STALE_SEC,
                   help="drop quotes staler than this many sec vs the freshest")
    a = p.parse_args(argv)
    sports = (a.sport,) if a.sport else DEFAULT_SPORTS
    print(render(scan(sports, a.date, min_clv_pct=a.min_clv,
                      max_stale_sec=a.max_stale)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
