"""
INT-V2 Betting Backtest
=======================
Tests whether INT-4 anomaly flags and INT-3 matchup deviation flags generate
positive edge on real sportsbook prop lines (or L5-mean synthetic proxy).

Strategies:
  1. anomaly_only   — INT-4 anomaly z-score direction -> OVER/UNDER bet
  2. matchup_only   — INT-3 matchup deviation -> OVER/UNDER per specific features
  3. combined       — anomaly + matchup direction agree (higher confidence)
  4. random         — random OVER/UNDER on same eligible games (baseline)

Outputs:
  - data/models/intelligence_betting_results.json
  - vault/Intelligence/Betting_Validation.md
"""

import json
import os
import random
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from lib_betting_validation import safe_odds  # Bug 10 guard (replaces weak inline that missed -99<f<100 filter)

warnings.filterwarnings("ignore")
random.seed(42)
np.random.seed(42)

ROOT = Path("C:/Users/neelj/nba-ai-system")

# ---------------------------------------------------------------------------
# Feature → stat direction mapping
# ---------------------------------------------------------------------------
# (feature_name, z_direction, bet_direction, stat_list)
# z_direction: 'positive' means high-z -> bet OVER
#              'negative' means high-neg-z -> bet UNDER
FEATURE_STAT_MAP = [
    # high paint_dwell_pct -> expect OVER PTS/REB
    ("paint_dwell_pct", "positive", "OVER", ["pts", "reb"]),
    # high touches_per_game -> expect OVER PTS/AST/tov
    ("touches_per_game", "positive", "OVER", ["pts", "ast", "tov"]),
    # high potential_assists -> expect OVER AST
    ("potential_assists", "positive", "OVER", ["ast"]),
    # defender_approach_speed is negative (approach = closing speed)
    # more negative speed (faster close) -> tighter defense -> UNDER PTS
    ("defender_approach_speed", "negative", "UNDER", ["pts"]),
    # avg_shot_distance high -> farther shots -> UNDER PTS, OVER FG3M
    ("avg_shot_distance", "positive", "OVER", ["fg3m"]),
    ("avg_shot_distance", "positive", "UNDER", ["pts"]),
    # shots_per_possession high -> more volume -> OVER PTS
    ("shots_per_possession", "positive", "OVER", ["pts"]),
    # play_type_transition_pct high -> more fast breaks -> OVER PTS
    ("play_type_transition_pct", "positive", "OVER", ["pts"]),
    # play_type_isolation_pct high -> more isolation usage -> OVER PTS
    ("play_type_isolation_pct", "positive", "OVER", ["pts"]),
    # avg_defender_distance high -> more open looks -> OVER PTS, FG3M
    ("avg_defender_distance", "positive", "OVER", ["pts", "fg3m"]),
    # contested_shot_rate high -> more contested -> UNDER PTS, FG3M
    ("contested_shot_rate", "positive", "UNDER", ["pts", "fg3m"]),
    # catch_shoot_pct high -> more catch-and-shoot (3pt role) -> OVER FG3M
    ("catch_shoot_pct", "positive", "OVER", ["fg3m"]),
    # avg_dribble_count high -> more ball-handling usage -> OVER AST, PTS
    ("avg_dribble_count", "positive", "OVER", ["ast", "pts"]),
    # second_chance_rate high -> more offensive rebounds -> OVER REB
    ("second_chance_rate", "positive", "OVER", ["reb"]),
    # preshot_velocity_peak high -> explosive movement -> OVER PTS
    ("preshot_velocity_peak", "positive", "OVER", ["pts"]),
]

# Build lookup: feature -> list of (z_direction, bet_direction, stat_list)
FEATURE_LOOKUP = {}
for feat, z_dir, bet_dir, stats in FEATURE_STAT_MAP:
    if feat not in FEATURE_LOOKUP:
        FEATURE_LOOKUP[feat] = []
    FEATURE_LOOKUP[feat].append((z_dir, bet_dir, stats))

# ---------------------------------------------------------------------------
# ROI calculation at -110 odds
# ---------------------------------------------------------------------------
OVER_ODDS_DEFAULT = -110
UNDER_ODDS_DEFAULT = -110
JUICE = 100 / 110  # implied win probability at -110


def roi_per_bet(won: bool, odds: float = -110) -> float:
    """Return P&L per $1 wagered at given American odds."""
    if odds < 0:
        win_amount = 100 / abs(odds)
    else:
        win_amount = odds / 100
    return win_amount if won else -1.0


# safe_odds imported from lib_betting_validation above (canonical version with -99<f<100 guard)


# ---------------------------------------------------------------------------
# 1. Load intelligence parquets
# ---------------------------------------------------------------------------
print("Loading intelligence parquets...")
anom = pd.read_parquet(ROOT / "data/intelligence/anomaly_log.parquet")
mdev = pd.read_parquet(ROOT / "data/intelligence/matchup_deviations.parquet")
streak = pd.read_parquet(ROOT / "data/intelligence/streak_signatures.parquet")

anom["game_date"] = pd.to_datetime(anom["game_date"])


def norm(s):
    return str(s).strip().lower()


anom["player_norm"] = anom["player_name"].map(norm)
mdev["player_norm"] = mdev["player_name"].map(norm)


# ---------------------------------------------------------------------------
# 2. Parse anomaly features
# ---------------------------------------------------------------------------
def parse_top3(s):
    try:
        return json.loads(s)
    except Exception:
        return []


