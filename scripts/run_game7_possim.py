"""
run_game7_possim.py — WCF Game 7 SAS @ OKC possession-by-possession Monte Carlo.

Runs GameSimulator (Block F, src/simulation/game_simulator.py) with:
  - Player seeds built from player_avgs_2024-25.json (name lookup) + predictions_cache_game7.parquet
  - OKC pace/off_rtg/def_rtg adjustments
  - Jalen Williams minutes floored at ~10 (hobbled)
  - 10,000 simulations
  - Output saved to data/cache/intel_game7/possession_sim.json
"""

from __future__ import annotations

import json
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Import the Block F simulator ─────────────────────────────────────────────
from src.simulation.game_simulator import GameSimulator, GameSimResult, _load_player_seed

# ── Rosters ──────────────────────────────────────────────────────────────────
# OKC (home). Jalen Williams (1631114) hobbled — excluded from active lineup.
OKC_LINEUP = [
    "1628983",   # Shai Gilgeous-Alexander
    "1631096",   # Chet Holmgren
    "1628392",   # Isaiah Hartenstein
    "1641717",   # Cason Wallace
    "1629652",   # Luguentz Dort
    "1642272",   # Jared McCain (now starting per G6)
    "1627936",   # Alex Caruso
    "1629026",   # Kenrich Williams
    "1631119",   # Jaylin Williams
]

# SAS (away)
SAS_LINEUP = [
    "1641705",   # Victor Wembanyama
    "1628368",   # De'Aaron Fox
    "1642264",   # Stephon Castle
    "1630170",   # Devin Vassell
    "1642844",   # Dylan Harper
    "1629640",   # Keldon Johnson
    "1628436",   # Luke Kornet
    "203084",    # Harrison Barnes
    "1630577",   # Julian Champagnie
    "202687",    # Bismack Biyombo
]

# ── Player name → id mapping for seed lookup ─────────────────────────────────
PLAYER_NAME_MAP = {
    "1628983": "shai gilgeous-alexander",
    "1631096": "chet holmgren",
    "1628392": "isaiah hartenstein",
    "1641717": "cason wallace",
    "1629652": "luguentz dort",
    "1627936": "alex caruso",
    "1629026": "kenrich williams",
    "1631119": "jaylin williams",
    "1630198": "isaiah joe",
    "1630598": "aaron wiggins",
    "1642272": "jared mccain",
    "1642260": "nikola topic",
    "1631114": "jalen williams",
    "1641705": "victor wembanyama",
    "1628368": "de'aaron fox",
    "1642264": "stephon castle",
    "1630170": "devin vassell",
    "1642844": "dylan harper",
    "1629640": "keldon johnson",
    "1628436": "luke kornet",
    "203084": "harrison barnes",
    "1630577": "julian champagnie",
    "202687": "bismack biyombo",
}

# ── Load player_avgs_2024-25.json (keyed by player name) ─────────────────────
AVGS_PATH = ROOT / "data" / "nba" / "player_avgs_2024-25.json"
with open(AVGS_PATH) as f:
    PLAYER_AVGS = json.load(f)  # {lower_name: {pts, reb, ast, ...}}

# ── Load predictions_cache_game7.parquet for q50 projections ──────────────────
CACHE_PATH = ROOT / "data" / "cache" / "predictions_cache_game7.parquet"
preds_df = pd.read_parquet(CACHE_PATH)
# Build: {player_id: {stat: q50}}
preds_q50 = {}
for pid_int, grp in preds_df.groupby("player_id"):
    preds_q50[str(pid_int)] = dict(zip(grp["stat"], grp["q50"]))

# ── Team stats (6-game WCF series averages) ───────────────────────────────────
# pace: avg possessions per team per game; off_rtg/def_rtg: per-100
OKC_TEAM_STATS = {"pace": 97.7, "off_rtg": 108.0, "def_rtg": 109.0, "oreb_pct": 0.30}
SAS_TEAM_STATS = {"pace": 97.7, "off_rtg": 109.0, "def_rtg": 108.0, "oreb_pct": 0.33}

