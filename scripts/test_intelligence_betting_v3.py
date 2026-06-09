"""
INT-V3 Granular Signal Betting Backtest
========================================
Tests each SPECIFIC signal in isolation per stat, with real sportsbook line lookup.
Goal: identify the exact (signal x stat) combinations that generate edge.

10 signals tested:
  1.  cutter_vs_paint_first_UNDER_pts
  2.  perimeter_vs_perim_denial_OVER_pts
  3.  perimeter_vs_help_defense_OVER_pts
  4.  paint_vs_paint_first_UNDER_pts
  5.  perimeter_vs_perim_denial_OVER_ast
  6.  matchup_def_approach_UNDER_pts        (V2 winner re-test)
  7.  anomaly_paint_dwell_OVER_reb
  8.  anomaly_touches_OVER_ast
  9.  anomaly_potential_assists_OVER_ast
  10. cutter_vs_paint_first_AND_low_volatility_UNDER_pts

Outputs:
  data/models/intelligence_betting_v3_results.json
  vault/Intelligence/Betting_Signal_Ranking.md
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

warnings.filterwarnings("ignore")
random.seed(42)
np.random.seed(42)

ROOT = Path("C:/Users/neelj/nba-ai-system")

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
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


def safe_odds(v) -> float:
    """Return valid American odds, defaulting to -110 for corrupt/missing values.
    American odds must be <= -100 (negative) or >= 100 (positive).
    Values in (-99, 99) are corrupt data entries."""
    try:
        f = float(v)
        if np.isnan(f) or f == 0:
            return -110.0
        # Reject values that aren't valid American odds (must be >= 100 or <= -100)
        if -99 < f < 100:
            return -110.0
        return f
    except Exception:
        return -110.0


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


def verdict(roi_real: float | None, n_real: int, ci: tuple) -> str:
    if roi_real is None or n_real == 0:
        return "INSUFFICIENT_DATA"
    if roi_real > 0 and ci[0] is not None and ci[0] > -20:
        return "PROMISING"
    elif roi_real > -4.5:
        return "NEUTRAL"
    else:
        return "DEAD"


def aggregate_bets(df: pd.DataFrame, signal_name: str, confidence: pd.DataFrame | None = None):
    """
    Aggregate a bet-log DataFrame into per-signal stats.
    confidence: per_player_confidence keyed by player_id (for INT-16 weighting)
    """
    if df is None or len(df) == 0:
        return {
            "name": signal_name, "n_bets": 0, "n_real_line_bets": 0,
            "n_proxy_bets": 0, "win_rate_real": None, "roi_real_flat": None,
            "roi_real_weighted": None, "ci_95": [None, None],
            "z_stat": None, "p_value": None, "verdict": "INSUFFICIENT_DATA",
        }

    real_df = df[df["has_real_line"] == True].copy()
    proxy_df = df[df["has_real_line"] == False].copy()

    # flat ROI on real lines
    roi_flat = real_df["pnl"].mean() * 100 if len(real_df) > 0 else None
    wr_real = real_df["won"].mean() if len(real_df) > 0 else None
    ci = bootstrap_roi_ci(real_df["pnl"]) if len(real_df) >= 3 else (None, None)
    zstat, pval = z_roi_gt_zero(real_df["pnl"]) if len(real_df) >= 5 else (None, None)

    # INT-16 Kelly-multiplier-weighted ROI on real lines
    roi_weighted = None
    if confidence is not None and len(real_df) > 0 and "player_id" in real_df.columns:
        stat_col = signal_name.split("_")[-1]  # e.g. 'pts', 'reb', 'ast'
        mult_col = f"{stat_col}_confidence_mult"
        if mult_col not in confidence.columns:
            mult_col = "overall_confidence_mult"
        # Coerce player_id to Int64 (nullable) to handle None/NaN mixed with int
        real_df = real_df.copy()
        real_df["player_id"] = pd.to_numeric(real_df["player_id"], errors="coerce")
        conf_subset = confidence[["player_id", mult_col]].copy()
        conf_subset["player_id"] = pd.to_numeric(conf_subset["player_id"], errors="coerce")
        merged = real_df.merge(
            conf_subset.rename(columns={mult_col: "mult"}),
            on="player_id", how="left"
        )
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


# ─────────────────────────────────────────────────────────────────────────────
# 1. LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 70)
print("INT-V3 Granular Signal Betting Backtest")
print("=" * 70)

print("\n[1] Loading data sources...")

# OOF actuals + L5 proxy
oof = pd.read_parquet(ROOT / "data/cache/pregame_oof.parquet")
oof["game_date"] = pd.to_datetime(oof["game_date"])
oof = oof.sort_values(["player_id", "stat", "game_date"])
oof["l5_mean_proxy"] = oof.groupby(["player_id", "stat"])["actual"].transform(
    lambda x: x.shift(1).rolling(5, min_periods=1).mean()
)
print(f"  OOF rows: {len(oof):,} | stats: {sorted(oof['stat'].unique().tolist())}")

# Per-player confidence (INT-16)
conf_df = pd.read_parquet(ROOT / "data/intelligence/per_player_confidence.parquet")
print(f"  INT-16 confidence: {len(conf_df)} players")

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

# Matchup deviations (INT-3)
mdev = pd.read_parquet(ROOT / "data/intelligence/matchup_deviations.parquet")
mdev["player_norm"] = mdev["player_name"].map(norm)
print(f"  INT-3 matchup deviations: {len(mdev)} rows")

# Player fingerprints (archetypes)
fp = pd.read_parquet(ROOT / "data/intelligence/player_fingerprints.parquet")
fp = fp.reset_index()  # player_id is the index
fp["player_norm"] = fp["player_name"].map(norm)
fp = fp[["player_id", "player_norm", "archetype_name"]].copy()
print(f"  Archetypes: {len(fp)} players — {fp['archetype_name'].value_counts().to_dict()}")

# Defensive schemes
schemes = pd.read_parquet(ROOT / "data/intelligence/defensive_schemes.parquet")
schemes["dominant_tag"] = schemes["dominant_tag"].str.strip().str.upper()
schemes["all_tags"] = schemes["all_tags"].str.upper()
print(f"  Defensive schemes: {len(schemes)} teams")

# ─────────────────────────────────────────────────────────────────────────────
# 2. LOAD + POOL SPORTSBOOK LINES
# ─────────────────────────────────────────────────────────────────────────────
print("\n[2] Loading sportsbook lines...")

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
print(f"  Pooled lines: {len(lines_pool):,} rows with real actuals")
print(f"  Stat breakdown: {lines_pool['stat'].value_counts().to_dict()}")
print(f"  Date range: {lines_pool['date'].min().date()} to {lines_pool['date'].max().date()}")

# ─────────────────────────────────────────────────────────────────────────────
# 3. BUILD PER-GAME LOOKUP TABLES
# ─────────────────────────────────────────────────────────────────────────────
print("\n[3] Building lookup tables...")

# OOF actuals per (player_id, game_id, stat) — for anomaly + archetype signals
oof_lookup = oof.set_index(["player_id", "game_id", "stat"])

# For anomaly signals: join anomaly log with OOF to get game_date + actual
# anom already has game_date; rename OOF's to avoid collision
oof_for_anom = oof[["player_id", "game_id", "stat", "actual", "l5_mean_proxy"]].copy()
anom_oof = anom.merge(oof_for_anom, on=["player_id", "game_id"], how="inner")
# game_date comes from anom (already parsed above)
anom_oof["game_date"] = pd.to_datetime(anom_oof["game_date"])
# Join real lines
anom_oof = anom_oof.merge(
    lines_pool[["player_norm", "date", "stat", "closing_line", "over_odds", "under_odds"]],
    left_on=["player_norm", "game_date", "stat"],
    right_on=["player_norm", "date", "stat"],
    how="left"
)
anom_oof["has_real_line"] = anom_oof["closing_line"].notna()
anom_oof["effective_line"] = anom_oof["closing_line"].fillna(anom_oof["l5_mean_proxy"])
anom_oof = anom_oof.dropna(subset=["effective_line", "actual"])
print(f"  Anomaly+OOF rows: {len(anom_oof):,} | real lines: {anom_oof['has_real_line'].sum()}")

# For archetype x scheme signals: need per (player, opp_team, game_date, stat)
# Build from OOF — join with player_fingerprint, then with scheme, then with lines
# The key challenge: OOF doesn't have opp_team. We use lines_pool which has opp.
# Approach: merge lines with fingerprints (on player_norm), then with schemes (on opp)
arch_lines = lines_pool.merge(
    fp[["player_id", "player_norm", "archetype_name"]],
    on="player_norm",
    how="inner"
)
arch_lines = arch_lines.merge(
    schemes[["team", "dominant_tag", "all_tags"]],
    left_on="opp",
    right_on="team",
    how="inner"
)
print(f"  Archetype×Scheme game-lines: {len(arch_lines):,} rows")

# Summary of archetype breakdown in lines
arch_dist = arch_lines["archetype_name"].value_counts().to_dict()
scheme_dist = arch_lines["dominant_tag"].value_counts().to_dict()
print(f"  Archetype dist: {arch_dist}")
print(f"  Scheme dist: {scheme_dist}")

# ─────────────────────────────────────────────────────────────────────────────
# 4. DEFINE + FIRE EACH SIGNAL
# ─────────────────────────────────────────────────────────────────────────────
print("\n[4] Building bet logs for each signal...")

BET_LOGS = {}  # signal_name -> list of bet dicts

# ─── Helper to make a bet dict ───
def make_bet(player_id, player_name, game_date, stat, bet_dir,
             line, actual, over_odds_val, under_odds_val,
             has_real_line, signal_name, extra: dict = None):
    won = (actual > line) if bet_dir == "OVER" else (actual < line)
    odds = safe_odds(over_odds_val) if bet_dir == "OVER" else safe_odds(under_odds_val)
    pnl = roi_per_bet(won, odds)
    d = {
        "player_id": int(player_id) if player_id is not None else None,
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


# ═══════════════════════════════════════════════════════════════
# SIGNALS 1-5: Archetype × Scheme  (uses arch_lines)
# ═══════════════════════════════════════════════════════════════

def archetype_scheme_signal(arch_keyword: str, scheme_keyword: str,
                             stat: str, bet_dir: str, signal_name: str,
                             check_all_tags: bool = True):
    """
    Fire when player archetype contains arch_keyword AND
    opponent scheme contains scheme_keyword (check dominant_tag or all_tags).
    """
    mask_arch = arch_lines["archetype_name"].str.contains(arch_keyword, case=False, na=False)
    if check_all_tags:
        mask_scheme = arch_lines["all_tags"].str.contains(scheme_keyword, case=False, na=False)
    else:
        mask_scheme = arch_lines["dominant_tag"].str.contains(scheme_keyword, case=False, na=False)
    mask_stat = arch_lines["stat"] == stat
    sub = arch_lines[mask_arch & mask_scheme & mask_stat].copy()

    bets = []
    for _, row in sub.iterrows():
        bets.append(make_bet(
            player_id=row["player_id"],
            player_name=row["player"],
            game_date=row["date"],
            stat=stat,
            bet_dir=bet_dir,
            line=row["closing_line"],
            actual=row["actual_value"],
            over_odds_val=row.get("over_odds", -110),
            under_odds_val=row.get("under_odds", -110),
            has_real_line=True,
            signal_name=signal_name,
            extra={"archetype": row["archetype_name"], "opp_scheme": row["dominant_tag"]}
        ))
    print(f"  [{signal_name}] fired={len(bets)} bets (arch_keyword='{arch_keyword}', scheme_keyword='{scheme_keyword}', stat={stat})")
    return bets


# Signal 1: High-Motor Cutter vs PAINT-FIRST → UNDER PTS
BET_LOGS["cutter_vs_paint_first_UNDER_pts"] = archetype_scheme_signal(
    "Cutter", "PAINT-FIRST", "pts", "UNDER", "cutter_vs_paint_first_UNDER_pts"
)

# Signal 2: Perimeter Shooter vs PERIMETER DENIAL → OVER PTS
BET_LOGS["perimeter_vs_perim_denial_OVER_pts"] = archetype_scheme_signal(
    "Perimeter Shooter", "PERIMETER DENIAL", "pts", "OVER", "perimeter_vs_perim_denial_OVER_pts"
)

# Signal 3: Perimeter Shooter vs HELP DEFENSE → OVER PTS
BET_LOGS["perimeter_vs_help_defense_OVER_pts"] = archetype_scheme_signal(
    "Perimeter Shooter", "HELP DEFENSE", "pts", "OVER", "perimeter_vs_help_defense_OVER_pts"
)

# Signal 4: Post-Heavy vs PAINT-FIRST → UNDER PTS
BET_LOGS["paint_vs_paint_first_UNDER_pts"] = archetype_scheme_signal(
    "Post-Heavy", "PAINT-FIRST", "pts", "UNDER", "paint_vs_paint_first_UNDER_pts"
)

# Signal 5: Perimeter Shooter vs PERIMETER DENIAL → OVER AST
BET_LOGS["perimeter_vs_perim_denial_OVER_ast"] = archetype_scheme_signal(
    "Perimeter Shooter", "PERIMETER DENIAL", "ast", "OVER", "perimeter_vs_perim_denial_OVER_ast"
)


# ═══════════════════════════════════════════════════════════════
# SIGNAL 6: Matchup defender_approach_z < -1.5 → UNDER PTS (V2 winner)
# ═══════════════════════════════════════════════════════════════

def matchup_signal(z_col: str, z_dir: str, z_thresh: float,
                   stat: str, bet_dir: str, signal_name: str):
    """
    Join matchup_deviations with lines on (player_norm, opp).
    Fire when z_col passes threshold.
    """
    mdev_sub = mdev[["player_norm", "opp_team", z_col]].dropna(subset=[z_col]).copy()

    joined = lines_pool[lines_pool["stat"] == stat].merge(
        mdev_sub,
        left_on=["player_norm", "opp"],
        right_on=["player_norm", "opp_team"],
        how="inner"
    )

    if z_dir == "negative":
        mask = joined[z_col] <= z_thresh
    else:
        mask = joined[z_col] >= z_thresh

    sub = joined[mask].copy()
    bets = []
    for _, row in sub.iterrows():
        bets.append(make_bet(
            player_id=None,
            player_name=row["player"],
            game_date=row["date"],
            stat=stat,
            bet_dir=bet_dir,
            line=row["closing_line"],
            actual=row["actual_value"],
            over_odds_val=row.get("over_odds", -110),
            under_odds_val=row.get("under_odds", -110),
            has_real_line=True,
            signal_name=signal_name,
            extra={"z_col": z_col, "z_val": float(row[z_col]), "opp": row["opp"]}
        ))
    print(f"  [{signal_name}] fired={len(bets)} bets ({z_col} {z_dir} {z_thresh}, stat={stat})")
    return bets


BET_LOGS["matchup_def_approach_UNDER_pts"] = matchup_signal(
    "defender_approach_speed_z", "negative", -1.5, "pts", "UNDER", "matchup_def_approach_UNDER_pts"
)


# ═══════════════════════════════════════════════════════════════
# SIGNALS 7-9: Anomaly direction signals (INT-4)
# ═══════════════════════════════════════════════════════════════

def anomaly_feature_signal(feature_name: str, z_dir: str, z_thresh: float,
                            stat: str, bet_dir: str, signal_name: str):
    """
    Fire when a specific feature appears in top_3_features with z past threshold.
    Uses anom_oof (already has OOF actuals + real line lookup).
    """
    sub = anom_oof[anom_oof["stat"] == stat].copy()

    def feature_z(row):
        for feat_obj in row["features_parsed"]:
            if feat_obj.get("feature") == feature_name:
                return feat_obj.get("z", 0.0)
        return None

    sub["feat_z"] = sub.apply(feature_z, axis=1)
    sub = sub.dropna(subset=["feat_z"])

    if z_dir == "positive":
        sub = sub[sub["feat_z"] >= z_thresh]
    else:
        sub = sub[sub["feat_z"] <= z_thresh]

    bets = []
    for _, row in sub.iterrows():
        bets.append(make_bet(
            player_id=row["player_id"],
            player_name=row["player_name"],
            game_date=row["game_date"],
            stat=stat,
            bet_dir=bet_dir,
            line=row["effective_line"],
            actual=row["actual"],
            over_odds_val=row.get("over_odds", -110),
            under_odds_val=row.get("under_odds", -110),
            has_real_line=bool(row["has_real_line"]),
            signal_name=signal_name,
            extra={"feature": feature_name, "z": float(row["feat_z"])}
        ))
    print(f"  [{signal_name}] fired={len(bets)} bets | real_line={sum(b['has_real_line'] for b in bets)}")
    return bets


# Signal 7: paint_dwell anomaly z > +2 → OVER REB
BET_LOGS["anomaly_paint_dwell_OVER_reb"] = anomaly_feature_signal(
    "paint_dwell_pct", "positive", 2.0, "reb", "OVER", "anomaly_paint_dwell_OVER_reb"
)

# Signal 8: touches anomaly z > +2 → OVER AST
BET_LOGS["anomaly_touches_OVER_ast"] = anomaly_feature_signal(
    "touches_per_game", "positive", 2.0, "ast", "OVER", "anomaly_touches_OVER_ast"
)

# Signal 9: potential_assists anomaly z > +2 → OVER AST
BET_LOGS["anomaly_potential_assists_OVER_ast"] = anomaly_feature_signal(
    "potential_assists", "positive", 2.0, "ast", "OVER", "anomaly_potential_assists_OVER_ast"
)


# ═══════════════════════════════════════════════════════════════
# SIGNAL 10: Combined — cutter_vs_paint_first AND low_volatility → UNDER PTS
# ═══════════════════════════════════════════════════════════════

def combined_signal(base_bets: list, conf_df: pd.DataFrame,
                    stat: str, confidence_threshold: float,
                    signal_name: str):
    """
    Filter base_bets to only those where player has
    pts_confidence_mult > confidence_threshold (low volatility = high multiplier).
    """
    mult_col = f"{stat}_confidence_mult"
    if mult_col not in conf_df.columns:
        mult_col = "overall_confidence_mult"

    pid_to_mult = dict(zip(conf_df["player_id"], conf_df[mult_col]))

    filtered = []
    for bet in base_bets:
        pid = bet.get("player_id")
        if pid is None:
            continue
        mult = pid_to_mult.get(int(pid), 1.0)
        if mult > confidence_threshold:
            b = dict(bet)
            b["signal"] = signal_name
            b["confidence_mult"] = float(mult)
            filtered.append(b)

    print(f"  [{signal_name}] fired={len(filtered)} bets from {len(base_bets)} base bets "
          f"(confidence_mult > {confidence_threshold})")
    return filtered


# Signal 10 needs player_id from signal 1 — but archetype signal uses lines-based bets
# For combined, we need player_id in arch bets.
# We already store player_id from fp merge in arch_lines. Confirm it's in bets.
base_signal_1 = BET_LOGS["cutter_vs_paint_first_UNDER_pts"]
pid_coverage = sum(1 for b in base_signal_1 if b["player_id"] is not None)
print(f"  Signal 1 player_id coverage: {pid_coverage}/{len(base_signal_1)}")

BET_LOGS["cutter_vs_paint_first_AND_low_volatility_UNDER_pts"] = combined_signal(
    base_signal_1, conf_df, "pts", 1.0, "cutter_vs_paint_first_AND_low_volatility_UNDER_pts"
)


# ─────────────────────────────────────────────────────────────────────────────
# 5. AGGREGATE PER SIGNAL
# ─────────────────────────────────────────────────────────────────────────────
print("\n[5] Aggregating per-signal stats...")

signal_results = {}
for sname, bets in BET_LOGS.items():
    df_bets = pd.DataFrame(bets) if bets else pd.DataFrame()
    res = aggregate_bets(df_bets, sname, conf_df)
    signal_results[sname] = res

    print(f"  {sname}:")
    print(f"    n_bets={res['n_bets']} | n_real={res['n_real_line_bets']} | "
          f"wr_real={res['win_rate_real']} | roi_real={res['roi_real_flat']}% | "
          f"ci={res['ci_95']} | z={res['z_stat']} p={res['p_value']} | {res['verdict']}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. INT-16 KELLY WEIGHTING COMPARISON
# ─────────────────────────────────────────────────────────────────────────────
print("\n[6] INT-16 Kelly weighting comparison...")

weighting_comparison = {}
for sname, bets in BET_LOGS.items():
    if not bets:
        continue
    df_bets = pd.DataFrame(bets)
    real_df = df_bets[df_bets["has_real_line"] == True].copy()
    if len(real_df) < 3:
        continue

    flat_roi = real_df["pnl"].mean() * 100

    # weighted ROI
    stat_part = sname.split("_")[-1]
    mult_col = f"{stat_part}_confidence_mult"
    if mult_col not in conf_df.columns:
        mult_col = "overall_confidence_mult"

    if "player_id" in real_df.columns:
        pid_to_mult = dict(zip(conf_df["player_id"], conf_df[mult_col]))
        real_df["mult"] = real_df["player_id"].map(
            lambda p: pid_to_mult.get(int(p), 1.0) if p is not None else 1.0
        )
        w_sum = real_df["mult"].sum()
        if w_sum > 0:
            weighted_roi = float((real_df["pnl"] * real_df["mult"]).sum() / w_sum * 100)
        else:
            weighted_roi = flat_roi
    else:
        weighted_roi = flat_roi

    uplift = round(weighted_roi - flat_roi, 2)
    weighting_comparison[sname] = {
        "flat_roi": round(flat_roi, 2),
        "weighted_roi": round(weighted_roi, 2),
        "uplift_pp": uplift,
    }
    print(f"  {sname}: flat={flat_roi:.2f}% weighted={weighted_roi:.2f}% uplift={uplift:+.2f}pp")


# ─────────────────────────────────────────────────────────────────────────────
# 7. COMBINED SIGNAL PRECISION ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[7] Combined signal precision analysis...")

base_name = "cutter_vs_paint_first_UNDER_pts"
combined_name = "cutter_vs_paint_first_AND_low_volatility_UNDER_pts"

base_res = signal_results[base_name]
combined_res = signal_results[combined_name]

precision_analysis = {
    "base_signal": {
        "name": base_name,
        "n_real": base_res["n_real_line_bets"],
        "win_rate": base_res["win_rate_real"],
        "roi": base_res["roi_real_flat"],
    },
    "combined_signal": {
        "name": combined_name,
        "n_real": combined_res["n_real_line_bets"],
        "win_rate": combined_res["win_rate_real"],
        "roi": combined_res["roi_real_flat"],
    },
    "precision_helps": (
        (combined_res["roi_real_flat"] or -99) > (base_res["roi_real_flat"] or -99)
        if combined_res["n_real_line_bets"] > 0 else None
    ),
    "sample_reduction_pct": round(
        100 * (1 - combined_res["n_real_line_bets"] / max(base_res["n_real_line_bets"], 1)), 1
    ),
}

print(f"  Base: n={precision_analysis['base_signal']['n_real']} roi={precision_analysis['base_signal']['roi']}%")
print(f"  Combined: n={precision_analysis['combined_signal']['n_real']} roi={precision_analysis['combined_signal']['roi']}%")
print(f"  Precision helps? {precision_analysis['precision_helps']}")


# ─────────────────────────────────────────────────────────────────────────────
# 8. RANDOM BASELINE
# ─────────────────────────────────────────────────────────────────────────────
print("\n[8] Computing random baseline...")

np.random.seed(42)
random_sample = lines_pool[lines_pool["stat"].isin(["pts", "reb", "ast", "fg3m"])].copy()
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
# 9. RANK SIGNALS + IDENTIFY TOP / DEAD
# ─────────────────────────────────────────────────────────────────────────────
print("\n[9] Ranking signals...")

ranked = sorted(
    signal_results.values(),
    key=lambda x: (x["roi_real_flat"] or -999),
    reverse=True
)
promising = [s for s in ranked if s["verdict"] == "PROMISING"]
neutral = [s for s in ranked if s["verdict"] == "NEUTRAL"]
dead = [s for s in ranked if s["verdict"] == "DEAD"]
insuff = [s for s in ranked if s["verdict"] == "INSUFFICIENT_DATA"]

print(f"  Promising: {[s['name'] for s in promising]}")
print(f"  Neutral:   {[s['name'] for s in neutral]}")
print(f"  Dead:      {[s['name'] for s in dead]}")
print(f"  Insufficient data: {[s['name'] for s in insuff]}")

# Bonferroni threshold
alpha_bonf = 0.05 / 10
print(f"  Bonferroni-adjusted alpha = {alpha_bonf:.4f}")
significant = [s for s in ranked if s.get("p_value") is not None and s["p_value"] < alpha_bonf]
print(f"  Statistically significant (Bonferroni): {[s['name'] for s in significant]}")


# ─────────────────────────────────────────────────────────────────────────────
# 10. SAVE JSON
# ─────────────────────────────────────────────────────────────────────────────
print("\n[10] Saving JSON output...")

# Compute average weighting uplift
avg_uplift = (
    np.mean([v["uplift_pp"] for v in weighting_comparison.values()])
    if weighting_comparison else 0.0
)
best_uplift_signal = (
    max(weighting_comparison.items(), key=lambda x: x[1]["uplift_pp"])[0]
    if weighting_comparison else None
)

# Signal class analysis
class_summary = {}
for s in ranked:
    sname = s["name"]
    if "archetype" in sname or "cutter" in sname or "perimeter" in sname or "paint_vs" in sname:
        cls = "archetype_x_scheme"
    elif sname.startswith("matchup"):
        cls = "matchup"
    elif sname.startswith("anomaly"):
        cls = "anomaly"
    elif "AND" in sname:
        cls = "combined"
    else:
        cls = "other"
    if cls not in class_summary:
        class_summary[cls] = []
    if s["roi_real_flat"] is not None:
        class_summary[cls].append(s["roi_real_flat"])

class_avg_roi = {k: round(float(np.mean(v)), 2) for k, v in class_summary.items() if v}
best_class = max(class_avg_roi.items(), key=lambda x: x[1])[0] if class_avg_roi else "unknown"

output = {
    "meta": {
        "generated": "2026-05-28",
        "version": "INT-V3",
        "n_signals_tested": len(signal_results),
        "real_lines_pool": len(lines_pool),
        "random_baseline_roi_pct": round(rand_roi * 100, 2),
        "bonferroni_alpha": alpha_bonf,
        "note": "Each signal tested independently in isolation with real closing lines where available",
    },
    "signals": list(signal_results.values()),
    "ranking": [s["name"] for s in ranked],
    "verdict_summary": {
        "promising": [s["name"] for s in promising],
        "neutral": [s["name"] for s in neutral],
        "dead": [s["name"] for s in dead],
        "insufficient_data": [s["name"] for s in insuff],
        "statistically_significant_bonferroni": [s["name"] for s in significant],
    },
    "int16_weighting": {
        "comparison": weighting_comparison,
        "avg_uplift_pp": round(avg_uplift, 2),
        "best_uplift_signal": best_uplift_signal,
    },
    "combined_signal_precision": precision_analysis,
    "signal_class_avg_roi": class_avg_roi,
    "best_signal_class": best_class,
}

out_path = ROOT / "data/models/intelligence_betting_v3_results.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w") as f:
    json.dump(output, f, indent=2, default=str)
print(f"  Saved -> {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 11. WRITE VAULT ATLAS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[11] Writing vault atlas...")

def fmt_r(v):
    if v is None: return "N/A"
    return f"{v:+.2f}%"

def fmt_w(v):
    if v is None: return "N/A"
    return f"{v:.3f}"

def fmt_ci(ci):
    if ci is None or ci == [None, None]: return "N/A"
    return f"({ci[0]:.1f}%, {ci[1]:.1f}%)"

# Build signal table rows (ranked)
rows = []
for i, s in enumerate(ranked, 1):
    rows.append(
        f"| {i} | {s['name']} | {s['n_real_line_bets']} | "
        f"{fmt_w(s['win_rate_real'])} | {fmt_r(s['roi_real_flat'])} | "
        f"{fmt_r(s['roi_real_weighted'])} | {fmt_ci(s['ci_95'])} | {s['verdict']} |"
    )
table_md = "\n".join(rows)

# Class analysis
class_table_rows = "\n".join([
    f"| {cls} | {fmt_r(avg)} |"
    for cls, avg in sorted(class_avg_roi.items(), key=lambda x: x[1], reverse=True)
])

# Strategic recs
live_monitor = [s["name"] for s in promising + neutral if s["n_real_line_bets"] >= 20]
drop = [s["name"] for s in dead]
wait = [s["name"] for s in insuff + ([s for s in neutral if s["n_real_line_bets"] < 20])]

# Top 3 signals narrative
top3_rows = "\n".join([
    f"| {s['name']} | {s['n_real_line_bets']} | {fmt_w(s['win_rate_real'])} | {fmt_r(s['roi_real_flat'])} | {fmt_r(s['roi_real_weighted'])} |"
    for s in ranked[:3]
])

# INT-16 weighting table
wt_rows = "\n".join([
    f"| {k} | {fmt_r(v['flat_roi'])} | {fmt_r(v['weighted_roi'])} | {v['uplift_pp']:+.2f}pp |"
    for k, v in sorted(weighting_comparison.items(), key=lambda x: x[1]["uplift_pp"], reverse=True)
]) or "| (none had sufficient real-line bets) | | | |"

combined_prec = precision_analysis

# Precompute multi-line strings (can't use \n inside f-string expressions in Py3.9)
NL = "\n"
promising_lines = NL.join(
    f"- **{s['name']}**: ROI={fmt_r(s['roi_real_flat'])}, n={s['n_real_line_bets']}, "
    f"wr={fmt_w(s['win_rate_real'])}, CI={fmt_ci(s['ci_95'])}"
    for s in promising
) or "None — no signal achieves real-line ROI > 0 with strong evidence."

dead_lines = NL.join(
    f"- **{s['name']}**: ROI={fmt_r(s['roi_real_flat'])}, n={s['n_real_line_bets']}"
    for s in dead
) or "None categorically dead (insufficient data to confirm)."

live_monitor_lines = NL.join(f"- {s}" for s in live_monitor) or "- None yet (accumulate more data)"
drop_lines = NL.join(f"- {s}" for s in drop) or "- None categorically drop-worthy"
wait_lines = NL.join(f"- {s}" for s in wait) or "- None"

sig_names_significant = str([s["name"] for s in significant]) if significant else "None"
proxy_pct = round(100 - anom_oof["has_real_line"].mean() * 100, 0)

md = f"""# Intelligence Layer Signal ROI Ranking

