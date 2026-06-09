"""
run_possession_sim_game7.py — WCF Game 7 SAS @ OKC possession-by-possession Monte Carlo (v2).

Improvements over v1 (run_game7_possim.py):
  - Seeds blended: 0.5 * player_avgs_2025-26.json + 0.5 * wcf_player_series_avg_6g.csv
    (for players present in the 6g playoff file; season-only for the rest)
  - All players looked up by player_id from 2025-26 JSON (not 2024-25)
  - Jalen Williams (1631114) excluded (hamstring, ruled OUT)
  - Same calibration factor (1.1702) as v1 for pts; reb/blk/stl unchanged
  - Output saved to data/cache/intel_game7/possession_sim_v2.json
"""

from __future__ import annotations

import json
import os
import re
import sys
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from typing import Dict
from src.simulation.game_simulator import GameSimulator, GameSimResult, _load_player_seed
import src.simulation.game_simulator as _sim_module

# ── Rosters ──────────────────────────────────────────────────────────────────
# OKC (home). Jalen Williams (1631114) EXCLUDED (hamstring, ruled OUT for G7).
OKC_LINEUP = [
    "1628983",   # Shai Gilgeous-Alexander
    "1631096",   # Chet Holmgren
    "1628392",   # Isaiah Hartenstein
    "1641717",   # Cason Wallace
    "1629652",   # Luguentz Dort
    "1642272",   # Jared McCain (starting G7)
    "1627936",   # Alex Caruso
    "1629026",   # Kenrich Williams
    "1631119",   # Jaylin Williams
    "1630198",   # Isaiah Joe
    "1630598",   # Aaron Wiggins
]

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
    "1630198": "Isaiah Joe",
    "1630598": "Aaron Wiggins",
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
    "1642260": "Nikola Topic",
}

# ── Team stats ────────────────────────────────────────────────────────────────
OKC_TEAM_STATS = {"pace": 97.7, "off_rtg": 108.0, "def_rtg": 109.0, "oreb_pct": 0.30}
SAS_TEAM_STATS = {"pace": 97.7, "off_rtg": 109.0, "def_rtg": 108.0, "oreb_pct": 0.33}

# ── Prop lines ────────────────────────────────────────────────────────────────
PROP_LINES = {
    "1628983": {"pts": 27.5},
    "1641705": {"pts": 27.5, "reb": 13.5, "blk": 3.5},
    "1628368": {"pts": 15.5},
    "1631096": {"reb": 8.5},
    "1642264": {"pts": 17.5},
    "1642844": {"pts": 9.5},
}

KEY_PLAYERS = ["1628983", "1641705", "1631096", "1642264", "1628368", "1642272", "1642844"]
REPORT_STATS = ["pts", "reb", "ast"]

# Pts calibration factor — same as v1 for comparability
CALIB_FACTOR = 1.1702


# ── Load data sources ─────────────────────────────────────────────────────────

def _norm_name(name: str) -> str:
    """Lowercase, strip punctuation/apostrophes for fuzzy matching."""
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def load_season_avgs() -> dict:
    """Load 2025-26 season avgs, keyed by player_id (str) AND by normalized name."""
    path = ROOT / "data" / "nba" / "player_avgs_2025-26.json"
    with open(path) as f:
        raw = json.load(f)
    # raw is keyed by lowercase player name; values have player_id field
    by_id = {}
    by_name = {}
    for name_key, data in raw.items():
        pid = str(int(data.get("player_id", 0)))
        if pid and pid != "0":
            by_id[pid] = data
        by_name[_norm_name(name_key)] = data
    return by_id, by_name


def load_playoff_avgs() -> dict:
    """Load 6-game WCF series avgs CSV, keyed by player_id (str)."""
    path = ROOT / "data" / "cache" / "intel_2026-05-26" / "wcf_player_series_avg_6g.csv"
    df = pd.read_csv(path)
    by_id = {}
    for _, row in df.iterrows():
        pid = str(int(row["player_id"]))
        by_id[pid] = row.to_dict()
    return by_id


