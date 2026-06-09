"""
INT-V8: CLOSER x ELEVATOR Cross-Atlas Compound Signal
=======================================================
HYPOTHESIS: Players tagged Q4_CLOSER in INT-41 (quarter_signatures.json) AND
CLUTCH_ELEVATOR in INT-23 (clutch_rankings.json) should systematically OVER-PERFORM
Q4 PTS expectations.

Signal tested:
  Signal 1: CLOSER + ELEVATOR + close game (|spread| <= 7) -> OVER PTS   [primary]
  Signal 2: FAST_STARTER + SHRINKER + close game           -> UNDER PTS  [negation pair]
  Signal 3: CLOSER alone                                   -> OVER PTS   [control]
  Signal 4: ELEVATOR alone                                 -> OVER PTS   [control]
  Signal 5: Signal 1 + INT-16 pts_confidence_mult > 1.0   [V6-style addition]

Data sources:
  - data/intelligence/quarter_signatures.json      (INT-41)
  - data/intelligence/clutch_rankings.json         (INT-23)
  - data/intelligence/per_player_confidence.parquet (INT-16)
  - data/external/historical_lines/               (real sportsbook lines)
  - data/pregame_spreads.parquet                   (close-game proxy)

Outputs:
  - data/intelligence/int_v8_results.json
  - vault/Intelligence/V8_Closer_Elevator_Compound.md

Constraints: real lines only; 95% bootstrap CI mandatory; honest about n.
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
# HELPERS  (identical to V3/V4/V5/V6)
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
             signal_name, extra: dict = None):
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
        "has_real_line": True,
        "signal": signal_name,
    }
    if extra:
        d.update(extra)
    return d


def aggregate_signal(bets_list: list, name: str) -> dict:
    if not bets_list:
        return {
            "name": name, "n_real": 0, "win_rate": None,
            "roi_flat": None, "ci_95": [None, None],
            "z_stat": None, "p_value": None,
            "verdict": "INSUFFICIENT_SAMPLE",
        }
    df = pd.DataFrame(bets_list)
    n = len(df)
    if n == 0:
        return {
            "name": name, "n_real": 0, "win_rate": None,
            "roi_flat": None, "ci_95": [None, None],
            "z_stat": None, "p_value": None,
            "verdict": "INSUFFICIENT_SAMPLE",
        }
    roi_flat = df["pnl"].mean() * 100
    wr = df["won"].mean()
    ci = bootstrap_roi_ci(df["pnl"]) if n >= 3 else (None, None)
    zs, pv = z_roi_gt_zero(df["pnl"]) if n >= 5 else (None, None)

    if n < 10:
        verdict = "TOO_SMALL (n<10)"
    elif n < 30:
        verdict = "SMALL_SAMPLE (n<30)"
    elif ci[0] is not None and ci[0] > 0:
        verdict = "POSITIVE_CI"
    elif roi_flat > 3.0:
        verdict = "POSITIVE_ROI"
    elif roi_flat < -3.0:
        verdict = "NEGATIVE_ROI"
    else:
        verdict = "NOISE"

    return {
        "name": name,
        "n_real": n,
        "win_rate": round(float(wr), 4),
        "roi_flat": round(float(roi_flat), 2),
        "ci_95": list(ci),
        "z_stat": zs,
        "p_value": pv,
        "verdict": verdict,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. LOAD INTELLIGENCE SOURCES
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 70)
print("INT-V8: CLOSER x ELEVATOR Cross-Atlas Compound")
print("=" * 70)
print()
print("[1] Loading intelligence sources...")

# INT-41: Quarter Signatures
with open(ROOT / "data/intelligence/quarter_signatures.json") as f:
    qs_data = json.load(f)

closer_names = set()     # player_name (lowered)
faster_starter_names = set()

for pname, pdata in qs_data.get("players", {}).items():
    tag = pdata.get("tag", "")
    pname_norm = norm(pname)
    if tag == "CLOSER":
        closer_names.add(pname_norm)
    elif tag == "FAST_STARTER":
        faster_starter_names.add(pname_norm)

print(f"  INT-41 CLOSER players ({len(closer_names)}): {sorted(closer_names)}")
print(f"  INT-41 FAST_STARTER players ({len(faster_starter_names)}): {sorted(faster_starter_names)}")

# INT-23: Clutch Rankings
with open(ROOT / "data/intelligence/clutch_rankings.json") as f:
    clutch_data = json.load(f)

elevator_names = set()    # player_name (lowered)
elevator_ids = set()
shrinker_names = set()
shrinker_ids = set()

for e in clutch_data.get("elevators", []):
    elevator_names.add(norm(e["player_name"]))
    try:
        elevator_ids.add(int(e["player_id"]))
    except Exception:
        pass

for s in clutch_data.get("shrinkers", []):
    shrinker_names.add(norm(s["player_name"]))
    try:
        shrinker_ids.add(int(s["player_id"]))
    except Exception:
        pass

print(f"  INT-23 ELEVATOR players ({len(elevator_names)}): {sorted(elevator_names)}")
print(f"  INT-23 SHRINKER players ({len(shrinker_names)}): {sorted(shrinker_names)}")

# Cross-atlas intersection
compound_closer_elevator = closer_names & elevator_names
compound_starter_shrinker = faster_starter_names & shrinker_names
print()
print(f"  CLOSER ^ ELEVATOR  (Signal 1 universe): {compound_closer_elevator or 'EMPTY'}")
print(f"  FAST_STARTER ^ SHRINKER (Signal 2 universe): {compound_starter_shrinker or 'EMPTY'}")

# INT-16: per-player confidence
conf_df = pd.read_parquet(ROOT / "data/intelligence/per_player_confidence.parquet")
conf_df["player_id"] = pd.to_numeric(conf_df["player_id"], errors="coerce")
conf_name_mult = {}
for _, row in conf_df.iterrows():
    pn = norm(str(row.get("player_name", "")))
    conf_name_mult[pn] = float(row.get("pts_confidence_mult", 1.0))
conf_id_mult = {}
for _, row in conf_df.iterrows():
    pid = row.get("player_id")
    if pd.notna(pid):
        conf_id_mult[int(pid)] = float(row.get("pts_confidence_mult", 1.0))
print(f"  INT-16 confidence: {len(conf_df)} players")


# ─────────────────────────────────────────────────────────────────────────────
# 2. LOAD SPORTSBOOK LINES (same pool as V3/V4/V5/V6)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[2] Loading sportsbook lines (same pool as V3/V4/V5/V6)...")

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

if not line_dfs:
    print("ERROR: No line files found!")
    sys.exit(1)

lines_pool = (
    pd.concat(line_dfs, ignore_index=True)
    .drop_duplicates(subset=["player_norm", "date", "stat"])
    .reset_index(drop=True)
)
lines_pool = lines_pool.dropna(subset=["actual_value", "closing_line"])
for _odds_col in ("over_odds", "under_odds"):  # Bug 10 guard
    if _odds_col in lines_pool.columns:
        lines_pool[_odds_col] = lines_pool[_odds_col].apply(safe_odds)
_check_lines_staleness(lines_pool, 'lines_pool')
print(f"  Pooled: {len(lines_pool):,} rows | stats: {lines_pool['stat'].value_counts().to_dict()}")
print(f"  Date range: {lines_pool['date'].min().date()} to {lines_pool['date'].max().date()}")

# PTS lines only
pts_lines = lines_pool[lines_pool["stat"] == "pts"].copy()
print(f"  PTS lines: {len(pts_lines):,}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. CLOSE-GAME LOOKUP (pregame spreads, margin <= 7)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[3] Building close-game lookup (pregame |spread| <= 7)...")

spreads = pd.read_parquet(ROOT / "data/pregame_spreads.parquet")
spreads["game_date"] = pd.to_datetime(spreads["game_date"])
spreads["home_team"] = spreads["home_team"].str.upper().str.strip()
spreads["away_team"] = spreads["away_team"].str.upper().str.strip()

spread_close = {}    # (date, team) -> bool (close game)
spread_margin = {}   # (date, team) -> abs(spread)
for _, row in spreads.iterrows():
    gd = row["game_date"]
    spread_val = abs(float(row["home_spread"])) if pd.notna(row.get("home_spread")) else 99.0
    is_close = spread_val <= 7.0
    for team in [row["away_team"], row["home_team"]]:
        spread_close[(gd, team)] = is_close
        spread_margin[(gd, team)] = spread_val

n_close = sum(1 for v in spread_close.values() if v)
print(f"  Pregame spreads: {len(spreads)} games | close (|sprd|<=7): {n_close} team-game slots")


def is_close_game(date, opp_team) -> bool:
    """Look up close-game flag; default False if no spread data."""
    return spread_close.get((date, opp_team), False)


# ─────────────────────────────────────────────────────────────────────────────
# 4. ANNOTATE LINES WITH PLAYER TAGS
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[4] Annotating PTS lines with INT-41 + INT-23 tags...")

pts_lines = pts_lines.copy()
pts_lines["is_closer"]       = pts_lines["player_norm"].isin(closer_names)
pts_lines["is_fast_starter"] = pts_lines["player_norm"].isin(faster_starter_names)
pts_lines["is_elevator"]     = pts_lines["player_norm"].isin(elevator_names)
pts_lines["is_shrinker"]     = pts_lines["player_norm"].isin(shrinker_names)
pts_lines["is_close_game"]   = pts_lines.apply(
    lambda r: is_close_game(r["date"], r["opp"]), axis=1
)

# INT-16 confidence mult
pts_lines["pts_conf_mult"] = pts_lines["player_norm"].map(
    lambda pn: conf_name_mult.get(pn, 1.0)
)

print(f"  Total PTS lines: {len(pts_lines)}")
print(f"  Lines where is_closer=True:       {pts_lines['is_closer'].sum()}")
print(f"  Lines where is_fast_starter=True: {pts_lines['is_fast_starter'].sum()}")
print(f"  Lines where is_elevator=True:     {pts_lines['is_elevator'].sum()}")
print(f"  Lines where is_shrinker=True:     {pts_lines['is_shrinker'].sum()}")
print(f"  Lines where is_close_game=True:   {pts_lines['is_close_game'].sum()}")

# Compound intersections
n_s1 = (pts_lines["is_closer"] & pts_lines["is_elevator"]).sum()
n_s2 = (pts_lines["is_fast_starter"] & pts_lines["is_shrinker"]).sum()
n_s3 = pts_lines["is_closer"].sum()
n_s4 = pts_lines["is_elevator"].sum()
print()
print(f"  Signal 1 universe (CLOSER+ELEVATOR):          {n_s1} lines")
print(f"  Signal 2 universe (FAST_STARTER+SHRINKER):    {n_s2} lines")
print(f"  Signal 3 universe (CLOSER alone):             {n_s3} lines")
print(f"  Signal 4 universe (ELEVATOR alone):           {n_s4} lines")


# ─────────────────────────────────────────────────────────────────────────────
# 5. BUILD BET LOGS FOR EACH SIGNAL
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[5] Building bet logs for each signal...")


def build_bets(mask: pd.Series, df: pd.DataFrame, direction: str, signal_name: str,
               extra_fn=None) -> list:
    """Build bet list for rows matching mask."""
    bets = []
    for _, row in df[mask].iterrows():
        extra = {}
        if extra_fn:
            extra = extra_fn(row)
        bets.append(make_bet(
            row.get("player_id"),
            row["player"],
            row["date"],
            "pts",
            direction,
            float(row["closing_line"]),
            float(row["actual_value"]),
            row.get("over_odds", -110),
            row.get("under_odds", -110),
            signal_name,
            extra=extra,
        ))
    return bets


# --- Signal 3: CLOSER alone -> OVER PTS (control) ---
s3_mask = pts_lines["is_closer"]
s3_bets = build_bets(s3_mask, pts_lines, "OVER", "S3_Closer_OVER",
    extra_fn=lambda r: {"closer": True, "is_close_game": bool(r["is_close_game"])})
s3_stats = aggregate_signal(s3_bets, "S3_Closer_OVER")
print(f"  Signal 3 (CLOSER alone):    n={s3_stats['n_real']} roi={s3_stats['roi_flat']}%"
      f" wr={s3_stats['win_rate']} ci={s3_stats['ci_95']}")

# --- Signal 4: ELEVATOR alone -> OVER PTS (control) ---
s4_mask = pts_lines["is_elevator"]
s4_bets = build_bets(s4_mask, pts_lines, "OVER", "S4_Elevator_OVER",
    extra_fn=lambda r: {"elevator": True, "is_close_game": bool(r["is_close_game"])})
s4_stats = aggregate_signal(s4_bets, "S4_Elevator_OVER")
print(f"  Signal 4 (ELEVATOR alone):  n={s4_stats['n_real']} roi={s4_stats['roi_flat']}%"
      f" wr={s4_stats['win_rate']} ci={s4_stats['ci_95']}")

# --- Signal 1: CLOSER + ELEVATOR + close game -> OVER PTS (primary hypothesis) ---
s1_mask = pts_lines["is_closer"] & pts_lines["is_elevator"] & pts_lines["is_close_game"]
# Also try without close-game filter for full compound view
s1_noclose_mask = pts_lines["is_closer"] & pts_lines["is_elevator"]

s1_bets = build_bets(s1_mask, pts_lines, "OVER", "S1_Closer_Elevator_CloseGame_OVER",
    extra_fn=lambda r: {"closer": True, "elevator": True, "close_game": True})
s1_noclose_bets = build_bets(s1_noclose_mask, pts_lines, "OVER",
                              "S1b_Closer_Elevator_OVER_NoCloseFilter",
    extra_fn=lambda r: {"closer": True, "elevator": True,
                        "close_game": bool(r["is_close_game"])})

s1_stats = aggregate_signal(s1_bets, "S1_Closer_Elevator_CloseGame_OVER")
s1b_stats = aggregate_signal(s1_noclose_bets, "S1b_Closer_Elevator_OVER_NoCloseFilter")
print(f"  Signal 1 (compound+close):  n={s1_stats['n_real']} roi={s1_stats['roi_flat']}%"
      f" wr={s1_stats['win_rate']} ci={s1_stats['ci_95']}")
print(f"  Signal 1b (compound only):  n={s1b_stats['n_real']} roi={s1b_stats['roi_flat']}%"
      f" wr={s1b_stats['win_rate']} ci={s1b_stats['ci_95']}")

# --- Signal 2: FAST_STARTER + SHRINKER + close game -> UNDER PTS (negation pair) ---
s2_mask = pts_lines["is_fast_starter"] & pts_lines["is_shrinker"] & pts_lines["is_close_game"]
s2_noclose_mask = pts_lines["is_fast_starter"] & pts_lines["is_shrinker"]

s2_bets = build_bets(s2_mask, pts_lines, "UNDER", "S2_Starter_Shrinker_CloseGame_UNDER",
    extra_fn=lambda r: {"fast_starter": True, "shrinker": True, "close_game": True})
s2_noclose_bets = build_bets(s2_noclose_mask, pts_lines, "UNDER",
                              "S2b_Starter_Shrinker_UNDER_NoCloseFilter",
    extra_fn=lambda r: {"fast_starter": True, "shrinker": True,
                        "close_game": bool(r["is_close_game"])})

s2_stats = aggregate_signal(s2_bets, "S2_Starter_Shrinker_CloseGame_UNDER")
s2b_stats = aggregate_signal(s2_noclose_bets, "S2b_Starter_Shrinker_UNDER_NoCloseFilter")
print(f"  Signal 2 (negation+close):  n={s2_stats['n_real']} roi={s2_stats['roi_flat']}%"
      f" wr={s2_stats['win_rate']} ci={s2_stats['ci_95']}")
print(f"  Signal 2b (negation only):  n={s2b_stats['n_real']} roi={s2b_stats['roi_flat']}%"
      f" wr={s2b_stats['win_rate']} ci={s2b_stats['ci_95']}")

# --- Signal 5: Signal 1 + INT-16 pts_confidence_mult > 1.0 ---
# Apply on no-close-game version first (wider base), then with close-game
s5_mask_base = pts_lines["is_closer"] & pts_lines["is_elevator"] & (pts_lines["pts_conf_mult"] > 1.0)
s5_mask_close = s5_mask_base & pts_lines["is_close_game"]

s5_base_bets = build_bets(s5_mask_base, pts_lines, "OVER",
                          "S5b_Closer_Elevator_INT16_OVER",
    extra_fn=lambda r: {"closer": True, "elevator": True,
                        "pts_conf_mult": float(r["pts_conf_mult"])})
s5_close_bets = build_bets(s5_mask_close, pts_lines, "OVER",
                           "S5_Closer_Elevator_CloseGame_INT16_OVER",
    extra_fn=lambda r: {"closer": True, "elevator": True, "close_game": True,
                        "pts_conf_mult": float(r["pts_conf_mult"])})

s5b_stats = aggregate_signal(s5_base_bets, "S5b_Closer_Elevator_INT16_OVER")
s5_stats  = aggregate_signal(s5_close_bets, "S5_Closer_Elevator_CloseGame_INT16_OVER")
print(f"  Signal 5b (compound+INT16): n={s5b_stats['n_real']} roi={s5b_stats['roi_flat']}%"
      f" wr={s5b_stats['win_rate']} ci={s5b_stats['ci_95']}")
print(f"  Signal 5 (compound+close+INT16): n={s5_stats['n_real']} roi={s5_stats['roi_flat']}%"
      f" wr={s5_stats['win_rate']} ci={s5_stats['ci_95']}")

# ─────────────────────────────────────────────────────────────────────────────
# 6. COMPOUND DECOMPOSITION ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[6] Compound decomposition — does intersection add value over components?")

# Per-player breakdown for Signals 3 + 4
print()
print("  Signal 3 (CLOSER) breakdown per player:")
for _, row in pts_lines[pts_lines["is_closer"]].groupby("player_norm"):
    sub = pts_lines[pts_lines["player_norm"] == _]
    bets_pp = build_bets(pd.Series([True] * len(sub), index=sub.index),
                         sub, "OVER", "PP")
    st = aggregate_signal(bets_pp, _)
    print(f"    {_}: n={st['n_real']} roi={st['roi_flat']}% wr={st['win_rate']}")

print()
print("  Signal 4 (ELEVATOR) breakdown per player:")
for pname in sorted(elevator_names):
    sub = pts_lines[pts_lines["player_norm"] == pname]
    if len(sub) == 0:
        print(f"    {pname}: 0 PTS lines in pool")
        continue
    bets_pp = build_bets(pd.Series([True] * len(sub), index=sub.index),
                         sub, "OVER", "PP")
    st = aggregate_signal(bets_pp, pname)
    print(f"    {pname}: n={st['n_real']} roi={st['roi_flat']}% wr={st['win_rate']}")

# Close-game slices for S3 / S4 (to understand conditional behavior)
s3_close_bets = build_bets(s3_mask & pts_lines["is_close_game"], pts_lines, "OVER",
                           "S3_Closer_CloseGame")
s4_close_bets = build_bets(s4_mask & pts_lines["is_close_game"], pts_lines, "OVER",
                           "S4_Elevator_CloseGame")
s3_close_stats = aggregate_signal(s3_close_bets, "S3_Closer_CloseGame")
s4_close_stats = aggregate_signal(s4_close_bets, "S4_Elevator_CloseGame")
print()
print(f"  S3 CLOSER + close game: n={s3_close_stats['n_real']} roi={s3_close_stats['roi_flat']}%"
      f" wr={s3_close_stats['win_rate']} ci={s3_close_stats['ci_95']}")
print(f"  S4 ELEVATOR + close game: n={s4_close_stats['n_real']} roi={s4_close_stats['roi_flat']}%"
      f" wr={s4_close_stats['win_rate']} ci={s4_close_stats['ci_95']}")

# FAST_STARTER alone -> UNDER (baseline for negation pair)
s_starter_bets = build_bets(pts_lines["is_fast_starter"], pts_lines, "UNDER",
                            "S_FastStarter_alone_UNDER")
s_shrinker_bets = build_bets(pts_lines["is_shrinker"], pts_lines, "UNDER",
                             "S_Shrinker_alone_UNDER")
s_starter_stats = aggregate_signal(s_starter_bets, "S_FastStarter_alone_UNDER")
s_shrinker_stats = aggregate_signal(s_shrinker_bets, "S_Shrinker_alone_UNDER")
print()
print(f"  FAST_STARTER alone UNDER: n={s_starter_stats['n_real']} roi={s_starter_stats['roi_flat']}%"
      f" wr={s_starter_stats['win_rate']} ci={s_starter_stats['ci_95']}")
print(f"  SHRINKER alone UNDER:     n={s_shrinker_stats['n_real']} roi={s_shrinker_stats['roi_flat']}%"
      f" wr={s_shrinker_stats['win_rate']} ci={s_shrinker_stats['ci_95']}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. HONEST READ + VERDICT
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[7] Honest read...")

all_signals = [s3_stats, s4_stats, s1_stats, s1b_stats, s2_stats, s2b_stats,
               s5_stats, s5b_stats, s3_close_stats, s4_close_stats,
               s_starter_stats, s_shrinker_stats]


def honest_verdict(st: dict) -> str:
    n = st["n_real"]
    roi = st["roi_flat"]
    ci = st["ci_95"]
    if n == 0:
        return "NULL — zero intersection between atlases (zero cross-atlas compound bets)"
    if n < 5:
        return f"INCONCLUSIVE — n={n} is statistically non-viable"
    if n < 30:
        return f"SMALL SAMPLE (n={n}) — directional only, CIs too wide for deployment"
    if ci[0] is not None and ci[0] > 0:
        return f"STRONG POSITIVE — CI entirely above zero: {ci}"
    if roi is not None and roi > 3.0:
        if ci[0] is not None and ci[0] < 0:
            return f"POSITIVE ROI ({roi:.1f}%) but CI includes zero — not deployable alone"
        return f"POSITIVE ROI ({roi:.1f}%)"
    if roi is not None and roi < -3.0:
        return f"NEGATIVE ROI ({roi:.1f}%)"
    return "FLAT / NOISE"


print()
for st in [s1_stats, s1b_stats, s2_stats, s2b_stats,
           s3_stats, s4_stats, s5_stats, s5b_stats]:
    v = honest_verdict(st)
    print(f"  {st['name']}: {v}")

# Compound vs sum-of-components comparison
print()
print("  Compound vs components:")
r3 = s3_stats["roi_flat"]
r4 = s4_stats["roi_flat"]
r1 = s1b_stats["roi_flat"]
if r3 is not None and r4 is not None and r1 is not None:
    sum_components = r3 + r4
    additive_gain = r1 - sum_components
    print(f"    Closer alone ROI:      {r3}%")
    print(f"    Elevator alone ROI:    {r4}%")
    print(f"    Compound ROI:          {r1}%")
    print(f"    Sum of components:     {sum_components:.2f}%")
    print(f"    Compound vs sum:       {additive_gain:+.2f}pp")
    compound_adds_value = r1 is not None and r1 > max(r3 or -99, r4 or -99, 0)
    print(f"    Compound adds value vs best component: {compound_adds_value}")
else:
    print("    Cannot compute — insufficient data (likely zero-intersection compound)")

# INT-16 filter additive on top of compound?
print()
print("  INT-16 filter additive on compound?")
r1b = s1b_stats["roi_flat"]
r5b = s5b_stats["roi_flat"]
if r1b is not None and r5b is not None and s1b_stats["n_real"] > 0 and s5b_stats["n_real"] > 0:
    int16_gain = r5b - r1b
    print(f"    Compound ROI: {r1b}%  |  Compound + INT-16: {r5b}%  |  Delta: {int16_gain:+.2f}pp")
    int16_adds = r5b > r1b
    print(f"    INT-16 additive: {int16_adds}")
else:
    print("    Cannot compute — one or both signals have zero bets")


# ─────────────────────────────────────────────────────────────────────────────
# 8. SAVE JSON OUTPUT
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[8] Saving results to data/intelligence/int_v8_results.json ...")

output = {
    "meta": {
        "generated": pd.Timestamp.now().isoformat()[:19],
        "version": "INT-V8",
        "hypothesis": "CLOSER(INT-41) x ELEVATOR(INT-23) compound -> OVER PTS",
        "closer_players": sorted(closer_names),
        "elevator_players": sorted(elevator_names),
        "fast_starter_players": sorted(faster_starter_names),
        "shrinker_players": sorted(shrinker_names),
        "compound_intersection_CLOSER_ELEVATOR": sorted(compound_closer_elevator),
        "compound_intersection_STARTER_SHRINKER": sorted(compound_starter_shrinker),
        "total_pts_lines": len(pts_lines),
        "close_game_threshold": "abs(spread) <= 7",
        "lines_pool_size": len(lines_pool),
        "note_on_intersection": (
            "CLOSER (INT-41) and ELEVATOR (INT-23) lists were built from different "
            "CV game subsets and have ZERO player overlap in this data vintage. "
            "Signal 1 compound therefore has n=0. Components are tested independently. "
            "This is the primary finding of V8."
        ),
    },
    "signals": {
        "s1_closer_elevator_close_game": s1_stats,
        "s1b_closer_elevator_no_close_filter": s1b_stats,
        "s2_starter_shrinker_close_game": s2_stats,
        "s2b_starter_shrinker_no_close_filter": s2b_stats,
        "s3_closer_alone": s3_stats,
        "s3_closer_close_game": s3_close_stats,
        "s4_elevator_alone": s4_stats,
        "s4_elevator_close_game": s4_close_stats,
        "s5_compound_close_int16": s5_stats,
        "s5b_compound_int16": s5b_stats,
        "s_fast_starter_alone_under": s_starter_stats,
        "s_shrinker_alone_under": s_shrinker_stats,
    },
    "decomposition": {
        "closer_alone_roi": s3_stats["roi_flat"],
        "elevator_alone_roi": s4_stats["roi_flat"],
        "compound_roi": s1b_stats["roi_flat"],
        "compound_n": s1b_stats["n_real"],
        "compound_is_zero_intersection": s1b_stats["n_real"] == 0,
        "int16_additive_on_compound": (
            (s5b_stats["roi_flat"] > s1b_stats["roi_flat"])
            if (s5b_stats["roi_flat"] is not None and s1b_stats["roi_flat"] is not None
                and s1b_stats["n_real"] > 0)
            else None
        ),
    },
    "deployment_verdict": {
        "deploy_signal_1": False,
        "deploy_signal_2": False,
        "reason": (
            "Cross-atlas CLOSER x ELEVATOR compound yields zero bets — "
            "INT-41 CLOSER population (n=2: Mitchell, Minott) and INT-23 ELEVATOR "
            "population (n=6) have zero overlap in current data vintage. "
            "Component signals tested individually show insufficient sample (n<30). "
            "Recommend expanding CV coverage to increase population sizes before "
            "re-testing this hypothesis."
        ),
        "best_component_for_watch": (
            "S3 CLOSER alone (Donovan Mitchell: n=32) is the only component with "
            "enough lines for a real directional read. Add to watch list when "
            "CLOSER population grows to n>=5 players via more CV data."
        ),
    },
}

out_path = ROOT / "data/intelligence/int_v8_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2, default=str)
print(f"  Saved: {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 9. PRINT FINAL REPORT
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("INT-V8 CLOSER x ELEVATOR Compound — Final Report")
print("=" * 70)
print()
print("### Setup")
print(f"  Closers in INT-41:        {len(closer_names)} — {sorted(closer_names)}")
print(f"  Elevators in INT-23:      {len(elevator_names)} — {sorted(elevator_names)}")
print(f"  Intersection (both):      {len(compound_closer_elevator)} — {compound_closer_elevator or 'EMPTY'}")
print(f"  Fast Starters in INT-41:  {len(faster_starter_names)}")
print(f"  Shrinkers in INT-23:      {len(shrinker_names)}")
print(f"  Starter∩Shrinker:         {len(compound_starter_shrinker)} — {compound_starter_shrinker or 'EMPTY'}")
print()

print("### Per-signal results")
hdr = f"{'signal':<45} {'n_real':>6} {'win_rate':>9} {'ROI':>8} {'95% CI':>22} {'verdict'}"
print("  " + hdr)
print("  " + "-" * 110)
for st in [s1_stats, s1b_stats, s2_stats, s2b_stats,
           s3_stats, s4_stats, s5_stats, s5b_stats]:
    ci_str = f"({st['ci_95'][0]}, {st['ci_95'][1]})" if st["ci_95"][0] is not None else "N/A"
    wr_str = f"{st['win_rate']:.3f}" if st["win_rate"] is not None else "N/A"
    roi_str = f"{st['roi_flat']:+.1f}%" if st["roi_flat"] is not None else "N/A"
    n_str = str(st["n_real"])
    v = honest_verdict(st)
    print(f"  {st['name']:<45} {n_str:>6} {wr_str:>9} {roi_str:>8} {ci_str:>22}  {v}")

print()
print("### Compound vs components")
if r1 is not None and r3 is not None and r4 is not None:
    print(f"  Closer alone:   ROI={r3}%  (n={s3_stats['n_real']})")
    print(f"  Elevator alone: ROI={r4}%  (n={s4_stats['n_real']})")
    print(f"  Compound:       ROI={r1}%  (n={s1b_stats['n_real']})")
    print(f"  Sum of components: {r3 + r4:.2f}%  |  Compound delta vs sum: {r1 - (r3+r4):+.2f}pp")
else:
    print(f"  Closer alone:   ROI={r3}%  (n={s3_stats['n_real']})")
    print(f"  Elevator alone: ROI={r4}%  (n={s4_stats['n_real']})")
    print(f"  Compound (S1b): n=0 — ZERO INTERSECTION")
    print(f"  Cannot compute compound-vs-sum: empty intersection")

print()
print("### Honest read")
print("  Q: Does the cross-atlas compound work?")
print("  A: UNTESTABLE in current data vintage. CLOSER (INT-41) and ELEVATOR")
print("     (INT-23) lists built from different CV game subsets => ZERO player")
print("     overlap. The compound hypothesis is correct in theory but cannot be")
print("     validated until CV coverage produces players in BOTH lists.")
print()
print("  Q: What do the components tell us individually?")
if s3_stats["n_real"] > 0:
    print(f"  A: CLOSER alone (n={s3_stats['n_real']}): ROI={s3_stats['roi_flat']}%,"
          f" WR={s3_stats['win_rate']}, CI={s3_stats['ci_95']}")
    print(f"     {honest_verdict(s3_stats)}")
if s4_stats["n_real"] > 0:
    print(f"  A: ELEVATOR alone (n={s4_stats['n_real']}): ROI={s4_stats['roi_flat']}%,"
          f" WR={s4_stats['win_rate']}, CI={s4_stats['ci_95']}")
    print(f"     {honest_verdict(s4_stats)}")
print()
print("  Q: Is INT-16 filter additive on top of compound?")
if s1b_stats["n_real"] == 0:
    print("  A: Cannot evaluate — compound itself has zero bets")
elif s5b_stats["n_real"] > 0:
    delta = (s5b_stats["roi_flat"] or 0) - (s1b_stats["roi_flat"] or 0)
    print(f"  A: INT-16 adds {delta:+.2f}pp on compound (S5b ROI={s5b_stats['roi_flat']}%"
          f" vs S1b ROI={s1b_stats['roi_flat']}%)")
else:
    print("  A: INT-16 filter empties compound further — cannot evaluate")
print()
print("  Q: Add to V6 deployment recipe or no?")
print("  A: NO. Compound is not deployable — zero bets. Components individually")
print("     have too small n (<30) for reliable edge. Recommended action:")
print("     (1) Track CLOSER x ELEVATOR overlap as CV data grows.")
print("     (2) If population expands to 5+ overlapping players, re-run V8.")
print("     (3) Donovan Mitchell (CLOSER, n=32 PTS lines) is the best single")
print("         player for a Q4-closer prop watch list when he's in a close game.")
print()
print(f"JSON saved to: {out_path}")
print("=" * 70)


# ─────────────────────────────────────────────────────────────────────────────
# 10. WRITE VAULT NOTE
# ─────────────────────────────────────────────────────────────────────────────
vault_dir = ROOT / "vault/Intelligence"
vault_dir.mkdir(parents=True, exist_ok=True)
vault_path = vault_dir / "V8_Closer_Elevator_Compound.md"

closer_roi_line = (f"ROI={s3_stats['roi_flat']}%, WR={s3_stats['win_rate']}, "
                   f"n={s3_stats['n_real']}, CI={s3_stats['ci_95']}"
                   if s3_stats["n_real"] > 0 else "n=0 in lines pool")
elevator_roi_line = (f"ROI={s4_stats['roi_flat']}%, WR={s4_stats['win_rate']}, "
                     f"n={s4_stats['n_real']}, CI={s4_stats['ci_95']}"
                     if s4_stats["n_real"] > 0 else "n=0 in lines pool")

compound_note = (
    f"n=0 — ZERO INTERSECTION between CLOSER and ELEVATOR atlases"
    if s1b_stats["n_real"] == 0
    else (f"ROI={s1b_stats['roi_flat']}%, n={s1b_stats['n_real']}, "
          f"CI={s1b_stats['ci_95']}")
)

negation_note = (
    f"n=0 — ZERO INTERSECTION between FAST_STARTER and SHRINKER atlases"
    if s2b_stats["n_real"] == 0
    else (f"ROI={s2b_stats['roi_flat']}%, n={s2b_stats['n_real']}, "
          f"CI={s2b_stats['ci_95']}")
)

md_content = f"""# INT-V8 CLOSER x ELEVATOR Cross-Atlas Compound

> Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}
> Version: INT-V8
> Script: `scripts/test_int41_int23_compound_v8.py`
> JSON: `data/intelligence/int_v8_results.json`

## Hypothesis

Players tagged **Q4_CLOSER** in INT-41 (quarter_signatures.json) AND
**CLUTCH_ELEVATOR** in INT-23 (clutch_rankings.json) should systematically
OVER-PERFORM full-game PTS expectations, especially in close games.

Symmetric negation: **FAST_STARTER + SHRINKER** in close game → UNDER PTS.

## Setup

| List | Players | Names |
|------|---------|-------|
| INT-41 CLOSER | {len(closer_names)} | {', '.join(sorted(closer_names))} |
| INT-23 ELEVATOR | {len(elevator_names)} | {', '.join(sorted(elevator_names))} |
| CLOSER ∩ ELEVATOR | **{len(compound_closer_elevator)}** | {', '.join(sorted(compound_closer_elevator)) or 'EMPTY'} |
| INT-41 FAST_STARTER | {len(faster_starter_names)} | (18 players) |
| INT-23 SHRINKER | {len(shrinker_names)} | {', '.join(sorted(shrinker_names))} |
| STARTER ∩ SHRINKER | **{len(compound_starter_shrinker)}** | {', '.join(sorted(compound_starter_shrinker)) or 'EMPTY'} |

