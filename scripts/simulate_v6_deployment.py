# -*- coding: utf-8 -*-
"""
INT-V7 V6 Deployment Simulation
=================================
Simulates applying the V6 depth-2 recipe across ALL eligible 2025-26 games
to compute total simulated P&L on a $1,000 bankroll.

Recipe (V6 depth-2 winner: +7.23% ROI, n=53):
  Player.archetype == "Perimeter Shooter / Transition Wing"  (INT-1)
  Opp scheme contains "PERIMETER DENIAL"                     (INT-12)
  Player.INT-16 pts_confidence_mult > 1.0                    (INT-16)
  → bet OVER PTS

Sizing (INT-16 × INT-39):
  bet_fraction = 0.01 × INT-16_pts_mult × INT-39_adj_pts_mult

4 scenarios:
  FULL_STACK    — recipe + INT-16 × INT-39 sizing
  INT16_ONLY    — recipe + INT-16 sizing only
  NAIVE_KELLY   — recipe + flat 1% sizing
  CONTROL       — any perimeter player vs any opp, flat 1%

Outputs:
  data/intelligence/v6_simulation_results.json
  vault/Intelligence/V6_Deployment_Simulation.md
"""

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from lib_betting_validation import safe_odds  # Bug 10 guard

warnings.filterwarnings("ignore")
np.random.seed(42)

ROOT = Path("C:/Users/neelj/nba-ai-system")

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def norm(s: str) -> str:
    return str(s).strip().lower()


# safe_odds imported from lib_betting_validation above


def pnl_at_odds(won: bool, odds: float, stake: float) -> float:
    """Absolute P&L given stake and American odds."""
    if odds < 0:
        win_amt = stake * (100.0 / abs(odds))
    else:
        win_amt = stake * (odds / 100.0)
    return win_amt if won else -stake


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


def max_drawdown(bankroll_series: list) -> float:
    """Compute maximum drawdown from bankroll trajectory (returns %)."""
    if len(bankroll_series) < 2:
        return 0.0
    peak = bankroll_series[0]
    max_dd = 0.0
    for val in bankroll_series:
        if val > peak:
            peak = val
        dd = (peak - val) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd * 100.0


# ─────────────────────────────────────────────────────────────────────────────
# 1. LOAD DATA SOURCES
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 70)
print("INT-V7 V6 Deployment Simulation")
print("=" * 70)
print()

print("[1] Loading data sources...")

# INT-1: Player fingerprints / archetypes
fp = pd.read_parquet(ROOT / "data/intelligence/player_fingerprints.parquet")
fp = fp.reset_index()
fp["player_norm"] = fp["player_name"].map(norm)
# player_id -> archetype_name
arch_map = dict(zip(fp["player_id"].astype(str), fp["archetype_name"]))
arch_map_by_norm = dict(zip(fp["player_norm"], fp["archetype_name"]))
# player_norm -> player_id
norm_to_pid = dict(zip(fp["player_norm"], fp["player_id"]))
perim_shooter_pids = set(
    fp[fp["archetype_name"].str.contains("Perimeter Shooter", case=False, na=False)]["player_id"].astype(int).tolist()
)
print(f"  INT-1: {len(fp)} players | "
      f"Perimeter Shooters: {len(perim_shooter_pids)} players")

# INT-12: Defensive schemes
schemes = pd.read_parquet(ROOT / "data/intelligence/defensive_schemes.parquet")
schemes["dominant_tag"] = schemes["dominant_tag"].str.strip().str.upper()
schemes["all_tags"] = schemes["all_tags"].str.upper()
# team -> (dominant_tag, all_tags)
team_scheme = dict(zip(schemes["team"].str.upper().str.strip(),
                       schemes.apply(lambda r: {"dominant": r["dominant_tag"],
                                                "all": r["all_tags"]}, axis=1)))
perim_denial_teams = set(
    schemes[schemes["all_tags"].str.contains("PERIMETER DENIAL", na=False)]["team"].str.upper().str.strip().tolist()
)
print(f"  INT-12: {len(schemes)} teams | "
      f"PERIMETER DENIAL teams: {sorted(perim_denial_teams)}")

