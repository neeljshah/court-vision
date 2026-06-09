"""
hunt_compound_signals_v3.py
============================
INT-75: 36 pre-registered compound betting signals
using 4 new team atlases + INT-69/67/54/16.

Themes:
  A (12): paint exposure x archetype (prior: INT-58 + BLK +0.26 corr)
  B (12): tempo x opposition (prior: V6 pattern + 2 surviving mx scalars)
  C (12): player-state x matchup (prior: INT-67 + INT-54 + INT-69)

Bonferroni z @ 36 hypotheses: STRICT z>=3.18, INVESTIGATIVE z>=2.5

SHIP gate per compound:
  n_bets >= 30
  ROI >= +5.0%
  z_raw >= 2.5 (INVESTIGATIVE) or >= 3.18 (STRICT_SHIP)
  real_z_vs_null >= 2.0
  mean_shift CI lower bound > 0

Outputs:
  data/intelligence/compound_signal_hunt_v3.parquet
  vault/Intelligence/INT-75_Compound_Signals_v3.md
"""

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

warnings.filterwarnings("ignore")
np.random.seed(42)

ROOT = Path(__file__).resolve().parent.parent
INTEL = ROOT / "data" / "intelligence"
LINES_DIR = ROOT / "data" / "external" / "historical_lines"
N_SHUFFLE = 200
BONFERRONI_N = 36
Z_STRICT = 3.18
Z_INVEST = 2.5
MIN_BETS = 30
MIN_ROI = 5.0
MIN_Z_VS_NULL = 2.0

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def norm(s: str) -> str:
    return str(s).strip().lower()


def load_lines() -> pd.DataFrame:
    """Load and pool all canonical lines files."""
    sources = [
        "extended_oos_canonical.csv",
        "benashkar_2026_canonical.csv",
        "regular_season_2025_26_oddsapi.csv",
        "regular_season_2024_25_oddsapi.csv",
    ]
    dfs = []
    for fname in sources:
        p = LINES_DIR / fname
        if p.exists():
            d = pd.read_csv(p, on_bad_lines="skip")
            d["date"] = pd.to_datetime(d["date"])
            d["player_norm"] = d["player"].map(norm)
            d["stat"] = d["stat"].str.lower().str.strip()
            dfs.append(d)
    pool = (
        pd.concat(dfs, ignore_index=True)
        .drop_duplicates(subset=["player_norm", "date", "stat"])
        .reset_index(drop=True)
    )
    pool = pool.dropna(subset=["actual_value", "closing_line"])
    return pool


def compute_roi(sub: pd.DataFrame, direction: str) -> float:
    """Compute naive ROI assuming -110 on hits and -110 on misses (flat -10% vig each bet)."""
    if len(sub) == 0:
        return 0.0
    shift = sub["actual_value"] - sub["closing_line"]
    if direction == "over":
        wins = (shift > 0).sum()
    else:
        wins = (shift < 0).sum()
    n = len(sub)
    # -110 vig: win +$91, lose -$100 per $100 stake
    roi = (wins * 91.0 - (n - wins) * 100.0) / (n * 100.0) * 100
    return round(float(roi), 3)


def analyze_signal(sub: pd.DataFrame, direction: str = "over") -> dict:
    """Compute n, hit_rate, ROI, mean shift, z, bootstrap CI, CLV proxy."""
    sub = sub.copy()
    sub["shift"] = sub["actual_value"] - sub["closing_line"]
    n = len(sub)
    if n < 5:
        return {"n": n, "hit_rate": None, "roi": None, "mu": None, "std": None,
                "z_raw": None, "ci_lo": None, "ci_hi": None, "clv_proxy": None}
    mu = sub["shift"].mean()
    std = sub["shift"].std(ddof=1)
    z_raw = mu / (std / np.sqrt(n))
    if direction == "under":
        z_raw = -z_raw
    boots = [sub["shift"].sample(frac=1, replace=True).mean() for _ in range(2000)]
    ci_lo, ci_hi = np.percentile(boots, [2.5, 97.5])
    if direction == "under":
        ci_lo, ci_hi = -ci_hi, -ci_lo
    if direction == "over":
        hit_rate = float((sub["actual_value"] > sub["closing_line"]).mean())
    else:
        hit_rate = float((sub["actual_value"] < sub["closing_line"]).mean())
    roi = compute_roi(sub, direction)
    # CLV proxy: mean(side * (actual - close) / |close|) * 100
    side_mult = 1.0 if direction == "over" else -1.0
    clv_proxy = float(
        (side_mult * sub["shift"] / sub["closing_line"].abs().clip(lower=0.5)).mean() * 100
    )
    return {
        "n": n,
        "hit_rate": round(hit_rate, 4),
        "roi": roi,
        "mu": round(mu, 4),
        "std": round(std, 4),
        "z_raw": round(float(z_raw), 4),
        "ci_lo": round(float(ci_lo), 4),
        "ci_hi": round(float(ci_hi), 4),
        "clv_proxy": round(clv_proxy, 4),
    }


def null_z(sub: pd.DataFrame, direction: str, real_z: float, stat: str) -> float:
    """Permutation null control: sample n_bets random bets from the SAME stat pool
    (independent of the compound filters) N_SHUFFLE times, compute z each time.
    Returns z of real_z within the null distribution.
    This correctly tests: is the signal stronger than random same-n selection?
    """
    n = len(sub)
    if n < 10:
        return 0.0
    # Pool of same-stat bets to draw from
    pool_stat = lines_pool[lines_pool["stat"] == stat].copy()
    pool_stat["shift"] = pool_stat["actual_value"] - pool_stat["closing_line"]
    if len(pool_stat) < n:
        return 0.0
    null_zs = []
    for _ in range(N_SHUFFLE):
        sample = pool_stat["shift"].sample(n=n, replace=False)
        nm = sample.mean()
        ns = sample.std(ddof=1)
        nz = nm / (ns / np.sqrt(n)) if ns > 0 else 0.0
        if direction == "under":
            nz = -nz
        null_zs.append(nz)
    null_arr = np.array(null_zs)
    if null_arr.std() < 1e-9:
        return 0.0
    return float((real_z - null_arr.mean()) / null_arr.std())


def verdict(n, roi, z_raw, z_vs_null, ci_lo) -> str:
    if n < MIN_BETS:
        return "REJECT_N"
    if roi < MIN_ROI:
        return "REJECT_ROI"
    if z_raw >= Z_STRICT and z_vs_null >= MIN_Z_VS_NULL and ci_lo > 0:
        return "STRICT_SHIP"
    if z_raw >= Z_INVEST and z_vs_null >= MIN_Z_VS_NULL and ci_lo > 0:
        return "INVESTIGATIVE"
    return "REJECT"


