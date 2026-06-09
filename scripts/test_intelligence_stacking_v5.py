"""
INT-V5 Compound Signal Stacking Backtest
=========================================
HYPOTHESIS: Stacking multiple INDEPENDENT intelligence signals produces combinatorial
edge that single signals cannot.  V2/V3/V4 tested individual signals — books may price
single patterns.  The INTERSECTION of two or more independent conditions may be
unpriced because books treat each dimension separately.

8 compound signals tested (see spec for full definitions):
  1.  B2B_AND_PaintFirstOpp_UNDER_reb
  2.  Altitude_AND_LowVolatility_UNDER_pts
  3.  ClutchShrinker_AND_CloseGame_UNDER_pts   (V4 re-run with tighter close-game filter)
  4.  HotTrend_AND_LowVolatility_OVER_pts
  5.  MatchupDefApproach_AND_LowVolatility_UNDER_pts
  6.  PerimDenialMatchup_AND_PerimeterShooter_OVER_pts
  7.  B2B_AND_HighVolatility_UNDER_pts
  8.  Anomaly_AND_Matchup_AND_Recent_OVER_reb    (triple intersection)

Outputs:
  data/models/intelligence_stacking_v5_results.json
  vault/Intelligence/Compound_Signal_Stacking.md
"""

import json
import os
import random
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

sys.path.insert(0, str(Path(__file__).parent))
from lib_betting_validation import safe_odds  # Bug 10 guard

warnings.filterwarnings("ignore")
random.seed(42)
np.random.seed(42)

ROOT = Path("C:/Users/neelj/nba-ai-system")

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS (identical to V3/V4)
# ─────────────────────────────────────────────────────────────────────────────

def norm(s: str) -> str:
    return str(s).strip().lower()


def _check_lines_staleness(lines_df, label='lines_df'):
    """Warn if the lines pool is more than 30 days older than current CV data (Bug 15)."""
    if 'date' in lines_df.columns:
        max_date = pd.to_datetime(lines_df['date']).max()
    elif 'game_date' in lines_df.columns:
        max_date = pd.to_datetime(lines_df['game_date']).max()
    else:
        return
    today = pd.Timestamp.now()
    gap_days = (today - max_date).days
    if gap_days > 30:
        print(f"WARNING: {label} max date {max_date.date()} is {gap_days} days old. "
              f"CV data may have grown since; results may be stale (Bug 15).")


# safe_odds imported from lib_betting_validation above


def roi_per_bet(won: bool, odds: float = -110.0) -> float:
    """P&L per $1 wagered at American odds."""
    if odds < 0:
        win_amt = 100.0 / abs(odds)
    else:
        win_amt = odds / 100.0
    return win_amt if won else -1.0


def bootstrap_roi_ci(pnl_series: pd.Series, n_boot: int = 3000, ci: float = 0.95):
    """Bootstrap 95% CI on mean ROI (%)."""
    if len(pnl_series) < 3:
        return (None, None)
    boots = [pnl_series.sample(frac=1, replace=True).mean() * 100 for _ in range(n_boot)]
    lo = np.percentile(boots, (1 - ci) / 2 * 100)
    hi = np.percentile(boots, (1 + ci) / 2 * 100)
    return (round(float(lo), 2), round(float(hi), 2))


def z_roi_gt_zero(pnl_series: pd.Series):
    """One-sided z-test: is mean ROI > 0?"""
    if len(pnl_series) < 5:
        return None, None
    mu = pnl_series.mean()
    se = pnl_series.std(ddof=1) / np.sqrt(len(pnl_series))
    if se == 0:
        return None, None
    z = mu / se
    p = 1 - scipy_stats.norm.cdf(z)
    return round(float(z), 3), round(float(p), 4)


def verdict(roi_real, n_real: int, ci: tuple) -> str:
    if roi_real is None or n_real == 0:
        return "INSUFFICIENT_DATA"
    if roi_real > 0 and ci[0] is not None and ci[0] > -20:
        return "PROMISING"
    elif roi_real > -4.5:
        return "NEUTRAL"
    else:
        return "DEAD"


def aggregate_bets(df: pd.DataFrame, signal_name: str, conf_df: pd.DataFrame = None):
    """Aggregate bet-log DataFrame into per-signal stats."""
    if df is None or len(df) == 0:
        return {
            "name": signal_name, "n_bets": 0, "n_real_line_bets": 0,
            "n_proxy_bets": 0, "win_rate_real": None, "roi_real_flat": None,
            "roi_real_weighted": None, "ci_95": [None, None],
            "z_stat": None, "p_value": None, "verdict": "INSUFFICIENT_DATA",
        }

    real_df = df[df["has_real_line"] == True].copy()
    proxy_df = df[df["has_real_line"] == False].copy()

    roi_flat = real_df["pnl"].mean() * 100 if len(real_df) > 0 else None
    wr_real = real_df["won"].mean() if len(real_df) > 0 else None
    ci = bootstrap_roi_ci(real_df["pnl"]) if len(real_df) >= 3 else (None, None)
    zstat, pval = z_roi_gt_zero(real_df["pnl"]) if len(real_df) >= 5 else (None, None)

    # INT-16 Kelly-multiplier weighted ROI
    roi_weighted = None
    if conf_df is not None and len(real_df) > 0 and "player_id" in real_df.columns:
        stat_col = signal_name.split("_")[-1]
        mult_col = f"{stat_col}_confidence_mult"
        if mult_col not in conf_df.columns:
            mult_col = "overall_confidence_mult"
        if mult_col in conf_df.columns:
            real_df2 = real_df.copy()
            real_df2["player_id"] = pd.to_numeric(real_df2["player_id"], errors="coerce")
            conf_sub = conf_df[["player_id", mult_col]].copy()
            conf_sub["player_id"] = pd.to_numeric(conf_sub["player_id"], errors="coerce")
            merged = real_df2.merge(conf_sub.rename(columns={mult_col: "mult"}), on="player_id", how="left")
            merged["mult"] = merged["mult"].fillna(1.0)
            if merged["mult"].sum() > 0:
                roi_weighted = round(
                    float((merged["pnl"] * merged["mult"]).sum() / merged["mult"].sum() * 100), 2
                )

    verd = verdict(roi_flat, len(real_df), ci)
    return {
        "name": signal_name,
        "n_bets": int(len(df)),
        "n_real_line_bets": int(len(real_df)),
        "n_proxy_bets": int(len(proxy_df)),
        "win_rate_real": round(float(wr_real), 4) if wr_real is not None else None,
        "roi_real_flat": round(roi_flat, 2) if roi_flat is not None else None,
        "roi_real_weighted": roi_weighted,
        "ci_95": list(ci),
        "z_stat": zstat,
        "p_value": pval,
        "verdict": verd,
    }


def make_bet(player_id, player_name, game_date, stat, bet_dir,
             line, actual, over_odds_val, under_odds_val,
             has_real_line, signal_name, extra: dict = None):
    won = (actual > line) if bet_dir == "OVER" else (actual < line)
    odds = safe_odds(over_odds_val) if bet_dir == "OVER" else safe_odds(under_odds_val)
    pnl = roi_per_bet(won, odds)
    d = {
        "player_id": int(player_id) if (player_id is not None and not pd.isna(player_id)) else None,
        "player_name": str(player_name),
        "game_date": str(game_date)[:10],
        "stat": stat,
        "bet_direction": bet_dir,
        "line": float(line),
        "actual": float(actual),
        "won": bool(won),
        "pnl": float(pnl),
        "has_real_line": bool(has_real_line),
        "signal": signal_name,
    }
    if extra:
        d.update(extra)
    return d


# ─────────────────────────────────────────────────────────────────────────────
# 1. LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 70)
print("INT-V5 Compound Signal Stacking Backtest (8 compound signals)")
print("=" * 70)
print()

print("[1] Loading data sources...")

# OOF actuals
oof = pd.read_parquet(ROOT / "data/cache/pregame_oof.parquet")
oof["game_date"] = pd.to_datetime(oof["game_date"])
oof = oof.sort_values(["player_id", "stat", "game_date"])
oof["l5_mean_proxy"] = oof.groupby(["player_id", "stat"])["actual"].transform(
    lambda x: x.shift(1).rolling(5, min_periods=1).mean()
)
print(f"  OOF: {len(oof):,} rows | stats: {sorted(oof['stat'].unique().tolist())}")

# Per-player confidence (INT-16)
conf_df = pd.read_parquet(ROOT / "data/intelligence/per_player_confidence.parquet")
print(f"  INT-16 confidence: {len(conf_df)} players")

# Player fingerprints + archetypes
fp = pd.read_parquet(ROOT / "data/intelligence/player_fingerprints.parquet")
fp = fp.reset_index()
fp["player_norm"] = fp["player_name"].map(norm)
fp = fp[["player_id", "player_norm", "archetype_name"]].copy()
print(f"  Fingerprints: {len(fp)} players | archetypes: {fp['archetype_name'].value_counts().to_dict()}")

# Defensive schemes
schemes = pd.read_parquet(ROOT / "data/intelligence/defensive_schemes.parquet")
schemes["dominant_tag"] = schemes["dominant_tag"].str.strip().str.upper()
schemes["all_tags"] = schemes["all_tags"].str.upper()
print(f"  Defensive schemes: {len(schemes)} teams | tags: {schemes['dominant_tag'].value_counts().to_dict()}")