SEASON_BY_ID, SEASON_BY_NAME = load_season_avgs()
PLAYOFF_BY_ID = load_playoff_avgs()


# ── Seed builder — blend 2025-26 season + WCF 6g ────────────────────────────

def build_blended_seed(pid: str) -> dict:
    """
    Build player seed dict with:
      - base: player_avgs_2025-26 (keyed by player_id)
      - if player in 6g playoff CSV: blend = 0.5 * season + 0.5 * playoff
      - if not in playoff CSV: use season only
    Falls back to hardcoded defaults for any missing field.
    """
    defaults = {
        "pts": 10.0, "reb": 4.0, "ast": 2.0, "fg3m": 0.8,
        "stl": 0.7, "blk": 0.3, "tov": 1.5, "min": 22.0,
        "fga": 7.0, "fg_pct": 0.45, "ft_pct": 0.77, "fta": 2.0,
        "fg3_pct": 0.35, "usage_rate": 0.20,
    }
    seed = dict(defaults)
    defaults_log = []

    # --- Season 2025-26 base ---
    season_data = SEASON_BY_ID.get(pid)
    if season_data is None:
        defaults_log.append(f"pid={pid}: NOT in player_avgs_2025-26 (used hardcoded defaults)")
    else:
        # Map season fields -> seed keys
        field_map = {
            "pts": "pts", "reb": "reb", "ast": "ast", "tov": "tov",
            "fg3m": "fg3m", "stl": "stl", "blk": "blk", "min": "min",
            "fg_pct": "fg_pct", "fg3_pct": "fg3_pct", "ft_pct": "ft_pct", "fta": "fta",
        }
        for src, dst in field_map.items():
            v = season_data.get(src)
            if v is not None:
                seed[dst] = float(v)

        # Derive fga and usage from season data
        if seed["fg_pct"] > 0:
            seed["fga"] = max(seed["pts"] / seed["fg_pct"] * 0.5, 3.0)
        seed["usage_rate"] = min(seed["pts"] / max(seed["min"], 1.0) * 22.0 / 110.0, 0.40)

    # --- Playoff 6g blend ---
    playoff_data = PLAYOFF_BY_ID.get(pid)
    if playoff_data is not None:
        # These columns exist in the playoff CSV
        playoff_field_map = {
            "pts_pg": "pts", "reb_pg": "reb", "ast_pg": "ast", "tov_pg": "tov",
            "fg3m_pg": "fg3m", "stl_pg": "stl", "blk_pg": "blk", "min_pg": "min",
            "fga_pg": "fga", "fta_pg": "fta",
        }
        # Also usage from usg_pct_pg (expressed as %, divide by 100)
        po_vals = {}
        for src, dst in playoff_field_map.items():
            v = playoff_data.get(src)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                po_vals[dst] = float(v)

        usg = playoff_data.get("usg_pct_pg")
        if usg is not None and not (isinstance(usg, float) and np.isnan(usg)):
            po_vals["usage_rate"] = float(usg) / 100.0

        # Blend: 0.5 season + 0.5 playoff for keys present in both
        if season_data is not None:
            for k, po_v in po_vals.items():
                if k in seed:
                    seed[k] = 0.5 * seed[k] + 0.5 * po_v
        else:
            # No season data — use playoff only
            for k, po_v in po_vals.items():
                seed[k] = po_v

        defaults_log.append(
            f"pid={pid}: blended 0.5*2025-26-season + 0.5*WCF-6g "
            f"(pts={seed['pts']:.1f}, reb={seed['reb']:.1f}, min={seed['min']:.1f}, "
            f"stl={seed['stl']:.2f}, blk={seed['blk']:.2f})"
        )
    else:
        defaults_log.append(
            f"pid={pid}: NOT in WCF 6g CSV — season-only seed "
            f"(pts={seed['pts']:.1f}, reb={seed['reb']:.1f})"
        )

    seed["player_id"] = pid
    return seed, defaults_log