# INT-16: Per-player confidence multipliers
conf_df = pd.read_parquet(ROOT / "data/intelligence/per_player_confidence.parquet")
conf_df["player_id"] = pd.to_numeric(conf_df["player_id"], errors="coerce")
pts_mult_map = {
    int(pid): float(v)
    for pid, v in zip(conf_df["player_id"], conf_df["pts_confidence_mult"])
    if pd.notna(pid) and pd.notna(v)
}
print(f"  INT-16: {len(conf_df)} players | "
      f"pts_mult > 1.0: {sum(1 for v in pts_mult_map.values() if v > 1.0)}")

# INT-39: CV quality-adjusted Kelly multipliers
with open(ROOT / "data/intelligence/cv_quality_confidence_curves.json",
          encoding="utf-8", errors="replace") as f:
    cq_curves = json.load(f)
qak = cq_curves["quality_adjusted_kelly"]  # {player_id_str: {adj_pts_mult: ...}}
int39_pts_mult_map = {}
for pid_str, entry in qak.items():
    try:
        pid_int = int(pid_str)
        adj_pts = entry.get("adj_pts_mult", 1.0)
        if adj_pts is not None:
            int39_pts_mult_map[pid_int] = float(adj_pts)
    except Exception:
        pass
print(f"  INT-39: {len(int39_pts_mult_map)} players with adj_pts_mult | "
      f"median: {np.median(list(int39_pts_mult_map.values())):.3f}")

# INT-18: Rolling trends (optional cancel filter)
trends = pd.read_parquet(ROOT / "data/intelligence/rolling_trends.parquet")
trends["player_id"] = pd.to_numeric(trends["player_id"], errors="coerce")
cold_pids = set(
    trends[trends["trend_tag"] == "COLD_DECLINE"]["player_id"].dropna().astype(int).tolist()
)
print(f"  INT-18: {len(trends)} trend records | COLD_DECLINE: {len(cold_pids)} players")

# ─────────────────────────────────────────────────────────────────────────────
# 2. LOAD + BUILD LINES POOL
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[2] Loading sportsbook lines (2025-26 season)...")

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

# Filter to 2025-26 season only (Oct 2025 onward)
lines_2526 = lines_pool[lines_pool["date"] >= "2025-10-01"].copy()
lines_pts_2526 = lines_2526[lines_2526["stat"] == "pts"].copy()

print(f"  Total pooled lines: {len(lines_pool):,} | 2025-26 PTS: {len(lines_pts_2526):,}")
print(f"  2025-26 date range: {lines_pts_2526['date'].min().date()} "
      f"to {lines_pts_2526['date'].max().date()}")

# Attach player_id from fingerprints
lines_pts_2526["player_id"] = lines_pts_2526["player_norm"].map(norm_to_pid)
lines_pts_2526["player_id"] = pd.to_numeric(lines_pts_2526["player_id"], errors="coerce")

# Sort chronologically
lines_pts_2526 = lines_pts_2526.sort_values("date").reset_index(drop=True)

# ─────────────────────────────────────────────────────────────────────────────
# 3. IDENTIFY ELIGIBLE BET CANDIDATES FOR RECIPE
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[3] Filtering to eligible bet candidates (V6 depth-2 recipe)...")

def is_perim_shooter(pid) -> bool:
    if pid is None or (isinstance(pid, float) and np.isnan(pid)):
        return False
    try:
        return int(pid) in perim_shooter_pids
    except Exception:
        return False


def is_perim_denial_opp(opp: str) -> bool:
    return str(opp).strip().upper() in perim_denial_teams


def get_pts_mult_int16(pid) -> float:
    if pid is None or (isinstance(pid, float) and np.isnan(pid)):
        return 1.0
    try:
        return pts_mult_map.get(int(pid), 1.0)
    except Exception:
        return 1.0