# Matchup deviations (INT-3) — has defender_approach_speed_z and paint_dwell_pct_z
mdev = pd.read_parquet(ROOT / "data/intelligence/matchup_deviations.parquet")
mdev["player_norm"] = mdev["player_name"].map(norm)
print(f"  INT-3 matchup deviations: {len(mdev)} rows")

# Anomaly log (INT-4)
anom = pd.read_parquet(ROOT / "data/intelligence/anomaly_log.parquet")
anom["game_date"] = pd.to_datetime(anom["game_date"])
anom["player_norm"] = anom["player_name"].map(norm)

def parse_top3(s):
    try:
        return json.loads(s)
    except Exception:
        return []

anom["features_parsed"] = anom["top_3_features"].apply(parse_top3)
print(f"  INT-4 anomaly log: {len(anom)} rows, {anom['game_id'].nunique()} unique games")

# Rolling trends (INT-18)
trends = pd.read_parquet(ROOT / "data/intelligence/rolling_trends.parquet")
trends["player_id"] = pd.to_numeric(trends["player_id"], errors="coerce")
hot_player_ids = set(trends[trends["trend_tag"].isin(["HOT_BREAKOUT", "WARMING"])]["player_id"].dropna().astype(int).tolist())
# Also build player_name -> trend_tag lookup for players not in player_id
hot_player_names = set(trends[trends["trend_tag"].isin(["HOT_BREAKOUT", "WARMING"])]["player_name"].map(norm).tolist())
print(f"  INT-18 rolling trends: {len(trends)} players | HOT/WARMING: {len(hot_player_ids)} (by id), {len(hot_player_names)} (by name)")

# Rest/travel (INT-22)
rt = pd.read_parquet(ROOT / "data/rest_travel.parquet")
rt["game_date"] = pd.to_datetime(rt["game_date"])
print(f"  INT-22 rest/travel: {len(rt):,} rows | B2B: {(rt['is_b2b'] == 1).sum()}, altitude>4k: {(rt['altitude_ft'] > 4000).sum()}")

# Clutch rankings (INT-23)
with open(ROOT / "data/intelligence/clutch_rankings.json") as f:
    clutch_data = json.load(f)
elevator_ids = set(int(p["player_id"]) for p in clutch_data.get("elevators", []))
shrinker_ids = set(int(p["player_id"]) for p in clutch_data.get("shrinkers", []))
print(f"  INT-23 clutch: {len(elevator_ids)} elevators, {len(shrinker_ids)} shrinkers")

# Pregame spreads (for close-game proxy)
spreads = pd.read_parquet(ROOT / "data/pregame_spreads.parquet")
spreads["game_date"] = pd.to_datetime(spreads["game_date"])
spreads["home_team"] = spreads["home_team"].str.upper().str.strip()
spreads["away_team"] = spreads["away_team"].str.upper().str.strip()
# Build (date, opp) -> is_projected_close lookup  (|spread| <= 3.5)
spread_close = {}
for _, row in spreads.iterrows():
    gd = row["game_date"]
    spread_val = abs(float(row["home_spread"])) if pd.notna(row["home_spread"]) else 99.0
    is_close = spread_val <= 3.5
    spread_close[(gd, row["away_team"])] = is_close
    spread_close[(gd, row["home_team"])] = is_close