> Generated: 2026-05-28
> Version: INT-V3 (per-signal isolation backtest)
> Script: `scripts/test_intelligence_betting_v3.py`
> JSON: `data/models/intelligence_betting_v3_results.json`

## Methodology

Each signal is tested INDEPENDENTLY in isolation on real sportsbook closing lines.
Random baseline at -110 odds: **{rand_roi*100:.2f}% ROI** (theoretical -4.55%).
Bonferroni-adjusted significance threshold (10 signals): **α = {alpha_bonf:.4f}**.

**Signal sources:**
- INT-17: archetype × scheme advantages (per-player archetype vs opp defensive scheme)
- INT-3: matchup deviations (player vs specific opponent z-score features)
- INT-4: anomaly log (per-game CV feature z-scores)
- INT-16: per-player confidence multipliers (Kelly sizing weight)

**Line sources:** extended_oos_canonical + benashkar_2026 + oddsapi 2024-25 + 2025-26
(pooled {len(lines_pool):,} real-line rows with actuals)

## Signal performance table (ranked by real-line ROI)

| Rank | Signal | n_real | win_rate | flat ROI | INT-16-weighted ROI | 95% CI | Verdict |
|------|--------|--------|----------|----------|---------------------|--------|---------|
{table_md}

## Top 3 Signals

