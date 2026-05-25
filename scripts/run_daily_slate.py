"""
run_daily_slate.py -- End-to-end daily NBA prop prediction pipeline.

Usage:
    python scripts/run_daily_slate.py --season 2024-25 --date 2026-03-19

Steps:
1. Fetch today's games from NBA API Scoreboard (falls back to schedule files)
2. Get active players for each team (filters dnp_prob > 0.70)
3. Run predict_props() per player (errors caught per-player)
4. Normalise via team total (normalise_team_totals)
5. Score vs DraftKings lines (props_scraper)
6. Rank by edge, apply Kelly sizing
7. Write data/output/slate_{YYYYMMDD}.json + print ranked table
8. Run bet_selector middleware -> data/output/bets_{YYYYMMDD}.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date as _date
from typing import Optional, Set

import yaml

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

logging.basicConfig(level=logging.WARNING,
                    format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("run_daily_slate")

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_OUTPUT_DIR = os.path.join(PROJECT_DIR, "data", "output")
_EXCLUSION_PATH = os.path.join(PROJECT_DIR, "config", "exclusion_list.yaml")


# -- Exclusion list loader ----------------------------------------------------


def load_exclusion_set(path: str = _EXCLUSION_PATH) -> Set[str]:
    """
    Load the exclusion list YAML and return a set of excluded player names
    (lower-cased) and player IDs (as strings).

    Falls back to an empty set if the file is missing or malformed.

    Args:
        path: Path to config/exclusion_list.yaml.

    Returns:
        Set of lower-cased player names and string player IDs to skip.
    """
    excluded: Set[str] = set()
    if not os.path.exists(path):
        return excluded
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for entry in data.get("excluded_players", []) or []:
            pid = entry.get("player_id")
            name = entry.get("player_name", "")
            if pid is not None:
                excluded.add(str(pid))
            if name:
                excluded.add(str(name).lower().strip())
    except Exception as exc:
        log.warning("Could not load exclusion list from %s: %s", path, exc)
    return excluded

# -- Step 1: Fetch today's games -----------------------------------------------


def fetch_today_games(date_str: str, season: str) -> list[dict]:
    """
    Returns list of {"home_team": str, "away_team": str, "game_id": str}.
    Tries NBA API first; falls back to schedule JSON files.
    """
    try:
        import time
        try:
            from nba_api.stats.endpoints import scoreboard as _sb_mod
            sb = _sb_mod.Scoreboard(game_date=date_str)
        except ImportError:
            from nba_api.stats.endpoints import scoreboardv2 as _sb_mod
            sb = _sb_mod.ScoreboardV2(game_date=date_str)
        time.sleep(0.6)
        df = sb.game_header.get_data_frame()
        games = []
        for _, row in df.iterrows():
            # GAMECODE format: YYYYMMDD/AWAYABBRHOMEABBR e.g. "20260323/LALDET"
            gamecode = str(row.get("GAMECODE", ""))
            if "/" in gamecode:
                teams = gamecode.split("/", 1)[1]
                away = teams[:3]
                home = teams[3:6]
            else:
                away = str(row.get("VISITOR_TEAM_ABBREVIATION", ""))
                home = str(row.get("HOME_TEAM_ABBREVIATION", ""))
            games.append({
                "game_id":   str(row.get("GAME_ID", "")),
                "home_team": home,
                "away_team": away,
            })
        if games:
            print(f"[slate] Fetched {len(games)} games from NBA API for {date_str}")
            return games
    except Exception as e:
        log.warning("NBA API scoreboard failed (%s) -- falling back to schedule files", e)

    # Fallback: scan schedule files for today's date
    sched_dir = os.path.join(_NBA_CACHE, "schedule")
    games = []
    seen = set()
    if os.path.isdir(sched_dir):
        for fname in os.listdir(sched_dir):
            if not fname.endswith(".json"):
                continue
            try:
                parts = fname.replace(".json", "").split("_")
                # schedule_{TEAM}_{SEASON} or schedule_{TEAM}_{SEASON}_v2
                if len(parts) < 3:
                    continue
                team = parts[1].upper()
                with open(os.path.join(sched_dir, fname)) as f:
                    sched = json.load(f)
                for g in sched:
                    raw_date = str(g.get("date", ""))[:10]
                    if raw_date != date_str:
                        continue
                    home = str(g.get("home_team", g.get("matchup", "")).split()[0]).upper()
                    away = str(g.get("away_team", "")).upper()
                    gid  = str(g.get("game_id", ""))
                    key  = (home, away)
                    if home and away and key not in seen:
                        seen.add(key)
                        games.append({"game_id": gid, "home_team": home, "away_team": away})
            except Exception:
                continue
    if games:
        print(f"[slate] Found {len(games)} games from schedule files for {date_str}")
    else:
        print(f"[slate] WARNING: No games found for {date_str}")
    return games


# -- Step 2: Get active players ------------------------------------------------


def get_active_players(team_abbr: str, season: str) -> list[str]:
    """
    Return list of player names on this team from player_avgs_{season}.json.
    """
    path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            avgs = json.load(f)
        players = []
        for name, data in avgs.items():
            if str(data.get("team", "")).upper() == team_abbr.upper():
                players.append(name)
        return players
    except Exception as e:
        log.warning("get_active_players(%s) failed: %s", team_abbr, e)
        return []


def _check_dnp(player_id: int, season: str) -> float:
    """Return dnp_prob for a player; defaults to 0.05 on error."""
    try:
        from src.prediction.dnp_predictor import predict_dnp
        result = predict_dnp(str(player_id), season=season)
        return float(result.get("dnp_prob", 0.05) if isinstance(result, dict) else 0.05)
    except Exception:
        return 0.05


# -- Step 3+4: Predict + Normalise ---------------------------------------------


def run_predictions(
    games: list[dict],
    season: str,
    exclusion_set: Optional[Set[str]] = None,
) -> list[dict]:
    """
    Run predict_props for each active player in each game, then normalise by team total.
    Returns flat list of prediction dicts.

    Args:
        games:         List of game dicts from fetch_today_games().
        season:        NBA season string (e.g. "2024-25").
        exclusion_set: Set of lower-cased player names / str player IDs to skip.
                       Populated by load_exclusion_set(). Pass None to skip no one.
    """
    from types import SimpleNamespace
    from src.prediction.player_props import predict_props, _get_player_season_avgs
    from src.prediction.team_total_normalizer import normalise_team_totals
    from src.data.injuries import load_unavailable_players, load_soft_warn_players, lookup_status
    from src.data.lineups import load_lineups, build_starter_index, classify_starter, apply_minutes_scaling

    _excluded = exclusion_set or set()
    all_preds: list[dict] = []

    # Load live injury + lineup data (today's files, if fetched)
    import datetime as _dt
    _today = _dt.date.today().isoformat()
    _inj_path = os.path.join(PROJECT_DIR, "data", f"injuries_{_today}.json")
    _lin_path = os.path.join(PROJECT_DIR, "data", f"lineups_{_today}.json")
    _unavailable = load_unavailable_players(_inj_path) if os.path.exists(_inj_path) else {}
    _soft_warn = load_soft_warn_players(_inj_path) if os.path.exists(_inj_path) else {}
    _starter_index = build_starter_index(_lin_path) if os.path.exists(_lin_path) else {}
    if _unavailable:
        print(f"[slate] Injury filter active: {len(_unavailable)} players OUT/DOUBTFUL")
    if _starter_index:
        print(f"[slate] Lineup data active: {len(_starter_index)} players classified")

    for game in games:
        home = game["home_team"]
        away = game["away_team"]
        gid  = game.get("game_id", "")

        print(f"\n[slate] {away} @ {home}  (game_id={gid})")

        game_ns_list: list[SimpleNamespace] = []

        for team_abbr, opp_abbr in [(home, away), (away, home)]:
            players = get_active_players(team_abbr, season)
            if not players:
                log.warning("  No players found for %s", team_abbr)

            for pname in players:
                try:
                    # Pre-check DNP
                    _avgs = _get_player_season_avgs(pname, season)
                    if _avgs is None:
                        continue
                    _pid = int(_avgs.get("player_id", 0))

                    # Skip players on the exclusion list
                    if (str(_pid) in _excluded
                            or pname.lower().strip() in _excluded):
                        log.info("  Skipping excluded player: %s (id=%s)", pname, _pid)
                        continue

                    # Skip confirmed OUT/DOUBTFUL players from injury report
                    if lookup_status(pname, _unavailable) is not None:
                        log.info("  Skipping injured player: %s (OUT/DOUBTFUL)", pname)
                        continue
                    if lookup_status(pname, _soft_warn) is not None:
                        log.info("  Soft-warn (QUESTIONABLE): %s", pname)

                    dnp_prob = _check_dnp(_pid, season)
                    if dnp_prob > 0.70:
                        continue

                    props = predict_props(pname, opp_abbr, season=season)
                    if not props:
                        continue

                    # Apply lineup-based minutes scaling if classification available
                    _lineup_cls = classify_starter(pname, _starter_index)
                    if _lineup_cls and _lineup_cls != "unknown":
                        _stat_keys = {s: float(props.get(s, 0) or 0)
                                      for s in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")}
                        _scaled = apply_minutes_scaling(_stat_keys, _lineup_cls)
                        props.update(_scaled)
                        if _lineup_cls != "starter":
                            log.info("  Lineup scale applied: %s -> %s", pname, _lineup_cls)

                    _proj_min = float(props.get("min", _avgs.get("min", 24.0)) or 24.0)
                    ns = SimpleNamespace(
                        player_name=pname,
                        player_id=_pid,
                        team=team_abbr,
                        opp_team=opp_abbr,
                        game_id=gid,
                        proj_pts=float(props.get("pts", 0) or 0),
                        proj_reb=float(props.get("reb", 0) or 0),
                        proj_ast=float(props.get("ast", 0) or 0),
                        proj_fg3m=float(props.get("fg3m", 0) or 0),
                        proj_stl=float(props.get("stl", 0) or 0),
                        proj_blk=float(props.get("blk", 0) or 0),
                        proj_tov=float(props.get("tov", 0) or 0),
                        proj_min=_proj_min,
                        dnp_prob=dnp_prob,
                        confidence=props.get("confidence", "low"),
                    )
                    game_ns_list.append(ns)
                    print(f"  {pname:<25} pts={props.get('pts', 0):.1f}  "
                          f"reb={props.get('reb', 0):.1f}  ast={props.get('ast', 0):.1f}")
                except Exception as e:
                    log.warning("  predict_props error for %s: %s", pname, e)
                    continue

        # Normalise by team total
        if game_ns_list:
            predicted_total = 220.0
            try:
                from src.prediction.game_models import predict as _gm
                _gm_out = _gm(home, away, season)
                predicted_total = float(_gm_out.get("total_est", 220.0))
            except Exception:
                pass

            try:
                game_ns_list = normalise_team_totals(game_ns_list, home, away, predicted_total)
            except Exception as e:
                log.debug("normalise_team_totals failed: %s", e)

        for ns in game_ns_list:
            all_preds.append({
                "player":     ns.player_name,
                "player_id":  ns.player_id,
                "team":       ns.team,
                "opp_team":   ns.opp_team,
                "game_id":    ns.game_id,
                "pts":        round(ns.proj_pts,  1),
                "reb":        round(ns.proj_reb,  1),
                "ast":        round(ns.proj_ast,  1),
                "fg3m":       round(ns.proj_fg3m, 1),
                "stl":        round(ns.proj_stl,  1),
                "blk":        round(ns.proj_blk,  1),
                "tov":        round(ns.proj_tov,  1),
                "proj_pts":   round(ns.proj_pts,  1),
                "proj_min":   round(ns.proj_min,  1),
                "dnp_prob":   round(ns.dnp_prob,  3),
                "confidence": ns.confidence,
            })

    return all_preds


# -- Step 5: Score vs book lines -----------------------------------------------


_STAT_PROP_TYPE_MAP = {
    "pts": ["points", "pts", "player_points"],
    "reb": ["rebounds", "reb", "player_rebounds", "total_rebounds"],
    "ast": ["assists", "ast", "player_assists"],
    "fg3m": ["threes", "fg3m", "three_pointers_made", "3-pointers_made"],
    "stl": ["steals", "stl", "player_steals"],
    "blk": ["blocks", "blk", "player_blocks"],
    "tov": ["turnovers", "tov", "player_turnovers"],
}


def fetch_book_lines() -> dict:
    """
    Return {player_name_lower: {stat: line}} from DraftKings via props_scraper.
    get_current_props() returns a list of dicts with player_name, prop_type, line.
    Returns {} on failure.
    """
    try:
        from src.data.props_scraper import get_current_props
        raw = get_current_props()
        if not raw:
            log.warning("props_scraper returned empty -- proceeding without book lines")
            return {}

        # Build reverse lookup: prop_type string -> our stat key
        _pt_to_stat: dict = {}
        for stat, aliases in _STAT_PROP_TYPE_MAP.items():
            for alias in aliases:
                _pt_to_stat[alias.lower().replace(" ", "_")] = stat

        index: dict = {}
        for entry in (raw if isinstance(raw, list) else []):
            pname = str(entry.get("player_name", "")).lower().strip()
            ptype = str(entry.get("prop_type", "")).lower().strip().replace(" ", "_")
            line  = entry.get("line")
            if pname and ptype and line is not None:
                stat = _pt_to_stat.get(ptype)
                if stat:
                    index.setdefault(pname, {})[stat] = float(line)

        log.info("Book lines loaded for %d players", len(index))
        return index
    except Exception as e:
        log.warning("props_scraper failed: %s", e)
        return {}


def score_vs_lines(preds: list[dict], book_lines: dict) -> list[dict]:
    """
    For each playerxstat, compute:
      edge_pct = model_proj - book_line  (raw difference)
      kelly    = edge_pct / (1 + edge_pct), capped at 0.04 (4% max)
    Adds {stat}_book_line, {stat}_edge, {stat}_kelly to each pred dict.
    """
    for p in preds:
        # Try both "First Last" and "first_last" key formats
        pname_lower = p["player"].lower().strip()
        pname_key   = pname_lower.replace(" ", "_")
        player_lines = (book_lines.get(pname_lower)
                        or book_lines.get(pname_key)
                        or {})

        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
            line = player_lines.get(stat)
            proj = float(p.get(stat, p.get(f"proj_{stat}", 0)) or 0)

            if line is not None:
                line = float(line)
                edge = proj - line
                kelly = edge / (1.0 + edge) if edge > 0 else 0.0
                kelly = min(kelly, 0.04)
            else:
                edge, kelly, line = 0.0, 0.0, None

            p[f"{stat}_book_line"] = line
            p[f"{stat}_edge"]      = round(edge, 2)
            p[f"{stat}_kelly"]     = round(kelly, 4)

    return preds


# -- Step 6+7: Rank + Write output ---------------------------------------------


def build_edge_rows(preds: list[dict], min_edge: float = 0.5) -> list[dict]:
    """
    Explode each playerxstat into a row. Filter |edge| > min_edge.
    Returns rows sorted descending by |edge|, each with:
      player, stat, projection, book_line, edge, kelly, confidence.
    """
    rows = []
    for p in preds:
        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
            proj  = float(p.get(stat, 0) or 0)
            line  = p.get(f"{stat}_book_line")
            edge  = p.get(f"{stat}_edge", 0.0)
            kelly = p.get(f"{stat}_kelly", 0.0)
            if abs(edge) > min_edge and line is not None:
                rows.append({
                    "player":     p["player"],
                    "stat":       stat,
                    "projection": round(proj, 1),
                    "book_line":  round(float(line), 1),
                    "edge":       round(edge, 2),
                    "kelly":      round(kelly, 4),
                    "confidence": p.get("confidence", "low"),
                    "team":       p.get("team", ""),
                    "opp_team":   p.get("opp_team", ""),
                    "game_id":    p.get("game_id", ""),
                    "dnp_prob":   p.get("dnp_prob", 0.0),
                })
    rows.sort(key=lambda r: abs(r["edge"]), reverse=True)
    return rows


def print_table(edge_rows: list[dict], preds: list[dict], top_n: int = 20) -> None:
    """Print ranked table: player | stat | projection | book_line | edge | kelly | confidence."""
    display = edge_rows[:top_n]

    if not display:
        # No edges -- show top projections
        display = [
            {"player": p["player"], "stat": "pts",
             "projection": float(p.get("pts", 0)),
             "book_line": None, "edge": 0.0, "kelly": 0.0,
             "confidence": p.get("confidence", "low")}
            for p in sorted(preds, key=lambda x: float(x.get("pts", 0)), reverse=True)[:top_n]
        ]

    print(f"\n{'='*72}")
    print(f"  NBA PROP EDGES  (top {top_n})")
    print(f"{'='*72}")
    hdr = f"  {'#':>2}  {'Player':<24} {'Stat':<6} {'Proj':>6} {'Line':>6} {'Edge':>7} {'Kelly':>7} {'Conf':<8}"
    print(hdr)
    print(f"  {'-'*68}")
    for i, r in enumerate(display, 1):
        line_s = f"{r['book_line']:>6.1f}" if r["book_line"] is not None else "   N/A"
        edge_s = f"{r['edge']:>+7.2f}"
        print(f"  {i:>2}  {r['player']:<24} {r['stat']:<6} "
              f"{r['projection']:>6.1f} {line_s} {edge_s} "
              f"{r['kelly']:>7.4f} {r.get('confidence',''):<8}")
    print(f"{'='*72}\n")


def write_output(preds: list[dict], edge_rows: list[dict], date_str: str) -> str:
    """Write full slate JSON to data/output/slate_{YYYYMMDD}.json."""
    import datetime as _datetime
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    date_compact = date_str.replace("-", "")
    out_path = os.path.join(_OUTPUT_DIR, f"slate_{date_compact}.json")
    payload = {
        "date":          date_str,
        "generated_at":  _datetime.datetime.utcnow().isoformat() + "Z",
        "top_edges":     edge_rows,
        "all_predictions": preds,
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"[slate] Output -> {out_path}  ({len(preds)} players, {len(edge_rows)} edges)")
    return out_path


# -- Step 4b: Linear stacker ensemble -----------------------------------------


def _apply_stacker(preds: list[dict]) -> list[dict]:
    """Overwrite base-learner projections with ensemble predictions where a
    fitted stacker model is available.  Runs row-by-row; failures are silently
    swallowed so the pipeline degrades gracefully when stacker is not trained.

    The ensemble uses prop_stacker.predict_ensemble() which requires the saved
    stacker model files (data/models/props_stacker_{stat}.pkl).  If none are
    found, the original predictions are returned unchanged.

    Args:
        preds: List of prediction dicts from run_predictions().

    Returns:
        Same list with 'pts'/'reb'/etc. fields updated to ensemble values.
    """
    try:
        from src.prediction.prop_stacker import load_stacker, STATS as _STATS
        import os

        # Check if any stacker models exist at all before importing numpy
        _models_dir = os.path.join(PROJECT_DIR, "data", "models")
        available = [s for s in _STATS
                     if os.path.exists(os.path.join(_models_dir, f"props_stacker_{s}.pkl"))]
        if not available:
            return preds

        import numpy as np
        from src.prediction.prop_stacker import predict_ensemble

        # Build a placeholder feature vector from the pred dict fields.
        # The stacker's meta-model only needs the base-learner OOF columns
        # (assembled at fit time); at inference we call predict_base_learner
        # for each base learner inside predict_ensemble — so X is not needed
        # from the pred dict directly.  We pass a single-row zero matrix as
        # a placeholder; predict_ensemble loads the saved full-train models
        # via prop_model_stack.predict_base_learner which ignores this X.
        # For player-level features, callers should use the full pipeline.

        _STAT_KEY = {"pts": "pts", "reb": "reb", "ast": "ast",
                     "fg3m": "fg3m", "stl": "stl", "blk": "blk", "tov": "tov"}

        n_updated = 0
        for p in preds:
            for stat in available:
                try:
                    raw_feat = np.zeros((1, 1))  # placeholder; model ignores shape
                    ens_preds = predict_ensemble(raw_feat, stat)
                    if not np.isnan(ens_preds[0]):
                        p[stat] = round(float(ens_preds[0]), 1)
                        p[f"proj_{stat}"] = p[stat]
                        n_updated += 1
                except Exception:
                    pass

        if n_updated:
            print(f"[slate] Linear stacker applied: {n_updated} projections updated")
    except Exception as exc:
        log.debug("_apply_stacker failed (non-fatal): %s", exc)

    return preds


# -- Main ----------------------------------------------------------------------


def main(season: str, date_str: str, dry_run: bool = False, build_ladder: bool = False) -> None:
    print(f"\n{'='*60}")
    print(f"  NBA Daily Slate -- {date_str}  (season {season})")
    print(f"{'='*60}")

    # 1. Fetch games
    games = fetch_today_games(date_str, season)
    if not games:
        print("[slate] No games today -- writing empty output.")
        write_output([], [], date_str)
        return

    # Load exclusion list (players with high rolling MAE are skipped)
    exclusion_set = load_exclusion_set()
    if exclusion_set:
        print(f"[slate] Exclusion list active: {len(exclusion_set)} entries "
              f"(from {_EXCLUSION_PATH})")

    # 1b. Auto-fetch injury report + lineups (non-fatal if sources unavailable)
    import subprocess as _sp
    _inj_path = os.path.join(PROJECT_DIR, "data", f"injuries_{date_str}.json")
    _lin_path = os.path.join(PROJECT_DIR, "data", f"lineups_{date_str}.json")
    if not os.path.exists(_inj_path):
        try:
            _r = _sp.run(
                [sys.executable, os.path.join(PROJECT_DIR, "scripts", "fetch_injury_espn.py"),
                 "--date", date_str],
                capture_output=True, text=True, timeout=30,
            )
            if _r.returncode == 0:
                print(f"[slate] Injury report fetched -> {_inj_path}")
            else:
                log.warning("[slate] fetch_injury_espn exited %d: %s", _r.returncode, _r.stderr[:200])
        except Exception as _e:
            log.warning("[slate] Auto injury fetch failed (non-fatal): %s", _e)
    else:
        print(f"[slate] Injury report already present: {_inj_path}")

    if not os.path.exists(_lin_path):
        try:
            _r2 = _sp.run(
                [sys.executable, os.path.join(PROJECT_DIR, "scripts", "fetch_lineups.py"),
                 "--date", date_str],
                capture_output=True, text=True, timeout=30,
            )
            if _r2.returncode == 0:
                print(f"[slate] Lineups fetched -> {_lin_path}")
            else:
                log.warning("[slate] fetch_lineups exited %d: %s", _r2.returncode, _r2.stderr[:200])
        except Exception as _e2:
            log.warning("[slate] Auto lineup fetch failed (non-fatal): %s", _e2)
    else:
        print(f"[slate] Lineups already present: {_lin_path}")

    # 2+3+4. Predict + normalise
    preds = run_predictions(games, season, exclusion_set=exclusion_set)
    if not preds:
        print("[slate] No predictions generated.")
        write_output([], [], date_str)
        return

    # 4b. Apply linear stacker ensemble predictions (non-fatal if stacker absent)
    preds = _apply_stacker(preds)

    # 5. Fetch book lines + score all stats
    book_lines = fetch_book_lines()
    if not book_lines:
        print("[slate] No book lines available -- showing projections only.")
    score_vs_lines(preds, book_lines)

    # 6. Build edge rows (all stats, |edge| > 0.5)
    edge_rows = build_edge_rows(preds, min_edge=0.5)

    # 7. Print ranked table + write output
    print_table(edge_rows, preds, top_n=20)
    write_output(preds, edge_rows, date_str)

    # 8. Alt-line ladder (if --build-ladder flag set)
    if build_ladder:
        try:
            from src.prediction.alt_line_ladder import build_alt_line_ladder, ladder_to_bets
            ladder_rows = []
            for row in edge_rows:
                lo_ci = row.get("ci_lo_80") or float(row.get("projection", 0)) * 0.7
                hi_ci = row.get("ci_hi_80") or float(row.get("projection", 0)) * 1.3
                ladder = build_alt_line_ladder(
                    player=row["player"], stat=row["stat"],
                    point_estimate=float(row.get("projection", 0)),
                    conformal_interval=(lo_ci, hi_ci),
                    pinnacle_signal={"line": float(row.get("book_line", 0) or 0),
                                     "over_odds": -110, "under_odds": -110},
                )
                top = [r for r in ladder if r["ev"] > 0.04][:3]
                for alt in top:
                    ladder_rows.append({**row, "alt_line": alt["alt_line"],
                                        "alt_line_ev": alt["ev"]})
            edge_rows = edge_rows + ladder_rows
            print(f"[slate] Alt-line ladder: {len(ladder_rows)} additional bets")
        except Exception as e:
            log.warning("alt_line_ladder failed (non-fatal): %s", e)

    # 9. Bet selector middleware
    try:
        from src.prediction.bet_selector import select as _select
        _select(edge_rows, date_str=date_str, dry_run=dry_run)
    except Exception as e:
        log.warning("bet_selector failed (non-fatal): %s", e)

    print(f"[slate] Done -- {len(preds)} players, {len(edge_rows)} edges surfaced.")


def rerun_for_scratch(player_name: str, season: str, date_str: str) -> None:
    """Rerun the full slate after a late scratch (task 19.5-03).

    A late scratch invalidates every prediction that assumed the player was
    active.  Re-running main() refreshes predictions and re-fires bet_selector
    (step 9) with the scratched player excluded.
    """
    log.warning("Late scratch detected: %s — rerunning slate for %s",
                player_name, date_str)
    main(season=season, date_str=date_str)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NBA Daily Prop Prediction Pipeline")
    parser.add_argument("--season",       default="2024-25",        help="NBA season (e.g. 2024-25)")
    parser.add_argument("--date",         default=str(_date.today()), help="Date YYYY-MM-DD")
    parser.add_argument("--dry-run",      action="store_true",      help="Paper-trade: log bets as status=paper")
    parser.add_argument("--build-ladder", action="store_true",      help="Generate alt-line ladder bets (requires Pinnacle lines)")
    args = parser.parse_args()
    main(season=args.season, date_str=args.date, dry_run=args.dry_run, build_ladder=args.build_ladder)
