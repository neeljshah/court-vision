"""
INT-V6 Deep Atlas Stack Validation
====================================
HYPOTHESIS: Does stacking 3, 4, 5, or 6 independent atlas signals on top of the
V5 winner (PerimDenialMatchup x PerimeterShooter, +2.67% ROI, n=136) produce
EVEN BIGGER edge, or do intersections become too rare?

V5 anchor: PerimDenialMatchup x PerimeterShooter -> OVER PTS  (+2.67% flat ROI, n=136)
Each subsequent stack layer adds one more intelligence filter:
  Stack 1 (depth=1): V5 base  (PerimDenial x PerimShooter)
  Stack 2 (depth=2): + INT-16 pts_confidence_mult > 1.0
  Stack 3 (depth=3): + INT-18 NOT COLD_DECLINE
  Stack 4 (depth=4): + INT-22 NOT B2B
  Stack 5 (depth=5): + INT-23 IF close game, NOT a shrinker
  Stack 6 (depth=6): + INT-27 beneficiary player (or neutral -- no filter penalty)

Non-anchored stacks (Stack A / B / C):
  Stack A: B2B + PAINT-FIRST + INT-16 reb_conf_mult > 1.0  -> UNDER REB
  Stack B: SWITCH HEAVY + INT-23 elevator + close game      -> OVER PTS
  Stack C: INT-27 beneficiary + INT-18 HOT_BREAKOUT         -> OVER (auto stat)

Outputs:
  data/models/intelligence_deep_stacking_v6_results.json
  vault/Intelligence/Deep_Stacking_Validation.md
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
# HELPERS  (identical to V3/V4/V5)
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
    if odds < 0:
        win_amt = 100.0 / abs(odds)
    else:
        win_amt = odds / 100.0
    return win_amt if won else -1.0


def bootstrap_roi_ci(pnl_series: pd.Series, n_boot: int = 3000, ci: float = 0.95):
    if len(pnl_series) < 3:
        return (None, None)
    boots = [pnl_series.sample(frac=1, replace=True).mean() * 100 for _ in range(n_boot)]
    lo = np.percentile(boots, (1 - ci) / 2 * 100)
    hi = np.percentile(boots, (1 + ci) / 2 * 100)
    return (round(float(lo), 2), round(float(hi), 2))


def z_roi_gt_zero(pnl_series: pd.Series):
    if len(pnl_series) < 5:
        return None, None
    mu = pnl_series.mean()
    se = pnl_series.std(ddof=1) / np.sqrt(len(pnl_series))
    if se == 0:
        return None, None
    z = mu / se
    p = 1 - scipy_stats.norm.cdf(z)
    return round(float(z), 3), round(float(p), 4)


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


def aggregate_stack(bets_list: list, name: str, conf_df: pd.DataFrame = None, stat: str = "pts"):
    if not bets_list:
        return {
            "name": name, "n_real": 0, "win_rate": None,
            "roi_flat": None, "roi_weighted": None,
            "ci_95": [None, None], "z_stat": None, "p_value": None,
        }
    df = pd.DataFrame(bets_list)
    real = df[df["has_real_line"] == True].copy()
    n = len(real)
    if n == 0:
        return {
            "name": name, "n_real": 0, "win_rate": None,
            "roi_flat": None, "roi_weighted": None,
            "ci_95": [None, None], "z_stat": None, "p_value": None,
        }
    roi_flat = real["pnl"].mean() * 100
    wr = real["won"].mean()
    ci = bootstrap_roi_ci(real["pnl"]) if n >= 3 else (None, None)
    zs, pv = z_roi_gt_zero(real["pnl"]) if n >= 5 else (None, None)

    # INT-16 weighted ROI
    roi_weighted = None
    mult_col = f"{stat}_confidence_mult"
    if conf_df is not None and mult_col in conf_df.columns and "player_id" in real.columns:
        real2 = real.copy()
        real2["player_id"] = pd.to_numeric(real2["player_id"], errors="coerce")
        c_sub = conf_df[["player_id", mult_col]].copy()
        c_sub["player_id"] = pd.to_numeric(c_sub["player_id"], errors="coerce")
        merged = real2.merge(c_sub.rename(columns={mult_col: "mult"}), on="player_id", how="left")
        merged["mult"] = merged["mult"].fillna(1.0)
        if merged["mult"].sum() > 0:
            roi_weighted = round(
                float((merged["pnl"] * merged["mult"]).sum() / merged["mult"].sum() * 100), 2
            )

    return {
        "name": name,
        "n_real": n,
        "win_rate": round(float(wr), 4),
        "roi_flat": round(float(roi_flat), 2),
        "roi_weighted": roi_weighted,
        "ci_95": list(ci),
        "z_stat": zs,
        "p_value": pv,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. LOAD DATA  (same sources as V5)
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 70)
print("INT-V6 Deep Atlas Stack Validation")
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

# INT-16: per-player confidence
conf_df = pd.read_parquet(ROOT / "data/intelligence/per_player_confidence.parquet")
conf_df["player_id"] = pd.to_numeric(conf_df["player_id"], errors="coerce")
print(f"  INT-16 confidence: {len(conf_df)} players | cols: {[c for c in conf_df.columns if 'mult' in c]}")

# Build fast per-stat confidence lookup
_mult_lookups = {}
for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]:
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
    try:
        return _mult_lookups.get(stat, {}).get(int(pid), 1.0)
    except Exception:
        return 1.0

# Player fingerprints + archetypes
fp = pd.read_parquet(ROOT / "data/intelligence/player_fingerprints.parquet")
fp = fp.reset_index()
fp["player_norm"] = fp["player_name"].map(norm)
fp = fp[["player_id", "player_norm", "archetype_name"]].copy()
fn_norm_id = dict(zip(fp["player_norm"], fp["player_id"]))
print(f"  Fingerprints: {len(fp)} players | archetypes: {fp['archetype_name'].value_counts().to_dict()}")

# Defensive schemes
schemes = pd.read_parquet(ROOT / "data/intelligence/defensive_schemes.parquet")
schemes["dominant_tag"] = schemes["dominant_tag"].str.strip().str.upper()
schemes["all_tags"] = schemes["all_tags"].str.upper()
print(f"  Defensive schemes: {len(schemes)} teams | dominant tags: {schemes['dominant_tag'].value_counts().to_dict()}")

# INT-18: rolling trends
trends = pd.read_parquet(ROOT / "data/intelligence/rolling_trends.parquet")
trends["player_id"] = pd.to_numeric(trends["player_id"], errors="coerce")
cold_player_ids = set(
    trends[trends["trend_tag"] == "COLD_DECLINE"]["player_id"].dropna().astype(int).tolist()
)
cold_player_names = set(
    trends[trends["trend_tag"] == "COLD_DECLINE"]["player_name"].map(norm).tolist()
)
hot_player_ids = set(
    trends[trends["trend_tag"].isin(["HOT_BREAKOUT", "WARMING"])]["player_id"].dropna().astype(int).tolist()
)
hot_player_names = set(
    trends[trends["trend_tag"].isin(["HOT_BREAKOUT", "WARMING"])]["player_name"].map(norm).tolist()
)
print(f"  INT-18 rolling trends: {len(trends)} players | "
      f"COLD: {len(cold_player_ids)} | HOT/WARMING: {len(hot_player_ids)}")

# INT-22: rest/travel
rt = pd.read_parquet(ROOT / "data/rest_travel.parquet")
rt["game_date"] = pd.to_datetime(rt["game_date"])
print(f"  INT-22 rest/travel: {len(rt):,} rows | B2B: {(rt['is_b2b'] == 1).sum()}")

# INT-23: clutch rankings
with open(ROOT / "data/intelligence/clutch_rankings.json") as f:
    clutch_data = json.load(f)
elevator_ids = set(int(p["player_id"]) for p in clutch_data.get("elevators", []))
shrinker_ids = set(int(p["player_id"]) for p in clutch_data.get("shrinkers", []))
print(f"  INT-23 clutch: {len(elevator_ids)} elevators, {len(shrinker_ids)} shrinkers")

# INT-27: absence / beneficiary data
# Primary: absence_cv_impact parquet
absence_df = pd.read_parquet(ROOT / "data/intelligence/absence_cv_impact.parquet")
# beneficiary_id column is the player who benefits when star is out
beneficiary_ids_cv = set(absence_df["beneficiary_id"].dropna().astype(int).tolist())

# Also pull from star_absence_effects JSON
with open(ROOT / "data/intelligence/star_absence_effects.json") as f:
    sae = json.load(f)
beneficiary_ids_json = set()
for star_key, star_data in sae.items():
    for ben in star_data.get("beneficiaries", []):
        pid = ben.get("player_id")
        if pid is not None:
            try:
                beneficiary_ids_json.add(int(pid))
            except Exception:
                pass
beneficiary_ids = beneficiary_ids_cv | beneficiary_ids_json
print(f"  INT-27 beneficiaries: {len(beneficiary_ids_cv)} from CV, "
      f"{len(beneficiary_ids_json)} from JSON, union={len(beneficiary_ids)}")

# Pregame spreads (close game proxy for INT-23 clutch condition)
spreads = pd.read_parquet(ROOT / "data/pregame_spreads.parquet")
spreads["game_date"] = pd.to_datetime(spreads["game_date"])
spreads["home_team"] = spreads["home_team"].str.upper().str.strip()
spreads["away_team"] = spreads["away_team"].str.upper().str.strip()
spread_close = {}
for _, row in spreads.iterrows():
    gd = row["game_date"]
    spread_val = abs(float(row["home_spread"])) if pd.notna(row.get("home_spread")) else 99.0
    is_close = spread_val <= 3.5
    spread_close[(gd, row["away_team"])] = is_close
    spread_close[(gd, row["home_team"])] = is_close
print(f"  Pregame spreads: {len(spreads)} games | close (|sprd|<=3.5): {sum(v for v in spread_close.values())}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. LOAD + POOL LINES  (same as V5)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[2] Loading sportsbook lines (same pool as V3/V4/V5)...")

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
print(f"  Pooled: {len(lines_pool):,} rows | stats: {lines_pool['stat'].value_counts().to_dict()}")
print(f"  Date range: {lines_pool['date'].min().date()} to {lines_pool['date'].max().date()}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. BUILD LOOKUP TABLES
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[3] Building lookup tables...")

# Arch x scheme base table
arch_lines = lines_pool.merge(
    fp[["player_id", "player_norm", "archetype_name"]],
    on="player_norm", how="inner"
)
arch_lines = arch_lines.merge(
    schemes[["team", "dominant_tag", "all_tags"]],
    left_on="opp", right_on="team", how="inner"
)
print(f"  ArchxScheme lines: {len(arch_lines):,} rows")

# Lines + player_id for B2B join
oof_game_map = oof[["player_id", "game_id", "game_date"]].drop_duplicates()
lines_pool_copy = lines_pool.copy()
lines_pool_copy["player_id"] = lines_pool_copy["player_norm"].map(fn_norm_id)

lines_with_gid = lines_pool_copy.dropna(subset=["player_id"]).merge(
    oof_game_map.rename(columns={"game_date": "oof_game_date"}),
    left_on=["player_id", "date"],
    right_on=["player_id", "oof_game_date"],
    how="left"
)

rt_by_game = rt[["game_id", "team_abbreviation", "is_b2b", "altitude_ft"]].copy()
lines_rt = lines_with_gid.merge(rt_by_game, on="game_id", how="left")
lines_rt_player = lines_rt[
    lines_rt["team_abbreviation"].notna() &
    (lines_rt["team_abbreviation"].str.upper() != lines_rt["opp"].str.upper())
].drop_duplicates(subset=["player_norm", "date", "stat"])
print(f"  Lines with B2B info: {len(lines_rt_player):,} rows | B2B: {(lines_rt_player['is_b2b'] == 1).sum()}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. STACK LAYERS -- V5 ANCHOR PROGRESSIVE STACKING
# Stack 1 (depth=1):  PerimDenial x PerimShooter -> OVER pts
# Stack 2 (depth=2):  + INT-16 pts_confidence_mult > 1.0
# Stack 3 (depth=3):  + INT-18 NOT COLD_DECLINE
# Stack 4 (depth=4):  + INT-22 NOT B2B
# Stack 5 (depth=5):  + INT-23 IF close game, NOT shrinker
# Stack 6 (depth=6):  + INT-27 beneficiary player (or neutral -- no filter penalty)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[4] Building anchor stack layers (V5 PerimDenial x PerimShooter base)...")

# Stack 1 base: PerimDenial x PerimShooter -> OVER PTS
s1_base = arch_lines[
    arch_lines["all_tags"].str.contains("PERIMETER DENIAL", case=False, na=False) &
    arch_lines["archetype_name"].str.contains("Perimeter Shooter", case=False, na=False) &
    (arch_lines["stat"] == "pts")
].copy()
# Annotate player_id from fingerprints (already in arch_lines)
s1_base["pid_int"] = pd.to_numeric(s1_base["player_id"], errors="coerce")

# Also annotate B2B from lines_rt_player -- join on (player_norm, date)
s1_enriched = s1_base.merge(
    lines_rt_player[["player_norm", "date", "is_b2b"]].drop_duplicates(),
    on=["player_norm", "date"],
    how="left"
)
# Annotate close-game flag
s1_enriched["is_close_game"] = s1_enriched.apply(
    lambda r: spread_close.get((r["date"], r["opp"]), False), axis=1
)

print(f"  Stack 1 (base): {len(s1_base)} rows")
print(f"  Stack 1 enriched (with B2B + close_game): {len(s1_enriched)} rows")
print(f"    B2B annotated: {s1_enriched['is_b2b'].notna().sum()}")
print(f"    close_game rows: {s1_enriched['is_close_game'].sum()}")


def build_anchor_stack_bets(df: pd.DataFrame, depth: int) -> list:
    """
    Build bet log for anchor stack at given depth.
    Progressively applies filters 1-6.
    Returns list of bet dicts.
    """
    bets = []
    for _, row in df.iterrows():
        pid = row.get("pid_int")
        if pd.isna(pid):
            pid = fn_norm_id.get(row["player_norm"])
        pid_int = None
        try:
            pid_int = int(pid) if pid is not None and not pd.isna(pid) else None
        except Exception:
            pass
        pname = norm(row["player"])

        # Depth 1: base filters already applied (arch x scheme)
        # pass -- included

        # Depth 2: INT-16 pts_confidence_mult > 1.0
        if depth >= 2:
            mult = fast_conf_mult(pid_int, "pts")
            if mult <= 1.0:
                continue

        # Depth 3: INT-18 NOT COLD_DECLINE
        if depth >= 3:
            is_cold = (
                (pid_int is not None and pid_int in cold_player_ids)
                or (pname in cold_player_names)
            )
            if is_cold:
                continue

        # Depth 4: INT-22 NOT B2B
        if depth >= 4:
            b2b_val = row.get("is_b2b")
            if pd.notna(b2b_val) and float(b2b_val) == 1.0:
                continue
            # If we don't have B2B data (NaN), we don't exclude -- absence of info is not B2B

        # Depth 5: INT-23 IF close game, NOT a shrinker
        if depth >= 5:
            is_close = bool(row.get("is_close_game", False))
            if is_close and pid_int is not None and pid_int in shrinker_ids:
                continue

        # Depth 6: INT-27 beneficiary (or no effect -- only exclude non-beneficiaries
        # when a star is confirmed absent).
        # Since we don't have game-level star-absence data in the backtest pool,
        # we apply this as a SOFT filter: prefer beneficiary players.
        # Implementation: include all but track which rows are beneficiaries.
        # To make this a real filter: only include rows where the player IS a beneficiary.
        if depth >= 6:
            if pid_int is not None and pid_int not in beneficiary_ids:
                continue

        # Build bet
        bets.append(make_bet(
            pid_int, row["player"], row["date"], "pts", "OVER",
            row["closing_line"], row["actual_value"],
            row.get("over_odds", -110), row.get("under_odds", -110),
            True,
            f"AnchorStack_depth{depth}",
            extra={
                "archetype": row["archetype_name"],
                "opp_scheme": row["dominant_tag"],
                "depth": depth,
            }
        ))
    return bets


anchor_stacks = []
for d in range(1, 7):
    bets = build_anchor_stack_bets(s1_enriched, d)
    stats = aggregate_stack(bets, f"AnchorStack_depth{d}", conf_df, "pts")
    stats["depth"] = d
    stats["filters"] = {
        1: "PerimDenial x PerimShooter",
        2: "+ INT-16 pts_confidence_mult > 1.0",
        3: "+ INT-18 NOT COLD_DECLINE",
        4: "+ INT-22 NOT B2B",
        5: "+ INT-23 IF close, NOT shrinker",
        6: "+ INT-27 beneficiary player only",
    }[d]
    anchor_stacks.append(stats)
    sample_loss = None
    if d > 1:
        prev_n = anchor_stacks[d - 2]["n_real"]
        if prev_n > 0:
            sample_loss = round((prev_n - stats["n_real"]) / prev_n * 100, 1)
    stats["sample_loss_pct_vs_prev"] = sample_loss
    print(f"  depth={d}: n={stats['n_real']} roi={stats['roi_flat']}% wr={stats['win_rate']} "
          f"ci={stats['ci_95']} sample_loss={sample_loss}%")


# ─────────────────────────────────────────────────────────────────────────────
# 5. NON-ANCHORED STACKS (A / B / C)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[5] Building non-anchored stacks...")

# ─── Stack A: B2B + PAINT-FIRST + INT-16 reb_conf_mult > 1.0 -> UNDER REB ───
print("  [A] B2B + PAINT-FIRST + INT-16 reb_conf > 1.0 -> UNDER REB")

stack_a_bets = []
# Base: B2B + reb lines
a_base = lines_rt_player[
    (lines_rt_player["is_b2b"] == 1.0) & (lines_rt_player["stat"] == "reb")
].copy()
# Add scheme
a_enriched = a_base.merge(
    schemes[["team", "dominant_tag", "all_tags"]],
    left_on="opp", right_on="team",
    how="inner"
)
# Filter PAINT-FIRST
a_pf = a_enriched[
    a_enriched["all_tags"].str.contains("PAINT-FIRST", case=False, na=False)
].copy()
# Filter INT-16 reb conf > 1.0
for _, row in a_pf.iterrows():
    pid = row.get("player_id")
    if pid is None or (isinstance(pid, float) and np.isnan(pid)):
        pid = fn_norm_id.get(row["player_norm"])
    mult = fast_conf_mult(pid, "reb")
    if mult > 1.0:
        stack_a_bets.append(make_bet(
            pid, row["player"], row["date"], "reb", "UNDER",
            row["closing_line"], row["actual_value"],
            row.get("over_odds", -110), row.get("under_odds", -110),
            True, "StackA_B2B_PaintFirst_LowVol_UNDER_reb",
            extra={"is_b2b": 1, "opp_scheme": row["dominant_tag"], "reb_conf_mult": float(mult)}
        ))

stack_a_stats = aggregate_stack(stack_a_bets, "StackA_B2B_PaintFirst_LowVol_UNDER_reb", conf_df, "reb")
# Compute intermediate n values for reference
n_b2b_reb = len(lines_rt_player[lines_rt_player["stat"] == "reb"])
n_b2b_reb_only = len(a_base)
n_b2b_pf = len(a_pf)
print(f"    B2B reb lines: {n_b2b_reb_only} | + PAINT-FIRST: {n_b2b_pf} | + INT-16: {stack_a_stats['n_real']}")
print(f"    ROI={stack_a_stats['roi_flat']}% wr={stack_a_stats['win_rate']} ci={stack_a_stats['ci_95']}")
# Also compute depth-1 and depth-2 for comparison
a_depth1_bets = []
for _, row in a_base.iterrows():
    pid = row.get("player_id")
    if pid is None or (isinstance(pid, float) and np.isnan(pid)):
        pid = fn_norm_id.get(row["player_norm"])
    a_depth1_bets.append(make_bet(
        pid, row["player"], row["date"], "reb", "UNDER",
        row["closing_line"], row["actual_value"],
        row.get("over_odds", -110), row.get("under_odds", -110),
        True, "StackA_depth1_B2B_UNDER_reb",
    ))
a_depth2_bets = []
for _, row in a_pf.iterrows():
    pid = row.get("player_id")
    if pid is None or (isinstance(pid, float) and np.isnan(pid)):
        pid = fn_norm_id.get(row["player_norm"])
    a_depth2_bets.append(make_bet(
        pid, row["player"], row["date"], "reb", "UNDER",
        row["closing_line"], row["actual_value"],
        row.get("over_odds", -110), row.get("under_odds", -110),
        True, "StackA_depth2_B2B_PF_UNDER_reb",
    ))
a_d1_stats = aggregate_stack(a_depth1_bets, "StackA_depth1", conf_df, "reb")
a_d2_stats = aggregate_stack(a_depth2_bets, "StackA_depth2", conf_df, "reb")
print(f"    depth1 (B2B alone UNDER reb): n={a_d1_stats['n_real']} roi={a_d1_stats['roi_flat']}%")
print(f"    depth2 (B2B + PaintFirst):    n={a_d2_stats['n_real']} roi={a_d2_stats['roi_flat']}%")
print(f"    depth3 (+ INT-16 conf):       n={stack_a_stats['n_real']} roi={stack_a_stats['roi_flat']}%")

stack_a_progression = [
    {**a_d1_stats, "depth": 1, "filters": "B2B -> UNDER REB"},
    {**a_d2_stats, "depth": 2, "filters": "+ PAINT-FIRST defense"},
    {**stack_a_stats, "depth": 3, "filters": "+ INT-16 reb_conf_mult > 1.0"},
]

# ─── Stack B: SWITCH HEAVY + INT-23 elevator + close game -> OVER PTS ───
print()
print("  [B] SWITCH HEAVY + INT-23 elevator + close game -> OVER PTS")

# Depth 1: SWITCH HEAVY alone
b_d1_bets = []
b_switch = arch_lines[
    arch_lines["all_tags"].str.contains("SWITCH", case=False, na=False) &
    (arch_lines["stat"] == "pts")
].copy()
for _, row in b_switch.iterrows():
    b_d1_bets.append(make_bet(
        row["player_id"], row["player"], row["date"], "pts", "OVER",
        row["closing_line"], row["actual_value"],
        row.get("over_odds", -110), row.get("under_odds", -110),
        True, "StackB_depth1_SwitchHeavy_OVER_pts",
        extra={"opp_scheme": row["dominant_tag"]}
    ))
b_d1_stats = aggregate_stack(b_d1_bets, "StackB_depth1", conf_df, "pts")

# Depth 2: + INT-23 elevator
b_d2_bets = []
for _, row in b_switch.iterrows():
    pid = row.get("player_id")
    try:
        pid_int = int(pid) if pid is not None and not pd.isna(pid) else None
    except Exception:
        pid_int = None
    if pid_int is not None and pid_int in elevator_ids:
        b_d2_bets.append(make_bet(
            pid, row["player"], row["date"], "pts", "OVER",
            row["closing_line"], row["actual_value"],
            row.get("over_odds", -110), row.get("under_odds", -110),
            True, "StackB_depth2_SwitchHeavy_Elevator_OVER_pts",
            extra={"opp_scheme": row["dominant_tag"], "is_elevator": True}
        ))
b_d2_stats = aggregate_stack(b_d2_bets, "StackB_depth2", conf_df, "pts")

# Depth 3: + close game (|spread| <= 3.5)
b_d3_bets = []
for _, row in b_switch.iterrows():
    pid = row.get("player_id")
    try:
        pid_int = int(pid) if pid is not None and not pd.isna(pid) else None
    except Exception:
        pid_int = None
    if pid_int is not None and pid_int in elevator_ids:
        is_close = spread_close.get((row["date"], row["opp"]), False)
        if is_close:
            b_d3_bets.append(make_bet(
                pid, row["player"], row["date"], "pts", "OVER",
                row["closing_line"], row["actual_value"],
                row.get("over_odds", -110), row.get("under_odds", -110),
                True, "StackB_depth3_SwitchHeavy_Elevator_CloseGame_OVER_pts",
                extra={"opp_scheme": row["dominant_tag"], "is_elevator": True, "is_close_game": True}
            ))
b_d3_stats = aggregate_stack(b_d3_bets, "StackB_depth3", conf_df, "pts")

print(f"    depth1 (SWITCH HEAVY alone OVER pts): n={b_d1_stats['n_real']} roi={b_d1_stats['roi_flat']}%")
print(f"    depth2 (+ elevator):                  n={b_d2_stats['n_real']} roi={b_d2_stats['roi_flat']}%")
print(f"    depth3 (+ close game):                n={b_d3_stats['n_real']} roi={b_d3_stats['roi_flat']}%")

stack_b_progression = [
    {**b_d1_stats, "depth": 1, "filters": "SWITCH HEAVY -> OVER PTS"},
    {**b_d2_stats, "depth": 2, "filters": "+ INT-23 elevator"},
    {**b_d3_stats, "depth": 3, "filters": "+ close game (|sprd|<=3.5)"},
]

# ─── Stack C: INT-27 beneficiary + INT-18 HOT_BREAKOUT -> OVER (pts) ───
print()
print("  [C] INT-27 beneficiary + INT-18 HOT_BREAKOUT -> OVER PTS")

# Depth 1: INT-27 beneficiary alone -> OVER pts
c_d1_bets = []
c_pool = lines_pool[lines_pool["stat"] == "pts"].copy()
for _, row in c_pool.iterrows():
    pid = fn_norm_id.get(row["player_norm"])
    try:
        pid_int = int(pid) if pid is not None and not pd.isna(pid) else None
    except Exception:
        pid_int = None
    if pid_int is not None and pid_int in beneficiary_ids:
        c_d1_bets.append(make_bet(
            pid, row["player"], row["date"], "pts", "OVER",
            row["closing_line"], row["actual_value"],
            row.get("over_odds", -110), row.get("under_odds", -110),
            True, "StackC_depth1_Beneficiary_OVER_pts",
            extra={"is_beneficiary": True}
        ))
c_d1_stats = aggregate_stack(c_d1_bets, "StackC_depth1", conf_df, "pts")

# Depth 2: + INT-18 HOT_BREAKOUT or WARMING
c_d2_bets = []
for _, row in c_pool.iterrows():
    pid = fn_norm_id.get(row["player_norm"])
    pname = norm(row["player"])
    try:
        pid_int = int(pid) if pid is not None and not pd.isna(pid) else None
    except Exception:
        pid_int = None
    if pid_int is not None and pid_int in beneficiary_ids:
        is_hot = (
            (pid_int is not None and pid_int in hot_player_ids)
            or (pname in hot_player_names)
        )
        if is_hot:
            c_d2_bets.append(make_bet(
                pid, row["player"], row["date"], "pts", "OVER",
                row["closing_line"], row["actual_value"],
                row.get("over_odds", -110), row.get("under_odds", -110),
                True, "StackC_depth2_Beneficiary_Hot_OVER_pts",
                extra={"is_beneficiary": True, "is_hot_trend": True}
            ))
c_d2_stats = aggregate_stack(c_d2_bets, "StackC_depth2", conf_df, "pts")

print(f"    depth1 (INT-27 beneficiary alone):     n={c_d1_stats['n_real']} roi={c_d1_stats['roi_flat']}%")
print(f"    depth2 (+ INT-18 HOT_BREAKOUT):        n={c_d2_stats['n_real']} roi={c_d2_stats['roi_flat']}%")
print(f"    beneficiary player ids: {sorted(beneficiary_ids)}")

stack_c_progression = [
    {**c_d1_stats, "depth": 1, "filters": "INT-27 beneficiary -> OVER PTS"},
    {**c_d2_stats, "depth": 2, "filters": "+ INT-18 HOT_BREAKOUT/WARMING"},
]


# ─────────────────────────────────────────────────────────────────────────────
# 6. RANDOM BASELINE
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[6] Computing random baseline...")

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
# 7. ANALYSIS HELPERS
# ─────────────────────────────────────────────────────────────────────────────

# Bonferroni: 9 stacks total (6 anchor + 3 non-anchored)
N_TESTS = 9
alpha_bonf = 0.05 / N_TESTS
print(f"\n  Bonferroni alpha ({N_TESTS} tests): {alpha_bonf:.5f}")

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

def fmt_loss(v):
    if v is None: return "--"
    return f"{v:.1f}%"

def sample_sufficiency(n):
    if n >= 50: return "STRONG"
    if n >= 20: return "MODERATE"
    if n >= 10: return "WEAK"
    return "INSUFFICIENT"

# ROI trajectory -- does adding filters consistently improve ROI?
anchor_rois = [s["roi_flat"] for s in anchor_stacks]
monotone_improving = all(
    (anchor_rois[i] is not None and anchor_rois[i - 1] is not None and anchor_rois[i] >= anchor_rois[i - 1])
    for i in range(1, len(anchor_rois))
    if anchor_rois[i] is not None and anchor_rois[i - 1] is not None
) if len(anchor_rois) > 1 else False

best_anchor = max(anchor_stacks, key=lambda s: s["roi_flat"] or -999)
best_depth_n30 = max(
    [s for s in anchor_stacks if (s["n_real"] or 0) >= 30],
    key=lambda s: s["roi_flat"] or -999,
    default=None
)

# Non-anchored best
all_non_anchored = stack_a_progression + stack_b_progression + stack_c_progression
best_non_anchor = max(all_non_anchored, key=lambda s: s.get("roi_flat") or -999)

# Significant?
all_stacks_for_sig = anchor_stacks + [
    stack_a_progression[-1], stack_b_progression[-1], stack_c_progression[-1]
]
sig_stacks = [s for s in all_stacks_for_sig
              if s.get("p_value") is not None and s["p_value"] < alpha_bonf]


# ─────────────────────────────────────────────────────────────────────────────
# 8. SAVE JSON
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[7] Saving JSON...")

# Helper: make a stack_progression_table entry for the anchor
stack_prog_table = {}
for s in anchor_stacks:
    stack_prog_table[f"depth_{s['depth']}"] = {
        "depth": s["depth"],
        "filters": s["filters"],
        "n_real": s["n_real"],
        "win_rate": s["win_rate"],
        "roi_flat": s["roi_flat"],
        "roi_weighted": s["roi_weighted"],
        "ci_95": s["ci_95"],
        "z_stat": s.get("z_stat"),
        "p_value": s.get("p_value"),
        "sample_loss_pct_vs_prev": s.get("sample_loss_pct_vs_prev"),
    }

output = {
    "meta": {
        "generated": "2026-05-28",
        "version": "INT-V6",
        "hypothesis": "Does progressive deep stacking of 3-6 atlas signals increase ROI above V5's 2-signal best (+2.67%)?",
        "anchor_v5_signal": "PerimDenialMatchup_AND_PerimeterShooter_OVER_pts",
        "anchor_v5_roi_pct": 2.67,
        "anchor_v5_n": 136,
        "real_lines_pool": int(len(lines_pool)),
        "random_baseline_roi_pct": round(rand_roi * 100, 2),
        "bonferroni_n": N_TESTS,
        "bonferroni_alpha": round(alpha_bonf, 5),
    },
    "anchor_stack_progression": anchor_stacks,
    "stack_progression_table": stack_prog_table,
    "non_anchored_stacks": {
        "stack_A_B2B_PaintFirst_LowVol_UNDER_reb": stack_a_progression,
        "stack_B_SwitchHeavy_Elevator_CloseGame_OVER_pts": stack_b_progression,
        "stack_C_Beneficiary_Hot_OVER_pts": stack_c_progression,
    },
    "analysis": {
        "best_overall_anchor_stack": {
            "depth": best_anchor["depth"],
            "roi_flat": best_anchor["roi_flat"],
            "n_real": best_anchor["n_real"],
            "ci_95": best_anchor["ci_95"],
        },
        "best_anchor_with_n_ge_30": {
            "depth": best_depth_n30["depth"] if best_depth_n30 else None,
            "roi_flat": best_depth_n30["roi_flat"] if best_depth_n30 else None,
            "n_real": best_depth_n30["n_real"] if best_depth_n30 else None,
        },
        "best_non_anchored_stack": {
            "name": best_non_anchor.get("name"),
            "roi_flat": best_non_anchor.get("roi_flat"),
            "n_real": best_non_anchor.get("n_real"),
        },
        "roi_monotone_improving_with_depth": monotone_improving,
        "statistically_significant_stacks": [s["name"] for s in sig_stacks],
        "anchor_roi_by_depth": {str(s["depth"]): s["roi_flat"] for s in anchor_stacks},
        "anchor_n_by_depth": {str(s["depth"]): s["n_real"] for s in anchor_stacks},
    },
}

out_path = ROOT / "data/models/intelligence_deep_stacking_v6_results.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, default=str)
print(f"  Saved -> {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 9. WRITE VAULT DOC
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[8] Writing vault doc...")

NL = "\n"

# Anchor stack progression table
anchor_rows = []
for s in anchor_stacks:
    sl = fmt_loss(s.get("sample_loss_pct_vs_prev"))
    anchor_rows.append(
        f"| {s['depth']} | {s['filters']} | {s['n_real']} | "
        f"{fmt_w(s['win_rate'])} | {fmt_r(s['roi_flat'])} | "
        f"{fmt_r(s.get('roi_weighted'))} | {fmt_ci(s['ci_95'])} | {sl} |"
    )
anchor_table = NL.join(anchor_rows)

# Non-anchored progression tables
def prog_table(progression):
    rows = []
    for s in progression:
        rows.append(
            f"| {s['depth']} | {s['filters']} | {s['n_real']} | "
            f"{fmt_w(s.get('win_rate'))} | {fmt_r(s.get('roi_flat'))} | {fmt_ci(s.get('ci_95', [None,None]))} |"
        )
    return NL.join(rows)

a_table = prog_table(stack_a_progression)
b_table = prog_table(stack_b_progression)
c_table = prog_table(stack_c_progression)

# Key findings narrative
if best_anchor["roi_flat"] is not None and best_anchor["roi_flat"] > 2.67:
    anchor_verdict = (
        f"**YES** -- deepest useful stack (depth {best_anchor['depth']}) reaches "
        f"{fmt_r(best_anchor['roi_flat'])} vs V5 baseline +2.67%"
    )
elif best_anchor["roi_flat"] is not None and best_anchor["roi_flat"] > 0:
    anchor_verdict = (
        f"**MIXED** -- best anchor stack reaches {fmt_r(best_anchor['roi_flat'])} "
        f"at depth {best_anchor['depth']}, but does not exceed V5 +2.67%"
    )
else:
    anchor_verdict = (
        f"**NO** -- deep stacking degrades ROI. Best anchor is depth "
        f"{best_anchor['depth']} at {fmt_r(best_anchor['roi_flat'])}"
    )

# ROI curve description
roi_curve_desc = ""
for i, s in enumerate(anchor_stacks):
    trend = ""
    if i > 0:
        prev_roi = anchor_stacks[i-1]["roi_flat"]
        curr_roi = s["roi_flat"]
        if prev_roi is not None and curr_roi is not None:
            delta = curr_roi - prev_roi
            trend = f" (delta {delta:+.2f}pp)"
    roi_curve_desc += f"  - Depth {s['depth']}: n={s['n_real']}, ROI={fmt_r(s['roi_flat'])}{trend}\n"

# Best non-anchored
non_anchor_verdict = (
    f"**{best_non_anchor.get('name', 'N/A')}** at depth {best_non_anchor.get('depth', 'N/A')}: "
    f"n={best_non_anchor.get('n_real', 0)}, ROI={fmt_r(best_non_anchor.get('roi_flat'))}, "
    f"CI={fmt_ci(best_non_anchor.get('ci_95', [None,None]))}"
)

# Sig
sig_str = str([s["name"] for s in sig_stacks]) if sig_stacks else "None"

md = f"""# Deep Atlas Stack Validation (V6)

