"""game_preview.py — assemble a GAME PREVIEW dossier for a date or a team pair.

This is a thin generator on top of :mod:`src.intel.matchup_report`. Given a
date (resolving every game on the slate) or an explicit home/away pair, it:

  1. resolves the matchup(s) from ``data/cache/games_lookup.json`` and/or the
     ``data/nba/season_games_<season>.json`` rows;
  2. resolves each team's roster (player_ids) from the per-date prediction
     caches (``data/cache/predictions_cache_<date>.parquet``), falling back to
     the most-recent team membership across all caches;
  3. calls :func:`src.intel.matchup_report.build_matchup_report` for each game;
  4. assembles a GAME PREVIEW dossier:
        - the descriptive matchup report,
        - a ranked TOP-5 EDGES list (player or scheme advantages),
        - the projected pace / possession ENVIRONMENT,
        - each team's KEY TO THE GAME (deterministic, from its own edges),
        - a clearly-labelled list of UNVALIDATED PREDICTIVE CANDIDATES.

HONESTY (the load-bearing rule of this build):
  * The matchup report + edges + keys are DESCRIPTIVE. They say how the game
    *projects to play*; they are leak-safe by nature and carry NO claimed
    accuracy lift.
  * The predictive hypotheses the matchup implies (e.g. "Player X PTS lean
    OVER because archetype Y attacks scheme Z") are emitted SEPARATELY under
    ``predictive_candidates``, each stamped ``status="UNVALIDATED_CANDIDATE"``
    and a ``gate`` block describing the honest gate (walk-forward + shadow) it
    must clear. NOTHING here is applied to any model. Tonight proved bulk
    atlas/matchup features need GATING — so these are candidates, not changes.

Public API:
    build_game_preview(home, away, ...) -> dict          # one game
    build_previews_for_date(date_str, ...) -> list[dict]  # whole slate
    resolve_games_for_date(date_str) -> list[dict]
    resolve_roster(team, date_str=None) -> list[int]

Schema documented on :func:`build_game_preview`.
"""
from __future__ import annotations

import datetime as _dt
import functools
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.intel import matchup_report as _mr
from src.intel import team_report as _tr

_ROOT = Path(__file__).resolve().parent.parent.parent
_CACHE = _ROOT / "data" / "cache"
_NBA = _ROOT / "data" / "nba"
_GAMES_LOOKUP = _CACHE / "games_lookup.json"

SCHEMA_VERSION = "game_preview/1.0"

# The honest gate every predictive candidate must clear before it can touch a
# model. Mirrors the project's dual-gate convention (walk-forward 4/4 folds AND
# single-split MAE strictly down) plus a shadow-deployment requirement.
_GATE_SPEC = {
    "status": "UNVALIDATED_CANDIDATE",
    "applied_to_model": False,
    "required_gates": [
        {
            "name": "walk_forward",
            "spec": "expanding-window walk-forward; candidate feature/adjustment "
                    "must improve target metric on ALL folds (4/4) — i.e. "
                    "neg_folds == 0 / all_improve == true",
        },
        {
            "name": "single_split_production",
            "spec": "production single-split MAE (or ROI for a bet lean) must be "
                    "strictly better than the no-candidate baseline",
        },
        {
            "name": "shadow",
            "spec": "log candidate lean vs realized outcome in shadow mode for "
                    ">=1 slate before any live wiring; check CLV/Brier, not just hit-rate",
        },
    ],
    "note": "Descriptive matchup signal ONLY. Bulk atlas/matchup features have "
            "historically failed the dual gate as redundant with usage/TS%/form; "
            "do NOT wire without passing all gates above.",
}


