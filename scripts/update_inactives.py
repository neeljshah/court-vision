"""update_inactives.py — pre-tip final inactives sweep (cycle 88c, loop 5).

30 minutes before tip, the NBA injury report's final revision plus
scoreboardv2's Inactive list together represent the ground truth for which
rostered players WILL NOT PLAY tonight. This script reads:

  - data/predictions/<date>.csv         (cycle 47/49/80 ledger, ~14 rows/player)
  - data/injuries_<date>.json           (cycle 43/60 scrape, OUT/DOUBTFUL/etc.)
  - scoreboardv2 Inactives list         (live nba_api fetch; optional)
  - optional manual --inactives-csv     (override / blocked-API fallback)

…and zeroes every prediction row belonging to a confirmed inactive player.
The original prediction is preserved in a new `pred_pre_inactive` column so
the cycle-80 ledger schema stays diffable and the downstream Kelly /
compare_to_lines callers can recover the pre-inactive number if needed.

Usage
-----
    python scripts/update_inactives.py                       # today
    python scripts/update_inactives.py --date 2026-05-24
    python scripts/update_inactives.py --inplace             # backup + overwrite
    python scripts/update_inactives.py --inactives-csv x.csv # manual override

Manual CSV format (no header row strictness — only `player` column required):
    player,team
    LeBron James,LAL
    Anthony Davis,LAL

Output
------
    data/predictions/<date>_post_inactives.csv (default)
    data/predictions/<date>.csv + <date>.csv.bak (with --inplace)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
from datetime import datetime, date as _date
from typing import Dict, List, Optional, Set, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Reuse the diacritic-insensitive canonical key from cycle 53 so 'Jokić'
# from a scoreboard payload matches 'Jokic' in the predictions CSV.
from src.data.injuries import (  # noqa: E402
    _name_key, load_unavailable_players,
)

_PRED_DIR = os.path.join(PROJECT_DIR, "data", "predictions")
_API_SLEEP = 0.6


# --- data sources -----------------------------------------------------------


def load_scoreboard_inactives(date_str: str) -> Set[str]:
    """Fetch today's Inactive players from scoreboardv2 (best-effort).

    Returns a set of canonical name keys. We hit NBAStatsHTTP directly to
    bypass the nba_api wrapper's WinProbability crash (same workaround as
    predict_slate.fetch_games). Returns an empty set on any failure so the
    pre-tip sweep degrades gracefully when the API is blocked.
    """
    keys: Set[str] = set()
    try:
        # Local import so tests can run offline without nba_api installed.
        import src.data.nba_api_headers_patch  # noqa: F401,PLC0415
        from nba_api.stats.library.http import NBAStatsHTTP  # noqa: PLC0415
        resp = NBAStatsHTTP().send_api_request(
            endpoint="scoreboardv2",
            parameters={
                "GameDate":  date_str,
                "LeagueID":  "00",
                "DayOffset": 0,
            },
        )
        time.sleep(_API_SLEEP)
        data = resp.get_dict()
        for s in data.get("resultSets") or data.get("resultSet") or []:
            if s.get("name") != "Inactive":
                continue
            headers = s.get("headers") or []
            idx = {col: i for i, col in enumerate(headers)}
            for row in s.get("rowSet") or []:
                # The endpoint exposes FIRST_NAME + LAST_NAME (preferred) but
                # falls back to a single PLAYER_NAME on some season slices.
                first = str(row[idx["FIRST_NAME"]]) if "FIRST_NAME" in idx else ""
                last  = str(row[idx["LAST_NAME"]])  if "LAST_NAME"  in idx else ""
                if first or last:
                    keys.add(_name_key(f"{first} {last}"))
                elif "PLAYER_NAME" in idx:
                    keys.add(_name_key(str(row[idx["PLAYER_NAME"]])))
    except Exception as e:
        print(f"  [warn] scoreboard inactives fetch failed: {e}")
    return keys


def load_manual_inactives(path: str) -> Set[str]:
    """Read a manual inactives CSV: `player[,team]`. First column wins.

    Tolerates header rows where the first cell is literally 'player'.
    Returns an empty set if the file is missing or malformed.
    """
    keys: Set[str] = set()
    if not path or not os.path.exists(path):
        return keys
    try:
        with open(path, encoding="utf-8") as fh:
            for i, row in enumerate(csv.reader(fh)):
                if not row:
                    continue
                name = (row[0] or "").strip()
                if not name:
                    continue
                if i == 0 and name.lower() == "player":
                    continue
                keys.add(_name_key(name))
    except Exception as e:
        print(f"  [warn] manual inactives read failed: {e}")
    return keys


# --- ledger mutation --------------------------------------------------------


def apply_inactives(in_path: str, out_path: str,
                    inactive_keys: Set[str]) -> Tuple[int, int]:
    """Rewrite the predictions CSV with pred=0 for inactive players.

    Returns (rows_zeroed, distinct_players_zeroed). Always writes
    `pred_pre_inactive` as the last column. Safe on re-run: rows that
    already carry the column are read back as the source-of-truth original.
    """
    if not os.path.exists(in_path):
        raise FileNotFoundError(f"predictions ledger not found: {in_path}")

    with open(in_path, encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    if not rows:
        # Nothing to mutate; still write an empty file so callers don't crash.
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerow([])
        return 0, 0

    header = rows[0]
    # Locate columns we need. Schema follows save_predictions_csv from cycle 80:
    # date, game_id, player_id, player, team, opp, venue, stat, pred,
    # lineup_status, lineup_class, play_pct, injury_status[, pred_pre_inactive]
    col = {name: i for i, name in enumerate(header)}
    for req in ("player", "pred"):
        if req not in col:
            raise ValueError(f"predictions CSV missing required column: {req!r}")
    has_inj_col   = "injury_status"     in col
    has_orig_col  = "pred_pre_inactive" in col

    # Append the new column if absent.
    if not has_orig_col:
        header = header + ["pred_pre_inactive"]
        pre_idx = len(header) - 1
    else:
        pre_idx = col["pred_pre_inactive"]

    rows_zeroed = 0
    zeroed_keys: Set[str] = set()
    out_rows: List[List[str]] = [header]
    for r in rows[1:]:
        # Pad short rows up to the new schema width.
        if len(r) < len(header):
            r = r + [""] * (len(header) - len(r))

        key = _name_key(r[col["player"]])
        if key in inactive_keys:
            try:
                original = float(r[col["pred"]])
            except (TypeError, ValueError):
                original = 0.0
            # First touch wins: don't clobber an earlier pre-inactive snapshot
            # if this script is run twice in a row.
            if not (has_orig_col and (r[pre_idx] or "").strip()):
                r[pre_idx] = f"{original:.4f}"
            r[col["pred"]] = "0.0000"
            if has_inj_col:
                r[col["injury_status"]] = "INACTIVE"
            rows_zeroed += 1
            zeroed_keys.add(key)
        else:
            # Keep the column populated (empty string) so the schema is stable.
            if not has_orig_col:
                r[pre_idx] = ""
        out_rows.append(r)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerows(out_rows)
    return rows_zeroed, len(zeroed_keys)


# --- CLI --------------------------------------------------------------------


def _gather_inactive_keys(date_str: str,
                          injuries_path: Optional[str],
                          manual_csv:    Optional[str],
                          skip_api:      bool) -> Tuple[Set[str], Dict[str, int]]:
    """Union the three inactive-name sources; return (keys, source_counts)."""
    counts: Dict[str, int] = {"injuries_out": 0, "scoreboard": 0, "manual": 0}

    keys: Set[str] = set()
    if injuries_path and os.path.exists(injuries_path):
        unav = load_unavailable_players(injuries_path)
        counts["injuries_out"] = len(unav)
        keys |= set(unav.keys())

    if not skip_api:
        sb = load_scoreboard_inactives(date_str)
        counts["scoreboard"] = len(sb)
        keys |= sb

    if manual_csv:
        mk = load_manual_inactives(manual_csv)
        counts["manual"] = len(mk)
        keys |= mk

    return keys, counts


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Pre-tip inactives sweep: zero predictions for players "
                    "confirmed OUT in the official injury report or "
                    "scoreboardv2 Inactive list.")
    ap.add_argument("--date", default=None,
                    help="Slate date YYYY-MM-DD (default: today)")
    ap.add_argument("--predictions", default=None,
                    help="Override input CSV path (default: data/predictions/<date>.csv)")
    ap.add_argument("--injuries", default=None,
                    help="Override injury JSON path (default: data/injuries_<date>.json)")
    ap.add_argument("--inactives-csv", default=None,
                    help="Manual inactives CSV (forward-compatible when nba_api is blocked).")
    ap.add_argument("--no-api", action="store_true",
                    help="Skip the scoreboardv2 Inactive fetch entirely.")
    ap.add_argument("--inplace", action="store_true",
                    help="Rewrite the input CSV; original preserved as <name>.csv.bak.")
    ap.add_argument("--out", default=None,
                    help="Override output path (default: data/predictions/<date>_post_inactives.csv)")
    args = ap.parse_args()

    if args.date:
        try:
            d = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"  [fail] bad --date format '{args.date}' — use YYYY-MM-DD.")
            return 2
    else:
        d = _date.today()
    date_str = d.isoformat()

    in_path = args.predictions or os.path.join(_PRED_DIR, f"{date_str}.csv")
    if not os.path.exists(in_path):
        print(f"  [fail] predictions ledger not found: {in_path}")
        return 2

    inj_path = args.injuries or os.path.join(PROJECT_DIR, "data",
                                              f"injuries_{date_str}.json")

    keys, counts = _gather_inactive_keys(
        date_str, inj_path, args.inactives_csv, skip_api=args.no_api,
    )

    if args.inplace:
        bak_path = in_path + ".bak"
        shutil.copy2(in_path, bak_path)
        out_path = in_path
        print(f"  [inplace] backed up original -> {bak_path}")
    else:
        out_path = args.out or os.path.join(
            _PRED_DIR, f"{date_str}_post_inactives.csv")

    rows_zeroed, players_zeroed = apply_inactives(in_path, out_path, keys)

    total = len(keys)
    src = ", ".join(f"{k}={v}" for k, v in counts.items() if v)
    src_part = f"  (sources: {src})" if src else ""
    print(f"{players_zeroed} players zeroed ({total} total inactives detected){src_part}")
    print(f"  rows zeroed: {rows_zeroed}    wrote -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