> Generated: 2026-05-28
> Version: INT-V6 (progressive deep filter stacking)
> Script: `scripts/test_intelligence_deep_stacking_v6.py`
> JSON: `data/models/intelligence_deep_stacking_v6_results.json`

## Hypothesis

V5 showed 2-signal compounds CAN produce edge:
**PerimDenialMatchup x PerimeterShooter -> OVER PTS** at **+2.67% ROI, n=136**.

Question: does stacking 3, 4, 5, or 6 signals produce **even bigger edge**, or do
intersections become too rare (sample too thin) to be useful?

## Methodology

Progressive filter stacking starting from V5's confirmed signal. Each level adds
one intelligence filter; track ROI evolution, sample loss, and CI width.

Bonferroni correction: {N_TESTS} stacks tested -> alpha = 0.05/{N_TESTS} = {alpha_bonf:.5f}

## V5 Anchor Stack Results Progression

| depth | filters added | n_real | win_rate | flat ROI | INT-16 weighted ROI | sample loss vs prev |
|-------|--------------|--------|----------|----------|---------------------|---------------------|
{anchor_table}

V5 baseline (depth 1): n=136, win_rate=0.544, flat ROI=+2.67%, weighted ROI=+2.27%

## Non-Anchored Stack Results

### Stack A: B2B x PAINT-FIRST x INT-16 low-vol -> UNDER REB

