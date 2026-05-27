"""settlement.py — Shadow-log settlement engine (overnight build).

Scores every bet the shadow logger captured (passed + blocked) against the
final NBA box-score from cdn.nba.com. Distinct from pnl_ledger settlement —
no bankroll mutation, no UUID bets, just enriching the shadow CSV rows with
realized outcomes.

Public API
----------
fetch_final_boxscore(game_id)          -> dict | None
settle_shadow_log(shadow_csv_path, finals) -> list[dict]
settle_day(date_str, base_dir=None)    -> int
"""
from __future__ import annotations

import csv
import os
import sys
import time
import urllib.error
import urllib.request
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

# Reuse payout math from pnl_ledger — DO NOT reimplement.
from src.betting.pnl_ledger import american_to_payout, _resolve_status  # noqa: E402

SHADOW_DIR = os.path.join(PROJECT_DIR, "data", "shadow")

# CDN endpoint for finalized box scores.
_CDN_URL = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"

# NBA CDN stat key -> shadow-log stat name mapping.
_STAT_MAP: Dict[str, str] = {
    "pts":  "points",
    "reb":  "reboundsTotal",
    "ast":  "assists",
    "fg3m": "threePointersMade",
    "stl":  "steals",
    "blk":  "blocks",
    "tov":  "turnovers",
}

# Settled CSV columns = shadow columns + 4 new ones.
_SHADOW_COLS = [
    "ts", "game_id", "period", "clock_remaining", "player_id", "name",
    "team", "stat", "side", "line", "book", "odds", "model_proj",
    "current_stat", "sigma", "raw_ev", "kelly", "tier", "gate_status",
    "gate_blocked_by", "source",
]
_SETTLED_EXTRA = ["actual_stat", "outcome", "realized_return_$1", "settled_at"]
_SETTLED_COLS  = _SHADOW_COLS + _SETTLED_EXTRA


# --------------------------------------------------------------------------- #
# HTTP helper with one Akamai-retry.                                          #
# --------------------------------------------------------------------------- #
def _fetch_json(url: str, timeout: int = 10) -> Optional[dict]:
    """GET url, parse JSON. Returns None on any error. One retry on 403."""
    headers = {
        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.nba.com/",
    }
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 403 and attempt == 0:
                time.sleep(2.0)   # Akamai edge-throttle: one backoff + retry
                continue
            return None
        except Exception:
            return None
    return None


# --------------------------------------------------------------------------- #
# Box-score fetch.                                                            #
# --------------------------------------------------------------------------- #
def fetch_final_boxscore(game_id: str) -> Optional[Dict]:
    """Fetch cdn.nba.com box score for game_id.

    Returns {(player_id, stat): value} for all players + all 7 tracked stats
    when gameStatus == 3 (final). Returns None if game not final or fetch failed.

    stat keys: pts, reb, ast, fg3m, stl, blk, tov
    """
    url = _CDN_URL.format(game_id=game_id)
    data = _fetch_json(url)
    if data is None:
        return None

    game = data.get("game", {})
    if int(game.get("gameStatus", 0)) != 3:
        return None

    finals: Dict = {}
    for side_key in ("homeTeam", "awayTeam"):
        for player in game.get(side_key, {}).get("players", []):
            pid = str(player.get("personId", ""))
            stats = player.get("statistics", {})
            for shadow_stat, cdn_key in _STAT_MAP.items():
                val = stats.get(cdn_key)
                if val is not None:
                    finals[(pid, shadow_stat)] = float(val)
    return finals