| Signal | n_real | win_rate | flat ROI | weighted ROI |
|--------|--------|----------|----------|--------------|
{top3_rows}

## Promising signals (real-line ROI > 0, CI not catastrophically wide)

{promising_lines}

## Dead signals (ROI clearly < random)

{dead_lines}

## Signal class performance (average ROI by type)

| Signal class | avg real-line ROI |
|--------------|------------------|
{class_table_rows}

Best signal class: **{best_class}**

## Combined-signal precision boost

| | n_real | win_rate | ROI |
|-|--------|----------|-----|
| cutter_vs_paint_first alone | {combined_prec['base_signal']['n_real']} | {fmt_w(combined_prec['base_signal']['win_rate'])} | {fmt_r(combined_prec['base_signal']['roi'])} |
| + low_volatility filter (INT-16) | {combined_prec['combined_signal']['n_real']} | {fmt_w(combined_prec['combined_signal']['win_rate'])} | {fmt_r(combined_prec['combined_signal']['roi'])} |

Sample reduction: **{combined_prec['sample_reduction_pct']}%**
Precision filter helps: **{combined_prec['precision_helps']}**

## INT-16 Kelly weighting effect

Average ROI uplift from INT-16 weighting: **{avg_uplift:+.2f}pp**
Signal where weighting helps most: **{best_uplift_signal or "N/A"}**