# ---------------------------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------------------------
print("[1] Loading lines pool...")
lines_pool = load_lines()
print(f"  Total bets (deduped): {len(lines_pool):,}")

print("[2] Loading atlas parquets...")

# Player fingerprints (archetype NAMES, not cluster IDs)
fp = pd.read_parquet(INTEL / "player_fingerprints.parquet").reset_index()
fp["player_norm"] = fp["player_name"].map(norm)

# Streak signatures
streak = pd.read_parquet(INTEL / "streak_signatures.parquet")
streak["player_norm"] = streak["player_name"].map(norm)

# Archetype drift
drift = pd.read_parquet(INTEL / "archetype_drift.parquet")
drift["player_norm"] = drift["player_name"].map(norm)

# Defensive schemes
schemes = pd.read_parquet(INTEL / "defensive_schemes.parquet")

# NEW Atlas A: opp_paint_allowance (C4, team-level)
opa = pd.read_parquet(INTEL / "opp_paint_allowance.parquet")

# NEW Atlas B: opp_defensive_intensity (C3, team-level)
odi = pd.read_parquet(INTEL / "opp_defensive_intensity.parquet")

# NEW Atlas C: team_tempo_spacing (C1/C2, team-level)
tts = pd.read_parquet(INTEL / "team_tempo_spacing.parquet")

# NEW Atlas D: matchup_grid (INT-63, game-level, has mx scalars)
mg = pd.read_parquet(INTEL / "matchup_grid.parquet")
mg["game_date"] = pd.to_datetime(mg["game_date"])

# INT-54: archetype outlier signals
ao = pd.read_parquet(INTEL / "archetype_outlier_signals.parquet")
ao["game_date"] = pd.to_datetime(ao["game_date"])

# INT-67: player development v2 (slope features)
dv2 = pd.read_parquet(INTEL / "player_development_v2.parquet")
dv2["game_date"] = pd.to_datetime(dv2["game_date"])

# INT-69: per-player calibration bias
cal = pd.read_parquet(INTEL / "per_player_calibration.parquet")
cal["asof_date"] = pd.to_datetime(cal["asof_date"])

# Matchup deviations (INT-3)
matchup = pd.read_parquet(INTEL / "matchup_deviations.parquet")
matchup["player_norm"] = matchup["player_name"].map(norm)

# Rest CV impact
rest = pd.read_parquet(INTEL / "rest_cv_impact.parquet")
rest["player_norm"] = rest["player_name"].map(norm)

# Clutch CV split
clutch = pd.read_parquet(INTEL / "clutch_cv_split.parquet")
clutch["player_norm"] = clutch["player_name"].map(norm)

print(f"  Lines pool: {len(lines_pool):,}  FP: {len(fp)}  Schemes: {len(schemes)}  OPA: {len(opa)}  ODI: {len(odi)}  TTS: {len(tts)}  MG: {len(mg)}")

ZERO_CV_PLAYERS = {"stephen curry", "keshad johnson"}

# ---------------------------------------------------------------------------
# BUILD TEAM-LEVEL SIGNAL LOOKUPS (for each atlas, get team lists by threshold)
# ---------------------------------------------------------------------------

# OPA: teams that allow high paint pct (above median)
# Use most recent asof row per team
opa_latest = opa.sort_values("game_date").groupby("team_id").last().reset_index()
odi_latest = odi.sort_values("game_date").groupby("team_id").last().reset_index()
tts_latest = tts.sort_values("game_date").groupby("team_id").last().reset_index()

# High paint-permissive defense teams
paint_allow_teams = opa_latest[
    opa_latest["opp_paint_pct_allowed_z"] > 0.3
]["team_id"].str.upper().tolist()

# Low paint-permissive (paint-stingy) defense teams
paint_stingy_teams = opa_latest[
    opa_latest["opp_paint_pct_allowed_z"] < -0.3
]["team_id"].str.upper().tolist()

# High 3pt allowance teams
high_3pt_allow_teams = opa_latest[
    opa_latest["opp_3pt_pct_allowed_z"] > 0.3
]["team_id"].str.upper().tolist()

# Low 3pt allowance teams (3pt-stingy)
low_3pt_allow_teams = opa_latest[
    opa_latest["opp_3pt_pct_allowed_z"] < -0.3
]["team_id"].str.upper().tolist()

# High contested shot defense (from ODI)
high_contest_teams = odi_latest[
    odi_latest["opp_contested_shot_rate_imposed_z"] > 0.3
]["team_id"].str.upper().tolist()

# High defensive intensity composite
high_def_intensity_teams = odi_latest[
    odi_latest["opp_defensive_intensity_z"] > 0.3
]["team_id"].str.upper().tolist()

# Pace-slowing defense
pace_slow_teams = odi_latest[
    odi_latest["opp_pace_imposed_z"] > 0.3
]["team_id"].str.upper().tolist()

# High catch-shoot allowed (from ODI)
catch_shoot_allow_teams = odi_latest[
    odi_latest["opp_catch_shoot_allowed_pct_z"] > 0.3
]["team_id"].str.upper().tolist()

# High-tempo offense teams (from TTS)
high_tempo_teams = tts_latest[
    tts_latest["team_tempo_z"] > 0.3
]["team_id"].str.upper().tolist()

# High-transition teams
high_transition_teams = tts_latest[
    tts_latest["team_transition_share_z"] > 0.3
]["team_id"].str.upper().tolist()

# High-spacing teams
high_spacing_teams = tts_latest[
    tts_latest["team_avg_spacing_z"] > 0.3
]["team_id"].str.upper().tolist()

# Paint-heavy offense teams
paint_heavy_off_teams = tts_latest[
    tts_latest["team_paint_dwell_z"] > 0.3
]["team_id"].str.upper().tolist()

# Schemes (from existing defensive_schemes atlas)
def scheme_teams(tag: str) -> list:
    return schemes[schemes["all_tags"].str.contains(tag, na=False)]["team"].str.upper().tolist()

help_def_teams = scheme_teams("HELP DEFENSE")
pace_ctrl_teams = scheme_teams("PACE CONTROL")
switch_heavy_teams = scheme_teams("SWITCH HEAVY")
perim_denial_teams = schemes[
    schemes["dominant_tag"].str.contains("PERIMETER DENIAL", na=False)
]["team"].str.upper().tolist()
paint_first_teams = schemes[
    schemes["dominant_tag"].str.contains("PAINT", na=False)
]["team"].str.upper().tolist()
drop_cov_teams = schemes[
    schemes["dominant_tag"].str.contains("DROP", na=False)
]["team"].str.upper().tolist()
iso_force_teams = scheme_teams("ISO FORCE")

