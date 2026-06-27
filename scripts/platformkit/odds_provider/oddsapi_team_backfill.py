"""scripts.platformkit.odds_provider.oddsapi_team_backfill -- independent, MULTI-SPORT
historical team-strength odds backfill from The Odds API (us,eu = Pinnacle + US books).

NORTH STAR: the devigged Pinnacle close is our benchmark ("beat the devigged close").
This is a ONE-TIME paid-API historical acquisition: it builds a leak-free, reusable
corpus of moneyline / spread / total closes per game, with the Shin-devigged anchor
(Pinnacle) precomputed. After this, the AI runs independently on our own keyless live
scrapers + this historical corpus -- the paid API is not needed for ongoing operation.

INDEPENDENT: owns its date planner, per-sport store, budget cap and idempotent manifest.
It borrows only the vetted HTTP/cache/budget machinery (src.data.odds_api_client._gate_or_fetch
-- sport-agnostic, imported never edited) and the vetted Shin devig (eval_gate.shin).
No price is ever fabricated; only genuinely PREGAME snapshots are kept; no $ / ROI implied.

Cost: 10 units x n_markets x n_regions per snapshot date. us,eu x {h2h,spreads,totals}
= 60 units/date. Active sports first: mlb + soccer_intl (World Cup); NBA is offseason.

CLI:
    python -m scripts.platformkit.odds_provider.oddsapi_team_backfill --sport mlb --season 2026
    python -m scripts.platformkit.odds_provider.oddsapi_team_backfill --sport soccer_intl --season wc2026
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.platformkit.eval_gate.shin import shin_devig_decimal  # noqa: E402
from scripts.platformkit.odds_provider.base import american_to_decimal  # noqa: E402

logger = logging.getLogger(__name__)

# ---- configuration -------------------------------------------------------- #

DEFAULT_REGION = "us,eu"                       # eu carries Pinnacle; us carries DK/FD/...
DEFAULT_MARKETS = ["h2h", "spreads", "totals"]
DEFAULT_ANCHOR = "pinnacle"                    # substring match (case-insensitive)
MAX_UNITS = 20000   # mirrors the client gate; we self-heal local budget from the header

SPORT_KEYS: Dict[str, str] = {
    "nba": "basketball_nba",
    "mlb": "baseball_mlb",
    "soccer_intl": "soccer_fifa_world_cup",    # World Cup
}

# Per-sport snapshot hour (UTC): chosen pregame for the evening slate; day games that
# already started are dropped by the pregame guard (kept honest, never as a "close").
SNAP_HOURS: Dict[str, str] = {
    "nba": "23:30:00", "mlb": "22:30:00", "soccer_intl": "15:30:00",
}

# Inclusive [start, end] calendar spans, one snapshot per day. Active sports first.
SEASONS: Dict[str, Dict[str, Tuple[str, str]]] = {
    "mlb": {
        "2026": ("2026-03-26", "2026-06-26"),   # season-to-date (recency-first)
        "2025": ("2025-03-27", "2025-11-01"),   # full incl postseason
    },
    "soccer_intl": {
        "wc2026": ("2026-06-11", "2026-06-26"),  # World Cup, tournament-to-date
    },
    "nba": {
        "2025_26": ("2025-10-21", "2026-04-12"),
        "2024_25": ("2024-10-22", "2025-04-13"),
    },
}

OUT_DIR = ROOT / "data" / "external" / "historical_lines"
DONE_PATH = OUT_DIR / "_team_backfill_done.json"


def _out_jsonl(sport: str) -> Path:
    return OUT_DIR / f"{sport}_team_strength.jsonl"


# ---- date planner --------------------------------------------------------- #

def season_snapshots(sport: str, season: str, snap_hour: Optional[str] = None) -> List[str]:
    """Return ISO8601 snapshot timestamps (one per in-season calendar day)."""
    spans = SEASONS.get(sport, {})
    if season not in spans:
        raise ValueError(f"unknown season {season!r} for {sport!r}; known: {sorted(spans)}")
    hour = snap_hour or SNAP_HOURS.get(sport, "23:30:00")
    start = datetime.strptime(spans[season][0], "%Y-%m-%d").date()
    end = datetime.strptime(spans[season][1], "%Y-%m-%d").date()
    out: List[str] = []
    d = start
    while d <= end:
        out.append(f"{d.isoformat()}T{hour}Z")
        d += timedelta(days=1)
    return out


# ---- pure parsers (no I/O; unit-testable on canned payloads) -------------- #

def _book_outcomes(market_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Outcomes -> [{name, price(decimal), american, point}].

    The client requests oddsFormat=american, so raw prices are American moneyline
    (e.g. -262 / +228); we convert to decimal (devig + storage canonical) and keep
    the raw american. Outcomes that fail to convert are dropped (never fabricated)."""
    out: List[Dict[str, Any]] = []
    for o in market_obj.get("outcomes", []) or []:
        raw = o.get("price")
        price = american_to_decimal(raw)
        if price is None:
            continue
        out.append({"name": str(o.get("name") or ""), "price": round(price, 5),
                    "american": raw, "point": o.get("point")})
    return out


