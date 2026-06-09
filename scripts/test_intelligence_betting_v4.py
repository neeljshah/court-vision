"""
INT-V4 Extended Betting Signal Backtest
========================================
Tests 12 signals: re-runs V3's #1 + 11 new from INT-20/INT-22/INT-23.

Signals:
  V3 re-run:
   1.  perimeter_vs_perim_denial_OVER_pts  (V3 #1)

  INT-20 — position × scheme:
   2.  C_vs_perim_denial_OVER_pts
   3.  C_vs_iso_force_OVER_pts
   4.  PG_vs_perim_denial_OVER_pts
   5.  C_vs_paint_first_OVER_reb
   6.  C_vs_iso_force_OVER_reb
   7.  PG_vs_perim_denial_OVER_ast

  INT-22 — fatigue / altitude:
   8.  B2B_UNDER_reb
   9.  altitude_UNDER_reb

  INT-23 — clutch:
  10.  clutch_elevator_close_game_OVER_pts
  11.  clutch_shrinker_close_game_UNDER_pts

  Combined:
  12.  B2B_AND_low_volatility_UNDER_pts

Outputs:
  data/models/intelligence_betting_v4_results.json
  vault/Intelligence/Betting_Signal_Ranking_v4.md
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


def aggregate_bets(df: pd.DataFrame, signal_name: str, confidence: pd.DataFrame = None):
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

    roi_weighted = None
    if confidence is not None and len(real_df) > 0 and "player_id" in real_df.columns:
        stat_col = signal_name.split("_")[-1]
        mult_col = f"{stat_col}_confidence_mult"
        if mult_col not in confidence.columns:
            mult_col = "overall_confidence_mult"
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
print("INT-V4 Extended Betting Signal Backtest (12 signals)")
print("=" * 70)

print("\n[1] Loading data sources...")

# OOF actuals
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

# Player fingerprints (archetypes)
fp = pd.read_parquet(ROOT / "data/intelligence/player_fingerprints.parquet")
fp = fp.reset_index()
fp["player_norm"] = fp["player_name"].map(norm)
fp = fp[["player_id", "player_norm", "archetype_name"]].copy()
print(f"  Archetypes: {len(fp)} players")

# Defensive schemes
schemes = pd.read_parquet(ROOT / "data/intelligence/defensive_schemes.parquet")
schemes["dominant_tag"] = schemes["dominant_tag"].str.strip().str.upper()
schemes["all_tags"] = schemes["all_tags"].str.upper()
print(f"  Defensive schemes: {len(schemes)} teams")

# Player positions (INT-20 requires C/PG/SF)
pp = pd.read_parquet(ROOT / "data/player_positions.parquet")
pp = pp[["player_id", "position"]].copy()
# Map raw position strings to simplified canonical position codes
def map_position(pos_str: str) -> str:
    """Map NBA API position string to simplified canonical: C, PF, SF, SG, PG."""
    if pd.isna(pos_str):
        return "UNKNOWN"
    p = pos_str.strip().upper()
    if p in ("CENTER", "CENTER-FORWARD", "FORWARD-CENTER"):
        return "C"
    if p in ("FORWARD", "POWER FORWARD", "FORWARD-CENTER"):
        return "PF"
    if p == "SMALL FORWARD":
        return "SF"
    if p in ("FORWARD-GUARD", "GUARD-FORWARD"):
        return "SF"  # treat swing as SF for analysis
    if p in ("SHOOTING GUARD",):
        return "SG"
    if p in ("GUARD",):
        return "PG"  # NBA API lumps PG/SG into "Guard"; will re-split below
    return "UNKNOWN"

# More precise mapping using NBA API position strings
POSITION_MAP = {
    "Guard": "PG",               # treat all Guards as potential PG for INT-20 PG signals
    "Center-Forward": "C",
    "Forward-Center": "C",
    "Forward": "SF",
    "Forward-Guard": "SF",
    "Center": "C",
    "Guard-Forward": "PG",
}
pp["pos_canonical"] = pp["position"].map(lambda x: POSITION_MAP.get(str(x).strip(), "UNKNOWN"))
print(f"  Player positions: {len(pp)} | canonical dist: {pp['pos_canonical'].value_counts().to_dict()}")

# Position×scheme interactions parquet (INT-20)
psi = pd.read_parquet(ROOT / "data/intelligence/position_scheme_interactions.parquet")
print(f"  Position×scheme interactions: {len(psi)} rows")

# Rest/travel (INT-22)
rt = pd.read_parquet(ROOT / "data/rest_travel.parquet")
rt["game_date"] = pd.to_datetime(rt["game_date"])
print(f"  Rest/travel: {len(rt):,} rows | B2B count: {rt['is_b2b'].sum():.0f}")

# Clutch rankings (INT-23)
with open(ROOT / "data/intelligence/clutch_rankings.json") as f:
    clutch_data = json.load(f)
elevator_ids = set(int(p["player_id"]) for p in clutch_data.get("elevators", []))
shrinker_ids = set(int(p["player_id"]) for p in clutch_data.get("shrinkers", []))
print(f"  Clutch: {len(elevator_ids)} elevators, {len(shrinker_ids)} shrinkers")


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
# 3. BUILD LOOKUP TABLES
# ─────────────────────────────────────────────────────────────────────────────
print("\n[3] Building lookup tables...")

# Archetype × scheme lookup (same as V3)
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

# Position × scheme lookup (INT-20)
# Join lines with player positions (on player_norm), then with schemes (on opp)
pos_lines = lines_pool.merge(
    fp[["player_id", "player_norm"]],
    on="player_norm",
    how="inner"
)
pos_lines = pos_lines.merge(
    pp[["player_id", "pos_canonical"]],
    on="player_id",
    how="left"
)
pos_lines = pos_lines.merge(
    schemes[["team", "dominant_tag", "all_tags"]],
    left_on="opp",
    right_on="team",
    how="inner"
)
print(f"  Position×Scheme game-lines: {len(pos_lines):,} rows")
print(f"  pos_canonical dist in pos_lines: {pos_lines['pos_canonical'].value_counts().to_dict()}")

# B2B / altitude lookup (INT-22)
# lines_pool has player, opp, venue, date
# rest_travel has team, game_date, is_b2b, altitude_ft
# Approach: player's TEAM is the one tired on B2B.
# We don't have player→team in lines_pool directly; use venue to determine
# if player is home or away, then opp for away=opp, home=home_team
# Simpler: use lines_pool date+player_norm and join to OOF for game_id,
# then join to rest_travel on game_id + player's team.
# But OOF doesn't have team either.
# Alternative: use lines_pool opp + venue:
#   if venue == 'home', player's team != opp → we can't get team from lines alone
# Best available: join lines_pool to rest_travel on game_date + player-side team.
# Since rest_travel has team + game_date, and lines has opp + venue + date:
#   if venue=='away', player's team = the team that traveled → rest_travel on (opp != opp... confusing)
# Cleanest: build a date+opp→is_b2b lookup. For "UNDER REB on B2B", the signal is:
#   the PLAYER is on B2B → their team is in rest_travel with is_b2b=1 on that date.
# Since lines has opp (opponent), and venue:
#   venue=='home': player's team = NOT opp (unknown). Use opp to find B2B for opponent's away game? No.
#   venue=='away': player's team traveling → match on opp_not_opp... still need player's team.
# Workaround: use lines_pool 'player_norm' → merge with OOF on player_norm + date to get game_id,
# then join game_id to rest_travel.

# Build player_norm → player_id map from lines+fp
player_norm_to_id = dict(zip(pos_lines["player_norm"], pos_lines["player_id"]))

# Build game_id lookup: OOF has (player_id, game_id, game_date)
oof_game_map = oof[["player_id", "game_id", "game_date"]].drop_duplicates()
oof_game_map["game_date"] = pd.to_datetime(oof_game_map["game_date"])

# For rest_travel: team + game_date → is_b2b, altitude_ft
rt_lookup = rt.set_index(["game_id", "team_abbreviation"])[["is_b2b", "altitude_ft"]].copy()

# For join: lines→ OOF (player_id+date) → game_id → rest_travel
# First build player_norm→player_id from fp (broader than arch_lines/pos_lines)
fn_norm_id = dict(zip(fp["player_norm"], fp["player_id"]))
lines_pool_copy = lines_pool.copy()
lines_pool_copy["player_id"] = lines_pool_copy["player_norm"].map(fn_norm_id)

# Join to OOF to get game_id
lines_with_gid = lines_pool_copy.dropna(subset=["player_id"]).merge(
    oof_game_map.rename(columns={"game_date": "oof_game_date"}),
    left_on=["player_id", "date"],
    right_on=["player_id", "oof_game_date"],
    how="left"
)
print(f"  Lines with game_id matched: {lines_with_gid['game_id'].notna().sum():,} / {len(lines_with_gid):,}")

# Join to rest_travel: need team abbreviation from game_id
# rest_travel has (game_id, team_abbreviation). Lines_pool has (player, opp, venue).
# The player's team: if venue=='home' → player's team is determined by home team.
# rest_travel one row per team per game — join on game_id alone to get both teams' rows,
# then pick the one that is NOT the opp.
rt_by_game = rt[["game_id", "team_abbreviation", "is_b2b", "altitude_ft"]].copy()

# Join lines to rest_travel on game_id
lines_rt = lines_with_gid.merge(
    rt_by_game,
    on="game_id",
    how="left"
)
# Filter to rows where team_abbreviation != opp (i.e., player's own team)
# For home players: their team != opp
# For away players: their team == traveling team → also != opp (since opp is the home team)
# Actually: opp in lines_pool is always the OPPONENT of the player.
# So player's team = team_abbreviation where team_abbreviation != opp
lines_rt_player = lines_rt[
    lines_rt["team_abbreviation"].notna() &
    (lines_rt["team_abbreviation"].str.upper() != lines_rt["opp"].str.upper())
].copy()
# Drop duplicate rows (shouldn't be many if game_id is unique per player)
lines_rt_player = lines_rt_player.drop_duplicates(subset=["player_norm", "date", "stat"])
print(f"  Lines with B2B/altitude context: {len(lines_rt_player):,} rows")
print(f"  B2B games in lines_rt_player: {(lines_rt_player['is_b2b'] == 1).sum()}")
print(f"  Altitude > 4000ft in lines_rt_player: {(lines_rt_player['altitude_ft'] > 4000).sum()}")

# For close-game signal (INT-23):
# We need game final margin. Use lines_pool date + opp with linescore_context (rolling blowout data)
# or approximate "projected close game" using pregame_spreads.
# pregame_spreads: game_date, home_team, away_team, home_spread
# A "projected close game" = |home_spread| <= 3.5 (line within 3.5 pts) as pregame proxy
# For lines that don't have a spread match, use the actual final margin from OOF if available.
# NOTE: INT-23 says "final margin <= 7" but we need to predict this BEFORE the game.
# We'll use two approaches:
#   A) Pregame proxy: |closing spread| <= 3.5 → "projected close"
#   B) Post-hoc actual: use player-level data where we know the game happened
# Since sportsbook lines have closing_line (player prop), not game spread, we'll approximate
# using pregame_spreads on date + opp matching.

spreads = pd.read_parquet(ROOT / "data/pregame_spreads.parquet")
spreads["game_date"] = pd.to_datetime(spreads["game_date"])
# Normalize team abbreviations
spreads["home_team"] = spreads["home_team"].str.upper().str.strip()
spreads["away_team"] = spreads["away_team"].str.upper().str.strip()

# Build date+opp → spread lookup (projected close = |spread| <= 3.5)
spread_close = {}
for _, row in spreads.iterrows():
    gd = row["game_date"]
    spread_val = abs(float(row["home_spread"])) if pd.notna(row["home_spread"]) else 99.0
    is_close = spread_val <= 3.5
    # Both teams' perspectives
    spread_close[(gd, row["away_team"])] = is_close   # home is the opp for away player
    spread_close[(gd, row["home_team"])] = is_close   # away is the opp for home player

print(f"  Pregame spreads loaded: {len(spreads)} games")
projected_close_count = sum(1 for v in spread_close.values() if v)
print(f"  Projected close games (|spread|<=3.5): {projected_close_count}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. BET-BUILDING HELPERS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[4] Building bet logs for each signal...")

BET_LOGS = {}


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


def archetype_scheme_signal(arch_keyword: str, scheme_keyword: str,
                             stat: str, bet_dir: str, signal_name: str,
                             check_all_tags: bool = True):
    """V3-compatible: fire when archetype contains keyword AND opp scheme contains keyword."""
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
    print(f"  [{signal_name}] fired={len(bets)} bets")
    return bets


def position_scheme_signal(pos_code: str, scheme_keyword: str,
                            stat: str, bet_dir: str, signal_name: str,
                            check_all_tags: bool = True):
    """
    INT-20: fire when player's canonical position == pos_code AND
    opponent scheme contains scheme_keyword.
    All bets have real lines (from pos_lines).
    """
    mask_pos = pos_lines["pos_canonical"] == pos_code
    if check_all_tags:
        mask_scheme = pos_lines["all_tags"].str.contains(scheme_keyword, case=False, na=False)
    else:
        mask_scheme = pos_lines["dominant_tag"].str.contains(scheme_keyword, case=False, na=False)
    mask_stat = pos_lines["stat"] == stat
    sub = pos_lines[mask_pos & mask_scheme & mask_stat].copy()

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
            extra={"pos_canonical": pos_code, "opp_scheme": row["dominant_tag"]}
        ))
    print(f"  [{signal_name}] fired={len(bets)} bets (pos={pos_code}, scheme='{scheme_keyword}', stat={stat})")
    return bets


def rest_signal(flag_col: str, flag_val, stat: str, bet_dir: str, signal_name: str):
    """
    INT-22: fire when player's team has flag_col == flag_val on game date.
    Uses lines_rt_player which already filters to the player's own team row.
    """
    mask = (lines_rt_player[flag_col] == flag_val) & (lines_rt_player["stat"] == stat)
    sub = lines_rt_player[mask].copy()

    bets = []
    for _, row in sub.iterrows():
        bets.append(make_bet(
            player_id=row.get("player_id"),
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
            extra={flag_col: float(row[flag_col]) if pd.notna(row[flag_col]) else None}
        ))
    print(f"  [{signal_name}] fired={len(bets)} bets (flag_col={flag_col}={flag_val}, stat={stat})")
    return bets


def altitude_signal(altitude_threshold: float, stat: str, bet_dir: str, signal_name: str):
    """
    INT-22: fire when the GAME venue altitude > threshold for AWAY players.
    altitude_ft in rest_travel is the venue altitude — affects both teams' CV,
    but the REB signal targets visiting players (paint_time drops for road team).
    """
    # Only fire for players who are AWAY (venue == 'away' in lines)
    mask = (
        (lines_rt_player["altitude_ft"] > altitude_threshold) &
        (lines_rt_player["stat"] == stat) &
        (lines_rt_player["venue"].str.lower() == "away")
    )
    sub = lines_rt_player[mask].copy()

    bets = []
    for _, row in sub.iterrows():
        bets.append(make_bet(
            player_id=row.get("player_id"),
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
            extra={"altitude_ft": float(row["altitude_ft"]) if pd.notna(row["altitude_ft"]) else None}
        ))
    print(f"  [{signal_name}] fired={len(bets)} bets (altitude>{altitude_threshold}ft, away only, stat={stat})")
    return bets


def clutch_signal(player_id_set: set, bet_dir: str, stat: str, signal_name: str):
    """
    INT-23: fire when player is clutch elevator/shrinker AND pregame spread is close.
    Close game proxy: |spread| <= 3.5 points.
    """
    stat_lines = lines_pool[lines_pool["stat"] == stat].copy()
    # Map player_norm → player_id
    stat_lines["pid"] = stat_lines["player_norm"].map(fn_norm_id)
    stat_lines["pid_int"] = pd.to_numeric(stat_lines["pid"], errors="coerce")

    # Is this player in the clutch set?
    mask_clutch = stat_lines["pid_int"].apply(
        lambda x: (not pd.isna(x)) and (int(x) in player_id_set)
    )

    # Is game projected close?
    def is_projected_close(row):
        return spread_close.get((row["date"], row["opp"]), False)

    stat_lines["projected_close"] = stat_lines.apply(is_projected_close, axis=1)
    mask_close = stat_lines["projected_close"] == True

    sub = stat_lines[mask_clutch & mask_close].copy()

    bets = []
    for _, row in sub.iterrows():
        bets.append(make_bet(
            player_id=row.get("pid_int"),
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
            extra={"projected_close": True}
        ))
    print(f"  [{signal_name}] fired={len(bets)} bets "
          f"(n_clutch_players={len(player_id_set)}, projected_close_via_spread)")
    return bets


def combined_b2b_lowvol(b2b_bets: list, conf_df: pd.DataFrame,
                        stat: str, confidence_threshold: float,
                        signal_name: str):
    """
    Signal 12: B2B UNDER + low volatility filter (INT-16 multiplier > threshold).
    """
    mult_col = f"{stat}_confidence_mult"
    if mult_col not in conf_df.columns:
        mult_col = "overall_confidence_mult"

    pid_to_mult = dict(zip(conf_df["player_id"], conf_df[mult_col]))

    filtered = []
    for bet in b2b_bets:
        pid = bet.get("player_id")
        if pid is None:
            continue
        mult = pid_to_mult.get(int(pid), 1.0)
        if mult > confidence_threshold:
            b = dict(bet)
            b["signal"] = signal_name
            b["confidence_mult"] = float(mult)
            filtered.append(b)

    print(f"  [{signal_name}] fired={len(filtered)} from {len(b2b_bets)} B2B bets "
          f"(confidence_mult>{confidence_threshold})")
    return filtered


# ─────────────────────────────────────────────────────────────────────────────
# 5. FIRE ALL 12 SIGNALS
# ─────────────────────────────────────────────────────────────────────────────

# ── Signal 1: V3 re-run — Perimeter Shooter vs PERIMETER DENIAL → OVER PTS ──
BET_LOGS["perimeter_vs_perim_denial_OVER_pts"] = archetype_scheme_signal(
    "Perimeter Shooter", "PERIMETER DENIAL", "pts", "OVER", "perimeter_vs_perim_denial_OVER_pts"
)

# ── INT-20 Signals ────────────────────────────────────────────────────────────

# Signal 2: C vs PERIMETER DENIAL → OVER PTS (t=4.93, +1.20 PTS)
BET_LOGS["C_vs_perim_denial_OVER_pts"] = position_scheme_signal(
    "C", "PERIMETER DENIAL", "pts", "OVER", "C_vs_perim_denial_OVER_pts"
)

# Signal 3: C vs ISO FORCE → OVER PTS (t=5.68, +1.09 PTS)
BET_LOGS["C_vs_iso_force_OVER_pts"] = position_scheme_signal(
    "C", "ISO FORCE", "pts", "OVER", "C_vs_iso_force_OVER_pts"
)

# Signal 4: PG vs PERIMETER DENIAL → OVER PTS (t=6.84, +0.88 PTS)
BET_LOGS["PG_vs_perim_denial_OVER_pts"] = position_scheme_signal(
    "PG", "PERIMETER DENIAL", "pts", "OVER", "PG_vs_perim_denial_OVER_pts"
)

# Signal 5: C vs PAINT-FIRST → OVER REB (t=2.47, +0.32 REB)
BET_LOGS["C_vs_paint_first_OVER_reb"] = position_scheme_signal(
    "C", "PAINT-FIRST", "reb", "OVER", "C_vs_paint_first_OVER_reb"
)

# Signal 6: C vs ISO FORCE → OVER REB (t=2.42, +0.31 REB)
BET_LOGS["C_vs_iso_force_OVER_reb"] = position_scheme_signal(
    "C", "ISO FORCE", "reb", "OVER", "C_vs_iso_force_OVER_reb"
)

# Signal 7: PG vs PERIMETER DENIAL → OVER AST (t=5.66, +0.25 AST)
BET_LOGS["PG_vs_perim_denial_OVER_ast"] = position_scheme_signal(
    "PG", "PERIMETER DENIAL", "ast", "OVER", "PG_vs_perim_denial_OVER_ast"
)

# ── INT-22 Signals ────────────────────────────────────────────────────────────

# Signal 8: B2B → UNDER REB (paint_time_pct -2.6%, t=-3.85, p=0.0002)
BET_LOGS["B2B_UNDER_reb"] = rest_signal("is_b2b", 1.0, "reb", "UNDER", "B2B_UNDER_reb")

# Signal 9: Altitude road game → UNDER REB (near_basket_pct -3.9%, t=-3.06, p=0.005)
# DEN altitude = 5183ft, UTA = 4327ft — threshold 4000ft
BET_LOGS["altitude_UNDER_reb"] = altitude_signal(4000.0, "reb", "UNDER", "altitude_UNDER_reb")

# ── INT-23 Signals ────────────────────────────────────────────────────────────

# Signal 10: Clutch elevator + projected close game → OVER PTS
BET_LOGS["clutch_elevator_close_game_OVER_pts"] = clutch_signal(
    elevator_ids, "OVER", "pts", "clutch_elevator_close_game_OVER_pts"
)

# Signal 11: Clutch shrinker + projected close game → UNDER PTS
BET_LOGS["clutch_shrinker_close_game_UNDER_pts"] = clutch_signal(
    shrinker_ids, "UNDER", "pts", "clutch_shrinker_close_game_UNDER_pts"
)

# ── Combined Signal ───────────────────────────────────────────────────────────

# Signal 12: B2B + low volatility → UNDER PTS
# Build base B2B bets for pts first
b2b_pts_bets = rest_signal("is_b2b", 1.0, "pts", "UNDER", "_b2b_pts_base")
BET_LOGS["B2B_AND_low_volatility_UNDER_pts"] = combined_b2b_lowvol(
    b2b_pts_bets, conf_df, "pts", 1.0, "B2B_AND_low_volatility_UNDER_pts"
)


# ─────────────────────────────────────────────────────────────────────────────
# 6. AGGREGATE PER SIGNAL
# ─────────────────────────────────────────────────────────────────────────────
print("\n[5] Aggregating per-signal stats...")

signal_results = {}
for sname, bets in BET_LOGS.items():
    df_bets = pd.DataFrame(bets) if bets else pd.DataFrame()
    res = aggregate_bets(df_bets, sname, conf_df)
    signal_results[sname] = res
    print(
        f"  {sname}:\n"
        f"    n_bets={res['n_bets']} | n_real={res['n_real_line_bets']} | "
        f"wr={res['win_rate_real']} | roi={res['roi_real_flat']}% | "
        f"ci={res['ci_95']} | z={res['z_stat']} p={res['p_value']} | {res['verdict']}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. INT-16 KELLY WEIGHTING
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

    stat_part = sname.split("_")[-1]
    mult_col = f"{stat_part}_confidence_mult"
    if mult_col not in conf_df.columns:
        mult_col = "overall_confidence_mult"

    if "player_id" in real_df.columns:
        pid_to_mult = dict(zip(conf_df["player_id"], conf_df[mult_col]))
        real_df["mult"] = real_df["player_id"].map(
            lambda p: pid_to_mult.get(int(p), 1.0) if (p is not None and not pd.isna(p)) else 1.0
        )
        w_sum = real_df["mult"].sum()
        weighted_roi = float((real_df["pnl"] * real_df["mult"]).sum() / w_sum * 100) if w_sum > 0 else flat_roi
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
# 8. COMBINED SIGNAL PRECISION ANALYSIS (B2B alone vs B2B+low-vol)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[7] Combined signal precision analysis...")

b2b_base_name = "B2B_UNDER_reb"
b2b_comb_name = "B2B_AND_low_volatility_UNDER_pts"

b2b_res = signal_results[b2b_base_name]
comb_res = signal_results[b2b_comb_name]

precision_analysis = {
    "base_signal": {
        "name": b2b_base_name,
        "n_real": b2b_res["n_real_line_bets"],
        "win_rate": b2b_res["win_rate_real"],
        "roi": b2b_res["roi_real_flat"],
    },
    "combined_signal": {
        "name": b2b_comb_name,
        "n_real": comb_res["n_real_line_bets"],
        "win_rate": comb_res["win_rate_real"],
        "roi": comb_res["roi_real_flat"],
    },
    "precision_helps": (
        (comb_res["roi_real_flat"] or -99) > (b2b_res["roi_real_flat"] or -99)
        if comb_res["n_real_line_bets"] > 0 else None
    ),
    "sample_reduction_pct": round(
        100 * (1 - comb_res["n_real_line_bets"] / max(b2b_res["n_real_line_bets"], 1)), 1
    ),
}
print(f"  B2B base: n={precision_analysis['base_signal']['n_real']} roi={precision_analysis['base_signal']['roi']}%")
print(f"  B2B+lowvol: n={precision_analysis['combined_signal']['n_real']} roi={precision_analysis['combined_signal']['roi']}%")
print(f"  Precision helps? {precision_analysis['precision_helps']}")


# ─────────────────────────────────────────────────────────────────────────────
# 9. RANDOM BASELINE
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
# 10. BUG 13 CROSS-CHECK: PERIMETER DENIAL confound with weak teams
# ─────────────────────────────────────────────────────────────────────────────
print("\n[9] Bug 13 cross-check: PERIMETER DENIAL team quality confound...")

# Load defensive scheme data to check avg def_rtg of PERIMETER DENIAL teams
bug13_analysis = {}

# For PERIMETER DENIAL signals, check what teams are triggering
pd_signals = [
    "C_vs_perim_denial_OVER_pts",
    "PG_vs_perim_denial_OVER_pts",
    "PG_vs_perim_denial_OVER_ast",
    "perimeter_vs_perim_denial_OVER_pts",
]

for sname in pd_signals:
    bets = BET_LOGS.get(sname, [])
    if not bets:
        bug13_analysis[sname] = {"n": 0, "note": "no bets fired"}
        continue
    df_b = pd.DataFrame(bets)
    # Check which opp teams appear
    if "opp_scheme" in df_b.columns:
        opp_schemes = df_b["opp_scheme"].value_counts().head(5).to_dict()
    else:
        opp_schemes = {}

    # Look up defensive ratings for these opponents
    # schemes parquet has team + dominant_tag
    pd_teams = schemes[schemes["all_tags"].str.contains("PERIMETER DENIAL", na=False)]["team"].tolist()
    # Try to get defensive rating from team_advanced_stats
    adv_path = ROOT / "data/team_advanced_stats.parquet"
    if adv_path.exists():
        adv = pd.read_parquet(adv_path)
        drtg_col = None
        for c in adv.columns:
            if "def_rtg" in c.lower() or "defensive_rating" in c.lower():
                drtg_col = c
                break
        if drtg_col and "team_abbreviation" in adv.columns:
            pd_team_rtg = adv[adv["team_abbreviation"].isin(pd_teams)][["team_abbreviation", drtg_col]].drop_duplicates()
            all_team_rtg = adv[drtg_col].mean()
            pd_avg_rtg = pd_team_rtg[drtg_col].mean()
            bug13_analysis[sname] = {
                "n_bets": len(df_b),
                "n_real": df_b["has_real_line"].sum() if "has_real_line" in df_b.columns else len(df_b),
                "roi": signal_results[sname]["roi_real_flat"],
                "pd_teams": pd_teams[:10],
                "pd_team_avg_def_rtg": round(float(pd_avg_rtg), 1) if not pd.isna(pd_avg_rtg) else None,
                "league_avg_def_rtg": round(float(all_team_rtg), 1) if not pd.isna(all_team_rtg) else None,
                "confound_note": (
                    "PERIMETER DENIAL teams have BETTER def_rtg than average — ROI may be genuine"
                    if (not pd.isna(pd_avg_rtg) and not pd.isna(all_team_rtg) and float(pd_avg_rtg) < float(all_team_rtg))
                    else "PERIMETER DENIAL teams have WORSE def_rtg — Bug 13 confound likely"
                ) if drtg_col else "def_rtg not found"
            }
        else:
            bug13_analysis[sname] = {"n_bets": len(df_b), "pd_teams": pd_teams[:10], "note": "def_rtg col not found"}
    else:
        bug13_analysis[sname] = {"n_bets": len(df_b), "pd_teams": pd_teams[:10], "note": "team_advanced_stats.parquet missing"}
    print(f"  {sname}: pd_teams={pd_teams[:5]} | {bug13_analysis[sname].get('confound_note', '')}")


# ─────────────────────────────────────────────────────────────────────────────
# 11. RANK + VERDICT
# ─────────────────────────────────────────────────────────────────────────────
print("\n[10] Ranking signals...")

# V3 best signal for comparison
v3_results_path = ROOT / "data/models/intelligence_betting_v3_results.json"
v3_comparison = {}
if v3_results_path.exists():
    with open(v3_results_path) as f:
        v3_data = json.load(f)
    for s in v3_data.get("signals", []):
        v3_comparison[s["name"]] = {
            "v3_roi": s.get("roi_real_flat"),
            "v3_n_real": s.get("n_real_line_bets"),
            "v3_verdict": s.get("verdict"),
        }
    print(f"  Loaded V3 results for {len(v3_comparison)} signals")

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

N_SIGNALS = len(signal_results)
alpha_bonf = 0.05 / N_SIGNALS
significant = [s for s in ranked if s.get("p_value") is not None and s["p_value"] < alpha_bonf]
print(f"  Bonferroni alpha ({N_SIGNALS} signals) = {alpha_bonf:.4f}")
print(f"  Statistically significant: {[s['name'] for s in significant]}")


# ─────────────────────────────────────────────────────────────────────────────
# 12. SIGNAL CLASS ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
class_summary = {}
for s in ranked:
    sname = s["name"]
    if sname.startswith("C_") or sname.startswith("PG_"):
        cls = "int20_position_x_scheme"
    elif sname.startswith("B2B") or sname.startswith("altitude"):
        cls = "int22_fatigue_altitude"
    elif sname.startswith("clutch"):
        cls = "int23_clutch"
    elif "perimeter_vs" in sname:
        cls = "v3_archetype_x_scheme"
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


# ─────────────────────────────────────────────────────────────────────────────
# 13. SAVE JSON
# ─────────────────────────────────────────────────────────────────────────────
print("\n[11] Saving JSON output...")

avg_uplift = (
    np.mean([v["uplift_pp"] for v in weighting_comparison.values()])
    if weighting_comparison else 0.0
)
best_uplift_signal = (
    max(weighting_comparison.items(), key=lambda x: x[1]["uplift_pp"])[0]
    if weighting_comparison else None
)

# V3 vs V4 comparison for the re-run signal
v3_vs_v4 = {}
rerun_signal = "perimeter_vs_perim_denial_OVER_pts"
if rerun_signal in signal_results and rerun_signal in v3_comparison:
    v4_res = signal_results[rerun_signal]
    v3_res = v3_comparison[rerun_signal]
    v3_vs_v4[rerun_signal] = {
        "v3_roi": v3_res["v3_roi"],
        "v4_roi": v4_res["roi_real_flat"],
        "v3_n_real": v3_res["v3_n_real"],
        "v4_n_real": v4_res["n_real_line_bets"],
        "change_pp": round((v4_res["roi_real_flat"] or 0) - (v3_res["v3_roi"] or 0), 2)
        if v4_res["roi_real_flat"] is not None and v3_res["v3_roi"] is not None else None,
    }

output = {
    "meta": {
        "generated": "2026-05-28",
        "version": "INT-V4",
        "n_signals_tested": N_SIGNALS,
        "real_lines_pool": len(lines_pool),
        "random_baseline_roi_pct": round(rand_roi * 100, 2),
        "bonferroni_alpha": alpha_bonf,
        "new_signal_sources": ["INT-20 position×scheme", "INT-22 rest/altitude", "INT-23 clutch"],
        "note": "12 signals: 1 V3 re-run + 6 INT-20 + 2 INT-22 + 2 INT-23 + 1 combined",
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
    "v3_vs_v4_comparison": v3_vs_v4,
    "bug13_cross_check": bug13_analysis,
}

out_path = ROOT / "data/models/intelligence_betting_v4_results.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w") as f:
    json.dump(output, f, indent=2, default=str)
print(f"  Saved -> {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 14. WRITE VAULT ATLAS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[12] Writing vault atlas...")

def fmt_r(v):
    if v is None: return "N/A"
    return f"{v:+.2f}%"

def fmt_w(v):
    if v is None: return "N/A"
    return f"{v:.3f}"

def fmt_ci(ci):
    if ci is None or ci == [None, None]: return "N/A"
    return f"({ci[0]:.1f}%, {ci[1]:.1f}%)"

# Build ranked table
rows = []
for i, s in enumerate(ranked, 1):
    rows.append(
        f"| {i} | {s['name']} | {s['n_real_line_bets']} | "
        f"{fmt_w(s['win_rate_real'])} | {fmt_r(s['roi_real_flat'])} | "
        f"{fmt_r(s['roi_real_weighted'])} | {fmt_ci(s['ci_95'])} | {s['verdict']} |"
    )
table_md = "\n".join(rows)

# Top 5
top5_rows = "\n".join([
    f"| {i+1} | {s['name']} | {s['n_real_line_bets']} | "
    f"{fmt_w(s['win_rate_real'])} | {fmt_r(s['roi_real_flat'])} | {fmt_r(s['roi_real_weighted'])} | "
    f"{fmt_ci(s['ci_95'])} | {s['verdict']} |"
    for i, s in enumerate(ranked[:5])
])

# INT-16 weighting table
wt_rows = "\n".join([
    f"| {k} | {fmt_r(v['flat_roi'])} | {fmt_r(v['weighted_roi'])} | {v['uplift_pp']:+.2f}pp |"
    for k, v in sorted(weighting_comparison.items(), key=lambda x: x[1]["uplift_pp"], reverse=True)
]) or "| (none) | | | |"

# V3 vs V4
v3v4_rows = "\n".join([
    f"| {k} | {fmt_r(v.get('v3_roi'))} (n={v.get('v3_n_real')}) | "
    f"{fmt_r(v.get('v4_roi'))} (n={v.get('v4_n_real')}) | "
    f"{fmt_r(v.get('change_pp'))} |"
    for k, v in v3_vs_v4.items()
]) or "| (V3 results not available) | | | |"

# Class table
class_table = "\n".join([
    f"| {cls} | {fmt_r(avg)} |"
    for cls, avg in sorted(class_avg_roi.items(), key=lambda x: x[1], reverse=True)
])

# Bug 13 table
bug13_rows = []
for sname, info in bug13_analysis.items():
    pd_rtg = info.get("pd_team_avg_def_rtg", "N/A")
    lg_rtg = info.get("league_avg_def_rtg", "N/A")
    note = info.get("confound_note", info.get("note", ""))
    bug13_rows.append(f"| {sname} | {fmt_r(info.get('roi'))} | {pd_rtg} | {lg_rtg} | {note} |")
bug13_md = "\n".join(bug13_rows) or "| (no PERIMETER DENIAL signals fired) | | | | |"

# NEW signal verdicts narrative
NL = "\n"
int20_names = ["C_vs_perim_denial_OVER_pts", "C_vs_iso_force_OVER_pts", "PG_vs_perim_denial_OVER_pts",
               "C_vs_paint_first_OVER_reb", "C_vs_iso_force_OVER_reb", "PG_vs_perim_denial_OVER_ast"]
int22_names = ["B2B_UNDER_reb", "altitude_UNDER_reb"]
int23_names = ["clutch_elevator_close_game_OVER_pts", "clutch_shrinker_close_game_UNDER_pts"]

def signal_verdict_line(name):
    r = signal_results.get(name)
    if not r:
        return f"- **{name}**: NOT RUN"
    return (f"- **{name}**: ROI={fmt_r(r['roi_real_flat'])}, n={r['n_real_line_bets']}, "
            f"wr={fmt_w(r['win_rate_real'])}, CI={fmt_ci(r['ci_95'])}, verdict={r['verdict']}")

int20_lines = NL.join(signal_verdict_line(n) for n in int20_names)
int22_lines = NL.join(signal_verdict_line(n) for n in int22_names)
int23_lines = NL.join(signal_verdict_line(n) for n in int23_names)

# Strategic recs
live_monitor = [s["name"] for s in promising + neutral if s["n_real_line_bets"] >= 10]
drop_list = [s["name"] for s in dead if s["n_real_line_bets"] >= 5]
wait_list = [s["name"] for s in insuff + [s for s in neutral if s["n_real_line_bets"] < 10]]

live_lines = NL.join(f"- {s}" for s in live_monitor) or "- None yet (n too small)"
drop_lines_str = NL.join(f"- {s}" for s in drop_list) or "- None categorically dead"
wait_lines_str = NL.join(f"- {s}" for s in wait_list) or "- None"

sig_names_significant = str([s["name"] for s in significant]) if significant else "None"

prec = precision_analysis
pc_note = (
    f"Low-volatility filter reduces sample by {prec['sample_reduction_pct']:.1f}% "
    f"and {'IMPROVES' if prec['precision_helps'] else 'DOES NOT IMPROVE'} ROI "
    f"from {fmt_r(prec['base_signal']['roi'])} to {fmt_r(prec['combined_signal']['roi'])}."
)

md = f"""# INT-V4 Extended Betting Signal Ranking

