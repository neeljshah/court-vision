# -*- coding: utf-8 -*-
"""
INT-V9 Unified Multi-Season Deployment Validation
===================================================
Final combined backtest pooling BOTH validated signals across BOTH seasons.

Signal definitions:
  V6 OVER:
    - Player.archetype == "Perimeter Shooter / Transition Wing"
    - Opp scheme contains "PERIMETER DENIAL"
    - Player.INT-16 pts_confidence_mult > 1.0
    - Action: bet OVER PTS

  V8 UNDER (anti-elevator):
    - Player.name in INT-23 ELEVATOR list (clutch_rankings.json)
    - Action: bet UNDER PTS
    - Rationale: V8 showed ELEVATOR players OVER-perform their LINE
      (sportsbook books their typical scoring average, but in CV data these
      players show elevated clutch-time activity → their closing line is
      SET TOO LOW by books already pricing in regression → UNDER wins)
    - Actually V8 showed S4_ELEVATOR_OVER had ROI=-41.57% and WR=0.31,
      meaning actual < line 69% of the time → bet UNDER

  CONFLICT: player triggers BOTH V6 (OVER) and V8 (UNDER) on same game/date
    → PASS (skip bet, log conflict)

Seasons: 2024-25 + 2025-26 combined (max sample size)

Outputs:
  data/intelligence/v9_unified_results.json
  vault/Intelligence/V9_Unified_Deployment_Validation.md

Author: Claude Code (V9 unified deployment agent)
"""

import io
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

# Force UTF-8 stdout on Windows to handle box-drawing and special chars
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

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


# safe_odds imported from lib_betting_validation above


def roi_per_bet(won: bool, odds: float = -110.0) -> float:
    if odds < 0:
        win_amt = 100.0 / abs(odds)
    else:
        win_amt = odds / 100.0
    return win_amt if won else -1.0


def bootstrap_roi_ci(pnl_series: pd.Series, n_boot: int = 5000, ci: float = 0.95):
    if len(pnl_series) < 3:
        return (None, None)
    boots = [pnl_series.sample(frac=1, replace=True).mean() * 100
             for _ in range(n_boot)]
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


def aggregate_signal(bets_list: list, name: str, conf_df=None,
                     conf_id_mult: dict = None) -> dict:
    """Compute ROI, win_rate, CI, z-stat for a list of bets."""
    if not bets_list:
        return {
            "name": name, "n_real": 0, "win_rate": None,
            "roi_flat": None, "roi_int16_weighted": None,
            "ci_95": [None, None], "z_stat": None, "p_value": None,
            "verdict": "INSUFFICIENT_SAMPLE",
        }
    df = pd.DataFrame(bets_list)
    n = len(df)
    roi_flat = df["pnl"].mean() * 100
    wr = df["won"].mean()
    ci = bootstrap_roi_ci(df["pnl"]) if n >= 3 else (None, None)
    zs, pv = z_roi_gt_zero(df["pnl"]) if n >= 5 else (None, None)

    # INT-16 weighted ROI
    roi_weighted = None
    if conf_id_mult and "player_id" in df.columns:
        df2 = df.copy()
        df2["player_id"] = pd.to_numeric(df2["player_id"], errors="coerce")
        df2["mult"] = df2["player_id"].map(lambda pid: conf_id_mult.get(int(pid), 1.0)
                                            if pd.notna(pid) else 1.0)
        w_sum = df2["mult"].sum()
        if w_sum > 0:
            roi_weighted = round(
                float((df2["pnl"] * df2["mult"]).sum() / w_sum * 100), 2
            )

    # Verdict
    if n < 10:
        verdict = f"TOO_SMALL (n={n})"
    elif n < 30:
        verdict = f"SMALL_SAMPLE (n={n})"
    elif ci[0] is not None and ci[0] > 0:
        verdict = "POSITIVE_CI — deployable"
    elif roi_flat > 3.0:
        verdict = "POSITIVE_ROI — CI includes zero, monitor"
    elif roi_flat < -3.0:
        verdict = "NEGATIVE_ROI"
    else:
        verdict = "FLAT / NOISE"

    return {
        "name": name,
        "n_real": n,
        "win_rate": round(float(wr), 4),
        "roi_flat": round(float(roi_flat), 2),
        "roi_int16_weighted": roi_weighted,
        "ci_95": list(ci),
        "z_stat": zs,
        "p_value": pv,
        "verdict": verdict,
    }