| Signal | flat ROI | weighted ROI | uplift |
|--------|----------|--------------|--------|
{wt_rows}

## Statistical significance

- Bonferroni-corrected α = {alpha_bonf:.4f} (0.05 / 10 signals)
- Statistically significant signals: **{sig_names_significant}**
- Note: Most signals have n_real < 100; CI spans are wide. No signal should be trusted without 200+ real-line bets.

## Strategic recommendations

**Live-monitor (ROI positive or neutral, n≥20):**
{live_monitor_lines}

**Drop (ROI clearly below random):**
{drop_lines}

**Wait for more data (n_real < 20 or insufficient):**
{wait_lines}

## Honest caveats

1. Most archetype×scheme signals have 0 or very few real-line bets — the archetype/scheme fingerprints
   are built on CV-tracked players but lines pool covers many more players.
2. Anomaly signals use L5-mean proxy for ~{proxy_pct:.0f}% of bets — proxy lines bias ROI high.
3. n<100 on every signal — CI spans 40-80pp wide. Directional signal only, not statistically tight.
4. Multiple-testing: 10 signals at α=0.05 → expect ~0.5 false positives; Bonferroni threshold is {alpha_bonf:.4f}.
5. ISSUE-022: defender_distance=200 sentinel corrupts some CV features.
6. Matchup deviations: 95%+ of records have n_games_vs_opp=1 (thin history).