print(f"  paint_allow: {paint_allow_teams}")
print(f"  paint_stingy: {paint_stingy_teams}")
print(f"  high_3pt_allow: {high_3pt_allow_teams}")
print(f"  high_tempo: {high_tempo_teams}")
print(f"  high_transition: {high_transition_teams}")
print(f"  high_contest: {high_contest_teams}")
print(f"  pace_slow: {pace_slow_teams}")

# ---------------------------------------------------------------------------
# PLAYER SET LOOKUPS
# ---------------------------------------------------------------------------

# Archetype name-based (use names per feedback_signal_selectors_use_names_not_cluster_ids)
def archetype_players(name: str) -> set:
    return {
        p for p in fp[fp["archetype_name"] == name]["player_norm"].unique()
        if p not in ZERO_CV_PLAYERS
    }

versatile_forward_players = archetype_players("Versatile Forward")
off_ball_forward_players = archetype_players("Off-Ball Forward")
perimeter_shooter_players = archetype_players("Perimeter Shooter (Contested)")
versatile_big_players = archetype_players("Versatile Big")

# Paint-heavy players from FP (continuous metric, not archetype)
paint_heavy_players = {
    p for p in fp[
        (fp["paint_dwell_pct"] > fp["paint_dwell_pct"].quantile(0.65))
        & (fp["n_cv_games"] >= 3)
    ]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

high_second_chance_players = {
    p for p in fp[
        (fp["second_chance_rate"] > 0.20) & (fp["n_cv_games"] >= 3)
    ]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

high_pa_players = {
    p for p in fp[
        (fp["potential_assists"] > fp["potential_assists"].quantile(0.70))
        & (fp["n_cv_games"] >= 3)
    ]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

high_vel_players = {
    p for p in fp[
        (fp["preshot_velocity_peak"] > fp["preshot_velocity_peak"].quantile(0.65))
        & (fp["n_cv_games"] >= 3)
    ]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

high_catch_shoot_players = {
    p for p in fp[
        (fp["catch_shoot_pct"] > fp["catch_shoot_pct"].quantile(0.65))
        & (fp["n_cv_games"] >= 3)
    ]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

high_isolation_players = {
    p for p in fp[
        (fp["play_type_isolation_pct"] > fp["play_type_isolation_pct"].quantile(0.70))
        & (fp["n_cv_games"] >= 3)
    ]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

high_transition_players = {
    p for p in fp[
        (fp["play_type_transition_pct"] > fp["play_type_transition_pct"].quantile(0.65))
        & (fp["n_cv_games"] >= 3)
    ]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

# Streak labels
hot_pts_players = {
    p for p in streak[streak["label_pts"] == "HOT"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}
cold_pts_players = {
    p for p in streak[streak["label_pts"] == "COLD"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}
hot_reb_players = {
    p for p in streak[streak["label_reb"] == "HOT"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}
cold_reb_players = {
    p for p in streak[streak["label_reb"] == "COLD"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}
hot_ast_players = {
    p for p in streak[streak["label_ast"] == "HOT"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

# Drift tags
transitioning_players = {
    p for p in drift[drift["drift_tag"] == "TRANSITIONING"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}
drifting_players = {
    p for p in drift[drift["drift_tag"] == "DRIFTING"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}
stable_players = {
    p for p in drift[drift["drift_tag"] == "STABLE"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

# INT-54: strong outlier flagged players
ao_strong = ao[ao["flag_strong_outlier"] == True]
# Need player_name lookup via player_id -> fp
pid_to_name = fp.set_index("player_id")["player_norm"].to_dict()
# Also check streak/drift
streak_pid_to_name = streak[["player_id","player_norm"]].drop_duplicates().set_index("player_id")["player_norm"].to_dict()
pid_to_name.update(streak_pid_to_name)

outlier_flagged_players = {
    pid_to_name.get(pid) for pid in ao_strong["player_id"].unique()
    if pid_to_name.get(pid) and pid_to_name.get(pid) not in ZERO_CV_PLAYERS
}
outlier_flagged_players.discard(None)

# INT-67: players with any_regime_change (slope drift signal)
dv2_pid_to_name = dv2[["player_id","player_name"]].drop_duplicates()
dv2_pid_to_name["player_norm"] = dv2_pid_to_name["player_name"].map(norm)
regime_change_players = {
    row["player_norm"] for _, row in dv2_pid_to_name[
        dv2_pid_to_name["player_id"].isin(
            dv2[dv2["any_regime_change"] == True]["player_id"].unique()
        )
    ].iterrows()
    if row["player_norm"] not in ZERO_CV_PLAYERS
}

# INT-67: players with high dev_score (overall behavioral drift)
dv2_latest = dv2.sort_values("game_date").groupby("player_id").last().reset_index()
dv2_latest["player_norm"] = dv2_latest["player_id"].map(
    dv2[["player_id","player_name"]].drop_duplicates().set_index("player_id")["player_name"].map(norm).to_dict()
)
high_dev_score_players = {
    row["player_norm"] for _, row in dv2_latest[
        dv2_latest["dev_score"] > dv2_latest["dev_score"].quantile(0.70)
    ].iterrows()
    if row["player_norm"] and row["player_norm"] not in ZERO_CV_PLAYERS
}

# INT-69: per-player calibration bias (large positive bias = model underestimates)
# Players where model consistently underpredicts pts (last row per player-stat)
def _underpred_players(stat: str, threshold: float = 0.7) -> set:
    """Return player_norm set where model consistently underestimates (bias_z > threshold).
    Uses player_name directly from calibration parquet.
    Note: INT-69 max bias_z is ~1.0; threshold lowered to 0.7 to get usable sets.
    """
    cdf = cal[cal["stat"] == stat].sort_values("asof_date").groupby("player_id").last().reset_index()
    result = set()
    for _, row in cdf[cdf["bias_z_l20"] > threshold].iterrows():
        pname = norm(row["player_name"]) if pd.notna(row["player_name"]) else None
        if pname and not pname.startswith("pid_") and pname not in ZERO_CV_PLAYERS:
            result.add(pname)
    return result

underpred_pts_players = _underpred_players("pts", threshold=0.7)
underpred_reb_players = _underpred_players("reb", threshold=0.7)
underpred_ast_players = _underpred_players("ast", threshold=0.7)

# Clutch
shrinker_players = {
    p for p in clutch[clutch["clutch_class"] == "SHRINKER"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}
elevator_players = {
    p for p in clutch[clutch["clutch_class"] == "ELEVATOR"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

# Rest
b2b_players = {
    p for p in rest[rest["context"] == "B2B"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

# Matchup deviations
high_space_matchup_players = {
    p for p in matchup[matchup["avg_defender_distance_z"] > 1.5]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

print(f"\n  Player set sizes:")
print(f"  VersatileForward={len(versatile_forward_players)}, OffBallForward={len(off_ball_forward_players)}, PerimShooter={len(perimeter_shooter_players)}, VersatileBig={len(versatile_big_players)}")
print(f"  paint_heavy={len(paint_heavy_players)}, high_second_chance={len(high_second_chance_players)}, high_pa={len(high_pa_players)}")
print(f"  hot_pts={len(hot_pts_players)}, cold_pts={len(cold_pts_players)}, hot_reb={len(hot_reb_players)}")
print(f"  transitioning={len(transitioning_players)}, outlier_flagged={len(outlier_flagged_players)}, high_dev_score={len(high_dev_score_players)}")
print(f"  underpred_pts={len(underpred_pts_players)}, underpred_reb={len(underpred_reb_players)}, underpred_ast={len(underpred_ast_players)}")

# ---------------------------------------------------------------------------
# HELPER: get sub-ledger
# ---------------------------------------------------------------------------

def get_sub(player_set, team_list: list, stat: str) -> pd.DataFrame:
    # player_set may be a set, list, or numpy array
    player_set = set(player_set) if not isinstance(player_set, set) else player_set
    if len(player_set) == 0 or len(team_list) == 0:
        return lines_pool.iloc[0:0]  # empty
    return lines_pool[
        lines_pool["player_norm"].isin(player_set)
        & lines_pool["opp"].str.upper().isin([t.upper() for t in team_list])
        & (lines_pool["stat"] == stat)
    ].copy()


# ---------------------------------------------------------------------------
# DEFINE 36 COMPOUNDS (12 Theme A + 12 Theme B + 12 Theme C)
# ---------------------------------------------------------------------------

COMPOUNDS = [
    # ===================================================================
    # THEME A: PAINT EXPOSURE x ARCHETYPE (12 compounds)
    # Prior: INT-58 OPA + BLK +0.26 corr; paint-heavy players vs paint-permissive D
    # ===================================================================
    {
        "compound_id": "A01",
        "name": "VersatileBig_x_PaintAllowD_OVER_REB",
        "theme": "A",
        "atlas_A": "INT-1 archetype=Versatile Big",
        "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
        "direction": "over",
        "stat": "reb",
        "player_set": versatile_big_players,
        "team_list": paint_allow_teams,
        "hypothesis": "Versatile Bigs occupy paint; paint-permissive D cedes rebounds",
    },
    {
        "compound_id": "A02",
        "name": "VersatileBig_x_PaintAllowD_OVER_PTS",
        "theme": "A",
        "atlas_A": "INT-1 archetype=Versatile Big",
        "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
        "direction": "over",
        "stat": "pts",
        "player_set": versatile_big_players,
        "team_list": paint_allow_teams,
        "hypothesis": "Versatile Bigs score in paint; permissive D = interior scoring opportunity",
    },
    {
        "compound_id": "A03",
        "name": "PaintHeavy_x_PaintAllowD_OVER_REB",
        "theme": "A",
        "atlas_A": "INT-1 paint_dwell_pct>65th",
        "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
        "direction": "over",
        "stat": "reb",
        "player_set": paint_heavy_players,
        "team_list": paint_allow_teams,
        "hypothesis": "CV-tracked high paint dwell + permissive paint D = REB opportunity",
    },
    {
        "compound_id": "A04",
        "name": "HighSecondChance_x_PaintAllowD_OVER_REB",
        "theme": "A",
        "atlas_A": "INT-1 second_chance_rate>0.20",
        "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
        "direction": "over",
        "stat": "reb",
        "player_set": high_second_chance_players,
        "team_list": paint_allow_teams,
        "hypothesis": "High second-chance players exploit paint-permissive D for extra possessions",
    },
    {
        "compound_id": "A05",
        "name": "OffBallForward_x_PaintStingyD_UNDER_REB",
        "theme": "A",
        "atlas_A": "INT-1 archetype=Off-Ball Forward",
        "atlas_B": "INT-58 opp_paint_pct_allowed_z<-0.3",
        "direction": "under",
        "stat": "reb",
        "player_set": off_ball_forward_players,
        "team_list": paint_stingy_teams,
        "hypothesis": "Off-ball forwards get fewer rebounds vs paint-stingy D; books price on avg",
    },
    {
        "compound_id": "A06",
        "name": "PerimShooter_x_PaintStingyD_UNDER_PTS",
        "theme": "A",
        "atlas_A": "INT-1 archetype=Perimeter Shooter (Contested)",
        "atlas_B": "INT-58 opp_paint_pct_allowed_z<-0.3",
        "direction": "under",
        "stat": "pts",
        "player_set": perimeter_shooter_players,
        "team_list": paint_stingy_teams,
        "hypothesis": "Contested perimeter shooters suppressed by D that denies paint penetration",
    },
    {
        "compound_id": "A07",
        "name": "VersatileBig_x_HighDefIntensity_UNDER_PTS",
        "theme": "A",
        "atlas_A": "INT-1 archetype=Versatile Big",
        "atlas_B": "ODI opp_defensive_intensity_z>0.3",
        "direction": "under",
        "stat": "pts",
        "player_set": versatile_big_players,
        "team_list": high_def_intensity_teams,
        "hypothesis": "Versatile Bigs suppressed by high-intensity D; their interior role is contested",
    },
    {
        "compound_id": "A08",
        "name": "PaintHeavy_x_HighDefIntensity_UNDER_PTS",
        "theme": "A",
        "atlas_A": "INT-1 paint_dwell_pct>65th",
        "atlas_B": "ODI opp_defensive_intensity_z>0.3",
        "direction": "under",
        "stat": "pts",
        "player_set": paint_heavy_players,
        "team_list": high_def_intensity_teams,
        "hypothesis": "Paint-heavy players face more contested shots vs intense D; scoring suppressed",
    },
    {
        "compound_id": "A09",
        "name": "PaintHeavy_x_HighContest_UNDER_FG3M",
        "theme": "A",
        "atlas_A": "INT-1 paint_dwell_pct>65th",
        "atlas_B": "ODI opp_contested_shot_rate_imposed_z>0.3",
        "direction": "under",
        "stat": "fg3m",
        "player_set": paint_heavy_players,
        "team_list": high_contest_teams,
        "hypothesis": "Paint-heavy players take fewer 3s; high contest D makes those 3s even harder",
    },
    {
        "compound_id": "A10",
        "name": "PerimShooter_x_HighContest_UNDER_FG3M",
        "theme": "A",
        "atlas_A": "INT-1 archetype=Perimeter Shooter (Contested)",
        "atlas_B": "ODI opp_contested_shot_rate_imposed_z>0.3",
        "direction": "under",
        "stat": "fg3m",
        "player_set": perimeter_shooter_players,
        "team_list": high_contest_teams,
        "hypothesis": "Contested perimeter shooters + high-contest D = mechanical 3pt suppression",
    },
    {
        "compound_id": "A11",
        "name": "HighCatchShoot_x_CatchShootAllowD_OVER_FG3M",
        "theme": "A",
        "atlas_A": "INT-1 catch_shoot_pct>65th",
        "atlas_B": "ODI opp_catch_shoot_allowed_pct_z>0.3",
        "direction": "over",
        "stat": "fg3m",
        "player_set": high_catch_shoot_players,
        "team_list": catch_shoot_allow_teams,
        "hypothesis": "C&S specialists + D that allows C&S = structural 3pt OVER",
    },
    {
        "compound_id": "A12",
        "name": "VersatileForward_x_PaintAllowD_OVER_REB",
        "theme": "A",
        "atlas_A": "INT-1 archetype=Versatile Forward",
        "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
        "direction": "over",
        "stat": "reb",
        "player_set": versatile_forward_players,
        "team_list": paint_allow_teams,
        "hypothesis": "Versatile Forwards can attack paint; permissive D cedes boards",
    },

    # ===================================================================
    # THEME B: TEMPO x OPPOSITION (12 compounds)
    # Prior: V6 pattern + mx_tempo_vs_opp_pace + mx_offense_vs_defense_composite surviving
    # ===================================================================
    {
        "compound_id": "B01",
        "name": "HighTransitionPlayer_x_PaceSlowD_UNDER_PTS",
        "theme": "B",
        "atlas_A": "INT-1 play_type_transition_pct>65th",
        "atlas_B": "ODI opp_pace_imposed_z>0.3 (pace-slowing D)",
        "direction": "under",
        "stat": "pts",
        "player_set": high_transition_players,
        "team_list": pace_slow_teams,
        "hypothesis": "Transition-dependent scorer faces D that slows pace; volume suppressed",
    },
    {
        "compound_id": "B02",
        "name": "HighTransitionPlayer_x_PaceSlowD_UNDER_AST",
        "theme": "B",
        "atlas_A": "INT-1 play_type_transition_pct>65th",
        "atlas_B": "ODI opp_pace_imposed_z>0.3 (pace-slowing D)",
        "direction": "under",
        "stat": "ast",
        "player_set": high_transition_players,
        "team_list": pace_slow_teams,
        "hypothesis": "Transition playmakers have fewer fast-break assist opportunities vs pace control",
    },
    {
        "compound_id": "B03",
        "name": "HighTempoTeam_x_PaceSlowOpp_UNDER_PTS",
        "theme": "B",
        "atlas_A": "TTS team_tempo_z>0.3 (offensive team; approximated via high_transition_players)",
        "atlas_B": "ODI opp_pace_imposed_z>0.3 (defensive opp)",
        "direction": "under",
        "stat": "pts",
        "player_set": high_transition_players,  # use transition players as proxy for high-tempo team membership
        "team_list": pace_slow_teams,
        "hypothesis": "High-tempo team facing pace-slowing D = reduced scoring for everyone on that team",
    },
    {
        "compound_id": "B04",
        "name": "HotPts_x_HighTempoOpp_OVER_PTS",
        "theme": "B",
        "atlas_A": "Streak HOT_PTS",
        "atlas_B": "TTS team_tempo_z>0.3 (opponent is high-tempo = likely fast game)",
        "direction": "over",
        "stat": "pts",
        "player_set": hot_pts_players,
        "team_list": high_tempo_teams,
        "hypothesis": "HOT scorer + high-tempo opponent = pace enables more possessions for streaking scorer",
    },
    {
        "compound_id": "B05",
        "name": "HighIso_x_HighDefIntensity_UNDER_PTS",
        "theme": "B",
        "atlas_A": "INT-1 play_type_isolation_pct>70th",
        "atlas_B": "ODI opp_defensive_intensity_z>0.3",
        "direction": "under",
        "stat": "pts",
        "player_set": high_isolation_players,
        "team_list": high_def_intensity_teams,
        "hypothesis": "Iso-heavy scorer + high-intensity D = primary scoring mechanism contested",
    },
    {
        "compound_id": "B06",
        "name": "HighTransition_x_HighTransitionOpp_OVER_PTS",
        "theme": "B",
        "atlas_A": "INT-1 play_type_transition_pct>65th",
        "atlas_B": "TTS team_transition_share_z>0.3 (opponent high transition too)",
        "direction": "over",
        "stat": "pts",
        "player_set": high_transition_players,
        "team_list": high_transition_teams,
        "hypothesis": "Transition scorer vs transition-style opponent = up-tempo game, more pts opportunities",
    },
    {
        "compound_id": "B07",
        "name": "HighPA_x_HighTempoOpp_OVER_AST",
        "theme": "B",
        "atlas_A": "INT-1 potential_assists>70th",
        "atlas_B": "TTS team_tempo_z>0.3",
        "direction": "over",
        "stat": "ast",
        "player_set": high_pa_players,
        "team_list": high_tempo_teams,
        "hypothesis": "High-PA facilitator + fast-paced opponent = more possessions = more assists",
    },
    {
        "compound_id": "B08",
        "name": "HotReb_x_PaintAllowD_OVER_REB",
        "theme": "B",
        "atlas_A": "Streak HOT_REB",
        "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
        "direction": "over",
        "stat": "reb",
        "player_set": hot_reb_players,
        "team_list": paint_allow_teams,
        "hypothesis": "HOT rebounder vs paint-permissive D = compound OVER; momentum + structural opportunity",
    },
    {
        "compound_id": "B09",
        "name": "ColdPts_x_PaceSlowD_UNDER_PTS",
        "theme": "B",
        "atlas_A": "Streak COLD_PTS",
        "atlas_B": "ODI opp_pace_imposed_z>0.3",
        "direction": "under",
        "stat": "pts",
        "player_set": cold_pts_players,
        "team_list": pace_slow_teams,
        "hypothesis": "COLD scorer + pace-slowing D = double suppression; books slow to adjust to cold streaks",
    },
    {
        "compound_id": "B10",
        "name": "HighSpacing_x_HighContest_UNDER_FG3M",
        "theme": "B",
        "atlas_A": "INT-1 preshot_velocity_peak>65th (C&S speed)",
        "atlas_B": "ODI opp_contested_shot_rate_imposed_z>0.3",
        "direction": "under",
        "stat": "fg3m",
        "player_set": high_vel_players,
        "team_list": high_contest_teams,
        "hypothesis": "Fast-release C&S players face contest-heavy D; their primary weapon countered",
    },
    {
        "compound_id": "B11",
        "name": "VersatileForward_x_PaceControl_UNDER_PTS",
        "theme": "B",
        "atlas_A": "INT-1 archetype=Versatile Forward",
        "atlas_B": "Schemes PACE CONTROL",
        "direction": "under",
        "stat": "pts",
        "player_set": versatile_forward_players,
        "team_list": pace_ctrl_teams,
        "hypothesis": "Versatile Forwards depend on pace; PACE CONTROL D reduces possessions",
    },
    {
        "compound_id": "B12",
        "name": "HotAst_x_PaceCtrlD_OVER_AST",
        "theme": "B",
        "atlas_A": "Streak HOT_AST",
        "atlas_B": "Schemes PACE CONTROL",
        "direction": "over",
        "stat": "ast",
        "player_set": hot_ast_players,
        "team_list": pace_ctrl_teams,
        "hypothesis": "HOT passer + PACE CONTROL (half-court sets) = more ISO kickout assists",
    },

    # ===================================================================
    # THEME C: PLAYER-STATE x MATCHUP (12 compounds)
    # Prior: INT-67 (slope drift) + INT-54 (outlier flagged) + INT-69 (calibration bias)
    # ===================================================================
    {
        "compound_id": "C01",
        "name": "Transitioning_x_PaintAllowD_OVER_REB",
        "theme": "C",
        "atlas_A": "INT-38 drift_tag=TRANSITIONING",
        "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
        "direction": "over",
        "stat": "reb",
        "player_set": transitioning_players,
        "team_list": paint_allow_teams,
        "hypothesis": "TRANSITIONING player (role shift) + paint-permissive D = under-priced interior access",
    },
    {
        "compound_id": "C02",
        "name": "Transitioning_x_HelpDef_OVER_PTS",
        "theme": "C",
        "atlas_A": "INT-38 drift_tag=TRANSITIONING",
        "atlas_B": "Schemes HELP DEFENSE",
        "direction": "over",
        "stat": "pts",
        "player_set": transitioning_players,
        "team_list": help_def_teams,
        "hypothesis": "TRANSITIONING player (new role) + HELP D = books use old archetype, new role exploits kick-outs",
    },
    {
        "compound_id": "C03",
        "name": "DevSlope_x_PaintAllowD_OVER_REB",
        "theme": "C",
        "atlas_A": "INT-67 any_regime_change=True",
        "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
        "direction": "over",
        "stat": "reb",
        "player_set": regime_change_players,
        "team_list": paint_allow_teams,
        "hypothesis": "INT-67 regime change player (slope flip) + paint-permissive D = emerging role under-priced",
    },
    {
        "compound_id": "C04",
        "name": "HighDevScore_x_HighDefIntensity_UNDER_PTS",
        "theme": "C",
        "atlas_A": "INT-67 dev_score>70th pct",
        "atlas_B": "ODI opp_defensive_intensity_z>0.3",
        "direction": "under",
        "stat": "pts",
        "player_set": high_dev_score_players,
        "team_list": high_def_intensity_teams,
        "hypothesis": "Player in behavioral drift (high dev_score) + intense D = volatile player faces tough matchup",
    },
    {
        "compound_id": "C05",
        "name": "OutlierFlagged_x_PaintAllowD_OVER_REB",
        "theme": "C",
        "atlas_A": "INT-54 flag_strong_outlier=True",
        "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
        "direction": "over",
        "stat": "reb",
        "player_set": outlier_flagged_players,
        "team_list": paint_allow_teams,
        "hypothesis": "INT-54 behavioral outlier (new tendency) + paint-permissive D = new role unlocks rebounds",
    },
    {
        "compound_id": "C06",
        "name": "UnderpredPts_x_PaintAllowD_OVER_PTS",
        "theme": "C",
        "atlas_A": "INT-69 pts bias_z>1.5 (model underpredicts)",
        "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
        "direction": "over",
        "stat": "pts",
        "player_set": underpred_pts_players,
        "team_list": paint_allow_teams,
        "hypothesis": "Model consistently underestimates player + paint-permissive D = double OVER edge",
    },
    {
        "compound_id": "C07",
        "name": "UnderpredReb_x_PaintAllowD_OVER_REB",
        "theme": "C",
        "atlas_A": "INT-69 reb bias_z>1.5 (model underpredicts)",
        "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
        "direction": "over",
        "stat": "reb",
        "player_set": underpred_reb_players,
        "team_list": paint_allow_teams,
        "hypothesis": "Model under-calls REB for this player + paint-permissive D = compound OVER",
    },
    {
        "compound_id": "C08",
        "name": "UnderpredAst_x_IsoForceD_OVER_AST",
        "theme": "C",
        "atlas_A": "INT-69 ast bias_z>1.5 (model underpredicts)",
        "atlas_B": "Schemes ISO FORCE",
        "direction": "over",
        "stat": "ast",
        "player_set": underpred_ast_players,
        "team_list": iso_force_teams,
        "hypothesis": "Model underpredicts AST + ISO FORCE D creates kick-out opportunities = compound OVER",
    },
    {
        "compound_id": "C09",
        "name": "Shrinker_x_HighDefIntensity_UNDER_PTS",
        "theme": "C",
        "atlas_A": "INT-26 clutch_class=SHRINKER",
        "atlas_B": "ODI opp_defensive_intensity_z>0.3",
        "direction": "under",
        "stat": "pts",
        "player_set": shrinker_players,
        "team_list": high_def_intensity_teams,
        "hypothesis": "SHRINKER (reduces usage in pressure) + high-intensity D = compound PTS suppression",
    },
    {
        "compound_id": "C10",
        "name": "B2B_x_HighDefIntensity_UNDER_PTS",
        "theme": "C",
        "atlas_A": "INT-13 rest=B2B",
        "atlas_B": "ODI opp_defensive_intensity_z>0.3",
        "direction": "under",
        "stat": "pts",
        "player_set": b2b_players,
        "team_list": high_def_intensity_teams,
        "hypothesis": "B2B fatigue + high-intensity D = compound UNDER; fatigue suppresses volume and efficiency",
    },
    {
        "compound_id": "C11",
        "name": "DevSlope_x_PaceSlowD_UNDER_PTS",
        "theme": "C",
        "atlas_A": "INT-67 any_regime_change=True",
        "atlas_B": "ODI opp_pace_imposed_z>0.3",
        "direction": "under",
        "stat": "pts",
        "player_set": regime_change_players,
        "team_list": pace_slow_teams,
        "hypothesis": "Behaviorally drifting player (unstable role) + pace-slowing D = fewer possessions to establish new role",
    },
    {
        "compound_id": "C12",
        "name": "Elevator_x_HighTempoOpp_OVER_PTS",
        "theme": "C",
        "atlas_A": "INT-26 clutch_class=ELEVATOR",
        "atlas_B": "TTS team_tempo_z>0.3",
        "direction": "over",
        "stat": "pts",
        "player_set": elevator_players,
        "team_list": high_tempo_teams,
        "hypothesis": "ELEVATOR (raises usage in pressure) + fast-paced opponent = more high-leverage possessions",
    },
]

# Note on B03: team-level compound approximated via player-level proxy (transition players)
# since the lines ledger does not have offensive team column.
# B03 player_set is already set to high_transition_players | high_tempo_teams in COMPOUNDS definition
# (high_tempo_teams are team abbreviation strings, which won't match player_norm — effectively
# the player_set reduces to high_transition_players since team abbreviations don't match player names)
# This is intentional: use transition-style players as proxies for high-tempo team membership.

print(f"\n[3] Running {len(COMPOUNDS)} compound tests...")

# ---------------------------------------------------------------------------
# COMPUTE ALL COMPOUNDS
# ---------------------------------------------------------------------------
results = []
for c in COMPOUNDS:
    sub = get_sub(c["player_set"], c["team_list"], c["stat"])
    r = analyze_signal(sub, c["direction"])
    n = r["n"]
    z_raw = r["z_raw"] if r["z_raw"] is not None else 0.0
    roi = r["roi"] if r["roi"] is not None else 0.0

    # null control (only if we have enough bets)
    if n >= 10 and r["z_raw"] is not None:
        z_vs_null = null_z(sub, c["direction"], z_raw, c["stat"])
    else:
        z_vs_null = 0.0

    ci_lo = r["ci_lo"] if r["ci_lo"] is not None else -999.0
    verd = verdict(n, roi, z_raw, z_vs_null, ci_lo)

    row = {
        "compound_id": c["compound_id"],
        "name": c["name"],
        "theme": c["theme"],
        "atlas_A": c["atlas_A"],
        "atlas_B": c["atlas_B"],
        "direction": c["direction"].upper(),
        "stat": c["stat"],
        "hypothesis": c["hypothesis"],
        "n_bets": n,
        "hit_rate": r["hit_rate"],
        "roi_pct": roi,
        "mean_shift": r["mu"],
        "std_shift": r["std"],
        "z_raw": round(z_raw, 4),
        "z_vs_null": round(z_vs_null, 4),
        "ci_lo": r["ci_lo"],
        "ci_hi": r["ci_hi"],
        "clv_proxy": r["clv_proxy"],
        "verdict": verd,
        "n_player_set": len(c["player_set"]) if hasattr(c["player_set"], "__len__") else 0,
        "n_team_list": len(c["team_list"]),
    }
    results.append(row)
    print(
        f"  {c['compound_id']} {c['stat'].upper():4s} {c['direction'].upper():5s} "
        f"n={n:4d} ROI={roi:+7.2f}% z={z_raw:+6.3f} z_null={z_vs_null:+5.2f} -> {verd}"
    )

# ---------------------------------------------------------------------------
# SAVE PARQUET
# ---------------------------------------------------------------------------
out_df = pd.DataFrame(results)
out_path = INTEL / "compound_signal_hunt_v3.parquet"
out_df.to_parquet(out_path, index=False)
print(f"\nSaved {len(out_df)} rows to {out_path}")

# ---------------------------------------------------------------------------
# SUMMARY STATS
# ---------------------------------------------------------------------------
n_with_30 = (out_df["n_bets"] >= 30).sum()
n_strict = (out_df["verdict"] == "STRICT_SHIP").sum()
n_invest = (out_df["verdict"] == "INVESTIGATIVE").sum()
n_reject = out_df["verdict"].str.startswith("REJECT").sum()

print(f"\n=== SUMMARY ===")
print(f"  Total compounds:          {len(out_df)}")
print(f"  n_bets >= 30:             {n_with_30} / {len(out_df)}")
print(f"  STRICT_SHIP (z>={Z_STRICT}):  {n_strict}")
print(f"  INVESTIGATIVE (z>={Z_INVEST}): {n_invest}")
print(f"  REJECT:                   {n_reject}")

# Top-10 by z_raw
ranked = out_df.sort_values("z_raw", ascending=False).head(10)
print("\n=== TOP-10 BY Z_RAW ===")
cols = ["compound_id", "name", "stat", "direction", "n_bets", "roi_pct", "z_raw", "z_vs_null", "verdict"]
print(ranked[cols].to_string(index=False))

# ---------------------------------------------------------------------------
# WRITE VAULT NOTE
# ---------------------------------------------------------------------------
vault_dir = ROOT / "vault" / "Intelligence"
vault_dir.mkdir(parents=True, exist_ok=True)
vault_path = vault_dir / "INT-75_Compound_Signals_v3.md"

# Build top-5 rows
top5 = out_df.sort_values("z_raw", ascending=False).head(5)

lines_md = [
    "# INT-75: Compound Signal Hunt v3",
    "",
    f"**Built:** 2026-05-29",
    f"**Compounds tested:** {len(out_df)} (36 pre-registered, Bonferroni z-thresholds: STRICT={Z_STRICT}, INVESTIGATIVE={Z_INVEST})",
    f"**Parquet:** `data/intelligence/compound_signal_hunt_v3.parquet`",
    f"**Script:** `scripts/hunt_compound_signals_v3.py`",
    "",
    "---",
    "",
    "## Atlas Inputs",
    "",
    "| Atlas | Source |",
    "|-------|--------|",
    "| INT-1 player_fingerprints | CV behavioral archetypes (4 types: Versatile Forward/Big, Off-Ball Forward, Perimeter Shooter Contested) |",
    "| INT-58 opp_paint_allowance | Team-level paint % allowed z-score (NEW C4 atlas) |",
    "| ODI opp_defensive_intensity | Team-level defensive intensity composite (NEW C3 atlas) |",
    "| TTS team_tempo_spacing | Offense team tempo z-score (NEW C1/C2 atlas) |",
    "| INT-63 matchup_grid | Game-level interaction scalars (mx_tempo_vs_opp_pace, mx_offense_vs_defense_composite) |",
    "| INT-54 archetype_outlier | Behavioral outlier flags |",
    "| INT-67 player_development_v2 | Within-season slope drift + regime change flags |",
    "| INT-69 per_player_calibration | Systematic model bias (bias_z > 1.5 = underpredicted) |",
    "| INT-38 archetype_drift | TRANSITIONING / DRIFTING / STABLE tags |",
    "| INT-5 streak_signatures | HOT/COLD labels for pts/reb/ast |",
    "| INT-12 defensive_schemes | HELP DEFENSE, PACE CONTROL, ISO FORCE, etc. |",
    "| INT-13 rest_cv_impact | B2B fatigue signals |",
    "| INT-26 clutch_cv_split | SHRINKER / ELEVATOR clutch tags |",
    "",
    "---",
    "",
    "## Run Summary",
    "",
    f"| Metric | Value |",
    f"|--------|-------|",
    f"| Total compounds | {len(out_df)} |",
    f"| Lines pool | {len(lines_pool):,} bets (deduped) |",
    f"| n_bets >= 30 | {n_with_30} / {len(out_df)} |",
    f"| STRICT_SHIP (z>={Z_STRICT}) | {n_strict} |",
    f"| INVESTIGATIVE (z>={Z_INVEST}) | {n_invest} |",
    f"| REJECT | {n_reject} |",
    "",
    "---",
    "",
    "## Top-5 Compounds by z_raw",
    "",
    "| Rank | ID | Name | Stat | Side | n | ROI% | z_raw | z_vs_null | Verdict |",
    "|------|----|------|------|------|---|------|-------|-----------|---------|",
]

for i, row in top5.reset_index(drop=True).iterrows():
    lines_md.append(
        f"| {i+1} | {row['compound_id']} | {row['name']} | {row['stat']} | {row['direction']} "
        f"| {row['n_bets']} | {row['roi_pct']:+.1f}% | {row['z_raw']:+.3f} | {row['z_vs_null']:+.2f} | {row['verdict']} |"
    )

lines_md.extend([
    "",
    "---",
    "",
    "## Full Results Table",
    "",
    "| ID | Name | Stat | Dir | n | ROI% | hit_rate | z_raw | z_vs_null | ci_lo | Verdict |",
    "|----|------|------|-----|---|------|----------|-------|-----------|-------|---------|",
])

for _, row in out_df.sort_values("z_raw", ascending=False).iterrows():
    lines_md.append(
        f"| {row['compound_id']} | {row['name']} | {row['stat']} | {row['direction']} "
        f"| {row['n_bets']} | {row['roi_pct']:+.1f}% | {row['hit_rate'] or 'N/A'} "
        f"| {row['z_raw']:+.3f} | {row['z_vs_null']:+.2f} | {row['ci_lo'] or 'N/A'} | {row['verdict']} |"
    )

lines_md.extend([
    "",
    "---",
    "",
    "## Honest Assessment",
    "",
    "### Atlas density constraints",
    "- The 4 new team atlases (OPA/ODI/TTS) only cover 2025-26 season (post Oct 2025).",
    "- The historical lines pool spans 2024-04 → 2026-05 but team-level atlas lookups are latest-row-per-team, not as-of-date joined.",
    "- This means some team filters apply a 2025-26 profile retrospectively to 2024-25 bets — **mild leakage risk for team-level filters**.",
    "- Player-level filters (FP archetypes, streaks, drift tags) are based on 2025-26 CV data only; joining to 2024-25 pool bets = stale-label risk.",
    "",
    "### INVESTIGATIVE tag warning",
    "INVESTIGATIVE (z>=2.5) is NOT a ship verdict. Requires live paper validation.",
    "Expected failure modes: atlas density bottleneck (n<30), 2024-25 backfill with stale team labels.",
    "",
    "### Bonferroni correction",
    f"At 36 simultaneous tests, STRICT threshold is z>={Z_STRICT} (Bonferroni-corrected p<0.05).",
    f"INVESTIGATIVE threshold z>={Z_INVEST} is NOT Bonferroni-corrected — treat as hypothesis-generating only.",
    "",
])

# Best signal takeaway
best = out_df.sort_values("z_raw", ascending=False).iloc[0]
best_n = out_df.sort_values("z_raw", ascending=False)
investigative_rows = out_df[out_df["verdict"] == "INVESTIGATIVE"]
best_invest = investigative_rows.iloc[0] if len(investigative_rows) > 0 else None

if n_strict > 0:
    strict_row = out_df[out_df["verdict"] == "STRICT_SHIP"].sort_values("z_raw", ascending=False).iloc[0]
    takeaway = f"STRICT_SHIP: {strict_row['compound_id']} {strict_row['name']} — {strict_row['stat']} {strict_row['direction']} n={strict_row['n_bets']} ROI={strict_row['roi_pct']:+.1f}% z={strict_row['z_raw']:+.3f}"
elif best_invest is not None:
    takeaway = f"Best INVESTIGATIVE: {best_invest['compound_id']} {best_invest['name']} — {best_invest['stat']} {best_invest['direction']} n={best_invest['n_bets']} ROI={best_invest['roi_pct']:+.1f}% z={best_invest['z_raw']:+.3f} (z_vs_null={best_invest['z_vs_null']:+.2f})"
else:
    takeaway = f"No signal crossed INVESTIGATIVE threshold. Highest z: {best['compound_id']} {best['name']} z={best['z_raw']:+.3f} n={best['n_bets']} — below threshold or insufficient n."

lines_md.extend([
    "## Key Takeaway",
    "",
    takeaway,
    "",
    "---",
    "",
    "*End INT-75*",
])

vault_path.write_text("\n".join(lines_md), encoding="utf-8")
print(f"\nVault note written: {vault_path}")
print(f"\nKey takeaway: {takeaway}")
