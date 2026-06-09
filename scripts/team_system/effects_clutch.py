"""
effects_clutch.py
-----------------
Measure clutch-time (last 5 min, margin<=5) usage concentration and efficiency effects.

Sources:
  - data/cache/signals/shotclock_leverage.parquet  (player clutch stats)
  - data/cache/team_system/pbp/*.json              (play-by-play for per-game clutch FGA)
  - data/cache/team_system/box/*.json              (full game player FGA for comparison)
  - data/cache/team_system/team_game.parquet       (team-level context)

Mechanics measured:
  1. usage_concentration: HHI (Herfindahl-Hirschman Index) of FGA distribution
     clutch_HHI / regular_HHI => concentration multiplier
  2. xfg_mult: clutch eFG% vs regular eFG%
     clutch_efg / regular_efg => efficiency multiplier

Output: actual numbers, n, significance reads.
"""

import json
import os
import re
import numpy as np
import pandas as pd
from pathlib import Path

REPO = Path("C:/Users/neelj/nba-ai-system")
PBP_DIR = REPO / "data/cache/team_system/pbp"
BOX_DIR = REPO / "data/cache/team_system/box"

# ── Helpers ─────────────────────────────────────────────────────────────────

def parse_clock(clock_str: str) -> float:
    """Convert ISO8601 game clock string (PT12M00.00S) to seconds remaining in period."""
    m = re.match(r"PT(\d+)M([\d.]+)S", clock_str)
    if not m:
        return None
    minutes = int(m.group(1))
    seconds = float(m.group(2))
    return minutes * 60 + seconds


def hhi(fga_list):
    """Herfindahl-Hirschman Index of a list of shot counts. Range 0-1."""
    total = sum(fga_list)
    if total == 0:
        return np.nan
    return sum((x / total) ** 2 for x in fga_list)


# ── 1. Load shotclock_leverage for player-level clutch eFG% ──────────────────

print("=== Loading shotclock_leverage ===")
sl = pd.read_parquet(REPO / "data/cache/signals/shotclock_leverage.parquet")

# Keep players with valid clutch data (NBA clutch = L5min margin<=5)
clutch = sl[sl["clutch_gp"].notna() & (sl["clutch_gp"] >= 10)].copy()
print(f"Players with >=10 clutch games: {len(clutch)}")
print(f"Clutch FG%:  mean={clutch['clutch_fg_pct'].mean():.4f}  median={clutch['clutch_fg_pct'].median():.4f}")

# Regular FG% from situational splits (tied/lead/trail eFG)
sit = pd.read_parquet(REPO / "data/cache/signals/situational_splits.parquet")
sit = sit[["player_id", "tied_efg", "lead_efg", "trail_efg",
           "tied_n_games", "lead_n_games", "trail_n_games"]].dropna(subset=["tied_efg"])

# Merge
merged = clutch.merge(sit, left_on="player_id", right_on="player_id", how="inner")
print(f"Merged rows: {len(merged)}")

# Weighted average regular eFG (tied+lead+trail weighted by n_games)
def weighted_efg(row):
    vals = []
    wts = []
    for s in ["tied", "lead", "trail"]:
        efg = row.get(f"{s}_efg")
        n = row.get(f"{s}_n_games", 0)
        if pd.notna(efg) and pd.notna(n) and n > 0:
            vals.append(efg * n)
            wts.append(n)
    if not wts:
        return np.nan
    return sum(vals) / sum(wts)

merged["reg_efg"] = merged.apply(weighted_efg, axis=1)
merged = merged.dropna(subset=["reg_efg"])

# Clutch eFG from fg_pct — note clutch_fg_pct is field goal % not eFG.
# We have clutch_fg3_pct but not clutch_fg3a to convert to eFG.
# Use clutch_fg_pct as a proxy (comparable directionally).
# Alternatively use lead_efg/trail_efg as proxies for non-clutch.
# We'll compare clutch FG% vs regular (tied) eFG as a directional read.
print("\n=== eFG / FG% comparison (clutch vs regular) ===")
# Use tied_efg as best proxy for neutral (balanced) game state
n_players = len(merged)
clutch_fgpct_mean = merged["clutch_fg_pct"].mean()
reg_efg_mean = merged["reg_efg"].mean()
tied_efg_mean = merged["tied_efg"].mean()