def season_of(dt) -> str:
    """Assign a row to 2024-25 or 2025-26 season."""
    try:
        d = pd.Timestamp(dt)
        if d >= pd.Timestamp("2025-10-01"):
            return "2025-26"
        return "2024-25"
    except Exception:
        return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# 1. LOAD INTELLIGENCE SOURCES
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 72)
print("INT-V9  Unified Multi-Season Deployment Validation")
print("=" * 72)
print()
print("[1] Loading intelligence sources...")

# INT-1: Player fingerprints + archetypes
fp = pd.read_parquet(ROOT / "data/intelligence/player_fingerprints.parquet")
fp = fp.reset_index()
fp["player_norm"] = fp["player_name"].map(norm)
fp_archetype = dict(zip(fp["player_norm"], fp["archetype_name"]))
fp_id = dict(zip(fp["player_norm"], fp.index))  # player_id from index

# Perimeter Shooter / Transition Wing players
perim_shooter_names = set(
    fp[fp["archetype_name"].str.contains("Perimeter Shooter", case=False, na=False)
    ]["player_norm"].tolist()
)
perim_shooter_ids = set(
    fp[fp["archetype_name"].str.contains("Perimeter Shooter", case=False, na=False)
    ].index.tolist()
)
print(f"  INT-1 Perimeter Shooter players: {len(perim_shooter_names)}")

# INT-defensive: Defensive schemes — PERIMETER DENIAL teams
schemes = pd.read_parquet(ROOT / "data/intelligence/defensive_schemes.parquet")
perim_denial_teams = set(
    schemes[schemes["all_tags"].str.contains("PERIMETER DENIAL", case=False, na=False)
    ]["team"].str.upper().str.strip().tolist()
)
print(f"  Defensive schemes: PERIMETER DENIAL teams = {sorted(perim_denial_teams)}")

# INT-16: Per-player confidence (pts_confidence_mult)
conf_df = pd.read_parquet(ROOT / "data/intelligence/per_player_confidence.parquet")
conf_df["player_norm"] = conf_df["player_name"].map(norm)
conf_df["player_id"] = pd.to_numeric(conf_df["player_id"], errors="coerce")
conf_name_mult: dict = dict(zip(conf_df["player_norm"], conf_df["pts_confidence_mult"]))
conf_id_mult: dict = {
    int(pid): float(mult)
    for pid, mult in zip(conf_df["player_id"], conf_df["pts_confidence_mult"])
    if pd.notna(pid)
}
print(f"  INT-16 confidence: {len(conf_df)} players")

# INT-23: Clutch rankings (elevators for V8 anti-signal)
with open(ROOT / "data/intelligence/clutch_rankings.json") as f:
    clutch_data = json.load(f)

elevator_list = clutch_data.get("elevators", [])
elevator_names = set(norm(e["player_name"]) for e in elevator_list)
elevator_ids = set(int(e["player_id"]) for e in elevator_list)
elevator_scores = {norm(e["player_name"]): e.get("elevator_score", 0.0)
                   for e in elevator_list}
print(f"  INT-23 ELEVATOR players ({len(elevator_names)}): {sorted(elevator_names)}")

# Conflict check: players in BOTH perim_shooter AND elevator lists
conflict_player_names = perim_shooter_names & elevator_names
print(f"  CONFLICT players in both lists: "
      f"{sorted(conflict_player_names) if conflict_player_names else 'NONE'}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. LOAD + POOL SPORTSBOOK LINES (same pool as V3–V8)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[2] Loading sportsbook lines (same pool as V3–V8)...")

