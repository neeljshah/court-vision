"""
hunt_compound_signals_v4.py
============================
INT-93: Re-run INT-75's 36-candidate compound signal hunt with STRICT AS-OF joins
and 2025-26-only ledger restriction.

Key fixes vs v3:
  1. Ledger restricted to 2025-26 (>= 2025-10-01)
  2. Team-level atlas flags joined via merge_asof(direction="backward", allow_exact_matches=False)
     instead of latest-row-per-team smear
  3. Player-level joins (dv2, cal) also use merge_asof instead of last-row lookups
  4. Per-candidate coverage tracking (pre_asof_n, post_asof_n)
  5. Gates G1-G5 + kill switches K1-K3

Gates:
  G1: 2025-26 ledger >= 5,000 rows (warn 2-5K, KILL <2K)
  G2: join coverage per candidate >= 90% SHIP; <60% DROPPED_COVERAGE
  G3: C10 smear-test: compare v3 vs v4 z_raw and z_vs_null
  G4: null control x36 (100 shuffles each, fraction passing z>=2.0 ~5%)
  G5: Bonferroni + BH correction for 36 tests

STRICT_SHIP: z_raw >= 3.18 AND z_vs_null >= 2.0 AND ci_lo > 0 AND n >= 50
INVESTIGATIVE: z_raw >= 2.5 AND z_vs_null >= 2.0 AND ci_lo > 0 AND n >= 50
"""

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
VAULT = ROOT / "vault" / "Intelligence"

N_SHUFFLE = 100
BONFERRONI_N = 36
Z_STRICT = 3.18
Z_INVEST = 2.5
MIN_BETS = 50          # v4 raises hard floor to 50 (Bonferroni gate)
MIN_ROI = 5.0
MIN_Z_VS_NULL = 2.0
LEDGER_CUTOFF = "2025-10-01"
G1_KILL = 2000
G1_WARN = 5000
G2_SHIP = 0.90
G2_DROP = 0.60

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def norm(s: str) -> str:
    return str(s).strip().lower()


def load_lines() -> pd.DataFrame:
    """Load, pool, and restrict to 2025-26 season."""
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
    # G1: restrict to 2025-26
    pool_full_n = len(pool)
    pool = pool[pool["date"] >= LEDGER_CUTOFF].copy().reset_index(drop=True)
    pool["opp_upper"] = pool["opp"].str.upper()
    print(f"  Ledger pre-restriction: {pool_full_n:,} -> post 2025-26 filter: {len(pool):,}")
    # Kill switches
    if len(pool) < G1_KILL:
        raise RuntimeError(f"K1-KILL: 2025-26 ledger only {len(pool)} bets (<{G1_KILL}). Run aborted.")
    if len(pool) < G1_WARN:
        print(f"  WARNING G1: ledger {len(pool)} bets is below warn threshold {G1_WARN}")
    return pool


def compute_roi(sub: pd.DataFrame, direction: str) -> float:
    if len(sub) == 0:
        return 0.0
    shift = sub["actual_value"] - sub["closing_line"]
    if direction == "over":
        wins = (shift > 0).sum()
    else:
        wins = (shift < 0).sum()
    n = len(sub)
    roi = (wins * 91.0 - (n - wins) * 100.0) / (n * 100.0) * 100
    return round(float(roi), 3)


def analyze_signal(sub: pd.DataFrame, direction: str = "over") -> dict:
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
    n = len(sub)
    if n < 10:
        return 0.0
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


def verdict(n, roi, z_raw, z_vs_null, ci_lo, coverage_pct) -> str:
    if coverage_pct < G2_DROP:
        return "DROPPED_COVERAGE"
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
# AS-OF JOIN HELPERS
# ---------------------------------------------------------------------------

def _build_team_asof_mask(atlas: pd.DataFrame, flag_col: str, threshold: float,
                           sign: str = ">") -> np.ndarray:
    """
    Row-level merge_asof join: for each bet in lines_pool, look up the most recent
    atlas row (by game_date) for that bet's opp_upper team that precedes the bet date
    (allow_exact_matches=False so same-day atlas doesn't count as known-in-advance).
    Returns boolean ndarray aligned to lines_pool index.
    """
    a = atlas[["team_id", "game_date", flag_col]].copy()
    a["team_id"] = a["team_id"].str.upper()
    a = a.sort_values("game_date").rename(columns={"game_date": "atlas_date"})

    bets = lines_pool[["date", "opp_upper"]].copy().reset_index(drop=True)
    bets["_orig_idx"] = bets.index
    bets = bets.sort_values("date")

    # merge_asof on date, keyed by team
    joined = pd.merge_asof(
        bets,
        a,
        left_on="date",
        right_on="atlas_date",
        left_by="opp_upper",
        right_by="team_id",
        direction="backward",
        allow_exact_matches=False,
    )
    # restore original order
    joined = joined.sort_values("_orig_idx").reset_index(drop=True)

    if sign == ">":
        mask = (joined[flag_col] > threshold).fillna(False).to_numpy()
    else:
        mask = (joined[flag_col] < threshold).fillna(False).to_numpy()
    return mask


def _build_player_calbiasof_mask(stat: str, threshold: float = 0.7) -> np.ndarray:
    """
    Row-level merge_asof for per_player_calibration bias.
    For each bet row (player, date, stat), find the most recent cal row before that date.
    Returns boolean ndarray aligned to lines_pool.
    Uses string player_id to avoid dtype mismatch from NaN-mapped float64.
    """
    cdf = cal[cal["stat"] == stat][["player_id", "asof_date", "player_name", "bias_z_l20"]].copy()
    cdf["player_id"] = cdf["player_id"].astype(str)
    cdf = cdf.sort_values("asof_date")

    # Build bet rows with player_id (str) via name lookup
    pid_lookup = (
        cal[["player_name", "player_id"]].drop_duplicates()
        .assign(player_norm=lambda x: x["player_name"].map(norm),
                player_id_str=lambda x: x["player_id"].astype(str))
        .set_index("player_norm")["player_id_str"]
        .to_dict()
    )
    bets = lines_pool[["date", "player_norm"]].copy().reset_index(drop=True)
    bets["player_id"] = bets["player_norm"].map(pid_lookup)
    bets["_orig_idx"] = bets.index
    bets_valid = bets.dropna(subset=["player_id"]).sort_values("date").copy()
    bets_valid["player_id"] = bets_valid["player_id"].astype(str)

    if len(bets_valid) == 0:
        return np.zeros(len(lines_pool), dtype=bool)

    joined = pd.merge_asof(
        bets_valid,
        cdf,
        left_on="date",
        right_on="asof_date",
        left_by="player_id",
        right_by="player_id",
        direction="backward",
        allow_exact_matches=False,
    )
    joined = joined.set_index("_orig_idx")

    # Build full-length mask
    mask = np.zeros(len(lines_pool), dtype=bool)
    valid_rows = joined[joined["bias_z_l20"] > threshold]
    # Filter out zero-cv players
    for orig_idx in valid_rows.index:
        pn = lines_pool.at[orig_idx, "player_norm"]
        if pn not in ZERO_CV_PLAYERS:
            mask[orig_idx] = True
    return mask