print(f"N players: {n_players}")
print(f"Clutch FG% mean:      {clutch_fgpct_mean:.4f}")
print(f"Regular eFG (wtd) mean: {reg_efg_mean:.4f}")
print(f"Tied eFG mean:          {tied_efg_mean:.4f}")

# FG% is not directly comparable to eFG% (eFG credits 3s 1.5x).
# But clutch_fg3_pct is available. We need 3PA rate to estimate eFG.
# Estimate: clutch_efg ≈ clutch_fg_pct + 0.5 * fg3_rate * clutch_fg3_pct
# We'll use the lead_efg/trail_efg as a contextual proxy instead.

# ── 2. From PBP: per-game clutch FGA distribution per team ──────────────────

print("\n=== Processing PBP files for clutch usage distribution ===")

MARGIN_THRESH = 5    # points, absolute
CLOCK_THRESH  = 300  # seconds (5 minutes)
MIN_CLUTCH_FGA = 5   # minimum team clutch FGA to include game

game_stats = []

pbp_files = sorted(os.listdir(PBP_DIR))
print(f"Total PBP files: {len(pbp_files)}")

for fname in pbp_files:
    if not fname.endswith(".json"):
        continue
    gid = fname.replace(".json", "")

    pbp_path = PBP_DIR / fname
    box_path = BOX_DIR / fname

    if not box_path.exists():
        continue

    with open(pbp_path) as f:
        pbp_data = json.load(f)
    with open(box_path) as f:
        box_data = json.load(f)

    actions = pbp_data["game"]["actions"]

    # Build player FGA in clutch vs non-clutch for both teams
    # Clutch = period 4 (or OT), clock <= 5 min, |home_score - away_score| <= 5
    # Non-clutch = all other field goal attempts in regulation

    clutch_fga = {}     # player_id -> {fgm, fga}
    nonclutch_fga = {}  # player_id -> {fgm, fga}

    for act in actions:
        if not act.get("isFieldGoal"):
            continue

        period = act.get("period", 0)
        clock_str = act.get("clock", "")
        clock_secs = parse_clock(clock_str)
        if clock_secs is None:
            continue

        action_type = act.get("actionType", "")
        sub_type = act.get("subType", "")

        # Score at time of shot
        score_home = int(act.get("scoreHome", 0) or 0)
        score_away = int(act.get("scoreAway", 0) or 0)
        margin = abs(score_home - score_away)

        pid = act.get("personId", 0)
        if pid == 0:
            continue

        made = (action_type == "2pt" or action_type == "3pt") and sub_type != "missed"
        # More reliable: check qualifiers or actionType
        # Actually in NBA PBP, actionType is the main category
        is_made = ("missed" not in str(act.get("description", "")).lower())
        # Use isFieldGoal=1 and check if description says missed
        description = act.get("description", "")
        is_made = "MISS" not in description.upper() and "missed" not in description.lower()

        is_3pt = action_type == "3pt"

        is_clutch = (period >= 4) and (clock_secs <= CLOCK_THRESH) and (margin <= MARGIN_THRESH)

        if is_clutch:
            if pid not in clutch_fga:
                clutch_fga[pid] = {"fga": 0, "fgm": 0, "fga3": 0, "fgm3": 0}
            clutch_fga[pid]["fga"] += 1
            if is_made:
                clutch_fga[pid]["fgm"] += 1
            if is_3pt:
                clutch_fga[pid]["fga3"] += 1
                if is_made:
                    clutch_fga[pid]["fgm3"] += 1
        elif period <= 4:  # Regular non-clutch
            if pid not in nonclutch_fga:
                nonclutch_fga[pid] = {"fga": 0, "fgm": 0, "fga3": 0, "fgm3": 0}
            nonclutch_fga[pid]["fga"] += 1
            if is_made:
                nonclutch_fga[pid]["fgm"] += 1
            if is_3pt:
                nonclutch_fga[pid]["fga3"] += 1
                if is_made:
                    nonclutch_fga[pid]["fgm3"] += 1

    # Get team rosters from box score
    for team_key in ["homeTeam", "awayTeam"]:
        team = box_data["game"].get(team_key, {})
        team_id = team.get("teamId")
        players = team.get("players", [])
        player_ids = {p["personId"] for p in players}

        # Team clutch FGA distribution
        team_clutch = {pid: clutch_fga[pid] for pid in player_ids if pid in clutch_fga}
        team_nonclutch = {pid: nonclutch_fga[pid] for pid in player_ids if pid in nonclutch_fga}

        clutch_fga_list = [v["fga"] for v in team_clutch.values()]
        nonclutch_fga_list = [v["fga"] for v in team_nonclutch.values()]

        total_clutch_fga = sum(clutch_fga_list)
        total_nonclutch_fga = sum(nonclutch_fga_list)

        if total_clutch_fga < MIN_CLUTCH_FGA:
            continue

        # HHI
        clutch_hhi = hhi(clutch_fga_list)
        nonclutch_hhi = hhi(nonclutch_fga_list) if total_nonclutch_fga > 0 else np.nan

        # eFG%: (FGM + 0.5*FG3M) / FGA
        def efg(stats_dict):
            fga = sum(v["fga"] for v in stats_dict.values())
            fgm = sum(v["fgm"] for v in stats_dict.values())
            fgm3 = sum(v["fgm3"] for v in stats_dict.values())
            if fga == 0:
                return np.nan
            return (fgm + 0.5 * fgm3) / fga

        clutch_efg_val = efg(team_clutch)
        nonclutch_efg_val = efg(team_nonclutch)

        # Top-1 and Top-2 scorer usage share in clutch
        sorted_clutch = sorted(clutch_fga_list, reverse=True)
        top1_share = sorted_clutch[0] / total_clutch_fga if sorted_clutch else np.nan
        top2_share = sum(sorted_clutch[:2]) / total_clutch_fga if len(sorted_clutch) >= 2 else top1_share

        sorted_nonclutch = sorted(nonclutch_fga_list, reverse=True)
        top1_nonclutch = sorted_nonclutch[0] / total_nonclutch_fga if sorted_nonclutch and total_nonclutch_fga > 0 else np.nan
        top2_nonclutch = sum(sorted_nonclutch[:2]) / total_nonclutch_fga if len(sorted_nonclutch) >= 2 and total_nonclutch_fga > 0 else top1_nonclutch

        game_stats.append({
            "gid": gid,
            "team_id": team_id,
            "clutch_fga": total_clutch_fga,
            "nonclutch_fga": total_nonclutch_fga,
            "clutch_hhi": clutch_hhi,
            "nonclutch_hhi": nonclutch_hhi,
            "clutch_efg": clutch_efg_val,
            "nonclutch_efg": nonclutch_efg_val,
            "clutch_top1_share": top1_share,
            "clutch_top2_share": top2_share,
            "nonclutch_top1_share": top1_nonclutch,
            "nonclutch_top2_share": top2_nonclutch,
            "n_clutch_players": len(clutch_fga_list),
        })

