"""fetch_rs_closing_lines_reb_ast.py — Iteration 10b.

Backfill 2024-25 regular-season closing lines for REB + AST using the
same 4 game-nights that already have PTS data (from commit 5650620f).

Strategy:
  - Event lists for the 4 RS dates are already cached → FREE (0 units).
  - Fetch player_rebounds + player_assists for top events with bk>0 from PTS.
  - Hard cap: used_units must stay <= 456 (256 start + 200 task cap).
  - Idempotent: cache makes re-runs free for already-fetched events.

Writes to: data/external/historical_lines/regular_season_2024_25_oddsapi.csv
  (appends REB + AST rows to the existing PTS-only file — schema has a
  `stat` column that already supports multiple stats.)
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, date as date_type
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from src.data.odds_api_client import (  # noqa: E402
    fetch_historical_event_odds,
    get_budget,
    BudgetExceeded,
)

OUT_CSV = (PROJECT_DIR / "data" / "external" / "historical_lines"
           / "regular_season_2024_25_oddsapi.csv")
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

CANONICAL_COLS = ["date", "player", "opp", "venue", "stat", "closing_line",
                  "over_odds", "under_odds", "actual_value"]

GAMELOG_DIR = PROJECT_DIR / "data" / "nba"

# Hard budget cap: task start=256, allow 200 more → stop at 456
BUDGET_CAP = 456

# RS dates we have event caches for
RS_DATES = {"2024-12-20", "2025-01-25", "2025-02-28", "2025-04-05"}

# Markets to fetch this run (skip pts — already have it)
MARKETS_TO_FETCH = ["player_rebounds", "player_assists"]

# Events with confirmed bookmakers (bk>0 from PTS cache analysis).
# snapshot_ts matches the event-list cache timestamp (T01:30:00Z pattern) so
# the API sees the same pre-tip window that returned bookmaker data for PTS.
# 10 events × 2 markets × 10 units = 200 units
# (Jan-25 event 178af5 already fetched at T12:00:00Z → cache hit → 0 new units)
SELECTED_EVENTS: List[Tuple[str, str, str]] = [
    # (date, event_id, snapshot_iso)
    ("2024-12-20", "1c742df7f4aebc9328c3824455b24eee", "2024-12-20T01:30:00Z"),
    ("2024-12-20", "5fd5e867bfeef8ce745416d8749be6e6", "2024-12-20T01:30:00Z"),
    ("2024-12-20", "69b2a23ca9e715f8b441c297d40f2028", "2024-12-20T01:30:00Z"),
    ("2025-01-25", "178af5284f2a47d4e8b7771bebab5da9", "2025-01-25T12:00:00Z"),  # already cached
    ("2025-02-28", "742d9eb489ac515af157e07c25047963", "2025-02-28T01:30:00Z"),
    ("2025-02-28", "b4df207df7266e383550fff09f779ad4", "2025-02-28T01:30:00Z"),
    ("2025-02-28", "1f2ae5bf11e887f1358d1f4bfaefeeee", "2025-02-28T01:30:00Z"),
    ("2025-04-05", "f1b09e8ad2a0b44a3cb893a048655a3b", "2025-04-05T01:30:00Z"),
    ("2025-04-05", "8b3771336f4f2f29a315e91f71496582", "2025-04-05T01:30:00Z"),
    ("2025-04-05", "dd7cec46d65fbdcee6b9e8cbb9da17e8", "2025-04-05T01:30:00Z"),
]

# Stat map: API market -> canonical stat code + gamelog column
STAT_META: Dict[str, Dict[str, str]] = {
    "player_rebounds": {"stat": "reb", "col": "REB"},
    "player_assists":  {"stat": "ast", "col": "AST"},
}


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
    if d.month >= 10:
        start = d.year
    else:
        start = d.year - 1
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


def _game_row_for_player_date(player_id: int, target_date: date_type) -> Optional[dict]:
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
    return best


# ─── parse bookmakers ─────────────────────────────────────────────────────────

def _parse_outcomes_for_market(bookmakers: List[dict], market_key: str) -> Dict[str, Dict[str, List]]:
    """Return {player_name: {point:[], over_price:[], under_price:[]}} for one market."""
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
    over_p = statistics.median(pdata["over_price"]) if pdata["over_price"] else -110
    under_p = statistics.median(pdata["under_price"]) if pdata["under_price"] else -110
    return round(median_point, 1), int(over_p), int(under_p)


# ─── existing rows loader ─────────────────────────────────────────────────────

def _load_existing_rows() -> List[Dict]:
    """Read existing CSV rows (PTS already written)."""
    if not OUT_CSV.exists():
        return []
    try:
        with open(OUT_CSV, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except Exception:
        return []


def _dedup_key(row: Dict) -> Tuple[str, str, str, str]:
    return (row.get("date", ""), row.get("player", "").lower().strip(),
            row.get("stat", ""), str(row.get("closing_line", "")))


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    budget = get_budget()
    print("\n" + "=" * 70)
    print("  Iter 10b — Regular-Season REB + AST Closing Lines Backfill")
    print(f"  budget start: {budget.get('used_units')}/{budget.get('max_units')} "
          f"(cap at {BUDGET_CAP})")
    print("=" * 70)

    # Load existing rows (PTS already there)
    existing_rows = _load_existing_rows()
    existing_keys = {_dedup_key(r) for r in existing_rows}
    new_rows: List[Dict[str, Any]] = []

    # Name → player_id cache
    name2pid: Dict[str, Optional[int]] = {}

    # Per-date/event/market counters
    per_date_counters: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"events_fetched": 0, "ast_rows": 0, "reb_rows": 0, "skipped": 0}
    )

    total_fetches = 0
    total_api_cost = 0

    for date_str, event_id, snapshot_iso in SELECTED_EVENTS:
        print(f"\n  [{date_str}] event={event_id[:20]}... snapshot={snapshot_iso}")

        event_new_rows: List[Dict[str, Any]] = []
        any_data = False

        for market_key in MARKETS_TO_FETCH:
            # Budget gate
            budget_now = get_budget()
            used = int(budget_now.get("used_units", 0))
            if used >= BUDGET_CAP:
                print(f"  !! BUDGET CAP REACHED ({used}/{BUDGET_CAP}) — aborting")
                break

            meta = STAT_META[market_key]
            stat_code = meta["stat"]
            gamelog_col = meta["col"]

            print(f"    Fetching {market_key}... ", end="", flush=True)
            try:
                payload = fetch_historical_event_odds(
                    event_id=event_id,
                    date=snapshot_iso,   # use exact snapshot timestamp matching event list
                    market=market_key,
                    region="us",
                )
                total_fetches += 1
                total_api_cost += 10
            except BudgetExceeded as e:
                print(f"BUDGET_EXCEEDED: {e}")
                break
            except Exception as e:
                print(f"ERROR: {e}")
                continue

            budget_after = get_budget()
            print(f"budget={budget_after.get('used_units')}/{budget_after.get('max_units')}")

            # Parse payload
            inner = payload.get("data", payload) if isinstance(payload, dict) else payload
            if isinstance(inner, list):
                inner = inner[0] if inner else {}
            bookmakers = inner.get("bookmakers", []) if isinstance(inner, dict) else []
            home_team = inner.get("home_team", "") if isinstance(inner, dict) else ""
            away_team = inner.get("away_team", "") if isinstance(inner, dict) else ""
            commence_raw = (inner.get("commence_time", date_str)
                            if isinstance(inner, dict) else date_str)
            game_date_str = str(commence_raw)[:10]

            print(f"      bk={len(bookmakers)}  {away_team[:20]}@{home_team[:20]}")

            if not bookmakers:
                per_date_counters[date_str]["skipped"] += 1
                continue

            any_data = True
            try:
                target_date = datetime.strptime(game_date_str, "%Y-%m-%d").date()
            except Exception:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

            per_player = _parse_outcomes_for_market(bookmakers, market_key)
            rows_this_market = 0

            for player_name, pdata in per_player.items():
                if not pdata["point"]:
                    continue

                # Resolve player id
                if player_name not in name2pid:
                    name2pid[player_name] = _resolve_player_id(player_name)
                pid = name2pid[player_name]
                if pid is None:
                    continue

                median_point, over_price, under_price = _consensus(pdata)
                if median_point <= 0:
                    continue

                # Join gamelog for actual stat value
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

                # Venue / opponent
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

                row: Dict[str, Any] = {
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
                dk = _dedup_key(row)
                if dk not in existing_keys:
                    existing_keys.add(dk)
                    event_new_rows.append(row)
                    rows_this_market += 1

                    if stat_code == "ast":
                        per_date_counters[date_str]["ast_rows"] += 1
                    elif stat_code == "reb":
                        per_date_counters[date_str]["reb_rows"] += 1

            print(f"      {stat_code}: {rows_this_market} rows added")

        if any_data:
            per_date_counters[date_str]["events_fetched"] += 1
        new_rows.extend(event_new_rows)

        # Final budget check after each event pair
        budget_now = get_budget()
        if int(budget_now.get("used_units", 0)) >= BUDGET_CAP:
            print(f"\n  !! BUDGET CAP REACHED — stopping event loop")
            break

    # ─── write CSV ────────────────────────────────────────────────────────────
    all_rows = existing_rows + new_rows
    print(f"\n  Writing {len(all_rows)} total rows ({len(existing_rows)} existing + "
          f"{len(new_rows)} new) -> {OUT_CSV}")
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANONICAL_COLS)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({c: row.get(c, "") for c in CANONICAL_COLS})

    # ─── report ───────────────────────────────────────────────────────────────
    final_budget = get_budget()
    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)

    total_ast = sum(v["ast_rows"] for v in per_date_counters.values())
    total_reb = sum(v["reb_rows"] for v in per_date_counters.values())

    print(f"\n  {'Date':<15} {'Events':>8} {'AST':>6} {'REB':>6}")
    print(f"  {'-'*15} {'-'*8} {'-'*6} {'-'*6}")
    for date_str in sorted(per_date_counters):
        c = per_date_counters[date_str]
        print(f"  {date_str:<15} {c['events_fetched']:>8} "
              f"{c['ast_rows']:>6} {c['reb_rows']:>6}")
    print(f"  {'TOTAL':<15} {sum(c['events_fetched'] for c in per_date_counters.values()):>8} "
          f"{total_ast:>6} {total_reb:>6}")

    print(f"\n  Total new CSV rows: AST={total_ast}, REB={total_reb}")
    print(f"  Total CSV rows (all stats): {len(all_rows)}")
    print(f"  API fetches made: {total_fetches} ({total_api_cost} units)")
    print(f"  Final budget: {final_budget.get('used_units')}/{final_budget.get('max_units')}")

    # Per-stat breakdown in final CSV
    stat_counts: Dict[str, int] = defaultdict(int)
    for row in all_rows:
        stat_counts[str(row.get("stat", "?"))] += 1
    print(f"\n  Rows by stat: {dict(sorted(stat_counts.items()))}")

    return total_ast, total_reb, final_budget


if __name__ == "__main__":
    main()