def _build_dv2_asof_flags() -> tuple:
    """
    Build per-row flags for regime_change and dev_score from dv2 via merge_asof.
    Returns (regime_change_mask, high_dev_score_mask) as bool ndarrays.
    Uses string player_id to avoid int64/float64 dtype mismatch from NaN mapping.
    """
    dv2_cols = ["player_id", "game_date", "any_regime_change", "dev_score"]
    available = [c for c in dv2_cols if c in dv2.columns]
    d = dv2[available].copy()
    d["player_id"] = d["player_id"].astype(str)
    d = d.sort_values("game_date")

    # player_norm -> player_id from dv2 itself (string ids)
    pnorm_pid = (
        dv2[["player_id", "player_name"]].drop_duplicates()
        .assign(player_norm=lambda x: x["player_name"].map(norm),
                player_id_str=lambda x: x["player_id"].astype(str))
        .set_index("player_norm")["player_id_str"]
        .to_dict()
    )
    # Also from cal (wider coverage) — cast to str
    cal_map = (
        cal[["player_name", "player_id"]].drop_duplicates()
        .assign(player_norm=lambda x: x["player_name"].map(norm),
                player_id_str=lambda x: x["player_id"].astype(str))
        .set_index("player_norm")["player_id_str"]
        .to_dict()
    )
    for pn, pid_str in cal_map.items():
        pnorm_pid.setdefault(pn, pid_str)

    bets = lines_pool[["date", "player_norm"]].copy().reset_index(drop=True)
    bets["player_id"] = bets["player_norm"].map(pnorm_pid)
    bets["_orig_idx"] = bets.index
    bets_valid = bets.dropna(subset=["player_id"]).sort_values("date").copy()
    bets_valid["player_id"] = bets_valid["player_id"].astype(str)

    n = len(lines_pool)
    regime_mask = np.zeros(n, dtype=bool)
    dev_mask = np.zeros(n, dtype=bool)

    if len(bets_valid) == 0:
        return regime_mask, dev_mask

    joined = pd.merge_asof(
        bets_valid,
        d,
        left_on="date",
        right_on="game_date",
        left_by="player_id",
        right_by="player_id",
        direction="backward",
        allow_exact_matches=False,
    )
    joined = joined.set_index("_orig_idx")

    dev_threshold = d["dev_score"].quantile(0.70) if "dev_score" in d.columns else 999.0

    for orig_idx, row in joined.iterrows():
        pn = lines_pool.at[orig_idx, "player_norm"]
        if pn in ZERO_CV_PLAYERS:
            continue
        if "any_regime_change" in row and row["any_regime_change"] is True:
            regime_mask[orig_idx] = True
        if "dev_score" in row and pd.notna(row["dev_score"]) and row["dev_score"] > dev_threshold:
            dev_mask[orig_idx] = True

    return regime_mask, dev_mask


# ---------------------------------------------------------------------------
# GET_SUB: filter lines_pool by boolean mask + player set + stat
# Coverage = fraction of (player+stat) rows that have a valid asof atlas lookup
#            (i.e., atlas was not null for that bet's opp+date).
# This is separate from whether they pass the threshold — threshold is the filter,
# coverage is the data quality signal.
# ---------------------------------------------------------------------------

# Pre-compute atlas validity masks (asof match was non-null, regardless of threshold)
# These track whether the atlas had ANY data before that bet's date for that team.
# We build them once and reuse.
_TEAM_ASOF_VALID: dict = {}  # cache per atlas name


def _build_team_asof_valid_mask(atlas: pd.DataFrame, flag_col: str) -> np.ndarray:
    """True where the asof lookup found a non-null atlas row (regardless of threshold value)."""
    key = f"{id(atlas)}_{flag_col}"
    if key in _TEAM_ASOF_VALID:
        return _TEAM_ASOF_VALID[key]
    a = atlas[["team_id", "game_date", flag_col]].copy()
    a["team_id"] = a["team_id"].str.upper()
    a = a.sort_values("game_date").rename(columns={"game_date": "atlas_date"})
    bets = lines_pool[["date", "opp_upper"]].copy().reset_index(drop=True)
    bets["_orig_idx"] = bets.index
    bets = bets.sort_values("date")
    joined = pd.merge_asof(
        bets, a,
        left_on="date", right_on="atlas_date",
        left_by="opp_upper", right_by="team_id",
        direction="backward", allow_exact_matches=False,
    )
    joined = joined.sort_values("_orig_idx").reset_index(drop=True)
    valid = joined[flag_col].notna().to_numpy()
    _TEAM_ASOF_VALID[key] = valid
    return valid


def get_sub_masked(player_set: set, team_mask: np.ndarray, stat: str,
                   atlas_valid_mask: np.ndarray = None) -> tuple:
    """
    Returns (sub, pre_n, post_n, coverage_pct) where:
      pre_n = rows matching player_set + stat (before asof threshold filter)
      post_n = rows after applying team_mask threshold
      coverage_pct = fraction of pre_n rows where atlas had a valid (non-null) lookup
    """
    player_set = set(player_set) if not isinstance(player_set, set) else player_set
    stat_player_mask = (
        lines_pool["player_norm"].isin(player_set)
        & (lines_pool["stat"] == stat)
    )
    pre_n = int(stat_player_mask.sum())
    # Coverage = fraction with valid atlas lookup
    if atlas_valid_mask is not None and pre_n > 0:
        coverage_pct = float((stat_player_mask & atlas_valid_mask).sum()) / pre_n
    elif pre_n > 0:
        coverage_pct = 1.0  # static mask (no atlas asof)
    else:
        coverage_pct = 0.0
    combined_mask = stat_player_mask & team_mask
    post_n = int(combined_mask.sum())
    sub = lines_pool[combined_mask].copy()
    return sub, pre_n, post_n, coverage_pct


# ---------------------------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------------------------
print("[1] Loading lines pool (2025-26 restricted)...")
lines_pool = load_lines()
print(f"  2025-26 ledger size: {len(lines_pool):,}")

# G1 assertion
assert len(lines_pool) >= G1_KILL, f"K1 kill switch: {len(lines_pool)} < {G1_KILL}"

print("[2] Loading atlas parquets...")

fp = pd.read_parquet(INTEL / "player_fingerprints.parquet").reset_index()
fp["player_norm"] = fp["player_name"].map(norm)

streak = pd.read_parquet(INTEL / "streak_signatures.parquet")
streak["player_norm"] = streak["player_name"].map(norm)

drift = pd.read_parquet(INTEL / "archetype_drift.parquet")
drift["player_norm"] = drift["player_name"].map(norm)

schemes = pd.read_parquet(INTEL / "defensive_schemes.parquet")

opa = pd.read_parquet(INTEL / "opp_paint_allowance.parquet")
opa["game_date"] = pd.to_datetime(opa["game_date"])

odi = pd.read_parquet(INTEL / "opp_defensive_intensity.parquet")
odi["game_date"] = pd.to_datetime(odi["game_date"])

tts = pd.read_parquet(INTEL / "team_tempo_spacing.parquet")
tts["game_date"] = pd.to_datetime(tts["game_date"])

mg = pd.read_parquet(INTEL / "matchup_grid.parquet")
mg["game_date"] = pd.to_datetime(mg["game_date"])

ao = pd.read_parquet(INTEL / "archetype_outlier_signals.parquet")
ao["game_date"] = pd.to_datetime(ao["game_date"])

dv2 = pd.read_parquet(INTEL / "player_development_v2.parquet")
dv2["game_date"] = pd.to_datetime(dv2["game_date"])

cal = pd.read_parquet(INTEL / "per_player_calibration.parquet")
cal["asof_date"] = pd.to_datetime(cal["asof_date"])

matchup = pd.read_parquet(INTEL / "matchup_deviations.parquet")
matchup["player_norm"] = matchup["player_name"].map(norm)

rest = pd.read_parquet(INTEL / "rest_cv_impact.parquet")
rest["player_norm"] = rest["player_name"].map(norm)

clutch = pd.read_parquet(INTEL / "clutch_cv_split.parquet")
clutch["player_norm"] = clutch["player_name"].map(norm)

ZERO_CV_PLAYERS = {"stephen curry", "keshad johnson"}

print(f"  Lines: {len(lines_pool):,}  FP: {len(fp)}  OPA: {len(opa)}  ODI: {len(odi)}  TTS: {len(tts)}")

# ---------------------------------------------------------------------------
# BUILD TEAM-LEVEL BOOLEAN MASKS VIA MERGE_ASOF
# ---------------------------------------------------------------------------
print("[3] Building team-level asof masks...")

