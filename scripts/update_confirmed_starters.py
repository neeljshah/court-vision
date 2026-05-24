"""update_confirmed_starters.py -- pre-tip confirmed-starters update (cycle 88d).

Second-biggest pre-tip live signal after the cycle-61 rotowire scrape: ~30
minutes before tip the NBA confirms the official starting lineup, which can
diverge from rotowire's PROJECTED / EXPECTED starters (late scratches, surprise
benchings, etc). When the confirmed 5 lands, the predictions ledger written by
predict_slate.py (cycle 47/49/80) needs to:

  * Promote newly-confirmed starters whose projected status was bench /
    questionable -> lineup_class = "starter".
  * Demote projected starters who didn't make the official 5 ->
    lineup_class = "bench".
  * Bump lineup_status text "Projected"/"Expected" -> "Confirmed" once
    rotowire (or the NBA) flips the badge for an unchanged starter.

This script does NOT mutate the `pred` column itself -- post-prediction
minutes scaling is the job of src.data.lineups.apply_minutes_scaling and
predict_slate.py. Here we only correct the CONTEXT columns
(lineup_status / lineup_class) so downstream consumers (compare_to_lines,
bet_selector, daily reporting) see the latest pre-tip lineup truth.

Sources used:
  1. data/lineups_<date>.json (cycle 61 rotowire) -- already merged when
     predict_slate.py ran, but may have hardened from Expected to Confirmed
     since then. --refresh-lineups re-runs fetch_lineups before reading.
  2. NBA scoreboardv2 -> GameHeader for game_ids on the date.
  3. NBA boxscoresummaryv2 / boxscoretraditionalv2 -- pulls the official
     STARTER flag for each player once available (~30 min pre-tip when the
     LineupStarters resultSet is populated).

The pure update_row() function is the testable atom -- everything else is
plumbing (CSV read/write, scoreboard fetch, lineup refresh).

CLI:
    python scripts/update_confirmed_starters.py
    python scripts/update_confirmed_starters.py --date 2026-05-24 --inplace
    python scripts/update_confirmed_starters.py --refresh-lineups
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
import unicodedata
from datetime import date as _date
from typing import Dict, Iterable, List, Optional, Set, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_PRED_DIR = os.path.join(PROJECT_DIR, "data", "predictions")
_API_SLEEP = 0.6


# -- pure helpers ------------------------------------------------------------

def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _name_key(name: str) -> str:
    """Diacritic + case insensitive name key (Jokic == Jokic)."""
    return _strip_accents(name).lower().strip()


def _strip_status_tags(name: str) -> str:
    """Strip trailing cycle-64 status tags like ' [BENCH]' / ' [QUES]' from
    a stored player name so confirmed-5 lookups match cleanly."""
    return str(name or "").split(" [")[0].strip()


def update_row(
    row: Dict[str, str],
    confirmed_starters_by_team: Dict[str, Set[str]],
    *,
    lineups_status_by_name: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Apply one pre-tip update to a single predictions-ledger row.

    PARAMETERS
    ----------
    row : the CSV row as a {col: value} dict. Must have 'player' and 'team'
          keys; 'lineup_status' / 'lineup_class' / 'play_pct' / 'injury_status'
          are optional but updated when present.
    confirmed_starters_by_team : {TEAM_ABBR: {name_key, ...}} of the OFFICIAL
          confirmed starting fives. Empty dict / missing team is treated as
          "not yet confirmed" -- no class change, status may still bump.
    lineups_status_by_name : optional {name_key: status_string} pulled from
          the (possibly-refreshed) lineups JSON. Used to bump the
          lineup_status text Projected/Expected -> Confirmed when the same
          player still appears as a starter in the JSON.

    RETURNS
    -------
    A NEW dict (caller's row is unmutated). When nothing changes the contents
    are identical to the input.
    """
    new = dict(row)
    raw_name = _strip_status_tags(new.get("player", ""))
    team = (new.get("team") or "").upper().strip()
    nkey = _name_key(raw_name)

    confirmed_set = confirmed_starters_by_team.get(team) if team else None
    is_in_confirmed = bool(confirmed_set and nkey in confirmed_set)

    current_class = (new.get("lineup_class") or "").strip().lower()

    # PROMOTION: in the official 5 but wasn't carrying the starter class.
    if confirmed_set is not None and is_in_confirmed and current_class != "starter":
        new["lineup_class"] = "starter"
        # Strip any QUES/BENCH tag from the stored player display name.
        if " [" in str(new.get("player", "")):
            new["player"] = raw_name

    # DEMOTION: was projected starter but isn't in the official 5.
    elif confirmed_set is not None and not is_in_confirmed and current_class == "starter":
        new["lineup_class"] = "bench"

    # STATUS BUMP: same player, hardened from Projected/Expected -> Confirmed.
    if lineups_status_by_name:
        latest_status = lineups_status_by_name.get(nkey)
        if latest_status:
            cur_status = (new.get("lineup_status") or "").strip()
            # Only ratchet forward. We don't downgrade Confirmed -> Expected.
            order = {"Unknown": 0, "Projected": 1, "Expected": 2, "Confirmed": 3}
            if order.get(latest_status, 0) > order.get(cur_status, 0):
                new["lineup_status"] = latest_status

    return new