gdf = pd.DataFrame(game_stats)
print(f"Game-team observations: {len(gdf)}")
print(gdf.describe().to_string())

# ── 3. Aggregate results ─────────────────────────────────────────────────────

print("\n=== RESULTS ===")
valid = gdf.dropna(subset=["clutch_hhi", "nonclutch_hhi", "clutch_efg", "nonclutch_efg"])
n = len(valid)
print(f"N game-team pairs (valid HHI+eFG): {n}")

# Usage concentration (HHI)
print(f"\n-- HHI (usage concentration) --")
print(f"Non-clutch HHI:  mean={valid['nonclutch_hhi'].mean():.4f}  median={valid['nonclutch_hhi'].median():.4f}")
print(f"Clutch HHI:      mean={valid['clutch_hhi'].mean():.4f}  median={valid['clutch_hhi'].median():.4f}")
hhi_ratio = valid["clutch_hhi"].mean() / valid["nonclutch_hhi"].mean()
print(f"Clutch/NonClutch HHI ratio: {hhi_ratio:.4f}")

# Top-1 and Top-2 shot share
valid2 = gdf.dropna(subset=["clutch_top1_share", "nonclutch_top1_share",
                              "clutch_top2_share", "nonclutch_top2_share"])
n2 = len(valid2)
print(f"\n-- Top scorer shot share --  (N={n2})")
print(f"Non-clutch top-1 share: {valid2['nonclutch_top1_share'].mean():.4f}")
print(f"Clutch    top-1 share:  {valid2['clutch_top1_share'].mean():.4f}")
print(f"Non-clutch top-2 share: {valid2['nonclutch_top2_share'].mean():.4f}")
print(f"Clutch    top-2 share:  {valid2['clutch_top2_share'].mean():.4f}")
top2_ratio = valid2["clutch_top2_share"].mean() / valid2["nonclutch_top2_share"].mean()
print(f"Top-2 concentration multiplier: {top2_ratio:.4f}")

