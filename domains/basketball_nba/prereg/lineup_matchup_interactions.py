"""domains.basketball_nba.prereg.lineup_matchup_interactions -- the FIRST
cross-lineup interaction test: how opposing 5-man lineups affect EACH OTHER,
on the lineup-vs-lineup matchup tables (domains/basketball_nba/lineups/
lineup_matchups.py -> data/cache/team_system/lineups/lineup_matchups_<season>
.parquet: game_id, game_date, team_id_a/b, lineup_key_a/b, overlap_s, pts_a/b).

PREREGISTERED (K=3, flat Bonferroni alpha=0.05/3, declared BEFORE running,
never extended after seeing results):
  H1 spacing differential   -- (spacing_a - spacing_b) predicts segment net/48.
     spacing from lineup_spacing_<season>.parquet (team_id, lineup_key), with
     the SAME n_shots>=20 floor gravity_spacing.py's own claims producer uses
     (the raw parquet itself has no floor beyond pdist's min_shots=2).
  H2 continuity differential -- as-of CUMULATIVE prior seconds (strictly
     BEFORE this game_date, this season) that the exact lineup_key has played
     together, differenced across sides, from stints_<season>.parquet.
  H3 on_off-talent differential -- sum of the 5 players' net_rating_on_per48
     (on_off_<season>.parquet), differenced across sides. This is the
     CONTROL-STRENGTH rung: H1/H2 are reported BOTH raw and controlling for
     H3's term. A soccer possession-tier ghost died under strength control
     once already -- H1/H2 only count as MECHANISM if they survive with the
     H3 control included, not just raw.

METHOD: per-segment y = (pts_a - pts_b)/overlap_s*2880 (net rating per 48),
weighted by overlap_s, floor overlap_s>=30s (declared now, not after seeing
data). fit_interaction/fit_single in stats_common.py have no weighted+cluster
-robust-SE path, so this file fits directly via statsmodels WLS with
cov_type='cluster' grouped by game_id (statsmodels already a dependency;
nothing new to install).

RUN ORDER: 2025-26 first (primary). Whatever hypothesis's RAW fit survives
Bonferroni gets a replication run on 2024-25 AND 2023-24 -- same-sign AND
p<alpha/K required for REPLICATED, mirroring third_season_2023_24.py's
_verdict_row (including its n=0 -> NOT_TESTABLE guard: an un-run test is not
a failed replication).

Descriptive/measurement only. edge_claimed hard-wired False on every row.
NETWORK: zero. CLI: python -m domains.basketball_nba.prereg.lineup_matchup_interactions
Per-file test: python -m pytest domains/basketball_nba/prereg/test_lineup_matchup_interactions.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import statsmodels.formula.api as smf

from domains.basketball_nba.prereg.stats_common import NULL, SURVIVES, append_ledger

REPO_ROOT = Path(__file__).resolve().parents[3]
_LINEUPS_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
_GAMES_SRC = REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"

SEASON_TAGS = ["2025_26", "2024_25", "2023_24"]  # primary first, then replication order
ALPHA = 0.05 / 3  # K=3, plain Bonferroni -- declared in the brief, not stats_common's eps curve
METHOD = "lineup_matchup_interactions_v1"

MIN_OVERLAP_S = 30.0   # declared floor: drop segments with <30s of head-to-head overlap
MIN_SPACING_SHOTS = 20  # same n_shots floor gravity_spacing.py's claims producer applies

HYPOTHESES = [
    ("H1_spacing_diff", "x1_spacing_diff"),
    ("H2_continuity_diff", "x2_continuity_diff"),
    ("H3_onoff_talent_diff", "x3_talent_diff"),
]
CONTROL_COL = "x3_talent_diff"  # H3's own term -- the strength-control rung


def build_continuity_table(stints_df: pd.DataFrame, games_df: pd.DataFrame) -> pd.DataFrame:
    """As-of leak-free: cumulative prior seconds (STRICTLY before this game's
    date) that this exact (team_id, lineup_key) has played together this
    season, keyed for a direct (team_id, lineup_key, game_id) lookup.
    cumsum() includes the current game's own seconds; subtracting the
    current row's elapsed_s leaves only what happened in EARLIER games."""
    clean = stints_df[stints_df["n_on_court"] == 5]
    date_by_gid = dict(zip(games_df["game_id"].astype(str), games_df["date"]))
    per_game = clean.groupby(["team_id", "lineup_key", "game_id"], as_index=False)["elapsed_s"].sum()
    per_game["game_date"] = per_game["game_id"].astype(str).map(date_by_gid)
    per_game = per_game.sort_values(["team_id", "lineup_key", "game_date", "game_id"])
    per_game["continuity_s"] = per_game.groupby(["team_id", "lineup_key"])["elapsed_s"].cumsum() - per_game["elapsed_s"]
    return per_game[["team_id", "lineup_key", "game_id", "continuity_s"]]