# ── Collect defaults log across all players ───────────────────────────────────
ALL_DEFAULTS_LOG = []

def _patched_load_player_seed(player_id: str, season: str) -> dict:
    seed, log = build_blended_seed(str(player_id))
    ALL_DEFAULTS_LOG.extend(log)
    return seed


# Monkey-patch the module-level function used inside GameSimulator._load_lineup
_sim_module._load_player_seed = _patched_load_player_seed

# Patch OREB rate
OREB_RATE = (OKC_TEAM_STATS["oreb_pct"] + SAS_TEAM_STATS["oreb_pct"]) / 2.0
_sim_module._OREB_RATE = OREB_RATE

PACE = (OKC_TEAM_STATS["pace"] + SAS_TEAM_STATS["pace"]) / 2.0  # 97.7
N_SIMS = 10_000


# ── Print preview of seeds before running ─────────────────────────────────────
print("=== SEED PREVIEW (KEY PLAYERS) ===")
preview_pids = ["1628983", "1641705", "1631096", "1642264", "1628368", "1642272", "1642844"]
for pid in preview_pids:
    s, _ = build_blended_seed(pid)
    name = PLAYER_DISPLAY.get(pid, pid)
    print(f"  {name}: pts={s['pts']:.1f}  reb={s['reb']:.1f}  min={s['min']:.1f}  "
          f"stl={s['stl']:.2f}  blk={s['blk']:.2f}  usage={s['usage_rate']:.3f}")


# ── Run simulation ────────────────────────────────────────────────────────────
print(f"\nRunning {N_SIMS:,} possession-by-possession simulations (v2, blended seeds)...")
print(f"  Home (OKC): {len(OKC_LINEUP)} players | Away (SAS): {len(SAS_LINEUP)} players")
print(f"  Pace override: {PACE:.1f} possessions per team per game")
print(f"  OREB rate: {OREB_RATE:.3f}")