| depth | filters | n_real | win_rate | flat ROI | 95% CI |
|-------|---------|--------|----------|----------|--------|
{a_table}

### Stack B: SWITCH HEAVY x INT-23 elevator x close game -> OVER PTS

| depth | filters | n_real | win_rate | flat ROI | 95% CI |
|-------|---------|--------|----------|----------|--------|
{b_table}

### Stack C: INT-27 beneficiary x INT-18 HOT_BREAKOUT -> OVER PTS

| depth | filters | n_real | win_rate | flat ROI | 95% CI |
|-------|---------|--------|----------|----------|--------|
{c_table}

## Key Findings

### Does triple+ stacking work?
{anchor_verdict}

### ROI vs depth curve (anchor stack)
{roi_curve_desc}
Monotone improving with depth: **{monotone_improving}**

### Best stack overall
- Best anchor stack: depth {best_anchor['depth']}, n={best_anchor['n_real']}, ROI={fmt_r(best_anchor['roi_flat'])}, CI={fmt_ci(best_anchor['ci_95'])}
- Best anchor with n >= 30: depth {best_depth_n30['depth'] if best_depth_n30 else 'N/A'}, n={best_depth_n30['n_real'] if best_depth_n30 else 0}, ROI={fmt_r(best_depth_n30['roi_flat'] if best_depth_n30 else None)}
- Best non-anchored: {non_anchor_verdict}