def get_pts_mult_int39(pid) -> float:
    """INT-39 quality-adjusted pts multiplier. Default 1.0 if not found."""
    if pid is None or (isinstance(pid, float) and np.isnan(pid)):
        return 1.0
    try:
        return int39_pts_mult_map.get(int(pid), 1.0)
    except Exception:
        return 1.0


def is_cold_player(pid) -> bool:
    if pid is None or (isinstance(pid, float) and np.isnan(pid)):
        return False
    try:
        return int(pid) in cold_pids
    except Exception:
        return False


# Annotate all 2025-26 PTS rows with recipe flags
lines_pts_2526["is_perim_shooter"] = lines_pts_2526["player_id"].apply(is_perim_shooter)
lines_pts_2526["is_perim_denial_opp"] = lines_pts_2526["opp"].apply(is_perim_denial_opp)
lines_pts_2526["int16_pts_mult"] = lines_pts_2526["player_id"].apply(get_pts_mult_int16)
lines_pts_2526["int39_pts_mult"] = lines_pts_2526["player_id"].apply(get_pts_mult_int39)
lines_pts_2526["is_cold"] = lines_pts_2526["player_id"].apply(is_cold_player)

# RECIPE candidates: archetype + scheme + INT-16 > 1.0
recipe_mask = (
    lines_pts_2526["is_perim_shooter"] &
    lines_pts_2526["is_perim_denial_opp"] &
    (lines_pts_2526["int16_pts_mult"] > 1.0)
)
recipe_candidates = lines_pts_2526[recipe_mask].copy()

# With INT-18 cancel filter (exclude COLD_DECLINE)
recipe_no_cold = recipe_candidates[~recipe_candidates["is_cold"]].copy()

# CONTROL: any perimeter player vs any opp (no scheme or confidence filter)
# Uses same Perimeter Shooter archetype but no other constraints
control_candidates = lines_pts_2526[lines_pts_2526["is_perim_shooter"]].copy()

print(f"  Perimeter Shooter rows (2025-26): {lines_pts_2526['is_perim_shooter'].sum()}")
print(f"  + vs PERIMETER DENIAL opp: {(lines_pts_2526['is_perim_shooter'] & lines_pts_2526['is_perim_denial_opp']).sum()}")
print(f"  + INT-16 mult > 1.0 (RECIPE candidates): {len(recipe_candidates)}")
print(f"  + INT-18 NOT COLD (recipe_no_cold): {len(recipe_no_cold)}")
print(f"  CONTROL (any perim shooter vs any opp): {len(control_candidates)}")

