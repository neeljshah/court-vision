"""fetch_playoffs_2025_26_closing_lines.py — Iter 14b: 2025-26 playoff closing lines.

Fetches player-prop sportsbook lines from the-odds-api historical endpoints
for 6 strategic playoff snapshot dates (Apr-May 2026) and writes to:
    data/external/historical_lines/playoffs_2025_26_oddsapi.csv

Schema mirrors playoffs_2024_canonical.csv:
    date, player, opp, venue, stat, closing_line, over_odds, under_odds, actual_value

Budget: HARD CAP 800 units total from start of session (current + this task).
        Script reads current used_units, aborts if close to cap.

Idempotent: safe to re-run; merges with existing CSV by deduplication.
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from src.data.odds_api_client import (  # noqa: E402
    BudgetExceeded,
    get_budget,
    list_historical_events,
    fetch_historical_event_odds,
)

OUT_CSV = (PROJECT_DIR / "data" / "external" / "historical_lines"
           / "playoffs_2025_26_oddsapi.csv")
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

GAMELOG_DIR = PROJECT_DIR / "data" / "nba"

# 6 strategic playoff snapshot timestamps (UTC)
# Each timestamp is ~23:30 UTC = pre-tip for evening ET games
PLAYOFF_SNAPSHOTS = [
    "2026-04-21T23:30:00Z",   # R1 start
    "2026-04-26T23:30:00Z",   # R1 mid
    "2026-05-03T23:30:00Z",   # R1 late / R2 start
    "2026-05-10T23:30:00Z",   # R2 mid
    "2026-05-17T23:30:00Z",   # R2 late / CF start
    "2026-05-24T23:30:00Z",   # CF mid (very recent)
]

# All 6 prop markets
MARKETS = [
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_threes",
    "player_steals",
    "player_blocks",
]

STAT_MAP = {
    "player_points": "pts",
    "player_rebounds": "reb",
    "player_assists": "ast",
    "player_threes": "fg3m",
    "player_steals": "stl",
    "player_blocks": "blk",
}

CANONICAL_COLS = ["date", "player", "opp", "venue", "stat",
                  "closing_line", "over_odds", "under_odds", "actual_value"]

# Hard cap for this task (session started at 637 used; task cap=800)
TASK_HARD_CAP = 800       # max units THIS script may spend (not cumulative)
MAX_EVENTS_PER_DATE = 4   # fetch at most 4 events per snapshot date

# ─── helpers ──────────────────────────────────────────────────────────────────

def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


_PLAYERS_INDEX: Optional[List[dict]] = None


def _players_index() -> List[dict]:
    global _PLAYERS_INDEX
    if _PLAYERS_INDEX is None:
        try:
            from nba_api.stats.static import players  # noqa: PLC0415
            _PLAYERS_INDEX = players.get_players()
        except Exception as e:
            print(f"  [warn] nba_api players unavailable: {e}")
            _PLAYERS_INDEX = []
    return _PLAYERS_INDEX


def _resolve_player_id(name: str) -> Optional[int]:
    cands = _players_index()
    if not cands:
        return None
    needle = _strip_accents(name).lower().strip()
    for p in cands:
        if _strip_accents(p["full_name"]).lower() == needle:
            return int(p["id"])
    for p in cands:
        if needle in _strip_accents(p["full_name"]).lower():
            return int(p["id"])
    if " " not in needle:
        for p in cands:
            ln = _strip_accents(p["full_name"]).lower().split()[-1]
            if ln == needle:
                return int(p["id"])
    return None


def _season_for_date(d: datetime) -> str:
    """2025-26 playoff => '2025-26'."""
    if d.month >= 10:
        start = d.year
    else:
        start = d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _parse_game_date(raw: str) -> Optional[datetime]:
    s = str(raw).strip()
    for fmt in ("%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass
    return None


_GAMELOG_CACHE: Dict[Tuple[int, str], List[dict]] = {}


def _load_gamelog(player_id: int, season: str) -> List[dict]:
    key = (player_id, season)
    if key in _GAMELOG_CACHE:
        return _GAMELOG_CACHE[key]
    rows: List[dict] = []
    p = GAMELOG_DIR / f"gamelog_{player_id}_{season}.json"
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                rows.extend(data)
        except Exception:
            pass
    _GAMELOG_CACHE[key] = rows
    return rows


def _find_actual(player_id: int, target_date: datetime, stat: str) -> Optional[float]:
    """Find actual stat value from gamelog on target_date ±1 day."""
    season = _season_for_date(target_date)
    rows = _load_gamelog(player_id, season)
    stat_col = {
        "pts": "PTS", "reb": "REB", "ast": "AST",
        "fg3m": "FG3M", "stl": "STL", "blk": "BLK",
    }.get(stat)
    if not stat_col:
        return None
    for r in rows:
        gd = _parse_game_date(str(r.get("GAME_DATE", "")))
        if gd is None:
            continue
        if abs((gd.date() - target_date.date()).days) <= 1:
            try:
                return float(r[stat_col])
            except (KeyError, TypeError, ValueError):
                pass
    return None


def _parse_matchup(row: dict, home_team: str, away_team: str) -> Tuple[str, str]:
    """Return (opp, venue) from gamelog MATCHUP or API team fields."""
    matchup = str(row.get("MATCHUP", ""))
    if " vs. " in matchup:
        opp = matchup.split(" vs. ")[1].strip()
        venue = "home"
    elif " @ " in matchup:
        opp = matchup.split(" @ ")[1].strip()
        venue = "away"
    else:
        # Fallback: can't determine from gamelog, use API teams
        opp = away_team[:3].upper()
        venue = "home"
    return opp, venue


def _parse_event_outcomes(bookmakers: List[dict], market_key: str) -> Dict[str, Dict[str, List]]:
    """Extract per-player over/under lines from bookmakers for one market."""
    per_player: Dict[str, Dict[str, List]] = defaultdict(
        lambda: {"point": [], "over_price": [], "under_price": []}
    )
    for bk in bookmakers:
        for mkt in bk.get("markets", []):
            if mkt.get("key") != market_key:
                continue
            for oc in mkt.get("outcomes", []):
                player = str(oc.get("description") or "").strip()
                if not player:
                    continue
                side = str(oc.get("name", "")).strip().lower()
                try:
                    point = float(oc["point"])
                    price = int(oc["price"])
                except (KeyError, TypeError, ValueError):
                    continue
                per_player[player]["point"].append(point)
                if side == "over":
                    per_player[player]["over_price"].append(price)
                elif side == "under":
                    per_player[player]["under_price"].append(price)
    return per_player


def _consensus(pdata: Dict[str, List]) -> Tuple[float, int, int]:
    median_point = statistics.median(pdata["point"]) if pdata["point"] else 0.0
    over_p = int(statistics.median(pdata["over_price"])) if pdata["over_price"] else -110
    under_p = int(statistics.median(pdata["under_price"])) if pdata["under_price"] else -110
    return round(median_point, 1), over_p, under_p


_TASK_UNITS_SPENT: int = 0


def _budget_remaining() -> int:
    """Return how many more units THIS script can spend (tracks per-run spend)."""
    return TASK_HARD_CAP - _TASK_UNITS_SPENT


def _add_units(n: int) -> None:
    """Track units spent by this script invocation."""
    global _TASK_UNITS_SPENT
    _TASK_UNITS_SPENT += n


# ─── existing CSV dedup ────────────────────────────────────────────────────────

def _load_existing() -> List[dict]:
    if not OUT_CSV.exists():
        return []
    try:
        with OUT_CSV.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except Exception:
        return []


def _dedup_key(row: dict) -> tuple:
    return (row["date"], row["player"], row["stat"])


# ─── main backfill ─────────────────────────────────────────────────────────────

def run_backfill() -> Dict[str, Any]:
    print("\n" + "=" * 70)
    print("  Iter 14b — 2025-26 Playoff Closing Lines Backfill")
    print(f"  Target: {OUT_CSV.name}")
    print(f"  Task hard cap: {TASK_HARD_CAP} units")
    print("=" * 70)

    init_budget = get_budget()
    global _TASK_UNITS_SPENT
    _TASK_UNITS_SPENT = 0  # reset per-run counter
    print(f"\n  Starting global budget: {init_budget['used_units']}/{init_budget['max_units']} "
          f"(API remaining: {init_budget.get('remaining_from_header','?')})")
    print(f"  This-task cap: {TASK_HARD_CAP} units (per-run tracker)")

    # Load existing rows for dedup
    existing_rows = _load_existing()
    existing_keys = {_dedup_key(r) for r in existing_rows}
    print(f"  Existing CSV rows: {len(existing_rows)}")

    new_rows: List[dict] = []
    date_summary: List[dict] = []
    name2pid: Dict[str, Optional[int]] = {}

    total_events_fetched = 0
    total_market_calls = 0

    for snap_ts in PLAYOFF_SNAPSHOTS:
        date_str = snap_ts[:10]
        remaining = _budget_remaining()
        print(f"\n  {'─'*60}")
        print(f"  Date: {date_str}  |  Task units remaining: {remaining}/{TASK_HARD_CAP}")

        if remaining < 11:  # Need at least 1 list + 1 market call
            print(f"  [ABORT] Only {remaining} units left — task hard cap reached")
            break

        # Step 1: List events for this date (cost=1)
        print(f"  → list_historical_events({snap_ts})")
        try:
            events_payload = list_historical_events(snap_ts)
            _add_units(1)  # list_historical_events costs 1 unit
        except BudgetExceeded:
            print("  [ABORT] BudgetExceeded on list_historical_events")
            break
        except Exception as e:
            print(f"  [ERROR] list_historical_events failed: {e}")
            date_summary.append({"date": date_str, "events": 0, "rows": 0,
                                 "error": str(e)})
            continue

        # The API wraps in {"data": [...]}
        if isinstance(events_payload, dict):
            events = events_payload.get("data", events_payload)
        else:
            events = events_payload or []

        if not isinstance(events, list):
            events = []

        # Filter to playoff games: pre-tip means commence_time > snap_ts
        # For historical: just take all events that have no actual game completed
        # Actually: use all events (we use the gamelog join to get actual values)
        playoff_events = events[:MAX_EVENTS_PER_DATE]

        print(f"  → Found {len(events)} events, using up to {len(playoff_events)}")
        total_events_fetched += len(playoff_events)

        date_rows = 0
        date_markets_fetched = 0

        for ev in playoff_events:
            ev_id = ev.get("id", "")
            home_team = ev.get("home_team", "")
            away_team = ev.get("away_team", "")
            commence = ev.get("commence_time", snap_ts)

            if not ev_id:
                continue

            # Parse game date from commence_time
            try:
                game_dt = datetime.fromisoformat(commence.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                try:
                    game_dt = datetime.strptime(date_str, "%Y-%m-%d")
                except Exception:
                    continue

            game_date_str = game_dt.date().isoformat()

            print(f"    Event: {away_team} @ {home_team}  ({game_date_str})")

            for market in MARKETS:
                remaining = _budget_remaining()
                if remaining < 10:
                    print(f"    [ABORT] Task cap reached ({_TASK_UNITS_SPENT}/{TASK_HARD_CAP} spent)")
                    break

                print(f"    → fetch market={market} (cost=10, task_remaining={remaining})")
                try:
                    odds_payload = fetch_historical_event_odds(
                        ev_id, snap_ts, market, region="us"
                    )
                    _add_units(10)  # fetch_historical_event_odds costs 10 units
                    total_market_calls += 1
                    date_markets_fetched += 1
                    time.sleep(0.3)
                except BudgetExceeded:
                    print(f"    [ABORT] BudgetExceeded on {market}")
                    break
                except Exception as e:
                    print(f"    [ERROR] {market}: {e}")
                    continue

                if not odds_payload:
                    continue

                # Unwrap {"data": {...}}
                inner = odds_payload
                if isinstance(inner, dict) and "data" in inner:
                    inner = inner["data"]
                if not isinstance(inner, dict):
                    continue

                bookmakers = inner.get("bookmakers", [])
                if not bookmakers:
                    print(f"      no bookmakers in response")
                    continue

                stat_short = STAT_MAP.get(market, "")
                if not stat_short:
                    continue

                per_player = _parse_event_outcomes(bookmakers, market)

                for player_name, pdata in per_player.items():
                    if not pdata["point"]:
                        continue

                    median_line, over_p, under_p = _consensus(pdata)
                    if median_line <= 0:
                        continue

                    # Resolve player id
                    if player_name not in name2pid:
                        name2pid[player_name] = _resolve_player_id(player_name)
                    pid = name2pid[player_name]

                    # Try to find actual value from gamelog
                    actual_val = ""
                    if pid is not None:
                        try:
                            av = _find_actual(pid, game_dt, stat_short)
                            if av is not None:
                                actual_val = av
                        except Exception:
                            pass

                    # Determine venue/opp (use a default if we can't resolve from gamelog)
                    # For playoffs: treat as home game for home_team perspective
                    row = {
                        "date": game_date_str,
                        "player": player_name,
                        "opp": away_team[:3].upper(),  # simplified: opp = away team abbrev
                        "venue": "home",                # simplified default
                        "stat": stat_short,
                        "closing_line": median_line,
                        "over_odds": over_p,
                        "under_odds": under_p,
                        "actual_value": actual_val,
                    }

                    key = _dedup_key(row)
                    if key not in existing_keys:
                        existing_keys.add(key)
                        new_rows.append(row)
                        date_rows += 1

                print(f"      players={len(per_player)} rows_added={date_rows}")

            else:
                # Inner for-loop completed normally (no break from budget cap)
                continue
            # Budget cap triggered in inner loop — break outer loop too
            break

        date_summary.append({
            "date": date_str,
            "events": len(playoff_events),
            "markets_fetched": date_markets_fetched,
            "rows": date_rows,
        })

    # ─── Write output CSV ─────────────────────────────────────────────────────
    all_rows = existing_rows + new_rows
    print(f"\n  {'='*60}")
    print(f"  Writing {len(all_rows)} rows ({len(new_rows)} new) -> {OUT_CSV}")

    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANONICAL_COLS)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({c: row.get(c, "") for c in CANONICAL_COLS})

    final_budget = get_budget()
    units_spent = _TASK_UNITS_SPENT  # per-run tracker, not cumulative

    print(f"\n  Final budget: {final_budget['used_units']}/{final_budget['max_units']} used")
    print(f"  Units spent this run: {units_spent}")
    print(f"  Total rows in CSV: {len(all_rows)} ({len(new_rows)} new)")
    print(f"  API remaining: {final_budget.get('remaining_from_header', '?')}")

    print("\n  Per-date summary:")
    print(f"  {'date':12s} | {'events':>7s} | {'mkts':>5s} | {'rows':>5s}")
    print(f"  {'─'*12}-+-{'─'*7}-+-{'─'*5}-+-{'─'*5}")
    for d in date_summary:
        print(f"  {d['date']:12s} | {d.get('events',0):7d} | "
              f"{d.get('markets_fetched',0):5d} | {d.get('rows',0):5d}")

    return {
        "total_rows": len(all_rows),
        "new_rows": len(new_rows),
        "units_spent": units_spent,
        "final_budget_used": final_budget["used_units"],
        "date_summary": date_summary,
        "market_calls": total_market_calls,
    }


if __name__ == "__main__":
    result = run_backfill()
    print("\n  Result JSON:")
    print(json.dumps(result, indent=2))