> Generated: 2026-05-28
> Version: INT-V4 (12 signals: V3 re-run + INT-20/INT-22/INT-23 extensions)
> Script: `scripts/test_intelligence_betting_v4.py`
> JSON: `data/models/intelligence_betting_v4_results.json`

## Setup

- Real lines pool: {len(lines_pool):,} rows (4 sources, de-duped)
- New signals tested: 12 (1 V3 re-run + 6 INT-20 + 2 INT-22 + 2 INT-23 + 1 combined)
- Random baseline ROI: **{rand_roi*100:.2f}%** (theoretical -4.55% at -110)
- Bonferroni alpha: **{alpha_bonf:.4f}** (0.05 / {N_SIGNALS} signals)

## Top 5 Most Promising Signals (by real-line ROI)

| Rank | Signal | n_real | win_rate | flat ROI | INT-16 weighted ROI | 95% CI | Verdict |
|------|--------|--------|----------|----------|---------------------|--------|---------|
{top5_rows}

## Full Signal Table (ranked by real-line ROI)

| Rank | Signal | n_real | win_rate | flat ROI | INT-16 weighted ROI | 95% CI | Verdict |
|------|--------|--------|----------|----------|---------------------|--------|---------|
{table_md}

## V3 vs V4 Comparison

| Signal | V3 result | V4 result | Change |
|--------|-----------|-----------|--------|
{v3v4_rows}