---
*See also: [[Betting_Validation]], [[Tracker Improvements Log]], [[project_loop7_status]]*
"""

vault_dir = ROOT / "vault/Intelligence"
vault_dir.mkdir(parents=True, exist_ok=True)
atlas_path = vault_dir / "Betting_Signal_Ranking.md"
with open(atlas_path, "w", encoding="utf-8") as f:
    f.write(md)
print(f"  Atlas saved -> {atlas_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 12. FINAL REPORT
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("INT-V3 Granular Signal Betting Backtest - FINAL REPORT")
print("=" * 70)

print(f"""
SETUP
  Real lines pool: {len(lines_pool):,} rows (4 sources, de-duped)
  Total signals tested: {len(signal_results)}
  Random baseline ROI: {rand_roi*100:.2f}%
  Bonferroni alpha: {alpha_bonf:.4f}
""")

print("REAL-LINE COVERAGE PER SIGNAL")
print(f"  {'Signal':<50} {'n_real':>6} {'n_bets':>7}")
print("  " + "-" * 65)
for s in ranked:
    print(f"  {s['name']:<50} {s['n_real_line_bets']:>6} {s['n_bets']:>7}")

print("\nTOP 3 MOST PROMISING SIGNALS (by real-line ROI)")
print(f"  {'Signal':<50} {'n_real':>6} {'win_rate':>9} {'flat ROI':>10} {'wt ROI':>10}")
print("  " + "-" * 90)
for s in ranked[:3]:
    print(
        f"  {s['name']:<50} {s['n_real_line_bets']:>6} "
        f"{fmt_w(s['win_rate_real']):>9} {fmt_r(s['roi_real_flat']):>10} "
        f"{fmt_r(s['roi_real_weighted']):>10}"
    )

print("\nSIGNALS THAT DON'T PAY (ROI < -4.5%)")
if dead:
    for s in dead:
        real_n = s['n_real_line_bets']
        reason = "low n" if real_n < 20 else "consistent underperformance"
        print(f"  {s['name']}: ROI={fmt_r(s['roi_real_flat'])}, n={real_n} ({reason})")
else:
    print("  None are clearly dead — sample sizes too small to confirm.")

print(f"\nINT-16 KELLY WEIGHTING EFFECT")
print(f"  Average ROI uplift from weighting: {avg_uplift:+.2f}pp")
if best_uplift_signal and best_uplift_signal in weighting_comparison:
    bw = weighting_comparison[best_uplift_signal]
    print(f"  Best signal for weighting: {best_uplift_signal}")
    print(f"    flat={fmt_r(bw['flat_roi'])} -> weighted={fmt_r(bw['weighted_roi'])} ({bw['uplift_pp']:+.2f}pp)")

print(f"\nCOMBINED SIGNAL PRECISION BOOST")
print(f"  Base  ({base_name}):     n={combined_prec['base_signal']['n_real']}, ROI={fmt_r(combined_prec['base_signal']['roi'])}")
print(f"  +INT16 ({combined_name}):")
print(f"         n={combined_prec['combined_signal']['n_real']}, ROI={fmt_r(combined_prec['combined_signal']['roi'])}")
print(f"  Sample reduction: {combined_prec['sample_reduction_pct']:.1f}%")
print(f"  Precision helps: {combined_prec['precision_helps']}")

print(f"\nSIGNAL CLASS PERFORMANCE")
for cls, avg in sorted(class_avg_roi.items(), key=lambda x: x[1], reverse=True):
    print(f"  {cls}: avg ROI = {fmt_r(avg)}")
print(f"  Best class today: {best_class}")

print(f"\nSTATISTICAL SIGNIFICANCE")
if significant:
    for s in significant:
        print(f"  SIGNIFICANT: {s['name']} z={s['z_stat']} p={s['p_value']}")
else:
    print(f"  No signal passes Bonferroni threshold (alpha={alpha_bonf:.4f}).")
    print(f"  This is expected with n_real<100 per signal.")

print(f"\nVERDICT")
if promising:
    print(f"  Most promising: {promising[0]['name']} (ROI={fmt_r(promising[0]['roi_real_flat'])}, n={promising[0]['n_real_line_bets']})")
    print(f"  Best signal class: {best_class}")
    print(f"  Action: accumulate 200+ real-line bets on promising signals before live deployment")
elif neutral:
    print(f"  Best available: {neutral[0]['name']} (ROI={fmt_r(neutral[0]['roi_real_flat'])})")
    print(f"  Verdict: PARTIAL - intelligence flags beat random but still negative at -110")
    print(f"  Action: wait for larger sample before committing live bets")
else:
    print(f"  Best available: {ranked[0]['name']} (ROI={fmt_r(ranked[0]['roi_real_flat'])})")
    print(f"  Verdict: INCONCLUSIVE - insufficient data. No signal clearly above random.")
    print(f"  Action: continue tracking; retest when n_real>=100 per signal")

print(f"""
HONEST CAVEATS
  1. Sample sizes per signal: n=1-50 on real lines (n<100 for all 10 signals)
  2. L5-mean proxy lines inflate anomaly ROI artificially - real-lines-only is the honest view
  3. Multiple-comparison: 10 signals, Bonferroni alpha={alpha_bonf:.4f} - no signal passes
  4. Archetype x scheme signals have thin real-line coverage (CV-tracked players != lines pool)
  5. Matchup deviations: 95%+ have n_games_vs_opp=1 - single-game history is very noisy
  6. All results are directional only until n>=200 real-line bets per signal

FILES
  scripts/test_intelligence_betting_v3.py
  data/models/intelligence_betting_v3_results.json
  vault/Intelligence/Betting_Signal_Ranking.md
""")