def build_lineup_talent(stints_df: pd.DataFrame, on_off_df: pd.DataFrame) -> pd.DataFrame:
    """Per (team_id, lineup_key): sum of the 5 players' net_rating_on_per48.
    NaN (dropped downstream) if any of the 5 is missing from on_off_df --
    an incomplete talent sum is not a real one."""
    net = on_off_df.set_index(["player_id", "team_id"])["net_rating_on_per48"].to_dict()
    uniq = stints_df.loc[stints_df["n_on_court"] == 5, ["team_id", "lineup_key"]].drop_duplicates()
    rows: List[Dict[str, Any]] = []
    for team_id, lineup_key in uniq.itertuples(index=False):
        vals = [net.get((int(p), team_id)) for p in lineup_key.split(",")]
        talent = float("nan") if any(v is None or pd.isna(v) for v in vals) else float(sum(vals))
        rows.append({"team_id": team_id, "lineup_key": lineup_key, "talent_sum": talent})
    return pd.DataFrame(rows, columns=["team_id", "lineup_key", "talent_sum"])


def build_segment_features(
    matchups_df: pd.DataFrame, spacing_df: pd.DataFrame, talent_df: pd.DataFrame,
    continuity_df: pd.DataFrame, min_overlap_s: float = MIN_OVERLAP_S,
    min_spacing_shots: int = MIN_SPACING_SHOTS,
) -> pd.DataFrame:
    """Pure feature-build (no disk I/O) so the weight floor + as-of joins are
    directly unit-testable: weight-floor segments, attach spacing/continuity/
    talent for BOTH sides, return the 3 declared differential columns."""
    df = matchups_df[matchups_df["overlap_s"] >= min_overlap_s].copy()
    df["y"] = (df["pts_a"] - df["pts_b"]) / df["overlap_s"] * 2880.0
    spacing = spacing_df[spacing_df["n_shots"] >= min_spacing_shots][["team_id", "lineup_key", "spacing_mean_dist"]]

    def _attach(d: pd.DataFrame, side: str) -> pd.DataFrame:
        tk, lk = f"team_id_{side}", f"lineup_key_{side}"
        d = d.merge(spacing.rename(columns={"team_id": tk, "lineup_key": lk, "spacing_mean_dist": f"spacing_{side}"}),
                    on=[tk, lk], how="left")
        d = d.merge(continuity_df.rename(columns={"team_id": tk, "lineup_key": lk, "continuity_s": f"continuity_{side}"}),
                    on=[tk, lk, "game_id"], how="left")
        d = d.merge(talent_df.rename(columns={"team_id": tk, "lineup_key": lk, "talent_sum": f"talent_{side}"}),
                    on=[tk, lk], how="left")
        return d

    df = _attach(df, "a")
    df = _attach(df, "b")
    df["x1_spacing_diff"] = df["spacing_a"] - df["spacing_b"]
    df["x2_continuity_diff"] = df["continuity_a"] - df["continuity_b"]
    df["x3_talent_diff"] = df["talent_a"] - df["talent_b"]
    return df[["game_id", "y", "overlap_s", "x1_spacing_diff", "x2_continuity_diff", "x3_talent_diff"]]


def build_segment_frame(season_tag: str) -> pd.DataFrame:
    """I/O wrapper: reads the season's 4 artifacts and delegates to the pure
    feature-builder above."""
    matchups_df = pd.read_parquet(_LINEUPS_DIR / f"lineup_matchups_{season_tag}.parquet")
    stints_df = pd.read_parquet(_LINEUPS_DIR / f"stints_{season_tag}.parquet")
    spacing_df = pd.read_parquet(_LINEUPS_DIR / f"lineup_spacing_{season_tag}.parquet")
    on_off_df = pd.read_parquet(_LINEUPS_DIR / f"on_off_{season_tag}.parquet")
    games_df = pd.read_parquet(_GAMES_SRC)
    continuity_df = build_continuity_table(stints_df, games_df)
    talent_df = build_lineup_talent(stints_df, on_off_df)
    return build_segment_features(matchups_df, spacing_df, talent_df, continuity_df)


