"""fetch_rs_closing_lines_expansive_iter35.py — Iter 35: Expansive 2025-26 backfill.

Fetches historical event odds for 25 NEW dates (all 2025-26 season — RS + playoffs)
not covered by previous fetches, and APPENDS to:
    data/external/historical_lines/regular_season_2025_26_oddsapi.csv  (RS dates)
    data/external/historical_lines/playoffs_2025_26_oddsapi.csv        (playoff dates)

Budget: Hard cap = start + 5,000 units (max ~8,500 total).
        Realistic: ~120-150 units/date * 25 dates = ~3,750.
        Headroom: ~1,250 units.

Idempotent: deduplicates on (date, player, stat) before writing.
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

# ─── output files ─────────────────────────────────────────────────────────────
RS_CSV = (PROJECT_DIR / "data" / "external" / "historical_lines"
          / "regular_season_2025_26_oddsapi.csv")
PO_CSV = (PROJECT_DIR / "data" / "external" / "historical_lines"
          / "playoffs_2025_26_oddsapi.csv")
RS_CSV.parent.mkdir(parents=True, exist_ok=True)

CANONICAL_COLS = [
    "date", "player", "opp", "venue", "stat",
    "closing_line", "over_odds", "under_odds", "actual_value", "season",
]

GAMELOG_DIR = PROJECT_DIR / "data" / "nba"

# ─── 25 new dates, not in existing coverage ──────────────────────────────────
# RS dates (Oct 2025 – Apr 13 2026)
RS_NEW_DATES: List[str] = [
    "2025-11-03T01:30:00Z",
    "2025-11-19T01:30:00Z",
    "2025-12-03T01:30:00Z",
    "2025-12-16T01:30:00Z",
    "2026-01-02T01:30:00Z",
    "2026-01-14T01:30:00Z",
    "2026-01-28T01:30:00Z",
    "2026-02-12T01:30:00Z",
    "2026-02-19T01:30:00Z",
    "2026-02-25T01:30:00Z",
    "2026-03-03T01:30:00Z",
    "2026-03-17T01:30:00Z",
    "2026-03-31T01:30:00Z",
    "2026-04-03T01:30:00Z",
    "2026-04-14T01:30:00Z",   # last week of RS
]

# Playoff dates (Apr 18 – May 26 2026)
PO_NEW_DATES: List[str] = [
    "2026-04-19T23:30:00Z",
    "2026-04-24T23:30:00Z",
    "2026-04-29T23:30:00Z",
    "2026-05-01T23:30:00Z",
    "2026-05-08T23:30:00Z",
    "2026-05-14T23:30:00Z",
    "2026-05-17T23:30:00Z",
    "2026-05-19T23:30:00Z",
    "2026-05-21T23:30:00Z",
    "2026-05-24T23:30:00Z",
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

STAT_META: Dict[str, Dict[str, str]] = {
    "player_points":   {"stat": "pts",  "col": "PTS"},
    "player_rebounds": {"stat": "reb",  "col": "REB"},
    "player_assists":  {"stat": "ast",  "col": "AST"},
    "player_threes":   {"stat": "fg3m", "col": "FG3M"},
    "player_steals":   {"stat": "stl",  "col": "STL"},
    "player_blocks":   {"stat": "blk",  "col": "BLK"},
}

MAX_EVENTS_PER_DATE = 5

# Hard cap: set after reading start budget
_BUDGET_AT_START: Optional[int] = None
TASK_BUDGET_CAP: Optional[int] = None   # start + 5000

# ─── player resolver ──────────────────────────────────────────────────────────
def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


_PLAYERS_INDEX: Optional[List[dict]] = None


def _players_index() -> List[dict]:
    global _PLAYERS_INDEX
    if _PLAYERS_INDEX is None:
        try:
            from nba_api.stats.static import players
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


# ─── fetch one date ───────────────────────────────────────────────────────────
def fetch_date(
    snap_ts: str,
    date_str: str,
    existing_keys: set,
) -> Tuple[List[Dict], Dict]:
    """Fetch one snapshot date. Returns (new_rows, summary_dict)."""
    print(f"\n{'─'*60}")
    print(f"  Date: {date_str}  (snap={snap_ts})")

    if _over_cap():
        print(f"  ABORT: budget cap ({_used()} >= {TASK_BUDGET_CAP})")
        return [], {"date": date_str, "events_attempted": 0, "rows": 0, "skipped": "cap"}

    # Step 1: list events
    try:
        ev_data = list_historical_events(snap_ts)
    except BudgetExceeded:
        print(f"  ABORT: BudgetExceeded on list_historical_events")
        return [], {"date": date_str, "events_attempted": 0, "rows": 0, "skipped": "budget"}
    except Exception as e:
        print(f"  ERROR listing events: {e}")
        return [], {"date": date_str, "events_attempted": 0, "rows": 0, "error": str(e)}

    print(f"  Budget after event list: {_used()}")

    # Extract events
    if isinstance(ev_data, dict):
        events = ev_data.get("data", [])
    elif isinstance(ev_data, list):
        events = ev_data
    else:
        events = []

    print(f"  Events from API: {len(events)}")

    # Filter by time window
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
        print(f"  No eligible events in 0-6h window, widening to same-date")
        for ev in events:
            ct_raw = ev.get("commence_time", "")
            try:
                ct = datetime.fromisoformat(str(ct_raw).replace("Z", "+00:00"))
                ct = ct.replace(tzinfo=timezone.utc) if ct.tzinfo is None else ct
            except Exception:
                continue
            if ct.strftime("%Y-%m-%d") == date_str:
                eligible.append((ev, ct))
        print(f"  Same-date eligible: {len(eligible)}")

    # Pick top MAX_EVENTS_PER_DATE (latest commence_time first)
    eligible.sort(key=lambda x: x[1], reverse=True)
    selected = eligible[:MAX_EVENTS_PER_DATE]
    print(f"  Selected {len(selected)} events for fetching")

    new_rows: List[Dict] = []
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

                # Venue
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

                dedup_key = (game_date_str, player_name, stat_code)
                if dedup_key in existing_keys:
                    continue

                new_rows.append({
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
                existing_keys.add(dedup_key)

    print(f"  Date {date_str}: {len(new_rows)} new rows | budget={_used()}")
    return new_rows, {
        "date": date_str,
        "events_attempted": events_attempted,
        "rows": len(new_rows),
    }


# ─── CSV read/write helpers ───────────────────────────────────────────────────
def load_existing_csv(path: Path) -> Tuple[List[Dict], set]:
    """Load existing CSV rows and return (rows, dedup_keys)."""
    if not path.exists():
        return [], set()
    rows = []
    keys = set()
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append(r)
            keys.add((r["date"], r["player"], r["stat"]))
    return rows, keys


def append_to_csv(path: Path, new_rows: List[Dict]) -> None:
    """Append rows to CSV (write header if file is new)."""
    write_header = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANONICAL_COLS)
        if write_header:
            writer.writeheader()
        for row in new_rows:
            writer.writerow({c: row.get(c, "") for c in CANONICAL_COLS})


# ─── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    global _BUDGET_AT_START, TASK_BUDGET_CAP

    _BUDGET_AT_START = _used()
    TASK_BUDGET_CAP = _BUDGET_AT_START + 5000
    print(f"\n{'='*70}")
    print(f"  Iter 35 — Expansive 2025-26 Backfill (+25 dates)")
    print(f"  Budget start: {_BUDGET_AT_START} | task cap: {TASK_BUDGET_CAP} | max: 20000")
    print(f"  RS dates: {len(RS_NEW_DATES)} | PO dates: {len(PO_NEW_DATES)}")
    print(f"{'='*70}\n")

    # Load existing rows (to avoid duplicates)
    rs_existing, rs_keys = load_existing_csv(RS_CSV)
    po_existing, po_keys = load_existing_csv(PO_CSV)
    print(f"  Existing RS rows: {len(rs_existing)} | PO rows: {len(po_existing)}")

    all_summary = []
    total_rs_new = 0
    total_po_new = 0

    # ── Regular Season dates ──────────────────────────────────────────────────
    rs_batch: List[Dict] = []
    for snap_ts in RS_NEW_DATES:
        date_str = snap_ts[:10]
        if _over_cap():
            print(f"\n  GLOBAL CAP REACHED ({_used()} >= {TASK_BUDGET_CAP}). Stopping.")
            break
        new_rows, summary = fetch_date(snap_ts, date_str, rs_keys)
        rs_batch.extend(new_rows)
        all_summary.append({**summary, "file": "RS"})
        total_rs_new += summary["rows"]

    if rs_batch:
        append_to_csv(RS_CSV, rs_batch)
        print(f"\n  Appended {len(rs_batch)} new rows to RS CSV")

    # ── Playoff dates ─────────────────────────────────────────────────────────
    po_batch: List[Dict] = []
    for snap_ts in PO_NEW_DATES:
        date_str = snap_ts[:10]
        if _over_cap():
            print(f"\n  GLOBAL CAP REACHED ({_used()} >= {TASK_BUDGET_CAP}). Stopping.")
            break
        new_rows, summary = fetch_date(snap_ts, date_str, po_keys)
        po_batch.extend(new_rows)
        all_summary.append({**summary, "file": "PO"})
        total_po_new += summary["rows"]

    if po_batch:
        append_to_csv(PO_CSV, po_batch)
        print(f"\n  Appended {len(po_batch)} new rows to PO CSV")

    # ── Summary table ─────────────────────────────────────────────────────────
    final_used = _used()
    units_spent = final_used - _BUDGET_AT_START

    print(f"\n{'='*70}")
    print(f"  PER-DATE SUMMARY")
    print(f"  {'Date':<12} {'File':<4} {'Events':<8} {'Rows':<6} {'Note'}")
    print(f"  {'-'*12} {'-'*4} {'-'*8} {'-'*6} {'-'*20}")
    for s in all_summary:
        note = s.get("error", s.get("skipped", ""))
        print(f"  {s['date']:<12} {s.get('file',''):<4} {s['events_attempted']:<8} {s['rows']:<6} {note}")

    # Final totals per stat
    all_new = rs_batch + po_batch
    per_stat: Dict[str, int] = defaultdict(int)
    for r in all_new:
        per_stat[r["stat"]] += 1

    print(f"\n  NEW ROWS BY STAT:")
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk"]:
        print(f"    {stat}: +{per_stat.get(stat, 0)}")

    rs_final_total = len(rs_existing) + total_rs_new
    po_final_total = len(po_existing) + total_po_new
    total_before = len(rs_existing) + len(po_existing)
    total_after = rs_final_total + po_final_total

    print(f"\n  CSV GROWTH:")
    print(f"    RS CSV:  {len(rs_existing)} -> {rs_final_total} (+{total_rs_new})")
    print(f"    PO CSV:  {len(po_existing)} -> {po_final_total} (+{total_po_new})")
    print(f"    Combined: {total_before} -> {total_after} (+{total_after - total_before})")

    print(f"\n  BUDGET:")
    print(f"    Start:    {_BUDGET_AT_START}")
    print(f"    Used:     {final_used}")
    print(f"    Spent:    {units_spent}")
    print(f"    Remaining: {20000 - final_used}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