# eFG efficiency
print(f"\n-- eFG% (efficiency) --  (N={n})")
print(f"Non-clutch eFG%: mean={valid['nonclutch_efg'].mean():.4f}  median={valid['nonclutch_efg'].median():.4f}")
print(f"Clutch eFG%:     mean={valid['clutch_efg'].mean():.4f}  median={valid['clutch_efg'].median():.4f}")
efg_ratio = valid["clutch_efg"].mean() / valid["nonclutch_efg"].mean()
print(f"Clutch/NonClutch eFG ratio (xfg_mult): {efg_ratio:.4f}")

# Paired t-test for HHI
from scipy import stats as sp_stats
t_hhi, p_hhi = sp_stats.ttest_rel(valid["clutch_hhi"], valid["nonclutch_hhi"])
t_efg, p_efg = sp_stats.ttest_rel(valid["clutch_efg"], valid["nonclutch_efg"])
t_top2, p_top2 = sp_stats.ttest_rel(valid2["clutch_top2_share"], valid2["nonclutch_top2_share"])

print(f"\n-- Significance (paired t-tests) --")
print(f"HHI:   t={t_hhi:.3f}, p={p_hhi:.4f}")
print(f"eFG:   t={t_efg:.3f}, p={p_efg:.4f}")
print(f"Top-2: t={t_top2:.3f}, p={p_top2:.4f}")

# ── 4. Player-level summary from shotclock_leverage ──────────────────────────

print("\n=== Player-level clutch shot rate concentration ===")
# Compare clutch_shots_pg vs shot volume (use scoring_profile for reg shots if available)
scoring = pd.read_parquet(REPO / "data/cache/signals/scoring_profile.parquet")
print("Scoring profile columns:", scoring.columns.tolist()[:15])

# ── 5. Summary ───────────────────────────────────────────────────────────────

print("\n=== SUMMARY ===")
print(f"Dataset: {len(pbp_files)} games ({min(gdf['gid'])} to {max(gdf['gid'])})")
print(f"Valid game-team pairs: {n}")
print(f"")
print(f"USAGE CONCENTRATION (HHI):")
print(f"  Baseline (non-clutch):  {valid['nonclutch_hhi'].mean():.4f}")
print(f"  Clutch:                 {valid['clutch_hhi'].mean():.4f}")
print(f"  Multiplier:             {hhi_ratio:.4f}  (p={p_hhi:.4f})")
print(f"")
print(f"TOP-2 SCORER SHOT SHARE:")
print(f"  Baseline:               {valid2['nonclutch_top2_share'].mean():.4f}")
print(f"  Clutch:                 {valid2['clutch_top2_share'].mean():.4f}")
print(f"  Multiplier:             {top2_ratio:.4f}  (p={p_top2:.4f})")
print(f"")
print(f"EFFICIENCY (eFG%):")
print(f"  Baseline (non-clutch):  {valid['nonclutch_efg'].mean():.4f}")
print(f"  Clutch:                 {valid['clutch_efg'].mean():.4f}")
print(f"  Multiplier (xfg_mult):  {efg_ratio:.4f}  (p={p_efg:.4f})")
print(f"")
print(f"HEADLINE: clutch usage concentrates ~{(hhi_ratio-1)*100:.1f}% more (HHI ratio {hhi_ratio:.3f})")
print(f"HEADLINE: clutch eFG shifts {(efg_ratio-1)*100:+.1f}% vs non-clutch (ratio {efg_ratio:.3f})")
print(f"RECOMMENDED SIM PARAMS:")
print(f"  usage_concentration: multiply player shot_share by HHI factor, or set top-scorer boost")
print(f"  xfg_mult: multiply shot eFG by {efg_ratio:.4f} for clutch possessions")