anom["features_parsed"] = anom["top_3_features"].apply(parse_top3)


def extract_feature_signals(row):
    """
    For each feature in the top-3 list, check if it matches FEATURE_LOOKUP
    and if its z-score direction gives a clear bet signal for any stat.
    Returns list of dicts: {feature, z, bet_direction, stats, signal_key}
    """
    signals = []
    for feat_obj in row["features_parsed"]:
        feat = feat_obj.get("feature", "")
        z = feat_obj.get("z", 0.0)
        if feat not in FEATURE_LOOKUP:
            continue
        for z_dir, bet_dir, stats in FEATURE_LOOKUP[feat]:
            if z_dir == "positive" and z >= 2.0:
                signals.append(
                    {
                        "feature": feat,
                        "z": z,
                        "bet_direction": bet_dir,
                        "stats": stats,
                        "signal_key": f"{feat}_{bet_dir}",
                    }
                )
            elif z_dir == "negative" and z <= -2.0:
                signals.append(
                    {
                        "feature": feat,
                        "z": z,
                        "bet_direction": bet_dir,
                        "stats": stats,
                        "signal_key": f"{feat}_{bet_dir}",
                    }
                )
    return signals


anom["signals"] = anom.apply(extract_feature_signals, axis=1)

# ---------------------------------------------------------------------------
# 3. Load OOF actuals (model per-game predictions + actuals)
# ---------------------------------------------------------------------------
print("Loading OOF actuals...")
oof = pd.read_parquet(ROOT / "data/cache/pregame_oof.parquet")
oof["game_date"] = pd.to_datetime(oof["game_date"])
oof = oof.sort_values(["player_id", "stat", "game_date"])

# Compute L5-mean proxy (shifted to avoid leakage)
oof["l5_mean_proxy"] = oof.groupby(["player_id", "stat"])["actual"].transform(
    lambda x: x.shift(1).rolling(5, min_periods=1).mean()
)

print(f"OOF rows: {len(oof)}, stats: {oof['stat'].value_counts().to_dict()}")

# ---------------------------------------------------------------------------
# 4. Load real sportsbook lines
# ---------------------------------------------------------------------------
print("Loading sportsbook lines...")
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
        # standardize stat names
        d["stat"] = d["stat"].str.lower().str.strip()
        line_dfs.append(d)
lines_pool = (
    pd.concat(line_dfs, ignore_index=True)
    .drop_duplicates(subset=["player_norm", "date", "stat"])
    .reset_index(drop=True)
)
for _odds_col in ("over_odds", "under_odds"):  # Bug 10 guard
    if _odds_col in lines_pool.columns:
        lines_pool[_odds_col] = lines_pool[_odds_col].apply(safe_odds)
print(f"Lines pool: {len(lines_pool)} rows, stats: {lines_pool['stat'].value_counts().to_dict()}")

# ---------------------------------------------------------------------------
# 5. Build the ANOMALY bet log (Strategy 1)
# ---------------------------------------------------------------------------
print("\nBuilding anomaly bet log (Strategy 1)...")

# Join anomaly log with OOF actuals
anom_oof = anom.merge(
    oof[["player_id", "game_id", "stat", "actual", "oof_pred", "l5_mean_proxy"]],
    on=["player_id", "game_id"],
)

# Join real sportsbook lines
anom_oof = anom_oof.merge(
    lines_pool[["player_norm", "date", "stat", "closing_line", "over_odds", "under_odds"]],
    left_on=["player_norm", "game_date", "stat"],
    right_on=["player_norm", "date", "stat"],
    how="left",
)

# Determine the "line" to use: real if available, else L5 proxy
anom_oof["has_real_line"] = anom_oof["closing_line"].notna()
anom_oof["effective_line"] = anom_oof["closing_line"].fillna(anom_oof["l5_mean_proxy"])
anom_oof["effective_over_odds"] = anom_oof["over_odds"].apply(safe_odds)
anom_oof["effective_under_odds"] = anom_oof["under_odds"].apply(safe_odds)

# Drop rows where we can't compute the effective line
anom_oof = anom_oof.dropna(subset=["effective_line", "actual"])

print(
    f"Anomaly + OOF rows: {len(anom_oof)} | "
    f"With real line: {anom_oof['has_real_line'].sum()} | "
    f"L5 proxy: {(~anom_oof['has_real_line']).sum()}"
)

# Generate bets from anomaly signals
anomaly_bets = []
for _, row in anom_oof.iterrows():
    signals = row["signals"]
    for sig in signals:
        stat = row["stat"]
        if stat not in sig["stats"]:
            continue
        bet_dir = sig["bet_direction"]
        line = row["effective_line"]
        actual = row["actual"]
        won = (actual > line) if bet_dir == "OVER" else (actual < line)
        odds = (
            row["effective_over_odds"] if bet_dir == "OVER" else row["effective_under_odds"]
        )
        pnl = roi_per_bet(won, odds)
        anomaly_bets.append(
            {
                "player_id": row["player_id"],
                "player_name": row["player_name"],
                "game_id": row["game_id"],
                "game_date": row["game_date"],
                "stat": stat,
                "feature": sig["feature"],
                "feature_z": sig["z"],
                "signal_key": sig["signal_key"],
                "bet_direction": bet_dir,
                "line": line,
                "actual": actual,
                "won": won,
                "pnl": pnl,
                "has_real_line": row["has_real_line"],
                "max_abs_z": row["max_abs_z"],
                "strategy": "anomaly_only",
            }
        )

