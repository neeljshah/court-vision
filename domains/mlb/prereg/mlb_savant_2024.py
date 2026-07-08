"""domains.mlb.prereg.mlb_savant_2024 -- uses the savant_backfill.py corpus
(data/cache/statcast/savant_full__2024.parquet: on_1b/on_2b/on_3b, launch_angle,
bb_type added vs statcast_fuller) for two things:

  1. REPLICATION: rerun the 3 PROVISIONAL survivors from mlb_hypotheses.py (platoon
     x pitch-type, count-leverage x mix, velo-band x TTO) on 2024 ALONE (an
     independent season from the 2022+2023 corpus they were found on) -> REPLICATED
     / FAILED_REPLICATION, method="replication_savant_2024".
  2. PREMISE-RECHECK + RUN of the 2 of 5 BLOCKED hypotheses this corpus's new
     columns actually unblock:
       - "base-out state x contact type (GB/FB)": on_1b/on_2b/on_3b + bb_type
         present -> is_risp x two_outs -> is_groundball.
       - "launch-angle tightness x park factor": launch_angle present; park factor
         reuses domains.mlb.asof_park.build_park_features UNCHANGED (walk-forward,
         no invention) on a per-game frame derived from this corpus's own
         post_home_score/post_away_score (final score = max of the cumulative
         post-play score column).
     The other 3 (bullpen-leverage, catcher-framing, sprint-speed) stay BLOCKED --
     see NOTE below; no proxy invented for any of them.

NOTE (catcher framing): this corpus ALSO carries 'description' (the real per-pitch
S/B/X sub-code -- ball/called_strike/swinging_strike/foul/hit_into_play), which
in principle could isolate a called-strike rate the way the previously-blocked
type=='S' bundling could not. NOT run this pass -- a leakage-safe catcher-skill
split (holding a catcher's own rows out of the average that describes them) is a
bigger, separate build than a like-for-like premise recheck; flagged, not faked.

Descriptive/measurement only. edge_claimed hard-wired False (stats_common).
CLI: python -m domains.mlb.prereg.mlb_savant_2024
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from domains.mlb.asof_park import build_park_features, load_park_features
from domains.mlb.prereg.mlb_hypotheses import (
    _BIP_HIT_EVENTS, _BIP_OUT_EVENTS, build_h4_platoon_pitchtype, build_h5_count_pitchmix,
    build_h8_velo_tto,
)
from domains.mlb.prereg.stats_common import (
    LEDGER_PATH, alpha_fwer, append_ledger, blocked_row, fit_interaction, replication_row,
    tested_row,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
_SAVANT_FP = REPO_ROOT / "data" / "cache" / "statcast" / "savant_full__2024.parquet"
SEASON = 2024
SPORT = "mlb"
_METHOD = f"replication_savant_{SEASON}"


def load_savant_2024() -> pd.DataFrame:
    return pd.read_parquet(_SAVANT_FP)


# --------------------------------------------------------------------------- #
# 1. Replication of the 3 provisional survivors, on 2024 alone.
# --------------------------------------------------------------------------- #
def run_replication(df: pd.DataFrame) -> list:
    """Same build_* functions as mlb_hypotheses.py (2022+2023 corpus) applied to
    the independent 2024 corpus -- REPLICATED iff the interaction clears the SAME
    alpha_fwer(3) bar (k=3, this replication set)."""
    alpha = alpha_fwer(3)
    rows = []
    fit4 = fit_interaction(build_h4_platoon_pitchtype(df),
                            "reaches_base ~ platoon_same_hand * is_breaking", kind="logit")
    rows.append(replication_row("platoon (P-hand x B-stand) x pitch type", SPORT, "PA",
                                fit4, alpha, _METHOD))
    fit5 = fit_interaction(build_h5_count_pitchmix(df),
                            "is_strike ~ pitcher_ahead * is_breaking", kind="logit")
    rows.append(replication_row("count leverage (ahead/behind) x pitch-mix", SPORT, "pitch",
                                fit5, alpha, _METHOD))
    fit8 = fit_interaction(build_h8_velo_tto(df),
                            "reaches_base ~ above_avg_velo * tto3", kind="logit")
    rows.append(replication_row("starter velo-band x TTO", SPORT, "PA", fit8, alpha, _METHOD))
    return rows


# --------------------------------------------------------------------------- #
# 2a. base-out state x contact type -- unblocked by on_1b/on_2b/on_3b + bb_type.
# --------------------------------------------------------------------------- #
def build_baseout_contacttype(df: pd.DataFrame) -> pd.DataFrame:
    """Balls in play only (type=='X', bb_type present). is_risp = runner on 2nd
    or 3rd (on_2b/on_3b non-null -- MLBAM runner id when occupied, NaN when not).
    two_outs = outs_when_up==2 (the state where a batter is most likely to alter
    approach to avoid a rally-ending double play / just put the ball in play)."""
    bip = df[(df["type"] == "X") & df["bb_type"].notna()].copy()
    bip["is_groundball"] = (bip["bb_type"] == "ground_ball").astype(int)
    bip["is_risp"] = (bip["on_2b"].notna() | bip["on_3b"].notna()).astype(int)
    bip["two_outs"] = (bip["outs_when_up"] == 2).astype(int)
    return bip[["is_groundball", "is_risp", "two_outs"]].dropna()


# --------------------------------------------------------------------------- #
# 2b. launch-angle tightness x park factor -- unblocked by launch_angle.
# --------------------------------------------------------------------------- #
def _local_park_factor(df: pd.DataFrame) -> pd.DataFrame:
    """Per-game_pk park_factor via the EXISTING walk-forward asof_park.py code,
    UNCHANGED -- no new park-factor logic invented. Final score per game_pk = max
    of the cumulative post_home_score/post_away_score columns (monotonic within a
    game). event_id here is just str(game_pk); local to this call, not the
    cross-corpus event_id domain -- no game_pk_bridge needed since we compute the
    factor entirely within this one corpus's own games."""
    g = df.groupby("game_pk").agg(
        date=("game_date", "first"), home_team=("home_team", "first"),
        away_team=("away_team", "first"),
        home_runs=("post_home_score", "max"), away_runs=("post_away_score", "max"),
    ).reset_index()
    g["event_id"] = g["game_pk"].astype(str)
    # explicit out_path so this NEVER overwrites the production asof_park.parquet
    # the totals/park-eval pipeline reads (build_park_features's default path).
    out_fp = REPO_ROOT / "data" / "domains" / "mlb" / "asof_park_savant_local.parquet"
    build_park_features(games=g[["event_id", "date", "home_team", "away_team",
                                 "home_runs", "away_runs"]], out_path=str(out_fp))
    pf = load_park_features(str(out_fp))
    pf["game_pk"] = pf["event_id"].astype(int)
    return pf[["game_pk", "park_factor"]]


