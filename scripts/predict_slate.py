"""predict_slate.py — full-slate prop predictions for every rostered player.

Loops over every game on a given date (NBA Scoreboard), fetches each team's
roster (CommonTeamRoster), and runs the production prop_pergame stack on every
player. Output is grouped per game, sorted within each team by recent volume
(L5 PTS) as a proxy for rotation likelihood, and capped at --top N players.

Usage:
    python scripts/predict_slate.py --date 2025-04-13 --top 5
    python scripts/predict_slate.py                        # defaults to today, top=8

Output (per game):
    === LAL @ DEN (2025-04-13) ===
      Nikola Jokic (DEN)    PTS 28.4  REB 12.1  AST 9.8  FG3M 1.5  STL 0.8  BLK 0.4  TOV 3.1
      LeBron James (LAL)    PTS 23.1  REB 8.0   AST 8.6  FG3M 2.0  STL 1.1  BLK 0.6  TOV 3.5
      ...
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, date as _date
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Reconfigure stdout to UTF-8 on Windows so accented player names (Jokić, Šengün,
# Dončić, ...) don't crash the print loop with cp1252.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# Silence the LGBMRegressor "X does not have valid feature names" UserWarning
# that fires once per stat per player — drowns out the actual output.
import warnings  # noqa: E402
warnings.filterwarnings("ignore", message="X does not have valid feature names")

# IMPORTANT: patch nba_api headers BEFORE any nba_api endpoint imports.
import src.data.nba_api_headers_patch  # noqa: F401,E402

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, predict_player_pergame, _MIN_PLAYED, _num,
)
from src.data.injuries import (  # noqa: E402
    load_unavailable_players, load_soft_warn_players, lookup_status,
)
from src.data.lineups import (  # noqa: E402
    build_starter_index, classify_starter,
    apply_minutes_scaling, STATUS_SCALE,
)


_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_PRED_DIR  = os.path.join(PROJECT_DIR, "data", "predictions")
_API_SLEEP = 0.6  # polite delay between nba_api calls


def _scale_lineup_preds(rows: List[Dict], starter_idx: Dict[str, dict]) -> List[Dict]:
    """Scale each player's preds dict by their lineup classification (cycle 67).

    Uses the original name (before _tag_lineup added '[BENCH]' etc) for the
    classification lookup. Returns NEW dicts — caller's rows are unmutated.
    """
    out = []
    for r in rows:
        raw_name = r["name"].split(" [")[0]   # strip any trailing tag
        cls = classify_starter(raw_name, starter_idx)
        scaled = apply_minutes_scaling(r["preds"], cls)
        r = dict(r); r["preds"] = scaled
        out.append(r)
    return out


def _tag_lineup(rows: List[Dict], starter_idx: Dict[str, dict]) -> List[Dict]:
    """Append lineup classification tag to each row's name (informational)."""
    out = []
    for r in rows:
        cls = classify_starter(r["name"], starter_idx)
        if cls == "starter":
            # Don't tag — starter is the default expectation.
            out.append(r); continue
        tag = cls.upper().replace("-", " ")
        r = dict(r); r["name"] = f"{r['name']} [{tag}]"
        out.append(r)
    return out


def _filter_injuries(rows: List[Dict], unav: Dict[str, str],
                      soft: Dict[str, str]) -> List[Dict]:
    """Drop unavailable players; mutate name in-place to append soft-warn tag."""
    out = []
    for r in rows:
        status = lookup_status(r["name"], unav, soft)
        if status and status in unav.values():
            continue
        if status:
            r = dict(r); r["name"] = f"{r['name']} [{status}]"
        out.append(r)
    return out