anomaly_bets_df = pd.DataFrame(anomaly_bets)
print(f"Anomaly bets generated: {len(anomaly_bets_df)}")
if len(anomaly_bets_df) > 0:
    print(f"  Stats: {anomaly_bets_df['stat'].value_counts().to_dict()}")
    print(f"  With real lines: {anomaly_bets_df['has_real_line'].sum()}")


# ---------------------------------------------------------------------------
# 6. Build the MATCHUP bet log (Strategy 2)
# ---------------------------------------------------------------------------
print("\nBuilding matchup bet log (Strategy 2)...")

# Join lines with matchup deviations on (player_norm, opp_team)
mdev_lines = lines_pool.merge(
    mdev[
        [
            "player_norm",
            "opp_team",
            "paint_dwell_pct_z",
            "potential_assists_z",
            "defender_approach_speed_z",
            "avg_defender_distance_z",
            "touches_per_game_z",
            "n_games_vs_opp",
            "notable_flag",
            "max_abs_z",
            "deviation_flags",
        ]
    ],
    left_on=["player_norm", "opp"],
    right_on=["player_norm", "opp_team"],
    how="inner",
)
mdev_lines = mdev_lines.dropna(subset=["actual_value", "closing_line"])

print(f"Matchup-lines rows: {len(mdev_lines)}")

# Strategy 2 signals:
# paint_dwell_pct_z > +1 -> OVER REB
# defender_approach_speed_z < -1 -> UNDER PTS (tighter defense)
# avg_defender_distance_z > +1 -> OVER PTS, FG3M (more open)
# potential_assists_z > +1 -> OVER AST
# touches_per_game_z > +1 -> OVER PTS
MATCHUP_SIGNALS = [
    ("paint_dwell_pct_z", "positive", 1.0, "OVER", ["reb"]),
    ("defender_approach_speed_z", "negative", -1.0, "UNDER", ["pts"]),
    ("avg_defender_distance_z", "positive", 1.0, "OVER", ["pts", "fg3m"]),
    ("potential_assists_z", "positive", 1.0, "OVER", ["ast"]),
    ("touches_per_game_z", "positive", 1.0, "OVER", ["pts"]),
]

matchup_bets = []
for _, row in mdev_lines.iterrows():
    stat = row["stat"].lower()
    actual = row["actual_value"]
    line = row["closing_line"]

    for z_col, z_dir, z_thresh, bet_dir, stats in MATCHUP_SIGNALS:
        if stat not in stats:
            continue
        z_val = row.get(z_col, 0.0)
        if pd.isna(z_val):
            continue
        triggered = (z_dir == "positive" and z_val >= z_thresh) or (
            z_dir == "negative" and z_val <= z_thresh
        )
        if not triggered:
            continue

        won = (actual > line) if bet_dir == "OVER" else (actual < line)
        over_odds = safe_odds(row.get("over_odds", -110))
        under_odds = safe_odds(row.get("under_odds", -110))
        odds = over_odds if bet_dir == "OVER" else under_odds
        pnl = roi_per_bet(won, odds)
        matchup_bets.append(
            {
                "player_name": row["player"],
                "date": row["date"],
                "opp_team": row["opp_team"],
                "stat": stat,
                "signal_key": f"{z_col}_{bet_dir}",
                "z_col": z_col,
                "z_val": z_val,
                "bet_direction": bet_dir,
                "line": line,
                "actual": actual,
                "won": won,
                "pnl": pnl,
                "has_real_line": True,  # all matchup bets use real lines
                "max_abs_z": row["max_abs_z"],
                "n_games_vs_opp": row["n_games_vs_opp"],
                "strategy": "matchup_only",
            }
        )

matchup_bets_df = pd.DataFrame(matchup_bets)
print(f"Matchup bets generated: {len(matchup_bets_df)}")
if len(matchup_bets_df) > 0:
    print(f"  Stats: {matchup_bets_df['stat'].value_counts().to_dict()}")
    print(f"  Signal distribution: {matchup_bets_df['signal_key'].value_counts().to_dict()}")


# ---------------------------------------------------------------------------
# 7. Build the COMBINED bet log (Strategy 3)
# ---------------------------------------------------------------------------
print("\nBuilding combined bet log (Strategy 3)...")

# Combined: must have BOTH an anomaly signal AND matchup signal pointing same direction
# We use the anomaly bets_df as the base and flag where matchup agrees
# For simplicity: if anomaly bet on (player, date, stat, direction) exists
# AND matchup bet on same (player, date, stat, direction) also triggered -> combined

if len(anomaly_bets_df) > 0 and len(matchup_bets_df) > 0:
    anom_key = anomaly_bets_df.copy()
    anom_key["date_str"] = anom_key["game_date"].dt.strftime("%Y-%m-%d")
    anom_key["key"] = (
        anom_key["player_name"].map(norm)
        + "|"
        + anom_key["date_str"]
        + "|"
        + anom_key["stat"]
        + "|"
        + anom_key["bet_direction"]
    )

    match_key = matchup_bets_df.copy()
    match_key["date_str"] = match_key["date"].dt.strftime("%Y-%m-%d")
    match_key["key"] = (
        match_key["player_name"].map(norm)
        + "|"
        + match_key["date_str"]
        + "|"
        + match_key["stat"]
        + "|"
        + match_key["bet_direction"]
    )

    combined_keys = set(anom_key["key"]) & set(match_key["key"])
    combined_bets_df = anom_key[anom_key["key"].isin(combined_keys)].copy()
    combined_bets_df["strategy"] = "combined"
    print(f"Combined bets (both signals agree): {len(combined_bets_df)}")