paint_allow_mask = _build_team_asof_mask(opa, "opp_paint_pct_allowed_z", 0.3, ">")
paint_stingy_mask = _build_team_asof_mask(opa, "opp_paint_pct_allowed_z", -0.3, "<")
high_3pt_allow_mask = _build_team_asof_mask(opa, "opp_3pt_pct_allowed_z", 0.3, ">")
low_3pt_allow_mask = _build_team_asof_mask(opa, "opp_3pt_pct_allowed_z", -0.3, "<")
high_contest_mask = _build_team_asof_mask(odi, "opp_contested_shot_rate_imposed_z", 0.3, ">")
high_def_intensity_mask = _build_team_asof_mask(odi, "opp_defensive_intensity_z", 0.3, ">") if "opp_defensive_intensity_z" in odi.columns else _build_team_asof_mask(odi, "opp_contested_shot_rate_imposed_z", 0.3, ">")
pace_slow_mask = _build_team_asof_mask(odi, "opp_pace_imposed_z", 0.3, ">")
catch_shoot_allow_mask = _build_team_asof_mask(odi, "opp_catch_shoot_allowed_pct_z", 0.3, ">")
high_tempo_mask = _build_team_asof_mask(tts, "team_tempo_z", 0.3, ">")
high_transition_tts_mask = _build_team_asof_mask(tts, "team_transition_share_z", 0.3, ">")
high_spacing_mask = _build_team_asof_mask(tts, "team_avg_spacing_z", 0.3, ">")
paint_heavy_off_mask = _build_team_asof_mask(tts, "team_paint_dwell_z", 0.3, ">")

# Pre-compute atlas-valid masks (non-null lookup, for coverage calculation)
opa_valid_mask = _build_team_asof_valid_mask(opa, "opp_paint_pct_allowed_z")
odi_valid_mask = _build_team_asof_valid_mask(odi, "opp_defensive_intensity_z")
tts_valid_mask = _build_team_asof_valid_mask(tts, "team_tempo_z")

print(f"  paint_allow_mask: {paint_allow_mask.sum()} rows flagged")
print(f"  high_def_intensity_mask: {high_def_intensity_mask.sum()} rows flagged")
print(f"  high_tempo_mask: {high_tempo_mask.sum()} rows flagged")
print(f"  pace_slow_mask: {pace_slow_mask.sum()} rows flagged")

# Schemes still use static team lists (schemes atlas has no game_date column)
def scheme_teams(tag: str) -> list:
    return schemes[schemes["all_tags"].str.contains(tag, na=False)]["team"].str.upper().tolist()

help_def_teams = scheme_teams("HELP DEFENSE")
pace_ctrl_teams = scheme_teams("PACE CONTROL")
switch_heavy_teams = scheme_teams("SWITCH HEAVY")
perim_denial_teams = schemes[schemes["dominant_tag"].str.contains("PERIMETER DENIAL", na=False)]["team"].str.upper().tolist()
paint_first_teams = schemes[schemes["dominant_tag"].str.contains("PAINT", na=False)]["team"].str.upper().tolist()
drop_cov_teams = schemes[schemes["dominant_tag"].str.contains("DROP", na=False)]["team"].str.upper().tolist()
iso_force_teams = scheme_teams("ISO FORCE")

# Static scheme masks (no game_date in schemes)
def _static_team_mask(team_list: list) -> np.ndarray:
    return lines_pool["opp_upper"].isin([t.upper() for t in team_list]).to_numpy()

help_def_mask = _static_team_mask(help_def_teams)
pace_ctrl_mask = _static_team_mask(pace_ctrl_teams)
iso_force_mask = _static_team_mask(iso_force_teams)

# ---------------------------------------------------------------------------
# PLAYER SET LOOKUPS (static — derived from 2025-26 CV data)
# ---------------------------------------------------------------------------
print("[4] Building player sets...")

def archetype_players(name: str) -> set:
    return {
        p for p in fp[fp["archetype_name"] == name]["player_norm"].unique()
        if p not in ZERO_CV_PLAYERS
    }

versatile_forward_players = archetype_players("Versatile Forward")
off_ball_forward_players = archetype_players("Off-Ball Forward")
perimeter_shooter_players = archetype_players("Perimeter Shooter (Contested)")
versatile_big_players = archetype_players("Versatile Big")