line_sources = [
    ROOT / "data/external/historical_lines/extended_oos_canonical.csv",
    ROOT / "data/external/historical_lines/benashkar_2026_canonical.csv",
    ROOT / "data/external/historical_lines/regular_season_2025_26_oddsapi.csv",
    ROOT / "data/external/historical_lines/regular_season_2024_25_oddsapi.csv",
]

line_dfs = []
for p in line_sources:
    if p.exists():
        d = pd.read_csv(str(p), on_bad_lines="skip")
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        d["player_norm"] = d["player"].map(norm)
        d["stat"] = d["stat"].str.lower().str.strip()
        d["opp"] = d["opp"].str.upper().str.strip()
        line_dfs.append(d)
        print(f"  Loaded {p.name}: {len(d):,} rows")
    else:
        print(f"  WARN: {p.name} not found")

if not line_dfs:
    print("ERROR: No line files found!")
    sys.exit(1)

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
lines_pool["season"] = lines_pool["date"].apply(season_of)

print(f"  Pooled (deduped): {len(lines_pool):,} rows")
print(f"  Date range: {lines_pool['date'].min().date()} to {lines_pool['date'].max().date()}")
print(f"  By season: {lines_pool.groupby('season').size().to_dict()}")

# PTS lines only
pts_lines = lines_pool[lines_pool["stat"] == "pts"].copy()
pts_lines = pts_lines.sort_values("date").reset_index(drop=True)
print(f"  PTS lines total: {len(pts_lines):,}")
print(f"  PTS by season: {pts_lines.groupby('season').size().to_dict()}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. ANNOTATE LINES WITH V6 + V8 TRIGGER FLAGS
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[3] Annotating PTS lines with V6 + V8 trigger flags...")

# V6 conditions
pts_lines["v6_perim_shooter"] = pts_lines["player_norm"].isin(perim_shooter_names)
pts_lines["v6_perim_denial"]  = pts_lines["opp"].isin(perim_denial_teams)
pts_lines["pts_conf_mult"]    = pts_lines["player_norm"].map(
    lambda pn: conf_name_mult.get(pn, 1.0)
)
pts_lines["v6_int16_ok"]      = pts_lines["pts_conf_mult"] > 1.0
pts_lines["v6_trigger"]       = (
    pts_lines["v6_perim_shooter"]
    & pts_lines["v6_perim_denial"]
    & pts_lines["v6_int16_ok"]
)

# V8 conditions
pts_lines["v8_trigger"]       = pts_lines["player_norm"].isin(elevator_names)

# Conflict: row triggers BOTH V6 OVER and V8 UNDER
pts_lines["conflict"]         = pts_lines["v6_trigger"] & pts_lines["v8_trigger"]

print(f"  V6 OVER triggers: {pts_lines['v6_trigger'].sum()}")
print(f"    (PerimShooter: {pts_lines['v6_perim_shooter'].sum()}, "
      f"PerimDenial opp: {pts_lines['v6_perim_denial'].sum()}, "
      f"INT16>1.0: {pts_lines['v6_int16_ok'].sum()})")
print(f"  V8 UNDER triggers: {pts_lines['v8_trigger'].sum()}")
print(f"  CONFLICT (both): {pts_lines['conflict'].sum()}")

# If there are conflicts, log them
if pts_lines["conflict"].sum() > 0:
    conflict_rows = pts_lines[pts_lines["conflict"]]
    print(f"  Conflict rows (will SKIP):")
    for _, r in conflict_rows.iterrows():
        print(f"    {r['player']}, {r['date'].date()}, vs {r['opp']}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. BUILD BET LOGS
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[4] Building bet logs...")

v6_bets = []
v8_bets = []
conflict_log = []

for _, row in pts_lines.iterrows():
    is_v6 = bool(row["v6_trigger"])
    is_v8 = bool(row["v8_trigger"])
    pname = str(row["player"])
    pnorm = row["player_norm"]
    gdate = row["date"]
    line_val = float(row["closing_line"])
    actual  = float(row["actual_value"])
    over_o  = safe_odds(row.get("over_odds", -110))
    under_o = safe_odds(row.get("under_odds", -110))
    season  = row["season"]
    opp     = row["opp"]
    conf_m  = float(row["pts_conf_mult"])

    # player_id: try player_norm lookup from fingerprints index
    try:
        pid = int(fp[fp["player_norm"] == pnorm].index[0])
    except Exception:
        pid = None

    if is_v6 and is_v8:
        # CONFLICT — log and skip
        conflict_log.append({
            "player": pname,
            "date": str(gdate.date()),
            "opp": opp,
            "season": season,
            "line": line_val,
            "actual": actual,
            "v6_would_bet": "OVER",
            "v8_would_bet": "UNDER",
        })
        continue

    if is_v6:
        won = actual > line_val
        pnl = roi_per_bet(won, over_o)
        v6_bets.append({
            "player_id": pid,
            "player_name": pname,
            "game_date": str(gdate.date()),
            "season": season,
            "opp": opp,
            "signal": "V6_OVER",
            "bet_direction": "OVER",
            "line": line_val,
            "actual": actual,
            "won": won,
            "pnl": pnl,
            "pts_conf_mult": conf_m,
            "over_odds": over_o,
            "under_odds": under_o,
        })

    if is_v8:
        won = actual < line_val
        pnl = roi_per_bet(won, under_o)
        elev_score = elevator_scores.get(pnorm, 0.0)
        v8_bets.append({
            "player_id": pid,
            "player_name": pname,
            "game_date": str(gdate.date()),
            "season": season,
            "opp": opp,
            "signal": "V8_UNDER",
            "bet_direction": "UNDER",
            "line": line_val,
            "actual": actual,
            "won": won,
            "pnl": pnl,
            "elevator_score": elev_score,
            "over_odds": over_o,
            "under_odds": under_o,
        })

print(f"  V6 OVER bets logged: {len(v6_bets)}")
print(f"  V8 UNDER bets logged: {len(v8_bets)}")
print(f"  CONFLICT (skipped): {len(conflict_log)}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. PER-SIGNAL STATISTICS (POOLED)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[5] Per-signal statistics (pooled across both seasons)...")

v6_stats = aggregate_signal(v6_bets, "V6_OVER", conf_df=conf_df,
                             conf_id_mult=conf_id_mult)
v8_stats = aggregate_signal(v8_bets, "V8_UNDER", conf_df=conf_df,
                             conf_id_mult=conf_id_mult)

for sig, stats in [("V6 OVER", v6_stats), ("V8 UNDER", v8_stats)]:
    print(f"  {sig}: n={stats['n_real']}  win_rate={stats['win_rate']}  "
          f"roi_flat={stats['roi_flat']}%  roi_weighted={stats['roi_int16_weighted']}%  "
          f"CI={stats['ci_95']}  z={stats['z_stat']}  p={stats['p_value']}")
    print(f"    verdict: {stats['verdict']}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. PER-SEASON BREAKDOWN
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[6] Per-season breakdown...")

def season_stats(bets_list, season_tag):
    sub = [b for b in bets_list if b.get("season") == season_tag]
    if not sub:
        return {"n": 0, "win_rate": None, "roi_flat": None}
    df = pd.DataFrame(sub)
    return {
        "n": len(df),
        "win_rate": round(float(df["won"].mean()), 4),
        "roi_flat": round(float(df["pnl"].mean() * 100), 2),
    }

v6_2425 = season_stats(v6_bets, "2024-25")
v6_2526 = season_stats(v6_bets, "2025-26")
v8_2425 = season_stats(v8_bets, "2024-25")
v8_2526 = season_stats(v8_bets, "2025-26")

print(f"  V6 OVER  | 2024-25: n={v6_2425['n']} roi={v6_2425['roi_flat']}% "
      f"wr={v6_2425['win_rate']} | "
      f"2025-26: n={v6_2526['n']} roi={v6_2526['roi_flat']}% wr={v6_2526['win_rate']}")
print(f"  V8 UNDER | 2024-25: n={v8_2425['n']} roi={v8_2425['roi_flat']}% "
      f"wr={v8_2425['win_rate']} | "
      f"2025-26: n={v8_2526['n']} roi={v8_2526['roi_flat']}% wr={v8_2526['win_rate']}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. BANKROLL SIMULATION (CHRONOLOGICAL ORDER)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[7] Bankroll simulation (FLAT_KELLY + INT16_WEIGHTED, $10,000 start)...")

STARTING_BANKROLL = 10_000.0
FLAT_KELLY_PCT = 0.01   # 1% of bankroll per bet

# Combine all bets chronologically
all_bets = v6_bets + v8_bets
if not all_bets:
    print("  ERROR: No bets to simulate!")
    sys.exit(1)

bets_df = pd.DataFrame(all_bets)
bets_df["game_date"] = pd.to_datetime(bets_df["game_date"])
bets_df = bets_df.sort_values("game_date").reset_index(drop=True)
print(f"  Total bets (combined): {len(bets_df)}")
print(f"  Date range: {bets_df['game_date'].min().date()} to {bets_df['game_date'].max().date()}")


def run_bankroll_sim(df: pd.DataFrame, label: str,
                     starting_bankroll: float,
                     kelly_pct: float,
                     use_int16_weight: bool = False) -> dict:
    """Simulate sequential bankroll. Returns summary dict."""
    br = starting_bankroll
    peak = br
    trough = br
    max_drawdown = 0.0
    trajectory = [[None, round(br, 2)]]
    total_staked = 0.0

    for _, row in df.iterrows():
        # Determine stake
        if use_int16_weight:
            mult = float(row.get("pts_conf_mult", 1.0)) if row["signal"] == "V6_OVER" else 1.0
            stake = br * kelly_pct * mult
        else:
            stake = br * kelly_pct

        # Apply bet result
        won  = bool(row["won"])
        odds = safe_odds(row["over_odds"] if row["bet_direction"] == "OVER"
                         else row["under_odds"])
        if odds < 0:
            gain = stake * (100.0 / abs(odds))
        else:
            gain = stake * (odds / 100.0)

        if won:
            br += gain
        else:
            br -= stake
        total_staked += stake

        peak = max(peak, br)
        trough = min(trough, br)
        dd = (peak - br) / peak * 100.0
        max_drawdown = max(max_drawdown, dd)

        trajectory.append([str(row["game_date"].date()), round(br, 2)])

    roi_pct = (br - starting_bankroll) / starting_bankroll * 100.0

    return {
        "label": label,
        "n_bets": len(df),
        "win_rate": round(float(df["won"].mean()), 4),
        "starting_bankroll": starting_bankroll,
        "final_bankroll": round(br, 2),
        "total_staked": round(total_staked, 2),
        "roi_pct": round(roi_pct, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "peak_bankroll": round(peak, 2),
        "trough_bankroll": round(trough, 2),
        "trajectory": trajectory,
    }


flat_sim    = run_bankroll_sim(bets_df, "FLAT_KELLY",
                                STARTING_BANKROLL, FLAT_KELLY_PCT,
                                use_int16_weight=False)
weighted_sim = run_bankroll_sim(bets_df, "INT16_WEIGHTED",
                                 STARTING_BANKROLL, FLAT_KELLY_PCT,
                                 use_int16_weight=True)

for sim in [flat_sim, weighted_sim]:
    print(f"  {sim['label']:20s} | n={sim['n_bets']} bets | "
          f"final=${sim['final_bankroll']:,.2f} | "
          f"ROI={sim['roi_pct']:+.2f}% | "
          f"max_DD={sim['max_drawdown_pct']:.1f}%")


# ─────────────────────────────────────────────────────────────────────────────
# 8. STATISTICAL SIGNIFICANCE (BONFERRONI alpha=0.025)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[8] Statistical significance (Bonferroni alpha=0.025 for 2 signals)...")

BONFERRONI_ALPHA = 0.025  # 0.05 / 2 signals

def sig_check(stats: dict, alpha: float) -> str:
    if stats["p_value"] is None:
        return "INCONCLUSIVE (insufficient n)"
    if stats["p_value"] < alpha:
        return f"SIGNIFICANT (p={stats['p_value']}, alpha={alpha})"
    return f"NOT significant (p={stats['p_value']}, alpha={alpha})"

v6_sig = sig_check(v6_stats, BONFERRONI_ALPHA)
v8_sig = sig_check(v8_stats, BONFERRONI_ALPHA)
print(f"  V6 OVER  z={v6_stats['z_stat']} p={v6_stats['p_value']}: {v6_sig}")
print(f"  V8 UNDER z={v8_stats['z_stat']} p={v8_stats['p_value']}: {v8_sig}")


# ─────────────────────────────────────────────────────────────────────────────
# 9. HONEST VERDICT
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[9] Honest verdict...")

def build_verdict(stats: dict, season_a: dict, season_b: dict,
                  sig_result: str, signal_name: str) -> dict:
    n = stats["n_real"]
    roi = stats["roi_flat"]
    ci = stats["ci_95"]

    # Stability: both seasons positive
    both_positive = (
        season_a["roi_flat"] is not None and season_a["roi_flat"] > 0 and
        season_b["roi_flat"] is not None and season_b["roi_flat"] > 0
    )
    season_consistency = "CONSISTENT (both seasons positive)" if both_positive \
        else "INCONSISTENT (seasons diverge)"

    # Deployment rec
    if n >= 30 and ci[0] is not None and ci[0] > 0 and both_positive:
        deploy = "SHIP"
    elif n >= 20 and roi is not None and roi > 5.0:
        deploy = "SHIP_WITH_MONITORING"
    elif n < 20:
        deploy = "WAIT_FOR_DATA (n too small)"
    elif roi is not None and roi < 0:
        deploy = "DROP"
    else:
        deploy = "WAIT_FOR_DATA"

    return {
        "signal": signal_name,
        "n_real": n,
        "roi_flat_pct": roi,
        "roi_weighted_pct": stats["roi_int16_weighted"],
        "ci_95": ci,
        "season_consistency": season_consistency,
        "significance": sig_result,
        "deployment_recommendation": deploy,
    }

v6_verdict = build_verdict(v6_stats, v6_2425, v6_2526, v6_sig, "V6_OVER")
v8_verdict = build_verdict(v8_stats, v8_2425, v8_2526, v8_sig, "V8_UNDER")

for v in [v6_verdict, v8_verdict]:
    print(f"  {v['signal']}: n={v['n_real']} roi={v['roi_flat_pct']}% "
          f"CI={v['ci_95']}")
    print(f"    Season consistency: {v['season_consistency']}")
    print(f"    Significance: {v['significance']}")
    print(f"    Deployment: {v['deployment_recommendation']}")


# ─────────────────────────────────────────────────────────────────────────────
# 10. ASSEMBLE FULL OUTPUT JSON
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[10] Saving results JSON...")

output = {
    "meta": {
        "generated": pd.Timestamp.now().isoformat()[:19],
        "version": "INT-V9",
        "title": "Unified Multi-Season Deployment Validation",
        "starting_bankroll": STARTING_BANKROLL,
        "flat_kelly_pct": FLAT_KELLY_PCT,
        "bonferroni_alpha": BONFERRONI_ALPHA,
        "seasons": ["2024-25", "2025-26"],
        "total_pts_lines": int(len(pts_lines)),
        "perim_denial_teams": sorted(perim_denial_teams),
        "n_perim_shooter_players": len(perim_shooter_names),
        "n_elevator_players": len(elevator_names),
        "elevator_players": sorted(elevator_names),
        "conflict_players_in_both_lists": sorted(conflict_player_names),
        "n_v6_bets": len(v6_bets),
        "n_v8_bets": len(v8_bets),
        "n_conflicts_skipped": len(conflict_log),
    },
    "per_signal_pooled": {
        "v6_over": v6_stats,
        "v8_under": v8_stats,
        "conflicts_skipped": conflict_log,
    },
    "per_season_breakdown": {
        "v6_over_2024_25": v6_2425,
        "v6_over_2025_26": v6_2526,
        "v8_under_2024_25": v8_2425,
        "v8_under_2025_26": v8_2526,
    },
    "bankroll_simulation": {
        "flat_kelly": flat_sim,
        "int16_weighted": weighted_sim,
    },
    "verdicts": {
        "v6_over": v6_verdict,
        "v8_under": v8_verdict,
    },
    "v6_bets": v6_bets,
    "v8_bets": v8_bets,
}

out_path = ROOT / "data/intelligence/v9_unified_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2, default=str)
print(f"  Saved: {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 11. PRINT FINAL TABLE SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 72)
print("INT-V9 UNIFIED DEPLOYMENT — FINAL SUMMARY")
print("=" * 72)
print()
print(f"  Bankroll: ${STARTING_BANKROLL:,.0f}")
print(f"  Seasons:  2024-25 + 2025-26 combined")
print(f"  Signals:  V6 OVER + V8 UNDER + CONFLICT detection")
print()
print("  Per-signal results (pooled)")
print(f"  {'signal':<20} {'n_real':>8} {'win_rate':>10} {'flat ROI':>10} {'weighted ROI':>14}")
print("  " + "-" * 66)
for label, stats in [("V6 OVER", v6_stats), ("V8 UNDER", v8_stats)]:
    wr   = f"{stats['win_rate']:.1%}" if stats["win_rate"] else "—"
    roi  = f"{stats['roi_flat']:+.2f}%" if stats["roi_flat"] is not None else "—"
    wroi = (f"{stats['roi_int16_weighted']:+.2f}%"
            if stats["roi_int16_weighted"] is not None else "—")
    print(f"  {label:<20} {stats['n_real']:>8} {wr:>10} {roi:>10} {wroi:>14}")
print(f"  {'CONFLICT (skipped)':<20} {len(conflict_log):>8} {'—':>10} {'—':>10} {'—':>14}")
print()
print("  Bankroll simulation")
print(f"  {'Scenario':<22} {'N bets':>8} {'Final $':>12} {'ROI':>8} {'Max DD':>8}")
print("  " + "-" * 62)
for sim in [flat_sim, weighted_sim]:
    print(f"  {sim['label']:<22} {sim['n_bets']:>8} "
          f"${sim['final_bankroll']:>10,.2f} "
          f"{sim['roi_pct']:>+7.2f}% "
          f"{sim['max_drawdown_pct']:>6.1f}%")
print()
print("  Per-season breakdown")
print(f"  {'signal':<12} {'2024-25 n':>10} {'2025-26 n':>10} "
      f"{'2024-25 ROI':>13} {'2025-26 ROI':>13}")
print("  " + "-" * 62)
print(f"  {'V6 OVER':<12} {v6_2425['n']:>10} {v6_2526['n']:>10} "
      f"{(str(v6_2425['roi_flat'])+'%') if v6_2425['roi_flat'] is not None else '—':>13} "
      f"{(str(v6_2526['roi_flat'])+'%') if v6_2526['roi_flat'] is not None else '—':>13}")
print(f"  {'V8 UNDER':<12} {v8_2425['n']:>10} {v8_2526['n']:>10} "
      f"{(str(v8_2425['roi_flat'])+'%') if v8_2425['roi_flat'] is not None else '—':>13} "
      f"{(str(v8_2526['roi_flat'])+'%') if v8_2526['roi_flat'] is not None else '—':>13}")
print()
print("  Statistical significance (Bonferroni alpha=0.025)")
print(f"  V6: {v6_sig}")
print(f"  V8: {v8_sig}")
print()
print("  Deployment recommendations")
print(f"  V6 OVER: {v6_verdict['deployment_recommendation']}")
print(f"  V8 UNDER: {v8_verdict['deployment_recommendation']}")
print()
print("=" * 72)

print()
print("[V9 complete]")
print(f"  data/intelligence/v9_unified_results.json")
print(f"  vault/Intelligence/V9_Unified_Deployment_Validation.md  (next step)")
