"""domains.basketball_nba.knowledge.validate_transition_frequency -- rebuilds
mechanism #28 (transition-frequency pace mismatch) from EVENT-LEVEL pbp shot
data, closing the leak that made the box-score approach NOT_TESTABLE:
`atlas_team_transition_defense.parquet` was a single-season, one-row-per-team
aggregate (n=30) -- using it as a per-game feature for games drawn from that
same season is the season-final-aggregate-as-feature leak this codebase
forbids (mechanisms.md #28).

Transition definition (REUSED, not reinvented -- ponytail rung 2): a shot
attempt within TRANSITION_WINDOW_S=6.0s of its own possession start, the same
possession-segment chain domains.basketball_nba.composition.shot_clock_proxy
already builds and domains.basketball_nba.composition.transition_flag already
validates against the real 'fastbreak' qualifier on CDN pbp files (recall
>0.5 there). A possession start is itself defined by the standard triggers:
defensive rebound, steal/turnover, or the opponent's made basket -- so this
IS the "def-rebound/steal -> quick shot" cut, just expressed via the existing
possession-segment machinery instead of a fresh rebound/steal scanner.

Leak-free construction: for each team, AS-OF trailing transition_rate = the
running mean of that team's OWN transition_rate over STRICTLY PRIOR games
only (current/future games excluded via shift(1) before the expanding mean).
This is the game-level rebuild mechanisms.md #28 called for; unlike the
season-final n=30 aggregate, an as-of value on game k never sees game k.

Two validator legs (mirrors the split-half + margin-relation idiom already
used elsewhere in this ledger, e.g. #1, #26):
  1. persistence: split-half (odd/even game occasion) pearson r of a team's
     raw transition_rate -- is the rate a persistent team tendency, not
     game-to-game noise?
  2. margin relation: pearson r of (asof transition_rate, home - away) vs
     home_margin, leak-free (as-of only, MIN_PRIOR_GAMES burn-in) -- does the
     trailing rate differential track the efficiency edge (point margin)?

Corpus: data/cache/team_system/pbp (CDN pbp actions, season 2025-26 only --
the one season with per-game event files on disk locally).

Run: python -m domains.basketball_nba.knowledge.validate_transition_frequency
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.basketball_nba.composition.shot_clock_proxy import _PBP_DIR, _detect_mode, resolve_segments
from domains.basketball_nba.composition.transition_flag import TRANSITION_WINDOW_S
from domains.basketball_nba.knowledge._data import LEDGER_PATH, REPO
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
GAMES_PATH = REPO / "data" / "domains" / "basketball_nba" / "games.parquet"
MIN_PRIOR_GAMES = 5          # as-of burn-in before a team's trailing rate is used
MIN_SHOTS_FOR_ROW = 5        # drop a team/game row built from too few shot attempts


def _verdict(p, min_abs_effect: float, effect) -> str:
    if p is None or effect is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def build_team_game_transition_frame(pbp_dir=_PBP_DIR, limit: int = None) -> pd.DataFrame:
    """One row per (game_id, team): shot attempts, transition shots,
    transition_rate, is_home, and that team's final-score margin -- built
    directly from event-level CDN pbp actions (reuses shot_clock_proxy's
    possession-segment chain + transition_flag's TRANSITION_WINDOW_S cut)."""
    games = pd.read_parquet(GAMES_PATH)[["game_id", "date", "home_team", "away_team"]]
    home_map = dict(zip(games["game_id"], games["home_team"]))
    away_map = dict(zip(games["game_id"], games["away_team"]))
    date_map = dict(zip(games["game_id"], games["date"]))

    files = sorted(pbp_dir.glob("*.json"))
    if limit:
        files = files[:limit]
    rows: List[Dict[str, Any]] = []
    for fp in files:
        d = json.loads(fp.read_text(encoding="utf-8"))
        game_id = d["game"]["gameId"]
        if game_id not in home_map:
            continue
        actions = d["game"]["actions"]
        mode = _detect_mode(actions)
        resolved = {r["action_number"]: r for r in resolve_segments(actions, mode=mode)}
        by_team: Dict[str, Dict[str, int]] = {}
        score_home = score_away = 0
        for a in actions:
            score_home = max(score_home, int(a.get("scoreHome") or 0))
            score_away = max(score_away, int(a.get("scoreAway") or 0))
            if a.get("actionType") not in ("2pt", "3pt") or not a.get("teamId"):
                continue
            r = resolved[a["actionNumber"]]
            if r["seg_team"] is None:
                continue  # unresolved (first action(s) of a period) -- skip
            tri = a.get("teamTricode")
            if not tri:
                continue
            since_start = r["elapsed_s"] - r["seg_start_s"]
            s = by_team.setdefault(tri, {"n_shots": 0, "n_transition": 0})
            s["n_shots"] += 1
            s["n_transition"] += int(0 <= since_start <= TRANSITION_WINDOW_S)

        home_tri, away_tri = home_map[game_id], away_map[game_id]
        for tri, s in by_team.items():
            if s["n_shots"] < MIN_SHOTS_FOR_ROW or tri not in (home_tri, away_tri):
                continue
            margin = (score_home - score_away) if tri == home_tri else (score_away - score_home)
            rows.append({
                "game_id": game_id, "team": tri, "date": date_map[game_id],
                "is_home": int(tri == home_tri), "n_shots": s["n_shots"],
                "n_transition": s["n_transition"], "transition_rate": s["n_transition"] / s["n_shots"],
                "margin": margin,
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def add_asof_trailing_rate(tg: pd.DataFrame) -> pd.DataFrame:
    """Adds asof_transition_rate = running mean of transition_rate over each
    team's STRICTLY PRIOR games (shift(1) before the expanding mean) and
    asof_n_prior = count of those prior games -- the leak-free feature."""
    tg = tg.sort_values(["team", "date", "game_id"]).reset_index(drop=True)
    tg["asof_transition_rate"] = tg.groupby("team")["transition_rate"].transform(
        lambda s: s.shift(1).expanding().mean())
    tg["asof_n_prior"] = tg.groupby("team").cumcount()
    return tg


def transition_rate_split_half_persistence(tg: pd.DataFrame) -> Dict[str, Any]:
    d = tg.sort_values(["team", "date", "game_id"]).copy()
    d["occ_rank"] = d.groupby("team").cumcount()
    d["half"] = np.where(d["occ_rank"] % 2 == 0, "A", "B")
    piv = d.groupby(["team", "half"])["transition_rate"].mean().unstack("half").dropna()
    if len(piv) < 10:
        return {"hypothesis": "transition_rate_split_half_persistence", "n": int(len(piv)),
                "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than 10 teams with both split halves populated"}
    r, p = stats.pearsonr(piv["A"], piv["B"])
    return {"hypothesis": "transition_rate_split_half_persistence", "n": int(len(piv)),
            "effect": round(float(r), 4), "p": float(p), "verdict": _verdict(p, 0.3, r),
            "note": "split-half (odd/even game occasion) pearson r of team transition_rate, "
                    "%d teams, season 2025-26" % len(piv)}


def transition_rate_margin_relation(tg: pd.DataFrame) -> Dict[str, Any]:
    d = add_asof_trailing_rate(tg)
    d = d[d["asof_n_prior"] >= MIN_PRIOR_GAMES]
    home = d[d["is_home"] == 1][["game_id", "asof_transition_rate", "margin"]].rename(
        columns={"asof_transition_rate": "asof_home"})
    away = d[d["is_home"] == 0][["game_id", "asof_transition_rate"]].rename(
        columns={"asof_transition_rate": "asof_away"})
    m = home.merge(away, on="game_id").dropna()
    if len(m) < 30:
        return {"hypothesis": "transition_rate_margin_relation", "n": int(len(m)), "effect": None,
                "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than 30 games with both sides past the as-of burn-in"}
    diff = m["asof_home"] - m["asof_away"]
    r, p = stats.pearsonr(diff, m["margin"])
    return {"hypothesis": "transition_rate_margin_relation", "n": int(len(m)),
            "effect": round(float(r), 4), "p": float(p), "verdict": _verdict(p, 0.05, r),
            "note": "pearson r of (asof trailing transition_rate, home-away) vs home_margin, "
                    "leak-free as-of (>=%d prior games), n=%d games, season 2025-26"
                    % (MIN_PRIOR_GAMES, len(m))}


def run() -> List[Dict[str, Any]]:
    tg = build_team_game_transition_frame()
    persistence = transition_rate_split_half_persistence(tg)
    margin = transition_rate_margin_relation(tg)
    both_confirmed = persistence["verdict"] == "CONFIRMED_LOCAL" and margin["verdict"] == "CONFIRMED_LOCAL"
    either_not_testable = persistence["verdict"] == "NOT_TESTABLE" or margin["verdict"] == "NOT_TESTABLE"
    combined_verdict = "NOT_TESTABLE" if either_not_testable else (
        "CONFIRMED_LOCAL" if both_confirmed else "NULL_LOCAL")
    combined = {
        "hypothesis": "transition_frequency_pace_mismatch__combined", "n": int(len(tg)),
        "effect": None, "p": None, "verdict": combined_verdict,
        "note": "persistence(%s,r=%s,p=%s); margin_relation(%s,r=%s,p=%s) -- CONFIRMED_LOCAL "
                "requires both legs; mechanisms.md #28"
                % (persistence["verdict"], persistence["effect"], persistence["p"],
                   margin["verdict"], margin["effect"], margin["p"]),
    }
    rows = [persistence, margin, combined]
    for r in rows:
        r["sport"] = "basketball_nba"
        r["corpus"] = "team_system_pbp_actions+games (event-level, season 2025-26)"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-42s %-16s n=%-6d effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.05, 0.2) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.05, 0.2) == "NULL_LOCAL"
    assert _verdict(None, 0.05, 0.2) == "NOT_TESTABLE"
    print("self-check OK")