def save_predictions_csv(
    out_path: str, date_str: str,
    games: List[Dict],
    per_game_rows: List[Tuple[Dict, List[Dict], List[Dict]]],
    starter_idx: Optional[Dict[str, dict]] = None,
    unav_inj: Optional[Dict[str, str]] = None,
    soft_inj: Optional[Dict[str, str]] = None,
) -> int:
    """Write one row per (player, stat) to CSV with prediction-time context.

    Cycle 80: schema now ALSO captures the lineup + injury context that
    was known at prediction time. This enables future empirical validation
    of any post-prediction adjustment (cycle 66/67 scale-by-status, etc.)
    once 30+ days of predictions + actuals accumulate.

    Schema:
        date, game_id, player_id, player, team, opp, venue, stat, pred,
        lineup_status, lineup_class, play_pct, injury_status

    Context columns are BLANK when their source data wasn't loaded — so
    the cycle-47 callers that don't pass starter_idx / inj data still work.

    Returns rows written.
    """
    # Local import to avoid the heavy top-level dependency for cycle-47 callers.
    from src.data.lineups import classify_starter as _classify

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    n = 0
    starter_idx = starter_idx or {}
    unav_inj = unav_inj or {}
    soft_inj = soft_inj or {}

    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([
            "date", "game_id", "player_id", "player", "team", "opp", "venue",
            "stat", "pred",
            "lineup_status", "lineup_class", "play_pct", "injury_status",
        ])
        for g, home_rows, away_rows in per_game_rows:
            game_id = g.get("game_id", "")
            home_abbrev = g.get("home_abbrev") or f"T{g.get('home_id')}"
            away_abbrev = g.get("away_abbrev") or f"T{g.get('away_id')}"
            for venue, rows, opp in (("home", home_rows, away_abbrev),
                                     ("away", away_rows, home_abbrev)):
                for r in rows:
                    # Strip any cycle-64 [TAG] suffix when looking up context
                    # so the lookup key matches the raw player name.
                    raw_name = r["name"].split(" [")[0]
                    rec = starter_idx.get(raw_name.lower())
                    lineup_status = rec["lineup_status"] if rec else ""
                    play_pct = rec["play_pct"] if rec else ""
                    lineup_class = (_classify(raw_name, starter_idx)
                                     if starter_idx else "")
                    inj_status = lookup_status(raw_name, unav_inj, soft_inj) or ""
                    for stat in STATS:
                        v = r["preds"].get(stat)
                        if v is None:
                            continue
                        w.writerow([
                            date_str, game_id, r["player_id"], raw_name,
                            r["team"], opp, venue, stat, f"{float(v):.4f}",
                            lineup_status, lineup_class, play_pct, inj_status,
                        ])
                        n += 1
    return n


def _detect_season(d: _date) -> str:
    """NBA season string 'YYYY-YY' for a given date.

    Season starts in October. Oct-Dec uses (year)-(year+1); Jan-Sep uses
    (year-1)-year (the season ending in spring).
    """
    if d.month >= 10:
        start = d.year
    else:
        start = d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _team_abbrev_lookup() -> Dict[int, str]:
    """Build {team_id: abbreviation} from nba_api's static team list."""
    try:
        from nba_api.stats.static import teams  # noqa: PLC0415
        return {int(t["id"]): str(t["abbreviation"]) for t in teams.get_teams()}
    except Exception as e:
        print(f"  [warn] could not load static team list: {e}")
        return {}


def fetch_games(date_str: str) -> List[Dict]:
    """Fetch games for a date via NBA scoreboardv2.

    Returns a list of {game_id, home_id, away_id, home_abbrev, away_abbrev}.
    Uses NBAStatsHTTP directly so we bypass nba_api's ScoreboardV2 wrapper —
    the wrapper crashes on missing 'WinProbability' in modern API responses.
    Empty list on failure or no games.
    """
    id_to_abbrev = _team_abbrev_lookup()
    games: List[Dict] = []
    try:
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
        result_sets = data.get("resultSets") or data.get("resultSet") or []
        gh = next((s for s in result_sets if s.get("name") == "GameHeader"), None)
        if not gh:
            return []
        headers = gh.get("headers") or []
        idx = {col: i for i, col in enumerate(headers)}
        for row in gh.get("rowSet") or []:
            try:
                home_id = int(row[idx["HOME_TEAM_ID"]])
                away_id = int(row[idx["VISITOR_TEAM_ID"]])
            except (KeyError, IndexError, TypeError, ValueError):
                continue
            home_abbrev = id_to_abbrev.get(home_id, "")
            away_abbrev = id_to_abbrev.get(away_id, "")
            # Fallback to parsing GAMECODE ("YYYYMMDD/AWAYHOM") for abbrevs.
            if not home_abbrev or not away_abbrev:
                gc = str(row[idx["GAMECODE"]]) if "GAMECODE" in idx else ""
                if "/" in gc:
                    teams_token = gc.split("/", 1)[1]
                    if len(teams_token) >= 6:
                        away_abbrev = away_abbrev or teams_token[:3]
                        home_abbrev = home_abbrev or teams_token[3:6]
            games.append({
                "game_id":     str(row[idx["GAME_ID"]]) if "GAME_ID" in idx else "",
                "home_id":     home_id,
                "away_id":     away_id,
                "home_abbrev": home_abbrev,
                "away_abbrev": away_abbrev,
            })
    except Exception as e:
        print(f"  [warn] scoreboard fetch failed: {e}")
        return []
    return games


def fetch_roster(team_id: int, season: str) -> List[Tuple[int, str]]:
    """Fetch a team's roster as [(player_id, player_name), ...].

    Raises on API failure so the caller can warn-and-skip per-team.
    """
    from nba_api.stats.endpoints import commonteamroster  # noqa: PLC0415
    cr = commonteamroster.CommonTeamRoster(team_id=team_id, season=season)
    time.sleep(_API_SLEEP)
    df = cr.common_team_roster.get_data_frame()
    out: List[Tuple[int, str]] = []
    for _, row in df.iterrows():
        try:
            pid = int(row["PLAYER_ID"])
            name = str(row["PLAYER"])
            out.append((pid, name))
        except Exception:
            continue
    return out