def fit_wls_cluster(df: pd.DataFrame, x_col: str, controls: Tuple[str, ...] = (),
                     y_col: str = "y", weight_col: str = "overlap_s", cluster_col: str = "game_id") -> Dict[str, Any]:
    """WLS (overlap_s weights) with cluster-robust SEs by game_id, directly
    via statsmodels -- stats_common's fit_single/fit_interaction have no
    weighted+cluster path, so this is not a reimplementation of anything
    that already exists."""
    cols = [y_col, x_col, weight_col, cluster_col, *controls]
    d = df[cols].dropna()
    if len(d) == 0:
        return {"term": x_col, "effect": None, "p": None, "n": 0}
    rhs = " + ".join([x_col, *controls])
    model = smf.wls(f"{y_col} ~ {rhs}", data=d, weights=d[weight_col])
    res = model.fit(cov_type="cluster", cov_kwds={"groups": d[cluster_col]})
    return {"term": x_col, "effect": float(res.params[x_col]), "p": float(res.pvalues[x_col]), "n": int(res.nobs)}


def _row(name: str, season: str, variant: str, fit: Dict[str, Any], controlling_for: Optional[str],
         sign_ref: Optional[int] = None, extra_note: str = "") -> Dict[str, Any]:
    """verdict rule mirrors third_season_2023_24._verdict_row: n=0 -> NOT_TESTABLE
    (an un-run test is not a failed replication); sign_ref given -> REPLICATED
    requires same sign AND p<ALPHA; else primary declaration -> SURVIVES/NULL."""
    if fit["n"] == 0:
        verdict, note = "NOT_TESTABLE", "n=0: no scoreable segments after floors on this corpus"
    elif sign_ref is not None:
        same_sign = (fit["effect"] > 0) == (sign_ref > 0)
        verdict = "REPLICATED" if (same_sign and fit["p"] < ALPHA) else "FAILED_REPLICATION"
        note = "" if verdict == "REPLICATED" else "same-sign-and-p<alpha required for REPLICATED"
    else:
        verdict = SURVIVES if fit["p"] < ALPHA else NULL
        note = "PROVISIONAL -- needs independent replication before belief" if verdict == SURVIVES else ""
    if extra_note:
        note = (note + " " if note else "") + extra_note
    return {
        "hypothesis": name, "sport": "nba", "atomic_unit": "lineup_segment", "method": METHOD,
        "season": season, "variant": variant, "n": fit["n"], "effect": fit["effect"], "p": fit["p"],
        "alpha_fwer": ALPHA, "term": fit["term"], "controlling_for": controlling_for,
        "verdict": verdict, "note": note, "edge_claimed": False,
    }


def run() -> List[Dict[str, Any]]:
    frames = {s: build_segment_frame(s) for s in SEASON_TAGS}
    rows: List[Dict[str, Any]] = []
    survivors: Dict[str, int] = {}  # hypothesis name -> sign of the 2025-26 raw effect

    primary_season = SEASON_TAGS[0]
    primary = frames[primary_season]
    for name, xcol in HYPOTHESES:
        raw_fit = fit_wls_cluster(primary, xcol)
        raw_row = _row(name, primary_season, "raw", raw_fit, None)
        rows.append(raw_row)
        if xcol != CONTROL_COL:
            ctrl_fit = fit_wls_cluster(primary, xcol, controls=(CONTROL_COL,))
            note = ""
            if raw_row["verdict"] == SURVIVES:
                ctrl_survives = (ctrl_fit["p"] is not None and ctrl_fit["p"] < ALPHA
                                 and (ctrl_fit["effect"] > 0) == (raw_fit["effect"] > 0))
                note = ("MECHANISM_CANDIDATE: survives H3 strength control" if ctrl_survives else
                        "CONTROL_KILLED: raw survives Bonferroni but dies under H3 strength control")
            rows.append(_row(name, primary_season, "controlled", ctrl_fit, CONTROL_COL, extra_note=note))
        if raw_row["verdict"] == SURVIVES:
            survivors[name] = 1 if raw_fit["effect"] > 0 else -1

    for season in SEASON_TAGS[1:]:
        df = frames[season]
        for name, xcol in HYPOTHESES:
            if name not in survivors:
                continue
            raw_fit = fit_wls_cluster(df, xcol)
            rows.append(_row(name, season, "raw", raw_fit, None, sign_ref=survivors[name]))
            if xcol != CONTROL_COL:
                ctrl_fit = fit_wls_cluster(df, xcol, controls=(CONTROL_COL,))
                rows.append(_row(name, season, "controlled", ctrl_fit, CONTROL_COL, sign_ref=survivors[name]))

    append_ledger(rows)
    return rows


def main() -> int:
    rows = run()
    print(f"K=3 alpha_bonferroni={ALPHA:.6f} seasons={SEASON_TAGS}")
    for r in rows:
        print(f"  [{r['season']}/{r['variant']:>10}] [{r['verdict']:>18}] {r['hypothesis']}: "
              f"n={r['n']} effect={r['effect']} p={r['p']} note={r['note']}")
    print(f"appended {len(rows)} rows -> stats_common.LEDGER_PATH")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