## NEW Signal Verdicts

### INT-20 — Position × Scheme signals
{int20_lines}

### INT-22 — Fatigue / Altitude signals
{int22_lines}

### INT-23 — Clutch profile signals
{int23_lines}

## Combined Signal Precision Test

{pc_note}

| | n_real | win_rate | ROI |
|-|--------|----------|-----|
| B2B_UNDER_reb (base) | {prec['base_signal']['n_real']} | {fmt_w(prec['base_signal']['win_rate'])} | {fmt_r(prec['base_signal']['roi'])} |
| B2B + low_volatility (combined) | {prec['combined_signal']['n_real']} | {fmt_w(prec['combined_signal']['win_rate'])} | {fmt_r(prec['combined_signal']['roi'])} |

## Bug 13 Cross-Check: PERIMETER DENIAL Confound

Bug 13 flag: PERIMETER DENIAL teams may be confounded with weak defensive teams (lower def_rtg),
meaning the positive OVER signal may reflect "playing a bad team" rather than true scheme advantage.

| Signal | ROI | PD team avg def_rtg | League avg def_rtg | Confound assessment |
|--------|-----|---------------------|---------------------|----------------------|
{bug13_md}

Interpretation: if PD team avg def_rtg > league avg, teams are WORSE defensively → Bug 13 likely.
If PD team avg def_rtg < league avg, teams are BETTER defensively → signal may be genuine scheme edge.