def build_launchangle_park(df: pd.DataFrame) -> pd.DataFrame:
    """Sweet Spot% band (launch_angle 8-32 deg) is Statcast's OWN published
    definition, not invented here. is_hitter_park = this game's home park_factor
    (walk-forward, NaN until warm) above the neutral 1.0 baseline. Outcome =
    extra-base hit among batted balls with a events-terminal outcome (single/
    double/triple/home_run/field_out/... -- ambiguous rows dropped, same
    convention as mlb_hypotheses.add_reaches_base)."""
    pf = _local_park_factor(df)
    bip = df[df["launch_angle"].notna() & df["events"].notna()].copy()
    bip = bip[bip["events"].isin(_BIP_HIT_EVENTS | _BIP_OUT_EVENTS | {"home_run"})]
    bip["is_xbh"] = bip["events"].isin({"double", "triple", "home_run"}).astype(int)
    bip["is_sweet_spot"] = bip["launch_angle"].between(8, 32).astype(int)
    bip = bip.merge(pf, on="game_pk", how="inner")
    bip["is_hitter_park"] = (bip["park_factor"] > 1.0).astype(int)
    return bip[["is_xbh", "is_sweet_spot", "is_hitter_park"]].dropna()


def run_newly_unblocked(df: pd.DataFrame) -> list:
    """The 2 of 5 BLOCKED hypotheses this corpus's new columns unblock, run at
    alpha_fwer(2) (k=2, this newly-tested set). The other 3 stay BLOCKED (see
    module docstring) -- rows re-appended so the ledger shows they were rechecked
    this pass, not silently dropped."""
    alpha = alpha_fwer(2)
    rows = []
    fit_bo = fit_interaction(build_baseout_contacttype(df),
                             "is_groundball ~ is_risp * two_outs", kind="logit")
    rows.append(tested_row("base-out state x contact type (GB/FB)", SPORT, "batted ball",
                           fit_bo, alpha, method=f"unblocked_savant_{SEASON}"))
    fit_la = fit_interaction(build_launchangle_park(df),
                             "is_xbh ~ is_sweet_spot * is_hitter_park", kind="logit")
    rows.append(tested_row("launch-angle tightness x park factor", SPORT, "batted ball",
                           fit_la, alpha, method=f"unblocked_savant_{SEASON}"))
    rows.append(blocked_row(
        "bullpen fatigue-chain x leverage", SPORT, "n/a",
        "still no leverage_index column and doc names no coarse late-inning+close-score "
        "proxy -- base-runner state alone (now present) does not make a formal leverage "
        "index; not inventing one.", method=f"unblocked_savant_{SEASON}_recheck"))
    rows.append(blocked_row(
        "catcher framing x pitch location (edge)", SPORT, "n/a",
        "'description' now present could isolate called_strike, but a leakage-safe "
        "catcher-skill split is a separate build, not run this pass (see module docstring).",
        method=f"unblocked_savant_{SEASON}_recheck"))
    rows.append(blocked_row(
        "sprint-speed x infield-alignment", SPORT, "n/a",
        "sprint_speed is a Statcast LEADERBOARD stat, not a per-pitch CSV column -- still "
        "not obtainable from this endpoint.", method=f"unblocked_savant_{SEASON}_recheck"))
    return rows


def main() -> int:
    df = load_savant_2024()
    rows = run_replication(df) + run_newly_unblocked(df)
    for r in rows:
        print(f"  [{r['verdict']:>20}] {r['hypothesis']}: n={r['n']} effect={r['effect']} p={r['p']}")
    append_ledger(rows)
    print(f"appended {len(rows)} rows -> {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


__all__ = ["load_savant_2024", "run_replication", "run_newly_unblocked",
           "build_baseout_contacttype", "build_launchangle_park", "_local_park_factor"]