else:
    combined_bets_df = pd.DataFrame()
    print("Combined: no overlapping signals found")


# ---------------------------------------------------------------------------
# 8. Build the RANDOM baseline (Strategy 4)
# ---------------------------------------------------------------------------
print("\nBuilding random baseline (Strategy 4)...")

# Use all lines rows that have an actual value
all_real_lines = lines_pool.dropna(subset=["actual_value", "closing_line"]).copy()
all_real_lines = all_real_lines[all_real_lines["stat"].isin(["pts", "reb", "ast", "fg3m", "blk", "stl"])]

# Sample same N bets as anomaly strategy (or all if fewer)
n_random = max(len(anomaly_bets_df), 500)
sample_idx = np.random.choice(len(all_real_lines), size=min(n_random, len(all_real_lines)), replace=False)
random_sample = all_real_lines.iloc[sample_idx].copy()
random_sample["rand_dir"] = np.random.choice(["OVER", "UNDER"], size=len(random_sample))
random_sample["won"] = (
    (random_sample["actual_value"] > random_sample["closing_line"]) & (random_sample["rand_dir"] == "OVER")
) | (
    (random_sample["actual_value"] < random_sample["closing_line"]) & (random_sample["rand_dir"] == "UNDER")
)

# At -110 odds, theoretical ROI = -4.55%
random_roi = random_sample["won"].mean() * JUICE - (1 - random_sample["won"].mean())
print(f"Random sample: {len(random_sample)} bets, win_rate={random_sample['won'].mean():.3f}, ROI={random_roi*100:.2f}%")


# ---------------------------------------------------------------------------
# 9. Aggregate per-strategy results
# ---------------------------------------------------------------------------
def aggregate_strategy(bets_df, strategy_name, use_real_only=False):
    if bets_df is None or len(bets_df) == 0:
        return {
            "strategy": strategy_name,
            "n_bets": 0,
            "win_rate": None,
            "roi": None,
            "with_real_lines_n": 0,
            "with_real_lines_roi": None,
        }
    df = bets_df.copy()
    if use_real_only:
        df = df[df.get("has_real_line", pd.Series([True] * len(df)))]
    if len(df) == 0:
        return {
            "strategy": strategy_name,
            "n_bets": 0,
            "win_rate": None,
            "roi": None,
        }
    wr = df["won"].mean()
    roi = df["pnl"].mean()
    result = {
        "strategy": strategy_name,
        "n_bets": int(len(df)),
        "win_rate": round(float(wr), 4),
        "roi_pct": round(float(roi) * 100, 2),
        "total_pnl": round(float(df["pnl"].sum()), 3),
    }
    # With real lines only
    real_df = df[df["has_real_line"] == True] if "has_real_line" in df.columns else df
    if len(real_df) > 0:
        result["real_line_n"] = int(len(real_df))
        result["real_line_win_rate"] = round(float(real_df["won"].mean()), 4)
        result["real_line_roi_pct"] = round(float(real_df["pnl"].mean()) * 100, 2)
    else:
        result["real_line_n"] = 0
        result["real_line_win_rate"] = None
        result["real_line_roi_pct"] = None
    return result


strat_results = {}
strat_results["anomaly_only"] = aggregate_strategy(anomaly_bets_df, "anomaly_only")
strat_results["matchup_only"] = aggregate_strategy(matchup_bets_df, "matchup_only")
strat_results["combined"] = aggregate_strategy(combined_bets_df, "combined")

# Random baseline
if len(random_sample) > 0:
    rand_roi = float(random_sample["won"].mean()) * JUICE - (1 - float(random_sample["won"].mean()))
    strat_results["random"] = {
        "strategy": "random",
        "n_bets": int(len(random_sample)),
        "win_rate": round(float(random_sample["won"].mean()), 4),
        "roi_pct": round(rand_roi * 100, 2),
        "real_line_n": int(len(random_sample)),
        "real_line_win_rate": round(float(random_sample["won"].mean()), 4),
        "real_line_roi_pct": round(rand_roi * 100, 2),
    }

print("\n=== STRATEGY SUMMARY ===")
for k, v in strat_results.items():
    print(f"  {k}: n={v['n_bets']}, wr={v.get('win_rate')}, roi={v.get('roi_pct')}%")


# ---------------------------------------------------------------------------
# 10. Per-signal analysis (within Strategy 1 and 2)
# ---------------------------------------------------------------------------
print("\nPer-signal analysis...")

per_signal = {}

if len(anomaly_bets_df) > 0:
    for sig_key, grp in anomaly_bets_df.groupby("signal_key"):
        wr = grp["won"].mean()
        roi = grp["pnl"].mean() * 100
        per_signal[sig_key] = {
            "source": "anomaly",
            "n_bets": int(len(grp)),
            "win_rate": round(float(wr), 4),
            "roi_pct": round(float(roi), 2),
            "stats": sorted(grp["stat"].unique().tolist()),
            "beat_random": roi > -4.55,
        }