# ── Prop lines ────────────────────────────────────────────────────────────────
PROP_LINES = {
    "1628983": {"pts": 27.5},                         # SGA
    "1641705": {"pts": 27.5, "reb": 13.5, "blk": 3.5},  # Wembanyama
    "1628368": {"pts": 15.5},                         # Fox
    "1631096": {"reb": 8.5},                          # Holmgren
    "1642264": {"pts": 17.5},                         # Castle
    "1642844": {"pts": 9.5},                          # Harper
}

PLAYER_DISPLAY = {
    "1628983": "Shai Gilgeous-Alexander",
    "1631096": "Chet Holmgren",
    "1628392": "Isaiah Hartenstein",
    "1641717": "Cason Wallace",
    "1629652": "Luguentz Dort",
    "1642272": "Jared McCain",
    "1627936": "Alex Caruso",
    "1629026": "Kenrich Williams",
    "1631119": "Jaylin Williams",
    "1641705": "Victor Wembanyama",
    "1628368": "De'Aaron Fox",
    "1642264": "Stephon Castle",
    "1630170": "Devin Vassell",
    "1642844": "Dylan Harper",
    "1629640": "Keldon Johnson",
    "1628436": "Luke Kornet",
    "203084": "Harrison Barnes",
    "1630577": "Julian Champagnie",
    "202687": "Bismack Biyombo",
}

# ── Key stats for per-player output ──────────────────────────────────────────
KEY_PLAYERS = ["1628983", "1641705", "1631096", "1642264", "1628368", "1642272", "1642844"]
REPORT_STATS = ["pts", "reb", "ast"]

# ── Build custom seed dict from player_avgs + fallback to q50 projections ────
def build_player_seed(pid: str, name: str | None, avgs_db: dict, q50_dict: dict) -> dict:
    """
    Build a seed dict for the simulator.
    Priority:
      1. player_avgs_2024-25 (regular season actuals, most reliable)
      2. predictions_cache_game7 q50 projections (model output)
      3. Position/role defaults
    """
    defaults = {
        "pts": 10.0, "reb": 4.0, "ast": 2.0, "fg3m": 0.8,
        "stl": 0.7, "blk": 0.3, "tov": 1.5, "min": 22.0,
        "fga": 7.0, "fg_pct": 0.45, "ft_pct": 0.77, "fta": 2.0,
        "fg3_pct": 0.35, "usage_rate": 0.20,
    }
    seed = dict(defaults)

    # Try player_avgs (keyed by lowercase name)
    avgs_data = None
    if name:
        avgs_data = avgs_db.get(name.lower())
    if avgs_data:
        for k in ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "min",
                  "fg_pct", "fg3_pct", "ft_pct", "fta"]:
            if k in avgs_data and avgs_data[k] is not None:
                seed[k] = float(avgs_data[k])
        # Compute fga from pts + fg_pct if available
        if seed["fg_pct"] > 0:
            seed["fga"] = max(float(seed.get("pts", 10) / max(seed["fg_pct"], 0.01)) * 0.5, 3.0)
        # Estimate usage from pts, min, avg team pts ~110
        seed["usage_rate"] = min(seed["pts"] / max(seed["min"], 1) * 22 / 110.0, 0.40)

    # Supplement missing fg_pct/usage from q50 if avgs missing
    q50 = q50_dict.get(pid, {})
    if q50 and not avgs_data:
        seed["pts"] = float(q50.get("pts", seed["pts"]))
        seed["reb"] = float(q50.get("reb", seed["reb"]))
        seed["ast"] = float(q50.get("ast", seed["ast"]))
        seed["fg3m"] = float(q50.get("fg3m", seed["fg3m"]))
        seed["stl"] = float(q50.get("stl", seed["stl"]))
        seed["blk"] = float(q50.get("blk", seed["blk"]))
        seed["tov"] = float(q50.get("tov", seed["tov"]))
        seed["usage_rate"] = min(seed["pts"] / 110.0, 0.40)

    seed["player_id"] = pid
    return seed


# ── Monkey-patch _load_player_seed in the simulator module ────────────────────
# The simulator calls _load_player_seed(player_id, season) which looks up by
# player_id in the JSON, but the JSON is keyed by name — so it always returns
# defaults. We replace it with our richer build_player_seed.

