"""fetch_2025_26_rs_closing_lines.py — Iter 14a: Backfill 2025-26 RS closing lines.

Fetches historical event odds for 12 dates across the 2025-26 NBA regular season
(Oct 22, 2025 -> Apr 13, 2026) and writes them to:
    data/external/historical_lines/regular_season_2025_26_oddsapi.csv

Budget plan: 12 dates × ~1 (event list) + up to 5 events × 6 markets × 10 = ~301 max per date.
Realistic: ~100-150 units/date. Hard cap: start_budget + 1500 units.

Schema matches regular_season_2024_25_oddsapi.csv:
    date,player,opp,venue,stat,closing_line,over_odds,under_odds,actual_value
Plus a season column: 2025-26
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, date as date_type, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from src.data.odds_api_client import (  # noqa: E402
    fetch_historical_event_odds,
    list_historical_events,
    get_budget,
    BudgetExceeded,
)

# ─── configuration ────────────────────────────────────────────────────────────

OUT_CSV = (PROJECT_DIR / "data" / "external" / "historical_lines"
           / "regular_season_2025_26_oddsapi.csv")
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

CANONICAL_COLS = [
    "date", "player", "opp", "venue", "stat",
    "closing_line", "over_odds", "under_odds", "actual_value", "season",
]

GAMELOG_DIR = PROJECT_DIR / "data" / "nba"

# 12 dates across 2025-26 RS — snapshot at T01:30Z (pre-tip for US east games)
RS_DATES: List[str] = [
    "2025-10-28T01:30:00Z",
    "2025-11-12T01:30:00Z",
    "2025-11-25T01:30:00Z",
    "2025-12-10T01:30:00Z",
    "2025-12-22T01:30:00Z",
    "2026-01-08T01:30:00Z",
    "2026-01-22T01:30:00Z",
    "2026-02-05T01:30:00Z",
    "2026-02-18T01:30:00Z",
    "2026-03-10T01:30:00Z",
    "2026-03-25T01:30:00Z",
    "2026-04-08T01:30:00Z",
]

# Markets: all 6 player-prop markets
MARKETS = [
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_threes",
    "player_steals",
    "player_blocks",
]

# Stat map: API market -> canonical stat code + gamelog column
STAT_META: Dict[str, Dict[str, str]] = {
    "player_points":   {"stat": "pts",  "col": "PTS"},
    "player_rebounds": {"stat": "reb",  "col": "REB"},
    "player_assists":  {"stat": "ast",  "col": "AST"},
    "player_threes":   {"stat": "fg3m", "col": "FG3M"},
    "player_steals":   {"stat": "stl",  "col": "STL"},
    "player_blocks":   {"stat": "blk",  "col": "BLK"},
}

# Max events per date to limit spending
MAX_EVENTS_PER_DATE = 5

# Hard cap: task start budget + 1500
_BUDGET_AT_START: Optional[int] = None
TASK_BUDGET_CAP: Optional[int] = None  # set after reading start

# ─── player resolver ──────────────────────────────────────────────────────────

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


_NAME2PID: Dict[str, Optional[int]] = {}


def _resolve_player_id(name: str) -> Optional[int]:
    if name in _NAME2PID:
        return _NAME2PID[name]
    cands = _players_index()
    if not cands:
        _NAME2PID[name] = None
        return None
    needle = _strip_accents(name).lower().strip()
    for p in cands:
        if _strip_accents(p["full_name"]).lower() == needle:
            _NAME2PID[name] = int(p["id"])
            return _NAME2PID[name]
    for p in cands:
        if needle in _strip_accents(p["full_name"]).lower():
            _NAME2PID[name] = int(p["id"])
            return _NAME2PID[name]
    if " " not in needle:
        for p in cands:
            ln = _strip_accents(p["full_name"]).lower().split()[-1]
            if ln == needle:
                _NAME2PID[name] = int(p["id"])
                return _NAME2PID[name]
    _NAME2PID[name] = None
    return None


# ─── gamelog loader ───────────────────────────────────────────────────────────

def _parse_game_date(raw: str) -> Optional[date_type]:
    s = str(raw).strip()
    for fmt in ("%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except Exception:
        pass
    return None


_GAMELOG_CACHE: Dict[Tuple[int, str], List[dict]] = {}


def _prior_season(s: str) -> str:
    try:
        start = int(s.split("-")[0])
        return f"{start-1}-{str(start)[-2:]}"
    except Exception:
        return s


def _season_for_date(d: date_type) -> str:
    if d.month >= 10:
        start = d.year
    else:
        start = d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _load_gamelog(player_id: int, season: str) -> List[dict]:
    key = (player_id, season)
    if key in _GAMELOG_CACHE:
        return _GAMELOG_CACHE[key]
    rows: List[dict] = []
    for try_season in (season, _prior_season(season)):
        p = GAMELOG_DIR / f"gamelog_{player_id}_{try_season}.json"
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    rows.extend(data)
            except Exception:
                pass
    _GAMELOG_CACHE[key] = rows
    return rows


def _game_row_for_player_date(
    player_id: int, target_date: date_type, stat_col: str
) -> Optional[dict]:
    season = _season_for_date(target_date)
    rows = _load_gamelog(player_id, season)
    best: Optional[dict] = None
    best_delta: int = 999
    for r in rows:
        gd = _parse_game_date(str(r.get("GAME_DATE", "")))
        if gd is None:
            continue
        delta = abs((gd - target_date).days)
        if delta <= 1 and delta < best_delta:
            best_delta = delta
            best = r
    if best is None:
        return None
    # Verify the stat column exists
    if best.get(stat_col) is None:
        return None
    return best


# ─── odds parser ──────────────────────────────────────────────────────────────

def _parse_outcomes(bookmakers: List[dict]) -> Dict[str, Dict[str, List]]:
    per_player: Dict[str, Dict[str, List]] = defaultdict(
        lambda: {"point": [], "over_price": [], "under_price": []}
    )
    for bk in bookmakers:
        for mkt in bk.get("markets", []):
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
    over_p = statistics.median(pdata["over_price"]) if pdata["over_price"] else -110
    under_p = statistics.median(pdata["under_price"]) if pdata["under_price"] else -110
    return round(median_point, 1), int(over_p), int(under_p)


# ─── budget helpers ───────────────────────────────────────────────────────────

def _used() -> int:
    return int(get_budget().get("used_units", 0))


def _over_cap() -> bool:
    return _used() >= TASK_BUDGET_CAP  # type: ignore[operator]


# ─── main fetch ───────────────────────────────────────────────────────────────

def fetch_all_dates() -> List[Dict[str, Any]]:
    global _BUDGET_AT_START, TASK_BUDGET_CAP

    _BUDGET_AT_START = _used()
    TASK_BUDGET_CAP = _BUDGET_AT_START + 1500
    print(f"\n{'='*70}")
    print(f"  Iter 14a — 2025-26 RS Closing Lines Backfill")
    print(f"  Budget start: {_BUDGET_AT_START} | cap: {TASK_BUDGET_CAP} | max: 3000")
    print(f"  Dates: {len(RS_DATES)} | Markets: {len(MARKETS)}")
    print(f"{'='*70}\n")

    all_rows: List[Dict[str, Any]] = []
    date_summary: List[Dict] = []

    for snap_ts in RS_DATES:
        date_str = snap_ts[:10]  # e.g. "2025-10-28"
        print(f"\n{'─'*60}")
        print(f"  Date: {date_str}  (snap={snap_ts})")

        if _over_cap():
            print(f"  ABORT: budget cap reached ({_used()} >= {TASK_BUDGET_CAP})")
            break

        # Step 1: list_historical_events (1 unit, cache-able)
        try:
            ev_data = list_historical_events(snap_ts)
        except BudgetExceeded:
            print(f"  ABORT: BudgetExceeded on list_historical_events")
            break
        except Exception as e:
            print(f"  ERROR listing events: {e}")
            date_summary.append({"date": date_str, "events_attempted": 0, "rows": 0, "error": str(e)})
            continue

        print(f"  Budget after event list: {_used()}")

        # Extract event list
        if isinstance(ev_data, dict):
            events = ev_data.get("data", [])
        elif isinstance(ev_data, list):
            events = ev_data
        else:
            events = []

        print(f"  Events from API: {len(events)}")

        # Step 2: filter to events that start AFTER snap_ts AND within 6 hours
        snap_dt = datetime.fromisoformat(snap_ts.replace("Z", "+00:00"))
        snap_dt_utc = snap_dt.replace(tzinfo=timezone.utc) if snap_dt.tzinfo is None else snap_dt

        eligible = []
        for ev in events:
            ct_raw = ev.get("commence_time", "")
            try:
                ct = datetime.fromisoformat(str(ct_raw).replace("Z", "+00:00"))
                ct = ct.replace(tzinfo=timezone.utc) if ct.tzinfo is None else ct
            except Exception:
                continue
            delta_h = (ct - snap_dt_utc).total_seconds() / 3600
            if 0 < delta_h < 6:
                eligible.append((ev, ct))

        if not eligible:
            print(f"  No eligible events (all outside 0-6h window)")
            # Try a wider window: any game on same date
            for ev in events:
                ct_raw = ev.get("commence_time", "")
                try:
                    ct = datetime.fromisoformat(str(ct_raw).replace("Z", "+00:00"))
                    ct = ct.replace(tzinfo=timezone.utc) if ct.tzinfo is None else ct
                except Exception:
                    continue
                if ct.strftime("%Y-%m-%d") == date_str:
                    eligible.append((ev, ct))
            print(f"  Widened to same-date: {len(eligible)} events")

        # Step 3: pick up to MAX_EVENTS_PER_DATE with LATEST commence_time
        eligible.sort(key=lambda x: x[1], reverse=True)
        selected = eligible[:MAX_EVENTS_PER_DATE]
        print(f"  Selected {len(selected)} events for fetching")

        date_rows = 0
        events_attempted = 0

        for ev, ct in selected:
            ev_id = ev.get("id", "")
            home = ev.get("home_team", "")
            away = ev.get("away_team", "")
            game_date_str = ct.strftime("%Y-%m-%d")
            events_attempted += 1

            print(f"    ev={ev_id[:16]}  {away}@{home}  {game_date_str}")

            if _over_cap():
                print(f"  ABORT: budget cap mid-date ({_used()} >= {TASK_BUDGET_CAP})")
                break

            # Step 4: fetch all 6 markets
            for market in MARKETS:
                if _over_cap():
                    print(f"  ABORT: budget cap mid-market")
                    break

                try:
                    odds_data = fetch_historical_event_odds(ev_id, snap_ts, market)
                except BudgetExceeded:
                    print(f"      BUDGET_EXCEEDED on {market}")
                    break
                except Exception as e:
                    print(f"      ERROR {market}: {e}")
                    continue

                print(f"      {market}: budget now={_used()}")

                # Extract bookmakers
                if isinstance(odds_data, dict):
                    inner = odds_data.get("data", odds_data)
                    if isinstance(inner, list) and inner:
                        inner = inner[0]
                    bookmakers = inner.get("bookmakers", []) if isinstance(inner, dict) else []
                elif isinstance(odds_data, list) and odds_data:
                    bookmakers = odds_data[0].get("bookmakers", []) if isinstance(odds_data[0], dict) else []
                else:
                    bookmakers = []

                if not bookmakers:
                    print(f"      {market}: no bookmakers")
                    continue

                meta = STAT_META[market]
                stat_code = meta["stat"]
                stat_col = meta["col"]

                try:
                    game_date = datetime.strptime(game_date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue

                per_player = _parse_outcomes(bookmakers)

                for player_name, pdata in per_player.items():
                    if not pdata["point"]:
                        continue

                    pid = _resolve_player_id(player_name)
                    if pid is None:
                        continue

                    median_point, over_price, under_price = _consensus(pdata)
                    if median_point <= 0:
                        continue

                    game_row = _game_row_for_player_date(pid, game_date, stat_col)
                    if game_row is None:
                        continue

                    actual_raw = game_row.get(stat_col)
                    try:
                        actual_val = float(actual_raw)
                    except (TypeError, ValueError):
                        continue

                    # Venue from MATCHUP
                    matchup = str(game_row.get("MATCHUP", ""))
                    if " vs. " in matchup:
                        opp_abbrev = matchup.split(" vs. ")[1].strip()
                        venue = "home"
                    elif " @ " in matchup:
                        opp_abbrev = matchup.split(" @ ")[1].strip()
                        venue = "away"
                    else:
                        opp_abbrev = away[:3].upper()
                        venue = "home"

                    all_rows.append({
                        "date": game_date_str,
                        "player": player_name,
                        "opp": opp_abbrev,
                        "venue": venue,
                        "stat": stat_code,
                        "closing_line": median_point,
                        "over_odds": over_price,
                        "under_odds": under_price,
                        "actual_value": actual_val,
                        "season": "2025-26",
                    })
                    date_rows += 1

        date_summary.append({
            "date": date_str,
            "events_attempted": events_attempted,
            "rows": date_rows,
        })
        print(f"  Date {date_str}: {date_rows} rows | budget={_used()}")

    return all_rows, date_summary


def write_csv(rows: List[Dict[str, Any]]) -> None:
    # Dedup: (date, player, stat)
    seen = set()
    deduped = []
    for r in rows:
        key = (r["date"], r["player"], r["stat"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    print(f"\n  Writing {len(deduped)} rows (deduped from {len(rows)}) -> {OUT_CSV}")
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANONICAL_COLS)
        writer.writeheader()
        for row in deduped:
            writer.writerow({c: row.get(c, "") for c in CANONICAL_COLS})

    # Per-stat count
    per_stat: Dict[str, int] = defaultdict(int)
    per_date: Dict[str, int] = defaultdict(int)
    for r in deduped:
        per_stat[r["stat"]] += 1
        per_date[r["date"]] += 1

    print("\n  Rows per stat:")
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk"]:
        print(f"    {stat}: {per_stat.get(stat, 0)}")

    print("\n  Rows per date:")
    for d in sorted(per_date):
        print(f"    {d}: {per_date[d]}")

    return deduped, per_stat


def print_date_table(date_summary: List[Dict]) -> None:
    print("\n  Per-date summary:")
    print(f"  {'Date':<12} {'Events':<8} {'Rows':<6}")
    print(f"  {'-'*12} {'-'*8} {'-'*6}")
    for s in date_summary:
        err = s.get("error", "")
        print(f"  {s['date']:<12} {s['events_attempted']:<8} {s['rows']:<6} {err}")


if __name__ == "__main__":
    rows, date_summary = fetch_all_dates()
    deduped, per_stat = write_csv(rows)
    print_date_table(date_summary)

    final_budget = get_budget()
    used = final_budget.get("used_units", 0)
    print(f"\n  Final budget: {used} / {final_budget.get('max_units', 3000)}")
    print(f"  Units spent this task: {used - _BUDGET_AT_START}")
    print(f"  Total rows: {len(deduped)}")