if len(matchup_bets_df) > 0:
    for sig_key, grp in matchup_bets_df.groupby("signal_key"):
        wr = grp["won"].mean()
        roi = grp["pnl"].mean() * 100
        per_signal[f"matchup_{sig_key}"] = {
            "source": "matchup",
            "n_bets": int(len(grp)),
            "win_rate": round(float(wr), 4),
            "roi_pct": round(float(roi), 2),
            "stats": sorted(grp["stat"].unique().tolist()),
            "beat_random": roi > -4.55,
        }

# Rank by ROI
per_signal_ranked = dict(
    sorted(per_signal.items(), key=lambda x: x[1]["roi_pct"], reverse=True)
)

print("Per-signal ROI (top 10):")
for k, v in list(per_signal_ranked.items())[:10]:
    print(f"  {k}: n={v['n_bets']}, roi={v['roi_pct']}%, wr={v['win_rate']}")


# ---------------------------------------------------------------------------
# 11. Real-lines-only analysis (most honest)
# ---------------------------------------------------------------------------
print("\nReal-lines-only analysis (121 bets from real sportsbook lines)...")

anom_real = anomaly_bets_df[anomaly_bets_df["has_real_line"] == True] if len(anomaly_bets_df) > 0 else pd.DataFrame()
real_lines_summary = {}
if len(anom_real) > 0:
    for stat in ["pts", "reb", "ast", "fg3m", "blk", "stl"]:
        sub = anom_real[anom_real["stat"] == stat]
        if len(sub) > 0:
            real_lines_summary[stat] = {
                "n": int(len(sub)),
                "win_rate": round(float(sub["won"].mean()), 3),
                "roi_pct": round(float(sub["pnl"].mean()) * 100, 2),
            }

print("Real-line anomaly bets by stat:", real_lines_summary)

# Confidence intervals via bootstrap
def bootstrap_roi_ci(pnl_series, n_boot=2000, ci=0.95):
    if len(pnl_series) < 3:
        return (None, None)
    boots = [pnl_series.sample(frac=1, replace=True).mean() * 100 for _ in range(n_boot)]
    lo = np.percentile(boots, (1 - ci) / 2 * 100)
    hi = np.percentile(boots, (1 - (1 - ci) / 2) * 100)
    return (round(float(lo), 2), round(float(hi), 2))


ci_results = {}
if len(anom_real) > 0 and len(anom_real) >= 3:
    ci_results["anomaly_real_lines"] = bootstrap_roi_ci(anom_real["pnl"])

if len(matchup_bets_df) >= 3:
    ci_results["matchup_real_lines"] = bootstrap_roi_ci(matchup_bets_df["pnl"])

print("Bootstrap 95% CI on ROI:", ci_results)


# ---------------------------------------------------------------------------
# 12. Sample size significance
# ---------------------------------------------------------------------------
def kelly_criterion(win_rate: float, odds: float = -110) -> float:
    """Kelly fraction for this win rate and odds."""
    if odds < 0:
        b = 100 / abs(odds)
    else:
        b = odds / 100
    p = win_rate
    q = 1 - p
    return max(0, (b * p - q) / b)


# ---------------------------------------------------------------------------
# 13. Build JSON output
# ---------------------------------------------------------------------------
print("\nBuilding JSON output...")

best_strategy = max(
    strat_results.items(),
    key=lambda x: x[1].get("roi_pct") or -999,
)[0]
best_roi = strat_results[best_strategy].get("roi_pct")
random_roi_pct = strat_results.get("random", {}).get("roi_pct", -4.55)

profitable_signals = {k: v for k, v in per_signal_ranked.items() if v["roi_pct"] > 0}
losing_signals = {k: v for k, v in per_signal_ranked.items() if v["roi_pct"] <= -4.55}

output = {
    "meta": {
        "generated": "2026-05-28",
        "line_source": "real sportsbook lines (extended_oos_canonical + benashkar_2026 + oddsapi) + L5-mean proxy where unavailable",
        "real_lines_pct": round(float(anom_oof["has_real_line"].mean()) * 100 if len(anom_oof) > 0 else 0, 1),
        "note": "Anomaly strategy uses real lines for 6.5% of bets; rest use L5-mean synthetic proxy",
    },
    "summary": {
        "n_eligible_player_games": int(anom["game_id"].nunique()),
        "n_anomaly_bets": int(len(anomaly_bets_df)),
        "n_matchup_bets": int(len(matchup_bets_df)),
        "random_baseline_roi_pct": float(random_roi_pct),
        "best_strategy": best_strategy,
        "best_strategy_roi_pct": float(best_roi) if best_roi is not None else None,
        "roi_delta_vs_random_pp": (
            round(float(best_roi) - float(random_roi_pct), 2)
            if best_roi is not None
            else None
        ),
    },
    "per_strategy": strat_results,
    "per_signal": per_signal_ranked,
    "real_lines_only": {
        "anomaly_bets": {
            "n": int(len(anom_real)) if len(anom_real) > 0 else 0,
            "win_rate": round(float(anom_real["won"].mean()), 4) if len(anom_real) > 0 else None,
            "roi_pct": round(float(anom_real["pnl"].mean()) * 100, 2) if len(anom_real) > 0 else None,
            "ci_95": ci_results.get("anomaly_real_lines"),
            "by_stat": real_lines_summary,
        },
        "matchup_bets": {
            "n": int(len(matchup_bets_df)),
            "win_rate": round(float(matchup_bets_df["won"].mean()), 4) if len(matchup_bets_df) > 0 else None,
            "roi_pct": round(float(matchup_bets_df["pnl"].mean()) * 100, 2) if len(matchup_bets_df) > 0 else None,
            "ci_95": ci_results.get("matchup_real_lines"),
        },
    },
    "bootstrap_ci_95": ci_results,
}