## Signal Class Performance

| Signal class | avg real-line ROI |
|--------------|------------------|
{class_table}

Best signal class: **{best_class}**

## INT-16 Kelly Weighting Effect

Average ROI uplift from INT-16 weighting: **{avg_uplift:+.2f}pp**
Signal with best weighting benefit: **{best_uplift_signal or "N/A"}**

| Signal | flat ROI | weighted ROI | uplift |
|--------|----------|--------------|--------|
{wt_rows}

## Statistical Significance

- Bonferroni-corrected α = {alpha_bonf:.4f} (0.05 / {N_SIGNALS} signals)
- Statistically significant signals: **{sig_names_significant}**
- Expected false positives at α=0.05 without correction: ~{N_SIGNALS * 0.05:.1f}

## Strategic Recommendations

**Live-monitor (ROI positive or neutral, n≥10):**
{live_lines}

**Drop (ROI clearly below random, n≥5):**
{drop_lines_str}

**Wait for more data (n<10 or insufficient):**
{wait_lines_str}

## Honest Caveats

1. Sample sizes remain small — n<100 on most signals. Trust CI direction more than exact ROI.
2. INT-20 position signals use NBA API "Guard"→PG, "Center"→C mapping. PG/SG distinction lost.
3. INT-22 B2B lookup requires OOF→game_id→rest_travel chain; ~{int(lines_rt_player['is_b2b'].sum())} B2B bets matched.
4. INT-23 clutch profile based on CV-tracked frames only (n_games=1-2 per player) — very small sample.
5. Clutch "close game" proxy uses pregame spread ≤3.5 pts — not actual final margin ≤7.
6. Bug 13: PERIMETER DENIAL teams may be weak defensively, inflating OVER signals spuriously.
7. Multiple testing: {N_SIGNALS} signals at α=0.05 → expect ~{N_SIGNALS * 0.05:.1f} false positives. Bonferroni threshold = {alpha_bonf:.4f}.
8. All results directional only until n≥200 real-line bets per signal.