def player_l5_pts(player_id: int, season: str,
                  gamelog_dir: str = _NBA_CACHE) -> Optional[float]:
    """Return the player's L5 average PTS for sorting; None when no cache.

    Mirrors the gamelog-read logic from predict_player._player_l5_l10 but
    only computes PTS (used solely for rotation-likelihood sorting).
    """
    path = os.path.join(gamelog_dir, f"gamelog_{player_id}_{season}.json")
    if not os.path.exists(path):
        # Fall back to prior season's gamelog so off-season runs still sort.
        try:
            start = int(season[:4]) - 1
            prev = f"{start}-{str(start + 1)[-2:]}"
        except (ValueError, TypeError):
            return None
        path = os.path.join(gamelog_dir, f"gamelog_{player_id}_{prev}.json")
        if not os.path.exists(path):
            return None
    try:
        games = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    played = [g for g in games if _num(g.get("MIN")) >= _MIN_PLAYED]
    if not played:
        return None
    recent = played[-5:]
    return sum(_num(g.get("PTS")) for g in recent) / max(1, len(recent))


def predict_team(team_id: int, team_abbrev: str, opp_abbrev: str,
                 season: str, is_home: bool, top_n: int,
                 rest_days: float = 2.0) -> List[Dict]:
    """Predict every roster player on a team; return up to top_n entries.

    Sorted by L5 PTS desc (rotation proxy). Players with no cached gamelog
    or no model prediction are skipped silently.
    """
    try:
        roster = fetch_roster(team_id, season)
    except Exception as e:
        print(f"  [warn] could not fetch roster for {team_abbrev}: {e}")
        return []

    # Sort the full roster by L5 PTS first so the top_n cap reflects rotation
    # likelihood — only the top minutes-eaters will be predicted/printed.
    ranked = []
    for pid, name in roster:
        l5 = player_l5_pts(pid, season) or 0.0
        ranked.append((l5, pid, name))
    ranked.sort(key=lambda t: t[0], reverse=True)

    results: List[Dict] = []
    for _l5, pid, name in ranked:
        if len(results) >= top_n:
            break
        try:
            preds = predict_player_pergame(
                pid, opp_abbrev, season,
                is_home=is_home, rest_days=rest_days,
                gamelog_dir=_NBA_CACHE, model_dir=_MODEL_DIR,
            )
        except Exception:
            preds = None
        if not preds:
            continue
        results.append({
            "player_id": pid,
            "name":      name,
            "team":      team_abbrev,
            "preds":     preds,
        })
    return results