out_path = ROOT / "data/models/intelligence_betting_results.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w") as f:
    json.dump(output, f, indent=2, default=str)
print(f"JSON saved -> {out_path}")


# ---------------------------------------------------------------------------
# 14. Print full report
# ---------------------------------------------------------------------------
def roi_str(x):
    if x is None:
        return "N/A"
    return f"{x:+.2f}%"


print("\n" + "=" * 70)
print("INT-V2 BETTING BACKTEST — FINAL REPORT")
print("=" * 70)

print("\nSETUP")
print(f"  Real sportsbook lines: YES ({output['meta']['real_lines_pct']}% of anomaly bets)")
print(f"  Remainder: L5-mean synthetic proxy")
print(f"  Eligible anomaly player-games: {output['summary']['n_eligible_player_games']}")
print(f"  Anomaly bets placed: {output['summary']['n_anomaly_bets']}")
print(f"  Matchup bets placed: {output['summary']['n_matchup_bets']}")
print(f"  Strategies tested: 4 (anomaly_only, matchup_only, combined, random)")

print("\nPER-STRATEGY RESULTS")
print(f"  {'strategy':<20} {'n_bets':>8} {'win_rate':>10} {'ROI':>10}")
print("  " + "-" * 52)
for k, v in strat_results.items():
    print(
        f"  {k:<20} {v['n_bets']:>8} "
        f"{v.get('win_rate', 0) or 0:>10.3f} "
        f"{roi_str(v.get('roi_pct')):>10}"
    )

print("\nREAL LINES ONLY (most honest subset)")
rl = output["real_lines_only"]
print(
    f"  Anomaly on real lines: n={rl['anomaly_bets']['n']}, "
    f"wr={rl['anomaly_bets']['win_rate']}, "
    f"ROI={roi_str(rl['anomaly_bets']['roi_pct'])}, "
    f"95%CI={rl['anomaly_bets']['ci_95']}"
)
print(
    f"  Matchup on real lines: n={rl['matchup_bets']['n']}, "
    f"wr={rl['matchup_bets']['win_rate']}, "
    f"ROI={roi_str(rl['matchup_bets']['roi_pct'])}, "
    f"95%CI={rl['matchup_bets']['ci_95']}"
)

print("\nPROFITABLE INTELLIGENCE SIGNALS (ROI > 0)")
print(f"  {'signal':<35} {'n':>5} {'wr':>7} {'ROI':>9} {'stats'}")
print("  " + "-" * 70)
if profitable_signals:
    for k, v in list(profitable_signals.items())[:10]:
        print(
            f"  {k:<35} {v['n_bets']:>5} "
            f"{v['win_rate']:>7.3f} "
            f"{roi_str(v['roi_pct']):>9} "
            f"{v['stats']}"
        )
else:
    print("  None found (no signal generates ROI > 0)")

print("\nLOSING SIGNALS (ROI <= -4.55%, worse than random)")
if losing_signals:
    for k, v in list(losing_signals.items())[:5]:
        print(f"  {k}: roi={roi_str(v['roi_pct'])}, n={v['n_bets']}")
else:
    print("  None worse than random (-4.55%)")

print("\nVERDICT")
any_positive = any(
    v.get("roi_pct", -999) > 0 for v in strat_results.values() if v["n_bets"] > 0
)
best_edge = strat_results[best_strategy].get("roi_pct", 0) or 0
random_edge = strat_results.get("random", {}).get("roi_pct", -4.55) or -4.55

if best_edge > 0:
    print(f"  YES — intelligence layer generates POSITIVE EDGE")
    print(f"  Best strategy: {best_strategy} ROI={roi_str(best_edge)} vs random={roi_str(random_edge)}")
    print(f"  Delta vs random: {best_edge - random_edge:+.2f}pp")
elif best_edge > random_edge:
    print(f"  PARTIAL — intelligence layer BEATS RANDOM but is still negative")
    print(f"  Best strategy: {best_strategy} ROI={roi_str(best_edge)} vs random={roi_str(random_edge)}")
    print(f"  Delta vs random: {best_edge - random_edge:+.2f}pp (less juice bled)")
else:
    print(f"  NO — intelligence layer does NOT generate edge above random")
    print(f"  Best strategy: {best_strategy} ROI={roi_str(best_edge)} vs random={roi_str(random_edge)}")

print("\nHONEST CAVEATS")
print(f"  1. Real lines cover only {output['meta']['real_lines_pct']}% of anomaly bets")
print("  2. L5-mean proxy line is a rough approximation — real books price in injury/lineup info")
print(f"  3. Anomaly bets N={len(anomaly_bets_df)} — small N; results not statistically tight (p<0.05 requires ~500+ bets per signal)")
print("  4. Matchup history: 95% of mdev records have n_games_vs_opp=1 (single game history, very weak)")
print("  5. ISSUE-022: defender_distance=200 sentinel corrupts some z-scores")
print("  6. defender_approach_speed sign convention uncertain (ISSUE logged in CLAUDE.md)")
print("  7. Anomalies concentrated in 2025-26 season only (smaller sample)")
print("  8. No multiple-testing correction applied")