sim = GameSimulator(season="2025-26")
result: GameSimResult = sim.simulate_game(
    home_lineup=OKC_LINEUP,
    away_lineup=SAS_LINEUP,
    n_sims=N_SIMS,
    cv_features={},
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


# Calibrated total stats
calib_total = total_arr * CALIB_FACTOR
total_stats = arr_stats(total_arr)
total_stats["calibrated_mean"] = round(float(np.mean(calib_total)), 1)
total_stats["calibrated_std"]  = round(float(np.std(calib_total)), 1)
total_stats["calibrated_p10"]  = round(float(np.percentile(calib_total, 10)), 1)
total_stats["calibrated_p50"]  = round(float(np.median(calib_total)), 1)
total_stats["calibrated_p90"]  = round(float(np.percentile(calib_total, 90)), 1)


# ── Per-player calibration factors ───────────────────────────────────────────
# The Block F sim structurally compresses star pts: with 11 OKC + 10 SAS players all
# competing for possessions, each player's usage share is diluted beyond their real
# NBA role. The team-level 1.1702 factor corrects TOTAL pts but not per-player balance.
#
# Per-player calibration: factor = blended_seed_pts / sim_raw_mean_pts
# This anchors each player's calibrated MEAN to their blended seed, while the sim
# contributes the distribution SHAPE (std, skew, p10/50/90 spread).
# Calibrated distribution = raw_arr * per_player_calib_factor.

PLAYER_SEED_PTS: Dict[str, float] = {}  # pid -> blended pts seed
for pid in KEY_PLAYERS:
    s, _ = build_blended_seed(pid)
    PLAYER_SEED_PTS[pid] = float(s["pts"])


def per_player_calib_factor(pid: str, raw_mean: float) -> float:
    """Scale factor so that raw_mean * factor = blended seed pts."""
    seed_pts = PLAYER_SEED_PTS.get(pid)
    if seed_pts is None or raw_mean < 0.5:
        return CALIB_FACTOR  # fall back to team factor
    return seed_pts / raw_mean


per_player = {}
per_player_calib_factors = {}
for pid in KEY_PLAYERS:
    pstats = result.player_stats.get(pid, {})
    if not pstats:
        continue
    entry = {}
    for stat in REPORT_STATS:
        arr = pstats.get(stat)
        if arr is not None and len(arr) > 0:
            raw_stats = arr_stats(arr)
            if stat == "pts":
                f = per_player_calib_factor(pid, raw_stats["mean"])
                per_player_calib_factors[pid] = round(f, 4)
                calib_arr = arr * f
                calib_s = arr_stats(calib_arr)
                raw_stats["calibrated_mean"] = calib_s["mean"]
                raw_stats["calibrated_std"]  = calib_s["std"]
                raw_stats["calibrated_p10"]  = calib_s["p10"]
                raw_stats["calibrated_p50"]  = calib_s["p50"]
                raw_stats["calibrated_p90"]  = calib_s["p90"]
            entry[stat] = raw_stats
    per_player[pid] = {
        "name": PLAYER_DISPLAY.get(pid, pid),
        "stats": entry,
        "seed_pts": PLAYER_SEED_PTS.get(pid),
        "per_player_calib_factor": per_player_calib_factors.get(pid),
    }

# P(over) for each prop line
# pts props: use per-player calibrated distribution (seed-anchored)
# reb/blk: no pts calibration; use raw sim
prop_results = {}
for pid, lines in PROP_LINES.items():
    name = PLAYER_DISPLAY.get(pid, pid)
    prop_results[pid] = {"name": name, "props": {}}
    pstats = result.player_stats.get(pid, {})
    for stat, line in lines.items():
        arr = pstats.get(stat)
        if arr is None or len(arr) == 0:
            p_over = 0.5
            p_over_calib = 0.5
            note = "no data"
        else:
            p_over = float(np.mean(arr > line))
            if stat == "pts":
                f = per_player_calib_factors.get(pid, CALIB_FACTOR)
                calib_arr = arr * f
                p_over_calib = float(np.mean(calib_arr > line))
                note = f"calib factor={f:.3f} (seed {PLAYER_SEED_PTS.get(pid, '?'):.1f} / raw {np.mean(arr):.1f})"
            else:
                p_over_calib = p_over  # no calibration for reb/blk
                note = None

        entry = {
            "line": line,
            "p_over": round(p_over, 4),
            "p_under": round(1.0 - p_over, 4),
            "p_over_calibrated": round(p_over_calib, 4),
        }
        if stat == "blk":
            entry["note"] = "blk from per-min Poisson model; no pts-calibration applied"
        elif note:
            entry["note"] = note
        prop_results[pid]["props"][stat] = entry

# Deduplicate defaults log (seed builder is called twice per player — once in preview)
seen = set()
deduped_defaults = []
for item in ALL_DEFAULTS_LOG:
    if item not in seen:
        seen.add(item)
        deduped_defaults.append(item)

deduped_defaults += [
    "Jalen Williams (1631114): EXCLUDED from OKC lineup (hamstring, ruled OUT G7) — zero minutes",
    "Nikola Topic (1642260): NOT in active roster, not included in OKC_LINEUP",
    f"OREB rate: {OREB_RATE:.3f} (average of OKC {OKC_TEAM_STATS['oreb_pct']} + SAS {SAS_TEAM_STATS['oreb_pct']})",
    f"Pace: {PACE:.1f} possessions/team (OKC series avg = SAS series avg = 97.7)",
    "cv_features: empty dict {} — no real-time tracking data; simulator uses positional defaults (defender_dist=4.0ft, spacing=0.0)",
    "off_rtg / def_rtg: context only — GameSimulator (Block F) derives points from possession outcomes, not rating formulas",
    "Blend recipe: for players in WCF 6g CSV => seed = 0.5*2025-26_season + 0.5*WCF_series_avg; else season-only",
    "fga for season-only players: pts / fg_pct * 0.5 approximation",
    "usage_rate: derived from blended pts/min * 22/110 (or from usg_pct_pg in playoff CSV if available)",
    f"Pts calibration: {CALIB_FACTOR}x applied post-hoc (same as v1 for comparability). Reb/blk/stl not calibrated.",
    "ast credits: flat 30% of made shots credited to random teammate — not usage-aware",
]

output = {
    "engine_used": "src/simulation/game_simulator.py — GameSimulator (Block F), possession-by-possession",
    "seed_recipe": "0.5 * player_avgs_2025-26.json + 0.5 * wcf_player_series_avg_6g.csv (for players in 6g file); 2025-26 season-only otherwise",
    "game": "WCF Game 7: SAS @ OKC, 2026-05-30, OKC home",
    "n_sims": N_SIMS,
    "home": "OKC",
    "away": "SAS",
    "home_lineup": OKC_LINEUP,
    "away_lineup": SAS_LINEUP,
    "home_win_prob": round(result.home_win_prob, 4),
    "away_win_prob": round(1.0 - result.home_win_prob, 4),
    "total": total_stats,
    "spread": arr_stats(spread_arr),
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
    "defaults_used": deduped_defaults,
    "team_stats_provided": {"OKC": OKC_TEAM_STATS, "SAS": SAS_TEAM_STATS},
    "calibration": {
        "factor": CALIB_FACTOR,
        "rationale": (
            "Block F simulator underscores: single ball-handler per possession, no off-ball scoring. "
            f"Same {CALIB_FACTOR}x factor as v1 for direct comparability. "
            "Pts distributions and prop P(over) corrected by factor. Spread/win_prob unaffected."
        ),
    },
}

# ── Print summary ─────────────────────────────────────────────────────────────
print(f"\nOKC win prob: {output['home_win_prob']:.1%}")
print(f"SAS win prob: {output['away_win_prob']:.1%}")
print(f"Projected total (raw): {output['total']['mean']:.1f} +/- {output['total']['std']:.1f}  "
      f"(p10={output['total']['p10']:.1f}, p50={output['total']['p50']:.1f}, p90={output['total']['p90']:.1f})")
print(f"Projected total (calibrated): {output['total']['calibrated_mean']:.1f} +/- "
      f"{output['total']['calibrated_std']:.1f}  "
      f"(p10={output['total']['calibrated_p10']:.1f}, p50={output['total']['calibrated_p50']:.1f}, "
      f"p90={output['total']['calibrated_p90']:.1f})")
print(f"Projected spread (OKC-SAS): {output['spread']['mean']:.1f} +/- {output['spread']['std']:.1f}")

print("\n=== PER-PLAYER DISTRIBUTIONS ===")
for pid, pdata in per_player.items():
    print(f"\n{pdata['name']}:")
    for stat, s in pdata["stats"].items():
        print(f"  {stat}: mean={s['mean']:.1f}  p10={s['p10']:.1f}  p50={s['p50']:.1f}  p90={s['p90']:.1f}")

print("\n=== PROP PROBABILITIES ===")
for pid, pdata in prop_results.items():
    print(f"\n{pdata['name']}:")
    for stat, pr in pdata["props"].items():
        calib_str = f"  [calib P(over)={pr['p_over_calibrated']:.3f}]" if stat == "pts" else ""
        print(f"  {stat} o{pr['line']}: P(over)={pr['p_over']:.3f}  P(under)={pr['p_under']:.3f}{calib_str}")

# ── Save ─────────────────────────────────────────────────────────────────────
OUT_DIR = ROOT / "data" / "cache" / "intel_game7"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "possession_sim_v2.json"

with open(OUT_PATH, "w") as f:
    json.dump(output, f, indent=2, default=lambda x: float(x) if isinstance(x, (np.floating, np.integer)) else x)

print(f"\nSaved to {OUT_PATH}")