# -- IO + plumbing -----------------------------------------------------------

def _load_lineups_status_index(date_str: str) -> Dict[str, str]:
    """Build {name_key: lineup_status} from data/lineups_<date>.json.

    Returns {} when the file is missing or unparseable -- consistent with
    src/data/lineups.build_starter_index's tolerance.
    """
    path = os.path.join(PROJECT_DIR, "data", f"lineups_{date_str}.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh) or {}
    except Exception:
        return {}
    out: Dict[str, str] = {}
    for g in payload.get("games", []) or []:
        for side in ("away", "home"):
            lu = g.get(f"{side}_lineup", {}) or {}
            status = lu.get("status", "Unknown")
            for s in lu.get("starters", []) or []:
                k = _name_key(s.get("name", ""))
                if k:
                    out[k] = status
    return out


def _fetch_confirmed_starters(date_str: str) -> Dict[str, Set[str]]:
    """Pull the official confirmed starting fives for each game on `date_str`.

    Returns {team_abbrev: {name_key, ...}}. Empty dict if scoreboard fails
    or no games are on the slate -- caller should fall through and not
    promote/demote anything.

    Each game contributes when boxscoretraditionalv2 returns rows with
    START_POSITION non-empty (the official starter flag). Before tip this
    populates ~30 minutes prior to the scheduled jump ball.
    """
    try:
        import src.data.nba_api_headers_patch  # noqa: F401
        from nba_api.stats.library.http import NBAStatsHTTP
        from nba_api.stats.endpoints import boxscoretraditionalv2
        from nba_api.stats.static import teams as _teams
    except Exception as e:
        print(f"[update_confirmed_starters] nba_api unavailable: {e}")
        return {}

    id_to_abbrev = {int(t["id"]): str(t["abbreviation"]) for t in _teams.get_teams()}

    try:
        resp = NBAStatsHTTP().send_api_request(
            endpoint="scoreboardv2",
            parameters={"GameDate": date_str, "LeagueID": "00", "DayOffset": 0},
        )
        time.sleep(_API_SLEEP)
        data = resp.get_dict()
        rs = data.get("resultSets") or data.get("resultSet") or []
        gh = next((s for s in rs if s.get("name") == "GameHeader"), None)
        if not gh:
            return {}
        idx = {c: i for i, c in enumerate(gh.get("headers") or [])}
        game_ids = [str(r[idx["GAME_ID"]]) for r in gh.get("rowSet") or []
                    if "GAME_ID" in idx]
    except Exception as e:
        print(f"[update_confirmed_starters] scoreboard fetch failed: {e}")
        return {}

    out: Dict[str, Set[str]] = {}
    for gid in game_ids:
        try:
            bx = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=gid)
            time.sleep(_API_SLEEP)
            df = bx.player_stats.get_data_frame()
        except Exception as e:
            print(f"[update_confirmed_starters] boxscore {gid} failed: {e}")
            continue
        for _, row in df.iterrows():
            try:
                start_pos = str(row.get("START_POSITION") or "").strip()
                if not start_pos:
                    continue
                tid = int(row.get("TEAM_ID"))
                abbr = id_to_abbrev.get(tid) or str(row.get("TEAM_ABBREVIATION") or "")
                name = str(row.get("PLAYER_NAME") or "")
                if not abbr or not name:
                    continue
                out.setdefault(abbr.upper(), set()).add(_name_key(name))
            except Exception:
                continue
    return out