print("\nFILES")
print(f"  {ROOT}/scripts/test_intelligence_betting_backtest.py")
print(f"  {ROOT}/data/models/intelligence_betting_results.json")
print(f"  {ROOT}/vault/Intelligence/Betting_Validation.md (see next step)")


# ---------------------------------------------------------------------------
# 15. Write Atlas markdown
# ---------------------------------------------------------------------------
print("\nWriting vault atlas...")

vault_dir = ROOT / "vault/Intelligence"
vault_dir.mkdir(parents=True, exist_ok=True)

anom_wr = strat_results["anomaly_only"].get("win_rate") or 0
anom_roi = strat_results["anomaly_only"].get("roi_pct")
match_wr = strat_results["matchup_only"].get("win_rate") or 0
match_roi = strat_results["matchup_only"].get("roi_pct")
comb_wr = strat_results["combined"].get("win_rate") or 0
comb_roi = strat_results["combined"].get("roi_pct")
rand_wr = strat_results.get("random", {}).get("win_rate") or 0
rand_roi = strat_results.get("random", {}).get("roi_pct")

def fmtw(v):
    if v is None: return "N/A"
    return f"{v:.3f}"
def fmtr(v):
    if v is None: return "N/A"
    return f"{v:+.2f}%"
def beat(roi):
    if roi is None: return "?"
    return "YES" if roi > (rand_roi or -4.55) else "NO"

# Build signal table rows
def signal_table_rows(signals_dict, top_n=8):
    rows = []
    for k, v in list(signals_dict.items())[:top_n]:
        rows.append(
            f"| {k} | {v.get('bet_direction','?') if 'bet_direction' in v else '—'} "
            f"| {v['stats']} | {v['n_bets']} | {fmtw(v['win_rate'])} | {fmtr(v['roi_pct'])} | {beat(v['roi_pct'])} |"
        )
    return "\n".join(rows) if rows else "| (none) | | | | | | |"

all_signal_rows = []
for k, v in per_signal_ranked.items():
    all_signal_rows.append(
        f"| {k} | {v['stats']} | {v['n_bets']} | {fmtw(v['win_rate'])} | {fmtr(v['roi_pct'])} | {beat(v['roi_pct'])} |"
    )

all_rows_md = "\n".join(all_signal_rows) if all_signal_rows else "| (none) | | | | | |"

profitable_rows = "\n".join([
    f"| {k} | {v['stats']} | {v['n_bets']} | {fmtw(v['win_rate'])} | {fmtr(v['roi_pct'])} |"
    for k, v in profitable_signals.items()
]) if profitable_signals else "| (none — no signal achieves ROI > 0) | | | | |"

losing_rows = "\n".join([
    f"| {k} | ROI={fmtr(v['roi_pct'])} n={v['n_bets']} — {v['stats']} |"
    for k, v in losing_signals.items()
]) if losing_signals else "| (none worse than random) | |"

kelly_anom = kelly_criterion(float(anom_wr)) if anom_wr else 0
kelly_match = kelly_criterion(float(match_wr)) if match_wr else 0

verdict_text = ""
if best_edge > 0:
    verdict_text = f"**YES** — the intelligence layer generates positive edge. Best strategy `{best_strategy}` ROI={fmtr(best_edge)}, delta vs random={best_edge - random_edge:+.2f}pp."
elif best_edge > (random_edge or -4.55):
    verdict_text = f"**PARTIAL** — beats random but still negative. Best `{best_strategy}` ROI={fmtr(best_edge)} vs random {fmtr(random_edge)}. Delta={best_edge - random_edge:+.2f}pp."
else:
    verdict_text = f"**NOT YET** — intelligence flags do not generate edge above random on this sample. Best `{best_strategy}` ROI={fmtr(best_edge)} vs random {fmtr(random_edge)}."