def print_game(home_abbrev: str, away_abbrev: str, date_str: str,
               home_rows: List[Dict], away_rows: List[Dict]) -> None:
    """Print one game banner + sorted player table (PTS desc, both teams)."""
    banner = f"=== {away_abbrev} @ {home_abbrev} ({date_str}) ==="
    print(f"\n{banner}")
    all_rows = sorted(
        home_rows + away_rows,
        key=lambda r: float(r["preds"].get("pts", 0.0) or 0.0),
        reverse=True,
    )
    if not all_rows:
        print("  (no predictions available)")
        return
    for r in all_rows:
        p = r["preds"]
        name_team = f"{r['name']} ({r['team']})"
        # Belt-and-braces: if stdout still can't encode this, drop diacritics.
        try:
            name_team.encode(sys.stdout.encoding or "utf-8")
        except (UnicodeEncodeError, LookupError):
            import unicodedata  # noqa: PLC0415
            name_team = "".join(
                c for c in unicodedata.normalize("NFKD", name_team)
                if not unicodedata.combining(c)
            ).encode("ascii", "replace").decode("ascii")
        print(
            f"  {name_team:<28}"
            f"  PTS {p.get('pts', 0):>5.1f}"
            f"  REB {p.get('reb', 0):>4.1f}"
            f"  AST {p.get('ast', 0):>4.1f}"
            f"  FG3M {p.get('fg3m', 0):>3.1f}"
            f"  STL {p.get('stl', 0):>3.1f}"
            f"  BLK {p.get('blk', 0):>3.1f}"
            f"  TOV {p.get('tov', 0):>4.1f}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="NBA full-slate prop predictions")
    ap.add_argument("--date", default=None,
                    help="Slate date YYYY-MM-DD (default: today)")
    ap.add_argument("--top", type=int, default=8,
                    help="Max players to show per team (default 8)")
    ap.add_argument("--season", default=None,
                    help="Season override (e.g. '2024-25'). Default: auto-detect.")
    ap.add_argument("--rest", type=float, default=2.0,
                    help="Days rest assumed for every player (default 2)")
    ap.add_argument("--save", nargs="?", const="__default__", default=None,
                    help="Write predictions CSV. Bare flag → data/predictions/<date>.csv; "
                         "with arg → write to that path. Schema: date,game_id,player_id,"
                         "player,team,opp,venue,stat,pred (one row per stat).")
    ap.add_argument("--injuries", nargs="?", const="__default__", default=None,
                    help="Cross-reference data/injuries_<date>.json. Players listed "
                         "OUT/DOUBTFUL/NOT-WITH-TEAM are skipped; QUESTIONABLE players "
                         "get a soft-warn tag in the printed output.")
    ap.add_argument("--lineups", nargs="?", const="__default__", default=None,
                    help="Cycle 64. Cross-reference data/lineups_<date>.json from the "
                         "cycle-61 rotowire scrape. Non-starters get a [BENCH] tag "
                         "in the printed output instead of being skipped (slate view "
                         "is informational, unlike compare_to_lines which is for betting).")
    ap.add_argument("--scale-by-status", action="store_true",
                    help="Cycle 67. Scale every stat prediction by lineup classification "
                         "(questionable*0.75, bench*0.30, no-game*0.0). Requires --lineups.")
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
    season = args.season or _detect_season(d)

    print(f"\n  Slate date: {date_str}    season={season}    top={args.top}/team    rest={args.rest}d")

    games = fetch_games(date_str)
    if not games:
        print(f"\nNo games on {date_str}")
        return 0

    print(f"  Found {len(games)} game(s).")

    # Cycle 53: injury cross-reference. {} on missing file → no filtering applied.
    inj_unav: Dict[str, str] = {}; inj_soft: Dict[str, str] = {}
    if args.injuries is not None:
        inj_path = (os.path.join(PROJECT_DIR, "data",
                                  f"injuries_{date_str}.json")
                    if args.injuries == "__default__" else args.injuries)
        inj_unav = load_unavailable_players(inj_path)
        inj_soft = load_soft_warn_players(inj_path)
        print(f"  [injuries] {len(inj_unav)} unavailable, {len(inj_soft)} questionable")

    # Cycle 64: lineup cross-reference. Tags non-starters in output.
    starter_idx: Dict[str, dict] = {}
    if args.lineups is not None:
        lu_path = (os.path.join(PROJECT_DIR, "data",
                                  f"lineups_{date_str}.json")
                    if args.lineups == "__default__" else args.lineups)
        starter_idx = build_starter_index(lu_path)
        print(f"  [lineups] {len(starter_idx)} starters across all teams tonight")

    per_game_rows: List[Tuple[Dict, List[Dict], List[Dict]]] = []
    for g in games:
        home_abbrev = g["home_abbrev"] or f"T{g['home_id']}"
        away_abbrev = g["away_abbrev"] or f"T{g['away_id']}"
        home_rows = predict_team(
            g["home_id"], home_abbrev, away_abbrev,
            season, is_home=True, top_n=args.top, rest_days=args.rest,
        )
        away_rows = predict_team(
            g["away_id"], away_abbrev, home_abbrev,
            season, is_home=False, top_n=args.top, rest_days=args.rest,
        )
        if inj_unav or inj_soft:
            # Skip unavailable players, tag soft-warn players in-place.
            home_rows = _filter_injuries(home_rows, inj_unav, inj_soft)
            away_rows = _filter_injuries(away_rows, inj_unav, inj_soft)
        if starter_idx:
            # Tag non-starters in name (slate is informational — never drop).
            home_rows = _tag_lineup(home_rows, starter_idx)
            away_rows = _tag_lineup(away_rows, starter_idx)
            if args.scale_by_status:
                home_rows = _scale_lineup_preds(home_rows, starter_idx)
                away_rows = _scale_lineup_preds(away_rows, starter_idx)
        print_game(home_abbrev, away_abbrev, date_str, home_rows, away_rows)
        per_game_rows.append((g, home_rows, away_rows))

    if args.save is not None:
        out = (os.path.join(_PRED_DIR, f"{date_str}.csv")
               if args.save == "__default__" else args.save)
        # Cycle 80: pass the context that was loaded for filtering/scaling so
        # the ledger captures it for future empirical validation.
        n = save_predictions_csv(
            out, date_str, games, per_game_rows,
            starter_idx=starter_idx if args.lineups is not None else None,
            unav_inj=inj_unav if args.injuries is not None else None,
            soft_inj=inj_soft if args.injuries is not None else None,
        )
        print(f"\n  Wrote {n} prediction rows → {out}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