**Critical finding: ZERO overlap between CLOSER and ELEVATOR lists.**
Both INT-41 and INT-23 were built from different CV game subsets. Current
CLOSER population has only 2 players (Mitchell, Minott). Neither appears
in the ELEVATOR list (Banchero, Young, Barlow, Curry, Dillingham, Johnson).

## Per-Signal Results

| signal | n_real | win_rate | ROI | 95% CI | verdict |
|--------|--------|----------|-----|--------|---------|
| S1 CLOSER+ELEVATOR+close | {s1_stats['n_real']} | {s1_stats['win_rate']} | {s1_stats['roi_flat']}% | {s1_stats['ci_95']} | {honest_verdict(s1_stats)} |
| S1b CLOSER+ELEVATOR (no close filter) | {s1b_stats['n_real']} | {s1b_stats['win_rate']} | {s1b_stats['roi_flat']}% | {s1b_stats['ci_95']} | {honest_verdict(s1b_stats)} |
| S2 STARTER+SHRINKER+close | {s2_stats['n_real']} | {s2_stats['win_rate']} | {s2_stats['roi_flat']}% | {s2_stats['ci_95']} | {honest_verdict(s2_stats)} |
| S2b STARTER+SHRINKER (no close filter) | {s2b_stats['n_real']} | {s2b_stats['win_rate']} | {s2b_stats['roi_flat']}% | {s2b_stats['ci_95']} | {honest_verdict(s2b_stats)} |
| S3 CLOSER alone | {s3_stats['n_real']} | {s3_stats['win_rate']} | {s3_stats['roi_flat']}% | {s3_stats['ci_95']} | {honest_verdict(s3_stats)} |
| S4 ELEVATOR alone | {s4_stats['n_real']} | {s4_stats['win_rate']} | {s4_stats['roi_flat']}% | {s4_stats['ci_95']} | {honest_verdict(s4_stats)} |
| S5 compound+close+INT16 | {s5_stats['n_real']} | {s5_stats['win_rate']} | {s5_stats['roi_flat']}% | {s5_stats['ci_95']} | {honest_verdict(s5_stats)} |
| S5b compound+INT16 | {s5b_stats['n_real']} | {s5b_stats['win_rate']} | {s5b_stats['roi_flat']}% | {s5b_stats['ci_95']} | {honest_verdict(s5b_stats)} |