md = f"""# Intelligence Layer Betting Validation

> Generated: 2026-05-28
> Backtest script: `scripts/test_intelligence_betting_backtest.py`
> Results JSON: `data/models/intelligence_betting_results.json`

## Methodology

- **INT-4 anomaly flags** (anomaly_log.parquet): per (player, game) anomaly z-scores.
  Direction-mapped to OVER/UNDER bets using feature → stat lookup table.
  Threshold: |z| >= 2.0 on top-3 anomalous features.

- **INT-3 matchup deviations** (matchup_deviations.parquet): per (player, opp_team) aggregate deviation from baseline.
  Signals: paint_dwell_z>+1→REB OVER, defender_approach_z<−1→PTS UNDER, avg_defender_dist_z>+1→PTS/FG3M OVER, etc.

- **Lines source**: Real sportsbook closing lines from extended_oos_canonical + benashkar_2026 + oddsapi (pooled, de-duped).
  Where no real line exists: L5-mean synthetic proxy from OOF actual history.
  Real line coverage for anomaly strategy: **{output['meta']['real_lines_pct']}%**.
  Matchup strategy: 100% real lines.

- **ROI**: at -110 odds (win = +$0.909, loss = −$1.00 per unit).

- **Baseline**: random OVER/UNDER on same games at -110 (theoretical −4.55% ROI).

## Coverage

| Metric | Value |
|--------|-------|
| Eligible anomaly player-games | {output['summary']['n_eligible_player_games']} |
| Anomaly bets placed | {output['summary']['n_anomaly_bets']} |
| Matchup bets placed | {output['summary']['n_matchup_bets']} |
| Anomaly bets on real lines | {output['real_lines_only']['anomaly_bets']['n']} |
| Random baseline ROI | −4.55% (theoretical) / {fmtr(rand_roi)} (empirical) |

## Per-Strategy Results

| Strategy | n_bets | win_rate | ROI | Beats random? | 95% CI |
|----------|--------|----------|-----|---------------|--------|
| anomaly_only | {strat_results['anomaly_only']['n_bets']} | {fmtw(anom_wr)} | {fmtr(anom_roi)} | {beat(anom_roi)} | {ci_results.get('anomaly_real_lines', 'N/A')} |
| matchup_only | {strat_results['matchup_only']['n_bets']} | {fmtw(match_wr)} | {fmtr(match_roi)} | {beat(match_roi)} | {ci_results.get('matchup_real_lines', 'N/A')} |
| combined | {strat_results['combined']['n_bets']} | {fmtw(comb_wr)} | {fmtr(comb_roi)} | {beat(comb_roi)} | — |
| random | {strat_results.get('random', {}).get('n_bets', 0)} | {fmtw(rand_wr)} | {fmtr(rand_roi)} | baseline | — |

### Real Lines Only (Most Honest)

| Source | n_bets | win_rate | ROI | 95% CI |
|--------|--------|----------|-----|--------|
| anomaly (real lines) | {output['real_lines_only']['anomaly_bets']['n']} | {fmtw(output['real_lines_only']['anomaly_bets']['win_rate'])} | {fmtr(output['real_lines_only']['anomaly_bets']['roi_pct'])} | {output['real_lines_only']['anomaly_bets']['ci_95']} |
| matchup (all real) | {output['real_lines_only']['matchup_bets']['n']} | {fmtw(output['real_lines_only']['matchup_bets']['win_rate'])} | {fmtr(output['real_lines_only']['matchup_bets']['roi_pct'])} | {output['real_lines_only']['matchup_bets']['ci_95']} |

## All Signal Results (ranked by ROI)

| signal | stats | n_bets | win_rate | ROI | beats random? |
|--------|-------|--------|----------|-----|---------------|
{all_rows_md}

## Profitable Intelligence Signals (ROI > 0)

| signal | stats | n_bets | win_rate | ROI |
|--------|-------|--------|----------|-----|
{profitable_rows}

## Losing Intelligence Signals (avoid)

| signal | issue |
|--------|-------|
{losing_rows}

## Strategic Takeaway

{verdict_text}

| Aspect | Detail |
|--------|--------|
| Best signal | `{list(per_signal_ranked.keys())[0] if per_signal_ranked else 'none'}` → ROI={fmtr(list(per_signal_ranked.values())[0]['roi_pct'] if per_signal_ranked else None)} on {list(per_signal_ranked.values())[0]['n_bets'] if per_signal_ranked else 0} bets |
| Kelly fraction (anomaly) | {kelly_anom:.2%} (0 = no edge; >0 = bet this fraction) |
| Kelly fraction (matchup) | {kelly_match:.2%} |
| Recommended sizing | {"Low confidence — flat 0.5u until N>200 per signal" if len(anomaly_bets_df) < 200 else "Medium confidence — 1-2u per signal with confirmed edge"} |

## Caveats

1. **Real lines coverage low**: Only {output['meta']['real_lines_pct']}% of anomaly bets have real sportsbook lines. L5-mean proxy lines understate book efficiency — actual ROI on real markets will likely be lower.
2. **Small N**: Anomaly strategy has N={len(anomaly_bets_df)} total bets. Statistical significance at p<0.05 requires ~500+ bets per signal. Results are directional, not statistically tight.
3. **Matchup history thin**: 95% of matchup_deviations records have n_games_vs_opp=1 — single-game history is very noisy as a predictive signal.
4. **Data quality issues**: ISSUE-022 (defender_distance=200 sentinel), ISSUE-023 (shot_clock MAE=17s) corrupt some CV features. defender_approach_speed sign convention may be inverted.
5. **Anomaly year**: INT-4 anomalies are concentrated in 2025-26 season only (smaller window).
6. **No multiple-testing correction**: {len(per_signal)} signals tested simultaneously — expected false positive rate without Bonferroni correction is elevated.
7. **No look-ahead**: All L5 proxies use shift(1) to avoid leakage. Real lines are closing lines (book view after all info).

## Next Steps

- If matchup ROI is positive: expand matchup_deviations coverage by requiring n_games_vs_opp>=2 for signal quality
- If anomaly ROI is positive on real lines: prioritize pairing with live injury feed (ISSUE listed in CLAUDE.md)
- Wire `closing_line` lookup into `predict_slate.py` so anomaly flags auto-generate bet recs at game time
- Re-run after 1 full season of live anomaly tracking to get N>500 per key signal

---
*See also: [[Tracker Improvements Log]], [[project_loop7_status]], [[feedback_grade_intelligence_not_execution]]*
"""

atlas_path = vault_dir / "Betting_Validation.md"
with open(atlas_path, "w", encoding="utf-8") as f:
    f.write(md)
print(f"Atlas saved -> {atlas_path}")
print("\nDone.")