# --------------------------------------------------------------------------- #
# Per-row settlement.                                                         #
# --------------------------------------------------------------------------- #
def _settle_row(row: Dict, finals: Dict) -> Dict:
    """Enrich one shadow row with outcome columns. Returns a new dict."""
    enriched = dict(row)
    now_iso = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")

    pid  = str(row.get("player_id", "")).strip()
    stat = str(row.get("stat", "")).strip().lower()
    side = str(row.get("side", "")).strip().upper()

    actual = finals.get((pid, stat))
    if actual is None:
        enriched.update({
            "actual_stat":        "",
            "outcome":            "no_actual",
            "realized_return_$1": "0.00",
            "settled_at":         now_iso,
        })
        return enriched

    enriched["actual_stat"] = f"{actual:.4f}"
    enriched["settled_at"]  = now_iso

    try:
        line = float(row.get("line", "nan"))
        odds = int(float(row.get("odds", -110) or -110))
    except (ValueError, TypeError):
        enriched.update({
            "outcome":            "no_actual",
            "realized_return_$1": "0.00",
        })
        return enriched

    # Reuse _resolve_status from pnl_ledger (push / won / lost).
    status = _resolve_status(line, side, actual)
    outcome_map = {"won": "hit", "lost": "miss", "push": "push"}
    outcome = outcome_map.get(status, "no_actual")

    if status == "won":
        realized = round(american_to_payout(odds), 4)
    elif status == "lost":
        realized = -1.0
    else:
        realized = 0.0

    enriched.update({
        "outcome":            outcome,
        "realized_return_$1": f"{realized:.4f}",
    })
    return enriched


def settle_shadow_log(shadow_csv_path: str, finals: Dict) -> List[Dict]:
    """Read shadow CSV, attach actual stat + outcome per row.

    Parameters
    ----------
    shadow_csv_path : path to one *_YYYY-MM-DD.csv shadow file
    finals : dict returned by fetch_final_boxscore — {(player_id, stat): value}

    Returns
    -------
    list of enriched row dicts with NEW columns:
        actual_stat, outcome, realized_return_$1, settled_at
    outcome in {hit, miss, push, no_actual}
    realized_return_$1: payout (win), -1 (loss), 0 (push/no_actual)
    """
    if not os.path.exists(shadow_csv_path):
        return []
    rows: List[Dict] = []
    with open(shadow_csv_path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append(_settle_row(r, finals))
    return rows


# --------------------------------------------------------------------------- #
# Day-level settlement.                                                       #
# --------------------------------------------------------------------------- #
def settle_day(date_str: str, base_dir: Optional[str] = None) -> int:
    """Settle all shadow CSVs for date_str; write consolidated settled CSV.

    For every data/shadow/*_<date_str>.csv:
      - extract game_id from filename stem
      - fetch final boxscore from cdn.nba.com
      - if finalized, settle all logged rows
    Writes data/shadow/settled_<date_str>.csv (all games, all gates).

    Parameters
    ----------
    date_str : "YYYY-MM-DD"
    base_dir : override data/shadow location (used in tests)

    Returns
    -------
    int : number of rows settled (written to the consolidated output)
    """
    shadow_dir = base_dir or SHADOW_DIR
    os.makedirs(shadow_dir, exist_ok=True)

    import glob as _glob

    pattern = os.path.join(shadow_dir, f"*_{date_str}.csv")
    candidates = sorted(_glob.glob(pattern))

    # Skip any existing settled_ output files.
    candidates = [p for p in candidates if not os.path.basename(p).startswith("settled_")]

    n_games     = len(candidates)
    n_finalized = 0
    all_rows: List[Dict] = []

    for path in candidates:
        stem     = os.path.basename(path).replace(f"_{date_str}.csv", "")
        game_id  = stem  # stem IS the game_id by Agent 1 naming convention
        finals   = fetch_final_boxscore(game_id)
        if finals is None:
            continue  # game not final or fetch failed
        n_finalized += 1
        rows = settle_shadow_log(path, finals)
        all_rows.extend(rows)

    # Write consolidated output (even if empty — header only is still valid).
    out_path = os.path.join(shadow_dir, f"settled_{date_str}.csv")
    _write_settled(out_path, all_rows)

    n_settled  = len(all_rows)
    # Hit-rate on PASSED bets only (gate_status == "passed").
    passed = [r for r in all_rows if str(r.get("gate_status", "")).lower() == "passed"]
    hits   = sum(1 for r in passed if r.get("outcome") == "hit")
    hit_rate = (100.0 * hits / len(passed)) if passed else 0.0

    print(
        f"{n_games} games found, {n_finalized} games finalized, "
        f"{n_settled} rows settled, hit-rate {hit_rate:.1f}% (passed only)"
    )
    return n_settled


def _write_settled(path: str, rows: List[Dict]) -> None:
    """Write settled rows to path. All shadow+extra columns; extras blank for partial rows."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_SETTLED_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            # Fill missing settled-extra cols with empty string.
            for col in _SETTLED_EXTRA:
                r.setdefault(col, "")
            w.writerow(r)
