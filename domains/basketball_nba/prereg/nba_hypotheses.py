"""domains.basketball_nba.prereg.nba_hypotheses -- the 10 NBA coach-mechanism
hypotheses preregistered in docs/research/coach_composition_architecture_
2026_07_08.md section (d), run at the ATOMIC unit named in the doc.

METHOD (per hypothesis, no invention beyond what the doc names):
  1. PREMISE-CHECK the data. 7 of 10 need a label that does not exist on this
     corpus (defensive coverage type, help-defense rate, paint touches, shot
     clock, player height, post-up rate) and the doc names no proxy for any
     of them -- those are BLOCKED-on-premise, not tested.
  2. The 3 with data present get an interaction (or, where the doc names
     only ONE factor, a single-predictor) logistic/OLS fit; the interaction/
     main-term's own p-value is compared against alpha_fwer(K) where K is
     the count of hypotheses actually TESTED this run (BLOCKED does not
     count -- there is no test to correct for).

Descriptive/measurement only. edge_claimed hard-wired False (stats_common).
NETWORK: zero. CLI: python -m domains.basketball_nba.prereg.nba_hypotheses
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from domains.basketball_nba.composition.shot_features import add_spacing
from domains.basketball_nba.lineups.pbp_lineups import _elapsed_s, _period_length_s
from domains.basketball_nba.prereg.stats_common import (
    LEDGER_PATH, alpha_fwer, append_ledger, blocked_row, fit_interaction, fit_single, tested_row,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
_PBP_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "pbp"
_STINTS_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "stints_2025_26.parquet"
_GAMES_PATH = REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"

SPORT = "nba"
MIN_LINEUP_ELAPSED_S = 300.0  # >=5 min floor before a lineup's net rating is trusted

# ---- premise-check: the 7 hypotheses this census cannot test, verbatim doc names ----
BLOCKED_REASONS: Dict[str, str] = {
    "gravity x drop coverage": "no defensive-coverage-type label (switch/drop) exists "
        "anywhere in the PBP corpus (actionType in {2pt,3pt,freethrow,other,substitution} "
        "only); doc names no proxy -- not proxying with e.g. defender-distance.",
    "lineup spacing x transition frequency": "no possession pace-state / transition-vs-"
        "halfcourt flag exists on this corpus; doc names no proxy formula.",
    "on-court shooting gravity x opponent help-rate": "no help-defense / 'nail help' rate "
        "exists on this corpus (concession_profiles.py has zone eFG-allowed, not a help-"
        "rotation rate); doc names no proxy.",
    "ball-handler usage x screen coverage (switch vs drop)": "same coverage-type gap as "
        "gravity x drop coverage -- switch/drop is not a labeled field anywhere.",
    "spacing x late-clock (<=7s) efficiency": "raw PBP action has no shotClock field (only "
        "game clock 'PT#M#S'); the shot-clock-bucket artifacts referenced in the doc live "
        "under human-gated src/scripts/intel, out of scope for this lane's own census.",
    "on/off gravity x paint touches allowed": "no touch-tracking data; concession_profiles "
        "has zone eFG-ALLOWED (efficiency), not touch FREQUENCY, and the doc does not name "
        "efficiency as an accepted proxy for touches.",
    "lineup size (avg height) x opponent post-up rate": "no player-height column on "
        "player_boxscores.parquet, and no post-up subType label (observed shot subTypes: "
        "'', 'Jump Shot', 'Layup', 'DUNK', 'Hook' -- no post-up tag) -- both factors absent.",
}


def _team_tricode_map(pbp_dir: Path = _PBP_DIR, limit: int = 60) -> Dict[str, int]:
    """tricode -> team_id, scanned off a sample of PBP files (teamTricode is
    stable per team all season; games.parquet only carries the tricode)."""
    out: Dict[str, int] = {}
    for fp in sorted(pbp_dir.glob("*.json"))[:limit]:
        for a in json.loads(fp.read_text(encoding="utf-8"))["game"]["actions"]:
            if a.get("teamId") and a.get("teamTricode"):
                out[a["teamTricode"]] = a["teamId"]
        if len(out) >= 30:
            break
    return out


def _other_team(ids: List[int], tid: int):
    rest = [i for i in ids if i != tid]
    return rest[0] if len(rest) == 1 else None


def _lineup_net_ratings(clean: pd.DataFrame) -> pd.DataFrame:
    g = clean.groupby(["team_id", "lineup_key"]).agg(
        pts_for=("pts_for", "sum"), pts_against=("pts_against", "sum"), elapsed_s=("elapsed_s", "sum"),
    ).reset_index()
    g = g[g["elapsed_s"] >= MIN_LINEUP_ELAPSED_S].copy()
    g["net_per48"] = (g["pts_for"] - g["pts_against"]) / g["elapsed_s"] * 2880.0
    return g[["team_id", "lineup_key", "net_per48"]]


def build_matchup_rows(stints_df: pd.DataFrame, games_df: pd.DataFrame) -> pd.DataFrame:
    """h3: lineup_vs_lineup net-rating x rest differential (atomic=stint).
    ponytail: own_net_per48 is season-aggregated INCLUDING the row's own stint
    (same documented in-sample-descriptor limit as shooter_zone_efg elsewhere
    in this codebase) -- fine for a descriptive atomic test, not a leak-free claim."""
    clean = stints_df[stints_df["n_on_court"] == 5].copy()
    lineup_net = _lineup_net_ratings(clean)
    team_ids_by_game = clean.groupby("game_id")["team_id"].unique().apply(list).to_dict()
    clean["opp_team_id"] = clean.apply(lambda r: _other_team(team_ids_by_game[r["game_id"]], r["team_id"]), axis=1)
    clean = clean.dropna(subset=["opp_team_id"])
    clean["opp_team_id"] = clean["opp_team_id"].astype("int64")  # Windows: astype(int)==int32, breaks merge_asof dtype match

    right = clean[["game_id", "period", "team_id", "lineup_key", "start_s"]].rename(
        columns={"team_id": "opp_team_id", "lineup_key": "opp_lineup_key"})
    matched = pd.merge_asof(
        clean.sort_values("start_s"), right.sort_values("start_s"),
        on="start_s", by=["game_id", "period", "opp_team_id"], direction="backward",
    )
    matched = matched.merge(lineup_net, on=["team_id", "lineup_key"], how="inner")
    matched = matched.merge(
        lineup_net.rename(columns={"team_id": "opp_team_id", "lineup_key": "opp_lineup_key", "net_per48": "opp_net_per48"}),
        on=["opp_team_id", "opp_lineup_key"], how="inner",
    )

    tmap = _team_tricode_map()
    rest_rows = []
    for _, r in games_df.iterrows():
        for side, tricode_col, rest_col in (("home", "home_team", "rest_days_home"), ("away", "away_team", "rest_days_away")):
            tid = tmap.get(r[tricode_col])
            if tid is not None:
                rest_rows.append({"game_id": r["game_id"], "team_id": tid, "rest_days": r[rest_col]})
    rest_df = pd.DataFrame(rest_rows)
    matched = matched.merge(rest_df, on=["game_id", "team_id"], how="inner")
    matched = matched.merge(rest_df.rename(columns={"team_id": "opp_team_id", "rest_days": "opp_rest_days"}),
                             on=["game_id", "opp_team_id"], how="inner")

    matched = matched[matched["elapsed_s"] >= 10.0].copy()
    matched["margin_per48"] = (matched["pts_for"] - matched["pts_against"]) / matched["elapsed_s"] * 2880.0
    matched["matchup_net_diff"] = matched["net_per48"] - matched["opp_net_per48"]
    matched["rest_diff"] = matched["rest_days"] - matched["opp_rest_days"]
    return matched[["margin_per48", "matchup_net_diff", "rest_diff"]].dropna()


def _load_missed_shots_and_rebounds(pbp_dir: Path = _PBP_DIR, limit: int | None = None) -> pd.DataFrame:
    """h7: stint continuity x defensive-rebound rate (atomic=rebound). Rebounds
    are logged as actionType=='other' free-text ('X defensive rebound' /
    'X offensive rebound' / 'Team offensive team rebound') -- the ONLY source
    on this corpus (no distinct 'rebound' actionType)."""
    rows: List[Dict[str, Any]] = []
    files = sorted(pbp_dir.glob("*.json"))
    if limit:
        files = files[:limit]
    for fp in files:
        game_json = json.loads(fp.read_text(encoding="utf-8"))
        game_id = game_json["game"]["gameId"]
        actions = sorted(game_json["game"]["actions"], key=lambda a: a["actionNumber"])
        missed = [a for a in actions if a.get("actionType") in ("2pt", "3pt") and a.get("shotResult") == "Missed"]
        rebs = [a for a in actions if a.get("actionType") == "other" and "rebound" in (a.get("description") or "").lower()]
        for m in missed:
            nxt = next((r for r in rebs if r["period"] == m["period"] and r["actionNumber"] > m["actionNumber"]), None)
            if nxt is None:
                continue
            rows.append({
                "game_id": game_id, "team_id": m["teamId"], "period": m["period"],
                "elapsed_s": _elapsed_s(m["period"], m["clock"]),
                "is_dreb": int("defensive rebound" in nxt["description"].lower()),
            })
    return pd.DataFrame(rows)


def build_continuity_dreb(stints_df: pd.DataFrame, pbp_dir: Path = _PBP_DIR) -> pd.DataFrame:
    shots = _load_missed_shots_and_rebounds(pbp_dir=pbp_dir)
    clean = stints_df[stints_df["n_on_court"] == 5].copy()
    team_ids_by_game = clean.groupby("game_id")["team_id"].unique().apply(list).to_dict()
    shots["defending_team_id"] = shots.apply(
        lambda r: _other_team(team_ids_by_game.get(r["game_id"], []), r["team_id"]), axis=1)
    shots = shots.dropna(subset=["defending_team_id"])
    shots["defending_team_id"] = shots["defending_team_id"].astype("int64")  # Windows astype(int) trap

    right = clean.rename(columns={"team_id": "defending_team_id"})[
        ["game_id", "period", "defending_team_id", "start_s"]]
    matched = pd.merge_asof(
        shots.sort_values("elapsed_s"), right.sort_values("start_s"),
        left_on="elapsed_s", right_on="start_s", by=["game_id", "period", "defending_team_id"],
        direction="backward",
    )
    matched["continuity_s"] = matched["elapsed_s"] - matched["start_s"]
    return matched.dropna(subset=["continuity_s"])[["continuity_s", "is_dreb"]]


def build_clutch_shots(pbp_dir: Path = _PBP_DIR) -> pd.DataFrame:
    """h10: spacing x clutch (atomic=shot). Clutch = kernel/config/game_state.py's
    NBA primary live constants (read-only reference, not imported/edited):
    clutch_margin=6.0 pts, clutch_remaining_sec=360.0, period>=4."""
    rows: List[Dict[str, Any]] = []
    for fp in sorted(pbp_dir.glob("*.json")):
        d = json.loads(fp.read_text(encoding="utf-8"))
        game_id = d["game"]["gameId"]
        for a in d["game"]["actions"]:
            if a.get("actionType") in ("2pt", "3pt") and a.get("teamId") and a.get("scoreHome") is not None:
                rows.append({
                    "game_id": game_id, "team_id": a["teamId"], "period": a["period"],
                    "elapsed_s": _elapsed_s(a["period"], a["clock"]),
                    "made": int(a.get("shotResult") == "Made"),
                    "score_home": int(a["scoreHome"]), "score_away": int(a["scoreAway"]),
                })
    df = pd.DataFrame(rows)
    df = add_spacing(df)
    remaining = df["period"].map(_period_length_s) - df["elapsed_s"]
    df["is_clutch"] = ((df["period"] >= 4) & (remaining <= 360.0) & ((df["score_home"] - df["score_away"]).abs() <= 6)).astype(int)
    return df[["made", "spacing_mean_dist", "is_clutch"]].dropna()


def run() -> tuple[List[Dict[str, Any]], int]:
    stints_df = pd.read_parquet(_STINTS_PATH)
    games_df = pd.read_parquet(_GAMES_PATH)
    rows: List[Dict[str, Any]] = []
    for name, reason in BLOCKED_REASONS.items():
        rows.append(blocked_row(name, SPORT, "n/a", reason))

    k = 3  # #3, #7, #10 -- the only ones with data present this census
    alpha = alpha_fwer(k)

    matchup = build_matchup_rows(stints_df, games_df)
    fit3 = fit_interaction(matchup, "margin_per48 ~ matchup_net_diff * rest_diff", kind="ols")
    rows.append(tested_row("lineup_vs_lineup net-rating x rest differential", SPORT, "stint", fit3, alpha))

    cont = build_continuity_dreb(stints_df)
    fit7 = fit_single(cont, "is_dreb ~ continuity_s", kind="logit")
    rows.append(tested_row("stint continuity x defensive rebound rate (single-factor: no "
                            "second named mechanism in the doc)", SPORT, "rebound", fit7, alpha))

    clutch = build_clutch_shots()
    fit10 = fit_interaction(clutch, "made ~ spacing_mean_dist * is_clutch", kind="logit")
    rows.append(tested_row("spacing x clutch (<=5 pt, <=5 min)", SPORT, "possession", fit10, alpha))

    return rows, k


def main() -> int:
    rows, k = run()
    print(f"K tested (NBA)={k} alpha_fwer={alpha_fwer(k):.6f}")
    for r in rows:
        print(f"  [{r['verdict']:>16}] {r['hypothesis']}: n={r['n']} effect={r['effect']} p={r['p']}")
    append_ledger(rows)
    print(f"appended {len(rows)} rows -> {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