def update_predictions_csv(
    in_path: str,
    out_path: str,
    confirmed_starters_by_team: Dict[str, Set[str]],
    lineups_status_by_name: Optional[Dict[str, str]] = None,
) -> Tuple[int, int, int]:
    """Stream the predictions CSV row-by-row, write the updated copy.

    Returns (rows_total, rows_promoted, rows_demoted) summary counters.
    """
    promoted = demoted = 0
    rows: List[Dict[str, str]] = []
    with open(in_path, encoding="utf-8", newline="") as fh:
        rdr = csv.DictReader(fh)
        fieldnames = list(rdr.fieldnames or [])
        for r in rdr:
            new = update_row(
                r,
                confirmed_starters_by_team,
                lineups_status_by_name=lineups_status_by_name,
            )
            old_cls = (r.get("lineup_class") or "").lower()
            new_cls = (new.get("lineup_class") or "").lower()
            if old_cls != "starter" and new_cls == "starter":
                promoted += 1
            elif old_cls == "starter" and new_cls == "bench":
                demoted += 1
            rows.append(new)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return len(rows), promoted, demoted


# -- CLI ---------------------------------------------------------------------

def _refresh_lineups(date_str: str) -> None:
    """Best-effort re-run of fetch_lineups.py to harden Projected -> Confirmed."""
    script = os.path.join(PROJECT_DIR, "scripts", "fetch_lineups.py")
    if not os.path.exists(script):
        print("[update_confirmed_starters] fetch_lineups.py missing -- skipped refresh")
        return
    try:
        subprocess.run(
            [sys.executable, script, "--date", date_str, "--force"],
            check=False, timeout=60,
        )
    except Exception as e:
        print(f"[update_confirmed_starters] lineup refresh failed: {e}")


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", default=None,
                    help="YYYY-MM-DD; default today.")
    ap.add_argument("--in", dest="in_path", default=None,
                    help="Predictions CSV (default data/predictions/<date>.csv).")
    ap.add_argument("--out", dest="out_path", default=None,
                    help="Output CSV (default writes alongside input with .updated.csv suffix).")
    ap.add_argument("--inplace", action="store_true",
                    help="Overwrite the input file in place.")
    ap.add_argument("--refresh-lineups", action="store_true",
                    help="Re-fetch rotowire lineups first (15-min cache bypass).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would change; do not write a CSV.")
    args = ap.parse_args(list(argv) if argv is not None else None)

    date_str = args.date or _date.today().isoformat()
    in_path = args.in_path or os.path.join(_PRED_DIR, f"{date_str}.csv")
    if not os.path.exists(in_path):
        print(f"[update_confirmed_starters] predictions ledger missing: {in_path}")
        return 1

    if args.inplace:
        out_path = in_path
    else:
        out_path = args.out_path or in_path.replace(".csv", ".updated.csv")

    if args.refresh_lineups:
        _refresh_lineups(date_str)

    lineups_status = _load_lineups_status_index(date_str)
    confirmed = _fetch_confirmed_starters(date_str)

    if not confirmed and not lineups_status:
        print("[update_confirmed_starters] no confirmed lineups + no lineups JSON -- nothing to do")
        return 0

    if args.dry_run:
        # Read once, count what would change, do not write.
        rows_total = promoted = demoted = 0
        with open(in_path, encoding="utf-8", newline="") as fh:
            rdr = csv.DictReader(fh)
            for r in rdr:
                rows_total += 1
                new = update_row(r, confirmed, lineups_status_by_name=lineups_status)
                old_cls = (r.get("lineup_class") or "").lower()
                new_cls = (new.get("lineup_class") or "").lower()
                if old_cls != "starter" and new_cls == "starter":
                    promoted += 1
                elif old_cls == "starter" and new_cls == "bench":
                    demoted += 1
        print(f"[update_confirmed_starters] dry-run: {rows_total} rows, "
              f"{promoted} promotions, {demoted} demotions (no file written)")
        return 0

    n, promoted, demoted = update_predictions_csv(
        in_path, out_path, confirmed,
        lineups_status_by_name=lineups_status,
    )
    print(f"[update_confirmed_starters] {n} rows -> {out_path}  "
          f"(promoted={promoted}, demoted={demoted}, "
          f"teams_confirmed={len(confirmed)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