# --------------------------------------------------------------------------- #
# Game resolution
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=4)
def _load_games_lookup() -> Dict[str, Any]:
    if not _GAMES_LOOKUP.exists():
        return {}
    try:
        with open(_GAMES_LOOKUP, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _et_date_of_start(start_time: str) -> Optional[str]:
    """Map a UTC start_time (ISO 'Z') to its US-Eastern game date (YYYY-MM-DD).

    NBA tip-offs are evening ET, i.e. the UTC instant lands on the *next* UTC
    calendar day. ET = UTC-4/-5; subtracting 5h is a safe, dependency-free
    approximation that recovers the correct game date for all evening tips.
    """
    if not start_time:
        return None
    try:
        s = start_time.replace("Z", "+00:00")
        dt = _dt.datetime.fromisoformat(s)
    except Exception:
        return None
    et = dt - _dt.timedelta(hours=5)
    return et.date().isoformat()


def resolve_games_for_date(date_str: str) -> List[Dict[str, Any]]:
    """Return de-duplicated games on ``date_str`` (ET) from games_lookup +
    season_games. Each game: {home, away, label, start_time, source, season}.
    """
    seen: Dict[tuple, Dict[str, Any]] = {}

    # 1) games_lookup.json (current/near-term slate, multi-source aliased)
    for gid, g in _load_games_lookup().items():
        st = g.get("start_time")
        if _et_date_of_start(st) != date_str:
            continue
        home, away = g.get("home_abbr"), g.get("away_abbr")
        if not home or not away:
            continue
        key = (home, away)
        if key not in seen:
            seen[key] = {
                "home": home, "away": away,
                "label": g.get("label") or f"{away} @ {home}",
                "start_time": st, "source": "games_lookup", "season": None,
            }

    # 2) season_games rows (historical / scheduled, has game_date directly)
    for season_file in sorted(_NBA.glob("season_games_*.json")):
        try:
            with open(season_file, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except Exception:
            continue
        rows = doc.get("rows") if isinstance(doc, dict) else doc
        if not isinstance(rows, list):
            continue
        season = doc.get("season") if isinstance(doc, dict) else None
        for r in rows:
            if r.get("game_date") != date_str:
                continue
            home, away = r.get("home_team"), r.get("away_team")
            if not home or not away:
                continue
            key = (home, away)
            if key not in seen:
                seen[key] = {
                    "home": home, "away": away,
                    "label": f"{away} @ {home}",
                    "start_time": None, "source": season_file.name,
                    "season": season or r.get("season"),
                }
    return list(seen.values())


# --------------------------------------------------------------------------- #
# Roster resolution (player_ids per team)
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=8)
def _prediction_cache_for_date(date_str: str) -> Optional[pd.DataFrame]:
    path = _CACHE / f"predictions_cache_{date_str}.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path, columns=["player_id", "player_name", "team"])
    except Exception:
        try:
            return pd.read_parquet(path)
        except Exception:
            return None


@functools.lru_cache(maxsize=1)
def _global_roster_map() -> Dict[str, List[int]]:
    """team -> [player_ids] aggregated across ALL prediction caches (fallback).

    Uses the most-recent cache a player appears in to assign their team, so
    mid-season moves resolve to the latest team.
    """
    files = sorted(p for p in _CACHE.glob("predictions_cache_*.parquet")
                   if ".bak" not in p.name)
    player_team: Dict[int, str] = {}
    player_name: Dict[int, str] = {}
    for f in files:  # ascending date -> later files overwrite earlier
        try:
            df = pd.read_parquet(f, columns=["player_id", "player_name", "team"])
        except Exception:
            continue
        for pid, nm, tm in zip(df["player_id"], df["player_name"], df["team"]):
            try:
                pid = int(pid)
            except (TypeError, ValueError):
                continue
            player_team[pid] = tm
            player_name[pid] = nm
    out: Dict[str, List[int]] = {}
    for pid, tm in player_team.items():
        out.setdefault(tm, []).append(pid)
    return out


def resolve_roster(team: str, date_str: Optional[str] = None) -> List[int]:
    """Resolve a team's roster (player_ids).

    Preference order:
      1. the prediction cache FOR ``date_str`` (exact slate roster), then
      2. the global roster map aggregated across all caches (fallback).
    """
    if date_str:
        df = _prediction_cache_for_date(date_str)
        if df is not None and "team" in df.columns:
            sub = df[df["team"] == team]
            ids = sorted({int(p) for p in sub["player_id"].tolist()})
            if ids:
                return ids
    return sorted(_global_roster_map().get(team, []))


# --------------------------------------------------------------------------- #
# Edge ranking + keys-to-the-game
# --------------------------------------------------------------------------- #
def _rank_top_edges(matchup: Dict[str, Any], top_n: int = 5) -> List[Dict[str, Any]]:
    """Merge scheme + player edges into one magnitude-ranked top-N list."""
    pool: List[Dict[str, Any]] = []
    for e in matchup.get("scheme_edges", []):
        pool.append({**e, "edge_class": "scheme"})
    for e in matchup.get("player_edges", []):
        pool.append({**e, "edge_class": "player"})
    pool.sort(key=lambda e: e.get("magnitude", 0.0), reverse=True)
    ranked = pool[:top_n]
    for i, e in enumerate(ranked):
        e["rank"] = i + 1
    return ranked


def _keys_to_game(matchup: Dict[str, Any], home: str, away: str) -> Dict[str, List[str]]:
    """One or two deterministic 'keys to the game' per team from its own edges."""
    keys: Dict[str, List[str]] = {home: [], away: []}
    tc = matchup.get("team_clash", {})

    # scheme edges -> the attacking team's key
    for e in matchup.get("scheme_edges", [])[:6]:
        atk = e.get("attacker")
        if atk in keys and len(keys[atk]) < 3:
            keys[atk].append(f"Exploit {e['tag']}: {e['description']}.")

    # top player edges -> that player's team key
    for e in matchup.get("player_edges", [])[:6]:
        tm = e.get("team")
        if tm in keys and len(keys[tm]) < 3:
            keys[tm].append(f"Feed {e['player_name']} — {e['skill']}.")

    # rebounding battle key
    reb = tc.get("rebounding_battle", {})
    hov = reb.get("home_oreb_vs_away_dreb")
    aov = reb.get("away_oreb_vs_home_dreb")
    if hov is not None and hov > 0.02 and len(keys[home]) < 3:
        keys[home].append("Win the offensive glass for extra possessions.")
    if aov is not None and aov > 0.02 and len(keys[away]) < 3:
        keys[away].append("Win the offensive glass for extra possessions.")

    # fallback generic key per team if nothing fired
    for t in (home, away):
        if not keys[t]:
            keys[t].append("Control pace and execute base offense efficiently.")
    return keys


# --------------------------------------------------------------------------- #
# Predictive candidates (UNVALIDATED — flagged for the honest gate)
# --------------------------------------------------------------------------- #
def _stat_for_skill(skill_metric: str) -> Optional[str]:
    """Map a player-edge skill metric to the prop stat its lean would touch."""
    return {
        "oreb_rate": "reb",
        "total_reb_rate": "reb",
        "pts_3pt_share": "fg3m",
        "catch_shoot_efg": "fg3m",
        "rim_protection": "blk",
        "ft_generation": "pts",
        "ast_pts_created": "ast",
        "post_up_ppp": "pts",
        "transition_pts_share": "pts",
    }.get(skill_metric)


def _build_predictive_candidates(matchup: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Translate the descriptive edges into UNVALIDATED predictive hypotheses.

    Each candidate states the *direction* the matchup implies and is stamped
    with the honest-gate spec. These are NOT predictions and NOT applied to any
    model — they are leads for the gating harness to test out-of-sample.
    """
    cands: List[Dict[str, Any]] = []

    # ---- player-prop leans from player_edges ------------------------------
    for e in matchup.get("player_edges", []):
        stat = _stat_for_skill(e.get("skill_metric", ""))
        if stat is None:
            continue
        cands.append({
            "candidate_type": "player_prop_lean",
            "player_id": e.get("player_id"),
            "player_name": e.get("player_name"),
            "team": e.get("team"),
            "vs_team": e.get("vs_team"),
            "stat": stat,
            "direction": "OVER",
            "rationale": (f"{e.get('player_name')} grades {e.get('player_percentile')}th-pct "
                          f"in {e.get('skill')} into a {e.get('opp_team_pctile', 0)*100:.0f}th-pct "
                          f"opposing unit ({e.get('vs_team')})."),
            "implied_magnitude": e.get("magnitude"),
            "basis_metric": e.get("skill_metric"),
            "opp_basis_metric": e.get("opp_team_metric"),
            "gate": dict(_GATE_SPEC),
        })

    # ---- team total / pace lean from pace environment ---------------------
    pace = (matchup.get("team_clash") or {}).get("pace_environment") or {}
    env = pace.get("pace_environment")
    if env in ("fast", "slow"):
        cands.append({
            "candidate_type": "game_total_lean",
            "stat": "game_total",
            "direction": "OVER" if env == "fast" else "UNDER",
            "rationale": (f"Projected pace {pace.get('projected_pace')} -> {env} "
                          f"possession environment (descriptive midpoint, not a "
                          f"possession-model output)."),
            "implied_magnitude": None,
            "gate": dict(_GATE_SPEC),
        })

    # ---- team-scheme lean from scheme_edges (top 3) -----------------------
    for e in matchup.get("scheme_edges", [])[:3]:
        cands.append({
            "candidate_type": "team_scheme_lean",
            "attacker": e.get("attacker"),
            "defender": e.get("defender"),
            "tag": e.get("tag"),
            "direction": "attacker_advantage",
            "rationale": e.get("description"),
            "implied_magnitude": e.get("magnitude"),
            "gate": dict(_GATE_SPEC),
        })

    cands.sort(key=lambda c: (c.get("implied_magnitude") or 0.0), reverse=True)
    return cands


# --------------------------------------------------------------------------- #
# Public entrypoints
# --------------------------------------------------------------------------- #
def build_game_preview(
    home: str,
    away: str,
    date_str: Optional[str] = None,
    home_roster: Optional[List[int]] = None,
    away_roster: Optional[List[int]] = None,
    team_ctx: Optional[Dict] = None,
    atlases: Optional[Dict] = None,
    label: Optional[str] = None,
    start_time: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble ONE game preview dossier.

    Returns a dict with this schema::

        {
          "schema_version": "game_preview/1.0",
          "home": str, "away": str, "label": "AWAY @ HOME",
          "date": str | None, "start_time": str | None,
          "generated_at": ISO date,

          # ---- DESCRIPTIVE (leak-safe, no claimed lift) ----
          "matchup_report": <matchup_report/1.0 dict>,
          "top_edges": [ {rank, edge_class:"scheme"|"player", magnitude,
                          description, ...} ... ],          # top 5, desc magnitude
          "pace_environment": { home_pace, away_pace, projected_pace,
                                pace_environment: "fast"|"average"|"slow", ... },
          "keys_to_the_game": { <home>: [str...], <away>: [str...] },

          # ---- UNVALIDATED (flagged for the honest gate; NOT applied) ----
          "predictive_candidates": [
              { "candidate_type": "player_prop_lean"|"game_total_lean"|
                                   "team_scheme_lean",
                "status": "UNVALIDATED_CANDIDATE",   # (from gate)
                "direction": "OVER"|"UNDER"|"attacker_advantage",
                "rationale": str,
                "gate": { status, applied_to_model:false, required_gates:[...] },
                ... },
          ],
          "candidate_disclaimer": str,
          "completeness": {...},
        }

    The ``predictive_candidates`` block is the ONLY predictive surface and every
    entry is explicitly ``status="UNVALIDATED_CANDIDATE"`` with
    ``applied_to_model=false``. The descriptive blocks make no accuracy claim.
    """
    if atlases is None:
        atlases = _tr.load_team_atlases()
    if team_ctx is None:
        team_ctx = _tr.build_league_context(atlases)

    if home_roster is None:
        home_roster = resolve_roster(home, date_str)
    if away_roster is None:
        away_roster = resolve_roster(away, date_str)

    matchup = _mr.build_matchup_report(
        home, away, home_roster=home_roster, away_roster=away_roster,
        team_ctx=team_ctx, atlases=atlases)

    top_edges = _rank_top_edges(matchup, top_n=5)
    pace_env = (matchup.get("team_clash") or {}).get("pace_environment") or {}
    keys = _keys_to_game(matchup, home, away)
    candidates = _build_predictive_candidates(matchup)
    # surface the status on each candidate (mirrors the gate.status)
    for c in candidates:
        c["status"] = c["gate"]["status"]

    preview: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "home": home,
        "away": away,
        "label": label or f"{away} @ {home}",
        "date": date_str,
        "start_time": start_time,
        "generated_at": _dt.date.today().isoformat(),
        # descriptive
        "matchup_report": matchup,
        "top_edges": top_edges,
        "pace_environment": pace_env,
        "keys_to_the_game": keys,
        # unvalidated predictive surface
        "predictive_candidates": candidates,
        "candidate_disclaimer": (
            "predictive_candidates are UNVALIDATED hypotheses implied by the "
            "descriptive matchup. They are NOT applied to any model and carry NO "
            "claimed accuracy lift. Each must clear walk-forward (4/4 folds) + "
            "single-split production + a shadow slate before any wiring."
        ),
        "completeness": matchup.get("completeness"),
    }
    return preview


def build_previews_for_date(
    date_str: str,
    max_games: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Build a preview for every game resolved on ``date_str`` (shares ctx)."""
    games = resolve_games_for_date(date_str)
    if max_games is not None:
        games = games[:max_games]
    atlases = _tr.load_team_atlases()
    team_ctx = _tr.build_league_context(atlases)
    previews: List[Dict[str, Any]] = []
    for g in games:
        previews.append(build_game_preview(
            g["home"], g["away"], date_str=date_str,
            team_ctx=team_ctx, atlases=atlases,
            label=g.get("label"), start_time=g.get("start_time")))
    return previews


if __name__ == "__main__":  # pragma: no cover
    import argparse

    ap = argparse.ArgumentParser(description="Build NBA game preview dossier(s).")
    ap.add_argument("--date", help="slate date YYYY-MM-DD (builds all games)")
    ap.add_argument("--home", help="home tricode (single-game mode)")
    ap.add_argument("--away", help="away tricode (single-game mode)")
    ap.add_argument("--edges-only", action="store_true",
                    help="print only top_edges + candidates")
    args = ap.parse_args()

    if args.date and not (args.home and args.away):
        out = build_previews_for_date(args.date)
    elif args.home and args.away:
        out = [build_game_preview(args.home, args.away, date_str=args.date)]
    else:
        ap.error("provide --date (slate) or --home/--away (single game)")

    if args.edges_only:
        for p in out:
            print(f"\n=== {p['label']} ===")
            for e in p["top_edges"]:
                print(f"  [{e['rank']}] ({e['edge_class']}) {e.get('description')}")
            print("  -- UNVALIDATED candidates --")
            for c in p["predictive_candidates"]:
                print(f"    * {c['candidate_type']} {c.get('direction')} "
                      f"[{c['status']}]: {c.get('rationale')}")
    else:
        print(json.dumps(out, indent=2, default=str))