if len(recipe_candidates) > 0:
    print(f"\n  Recipe candidates detail:")
    print(f"    Players: {sorted(recipe_candidates['player'].unique().tolist())}")
    print(f"    Opps: {sorted(recipe_candidates['opp'].unique().tolist())}")
    print(f"    Date range: {recipe_candidates['date'].min().date()} "
          f"to {recipe_candidates['date'].max().date()}")
    win_rate_raw = (recipe_candidates["actual_value"] > recipe_candidates["closing_line"]).mean()
    print(f"    Raw OVER win rate: {win_rate_raw:.3f}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. SEQUENTIAL BANKROLL SIMULATION
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[4] Running sequential bankroll simulations...")

STARTING_BANKROLL = 1000.0
BASE_KELLY = 0.01  # 1% base


def simulate_sequential(
    candidates: pd.DataFrame,
    scenario_name: str,
    use_int16: bool = True,
    use_int39: bool = True,
    flat_kelly: bool = False,
    starting_bankroll: float = STARTING_BANKROLL,
) -> dict:
    """
    Simulate sequential Kelly betting on the candidate bet rows.
    Returns scenario results dict.
    """
    if len(candidates) == 0:
        return {
            "n_bets": 0,
            "win_rate": None,
            "cumulative_pnl": 0.0,
            "final_bankroll": starting_bankroll,
            "max_drawdown": 0.0,
            "roi_pct": None,
            "bankroll_trajectory": [(None, starting_bankroll)],
            "total_staked": 0.0,
        }

    bankroll = starting_bankroll
    trajectory = [(None, bankroll)]
    wins = 0
    total_staked = 0.0
    bets = []

    for _, row in candidates.sort_values("date").iterrows():
        pid = row.get("player_id")
        date_str = str(row["date"])[:10]
        odds = safe_odds(row.get("over_odds", -110))
        line = float(row["closing_line"])
        actual = float(row["actual_value"])
        won = actual > line

        if flat_kelly:
            bet_frac = BASE_KELLY
        elif use_int16 and not use_int39:
            mult16 = float(row.get("int16_pts_mult", 1.0))
            bet_frac = BASE_KELLY * mult16
        elif use_int16 and use_int39:
            mult16 = float(row.get("int16_pts_mult", 1.0))
            mult39 = float(row.get("int39_pts_mult", 1.0))
            bet_frac = BASE_KELLY * mult16 * mult39
        else:
            bet_frac = BASE_KELLY

        # Cap fraction at 5% to avoid ruin on single bet
        bet_frac = min(bet_frac, 0.05)
        stake = bankroll * bet_frac
        total_staked += stake

        pnl = pnl_at_odds(won, odds, stake)
        bankroll += pnl

        if won:
            wins += 1

        trajectory.append((date_str, round(bankroll, 2)))
        bets.append({
            "date": date_str,
            "player": str(row["player"]),
            "line": line,
            "actual": actual,
            "won": bool(won),
            "stake": round(stake, 2),
            "pnl": round(pnl, 2),
            "bankroll_after": round(bankroll, 2),
            "int16_mult": round(float(row.get("int16_pts_mult", 1.0)), 4),
            "int39_mult": round(float(row.get("int39_pts_mult", 1.0)), 4),
            "opp": str(row["opp"]),
        })

    n = len(bets)
    wr = wins / n if n > 0 else None
    cumulative_pnl = bankroll - starting_bankroll
    roi_pct = (cumulative_pnl / total_staked * 100) if total_staked > 0 else None
    max_dd = max_drawdown([t[1] for t in trajectory])

    wr_display = f"{wr:.3f}" if wr is not None else "N/A"
    roi_display = f"{roi_pct:+.2f}%" if roi_pct is not None else "N/A"
    print(f"  {scenario_name:<20}: n={n:>4} | wr={wr_display} | "
          f"P&L=${cumulative_pnl:+.2f} | ROI={roi_display} | "
          f"final=${bankroll:.2f} | maxDD={max_dd:.1f}%")

    return {
        "n_bets": n,
        "win_rate": round(float(wr), 4) if wr is not None else None,
        "cumulative_pnl": round(float(cumulative_pnl), 2),
        "final_bankroll": round(float(bankroll), 2),
        "max_drawdown": round(float(max_dd), 2),
        "roi_pct": round(float(roi_pct), 2) if roi_pct is not None else None,
        "bankroll_trajectory": trajectory,
        "total_staked": round(float(total_staked), 2),
        "bets": bets,
    }


# Run 4 scenarios
scenarios = {}

print()
print("  Scenario 1: FULL_STACK (recipe + INT-16 × INT-39 sizing)")
scenarios["FULL_STACK"] = simulate_sequential(
    recipe_candidates, "FULL_STACK",
    use_int16=True, use_int39=True, flat_kelly=False
)

print("  Scenario 2: INT16_ONLY (recipe + INT-16 sizing only)")
scenarios["INT16_ONLY"] = simulate_sequential(
    recipe_candidates, "INT16_ONLY",
    use_int16=True, use_int39=False, flat_kelly=False
)

print("  Scenario 3: NAIVE_KELLY (recipe + flat 1% sizing)")
scenarios["NAIVE_KELLY"] = simulate_sequential(
    recipe_candidates, "NAIVE_KELLY",
    flat_kelly=True
)

print("  Scenario 4: CONTROL (any perim shooter vs any opp, flat 1%)")
scenarios["CONTROL"] = simulate_sequential(
    control_candidates, "CONTROL",
    flat_kelly=True
)


# ─────────────────────────────────────────────────────────────────────────────
# 5. COMPUTE COMPARISONS
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[5] Computing comparisons...")

def safe_diff(a, b):
    if a is None or b is None:
        return None
    return round(a - b, 2)


comparisons = {
    "FULL_STACK_vs_CONTROL": {
        "pnl_diff": safe_diff(
            scenarios["FULL_STACK"]["cumulative_pnl"],
            scenarios["CONTROL"]["cumulative_pnl"]
        ),
        "roi_diff": safe_diff(
            scenarios["FULL_STACK"]["roi_pct"],
            scenarios["CONTROL"]["roi_pct"]
        ),
    },
    "FULL_STACK_vs_NAIVE": {
        "pnl_diff": safe_diff(
            scenarios["FULL_STACK"]["cumulative_pnl"],
            scenarios["NAIVE_KELLY"]["cumulative_pnl"]
        ),
        "roi_diff": safe_diff(
            scenarios["FULL_STACK"]["roi_pct"],
            scenarios["NAIVE_KELLY"]["roi_pct"]
        ),
    },
    "INT16_vs_FULL_STACK": {
        "pnl_diff": safe_diff(
            scenarios["INT16_ONLY"]["cumulative_pnl"],
            scenarios["FULL_STACK"]["cumulative_pnl"]
        ),
        "roi_diff": safe_diff(
            scenarios["INT16_ONLY"]["roi_pct"],
            scenarios["FULL_STACK"]["roi_pct"]
        ),
    },
}

print(f"  FULL_STACK vs CONTROL: P&L diff={comparisons['FULL_STACK_vs_CONTROL']['pnl_diff']}, "
      f"ROI diff={comparisons['FULL_STACK_vs_CONTROL']['roi_diff']}pp")
print(f"  FULL_STACK vs NAIVE:   P&L diff={comparisons['FULL_STACK_vs_NAIVE']['pnl_diff']}, "
      f"ROI diff={comparisons['FULL_STACK_vs_NAIVE']['roi_diff']}pp")


# ─────────────────────────────────────────────────────────────────────────────
# 6. SAVE JSON
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[6] Saving JSON output...")

# Trim bankroll_trajectory for JSON (keep every row, they're already chronological)
# Remove bets detail from JSON to keep file manageable
scenarios_json = {}
for name, result in scenarios.items():
    entry = {k: v for k, v in result.items() if k != "bets"}
    # Trim trajectory to (date, bankroll) tuples
    entry["bankroll_trajectory"] = [
        (t[0], t[1]) for t in entry["bankroll_trajectory"]
    ]
    scenarios_json[name] = entry

output = {
    "meta": {
        "generated": "2026-05-28",
        "version": "INT-V7-simulation",
        "starting_bankroll": STARTING_BANKROLL,
        "base_kelly_pct": BASE_KELLY * 100,
        "recipe": {
            "archetype": "Perimeter Shooter / Transition Wing",
            "opp_scheme": "PERIMETER DENIAL",
            "int16_filter": "pts_confidence_mult > 1.0",
            "bet_direction": "OVER PTS",
        },
        "perim_denial_teams": sorted(perim_denial_teams),
        "n_perim_shooter_players": len(perim_shooter_pids),
        "v6_backtest_roi_pct": 7.23,
        "v6_backtest_n": 53,
        "season_filter": "2025-26 (>= 2025-10-01)",
        "total_2526_pts_lines": len(lines_pts_2526),
        "recipe_eligible_bets": len(recipe_candidates),
        "control_eligible_bets": len(control_candidates),
    },
    "scenarios": scenarios_json,
    "comparison": comparisons,
}

out_dir = ROOT / "data/intelligence"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "v6_simulation_results.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, default=str)
print(f"  Saved -> {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. WRITE VAULT DOC
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[7] Writing vault doc...")

def fmt_pct(v):
    if v is None:
        return "N/A"
    return f"{v:+.2f}%"

def fmt_wr(v):
    if v is None:
        return "N/A"
    return f"{v:.3f} ({v*100:.1f}%)"

def fmt_money(v):
    if v is None:
        return "N/A"
    return f"${v:,.2f}"

# Bankroll trajectory narrative (text rendering)
def trajectory_summary(traj: list, name: str) -> str:
    if len(traj) < 2:
        return f"  {name}: No bets placed.\n"
    init_bk = traj[0][1]
    final_bk = traj[-1][1]
    # Peak and trough
    vals = [t[1] for t in traj]
    peak_bk = max(vals)
    trough_bk = min(vals)
    peak_idx = vals.index(peak_bk)
    trough_idx = vals.index(trough_bk)
    peak_date = traj[peak_idx][0] or "start"
    trough_date = traj[trough_idx][0] or "start"
    direction = "grew" if final_bk > init_bk else "DECLINED"
    return (
        f"  {name}: started ${init_bk:.0f} → ended {fmt_money(final_bk)}\n"
        f"    Peak: {fmt_money(peak_bk)} on {peak_date}\n"
        f"    Trough: {fmt_money(trough_bk)} on {trough_date}\n"
        f"    Bankroll {direction} by {fmt_pct((final_bk - init_bk) / init_bk * 100)}\n"
    )


def traj_text_chart(traj: list, name: str, width: int = 50, height: int = 10) -> str:
    """ASCII-art bankroll timeline."""
    if len(traj) < 2:
        return f"  {name}: N/A\n"
    vals = [t[1] for t in traj]
    min_v = min(vals)
    max_v = max(vals)
    if max_v == min_v:
        return f"  {name}: Flat at {fmt_money(vals[-1])}\n"
    rows = []
    for row_i in range(height):
        threshold = max_v - (max_v - min_v) * (row_i / (height - 1))
        line = ""
        for i in range(width):
            idx = int(i * (len(vals) - 1) / (width - 1))
            line += "*" if vals[idx] >= threshold else " "
        prefix = f"  {fmt_money(threshold):>10} |"
        rows.append(prefix + line)
    x_axis = "  " + " " * 12 + "-" * width
    dates = f"  {'start':>12}{'end':>{width-4}}"
    return name + " bankroll trajectory:\n" + "\n".join(rows) + "\n" + x_axis + "\n" + dates + "\n"


# Scenario table rows
def tbl_row(name, s):
    return (
        f"| {name:<20} | {s['n_bets']:>6} | "
        f"{fmt_wr(s['win_rate']):>14} | "
        f"{fmt_money(s['final_bankroll']):>14} | "
        f"{fmt_pct(s['roi_pct']):>8} | "
        f"{s['max_drawdown']:>7.1f}% |"
    )


tbl_header = (
    "| Scenario             | N bets | Win rate        | "
    "Final bankroll  |   ROI    | Max DD  |"
)
tbl_sep = "|" + "-" * 22 + "|" + "-" * 8 + "|" + "-" * 17 + "|" + "-" * 16 + "|" + "-" * 10 + "|" + "-" * 9 + "|"

recipe_eligible = len(recipe_candidates)
control_eligible = len(control_candidates)

fs = scenarios["FULL_STACK"]
i16 = scenarios["INT16_ONLY"]
nk = scenarios["NAIVE_KELLY"]
ctrl = scenarios["CONTROL"]

# Key verdicts
def positive_verdict(s):
    if s["roi_pct"] is None:
        return "INSUFFICIENT DATA"
    if s["roi_pct"] > 5.0:
        return "STRONGLY POSITIVE"
    if s["roi_pct"] > 0:
        return "POSITIVE"
    if s["roi_pct"] > -3.0:
        return "MARGINAL NEGATIVE"
    return "NEGATIVE"

# Receipt signal replication
v6_roi = 7.23
replication = "REPLICATED"
if fs["roi_pct"] is None:
    replication = "INSUFFICIENT DATA"
elif fs["roi_pct"] >= v6_roi * 0.85:
    replication = f"REPLICATED (simulation {fmt_pct(fs['roi_pct'])} vs backtest +7.23%)"
elif fs["roi_pct"] > 0:
    replication = f"UNDERWHELMED (simulation {fmt_pct(fs['roi_pct'])} vs backtest +7.23% -- forward-test degradation)"
else:
    replication = f"FAILED TO REPLICATE (simulation {fmt_pct(fs['roi_pct'])} vs backtest +7.23%)"

int39_effect = ""
if i16["roi_pct"] is not None and fs["roi_pct"] is not None:
    diff = fs["roi_pct"] - i16["roi_pct"]
    if abs(diff) < 0.5:
        int39_effect = f"Minimal (~{diff:+.2f}pp ROI delta) — quality adjustment has small effect on this thin sample"
    elif diff > 0:
        int39_effect = f"Positive (+{diff:.2f}pp ROI delta) — INT-39 quality weighting improved sizing"
    else:
        int39_effect = f"Negative ({diff:.2f}pp ROI delta) — INT-39 quality downweighted winning bets"

sample_note = ""
if recipe_eligible < 20:
    sample_note = (
        f"**WARNING: Only {recipe_eligible} eligible bets** — well below the 50-bet threshold for "
        f"reliable inference. Results are directional only."
    )
elif recipe_eligible < 50:
    sample_note = (
        f"**CAUTION: {recipe_eligible} eligible bets** — below the 50-bet threshold. "
        f"CI is wide; treat as indicative."
    )
else:
    sample_note = (
        f"{recipe_eligible} bets is in the MODERATE range. "
        f"Results carry moderate confidence."
    )

# Trajectory charts
traj_full = traj_text_chart(fs["bankroll_trajectory"], "FULL_STACK")
traj_ctrl = traj_text_chart(ctrl["bankroll_trajectory"], "CONTROL")

md = f"""# V6 Deployment Simulation (2025-26)

> Generated: 2026-05-28
> Version: INT-V7 end-to-end deployment test
> Script: `scripts/simulate_v6_deployment.py`
> JSON: `data/intelligence/v6_simulation_results.json`

## Setup

- **Starting bankroll:** $1,000
- **Base Kelly fraction:** 1% per bet
- **Recipe (V6 depth-2):** PerimShooter × PerimDenial × INT-16 low-vol → OVER PTS
- **PERIMETER DENIAL teams in pool:** {', '.join(sorted(perim_denial_teams))}
- **Perimeter Shooter players:** {len(perim_shooter_pids)} (INT-1)
- **Eligible recipe bets (2025-26):** {recipe_eligible}
- **Control bets (any perim shooter, any opp):** {control_eligible}
- **V6 backtest anchor:** n=53, ROI=+7.23% (flat), weighted=+7.39%

## Scenario Comparison Table

{tbl_header}
{tbl_sep}
{tbl_row('FULL_STACK', fs)}
{tbl_row('INT16_ONLY', i16)}
{tbl_row('NAIVE_KELLY', nk)}
{tbl_row('CONTROL', ctrl)}

## Bankroll Trajectory Commentary

{trajectory_summary(fs['bankroll_trajectory'], 'FULL_STACK')}
{trajectory_summary(ctrl['bankroll_trajectory'], 'CONTROL')}

### FULL_STACK ASCII chart
```
{traj_full}
```

### CONTROL ASCII chart
```
{traj_ctrl}
```

## Sizing Comparison

| Scenario | Base | INT-16 mult | INT-39 mult | Effective frac range |
|----------|------|-------------|-------------|---------------------|
| FULL_STACK | 1% | Yes | Yes | 1% × mult16 × mult39 |
| INT16_ONLY | 1% | Yes | No | 1% × mult16 |
| NAIVE_KELLY | 1% | No | No | flat 1% |
| CONTROL | 1% | No | No | flat 1% (any perim player) |

## Honest Read

### Does the deployment recipe simulate as profitable?
**{positive_verdict(fs)}** — {replication}

### INT-39 quality-adjustment effect
{int39_effect if int39_effect else "N/A (insufficient data for one or both scenarios)"}

### Sample size note
{sample_note}

### Is the +7.23% ROI from V6 replicated?
{replication}

### Key caveats
1. All signals (INT-1 archetypes, INT-12 schemes, INT-16 confidence) are computed on the FULL
   historical dataset including 2025-26 — there is mild look-ahead in the signal labels. The
   deployment recipe should be re-evaluated with rolling/as-of-date signal computation.
2. PERIMETER DENIAL is rare: only {len(perim_denial_teams)} teams carry that tag, so games where
   this matchup occurs are limited throughout the season.
3. INT-39 coverage is sparse ({len(int39_pts_mult_map)} players with CV data); most players
   fall back to the 1.0 default multiplier.
4. The V6 backtest ROI of +7.23% was computed on a pooled multi-season sample that includes
   pre-2025-26 data. This simulation restricts to 2025-26 only — seasonal variation is expected.
5. Sequential Kelly with 1% base and caps at 5% single-bet max is conservative by design.
   Real deployment would use a tighter CI + dynamic re-calibration.

## Comparison to V6 Backtest

| Metric | V6 backtest | Deployment simulation |
|--------|------------|----------------------|
| Recipe | PerimShooter × PerimDenial × INT-16 | Same |
| Bet direction | OVER PTS | OVER PTS |
| N eligible | 53 | {recipe_eligible} |
| Win rate | ~0.566 (implied by +7.23%) | {fmt_wr(fs['win_rate'])} |
| Flat ROI | +7.23% | {fmt_pct(fs['roi_pct'])} |
| Final bankroll | N/A (not sequential) | {fmt_money(fs['final_bankroll'])} |
| Max drawdown | N/A | {fs['max_drawdown']:.1f}% |

---
*See also: [[Deep_Stacking_Validation]], [[Betting_Signal_Ranking]], [[project_loop7_status]]*
"""

vault_dir = ROOT / "vault/Intelligence"
vault_dir.mkdir(parents=True, exist_ok=True)
vault_path = vault_dir / "V6_Deployment_Simulation.md"
with open(vault_path, "w", encoding="utf-8") as f:
    f.write(md)
print(f"  Vault doc saved -> {vault_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 8. FINAL REPORT
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("INT-V7 V6 Deployment Simulation — FINAL REPORT")
print("=" * 70)

print(f"""
Setup
  Bankroll: ${STARTING_BANKROLL:,.0f} starting
  Base Kelly: {BASE_KELLY*100:.0f}%
  Recipe: V6 depth-2 (PerimShooter x PerimDenial x INT-16 low-vol -> OVER PTS)
  PERIMETER DENIAL teams: {sorted(perim_denial_teams)}
  Eligible recipe bets in 2025-26: {recipe_eligible}
  V6 backtest reference: n=53, ROI=+7.23%
""")

print("Scenario comparison")
print(f"  {'Scenario':<20} {'N bets':>6} {'Win rate':>9} {'Final BK':>10} {'ROI':>8} {'MaxDD':>8}")
print("  " + "-" * 67)
for name, s in [("FULL_STACK", fs), ("INT16_ONLY", i16), ("NAIVE_KELLY", nk), ("CONTROL", ctrl)]:
    wr_str = f"{s['win_rate']:.3f}" if s['win_rate'] is not None else "  N/A "
    roi_str = fmt_pct(s['roi_pct'])
    print(f"  {name:<20} {s['n_bets']:>6} {wr_str:>9} "
          f"{fmt_money(s['final_bankroll']):>10} {roi_str:>8} "
          f"{s['max_drawdown']:>7.1f}%")

print()
print("Comparisons")
for k, v in comparisons.items():
    print(f"  {k}: P&L diff={v['pnl_diff']}, ROI diff={v['roi_diff']}pp")

print()
print("Verdict")
print(f"  FULL_STACK: {positive_verdict(fs)}")
print(f"  Replication: {replication}")
print(f"  INT-39 effect: {int39_effect if int39_effect else 'N/A'}")
print(f"  Sample note: {sample_note}")

print(f"""
Files
  scripts/simulate_v6_deployment.py
  data/intelligence/v6_simulation_results.json
  vault/Intelligence/V6_Deployment_Simulation.md
""")
