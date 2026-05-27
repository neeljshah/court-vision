"""fetch_rs_closing_lines.py — Iteration 6: parse ALL cached event-odds files
and join to actual gamelog PTS to build regular_season_2024_25_oddsapi.csv.

All API data already fetched in the prior run (budget 256/450).
This script ONLY reads from local cache — zero new API calls.

Schema mirrors playoffs_2024_canonical.csv:
    date,player,opp,venue,stat,closing_line,over_odds,under_odds,actual_value
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

from src.data.odds_api_client import get_budget  # noqa: E402

OUT_CSV = (PROJECT_DIR / "data" / "external" / "historical_lines"
           / "regular_season_2024_25_oddsapi.csv")
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

CANONICAL_COLS = ["date", "player", "opp", "venue", "stat", "closing_line",
                  "over_odds", "under_odds", "actual_value"]

GAMELOG_DIR = PROJECT_DIR / "data" / "nba"
EVENT_ODDS_CACHE = PROJECT_DIR / "data" / "cache" / "odds_api" / "historical_event_odds"

# Only include dates from the 4 regular-season snapshot dates
RS_DATE_PREFIXES = {"2024-12-20", "2025-01-25", "2025-02-28", "2025-04-05"}

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
    """Parse gamelog GAME_DATE in any format."""
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


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> Tuple[List[Dict], Dict]:
    budget = get_budget()
    print("\n" + "=" * 70)
    print("  Iteration 6 — Regular-Season PTS Closing Lines")
    print(f"  Reading from cache only. budget_used={budget.get('used_units')}")
    print("=" * 70)

    # Iterate over ALL cached event odds files for our 4 RS dates
    cache_files = sorted(EVENT_ODDS_CACHE.glob("*.json"))
    rs_files = [f for f in cache_files
                if any(f.name.startswith(d) for d in RS_DATE_PREFIXES)]
    print(f"\n  Found {len(rs_files)} RS event-odds cache files")

    all_output_rows: List[Dict[str, Any]] = []
    counters = {
        "events_with_books": 0,
        "events_no_books": 0,
        "player_odds_rows": 0,
        "skipped_no_pid": 0,
        "skipped_zero_line": 0,
        "skipped_no_actual": 0,
        "rows_added": 0,
    }

    # Name cache for resolved player IDs
    name2pid: Dict[str, Optional[int]] = {}

    for cache_file in rs_files:
        raw_date_prefix = cache_file.name[:10]  # "2024-12-20"
        data = json.loads(cache_file.read_text(encoding="utf-8"))

        # Extract inner event dict
        inner = data.get("data", data)
        if isinstance(inner, list):
            inner = inner[0] if inner else {}

        bookmakers = inner.get("bookmakers", []) if isinstance(inner, dict) else []
        home_team = inner.get("home_team", "") if isinstance(inner, dict) else ""
        away_team = inner.get("away_team", "") if isinstance(inner, dict) else ""
        commence_raw = (inner.get("commence_time", raw_date_prefix)
                        if isinstance(inner, dict) else raw_date_prefix)
        game_date_str = str(commence_raw)[:10]

        print(f"\n  {cache_file.name[:55]}  bks={len(bookmakers)}  "
              f"{away_team[:20]}@{home_team[:20]}  game_date={game_date_str}")

        if not bookmakers:
            counters["events_no_books"] += 1
            continue

        counters["events_with_books"] += 1

        try:
            target_date = datetime.strptime(game_date_str, "%Y-%m-%d").date()
        except Exception:
            target_date = datetime.strptime(raw_date_prefix, "%Y-%m-%d").date()

        per_player = _parse_outcomes(bookmakers)
        counters["player_odds_rows"] += len(per_player)

        for player_name, pdata in per_player.items():
            if not pdata["point"]:
                continue

            # Resolve player id (cached per run)
            if player_name not in name2pid:
                name2pid[player_name] = _resolve_player_id(player_name)
            pid = name2pid[player_name]
            if pid is None:
                counters["skipped_no_pid"] += 1
                continue

            median_point, over_price, under_price = _consensus(pdata)
            if median_point <= 0:
                counters["skipped_zero_line"] += 1
                continue

            # Join gamelog for actual PTS
            game_row = _game_row_for_player_date(pid, target_date)
            if game_row is None:
                counters["skipped_no_actual"] += 1
                continue

            actual_pts = game_row.get("PTS")
            if actual_pts is None:
                counters["skipped_no_actual"] += 1
                continue
            try:
                actual_pts = float(actual_pts)
            except (TypeError, ValueError):
                counters["skipped_no_actual"] += 1
                continue

            # Venue / opponent from MATCHUP (e.g. "IND @ SAS" or "SAS vs. IND")
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

            all_output_rows.append({
                "date": game_date_str,
                "player": player_name,
                "opp": opp_abbrev,
                "venue": venue,
                "stat": "pts",
                "closing_line": median_point,
                "over_odds": over_price,
                "under_odds": under_price,
                "actual_value": actual_pts,
            })
            counters["rows_added"] += 1

        print(f"    players_resolved={sum(1 for p in per_player if name2pid.get(p) is not None)}"
              f"  rows_from_event={counters['rows_added']}")

    # ─── write CSV ────────────────────────────────────────────────────────────
    print(f"\n  Writing {len(all_output_rows)} rows -> {OUT_CSV}")
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANONICAL_COLS)
        writer.writeheader()
        for row in all_output_rows:
            writer.writerow({c: row.get(c, "") for c in CANONICAL_COLS})

    # ─── report ───────────────────────────────────────────────────────────────
    print(f"\n  --- Counters ---")
    for k, v in counters.items():
        print(f"    {k}: {v}")

    print(f"\n  --- Sample (first 5 rows) ---")
    print(",".join(CANONICAL_COLS))
    for row in all_output_rows[:5]:
        print(",".join(str(row.get(c, "")) for c in CANONICAL_COLS))

    # Per-date breakdown
    per_date: Dict[str, int] = defaultdict(int)
    for row in all_output_rows:
        per_date[row["date"]] += 1
    print(f"\n  --- Rows per game date ---")
    for d in sorted(per_date):
        print(f"    {d}: {per_date[d]} rows")

    final_budget = get_budget()
    print(f"\n  Final budget: {final_budget.get('used_units')}/{final_budget.get('max_units')} used")
    print(f"  Total CSV rows: {len(all_output_rows)}")
    return all_output_rows, counters


if __name__ == "__main__":
    main()