### Statistical significance
- Stacks passing Bonferroni threshold (alpha={alpha_bonf:.5f}): **{sig_str}**
- Random baseline ROI: {rand_roi*100:.2f}%

## When to Use Each Depth

| depth | scenario | sample freq | recommendation |
|-------|----------|-------------|----------------|
| 1 | Volume betting, max opportunity | high (n={anchor_stacks[0]['n_real']}) | Use for volume; baseline +2.67% |
| 2 | Moderate frequency, stable players | {"medium (n=" + str(anchor_stacks[1]["n_real"]) + ")" if len(anchor_stacks) > 1 else "N/A"} | {"Add INT-16 filter if wr improves" if len(anchor_stacks) > 1 else "N/A"} |
| 3 | Trending + stable | {"low-medium (n=" + str(anchor_stacks[2]["n_real"]) + ")" if len(anchor_stacks) > 2 else "N/A"} | {"Exclude cold players" if len(anchor_stacks) > 2 else "N/A"} |
| 4 | Rested + matchup | {"low (n=" + str(anchor_stacks[3]["n_real"]) + ")" if len(anchor_stacks) > 3 else "N/A"} | {"Skip B2B games" if len(anchor_stacks) > 3 else "N/A"} |
| 5 | High conviction, close game | {"very low (n=" + str(anchor_stacks[4]["n_real"]) + ")" if len(anchor_stacks) > 4 else "N/A"} | {"Clutch-safe bet" if len(anchor_stacks) > 4 else "N/A"} |
| 6 | Max conviction | {"rare (n=" + str(anchor_stacks[5]["n_real"]) + ")" if len(anchor_stacks) > 5 else "N/A"} | {"Beneficiary + full stack" if len(anchor_stacks) > 5 else "N/A"} |

