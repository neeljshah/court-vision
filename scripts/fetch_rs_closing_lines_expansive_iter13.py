"""fetch_rs_closing_lines_expansive_iter13.py -- Iter 13: expansive RS backfill.

8 new game-nights across the 2024-25 regular season, all 6 player-prop markets,
up to 6 events per date.  MAX budget cap: 2800 used_units.

Writes APPENDS rows to:
  data/external/historical_lines/regular_season_2024_25_oddsapi.csv

Markets: player_points, player_rebounds, player_assists, player_threes,
         player_steals, player_blocks

Stat mapping:
  player_points  -> pts  (gamelog col: PTS)
  player_rebounds -> reb (gamelog col: REB)
  player_assists -> ast  (gamelog col: AST)
  player_threes  -> fg3m (gamelog col: FG3M)
  player_steals  -> stl  (gamelog col: STL)
  player_blocks  -> blk  (gamelog col: BLK)
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone, date as date_type
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from src.data.odds_api_client import (  # noqa: E402
    list_historical_events,
    fetch_historical_event_odds,
    get_budget,
    BudgetExceeded,
)

# --- config -------------------------------------------------------------------

OUT_CSV = (PROJECT_DIR / "data" / "external" / "historical_lines"
           / "regular_season_2024_25_oddsapi.csv")
GAMELOG_DIR = PROJECT_DIR / "data" / "nba"
BUDGET_CAP = 2800         # hard stop before this value
MAX_EVENTS_PER_DATE = 6
MAX_FUTURE_HOURS = 6.0    # only events starting within 6h of snapshot

# 8 new game-nights (not overlapping existing 4 dates)
NEW_DATES = [
    "2024-11-15T01:30:00Z",
    "2024-12-05T01:30:00Z",
    "2024-12-28T01:30:00Z",
    "2025-01-08T01:30:00Z",
    "2025-02-05T01:30:00Z",
    "2025-02-15T01:30:00Z",
    "2025-03-08T01:30:00Z",
    "2025-03-25T01:30:00Z",
]

MARKETS = [
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_threes",
    "player_steals",
    "player_blocks",
]

STAT_META: Dict[str, Dict[str, str]] = {
    "player_points":   {"stat": "pts",  "col": "PTS"},
    "player_rebounds": {"stat": "reb",  "col": "REB"},
    "player_assists":  {"stat": "ast",  "col": "AST"},
    "player_threes":   {"stat": "fg3m", "col": "FG3M"},
    "player_steals":   {"stat": "stl",  "col": "STL"},
    "player_blocks":   {"stat": "blk",  "col": "BLK"},
}

CANONICAL_COLS = ["date", "player", "opp", "venue", "stat", "closing_line",
                  "over_odds", "under_odds", "actual_value"]

# --- player / gamelog helpers -------------------------------------------------

def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


_PLAYERS_INDEX: Optional[List[dict]] = None


def _players_index() -> List[dict]:
    global _PLAYERS_INDEX
    if _PLAYERS_INDEX is None:
        try:
            from nba_api.stats.static import players  # noqa
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


def _season_for_date(d: date_type) -> str:
    start = d.year if d.month >= 10 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _prior_season(s: str) -> str:
    try:
        start = int(s.split("-")[0])
        return f"{start-1}-{str(start)[-2:]}"
    except Exception:
        return s


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
    player_id: int,
    target_date: date_type,
) -> Optional[dict]:
    season = _season_for_date(target_date)
    rows = _load_gamelog(player_id, season)
    best: Optional[dict] = None
    best_delta = 999
    for r in rows:
        gd = _parse_game_date(str(r.get("GAME_DATE", "")))
        if gd is None:
            continue
        delta = abs((gd - target_date).days)
        if delta <= 1 and delta < best_delta:
            best_delta = delta
            best = r
    return best


# --- bookmaker parsers ---------------------------------------------------------

def _parse_outcomes(
    bookmakers: List[dict],
) -> Dict[str, Dict[str, List]]:
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


def _consensus(
    pdata: Dict[str, List],
) -> Tuple[float, int, int]:
    median_point = statistics.median(pdata["point"]) if pdata["point"] else 0.0
    over_p = statistics.median(pdata["over_price"]) if pdata["over_price"] else -110
    under_p = statistics.median(pdata["under_price"]) if pdata["under_price"] else -110
    return round(median_point, 1), int(over_p), int(under_p)


# --- dedup helper -------------------------------------------------------------

def _load_existing_keys(csv_path: Path) -> set:
    """Return set of (date, player, stat) keys already in the CSV."""
    keys = set()
    if not csv_path.exists():
        return keys
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            keys.add((row["date"], row["player"], row["stat"]))
    return keys


# --- main ---------------------------------------------------------------------

def main() -> None:
    print("\n" + "=" * 70)
    print("  Iter 13 -- Expansive RS Closing-Line Backfill (8 new dates)")
    print("=" * 70)

    budget = get_budget()
    print(f"  Budget at start: {budget['used_units']}/{budget['max_units']}")

    # Load existing CSV keys for dedup
    existing_keys = _load_existing_keys(OUT_CSV)
    print(f"  Existing rows in CSV: {len(existing_keys)} unique (date,player,stat) keys")

    all_new_rows: List[Dict[str, Any]] = []
    date_summary: List[dict] = []

    for snapshot_ts in NEW_DATES:
        date_str = snapshot_ts[:10]  # "2024-11-15"
        snap_dt = datetime.fromisoformat(snapshot_ts.replace("Z", "+00:00"))

        print(f"\n{'-'*60}")
        print(f"  DATE: {date_str}  (snapshot={snapshot_ts})")

        # -- Step 1: list historical events ----------------------------------
        budget = get_budget()
        if budget["used_units"] >= BUDGET_CAP:
            print(f"  HARD STOP -- budget {budget['used_units']} >= {BUDGET_CAP}")
            break

        try:
            events_resp = list_historical_events(snapshot_ts)
        except BudgetExceeded as e:
            print(f"  [skip date] BudgetExceeded: {e}")
            break
        except Exception as e:
            print(f"  [skip date] list_historical_events error: {e}")
            date_summary.append({
                "date": date_str, "events_attempted": 0,
                "events_with_books": 0, "rows_added": 0, "error": str(e),
            })
            continue

        budget = get_budget()
        print(f"  Budget after list_events: {budget['used_units']}")

        # Parse events list
        if isinstance(events_resp, dict):
            events_data = events_resp.get("data", [])
        else:
            events_data = events_resp or []

        print(f"  Total events in response: {len(events_data)}")

        # Filter: pre-tip within 6 hours of snapshot
        pre_tip = []
        for ev in events_data:
            ct_raw = ev.get("commence_time", "")
            try:
                ct_dt = datetime.fromisoformat(ct_raw.replace("Z", "+00:00"))
            except Exception:
                continue
            delta_h = (ct_dt - snap_dt).total_seconds() / 3600.0
            if 0.0 <= delta_h <= MAX_FUTURE_HOURS:
                pre_tip.append((delta_h, ev))

        # Sort by delta desc (prefer games closest to tip)
        pre_tip.sort(key=lambda x: -x[0])
        selected = pre_tip[:MAX_EVENTS_PER_DATE]
        print(f"  Pre-tip events (0-6h): {len(pre_tip)} -> selected {len(selected)}")
        for dh, ev in selected:
            print(f"    +{dh:.1f}h  {ev.get('away_team','?')[:22]} @ {ev.get('home_team','?')[:22]}  id={ev['id']}")

        date_rows_added = 0
        date_events_with_books = 0

        # -- Step 2: fetch all 6 markets for each selected event -------------
        for _, ev in selected:
            event_id = ev["id"]
            home_team = ev.get("home_team", "")
            away_team = ev.get("away_team", "")
            commence_raw = ev.get("commence_time", date_str)
            game_date_str = str(commence_raw)[:10]

            try:
                target_date = datetime.strptime(game_date_str, "%Y-%m-%d").date()
            except Exception:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

            event_got_books = False

            for market in MARKETS:
                budget = get_budget()
                if budget["used_units"] >= BUDGET_CAP:
                    print(f"  HARD STOP -- budget {budget['used_units']} >= {BUDGET_CAP}")
                    # flush what we have and exit
                    _append_rows(OUT_CSV, all_new_rows, existing_keys)
                    _print_summary(date_summary, all_new_rows, budget)
                    return

                stat_info = STAT_META[market]
                stat_code = stat_info["stat"]
                gamelog_col = stat_info["col"]

                try:
                    odds_resp = fetch_historical_event_odds(
                        event_id, snapshot_ts, market
                    )
                except BudgetExceeded as e:
                    print(f"      [stop] BudgetExceeded on {market}: {e}")
                    _append_rows(OUT_CSV, all_new_rows, existing_keys)
                    _print_summary(date_summary, all_new_rows, get_budget())
                    return
                except Exception as e:
                    print(f"      [skip] {market} fetch error: {e}")
                    continue

                budget = get_budget()
                print(f"    [{market}] budget={budget['used_units']}", end="  ")

                # Unwrap response
                if isinstance(odds_resp, dict):
                    inner = odds_resp.get("data", odds_resp)
                else:
                    inner = odds_resp

                if isinstance(inner, list):
                    inner = inner[0] if inner else {}

                bookmakers = inner.get("bookmakers", []) if isinstance(inner, dict) else []

                if not bookmakers:
                    print("0 bookmakers -> skip")
                    continue

                event_got_books = True
                per_player = _parse_outcomes(bookmakers)
                print(f"bks={len(bookmakers)} players={len(per_player)}", end="  ")

                mkt_rows = 0
                for player_name, pdata in per_player.items():
                    if not pdata["point"]:
                        continue

                    # Dedup check
                    dedup_key = (game_date_str, player_name, stat_code)
                    if dedup_key in existing_keys:
                        continue

                    pid = _resolve_player_id(player_name)
                    if pid is None:
                        continue

                    median_point, over_price, under_price = _consensus(pdata)
                    if median_point <= 0:
                        continue

                    game_row = _game_row_for_player_date(pid, target_date)
                    if game_row is None:
                        continue

                    actual_val = game_row.get(gamelog_col)
                    if actual_val is None:
                        continue
                    try:
                        actual_val = float(actual_val)
                    except (TypeError, ValueError):
                        continue

                    # Venue/opp from gamelog MATCHUP
                    matchup = str(game_row.get("MATCHUP", ""))
                    if " vs. " in matchup:
                        opp_abbrev = matchup.split(" vs. ")[1].strip()
                        venue = "home"
                    elif " @ " in matchup:
                        opp_abbrev = matchup.split(" @ ")[1].strip()
                        venue = "away"
                    else:
                        opp_abbrev = away_team[:3].upper()
                        venue = "home"

                    new_row = {
                        "date": game_date_str,
                        "player": player_name,
                        "opp": opp_abbrev,
                        "venue": venue,
                        "stat": stat_code,
                        "closing_line": median_point,
                        "over_odds": over_price,
                        "under_odds": under_price,
                        "actual_value": actual_val,
                    }
                    all_new_rows.append(new_row)
                    existing_keys.add(dedup_key)
                    mkt_rows += 1
                    date_rows_added += 1

                print(f"rows_added={mkt_rows}")

            if event_got_books:
                date_events_with_books += 1

        date_summary.append({
            "date": date_str,
            "events_attempted": len(selected),
            "events_with_books": date_events_with_books,
            "rows_added": date_rows_added,
            "error": None,
        })

    # -- flush all rows ------------------------------------------------------
    _append_rows(OUT_CSV, all_new_rows, set())  # keys already deduped inline
    _print_summary(date_summary, all_new_rows, get_budget())


def _append_rows(
    csv_path: Path,
    new_rows: List[Dict[str, Any]],
    _unused_keys: set,
) -> None:
    """Append new_rows to the CSV (write header if file missing)."""
    if not new_rows:
        print("\n  [info] No new rows to append.")
        return
    file_exists = csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANONICAL_COLS)
        if not file_exists:
            writer.writeheader()
        for row in new_rows:
            writer.writerow({c: row.get(c, "") for c in CANONICAL_COLS})
    print(f"\n  Appended {len(new_rows)} rows -> {csv_path}")


def _print_summary(
    date_summary: List[dict],
    all_new_rows: List[Dict[str, Any]],
    budget: dict,
) -> None:
    print("\n" + "=" * 70)
    print("  ITER 13 SUMMARY")
    print("=" * 70)
    print(f"\n  Per-date table:")
    print(f"  {'date':<12} {'attempted':>10} {'w_books':>8} {'rows':>6} {'error'}")
    total_rows = 0
    for d in date_summary:
        err = d.get("error") or ""
        print(f"  {d['date']:<12} {d['events_attempted']:>10} {d['events_with_books']:>8} "
              f"{d['rows_added']:>6}  {err[:40]}")
        total_rows += d["rows_added"]

    print(f"\n  Total new rows appended: {total_rows}")
    print(f"  Budget: {budget['used_units']} / {budget['max_units']}")

    # Per-stat summary across new rows
    per_stat = defaultdict(int)
    per_date = defaultdict(int)
    for r in all_new_rows:
        per_stat[r["stat"]] += 1
        per_date[r["date"]] += 1

    print(f"\n  New rows by stat:")
    for s in sorted(per_stat):
        print(f"    {s}: {per_stat[s]}")

    print(f"\n  New rows by date:")
    for d in sorted(per_date):
        print(f"    {d}: {per_date[d]}")


if __name__ == "__main__":
    main()