import src.simulation.game_simulator as _sim_module

def _patched_load_player_seed(player_id: str, season: str) -> dict:
    name = PLAYER_NAME_MAP.get(str(player_id))
    return build_player_seed(str(player_id), name, PLAYER_AVGS, preds_q50)

_sim_module._load_player_seed = _patched_load_player_seed


# ── Patch OREB rate from team stats ──────────────────────────────────────────
# Use average of both teams' oreb_pct
_sim_module._OREB_RATE = (OKC_TEAM_STATS["oreb_pct"] + SAS_TEAM_STATS["oreb_pct"]) / 2.0  # 0.315

# ── Run simulation ────────────────────────────────────────────────────────────
N_SIMS = 10_000
PACE = (OKC_TEAM_STATS["pace"] + SAS_TEAM_STATS["pace"]) / 2.0  # 97.7

print(f"Running {N_SIMS:,} possession-by-possession simulations...")
print(f"  Home (OKC): {len(OKC_LINEUP)} players | Away (SAS): {len(SAS_LINEUP)} players")
print(f"  Pace override: {PACE:.1f} possessions per team per game")
print(f"  OREB rate: {_sim_module._OREB_RATE:.3f}")

sim = GameSimulator(season="2024-25")
result: GameSimResult = sim.simulate_game(
    home_lineup=OKC_LINEUP,
    away_lineup=SAS_LINEUP,
    n_sims=N_SIMS,
    cv_features={},   # no CV data — will use defaults
    pace_override=PACE,
)

print("\n=== SIMULATION COMPLETE ===")
print(result.summary())

# ── Build output dict ─────────────────────────────────────────────────────────
spread_arr = result.spread_distribution
total_arr  = result.total_distribution

def arr_stats(arr: np.ndarray) -> dict:
    return {
        "mean": round(float(np.mean(arr)), 3),
        "std":  round(float(np.std(arr)), 3),
        "p10":  round(float(np.percentile(arr, 10)), 3),
        "p50":  round(float(np.median(arr)), 3),
        "p90":  round(float(np.percentile(arr, 90)), 3),
    }

per_player = {}
for pid in KEY_PLAYERS:
    pstats = result.player_stats.get(pid, {})
    if not pstats:
        continue
    entry = {}
    for stat in REPORT_STATS:
        arr = pstats.get(stat)
        if arr is not None and len(arr) > 0:
            entry[stat] = arr_stats(arr)
    per_player[pid] = {
        "name": PLAYER_DISPLAY.get(pid, pid),
        "stats": entry,
    }

# P(over) for each prop line
prop_results = {}
for pid, lines in PROP_LINES.items():
    name = PLAYER_DISPLAY.get(pid, pid)
    prop_results[pid] = {"name": name, "props": {}}
    for stat, line in lines.items():
        p_over = result.prop_probability(pid, stat, line)
        prop_results[pid]["props"][stat] = {
            "line": line,
            "p_over": round(p_over, 4),
            "p_under": round(1.0 - p_over, 4),
        }

# Document defaults used
defaults_used = [
    "player_avgs_2024-25.json looked up by player NAME (not player_id key) — all 21 of 23 players found",
    "Dylan Harper (1642844): NOT in player_avgs_2024-25 — seeded from predictions_cache_game7 q50 (pts=9.32, reb=3.30, ast=2.75)",
    "Nikola Topic (1642260): NOT in player_avgs_2024-25 and NOT in SAS lineup (excluded); no minutes assigned",
    "Jalen Williams (1631114): EXCLUDED from OKC lineup (hobbled hamstring, ~10 min G6) — zero minutes assigned to simulator",
    "usage_rate: derived from (pts/min)*22/110 per player — no direct usage_rate in player_avgs_2024-25",
    "fga: derived from pts/fg_pct*0.5 approximation — no direct fga in player_avgs_2024-25",
    "cv_features: empty dict {} — no real-time tracking data for this game; simulator uses positional defaults (defender_dist=4.0ft, spacing=0.0)",
    f"OREB rate: {_sim_module._OREB_RATE:.3f} (average of OKC {OKC_TEAM_STATS['oreb_pct']} + SAS {SAS_TEAM_STATS['oreb_pct']})",
    f"Pace: {PACE:.1f} (average of OKC + SAS series pace {OKC_TEAM_STATS['pace']}; used as pace_override)",
    "off_rtg / def_rtg: provided as context ONLY — not directly consumed by GameSimulator (Block F derives points from possession outcomes, not rating-adjustment formulas)",
    "game_state: simulator approximates period from possession count step//25+1; does not track live score diff between teams (uses _STATE_NORMAL only)",
    "ast credits: flat 30% of made shots credited to a random teammate — not usage-aware",
    "stl/blk: derived from per-minute rate × avg_min from player_avgs; poisson-sampled",
    "dreb: 75% of avg_reb × avg_min rate, poisson-sampled; no real rebound tracking model",
    "Player averages source: NBA 2024-25 regular season (not 2025-26 playoff-specific — no playoff-specific cache found)",
]