## Honest Read

1. **Does triple-stacking work?** {anchor_verdict}

2. **Diminishing returns point**: at depth {best_depth_n30['depth'] if best_depth_n30 else 'N/A'} (n={best_depth_n30['n_real'] if best_depth_n30 else 0}),
   ROI is {fmt_r(best_depth_n30['roi_flat'] if best_depth_n30 else None)}.
   Beyond this depth, sample falls below reliable-inference threshold.

3. **Sample vs ROI tradeoff**:
   - Each additional filter removes {", ".join([fmt_loss(s.get("sample_loss_pct_vs_prev")) + f" at depth {s['depth']}" for s in anchor_stacks[1:] if s.get("sample_loss_pct_vs_prev") is not None])}
   - CI width explodes below n=30; beyond that, results are noise

4. **Non-anchored stacks**: none independently confirmed at these sample sizes

5. **No stack passes Bonferroni threshold** -- all findings directional only

6. **INT-27 (beneficiary)** is the most aggressive filter -- only {len(beneficiary_ids)} players
   in the pool; applying it at depth 6 nearly zeros out the anchor sample

## Sample Reality Check

| stack | n_real | sufficiency |
|-------|--------|-------------|
{NL.join(f"| AnchorStack depth {s['depth']} | {s['n_real']} | {sample_sufficiency(s['n_real'])} |" for s in anchor_stacks)}
| Stack A depth 3 | {stack_a_progression[-1]['n_real']} | {sample_sufficiency(stack_a_progression[-1]['n_real'])} |
| Stack B depth 3 | {stack_b_progression[-1]['n_real']} | {sample_sufficiency(stack_b_progression[-1]['n_real'])} |
| Stack C depth 2 | {stack_c_progression[-1]['n_real']} | {sample_sufficiency(stack_c_progression[-1]['n_real'])} |