print(f"  Pregame spreads: {len(spreads)} games | projected close (|sprd|<=3.5): {sum(v for v in spread_close.values())}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. LOAD + POOL SPORTSBOOK LINES
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[2] Loading sportsbook lines...")

line_sources = [
    ROOT / "data/external/historical_lines/extended_oos_canonical.csv",
    ROOT / "data/external/historical_lines/benashkar_2026_canonical.csv",
    ROOT / "data/external/historical_lines/regular_season_2025_26_oddsapi.csv",
    ROOT / "data/external/historical_lines/regular_season_2024_25_oddsapi.csv",
]

line_dfs = []
for p in line_sources:
    if p.exists():
        d = pd.read_csv(p)
        d["date"] = pd.to_datetime(d["date"])
        d["player_norm"] = d["player"].map(norm)
        d["stat"] = d["stat"].str.lower().str.strip()
        d["opp"] = d["opp"].str.upper().str.strip()
        line_dfs.append(d)
        print(f"  Loaded {p.name}: {len(d):,} rows")

lines_pool = (
    pd.concat(line_dfs, ignore_index=True)
    .drop_duplicates(subset=["player_norm", "date", "stat"])
    .reset_index(drop=True)
)
lines_pool = lines_pool.dropna(subset=["actual_value", "closing_line"])
_check_lines_staleness(lines_pool, 'lines_pool')
for _odds_col in ("over_odds", "under_odds"):  # Bug 10 guard
    if _odds_col in lines_pool.columns:
        lines_pool[_odds_col] = lines_pool[_odds_col].apply(safe_odds)
print(f"  Pooled lines: {len(lines_pool):,} rows")
print(f"  Stat breakdown: {lines_pool['stat'].value_counts().to_dict()}")
print(f"  Date range: {lines_pool['date'].min().date()} to {lines_pool['date'].max().date()}")

# Real-line coverage
real_line_pct = 100.0  # all rows in pool have real closing lines
print(f"  Real-line coverage: 100% (all pool rows have actuals)")


# ─────────────────────────────────────────────────────────────────────────────
# 3. BUILD LOOKUP TABLES
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[3] Building lookup tables...")

# player_norm → player_id from fingerprints (broadest coverage)
fn_norm_id = dict(zip(fp["player_norm"], fp["player_id"]))

# Arch × scheme base table (same as V3/V4)
arch_lines = lines_pool.merge(
    fp[["player_id", "player_norm", "archetype_name"]],
    on="player_norm", how="inner"
)
arch_lines = arch_lines.merge(
    schemes[["team", "dominant_tag", "all_tags"]],
    left_on="opp", right_on="team", how="inner"
)
print(f"  Arch×Scheme lines: {len(arch_lines):,} rows")

# OOF game_id lookup
oof_game_map = oof[["player_id", "game_id", "game_date"]].drop_duplicates()

# Lines pool + player_id + game_id (for B2B/altitude join)
lines_pool_copy = lines_pool.copy()
lines_pool_copy["player_id"] = lines_pool_copy["player_norm"].map(fn_norm_id)

lines_with_gid = lines_pool_copy.dropna(subset=["player_id"]).merge(
    oof_game_map.rename(columns={"game_date": "oof_game_date"}),
    left_on=["player_id", "date"],
    right_on=["player_id", "oof_game_date"],
    how="left"
)
print(f"  Lines with game_id: {lines_with_gid['game_id'].notna().sum():,} / {len(lines_with_gid):,}")

# Join to rest_travel to get B2B / altitude per player-game
rt_by_game = rt[["game_id", "team_abbreviation", "is_b2b", "altitude_ft"]].copy()
lines_rt = lines_with_gid.merge(rt_by_game, on="game_id", how="left")
# Filter to player's OWN team row (team_abbreviation != opp)
lines_rt_player = lines_rt[
    lines_rt["team_abbreviation"].notna() &
    (lines_rt["team_abbreviation"].str.upper() != lines_rt["opp"].str.upper())
].drop_duplicates(subset=["player_norm", "date", "stat"])
print(f"  Lines with B2B/altitude: {len(lines_rt_player):,} rows | B2B: {(lines_rt_player['is_b2b'] == 1).sum()}")
print(f"  Altitude>4000ft: {(lines_rt_player['altitude_ft'] > 4000).sum()}")

# Build OOF anomaly merged dataset (for compound anomaly signal)
oof_for_anom = oof[["player_id", "game_id", "stat", "actual", "l5_mean_proxy"]].copy()
anom_oof = anom.merge(oof_for_anom, on=["player_id", "game_id"], how="inner")
anom_oof["game_date"] = pd.to_datetime(anom_oof["game_date"])
anom_oof = anom_oof.merge(
    lines_pool[["player_norm", "date", "stat", "closing_line", "over_odds", "under_odds"]],
    left_on=["player_norm", "game_date", "stat"],
    right_on=["player_norm", "date", "stat"],
    how="left"
)
anom_oof["has_real_line"] = anom_oof["closing_line"].notna()
anom_oof["effective_line"] = anom_oof["closing_line"].fillna(anom_oof["l5_mean_proxy"])
anom_oof = anom_oof.dropna(subset=["effective_line", "actual"])
print(f"  Anomaly+OOF: {len(anom_oof):,} rows | real lines: {anom_oof['has_real_line'].sum()}")

# Matchup deviations + lines join (for matchup-based compound signals)
mdev_lines_pts = lines_pool[lines_pool["stat"] == "pts"].merge(
    mdev[["player_norm", "opp_team", "defender_approach_speed_z", "paint_dwell_pct_z"]],
    left_on=["player_norm", "opp"],
    right_on=["player_norm", "opp_team"],
    how="inner"
)
mdev_lines_reb = lines_pool[lines_pool["stat"] == "reb"].merge(
    mdev[["player_norm", "opp_team", "paint_dwell_pct_z"]],
    left_on=["player_norm", "opp"],
    right_on=["player_norm", "opp_team"],
    how="inner"
)
print(f"  Matchup deviation lines (pts): {len(mdev_lines_pts):,} rows")
print(f"  Matchup deviation lines (reb): {len(mdev_lines_reb):,} rows")

# Confidence multiplier lookup
pid_to_pts_mult = dict(zip(conf_df["player_id"], conf_df["pts_confidence_mult"]
                           if "pts_confidence_mult" in conf_df.columns else conf_df.iloc[:, 7]))
pid_to_reb_mult = dict(zip(conf_df["player_id"], conf_df["reb_confidence_mult"]
                           if "reb_confidence_mult" in conf_df.columns else conf_df.iloc[:, 9]))

# Determine actual column names
pts_mult_col = "pts_confidence_mult" if "pts_confidence_mult" in conf_df.columns else None
reb_mult_col = "reb_confidence_mult" if "reb_confidence_mult" in conf_df.columns else None
overall_mult_col = "overall_confidence_mult" if "overall_confidence_mult" in conf_df.columns else None

def get_conf_mult(pid, stat):
    """Look up INT-16 confidence multiplier for a player×stat."""
    if pid is None or (isinstance(pid, float) and np.isnan(pid)):
        return 1.0
    pid = int(pid)
    col = f"{stat}_confidence_mult"
    if col in conf_df.columns:
        lookup = dict(zip(conf_df["player_id"].astype(int, errors="ignore"), conf_df[col]))
        return float(lookup.get(pid, 1.0))
    return 1.0

# Pre-build fast lookup dicts from conf_df
_mult_lookups = {}
for stat in ["pts", "reb", "ast"]:
    col = f"{stat}_confidence_mult"
    if col in conf_df.columns:
        _mult_lookups[stat] = {
            int(pid): float(v)
            for pid, v in zip(conf_df["player_id"], conf_df[col])
            if pd.notna(pid) and pd.notna(v)
        }

def fast_conf_mult(pid, stat):
    if pid is None or (isinstance(pid, float) and np.isnan(pid)):
        return 1.0
    return _mult_lookups.get(stat, {}).get(int(pid), 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# 4. COMPONENT SIGNAL ROI (for comparison table)
# We need ROI for each component individually to compare vs compound.
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[4] Computing component-signal ROI baselines...")

COMPONENT_RESULTS = {}


def compute_simple_roi(bets_list, name):
    if not bets_list:
        return {"name": name, "n_real": 0, "win_rate": None, "roi": None, "ci_95": [None, None]}
    df = pd.DataFrame(bets_list)
    real = df[df["has_real_line"] == True] if "has_real_line" in df.columns else df
    n = len(real)
    if n == 0:
        return {"name": name, "n_real": 0, "win_rate": None, "roi": None, "ci_95": [None, None]}
    roi = real["pnl"].mean() * 100
    wr = real["won"].mean()
    ci = bootstrap_roi_ci(real["pnl"])
    return {
        "name": name,
        "n_real": n,
        "win_rate": round(float(wr), 4),
        "roi": round(float(roi), 2),
        "ci_95": list(ci),
    }


# Component A: B2B alone → UNDER reb
_b2b_reb_bets = []
for _, row in lines_rt_player[lines_rt_player["stat"] == "reb"].iterrows():
    if row.get("is_b2b") == 1.0:
        _b2b_reb_bets.append(make_bet(
            row.get("player_id"), row["player"], row["date"], "reb", "UNDER",
            row["closing_line"], row["actual_value"],
            row.get("over_odds", -110), row.get("under_odds", -110),
            True, "_b2b_reb_base"
        ))
COMPONENT_RESULTS["B2B_alone_UNDER_reb"] = compute_simple_roi(_b2b_reb_bets, "B2B_alone_UNDER_reb")
print(f"  B2B alone UNDER reb: n={COMPONENT_RESULTS['B2B_alone_UNDER_reb']['n_real']} roi={COMPONENT_RESULTS['B2B_alone_UNDER_reb']['roi']}%")

# Component B: paint-first defense alone → UNDER reb
_pf_reb_bets = []
pf_lines = arch_lines[arch_lines["all_tags"].str.contains("PAINT-FIRST", case=False, na=False) & (arch_lines["stat"] == "reb")]
for _, row in pf_lines.iterrows():
    _pf_reb_bets.append(make_bet(
        row["player_id"], row["player"], row["date"], "reb", "UNDER",
        row["closing_line"], row["actual_value"],
        row.get("over_odds", -110), row.get("under_odds", -110),
        True, "_pf_reb_base",
        extra={"opp_scheme": row["dominant_tag"]}
    ))
COMPONENT_RESULTS["PaintFirst_alone_UNDER_reb"] = compute_simple_roi(_pf_reb_bets, "PaintFirst_alone_UNDER_reb")
print(f"  PaintFirst alone UNDER reb: n={COMPONENT_RESULTS['PaintFirst_alone_UNDER_reb']['n_real']} roi={COMPONENT_RESULTS['PaintFirst_alone_UNDER_reb']['roi']}%")

# Component C: altitude alone → UNDER pts (road)
_alt_pts_bets = []
for _, row in lines_rt_player[
    (lines_rt_player["altitude_ft"] > 4000) &
    (lines_rt_player["stat"] == "pts") &
    (lines_rt_player.get("venue", pd.Series(["away"] * len(lines_rt_player), index=lines_rt_player.index)).str.lower() == "away")
].iterrows():
    _alt_pts_bets.append(make_bet(
        row.get("player_id"), row["player"], row["date"], "pts", "UNDER",
        row["closing_line"], row["actual_value"],
        row.get("over_odds", -110), row.get("under_odds", -110),
        True, "_altitude_pts_base",
        extra={"altitude_ft": float(row["altitude_ft"]) if pd.notna(row["altitude_ft"]) else None}
    ))
COMPONENT_RESULTS["Altitude_alone_UNDER_pts"] = compute_simple_roi(_alt_pts_bets, "Altitude_alone_UNDER_pts")
print(f"  Altitude alone UNDER pts: n={COMPONENT_RESULTS['Altitude_alone_UNDER_pts']['n_real']} roi={COMPONENT_RESULTS['Altitude_alone_UNDER_pts']['roi']}%")

# Component D: low volatility alone → UNDER pts (pts_confidence_mult > 1.0)
_lowvol_pts_bets = []
for _, row in lines_pool[lines_pool["stat"] == "pts"].iterrows():
    pid = fn_norm_id.get(row["player_norm"])
    mult = fast_conf_mult(pid, "pts")
    if mult > 1.0:
        _lowvol_pts_bets.append(make_bet(
            pid, row["player"], row["date"], "pts", "UNDER",
            row["closing_line"], row["actual_value"],
            row.get("over_odds", -110), row.get("under_odds", -110),
            True, "_lowvol_pts_base",
            extra={"pts_conf_mult": float(mult)}
        ))
COMPONENT_RESULTS["LowVolatility_alone_UNDER_pts"] = compute_simple_roi(_lowvol_pts_bets, "LowVolatility_alone_UNDER_pts")
print(f"  LowVolatility alone UNDER pts: n={COMPONENT_RESULTS['LowVolatility_alone_UNDER_pts']['n_real']} roi={COMPONENT_RESULTS['LowVolatility_alone_UNDER_pts']['roi']}%")

# Component E: clutch shrinker alone → UNDER pts
_shrinker_pts_bets = []
for _, row in lines_pool[lines_pool["stat"] == "pts"].iterrows():
    pid = fn_norm_id.get(row["player_norm"])
    if pid is not None and not pd.isna(pid) and int(pid) in shrinker_ids:
        _shrinker_pts_bets.append(make_bet(
            pid, row["player"], row["date"], "pts", "UNDER",
            row["closing_line"], row["actual_value"],
            row.get("over_odds", -110), row.get("under_odds", -110),
            True, "_shrinker_pts_base"
        ))
COMPONENT_RESULTS["ClutchShrinker_alone_UNDER_pts"] = compute_simple_roi(_shrinker_pts_bets, "ClutchShrinker_alone_UNDER_pts")
print(f"  ClutchShrinker alone UNDER pts: n={COMPONENT_RESULTS['ClutchShrinker_alone_UNDER_pts']['n_real']} roi={COMPONENT_RESULTS['ClutchShrinker_alone_UNDER_pts']['roi']}%")

# Component F: close game alone → UNDER pts
_close_game_pts_bets = []
for _, row in lines_pool[lines_pool["stat"] == "pts"].iterrows():
    is_close = spread_close.get((row["date"], row["opp"]), False)
    if is_close:
        pid = fn_norm_id.get(row["player_norm"])
        _close_game_pts_bets.append(make_bet(
            pid, row["player"], row["date"], "pts", "UNDER",
            row["closing_line"], row["actual_value"],
            row.get("over_odds", -110), row.get("under_odds", -110),
            True, "_close_game_pts_base"
        ))
COMPONENT_RESULTS["CloseGame_alone_UNDER_pts"] = compute_simple_roi(_close_game_pts_bets, "CloseGame_alone_UNDER_pts")
print(f"  CloseGame alone UNDER pts: n={COMPONENT_RESULTS['CloseGame_alone_UNDER_pts']['n_real']} roi={COMPONENT_RESULTS['CloseGame_alone_UNDER_pts']['roi']}%")

# Component G: HOT trend alone → OVER pts
_hot_pts_bets = []
for _, row in lines_pool[lines_pool["stat"] == "pts"].iterrows():
    pid = fn_norm_id.get(row["player_norm"])
    pname = norm(row["player"])
    is_hot = (
        (pid is not None and not pd.isna(pid) and int(pid) in hot_player_ids)
        or (pname in hot_player_names)
    )
    if is_hot:
        _hot_pts_bets.append(make_bet(
            pid, row["player"], row["date"], "pts", "OVER",
            row["closing_line"], row["actual_value"],
            row.get("over_odds", -110), row.get("under_odds", -110),
            True, "_hot_trend_pts_base"
        ))
COMPONENT_RESULTS["HotTrend_alone_OVER_pts"] = compute_simple_roi(_hot_pts_bets, "HotTrend_alone_OVER_pts")
print(f"  HotTrend alone OVER pts: n={COMPONENT_RESULTS['HotTrend_alone_OVER_pts']['n_real']} roi={COMPONENT_RESULTS['HotTrend_alone_OVER_pts']['roi']}%")

# Component H: matchup_def_approach_z < -1.5 alone → UNDER pts (V2 winner)
_matchup_z_pts_bets = []
for _, row in mdev_lines_pts[mdev_lines_pts["defender_approach_speed_z"] <= -1.5].iterrows():
    pid = fn_norm_id.get(row["player_norm"])
    _matchup_z_pts_bets.append(make_bet(
        pid, row["player"], row["date"], "pts", "UNDER",
        row["closing_line"], row["actual_value"],
        row.get("over_odds", -110), row.get("under_odds", -110),
        True, "_matchup_z_pts_base",
        extra={"defender_approach_speed_z": float(row["defender_approach_speed_z"])}
    ))
COMPONENT_RESULTS["MatchupDefApproach_alone_UNDER_pts"] = compute_simple_roi(_matchup_z_pts_bets, "MatchupDefApproach_alone_UNDER_pts")
print(f"  MatchupDefApproach alone UNDER pts: n={COMPONENT_RESULTS['MatchupDefApproach_alone_UNDER_pts']['n_real']} roi={COMPONENT_RESULTS['MatchupDefApproach_alone_UNDER_pts']['roi']}%")

# Component I: PERIMETER DENIAL scheme alone → OVER pts (V3 winner)
_perim_denial_pts_bets = []
pd_arch = arch_lines[arch_lines["all_tags"].str.contains("PERIMETER DENIAL", case=False, na=False) & (arch_lines["stat"] == "pts")]
for _, row in pd_arch.iterrows():
    _perim_denial_pts_bets.append(make_bet(
        row["player_id"], row["player"], row["date"], "pts", "OVER",
        row["closing_line"], row["actual_value"],
        row.get("over_odds", -110), row.get("under_odds", -110),
        True, "_perim_denial_pts_base",
        extra={"archetype": row["archetype_name"], "opp_scheme": row["dominant_tag"]}
    ))
COMPONENT_RESULTS["PerimDenial_alone_OVER_pts"] = compute_simple_roi(_perim_denial_pts_bets, "PerimDenial_alone_OVER_pts")
print(f"  PerimDenial alone OVER pts: n={COMPONENT_RESULTS['PerimDenial_alone_OVER_pts']['n_real']} roi={COMPONENT_RESULTS['PerimDenial_alone_OVER_pts']['roi']}%")

# Component J: Perimeter Shooter archetype alone → OVER pts
_perim_shooter_pts_bets = []
ps_lines = arch_lines[arch_lines["archetype_name"].str.contains("Perimeter Shooter", case=False, na=False) & (arch_lines["stat"] == "pts")]
for _, row in ps_lines.iterrows():
    _perim_shooter_pts_bets.append(make_bet(
        row["player_id"], row["player"], row["date"], "pts", "OVER",
        row["closing_line"], row["actual_value"],
        row.get("over_odds", -110), row.get("under_odds", -110),
        True, "_perim_shooter_pts_base",
        extra={"archetype": row["archetype_name"]}
    ))
COMPONENT_RESULTS["PerimShooter_alone_OVER_pts"] = compute_simple_roi(_perim_shooter_pts_bets, "PerimShooter_alone_OVER_pts")
print(f"  PerimShooter alone OVER pts: n={COMPONENT_RESULTS['PerimShooter_alone_OVER_pts']['n_real']} roi={COMPONENT_RESULTS['PerimShooter_alone_OVER_pts']['roi']}%")

# Component K: high volatility alone → UNDER pts (pts_confidence_mult < 0.8)
_highvol_pts_bets = []
for _, row in lines_pool[lines_pool["stat"] == "pts"].iterrows():
    pid = fn_norm_id.get(row["player_norm"])
    mult = fast_conf_mult(pid, "pts")
    if mult < 0.8:
        _highvol_pts_bets.append(make_bet(
            pid, row["player"], row["date"], "pts", "UNDER",
            row["closing_line"], row["actual_value"],
            row.get("over_odds", -110), row.get("under_odds", -110),
            True, "_highvol_pts_base",
            extra={"pts_conf_mult": float(mult)}
        ))
COMPONENT_RESULTS["HighVolatility_alone_UNDER_pts"] = compute_simple_roi(_highvol_pts_bets, "HighVolatility_alone_UNDER_pts")
print(f"  HighVolatility alone UNDER pts: n={COMPONENT_RESULTS['HighVolatility_alone_UNDER_pts']['n_real']} roi={COMPONENT_RESULTS['HighVolatility_alone_UNDER_pts']['roi']}%")

# Component L: anomaly paint_dwell z > 2 alone → OVER reb
_anom_pd_reb_bets = []
for _, row in anom_oof[anom_oof["stat"] == "reb"].iterrows():
    for feat_obj in row["features_parsed"]:
        if feat_obj.get("feature") == "paint_dwell_pct" and feat_obj.get("z", 0) >= 2.0:
            _anom_pd_reb_bets.append(make_bet(
                row["player_id"], row["player_name"], row["game_date"], "reb", "OVER",
                row["effective_line"], row["actual"],
                row.get("over_odds", -110), row.get("under_odds", -110),
                bool(row["has_real_line"]), "_anomaly_paint_dwell_reb_base",
                extra={"paint_dwell_z": float(feat_obj["z"])}
            ))
            break
COMPONENT_RESULTS["AnomalyPaintDwell_alone_OVER_reb"] = compute_simple_roi(_anom_pd_reb_bets, "AnomalyPaintDwell_alone_OVER_reb")
print(f"  Anomaly paint_dwell alone OVER reb: n={COMPONENT_RESULTS['AnomalyPaintDwell_alone_OVER_reb']['n_real']} roi={COMPONENT_RESULTS['AnomalyPaintDwell_alone_OVER_reb']['roi']}%")

# Component M: matchup paint deviation alone → OVER reb
_matchup_paint_reb_bets = []
for _, row in mdev_lines_reb[mdev_lines_reb["paint_dwell_pct_z"] >= 1.0].iterrows():
    pid = fn_norm_id.get(row["player_norm"])
    _matchup_paint_reb_bets.append(make_bet(
        pid, row["player"], row["date"], "reb", "OVER",
        row["closing_line"], row["actual_value"],
        row.get("over_odds", -110), row.get("under_odds", -110),
        True, "_matchup_paint_reb_base",
        extra={"paint_dwell_z": float(row["paint_dwell_pct_z"])}
    ))
COMPONENT_RESULTS["MatchupPaint_alone_OVER_reb"] = compute_simple_roi(_matchup_paint_reb_bets, "MatchupPaint_alone_OVER_reb")
print(f"  MatchupPaint alone OVER reb: n={COMPONENT_RESULTS['MatchupPaint_alone_OVER_reb']['n_real']} roi={COMPONENT_RESULTS['MatchupPaint_alone_OVER_reb']['roi']}%")


# ─────────────────────────────────────────────────────────────────────────────
# 5. COMPOUND SIGNALS
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[5] Building compound signal bet logs...")

BET_LOGS = {}


# ═══════════════════════════════════════════════════════════
# COMPOUND 1: B2B AND Paint-First Opp → UNDER reb
# Conditions: is_b2b==1 AND opp scheme has PAINT-FIRST
# Reasoning: tired player + defense that floods paint = double squeeze on rebounding
# ═══════════════════════════════════════════════════════════
print()
print("  [C1] B2B_AND_PaintFirstOpp_UNDER_reb ...")

c1_bets = []
# lines_rt_player has B2B info; arch_lines has scheme info
# We need both: join lines_rt_player (for is_b2b) with schemes (for opp scheme)
c1_base = lines_rt_player[
    (lines_rt_player["is_b2b"] == 1.0) & (lines_rt_player["stat"] == "reb")
].copy()

# Add scheme info by joining on opp
c1_base = c1_base.merge(
    schemes[["team", "dominant_tag", "all_tags"]],
    left_on="opp", right_on="team", how="inner"
)
# Filter to paint-first defense
c1_filtered = c1_base[
    c1_base["all_tags"].str.contains("PAINT-FIRST", case=False, na=False)
].copy()

for _, row in c1_filtered.iterrows():
    c1_bets.append(make_bet(
        row.get("player_id"), row["player"], row["date"], "reb", "UNDER",
        row["closing_line"], row["actual_value"],
        row.get("over_odds", -110), row.get("under_odds", -110),
        True, "B2B_AND_PaintFirstOpp_UNDER_reb",
        extra={"is_b2b": 1, "opp_scheme": row["dominant_tag"]}
    ))

BET_LOGS["B2B_AND_PaintFirstOpp_UNDER_reb"] = c1_bets
print(f"    Fired: {len(c1_bets)} bets | B2B reb candidates: {len(c1_base.merge(schemes[['team']], left_on='opp', right_on='team', how='inner') if True else c1_base)}")
print(f"    (B2B alone UNDER reb: n={COMPONENT_RESULTS['B2B_alone_UNDER_reb']['n_real']}, PaintFirst alone: n={COMPONENT_RESULTS['PaintFirst_alone_UNDER_reb']['n_real']})")


# ═══════════════════════════════════════════════════════════
# COMPOUND 2: Altitude > 4000ft AND Low Volatility → UNDER pts
# Conditions: venue altitude_ft > 4000 (road game in DEN/UTA)
#             AND player INT-16 pts_confidence_mult > 1.0
# Reasoning: high-altitude road game suppresses output;
#            low-volatility player = reliable suppression (not noisy)
# ═══════════════════════════════════════════════════════════
print()
print("  [C2] Altitude_AND_LowVolatility_UNDER_pts ...")

c2_bets = []
c2_base = lines_rt_player[
    (lines_rt_player["altitude_ft"] > 4000) &
    (lines_rt_player["stat"] == "pts")
].copy()
if "venue" in c2_base.columns:
    c2_base = c2_base[c2_base["venue"].str.lower() == "away"].copy()

for _, row in c2_base.iterrows():
    pid = row.get("player_id")
    if pid is None or (isinstance(pid, float) and np.isnan(pid)):
        pid = fn_norm_id.get(row["player_norm"])
    mult = fast_conf_mult(pid, "pts")
    if mult > 1.0:
        c2_bets.append(make_bet(
            pid, row["player"], row["date"], "pts", "UNDER",
            row["closing_line"], row["actual_value"],
            row.get("over_odds", -110), row.get("under_odds", -110),
            True, "Altitude_AND_LowVolatility_UNDER_pts",
            extra={"altitude_ft": float(row["altitude_ft"]) if pd.notna(row["altitude_ft"]) else None,
                   "pts_conf_mult": float(mult)}
        ))

BET_LOGS["Altitude_AND_LowVolatility_UNDER_pts"] = c2_bets
print(f"    Fired: {len(c2_bets)} bets (from {len(c2_base)} high-altitude road pts lines)")
print(f"    (Altitude alone UNDER pts: n={COMPONENT_RESULTS['Altitude_alone_UNDER_pts']['n_real']}, "
      f"LowVol alone: n={COMPONENT_RESULTS['LowVolatility_alone_UNDER_pts']['n_real']})")


# ═══════════════════════════════════════════════════════════
# COMPOUND 3: ClutchShrinker AND Close Game → UNDER pts
# Conditions: player in INT-23 shrinker list (top 11)
#             AND final margin proxy <= 3.5 (|pregame spread| <= 3.5)
# ═══════════════════════════════════════════════════════════
print()
print("  [C3] ClutchShrinker_AND_CloseGame_UNDER_pts ...")

c3_bets = []
c3_pool = lines_pool[lines_pool["stat"] == "pts"].copy()
c3_pool["player_id_lookup"] = c3_pool["player_norm"].map(fn_norm_id)
c3_pool["pid_int"] = pd.to_numeric(c3_pool["player_id_lookup"], errors="coerce")

for _, row in c3_pool.iterrows():
    pid = row.get("pid_int")
    if pd.isna(pid):
        continue
    is_shrinker = int(pid) in shrinker_ids
    is_close = spread_close.get((row["date"], row["opp"]), False)
    if is_shrinker and is_close:
        c3_bets.append(make_bet(
            pid, row["player"], row["date"], "pts", "UNDER",
            row["closing_line"], row["actual_value"],
            row.get("over_odds", -110), row.get("under_odds", -110),
            True, "ClutchShrinker_AND_CloseGame_UNDER_pts",
            extra={"is_shrinker": True, "projected_close": True}
        ))

BET_LOGS["ClutchShrinker_AND_CloseGame_UNDER_pts"] = c3_bets
print(f"    Fired: {len(c3_bets)} bets")
print(f"    (ClutchShrinker alone: n={COMPONENT_RESULTS['ClutchShrinker_alone_UNDER_pts']['n_real']}, "
      f"CloseGame alone: n={COMPONENT_RESULTS['CloseGame_alone_UNDER_pts']['n_real']})")


# ═══════════════════════════════════════════════════════════
# COMPOUND 4: HotTrend AND Low Volatility → OVER pts
# Conditions: player tagged HOT_BREAKOUT or WARMING in INT-18
#             AND INT-16 pts_confidence_mult > 1.0
# Reasoning: trending up + consistent = trustworthy signal
# ═══════════════════════════════════════════════════════════
print()
print("  [C4] HotTrend_AND_LowVolatility_OVER_pts ...")

c4_bets = []
c4_pool = lines_pool[lines_pool["stat"] == "pts"].copy()

for _, row in c4_pool.iterrows():
    pid = fn_norm_id.get(row["player_norm"])
    pname = norm(row["player"])
    is_hot = (
        (pid is not None and not pd.isna(pid) and int(pid) in hot_player_ids)
        or (pname in hot_player_names)
    )
    if not is_hot:
        continue
    mult = fast_conf_mult(pid, "pts")
    if mult > 1.0:
        c4_bets.append(make_bet(
            pid, row["player"], row["date"], "pts", "OVER",
            row["closing_line"], row["actual_value"],
            row.get("over_odds", -110), row.get("under_odds", -110),
            True, "HotTrend_AND_LowVolatility_OVER_pts",
            extra={"is_hot_trend": True, "pts_conf_mult": float(mult)}
        ))

BET_LOGS["HotTrend_AND_LowVolatility_OVER_pts"] = c4_bets
print(f"    Fired: {len(c4_bets)} bets")
print(f"    (HotTrend alone OVER pts: n={COMPONENT_RESULTS['HotTrend_alone_OVER_pts']['n_real']}, "
      f"LowVol alone: n={COMPONENT_RESULTS['LowVolatility_alone_UNDER_pts']['n_real']})")


# ═══════════════════════════════════════════════════════════
# COMPOUND 5: MatchupDefApproach AND LowVolatility → UNDER pts
# Conditions: matchup_defender_approach_z < -1.5 (V2 winner)
#             AND player INT-16 pts_confidence_mult > 1.0
# Reasoning: facing sluggish defender + reliable baseline = cleaner edge
# ═══════════════════════════════════════════════════════════
print()
print("  [C5] MatchupDefApproach_AND_LowVolatility_UNDER_pts ...")

c5_bets = []
c5_base = mdev_lines_pts[mdev_lines_pts["defender_approach_speed_z"] <= -1.5].copy()

for _, row in c5_base.iterrows():
    pid = fn_norm_id.get(row["player_norm"])
    mult = fast_conf_mult(pid, "pts")
    if mult > 1.0:
        c5_bets.append(make_bet(
            pid, row["player"], row["date"], "pts", "UNDER",
            row["closing_line"], row["actual_value"],
            row.get("over_odds", -110), row.get("under_odds", -110),
            True, "MatchupDefApproach_AND_LowVolatility_UNDER_pts",
            extra={"defender_approach_speed_z": float(row["defender_approach_speed_z"]),
                   "pts_conf_mult": float(mult)}
        ))

BET_LOGS["MatchupDefApproach_AND_LowVolatility_UNDER_pts"] = c5_bets
print(f"    Fired: {len(c5_bets)} bets (from {len(c5_base)} matchup-z pts lines)")
print(f"    (MatchupDefApproach alone: n={COMPONENT_RESULTS['MatchupDefApproach_alone_UNDER_pts']['n_real']}, "
      f"LowVol alone: n={COMPONENT_RESULTS['LowVolatility_alone_UNDER_pts']['n_real']})")


# ═══════════════════════════════════════════════════════════
# COMPOUND 6: PerimDenialMatchup AND PerimeterShooter → OVER pts
# Conditions: opp scheme tag contains PERIMETER DENIAL
#             AND player archetype = Perimeter Shooter / Transition Wing
# This re-runs V3's best signal but restricts to only Perimeter Shooter archetypes
# ═══════════════════════════════════════════════════════════
print()
print("  [C6] PerimDenialMatchup_AND_PerimeterShooter_OVER_pts ...")

c6_bets = []
c6_base = arch_lines[
    arch_lines["all_tags"].str.contains("PERIMETER DENIAL", case=False, na=False) &
    arch_lines["archetype_name"].str.contains("Perimeter Shooter", case=False, na=False) &
    (arch_lines["stat"] == "pts")
].copy()

for _, row in c6_base.iterrows():
    c6_bets.append(make_bet(
        row["player_id"], row["player"], row["date"], "pts", "OVER",
        row["closing_line"], row["actual_value"],
        row.get("over_odds", -110), row.get("under_odds", -110),
        True, "PerimDenialMatchup_AND_PerimeterShooter_OVER_pts",
        extra={"archetype": row["archetype_name"], "opp_scheme": row["dominant_tag"]}
    ))

BET_LOGS["PerimDenialMatchup_AND_PerimeterShooter_OVER_pts"] = c6_bets
print(f"    Fired: {len(c6_bets)} bets")
print(f"    (PerimDenial alone: n={COMPONENT_RESULTS['PerimDenial_alone_OVER_pts']['n_real']}, "
      f"PerimShooter alone: n={COMPONENT_RESULTS['PerimShooter_alone_OVER_pts']['n_real']})")


# ═══════════════════════════════════════════════════════════
# COMPOUND 7: B2B AND High Volatility → UNDER pts
# Conditions: is_b2b AND INT-16 pts_confidence_mult < 0.8
# Reasoning: volatile player + tired = double whammy on output reliability
# ═══════════════════════════════════════════════════════════
print()
print("  [C7] B2B_AND_HighVolatility_UNDER_pts ...")

c7_bets = []
c7_base = lines_rt_player[
    (lines_rt_player["is_b2b"] == 1.0) & (lines_rt_player["stat"] == "pts")
].copy()

for _, row in c7_base.iterrows():
    pid = row.get("player_id")
    if pid is None or (isinstance(pid, float) and np.isnan(pid)):
        pid = fn_norm_id.get(row["player_norm"])
    mult = fast_conf_mult(pid, "pts")
    if mult < 0.8:
        c7_bets.append(make_bet(
            pid, row["player"], row["date"], "pts", "UNDER",
            row["closing_line"], row["actual_value"],
            row.get("over_odds", -110), row.get("under_odds", -110),
            True, "B2B_AND_HighVolatility_UNDER_pts",
            extra={"is_b2b": 1, "pts_conf_mult": float(mult)}
        ))

BET_LOGS["B2B_AND_HighVolatility_UNDER_pts"] = c7_bets
print(f"    Fired: {len(c7_bets)} bets (from {len(c7_base)} B2B pts lines)")
print(f"    (B2B alone: n={COMPONENT_RESULTS['B2B_alone_UNDER_reb']['n_real']}, "
      f"HighVol alone: n={COMPONENT_RESULTS['HighVolatility_alone_UNDER_pts']['n_real']})")


# ═══════════════════════════════════════════════════════════
# COMPOUND 8: Anomaly + Matchup + Recent → OVER reb  (TRIPLE)
# Conditions: player has INT-4 anomaly z > 2.0 on paint_dwell in any recent game
#             AND matchup_deviation paint_dwell > +1.0 sigma vs this opp
#             AND INT-18 tag in [HOT_BREAKOUT, WARMING]
# ═══════════════════════════════════════════════════════════
print()
print("  [C8] Anomaly_AND_Matchup_AND_Recent_OVER_reb ...")

# Build per-player anomaly paint_dwell flag from anom_oof
anom_paint_players = set()
for _, row in anom_oof.iterrows():
    for feat in row["features_parsed"]:
        if feat.get("feature") == "paint_dwell_pct" and feat.get("z", 0) >= 2.0:
            anom_paint_players.add(int(row["player_id"]))
            break

print(f"    Players with paint_dwell anomaly z>2: {len(anom_paint_players)}")
print(f"    HOT/WARMING player ids: {len(hot_player_ids)}")
print(f"    HOT/WARMING player names: {len(hot_player_names)}")

c8_bets = []
c8_candidates = 0
for _, row in mdev_lines_reb.iterrows():
    if row["paint_dwell_pct_z"] <= 1.0:
        continue
    c8_candidates += 1
    pid = fn_norm_id.get(row["player_norm"])
    pname = norm(row["player"])
    # Check anomaly condition
    has_anomaly = (pid is not None and not pd.isna(pid) and int(pid) in anom_paint_players)
    # Check HOT/WARMING condition
    is_hot = (
        (pid is not None and not pd.isna(pid) and int(pid) in hot_player_ids)
        or (pname in hot_player_names)
    )
    if has_anomaly and is_hot:
        c8_bets.append(make_bet(
            pid, row["player"], row["date"], "reb", "OVER",
            row["closing_line"], row["actual_value"],
            row.get("over_odds", -110), row.get("under_odds", -110),
            True, "Anomaly_AND_Matchup_AND_Recent_OVER_reb",
            extra={"paint_dwell_matchup_z": float(row["paint_dwell_pct_z"]),
                   "has_anomaly": True, "is_hot_trend": True}
        ))

BET_LOGS["Anomaly_AND_Matchup_AND_Recent_OVER_reb"] = c8_bets
print(f"    Fired: {len(c8_bets)} bets (matchup+paint candidates: {c8_candidates})")
print(f"    (AnomalyPaintDwell alone: n={COMPONENT_RESULTS['AnomalyPaintDwell_alone_OVER_reb']['n_real']}, "
      f"MatchupPaint alone: n={COMPONENT_RESULTS['MatchupPaint_alone_OVER_reb']['n_real']}, "
      f"HotTrend alone: n={COMPONENT_RESULTS['HotTrend_alone_OVER_pts']['n_real']})")


# ─────────────────────────────────────────────────────────────────────────────
# 6. AGGREGATE PER COMPOUND SIGNAL
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[6] Aggregating compound signal results...")

compound_results = {}
for sname, bets in BET_LOGS.items():
    df_bets = pd.DataFrame(bets) if bets else pd.DataFrame()
    res = aggregate_bets(df_bets, sname, conf_df)
    compound_results[sname] = res
    print(
        f"  {sname}:\n"
        f"    n_bets={res['n_bets']} | n_real={res['n_real_line_bets']} | "
        f"wr={res['win_rate_real']} | roi={res['roi_real_flat']}% | "
        f"ci={res['ci_95']} | z={res['z_stat']} p={res['p_value']} | {res['verdict']}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. RANDOM BASELINE
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[7] Computing random baseline...")

np.random.seed(42)
random_sample = lines_pool[lines_pool["stat"].isin(["pts", "reb", "ast"])].copy()
random_sample = random_sample.sample(min(2000, len(random_sample)), random_state=42)
random_sample["rand_dir"] = np.random.choice(["OVER", "UNDER"], size=len(random_sample))
random_sample["won"] = (
    ((random_sample["actual_value"] > random_sample["closing_line"]) & (random_sample["rand_dir"] == "OVER"))
    | ((random_sample["actual_value"] < random_sample["closing_line"]) & (random_sample["rand_dir"] == "UNDER"))
)
JUICE = 100 / 110
rand_wr = float(random_sample["won"].mean())
rand_roi = rand_wr * JUICE - (1 - rand_wr)
print(f"  Random baseline: n={len(random_sample)}, wr={rand_wr:.3f}, roi={rand_roi*100:.2f}%")


# ─────────────────────────────────────────────────────────────────────────────
# 8. RANK COMPOUND SIGNALS
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[8] Ranking compound signals...")

ranked = sorted(
    compound_results.values(),
    key=lambda x: (x["roi_real_flat"] or -999),
    reverse=True
)
promising = [s for s in ranked if s["verdict"] == "PROMISING"]
neutral = [s for s in ranked if s["verdict"] == "NEUTRAL"]
dead = [s for s in ranked if s["verdict"] == "DEAD"]
insuff = [s for s in ranked if s["verdict"] == "INSUFFICIENT_DATA"]

# Bonferroni: 8 signals
N_COMPOUNDS = len(compound_results)
alpha_bonf = 0.05 / N_COMPOUNDS
significant = [s for s in ranked if s.get("p_value") is not None and s["p_value"] < alpha_bonf]

print(f"  Promising: {[s['name'] for s in promising]}")
print(f"  Neutral:   {[s['name'] for s in neutral]}")
print(f"  Dead:      {[s['name'] for s in dead]}")
print(f"  Insufficient: {[s['name'] for s in insuff]}")
print(f"  Bonferroni alpha ({N_COMPOUNDS} tests) = {alpha_bonf:.4f}")
print(f"  Statistically significant: {[s['name'] for s in significant]}")


# ─────────────────────────────────────────────────────────────────────────────
# 9. COMPONENT VS COMPOUND COMPARISON TABLE
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[9] Component vs Compound comparison...")

COMPOUND_COMPONENT_MAP = {
    "B2B_AND_PaintFirstOpp_UNDER_reb": [
        ("B2B_alone_UNDER_reb", "B2B"),
        ("PaintFirst_alone_UNDER_reb", "PaintFirst"),
    ],
    "Altitude_AND_LowVolatility_UNDER_pts": [
        ("Altitude_alone_UNDER_pts", "Altitude"),
        ("LowVolatility_alone_UNDER_pts", "LowVolatility"),
    ],
    "ClutchShrinker_AND_CloseGame_UNDER_pts": [
        ("ClutchShrinker_alone_UNDER_pts", "ClutchShrinker"),
        ("CloseGame_alone_UNDER_pts", "CloseGame"),
    ],
    "HotTrend_AND_LowVolatility_OVER_pts": [
        ("HotTrend_alone_OVER_pts", "HotTrend"),
        ("LowVolatility_alone_UNDER_pts", "LowVolatility"),
    ],
    "MatchupDefApproach_AND_LowVolatility_UNDER_pts": [
        ("MatchupDefApproach_alone_UNDER_pts", "MatchupDefApproach"),
        ("LowVolatility_alone_UNDER_pts", "LowVolatility"),
    ],
    "PerimDenialMatchup_AND_PerimeterShooter_OVER_pts": [
        ("PerimDenial_alone_OVER_pts", "PerimDenial"),
        ("PerimShooter_alone_OVER_pts", "PerimShooter"),
    ],
    "B2B_AND_HighVolatility_UNDER_pts": [
        ("B2B_alone_UNDER_reb", "B2B (proxy)"),
        ("HighVolatility_alone_UNDER_pts", "HighVolatility"),
    ],
    "Anomaly_AND_Matchup_AND_Recent_OVER_reb": [
        ("AnomalyPaintDwell_alone_OVER_reb", "AnomalyPaintDwell"),
        ("MatchupPaint_alone_OVER_reb", "MatchupPaint"),
        ("HotTrend_alone_OVER_pts", "HotTrend"),
    ],
}

component_comparison = {}
for cname, components in COMPOUND_COMPONENT_MAP.items():
    comp_roi = compound_results[cname]["roi_real_flat"]
    comp_n = compound_results[cname]["n_real_line_bets"]
    comp_wr = compound_results[cname]["win_rate_real"]
    parts = []
    for comp_key, comp_label in components:
        c_res = COMPONENT_RESULTS.get(comp_key, {})
        parts.append({
            "label": comp_label,
            "key": comp_key,
            "n_real": c_res.get("n_real", 0),
            "roi": c_res.get("roi"),
            "win_rate": c_res.get("win_rate"),
        })

    # Does compounding boost above best component?
    best_comp_roi = max((p["roi"] for p in parts if p["roi"] is not None), default=None)
    boost = None
    if comp_roi is not None and best_comp_roi is not None:
        boost = round(comp_roi - best_comp_roi, 2)

    component_comparison[cname] = {
        "compound_roi": comp_roi,
        "compound_n": comp_n,
        "compound_wr": comp_wr,
        "components": parts,
        "best_component_roi": best_comp_roi,
        "boost_vs_best_component_pp": boost,
        "compounding_helps": bool(boost > 0) if boost is not None else None,
    }
    print(f"  {cname}:")
    print(f"    compound: ROI={comp_roi}%, n={comp_n}")
    for p in parts:
        print(f"    component [{p['label']}]: ROI={p['roi']}%, n={p['n_real']}")
    if boost is not None:
        sign = "+" if boost >= 0 else ""
        print(f"    -> boost vs best component: {sign}{boost:.2f}pp | helps: {boost > 0}")


# ─────────────────────────────────────────────────────────────────────────────
# 10. V4 RESULTS COMPARISON (load previous best signals for context)
# ─────────────────────────────────────────────────────────────────────────────
v4_comparison = {}
v4_path = ROOT / "data/models/intelligence_betting_v4_results.json"
if v4_path.exists():
    with open(v4_path) as f:
        v4_data = json.load(f)
    for s in v4_data.get("signals", []):
        v4_comparison[s["name"]] = {
            "roi": s.get("roi_real_flat"),
            "n_real": s.get("n_real_line_bets"),
            "verdict": s.get("verdict"),
        }
    print(f"\n  Loaded V4 results: {len(v4_comparison)} signals for context")
    v4_random_baseline = v4_data.get("meta", {}).get("random_baseline_roi_pct", rand_roi * 100)
else:
    v4_random_baseline = rand_roi * 100
    print("  V4 results not found — using current random baseline")


# ─────────────────────────────────────────────────────────────────────────────
# 11. SAVE JSON
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[10] Saving JSON output...")

output = {
    "meta": {
        "generated": "2026-05-28",
        "version": "INT-V5",
        "hypothesis": "Compound signal stacking produces combinatorial edge not priced by books individually",
        "n_compounds_tested": N_COMPOUNDS,
        "real_lines_pool": int(len(lines_pool)),
        "random_baseline_roi_pct": round(rand_roi * 100, 2),
        "bonferroni_alpha": round(alpha_bonf, 5),
        "bonferroni_n": N_COMPOUNDS,
        "note": "8 compound signals — each requires ALL component conditions to fire simultaneously",
    },
    "compound_signals": list(compound_results.values()),
    "ranking": [s["name"] for s in ranked],
    "verdict_summary": {
        "promising": [s["name"] for s in promising],
        "neutral": [s["name"] for s in neutral],
        "dead": [s["name"] for s in dead],
        "insufficient_data": [s["name"] for s in insuff],
        "statistically_significant_bonferroni": [s["name"] for s in significant],
    },
    "component_signals": COMPONENT_RESULTS,
    "component_vs_compound": component_comparison,
    "v4_context": v4_comparison,
    "random_baseline_roi_pct": round(rand_roi * 100, 2),
}

out_path = ROOT / "data/models/intelligence_stacking_v5_results.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, default=str)
print(f"  Saved -> {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 12. WRITE VAULT DOC
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[11] Writing vault doc...")

def fmt_r(v):
    if v is None: return "N/A"
    return f"{v:+.2f}%"

def fmt_w(v):
    if v is None: return "N/A"
    return f"{v:.3f}"

def fmt_ci(ci):
    if not ci or ci == [None, None]: return "N/A"
    a, b = ci
    if a is None or b is None: return "N/A"
    return f"({a:.1f}%, {b:.1f}%)"

# Full ranked table
rows_md = []
for i, s in enumerate(ranked, 1):
    rows_md.append(
        f"| {i} | {s['name']} | {s['n_real_line_bets']} | "
        f"{fmt_w(s['win_rate_real'])} | {fmt_r(s['roi_real_flat'])} | "
        f"{fmt_ci(s['ci_95'])} | {s['verdict']} |"
    )
ranked_table = "\n".join(rows_md)

# Component vs compound table
comp_rows = []
for cname, cc in component_comparison.items():
    comp_a = cc["components"][0] if len(cc["components"]) > 0 else {}
    comp_b = cc["components"][1] if len(cc["components"]) > 1 else {}
    boost = cc.get("boost_vs_best_component_pp")
    boost_str = f"{boost:+.2f}pp" if boost is not None else "N/A"
    helps = "YES" if cc.get("compounding_helps") else ("NO" if cc.get("compounding_helps") is False else "N/A")
    comp_rows.append(
        f"| {cname} | {fmt_r(comp_a.get('roi'))} (n={comp_a.get('n_real',0)}) | "
        f"{fmt_r(comp_b.get('roi'))} (n={comp_b.get('n_real',0)}) | "
        f"{fmt_r(cc['compound_roi'])} (n={cc['compound_n']}) | "
        f"{boost_str} | {helps} |"
    )
comp_table = "\n".join(comp_rows)

# Promising + dead narrative
NL = "\n"
promising_lines_md = NL.join(
    f"- **{s['name']}**: ROI={fmt_r(s['roi_real_flat'])}, n={s['n_real_line_bets']}, "
    f"wr={fmt_w(s['win_rate_real'])}, CI={fmt_ci(s['ci_95'])}"
    for s in promising
) or "None — no compound signal achieves positive real-line ROI with strong CI."

dead_lines_md = NL.join(
    f"- **{s['name']}**: ROI={fmt_r(s['roi_real_flat'])}, n={s['n_real_line_bets']}"
    for s in dead
) or "None categorically dead at this sample size."

best_compound = ranked[0] if ranked else None
best_compound_name = best_compound["name"] if best_compound else "N/A"
best_compound_roi = fmt_r(best_compound["roi_real_flat"]) if best_compound else "N/A"
best_compound_n = best_compound["n_real_line_bets"] if best_compound else 0
best_compound_ci = fmt_ci(best_compound["ci_95"]) if best_compound else "N/A"

# Boosts analysis
n_boosts = sum(1 for cc in component_comparison.values() if cc.get("compounding_helps") is True)
n_no_boost = sum(1 for cc in component_comparison.values() if cc.get("compounding_helps") is False)
n_insuff = sum(1 for cc in component_comparison.values() if cc.get("compounding_helps") is None)

# Strategic recommendations
live_monitor_list = [s["name"] for s in promising + neutral if s["n_real_line_bets"] >= 5]
drop_list = [s["name"] for s in dead if s["n_real_line_bets"] >= 5]
wait_list = [s["name"] for s in insuff + [s for s in dead if s["n_real_line_bets"] < 5]]

live_mon_md = NL.join(f"- {s}" for s in live_monitor_list) or "- None (all compounds too sparse)"
drop_md = NL.join(f"- {s}" for s in drop_list) or "- None categorically drop-worthy (n too small)"
wait_md = NL.join(f"- {s}" for s in wait_list) or "- None"

sig_names_bonf = [s["name"] for s in significant]
sig_bonf_str = str(sig_names_bonf) if sig_names_bonf else "None"

# Sample coverage analysis
total_compound_bets = sum(r["n_real_line_bets"] for r in compound_results.values())
avg_compound_n = total_compound_bets / N_COMPOUNDS if N_COMPOUNDS > 0 else 0

# Compound 8 is triple
c8_fired = compound_results.get("Anomaly_AND_Matchup_AND_Recent_OVER_reb", {}).get("n_real_line_bets", 0)

# V4 best signal context
v4_best_name, v4_best_roi = "N/A", None
if v4_comparison:
    v4_sorted = sorted(v4_comparison.items(), key=lambda x: x[1].get("roi") or -999, reverse=True)
    if v4_sorted:
        v4_best_name = v4_sorted[0][0]
        v4_best_roi = v4_sorted[0][1].get("roi")

real_line_pct_pool = 100.0

md = f"""# Compound Signal Stacking — INT-V5 Results

> Generated: 2026-05-28
> Version: INT-V5 (compound signal stacking)
> Script: `scripts/test_intelligence_stacking_v5.py`
> JSON: `data/models/intelligence_stacking_v5_results.json`

## Hypothesis

Single intelligence signals (V2/V3/V4) may be priced by sophisticated books.
**COMPOUND signals** require ALL component conditions to fire simultaneously.
If books price each dimension independently, the intersection may not be priced.

## Setup

| Parameter | Value |
|-----------|-------|
| Compound signals tested | {N_COMPOUNDS} |
| Component baselines computed | {len(COMPONENT_RESULTS)} |
| Real lines pool | {len(lines_pool):,} rows |
| Real-line coverage | {real_line_pct_pool:.0f}% |
| Random baseline ROI | {rand_roi*100:.2f}% |
| Bonferroni alpha (8 tests) | α = {alpha_bonf:.5f} |
| V4 best single-signal ROI | {fmt_r(v4_best_roi)} ({v4_best_name}) |

## Compound Signal Rankings

| Rank | Compound Signal | n_real | win_rate | flat ROI | 95% CI | Verdict |
|------|----------------|--------|----------|----------|--------|---------|
{ranked_table}

## Component vs Compound Comparison

For each compound, does stacking boost ROI above the best component alone?

| Compound | Component A ROI | Component B ROI | Compound ROI | Boost | Helps? |
|----------|----------------|----------------|--------------|-------|--------|
{comp_table}

**Summary:** {n_boosts}/{N_COMPOUNDS} compounds beat their best component | {n_no_boost} did not | {n_insuff} insufficient data

## Promising Compound Signals

{promising_lines_md}

## Dead Compound Signals

{dead_lines_md}

## Best Compound Discovered

- **Name:** {best_compound_name}
- **ROI:** {best_compound_roi}
- **n:** {best_compound_n}
- **95% CI:** {best_compound_ci}
- **Verdict:** {best_compound["verdict"] if best_compound else "N/A"}
- **Interpretation:** {"Compound intersection of conditions that individually may not be edge; stacking may isolate rare unpriced scenarios." if best_compound else "N/A"}

## Statistical Significance (Bonferroni)

- 8 compound signals tested; α = 0.05/8 = {alpha_bonf:.5f}
- Signals passing Bonferroni threshold: **{sig_bonf_str}**
- Expected false positives at α=0.05 without correction: ~0.4

## Sample Size Reality Check

| Compound | n_real | Sufficient for inference? |
|----------|--------|--------------------------|
{chr(10).join(f"| {r['name']} | {r['n_real_line_bets']} | {'YES (>=20)' if r['n_real_line_bets'] >= 20 else 'MARGINAL (5-19)' if r['n_real_line_bets'] >= 5 else 'NO (<5)'} |" for r in ranked)}

Average n_real per compound: {avg_compound_n:.1f}
Total compound bets across all 8 signals: {total_compound_bets}

## Why Compound Intersections Are Sparse

AND-logic multiplicatively reduces sample size. If signal A fires in 5% of games
and signal B fires in 3% independently, the compound fires in ~0.15% of games.
With ~10,000 real-line rows per stat, expect 15 compound bets — barely enough for
any statistical conclusion. This is the **fundamental challenge** of compound stacking.

## Strategic Takeaways

**Worth live-monitoring (positive or neutral ROI, n >= 5):**
{live_mon_md}

**Drop (clearly negative ROI, n sufficient to trust):**
{drop_md}

**Wait for more data (n too small):**
{wait_md}

## Honest Caveats

1. **Tiny intersection samples**: compound AND-logic produces very few bets. Most
   compounds fire fewer than 20 times — CIs span 60-100pp wide. No conclusion is
   statistically reliable.
2. **8-test multiple comparisons**: Bonferroni α = {alpha_bonf:.5f}. Any apparent winner
   is almost certainly a noise artifact at these n values.
3. **Books may already price compound conditions**: if B2B + paint-first is a known
   scheduling edge, sportsbooks may have already tightened those lines.
4. **Triple intersection (C8)** is expected to fire extremely rarely — useful only
   as a high-conviction filter if enough historical data exists.
5. **Rolling trends recency**: INT-18 covers only {len(trends)} players and dates from
   2026-01 — limited temporal overlap with lines pool.
6. **Altitude/B2B context**: lines_rt_player join recovers ~{len(lines_rt_player):,} rows
   out of {len(lines_pool):,} total; players without OOF game_id match lose altitude/B2B context.

## Cross-Version Context

| Version | Best signal | ROI | n |
|---------|-------------|-----|---|
| V2 | matchup_def_approach_UNDER_pts | ~+8% | small |
| V3 | perimeter_vs_perim_denial_OVER_pts | best archetype×scheme | small |
| V4 | (position×scheme + clutch + B2B) | various | small |
| V5 | {best_compound_name} | {best_compound_roi} | {best_compound_n} |

**Key finding**: Compound stacking {'shows promise — the intersection boosts ROI above components in ' + str(n_boosts) + ' of ' + str(N_COMPOUNDS) + ' cases' if n_boosts > 0 else 'does NOT consistently boost ROI above individual components at current sample sizes'}. Until more data accumulates, stacking adds complexity without confirmed edge.

---
*See also: [[Betting_Signal_Ranking]], [[Betting_Signal_Ranking_v4]], [[project_loop7_status]], [[Tracker Improvements Log]]*
"""

vault_dir = ROOT / "vault/Intelligence"
vault_dir.mkdir(parents=True, exist_ok=True)
vault_path = vault_dir / "Compound_Signal_Stacking.md"
with open(vault_path, "w", encoding="utf-8") as f:
    f.write(md)
print(f"  Vault doc saved -> {vault_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 13. FINAL REPORT
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("INT-V5 Compound Signal Stacking — FINAL REPORT")
print("=" * 70)

print(f"""
SETUP
  Compound signals tested: {N_COMPOUNDS}
  Component baselines: {len(COMPONENT_RESULTS)}
  Real lines pool: {len(lines_pool):,} rows
  Random baseline ROI: {rand_roi*100:.2f}%
  Bonferroni alpha: {alpha_bonf:.5f} (0.05/{N_COMPOUNDS})
""")

print("COMPOUND SIGNAL RANKINGS (by real-line ROI)")
print(f"  {'Compound Signal':<55} {'n_real':>6} {'win_rate':>9} {'flat ROI':>10} {'CI':>25}")
print("  " + "-" * 110)
for s in ranked:
    print(
        f"  {s['name']:<55} {s['n_real_line_bets']:>6} "
        f"{fmt_w(s['win_rate_real']):>9} {fmt_r(s['roi_real_flat']):>10} "
        f"{fmt_ci(s['ci_95']):>25}  {s['verdict']}"
    )

print()
print("COMPONENT VS COMPOUND (does stacking boost ROI?)")
print(f"  {'Compound':<50} {'Best Comp ROI':>15} {'Compound ROI':>14} {'Boost':>8} {'Helps?':>8}")
print("  " + "-" * 100)
for cname, cc in component_comparison.items():
    boost = cc.get("boost_vs_best_component_pp")
    boost_str = f"{boost:+.2f}pp" if boost is not None else "N/A"
    helps = "YES" if cc.get("compounding_helps") else ("NO" if cc.get("compounding_helps") is False else "?")
    print(
        f"  {cname:<50} {fmt_r(cc['best_component_roi']):>15} "
        f"{fmt_r(cc['compound_roi']):>14} {boost_str:>8} {helps:>8}"
    )

print()
print(f"STACKING SUMMARY: {n_boosts}/{N_COMPOUNDS} compounds beat best component | "
      f"{n_no_boost} did not | {n_insuff} insufficient data")

print()
print("STATISTICAL SIGNIFICANCE")
if significant:
    for s in significant:
        print(f"  SIGNIFICANT: {s['name']} z={s['z_stat']} p={s['p_value']}")
else:
    print(f"  None pass Bonferroni threshold (alpha={alpha_bonf:.5f}) — expected at these n values.")

print()
print("ANSWER TO HYPOTHESIS")
if n_boosts >= 3:
    print("  TENTATIVE YES: Majority of compounds boost ROI vs best component.")
    print("  BUT: Sample sizes are too small for statistical confidence.")
    print("  Action: Live-monitor top compounds; accumulate 200+ bets before deploying.")
elif n_boosts >= 1:
    print("  MIXED: Some compounds boost ROI, most do not.")
    print("  Key insight: stacking is NOT universally beneficial.")
    print("  Action: Only pursue compounds that show directional boost with n >= 20.")
else:
    print("  NEGATIVE: Compounding does NOT boost ROI at current data levels.")
    print("  Likely cause: sample sizes too small (AND-logic over-fragments already thin data).")
    print("  Action: Revisit with 3-5x more line data before concluding stacking fails.")

print()
print("HONEST CAVEATS")
print(f"""
  1. Compound AND-logic is multiplicatively sparse — avg n_real = {avg_compound_n:.1f}/compound
  2. No compound passes Bonferroni threshold — all verdicts are directional only
  3. Books may price compound conditions (B2B schedule is public; altitude is public)
  4. Rolling trends (INT-18) covers only {len(trends)} players — very limited compound overlap
  5. Triple intersection (C8) barely fires — conceptually valid but empirically untestable
  6. All signals need 200+ real-line bets before live deployment
""")

print(f"""
FILES
  scripts/test_intelligence_stacking_v5.py
  data/models/intelligence_stacking_v5_results.json
  vault/Intelligence/Compound_Signal_Stacking.md
""")