output = {
    "engine_used": "src/simulation/game_simulator.py — GameSimulator (Block F), possession-by-possession",
    "game": "WCF Game 7: SAS @ OKC, 2026-05-30, OKC home",
    "n_sims": N_SIMS,
    "home": "OKC",
    "away": "SAS",
    "home_lineup": OKC_LINEUP,
    "away_lineup": SAS_LINEUP,
    "home_win_prob": round(result.home_win_prob, 4),
    "away_win_prob": round(1.0 - result.home_win_prob, 4),
    "total": arr_stats(total_arr),
    "spread": arr_stats(spread_arr),   # OKC - SAS; positive = OKC wins by that margin
    "spread_prob": {
        "okc_minus_3": round(result.spread_probability(-3.0), 4),
        "okc_minus_5": round(result.spread_probability(-5.0), 4),
        "okc_plus_3":  round(result.spread_probability(3.0), 4),
        "okc_plus_5":  round(result.spread_probability(5.0), 4),
    },
    "total_prob": {
        "over_205": round(result.total_probability(205.0, over=True), 4),
        "over_210": round(result.total_probability(210.0, over=True), 4),
        "over_215": round(result.total_probability(215.0, over=True), 4),
    },
    "per_player": per_player,
    "prop_lines": prop_results,
    "defaults_used": defaults_used,
    "team_stats_provided": {
        "OKC": OKC_TEAM_STATS,
        "SAS": SAS_TEAM_STATS,
    },
}

# Print key numbers
print(f"\nOKC win prob: {output['home_win_prob']:.1%}")
print(f"SAS win prob: {output['away_win_prob']:.1%}")
print(f"Projected total: {output['total']['mean']:.1f} ± {output['total']['std']:.1f} (p10={output['total']['p10']:.1f}, p50={output['total']['p50']:.1f}, p90={output['total']['p90']:.1f})")
print(f"Projected spread (OKC-SAS): {output['spread']['mean']:.1f} ± {output['spread']['std']:.1f}")

print("\n=== PER-PLAYER DISTRIBUTIONS ===")
for pid, pdata in per_player.items():
    print(f"\n{pdata['name']}:")
    for stat, s in pdata["stats"].items():
        print(f"  {stat}: mean={s['mean']:.1f}  p10={s['p10']:.1f}  p50={s['p50']:.1f}  p90={s['p90']:.1f}")

print("\n=== PROP PROBABILITIES ===")
for pid, pdata in prop_results.items():
    print(f"\n{pdata['name']}:")
    for stat, pr in pdata["props"].items():
        print(f"  {stat} o{pr['line']}: P(over)={pr['p_over']:.3f}  P(under)={pr['p_under']:.3f}")

# ── Save output ───────────────────────────────────────────────────────────────
OUT_PATH = ROOT / "data" / "cache" / "intel_game7" / "possession_sim.json"
with open(OUT_PATH, "w") as f:
    # Convert numpy types for JSON serialization
    json.dump(output, f, indent=2, default=lambda x: float(x) if isinstance(x, (np.floating, np.integer)) else x)

print(f"\n✓ Saved to {OUT_PATH}")