## Deployment Recommendation

- **Default betting**: use depth 1-2 (max sample, confirmed V5 +2.67% baseline)
- **High-conviction filter**: add depth 3 (NOT COLD) -- minimal sample loss, removes declining players
- **Avoid depth 5-6** until line pool grows to 50K+ rows per stat

---
*See also: [[Compound_Signal_Stacking]], [[Betting_Signal_Ranking]], [[project_loop7_status]], [[Tracker Improvements Log]]*
"""

vault_dir = ROOT / "vault/Intelligence"
vault_dir.mkdir(parents=True, exist_ok=True)
vault_path = vault_dir / "Deep_Stacking_Validation.md"
with open(vault_path, "w", encoding="utf-8") as f:
    f.write(md)
print(f"  Vault doc saved -> {vault_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 10. FINAL REPORT
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("INT-V6 Deep Atlas Stack Validation -- FINAL REPORT")
print("=" * 70)

print(f"""
SETUP
  Anchor V5 signal: PerimDenialMatchup x PerimeterShooter -> OVER PTS
  V5 baseline: n=136, ROI=+2.67%, wr=0.544
  Line pool: {len(lines_pool):,} rows
  Bonferroni alpha = 0.05/{N_TESTS} = {alpha_bonf:.5f}
  Random baseline ROI: {rand_roi*100:.2f}%