---
*See also: [[Betting_Signal_Ranking]], [[project_loop7_status]], [[Tracker Improvements Log]]*
"""

vault_dir = ROOT / "vault/Intelligence"
vault_dir.mkdir(parents=True, exist_ok=True)
atlas_path = vault_dir / "Betting_Signal_Ranking_v4.md"
with open(atlas_path, "w", encoding="utf-8") as f:
    f.write(md)
print(f"  Atlas saved -> {atlas_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 15. FINAL REPORT
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("INT-V4 Extended Betting Signal Backtest - FINAL REPORT")
print("=" * 70)

print(f"""
SETUP
  Real lines pool: {len(lines_pool):,} rows (4 sources, de-duped)
  New signals tested: {N_SIGNALS} (1 V3 re-run + 6 INT-20 + 2 INT-22 + 2 INT-23 + 1 combined)
  Random baseline ROI: {rand_roi*100:.2f}%
  Bonferroni alpha: {alpha_bonf:.4f}
""")

print("REAL-LINE COVERAGE PER SIGNAL")
print(f"  {'Signal':<55} {'n_real':>6} {'n_bets':>7}")
print("  " + "-" * 70)
for s in ranked:
    print(f"  {s['name']:<55} {s['n_real_line_bets']:>6} {s['n_bets']:>7}")

print("\nTOP 5 MOST PROMISING SIGNALS (by real-line ROI)")
print(f"  {'Signal':<55} {'n_real':>6} {'win_rate':>9} {'flat ROI':>10} {'wt ROI':>10}")
print("  " + "-" * 95)
for s in ranked[:5]:
    print(
        f"  {s['name']:<55} {s['n_real_line_bets']:>6} "
        f"{fmt_w(s['win_rate_real']):>9} {fmt_r(s['roi_real_flat']):>10} "
        f"{fmt_r(s['roi_real_weighted']):>10}"
    )

print("\nV3 vs V4 COMPARISON")
if v3_vs_v4:
    for sig, cmp in v3_vs_v4.items():
        print(f"  {sig}:")
        print(f"    V3: ROI={fmt_r(cmp['v3_roi'])} n={cmp['v3_n_real']}")
        print(f"    V4: ROI={fmt_r(cmp['v4_roi'])} n={cmp['v4_n_real']}")
        print(f"    Change: {fmt_r(cmp.get('change_pp'))}")
else:
    print("  V3 results file not found — comparison unavailable")

print("\nNEW SIGNAL VERDICTS")
print("  INT-20 (position × scheme):")
for n in int20_names:
    r = signal_results[n]
    print(f"    {n}: ROI={fmt_r(r['roi_real_flat'])} n={r['n_real_line_bets']} [{r['verdict']}]")
print("  INT-22 (fatigue/altitude):")
for n in int22_names:
    r = signal_results[n]
    print(f"    {n}: ROI={fmt_r(r['roi_real_flat'])} n={r['n_real_line_bets']} [{r['verdict']}]")
print("  INT-23 (clutch):")
for n in int23_names:
    r = signal_results[n]
    print(f"    {n}: ROI={fmt_r(r['roi_real_flat'])} n={r['n_real_line_bets']} [{r['verdict']}]")

print("\nCOMBINED SIGNAL PRECISION TEST")
print(f"  {pc_note}")

print(f"\nINT-16 KELLY WEIGHTING EFFECT")
print(f"  Average ROI uplift from weighting: {avg_uplift:+.2f}pp")

print(f"\nSIGNAL CLASS PERFORMANCE")
for cls, avg in sorted(class_avg_roi.items(), key=lambda x: x[1], reverse=True):
    print(f"  {cls}: avg ROI = {fmt_r(avg)}")
print(f"  Best class: {best_class}")

print(f"\nSTATISTICAL SIGNIFICANCE")
if significant:
    for s in significant:
        print(f"  SIGNIFICANT: {s['name']} z={s['z_stat']} p={s['p_value']}")
else:
    print(f"  No signal passes Bonferroni threshold (alpha={alpha_bonf:.4f}).")

print(f"\nBUG 13 CROSS-CHECK")
for sname, info in bug13_analysis.items():
    print(f"  {sname}: {info.get('confound_note', info.get('note', 'no info'))}")

print(f"\nSTRATEGIC TAKEAWAYS")
if promising:
    print(f"  Live-monitor: {[s['name'] for s in promising[:3]]}")
else:
    print(f"  Live-monitor: {live_monitor[:3] if live_monitor else 'accumulate data first'}")
print(f"  Drop: {drop_list[:3] if drop_list else 'none categorically dead'}")
print(f"  Wait-for-data: {wait_list[:3] if wait_list else 'none'}")

print(f"""
HONEST CAVEATS
  1. Sample sizes small (n<100 per signal on real lines); CIs are wide.
  2. INT-20: "Guard" position in NBA API conflates PG+SG — PG signals cover both.
  3. INT-22: B2B/altitude lookup requires game_id chain; matched {int(lines_rt_player['is_b2b'].sum())} B2B bets.
  4. INT-23: Clutch profiles from 1-2 tracked games per player — extremely thin.
  5. Clutch close-game proxy = pregame spread <=3.5, not actual final margin <=7.
  6. Bug 13: check def_rtg table for PERIMETER DENIAL teams before deploying live.
  7. {N_SIGNALS} signals tested; Bonferroni alpha = {alpha_bonf:.4f}.

FILES
  scripts/test_intelligence_betting_v4.py
  data/models/intelligence_betting_v4_results.json
  vault/Intelligence/Betting_Signal_Ranking_v4.md
""")