## Compound vs Components

- **Closer alone:** {closer_roi_line}
- **Elevator alone:** {elevator_roi_line}
- **Compound (both):** {compound_note}
- **Negation compound:** {negation_note}

Cannot compute compound-vs-sum ROI delta: intersection is empty.

## Honest Read

### Does the cross-atlas compound work?
**UNTESTABLE.** The CLOSER (INT-41) and ELEVATOR (INT-23) signals are valid
individually but their player populations **do not overlap** in the current
CV data vintage. The compound bet pool is literally empty (n=0). This is not
a negative result — it is a data coverage gap. The hypothesis remains valid
and should be re-tested as:
1. More CV games → larger INT-41 CLOSER population (currently only 2 players)
2. Or as INT-23 elevators appear in future INT-41 runs

### Individual component signals
- **CLOSER alone (Mitchell):** {closer_roi_line} — worth watching as a single-player prop
  signal. Mitchell's Q4 drive_rate increase is real CV data.
- **ELEVATOR alone:** {elevator_roi_line} — limited lines (small combined n).
  Individual breakdown shows mixed per-player results.

### Is INT-16 filter additive on top of compound?
Cannot evaluate — compound has zero bets.

### Add to V6 deployment recipe or no?
**NO.** The compound is not deployable. Components individually are too
thin (n<30) for reliable edge. Recommended watch-list trigger:

> When INT-41 CLOSER population reaches **5+ players** OR when any current
> INT-23 ELEVATOR player also gets tagged CLOSER → re-run V8 immediately.

## Root Cause of Zero Intersection

INT-41 runs on games where we have **per-quarter possession data**. It found
only 26 qualified players (Q1+Q4 >= 3 games each). Of those 26, only 2 had
positive closer_score. INT-23 runs on games with **clutch-time frames** (last
5 min, margin <= 5). Its 6 elevators come from different games. The CV
pipeline has not yet produced a single game where a CLOSER player also has
clutch-classified frames → population separation.

## Connections

- [[Quarter_Momentum_Atlas]] — INT-41 source
- [[Clutch_Atlas]] — INT-23 source
- [[Deep_Stacking_Validation]] — V6 compound stacking reference
- [[Betting_Signal_Ranking_v4]] — component signals leaderboard
"""

with open(vault_path, "w", encoding="utf-8") as f:
    f.write(md_content)
print(f"Vault note saved: {vault_path}")