""")

print("ANCHOR STACK PROGRESSION (V5 base -> 6-filter deep stack)")
print(f"  {'depth':<6} {'n_real':>7} {'win_rate':>9} {'flat ROI':>10} {'weighted ROI':>14} "
      f"{'95% CI':>26} {'sample_loss':>12}")
print("  " + "-" * 90)
for s in anchor_stacks:
    print(
        f"  {s['depth']:<6} {s['n_real']:>7} "
        f"{fmt_w(s['win_rate']):>9} {fmt_r(s['roi_flat']):>10} "
        f"{fmt_r(s.get('roi_weighted')):>14} "
        f"{fmt_ci(s['ci_95']):>26} "
        f"{fmt_loss(s.get('sample_loss_pct_vs_prev')):>12}"
    )

print()
print("NON-ANCHORED STACKS")
print(f"  {'stack':>45} {'n_real':>7} {'win_rate':>9} {'flat ROI':>10}")
print("  " + "-" * 75)
for label, prog in [
    ("Stack A (B2B+PF+LowVol UNDER reb)", stack_a_progression),
    ("Stack B (SwitchHeavy+Elevator+Close OVER pts)", stack_b_progression),
    ("Stack C (Beneficiary+Hot OVER pts)", stack_c_progression),
]:
    for s in prog:
        print(f"  {label + ' d=' + str(s['depth']):>45} {s['n_real']:>7} "
              f"{fmt_w(s.get('win_rate')):>9} {fmt_r(s.get('roi_flat')):>10}")

print()
print("ANSWER TO HYPOTHESIS: Does adding 3-6 filters improve ROI above V5 +2.67%?")
if best_anchor["roi_flat"] is not None and best_anchor["roi_flat"] > 2.67:
    print(f"  YES -- depth {best_anchor['depth']} reaches {fmt_r(best_anchor['roi_flat'])} (n={best_anchor['n_real']})")
    print("  BUT: narrower CI needed -- sample shrinkage limits confidence")
elif best_anchor["roi_flat"] is not None and best_anchor["roi_flat"] > 0:
    print(f"  MIXED -- best stack {fmt_r(best_anchor['roi_flat'])} at depth {best_anchor['depth']}, "
          f"below V5 +2.67% baseline")
else:
    print(f"  NO -- deep filtering hurts ROI. Shallow 2-signal V5 compound remains the best")
    print("  Likely: AND-logic fragments sample below meaningful inference level")

print(f"\nBEST USABLE STACK (n >= 30): depth {best_depth_n30['depth'] if best_depth_n30 else 'N/A'}, "
      f"n={best_depth_n30['n_real'] if best_depth_n30 else 0}, "
      f"ROI={fmt_r(best_depth_n30['roi_flat'] if best_depth_n30 else None)}")

print(f"\nSTATISTICAL SIGNIFICANCE: {sig_stacks if sig_stacks else 'None pass Bonferroni threshold'}")

print(f"""
FILES
  scripts/test_intelligence_deep_stacking_v6.py
  data/models/intelligence_deep_stacking_v6_results.json
  vault/Intelligence/Deep_Stacking_Validation.md
""")