def _anchor_devig(outcomes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Shin-devig an n-way anchor market (2-way ML/spread/total, 3-way soccer 1X2);
    None when fewer than 2 priced sides or the booksum is degenerate."""
    if len(outcomes) < 2:
        return None
    prices = [o["price"] for o in outcomes]
    booksum = sum(1.0 / p for p in prices)
    try:
        probs, z = shin_devig_decimal(prices)
    except (AssertionError, ValueError, ZeroDivisionError):
        return None
    return {"names": [o["name"] for o in outcomes],
            "probs": [round(p, 6) for p in probs],
            "z": round(float(z), 6), "booksum": round(booksum, 6)}


def _is_pregame(commence: Optional[str], snapshot_ts: Optional[str]) -> bool:
    """True when the game had NOT started at the snapshot (commence > snapshot)."""
    if not commence or not snapshot_ts:
        return True                     # no info -> don't drop (parser-level tests)
    try:
        c = datetime.fromisoformat(commence.replace("Z", "+00:00"))
        s = datetime.fromisoformat(snapshot_ts.replace("Z", "+00:00"))
    except ValueError:
        return True
    return c > s


def parse_event(ev: Dict[str, Any], market: str, anchor: str = DEFAULT_ANCHOR,
                snapshot_ts: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Normalise one event for one market: anchor outcomes + devig + all books.

    Returns None when the event is in-play at the snapshot (not a close) or carries
    no priced book for this market. The anchor (Pinnacle) devig is the benchmark
    close; absent when Pinnacle does not price this market in this snapshot."""
    if not _is_pregame(ev.get("commence_time"), snapshot_ts):
        return None
    all_books: Dict[str, List[Dict[str, Any]]] = {}
    anchor_outcomes: List[Dict[str, Any]] = []
    for bk in ev.get("bookmakers", []) or []:
        title = str(bk.get("title") or "")
        mkt = next((m for m in bk.get("markets", []) or [] if m.get("key") == market), None)
        if mkt is None:
            continue
        outs = _book_outcomes(mkt)
        if not outs:
            continue
        all_books[title] = outs
        if anchor in title.lower():
            anchor_outcomes = outs
    if not all_books:
        return None
    return {
        "event_id": ev.get("id"), "commence_time": ev.get("commence_time"),
        "home": ev.get("home_team"), "away": ev.get("away_team"),
        "market": market, "n_books": len(all_books), "anchor": anchor,
        "anchor_outcomes": anchor_outcomes, "anchor_devig": _anchor_devig(anchor_outcomes),
        "all_books": all_books,
    }


def parse_snapshot(payload: Any, market: str, date: str, anchor: str = DEFAULT_ANCHOR,
                   sport: Optional[str] = None) -> List[Dict[str, Any]]:
    """Parse a /historical/.../odds payload into per-event PREGAME rows for one market."""
    data = payload.get("data") if isinstance(payload, dict) else payload
    snapshot_ts = payload.get("timestamp") if isinstance(payload, dict) else None
    rows: List[Dict[str, Any]] = []
    for ev in data or []:
        row = parse_event(ev, market, anchor=anchor, snapshot_ts=snapshot_ts)
        if row is None:
            continue
        row["date"] = date[:10]
        row["snapshot_ts"] = snapshot_ts
        row["sport"] = sport
        rows.append(row)
    return rows


# ---- idempotent store ----------------------------------------------------- #

def _load_done() -> Dict[str, Any]:
    if DONE_PATH.exists():
        try:
            return json.loads(DONE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("done-manifest corrupt -- starting fresh")
    return {}


def _save_done(done: Dict[str, Any]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DONE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(done, indent=0), encoding="utf-8")
    tmp.replace(DONE_PATH)


def _done_key(sport: str, date: str, market: str, region: str) -> str:
    return f"{sport}|{date[:10]}|{market}|{region}"


def _append_rows(rows: List[Dict[str, Any]], sport: str, region: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with _out_jsonl(sport).open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(dict(r, region=region)) + "\n")


# ---- budget self-heal ----------------------------------------------------- #

def reconcile_local_budget() -> Optional[int]:
    """Sync the client's local _budget.json used_units to the authoritative API
    header (remaining_from_header). The local accumulator drifts (e.g. after a
    billing-period reset); the response header is ground truth."""
    from src.data.odds_api_client import get_budget, BUDGET_PATH  # type: ignore
    state = get_budget()
    remaining = state.get("remaining_from_header")
    if not isinstance(remaining, int):
        return None
    state["used_units"] = MAX_UNITS - remaining
    state["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    BUDGET_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return remaining


# ---- sport-agnostic fetch (gated client is NBA-locked; _gate_or_fetch is not) -- #

def _fetch_historical(sport_key: str, date: str, market: str, region: str,
                      cost_units: int) -> Any:
    from src.data.odds_api_client import _gate_or_fetch, _api_key, API_BASE  # type: ignore
    date_iso = date if "T" in date else f"{date}T12:00:00Z"
    params = {"apiKey": _api_key(), "regions": region, "markets": market,
              "oddsFormat": "american", "date": date_iso}
    url = f"{API_BASE}/historical/sports/{sport_key}/odds?" + urllib.parse.urlencode(params)
    cache_key = f"{sport_key}_{date[:10]}_{market}_{region}"
    return _gate_or_fetch("historical_odds", cache_key, url, params, cost_units=cost_units)


# ---- runner --------------------------------------------------------------- #

def run_backfill(sport: str, dates: List[str], markets: List[str],
                 region: str = DEFAULT_REGION, max_units: int = 200,
                 anchor: str = DEFAULT_ANCHOR) -> Dict[str, Any]:
    """Fetch + parse + append PREGAME closes, capped at `max_units` for this run.
    Idempotent: (sport, date, market, region) already in the manifest are skipped;
    the client also serves from its 30-day disk cache (re-runs cost zero units)."""
    from src.data.odds_api_client import BudgetExceeded, get_budget  # type: ignore
    sport_key = SPORT_KEYS[sport]
    n_regions = len([r for r in region.split(",") if r.strip()])
    cost = 10 * n_regions
    rem0 = get_budget().get("remaining_from_header")
    done = _load_done()
    spent = n_rows = n_calls = skipped = 0
    for date in dates:
        for market in markets:
            key = _done_key(sport, date, market, region)
            if key in done:
                skipped += 1
                continue
            if spent + cost > max_units:
                logger.info("run cap reached (%d + %d > %d) -- stopping cleanly",
                            spent, cost, max_units)
                _save_done(done)
                return _summary(n_calls, n_rows, spent, skipped, rem0,
                                capped=True, next_date=date, next_market=market)
            try:
                payload = _fetch_historical(sport_key, date, market, region, cost)
            except BudgetExceeded as e:
                logger.warning("budget gate tripped: %s", e)
                _save_done(done)
                return _summary(n_calls, n_rows, spent, skipped, rem0, budget_gate=True)
            spent += cost
            n_calls += 1
            rows = parse_snapshot(payload, market, date, anchor=anchor, sport=sport)
            _append_rows(rows, sport, region)
            n_rows += len(rows)
            done[key] = {"rows": len(rows),
                         "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            _save_done(done)   # incremental: kill-safe resume w/o duplicate rows
    _save_done(done)
    reconcile_local_budget()
    return _summary(n_calls, n_rows, spent, skipped, rem0)


def _summary(n_calls: int, n_rows: int, spent: int, skipped: int,
             rem0: Optional[int] = None, **extra: Any) -> Dict[str, Any]:
    """`units_est` = worst-case (drives the cap); `units_actual` = real API-header
    delta (0 on cache hits). Honest accounting: re-parses cost no real credits."""
    from src.data.odds_api_client import get_budget  # type: ignore
    rem1 = get_budget().get("remaining_from_header")
    actual = (rem0 - rem1) if isinstance(rem0, int) and isinstance(rem1, int) else None
    s = {"calls": n_calls, "rows": n_rows, "units_est": spent,
         "units_actual": actual, "remaining": rem1, "skipped": skipped}
    s.update(extra)
    return s


# ---- CLI ------------------------------------------------------------------ #

def _expand_dates(args: argparse.Namespace) -> List[str]:
    if args.dates:
        hour = SNAP_HOURS.get(args.sport, "23:30:00")
        return [d if "T" in d else f"{d}T{hour}Z" for d in args.dates]
    if args.season == "all":
        out: List[str] = []
        for s in SEASONS.get(args.sport, {}):
            out.extend(season_snapshots(args.sport, s))
        return out
    return season_snapshots(args.sport, args.season)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Backfill historical team-strength odds (us,eu + Pinnacle).")
    ap.add_argument("--sport", default="mlb", choices=sorted(SPORT_KEYS))
    ap.add_argument("--season", default="all",
                    help="season key for the sport, or 'all' (ignored when --dates given)")
    ap.add_argument("--dates", nargs="*", help="explicit snapshot dates (YYYY-MM-DD or ISO)")
    ap.add_argument("--markets", nargs="*", default=DEFAULT_MARKETS)
    ap.add_argument("--region", default=DEFAULT_REGION)
    ap.add_argument("--anchor", default=DEFAULT_ANCHOR)
    ap.add_argument("--max-units", type=int, default=200,
                    help="per-run credit cap (default 200)")
    ap.add_argument("--reconcile-only", action="store_true",
                    help="just sync local budget from the API header and exit")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.reconcile_only:
        print(json.dumps({"reconciled_remaining": reconcile_local_budget()}))
        return 0

    dates = _expand_dates(args)
    summary = run_backfill(args.sport, dates, args.markets, region=args.region,
                           max_units=args.max_units, anchor=args.anchor)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