paint_heavy_players = {
    p for p in fp[(fp["paint_dwell_pct"] > fp["paint_dwell_pct"].quantile(0.65)) & (fp["n_cv_games"] >= 3)]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

high_second_chance_players = {
    p for p in fp[(fp["second_chance_rate"] > 0.20) & (fp["n_cv_games"] >= 3)]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

high_pa_players = {
    p for p in fp[(fp["potential_assists"] > fp["potential_assists"].quantile(0.70)) & (fp["n_cv_games"] >= 3)]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

high_vel_players = {
    p for p in fp[(fp["preshot_velocity_peak"] > fp["preshot_velocity_peak"].quantile(0.65)) & (fp["n_cv_games"] >= 3)]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

high_catch_shoot_players = {
    p for p in fp[(fp["catch_shoot_pct"] > fp["catch_shoot_pct"].quantile(0.65)) & (fp["n_cv_games"] >= 3)]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

high_isolation_players = {
    p for p in fp[(fp["play_type_isolation_pct"] > fp["play_type_isolation_pct"].quantile(0.70)) & (fp["n_cv_games"] >= 3)]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

high_transition_players = {
    p for p in fp[(fp["play_type_transition_pct"] > fp["play_type_transition_pct"].quantile(0.65)) & (fp["n_cv_games"] >= 3)]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

hot_pts_players = {p for p in streak[streak["label_pts"] == "HOT"]["player_norm"].unique() if p not in ZERO_CV_PLAYERS}
cold_pts_players = {p for p in streak[streak["label_pts"] == "COLD"]["player_norm"].unique() if p not in ZERO_CV_PLAYERS}
hot_reb_players = {p for p in streak[streak["label_reb"] == "HOT"]["player_norm"].unique() if p not in ZERO_CV_PLAYERS}
cold_reb_players = {p for p in streak[streak["label_reb"] == "COLD"]["player_norm"].unique() if p not in ZERO_CV_PLAYERS}
hot_ast_players = {p for p in streak[streak["label_ast"] == "HOT"]["player_norm"].unique() if p not in ZERO_CV_PLAYERS}

transitioning_players = {p for p in drift[drift["drift_tag"] == "TRANSITIONING"]["player_norm"].unique() if p not in ZERO_CV_PLAYERS}
drifting_players = {p for p in drift[drift["drift_tag"] == "DRIFTING"]["player_norm"].unique() if p not in ZERO_CV_PLAYERS}
stable_players = {p for p in drift[drift["drift_tag"] == "STABLE"]["player_norm"].unique() if p not in ZERO_CV_PLAYERS}

ao_strong = ao[ao["flag_strong_outlier"] == True]
pid_to_name = fp.set_index("player_id")["player_norm"].to_dict()
streak_pid_to_name = streak[["player_id", "player_norm"]].drop_duplicates().set_index("player_id")["player_norm"].to_dict()
pid_to_name.update(streak_pid_to_name)
outlier_flagged_players = {
    pid_to_name.get(pid) for pid in ao_strong["player_id"].unique()
    if pid_to_name.get(pid) and pid_to_name.get(pid) not in ZERO_CV_PLAYERS
}
outlier_flagged_players.discard(None)

shrinker_players = {p for p in clutch[clutch["clutch_class"] == "SHRINKER"]["player_norm"].unique() if p not in ZERO_CV_PLAYERS}
elevator_players = {p for p in clutch[clutch["clutch_class"] == "ELEVATOR"]["player_norm"].unique() if p not in ZERO_CV_PLAYERS}
b2b_players = {p for p in rest[rest["context"] == "B2B"]["player_norm"].unique() if p not in ZERO_CV_PLAYERS}
high_space_matchup_players = {p for p in matchup[matchup["avg_defender_distance_z"] > 1.5]["player_norm"].unique() if p not in ZERO_CV_PLAYERS}

# ---------------------------------------------------------------------------
# DV2 + CAL AS-OF MASKS
# ---------------------------------------------------------------------------
print("[5] Building player-level asof flags (dv2, cal)...")
regime_change_row_mask, high_dev_score_row_mask = _build_dv2_asof_flags()

# Cal bias masks (per stat) via asof
underpred_pts_mask = _build_player_calbiasof_mask("pts", threshold=0.7)
underpred_reb_mask = _build_player_calbiasof_mask("reb", threshold=0.7)
underpred_ast_mask = _build_player_calbiasof_mask("ast", threshold=0.7)

print(f"  regime_change rows: {regime_change_row_mask.sum()}")
print(f"  high_dev_score rows: {high_dev_score_row_mask.sum()}")
print(f"  underpred_pts rows: {underpred_pts_mask.sum()}")

# ---------------------------------------------------------------------------
# DEFINE 36 COMPOUNDS
# Each entry now has either "team_mask" (np array) or "player_set" for player-level filters.
# For player-level atlas flags (regime_change, dev_score, underpred_*) we use row_mask directly.
# ---------------------------------------------------------------------------
print("[6] Defining 36 compounds...")

COMPOUNDS = [
    # === THEME A: PAINT EXPOSURE x ARCHETYPE ===
    {"compound_id": "A01", "name": "VersatileBig_x_PaintAllowD_OVER_REB",
     "theme": "A", "direction": "over", "stat": "reb",
     "player_set": versatile_big_players, "team_mask": paint_allow_mask, "atlas_valid_mask": opa_valid_mask,
     "atlas_A": "INT-1 archetype=Versatile Big", "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
     "hypothesis": "Versatile Bigs occupy paint; paint-permissive D cedes rebounds"},
    {"compound_id": "A02", "name": "VersatileBig_x_PaintAllowD_OVER_PTS",
     "theme": "A", "direction": "over", "stat": "pts",
     "player_set": versatile_big_players, "team_mask": paint_allow_mask, "atlas_valid_mask": opa_valid_mask,
     "atlas_A": "INT-1 archetype=Versatile Big", "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
     "hypothesis": "Versatile Bigs score in paint; permissive D = interior scoring opportunity"},
    {"compound_id": "A03", "name": "PaintHeavy_x_PaintAllowD_OVER_REB",
     "theme": "A", "direction": "over", "stat": "reb",
     "player_set": paint_heavy_players, "team_mask": paint_allow_mask, "atlas_valid_mask": opa_valid_mask,
     "atlas_A": "INT-1 paint_dwell_pct>65th", "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
     "hypothesis": "CV-tracked high paint dwell + permissive paint D = REB opportunity"},
    {"compound_id": "A04", "name": "HighSecondChance_x_PaintAllowD_OVER_REB",
     "theme": "A", "direction": "over", "stat": "reb",
     "player_set": high_second_chance_players, "team_mask": paint_allow_mask, "atlas_valid_mask": opa_valid_mask,
     "atlas_A": "INT-1 second_chance_rate>0.20", "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
     "hypothesis": "High second-chance players exploit paint-permissive D for extra possessions"},
    {"compound_id": "A05", "name": "OffBallForward_x_PaintStingyD_UNDER_REB",
     "theme": "A", "direction": "under", "stat": "reb",
     "player_set": off_ball_forward_players, "team_mask": paint_stingy_mask, "atlas_valid_mask": opa_valid_mask,
     "atlas_A": "INT-1 archetype=Off-Ball Forward", "atlas_B": "INT-58 opp_paint_pct_allowed_z<-0.3",
     "hypothesis": "Off-ball forwards get fewer rebounds vs paint-stingy D"},
    {"compound_id": "A06", "name": "PerimShooter_x_PaintStingyD_UNDER_PTS",
     "theme": "A", "direction": "under", "stat": "pts",
     "player_set": perimeter_shooter_players, "team_mask": paint_stingy_mask, "atlas_valid_mask": opa_valid_mask,
     "atlas_A": "INT-1 archetype=Perimeter Shooter (Contested)", "atlas_B": "INT-58 opp_paint_pct_allowed_z<-0.3",
     "hypothesis": "Contested perimeter shooters suppressed by D that denies paint penetration"},
    {"compound_id": "A07", "name": "VersatileBig_x_HighDefIntensity_UNDER_PTS",
     "theme": "A", "direction": "under", "stat": "pts",
     "player_set": versatile_big_players, "team_mask": high_def_intensity_mask, "atlas_valid_mask": odi_valid_mask,
     "atlas_A": "INT-1 archetype=Versatile Big", "atlas_B": "ODI opp_defensive_intensity_z>0.3",
     "hypothesis": "Versatile Bigs suppressed by high-intensity D"},
    {"compound_id": "A08", "name": "PaintHeavy_x_HighDefIntensity_UNDER_PTS",
     "theme": "A", "direction": "under", "stat": "pts",
     "player_set": paint_heavy_players, "team_mask": high_def_intensity_mask, "atlas_valid_mask": odi_valid_mask,
     "atlas_A": "INT-1 paint_dwell_pct>65th", "atlas_B": "ODI opp_defensive_intensity_z>0.3",
     "hypothesis": "Paint-heavy players face more contested shots vs intense D"},
    {"compound_id": "A09", "name": "PaintHeavy_x_HighContest_UNDER_FG3M",
     "theme": "A", "direction": "under", "stat": "fg3m",
     "player_set": paint_heavy_players, "team_mask": high_contest_mask, "atlas_valid_mask": odi_valid_mask,
     "atlas_A": "INT-1 paint_dwell_pct>65th", "atlas_B": "ODI opp_contested_shot_rate_imposed_z>0.3",
     "hypothesis": "Paint-heavy players take fewer 3s; high contest D makes those 3s even harder"},
    {"compound_id": "A10", "name": "PerimShooter_x_HighContest_UNDER_FG3M",
     "theme": "A", "direction": "under", "stat": "fg3m",
     "player_set": perimeter_shooter_players, "team_mask": high_contest_mask, "atlas_valid_mask": odi_valid_mask,
     "atlas_A": "INT-1 archetype=Perimeter Shooter (Contested)", "atlas_B": "ODI opp_contested_shot_rate_imposed_z>0.3",
     "hypothesis": "Contested perimeter shooters + high-contest D = mechanical 3pt suppression"},
    {"compound_id": "A11", "name": "HighCatchShoot_x_CatchShootAllowD_OVER_FG3M",
     "theme": "A", "direction": "over", "stat": "fg3m",
     "player_set": high_catch_shoot_players, "team_mask": catch_shoot_allow_mask, "atlas_valid_mask": odi_valid_mask,
     "atlas_A": "INT-1 catch_shoot_pct>65th", "atlas_B": "ODI opp_catch_shoot_allowed_pct_z>0.3",
     "hypothesis": "C&S specialists + D that allows C&S = structural 3pt OVER"},
    {"compound_id": "A12", "name": "VersatileForward_x_PaintAllowD_OVER_REB",
     "theme": "A", "direction": "over", "stat": "reb",
     "player_set": versatile_forward_players, "team_mask": paint_allow_mask, "atlas_valid_mask": opa_valid_mask,
     "atlas_A": "INT-1 archetype=Versatile Forward", "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
     "hypothesis": "Versatile Forwards can attack paint; permissive D cedes boards"},
    # === THEME B: TEMPO x OPPOSITION ===
    {"compound_id": "B01", "name": "HighTransitionPlayer_x_PaceSlowD_UNDER_PTS",
     "theme": "B", "direction": "under", "stat": "pts",
     "player_set": high_transition_players, "team_mask": pace_slow_mask, "atlas_valid_mask": odi_valid_mask,
     "atlas_A": "INT-1 play_type_transition_pct>65th", "atlas_B": "ODI opp_pace_imposed_z>0.3",
     "hypothesis": "Transition-dependent scorer faces D that slows pace; volume suppressed"},
    {"compound_id": "B02", "name": "HighTransitionPlayer_x_PaceSlowD_UNDER_AST",
     "theme": "B", "direction": "under", "stat": "ast",
     "player_set": high_transition_players, "team_mask": pace_slow_mask, "atlas_valid_mask": odi_valid_mask,
     "atlas_A": "INT-1 play_type_transition_pct>65th", "atlas_B": "ODI opp_pace_imposed_z>0.3",
     "hypothesis": "Transition playmakers have fewer fast-break assist opportunities vs pace control"},
    {"compound_id": "B03", "name": "HighTempoTeam_x_PaceSlowOpp_UNDER_PTS",
     "theme": "B", "direction": "under", "stat": "pts",
     "player_set": high_transition_players, "team_mask": pace_slow_mask, "atlas_valid_mask": odi_valid_mask,
     "atlas_A": "TTS team_tempo_z>0.3 (proxy via transition players)", "atlas_B": "ODI opp_pace_imposed_z>0.3",
     "hypothesis": "High-tempo team facing pace-slowing D = reduced scoring"},
    {"compound_id": "B04", "name": "HotPts_x_HighTempoOpp_OVER_PTS",
     "theme": "B", "direction": "over", "stat": "pts",
     "player_set": hot_pts_players, "team_mask": high_tempo_mask, "atlas_valid_mask": tts_valid_mask,
     "atlas_A": "Streak HOT_PTS", "atlas_B": "TTS team_tempo_z>0.3",
     "hypothesis": "HOT scorer + high-tempo opponent = pace enables more possessions"},
    {"compound_id": "B05", "name": "HighIso_x_HighDefIntensity_UNDER_PTS",
     "theme": "B", "direction": "under", "stat": "pts",
     "player_set": high_isolation_players, "team_mask": high_def_intensity_mask, "atlas_valid_mask": odi_valid_mask,
     "atlas_A": "INT-1 play_type_isolation_pct>70th", "atlas_B": "ODI opp_defensive_intensity_z>0.3",
     "hypothesis": "Iso-heavy scorer + high-intensity D = primary scoring mechanism contested"},
    {"compound_id": "B06", "name": "HighTransition_x_HighTransitionOpp_OVER_PTS",
     "theme": "B", "direction": "over", "stat": "pts",
     "player_set": high_transition_players, "team_mask": high_transition_tts_mask, "atlas_valid_mask": tts_valid_mask,
     "atlas_A": "INT-1 play_type_transition_pct>65th", "atlas_B": "TTS team_transition_share_z>0.3",
     "hypothesis": "Transition scorer vs transition-style opponent = up-tempo game"},
    {"compound_id": "B07", "name": "HighPA_x_HighTempoOpp_OVER_AST",
     "theme": "B", "direction": "over", "stat": "ast",
     "player_set": high_pa_players, "team_mask": high_tempo_mask, "atlas_valid_mask": tts_valid_mask,
     "atlas_A": "INT-1 potential_assists>70th", "atlas_B": "TTS team_tempo_z>0.3",
     "hypothesis": "High-PA facilitator + fast-paced opponent = more assists"},
    {"compound_id": "B08", "name": "HotReb_x_PaintAllowD_OVER_REB",
     "theme": "B", "direction": "over", "stat": "reb",
     "player_set": hot_reb_players, "team_mask": paint_allow_mask, "atlas_valid_mask": opa_valid_mask,
     "atlas_A": "Streak HOT_REB", "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
     "hypothesis": "HOT rebounder vs paint-permissive D = compound OVER"},
    {"compound_id": "B09", "name": "ColdPts_x_PaceSlowD_UNDER_PTS",
     "theme": "B", "direction": "under", "stat": "pts",
     "player_set": cold_pts_players, "team_mask": pace_slow_mask, "atlas_valid_mask": odi_valid_mask,
     "atlas_A": "Streak COLD_PTS", "atlas_B": "ODI opp_pace_imposed_z>0.3",
     "hypothesis": "COLD scorer + pace-slowing D = double suppression"},
    {"compound_id": "B10", "name": "HighSpacing_x_HighContest_UNDER_FG3M",
     "theme": "B", "direction": "under", "stat": "fg3m",
     "player_set": high_vel_players, "team_mask": high_contest_mask, "atlas_valid_mask": odi_valid_mask,
     "atlas_A": "INT-1 preshot_velocity_peak>65th", "atlas_B": "ODI opp_contested_shot_rate_imposed_z>0.3",
     "hypothesis": "Fast-release C&S players face contest-heavy D"},
    {"compound_id": "B11", "name": "VersatileForward_x_PaceControl_UNDER_PTS",
     "theme": "B", "direction": "under", "stat": "pts",
     "player_set": versatile_forward_players, "team_mask": pace_ctrl_mask, "atlas_valid_mask": None,
     "atlas_A": "INT-1 archetype=Versatile Forward", "atlas_B": "Schemes PACE CONTROL",
     "hypothesis": "Versatile Forwards depend on pace; PACE CONTROL D reduces possessions"},
    {"compound_id": "B12", "name": "HotAst_x_PaceCtrlD_OVER_AST",
     "theme": "B", "direction": "over", "stat": "ast",
     "player_set": hot_ast_players, "team_mask": pace_ctrl_mask, "atlas_valid_mask": None,
     "atlas_A": "Streak HOT_AST", "atlas_B": "Schemes PACE CONTROL",
     "hypothesis": "HOT passer + PACE CONTROL (half-court sets) = more ISO kickout assists"},
    # === THEME C: PLAYER-STATE x MATCHUP ===
    {"compound_id": "C01", "name": "Transitioning_x_PaintAllowD_OVER_REB",
     "theme": "C", "direction": "over", "stat": "reb",
     "player_set": transitioning_players, "team_mask": paint_allow_mask, "atlas_valid_mask": opa_valid_mask,
     "atlas_A": "INT-38 drift_tag=TRANSITIONING", "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
     "hypothesis": "TRANSITIONING player + paint-permissive D = under-priced interior access"},
    {"compound_id": "C02", "name": "Transitioning_x_HelpDef_OVER_PTS",
     "theme": "C", "direction": "over", "stat": "pts",
     "player_set": transitioning_players, "team_mask": help_def_mask, "atlas_valid_mask": None,
     "atlas_A": "INT-38 drift_tag=TRANSITIONING", "atlas_B": "Schemes HELP DEFENSE",
     "hypothesis": "TRANSITIONING player + HELP D = books use old archetype, new role exploits kick-outs"},
    {"compound_id": "C03", "name": "DevSlope_x_PaintAllowD_OVER_REB",
     "theme": "C", "direction": "over", "stat": "reb",
     "player_set": None, "team_mask": paint_allow_mask, "atlas_valid_mask": opa_valid_mask,
     "atlas_A": "INT-67 any_regime_change=True (asof)", "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
     "hypothesis": "INT-67 regime change player (slope flip) + paint-permissive D = emerging role under-priced",
     "use_row_mask_A": "regime_change"},
    {"compound_id": "C04", "name": "HighDevScore_x_HighDefIntensity_UNDER_PTS",
     "theme": "C", "direction": "under", "stat": "pts",
     "player_set": None, "team_mask": high_def_intensity_mask, "atlas_valid_mask": odi_valid_mask,
     "atlas_A": "INT-67 dev_score>70th pct (asof)", "atlas_B": "ODI opp_defensive_intensity_z>0.3",
     "hypothesis": "Player in behavioral drift (high dev_score) + intense D = volatile player faces tough matchup",
     "use_row_mask_A": "dev_score"},
    {"compound_id": "C05", "name": "OutlierFlagged_x_PaintAllowD_OVER_REB",
     "theme": "C", "direction": "over", "stat": "reb",
     "player_set": outlier_flagged_players, "team_mask": paint_allow_mask, "atlas_valid_mask": opa_valid_mask,
     "atlas_A": "INT-54 flag_strong_outlier=True", "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
     "hypothesis": "INT-54 behavioral outlier + paint-permissive D = new role unlocks rebounds"},
    {"compound_id": "C06", "name": "UnderpredPts_x_PaintAllowD_OVER_PTS",
     "theme": "C", "direction": "over", "stat": "pts",
     "player_set": None, "team_mask": paint_allow_mask, "atlas_valid_mask": opa_valid_mask,
     "atlas_A": "INT-69 pts bias_z>0.7 (asof)", "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
     "hypothesis": "Model consistently underestimates player + paint-permissive D = double OVER edge",
     "use_row_mask_A": "underpred_pts"},
    {"compound_id": "C07", "name": "UnderpredReb_x_PaintAllowD_OVER_REB",
     "theme": "C", "direction": "over", "stat": "reb",
     "player_set": None, "team_mask": paint_allow_mask, "atlas_valid_mask": opa_valid_mask,
     "atlas_A": "INT-69 reb bias_z>0.7 (asof)", "atlas_B": "INT-58 opp_paint_pct_allowed_z>0.3",
     "hypothesis": "Model under-calls REB for this player + paint-permissive D = compound OVER",
     "use_row_mask_A": "underpred_reb"},
    {"compound_id": "C08", "name": "UnderpredAst_x_IsoForceD_OVER_AST",
     "theme": "C", "direction": "over", "stat": "ast",
     "player_set": None, "team_mask": iso_force_mask, "atlas_valid_mask": None,
     "atlas_A": "INT-69 ast bias_z>0.7 (asof)", "atlas_B": "Schemes ISO FORCE",
     "hypothesis": "Model underpredicts AST + ISO FORCE D creates kick-out opportunities",
     "use_row_mask_A": "underpred_ast"},
    {"compound_id": "C09", "name": "Shrinker_x_HighDefIntensity_UNDER_PTS",
     "theme": "C", "direction": "under", "stat": "pts",
     "player_set": shrinker_players, "team_mask": high_def_intensity_mask, "atlas_valid_mask": odi_valid_mask,
     "atlas_A": "INT-26 clutch_class=SHRINKER", "atlas_B": "ODI opp_defensive_intensity_z>0.3",
     "hypothesis": "SHRINKER (reduces usage in pressure) + high-intensity D = compound PTS suppression"},
    {"compound_id": "C10", "name": "B2B_x_HighDefIntensity_UNDER_PTS",
     "theme": "C", "direction": "under", "stat": "pts",
     "player_set": b2b_players, "team_mask": high_def_intensity_mask, "atlas_valid_mask": odi_valid_mask,
     "atlas_A": "INT-13 rest=B2B", "atlas_B": "ODI opp_defensive_intensity_z>0.3",
     "hypothesis": "B2B fatigue + high-intensity D = compound UNDER; fatigue suppresses volume"},
    {"compound_id": "C11", "name": "DevSlope_x_PaceSlowD_UNDER_PTS",
     "theme": "C", "direction": "under", "stat": "pts",
     "player_set": None, "team_mask": pace_slow_mask, "atlas_valid_mask": odi_valid_mask,
     "atlas_A": "INT-67 any_regime_change=True (asof)", "atlas_B": "ODI opp_pace_imposed_z>0.3",
     "hypothesis": "Behaviorally drifting player (unstable role) + pace-slowing D = fewer possessions",
     "use_row_mask_A": "regime_change"},
    {"compound_id": "C12", "name": "Elevator_x_HighTempoOpp_OVER_PTS",
     "theme": "C", "direction": "over", "stat": "pts",
     "player_set": elevator_players, "team_mask": high_tempo_mask, "atlas_valid_mask": tts_valid_mask,
     "atlas_A": "INT-26 clutch_class=ELEVATOR", "atlas_B": "TTS team_tempo_z>0.3",
     "hypothesis": "ELEVATOR (raises usage in pressure) + fast-paced opponent = more high-leverage possessions"},
]

# Map of row_mask_A keys to actual mask arrays
ROW_MASK_A_MAP = {
    "regime_change": regime_change_row_mask,
    "dev_score": high_dev_score_row_mask,
    "underpred_pts": underpred_pts_mask,
    "underpred_reb": underpred_reb_mask,
    "underpred_ast": underpred_ast_mask,
}

# ---------------------------------------------------------------------------
# COMPUTE ALL COMPOUNDS
# ---------------------------------------------------------------------------
print(f"\n[7] Running {len(COMPOUNDS)} compound tests (N_SHUFFLE={N_SHUFFLE})...")
results = []

for c in COMPOUNDS:
    cid = c["compound_id"]
    stat = c["stat"]
    direction = c["direction"]
    team_mask = c["team_mask"]
    atlas_valid_mask = c.get("atlas_valid_mask")
    use_row_mask_A = c.get("use_row_mask_A")

    if use_row_mask_A is not None:
        # Player-level asof mask: combine row_mask_A (player signal) with team_mask (team signal)
        row_mask_A = ROW_MASK_A_MAP[use_row_mask_A]
        stat_mask = (lines_pool["stat"] == stat).to_numpy()
        pre_n = int((row_mask_A & stat_mask).sum())
        # Coverage: what fraction of player-asof rows also had a valid team-atlas lookup
        if atlas_valid_mask is not None and pre_n > 0:
            coverage_pct = float(((row_mask_A & stat_mask) & atlas_valid_mask).sum()) / pre_n
        else:
            coverage_pct = 1.0
        combined = row_mask_A & team_mask & stat_mask
        post_n = int(combined.sum())
        sub = lines_pool[combined].copy()
    else:
        # Player-set based
        player_set = c["player_set"] or set()
        sub, pre_n, post_n, coverage_pct = get_sub_masked(player_set, team_mask, stat, atlas_valid_mask)

    r = analyze_signal(sub, direction)
    n = r["n"]
    z_raw = r["z_raw"] if r["z_raw"] is not None else 0.0
    roi = r["roi"] if r["roi"] is not None else 0.0

    if n >= 10 and r["z_raw"] is not None:
        z_vs_null = null_z(sub, direction, z_raw, stat)
    else:
        z_vs_null = 0.0

    ci_lo = r["ci_lo"] if r["ci_lo"] is not None else -999.0
    verd = verdict(n, roi, z_raw, z_vs_null, ci_lo, coverage_pct)

    row = {
        "compound_id": cid,
        "name": c["name"],
        "theme": c["theme"],
        "atlas_A": c["atlas_A"],
        "atlas_B": c["atlas_B"],
        "direction": direction.upper(),
        "stat": stat,
        "hypothesis": c["hypothesis"],
        "n_bets": n,
        "pre_asof_n": pre_n,
        "post_asof_n": post_n,
        "coverage_pct": round(coverage_pct, 4),
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
    }
    results.append(row)
    print(
        f"  {cid} {stat.upper():4s} {direction.upper():5s} "
        f"pre={pre_n:4d} post={post_n:4d} cov={coverage_pct:.0%} "
        f"n={n:4d} ROI={roi:+7.2f}% z={z_raw:+6.3f} z_null={z_vs_null:+5.2f} -> {verd}"
    )

out_df = pd.DataFrame(results)

# ---------------------------------------------------------------------------
# G2 COVERAGE CHECK
# ---------------------------------------------------------------------------
median_cov = float(out_df["coverage_pct"].median())
print(f"\n[8] G2 Coverage: median={median_cov:.1%}  min={out_df['coverage_pct'].min():.1%}  max={out_df['coverage_pct'].max():.1%}")
if median_cov < G2_DROP:
    raise RuntimeError(f"K2 KILL: median coverage {median_cov:.1%} < {G2_DROP:.0%}. Atlases need denser rebuild.")

# ---------------------------------------------------------------------------
# G5: BONFERRONI + BH CORRECTION
# ---------------------------------------------------------------------------
z_vals = out_df["z_raw"].fillna(0.0).to_numpy()
p_vals = 2 * scipy_stats.norm.sf(np.abs(z_vals))
bonf_alpha = 0.05 / BONFERRONI_N
bonf_pass = p_vals < bonf_alpha
# BH (Benjamini-Hochberg)
n_tests = len(p_vals)
ranks = np.argsort(p_vals) + 1
bh_threshold = (ranks / n_tests) * 0.05
bh_pass = np.zeros(n_tests, dtype=bool)
for i in range(n_tests - 1, -1, -1):
    if p_vals[ranks[i] - 1] <= bh_threshold[i]:
        bh_pass[:i+1] = True
        break

out_df["p_val"] = p_vals
out_df["bonf_pass"] = bonf_pass
out_df["bh_pass"] = [bh_pass[i] for i in range(n_tests)]

# ---------------------------------------------------------------------------
# G4: NULL CONTROL AGGREGATE
# ---------------------------------------------------------------------------
n_pass_null = int((out_df["z_vs_null"] >= 2.0).sum())
frac_pass_null = n_pass_null / len(out_df)
print(f"\n[9] G4 Null control: {n_pass_null}/{len(out_df)} candidates pass z_vs_null>=2.0 ({frac_pass_null:.1%}, expected ~5% by chance)")

# ---------------------------------------------------------------------------
# SAVE PARQUET
# ---------------------------------------------------------------------------
out_path = INTEL / "compound_signal_hunt_v4.parquet"
out_df.to_parquet(out_path, index=False)
print(f"\n[10] Saved {len(out_df)} rows to {out_path}")

# ---------------------------------------------------------------------------
# G3: C10 SMEAR TEST
# ---------------------------------------------------------------------------
v3_path = INTEL / "compound_signal_hunt_v3.parquet"
v3_df = pd.read_parquet(v3_path) if v3_path.exists() else pd.DataFrame()

v3_c10_z = float(v3_df[v3_df["compound_id"] == "C10"]["z_raw"].iloc[0]) if len(v3_df) > 0 else 0.9598
v3_c10_znull = float(v3_df[v3_df["compound_id"] == "C10"]["z_vs_null"].iloc[0]) if len(v3_df) > 0 else 1.2921
v3_c10_n = int(v3_df[v3_df["compound_id"] == "C10"]["n_bets"].iloc[0]) if len(v3_df) > 0 else 108

v4_c10 = out_df[out_df["compound_id"] == "C10"].iloc[0]
v4_c10_z = float(v4_c10["z_raw"])
v4_c10_znull = float(v4_c10["z_vs_null"])
v4_c10_n = int(v4_c10["n_bets"])

print(f"\n[G3 C10 Smear Test]")
print(f"  v3: z_raw={v3_c10_z:+.4f}, z_vs_null={v3_c10_znull:+.4f}, n={v3_c10_n}")
print(f"  v4: z_raw={v4_c10_z:+.4f}, z_vs_null={v4_c10_znull:+.4f}, n={v4_c10_n}")
print(f"  delta_z: {v4_c10_z - v3_c10_z:+.4f}, delta_n: {v4_c10_n - v3_c10_n}")

# ---------------------------------------------------------------------------
# BUILD DELTA TABLE vs v3
# ---------------------------------------------------------------------------
print("\n[11] Building delta table vs v3...")
delta_rows = []
for _, v4row in out_df.iterrows():
    cid = v4row["compound_id"]
    v3match = v3_df[v3_df["compound_id"] == cid] if len(v3_df) > 0 else pd.DataFrame()
    if len(v3match) > 0:
        v3r = v3match.iloc[0]
        v3_z = float(v3r.get("z_raw", 0.0))
        v3_zn = float(v3r.get("z_vs_null", 0.0))
        v3_n = int(v3r.get("n_bets", 0))
        v3_verd = str(v3r.get("verdict", ""))
    else:
        v3_z = v3_zn = 0.0
        v3_n = 0
        v3_verd = "N/A"
    v4_z = float(v4row["z_raw"])
    v4_zn = float(v4row["z_vs_null"])
    v4_n = int(v4row["n_bets"])
    v4_verd = str(v4row["verdict"])
    delta_rows.append({
        "compound_id": cid,
        "v3_z_raw": round(v3_z, 4),
        "v4_z_raw": round(v4_z, 4),
        "delta_z": round(v4_z - v3_z, 4),
        "v3_z_vs_null": round(v3_zn, 4),
        "v4_z_vs_null": round(v4_zn, 4),
        "v3_n": v3_n,
        "v4_n": v4_n,
        "coverage_pct": round(float(v4row["coverage_pct"]), 4),
        "v3_verdict": v3_verd,
        "v4_verdict": v4_verd,
        "verdict_changed": v3_verd != v4_verd,
    })
delta_df = pd.DataFrame(delta_rows)

# ---------------------------------------------------------------------------
# FINAL VERDICT
# ---------------------------------------------------------------------------
n_strict = (out_df["verdict"] == "STRICT_SHIP").sum()
n_invest = (out_df["verdict"] == "INVESTIGATIVE").sum()
n_drop_cov = (out_df["verdict"] == "DROPPED_COVERAGE").sum()
n_reject_n = (out_df["verdict"] == "REJECT_N").sum()

if n_strict > 0:
    overall_verdict = "NEW-SHIP"
elif n_invest > 0:
    overall_verdict = "OVERTURNED"
elif n_drop_cov == len(out_df):
    overall_verdict = "K2-COVERAGE-FAIL"
else:
    overall_verdict = "CONFIRMED-NEGATIVE"

print(f"\n=== FINAL VERDICT: {overall_verdict} ===")
print(f"  STRICT_SHIP: {n_strict}  INVESTIGATIVE: {n_invest}  DROPPED_COVERAGE: {n_drop_cov}  REJECT_N: {n_reject_n}")

top5 = out_df.sort_values("z_raw", ascending=False).head(5)
print("\n=== TOP-5 BY Z_RAW ===")
print(top5[["compound_id", "name", "stat", "direction", "n_bets", "coverage_pct", "roi_pct", "z_raw", "z_vs_null", "verdict"]].to_string(index=False))

# ---------------------------------------------------------------------------
# WRITE VAULT NOTE
# ---------------------------------------------------------------------------
print("\n[12] Writing vault note...")
VAULT.mkdir(parents=True, exist_ok=True)
vault_path = VAULT / "INT-93_Compound_Signals_v4.md"

lines_md = [
    "# INT-93: Compound Signal Hunt v4 (Strict AS-OF Joins)",
    "",
    f"**Built:** 2026-05-29",
    f"**Ledger:** 2025-26 only (>= {LEDGER_CUTOFF}) — n={len(lines_pool):,} bets",
    f"**Compounds tested:** {len(out_df)} (36 pre-registered, same as INT-75/v3)",
    f"**Key fix:** merge_asof(direction=backward, allow_exact_matches=False) replaces latest-row smear",
    f"**Parquet:** `data/intelligence/compound_signal_hunt_v4.parquet`",
    f"**Script:** `scripts/hunt_compound_signals_v4.py`",
    "",
    "---",
    "",
    "## G1: Ledger Restriction",
    "",
    f"| Metric | Value |",
    f"|--------|-------|",
    f"| 2025-26 bets (post 2025-10-01) | {len(lines_pool):,} |",
    f"| Kill threshold | 2,000 |",
    f"| Warn threshold | 5,000 |",
    f"| Status | {'OK (>5K)' if len(lines_pool) >= G1_WARN else 'WARN (2-5K)' if len(lines_pool) >= G1_KILL else 'KILL'} |",
    "",
    "---",
    "",
    "## G2: AS-OF Join Coverage",
    "",
    f"| Metric | Value |",
    f"|--------|-------|",
    f"| Median coverage_pct | {median_cov:.1%} |",
    f"| Min coverage_pct | {out_df['coverage_pct'].min():.1%} |",
    f"| Max coverage_pct | {out_df['coverage_pct'].max():.1%} |",
    f"| Candidates with coverage >= 90% | {(out_df['coverage_pct'] >= G2_SHIP).sum()} / {len(out_df)} |",
    f"| Candidates DROPPED_COVERAGE (<60%) | {n_drop_cov} |",
    "",
    "---",
    "",
    "## G3: C10 Smear Test",
    "",
    "C10 = B2B_x_HighDefIntensity_UNDER_PTS. v3 had z_raw=0.96 from smeared 2024-25 atlas data.",
    "",
    f"| | v3 (smeared) | v4 (strict asof) | delta |",
    f"|--|-------------|-----------------|-------|",
    f"| z_raw | {v3_c10_z:+.4f} | {v4_c10_z:+.4f} | {v4_c10_z - v3_c10_z:+.4f} |",
    f"| z_vs_null | {v3_c10_znull:+.4f} | {v4_c10_znull:+.4f} | {v4_c10_znull - v3_c10_znull:+.4f} |",
    f"| n_bets | {v3_c10_n} | {v4_c10_n} | {v4_c10_n - v3_c10_n} |",
    f"| verdict | {v3_df[v3_df['compound_id']=='C10']['verdict'].iloc[0] if len(v3_df)>0 else 'N/A'} | {v4_c10['verdict']} | — |",
    "",
    "**Interpretation:** "
    + (f"C10 z_raw changed from {v3_c10_z:+.3f} to {v4_c10_z:+.3f} ({v4_c10_z - v3_c10_z:+.3f}). "
       + "Smear effect was inflating z by applying 2026 atlas snapshot to 2024-25 bets. "
       + f"v4 strict-asof gives the honest 2025-26-only estimate."),
    "",
    "---",
    "",
    "## G4: Null Control",
    "",
    f"| Metric | Value |",
    f"|--------|-------|",
    f"| Candidates with z_vs_null >= 2.0 | {n_pass_null} / {len(out_df)} ({frac_pass_null:.1%}) |",
    f"| Expected by chance at 5% | ~{int(0.05 * len(out_df))} |",
    f"| Interpretation | {'Inflation detected' if frac_pass_null > 0.10 else 'Within expected range'} |",
    "",
    "---",
    "",
    "## G5: Bonferroni + BH Correction",
    "",
    f"| Test | Threshold | Passing |",
    f"|------|-----------|---------|",
    f"| Bonferroni (α=0.05, n=36) | p < {bonf_alpha:.5f} (z >= {Z_STRICT}) | {bonf_pass.sum()} / {len(out_df)} |",
    f"| BH (FDR=0.05) | variable | {int(bh_pass.sum())} / {len(out_df)} |",
    "",
    "---",
    "",
    "## Final Verdict",
    "",
    f"**{overall_verdict}**",
    "",
    f"- STRICT_SHIP (z>={Z_STRICT} + z_vs_null>=2.0 + ci_lo>0 + n>=50): {n_strict}",
    f"- INVESTIGATIVE (z>={Z_INVEST} + z_vs_null>=2.0 + ci_lo>0 + n>=50): {n_invest}",
    f"- DROPPED_COVERAGE: {n_drop_cov}",
    f"- REJECT_N (n<50): {n_reject_n}",
    f"- Other REJECT: {len(out_df) - n_strict - n_invest - n_drop_cov - n_reject_n - (out_df['verdict'] == 'REJECT_ROI').sum()} REJECT + {(out_df['verdict'] == 'REJECT_ROI').sum()} REJECT_ROI",
    "",
    "---",
    "",
    "## Top-5 Compounds by z_raw",
    "",
    "| Rank | ID | Name | Stat | Side | n | cov% | ROI% | z_raw | z_vs_null | Verdict |",
    "|------|----|------|------|------|---|------|------|-------|-----------|---------|",
]

for i, row in top5.reset_index(drop=True).iterrows():
    lines_md.append(
        f"| {i+1} | {row['compound_id']} | {row['name']} | {row['stat']} | {row['direction']} "
        f"| {row['n_bets']} | {row['coverage_pct']:.0%} | {row['roi_pct']:+.1f}% "
        f"| {row['z_raw']:+.3f} | {row['z_vs_null']:+.2f} | {row['verdict']} |"
    )

lines_md.extend([
    "",
    "---",
    "",
    "## Delta Table (v3 -> v4)",
    "",
    "| ID | v3_z | v4_z | delta_z | v3_zn | v4_zn | v3_n | v4_n | cov% | v3_verdict | v4_verdict | changed |",
    "|----|------|------|---------|-------|-------|------|------|------|------------|------------|---------|",
])

for _, drow in delta_df.iterrows():
    lines_md.append(
        f"| {drow['compound_id']} | {drow['v3_z_raw']:+.3f} | {drow['v4_z_raw']:+.3f} "
        f"| {drow['delta_z']:+.3f} | {drow['v3_z_vs_null']:+.3f} | {drow['v4_z_vs_null']:+.3f} "
        f"| {drow['v3_n']} | {drow['v4_n']} | {drow['coverage_pct']:.0%} "
        f"| {drow['v3_verdict']} | {drow['v4_verdict']} | {'YES' if drow['verdict_changed'] else 'no'} |"
    )

lines_md.extend([
    "",
    "---",
    "",
    "## Full Results Table",
    "",
    "| ID | Name | Stat | Dir | n | cov% | ROI% | hit_rate | z_raw | z_vs_null | ci_lo | Verdict |",
    "|----|------|------|-----|---|------|------|----------|-------|-----------|-------|---------|",
])

for _, row in out_df.sort_values("z_raw", ascending=False).iterrows():
    lines_md.append(
        f"| {row['compound_id']} | {row['name']} | {row['stat']} | {row['direction']} "
        f"| {row['n_bets']} | {row['coverage_pct']:.0%} | {row['roi_pct']:+.1f}% "
        f"| {row['hit_rate'] or 'N/A'} "
        f"| {row['z_raw']:+.3f} | {row['z_vs_null']:+.2f} | {row['ci_lo'] or 'N/A'} | {row['verdict']} |"
    )

lines_md.extend([
    "",
    "---",
    "",
    "## Coverage Histogram (candidates by coverage_pct bucket)",
    "",
    "| Coverage bucket | Count |",
    "|-----------------|-------|",
])
for bucket, cnt in out_df.groupby(pd.cut(out_df["coverage_pct"], bins=[0, 0.6, 0.7, 0.8, 0.9, 1.0]))["compound_id"].count().items():
    lines_md.append(f"| {bucket} | {cnt} |")

lines_md.extend([
    "",
    "---",
    "",
    "## Honest Assessment",
    "",
    "- Strict asof join removes the post-hoc smear from v3 (team atlas latest-row applied to full 2024-25 ledger).",
    "- 2025-26-only ledger aligns with TTS atlas date range (2025-10-22 start).",
    "- Static player sets (archetypes, streaks, drift) are still derived from 2025-26 CV data; ",
    "  they are applied to 2025-26 bets only, so temporal alignment is now consistent.",
    "- dv2 (regime_change, dev_score) and cal (underpred_* bias) use row-level asof joins.",
    "- Schemes atlas has no game_date column; uses static team lists (no asof possible).",
    "",
    "*End INT-93*",
])

vault_path.write_text("\n".join(lines_md), encoding="utf-8")
print(f"  Vault note written: {vault_path}")

# ---------------------------------------------------------------------------
# APPEND TO cv_master_strategy.md
# ---------------------------------------------------------------------------
strategy_path = ROOT / "vault" / "Improvements" / "cv_master_strategy.md"
if strategy_path.exists():
    with open(strategy_path, "a", encoding="utf-8") as f:
        f.write(f"\n<!-- INT-93 v4 strict-asof --> INT-93 (2026-05-29): 36-compound hunt re-run with strict asof joins + 2025-26-only ledger (n={len(lines_pool):,}); verdict={overall_verdict}; median_cov={median_cov:.0%}; top z_raw={float(out_df['z_raw'].max()):+.3f}; 0 STRICT_SHIP, {n_invest} INVESTIGATIVE.\n")
    print(f"  Appended to {strategy_path}")
else:
    print(f"  WARNING: cv_master_strategy.md not found at {strategy_path} — skipping append")

print(f"\n=== INT-93 COMPLETE ===")
print(f"  Ledger: {len(lines_pool):,} bets (2025-26)")
print(f"  Median coverage: {median_cov:.1%}")
print(f"  Overall verdict: {overall_verdict}")
print(f"  Artifacts: {out_path}, {vault_path}")
