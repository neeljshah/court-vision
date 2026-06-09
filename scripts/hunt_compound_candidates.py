"""
hunt_compound_candidates.py
============================
INT-VX: Systematic compound signal hunting across 33+ atlas outputs.

Searches for 2-axis filter compounds (atlas_A x atlas_B) that show
promising stat shifts in the historical lines pool but have NOT been
tested in any previous V2–V9 signal round.

Outputs:
  data/intelligence/compound_candidates.parquet
  (cols: candidate_name, atlas_A, atlas_B, direction, target_stat,
         n_games_matched, mean_stat_shift_vs_base, std_shift, motivation)

Usage:
  python scripts/hunt_compound_candidates.py
"""

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

warnings.filterwarnings("ignore")
np.random.seed(42)

ROOT = Path("C:/Users/neelj/nba-ai-system")
INTEL = ROOT / "data/intelligence"
LINES_DIR = ROOT / "data/external/historical_lines"


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def norm(s: str) -> str:
    return str(s).strip().lower()


def load_lines() -> pd.DataFrame:
    """Load and pool all canonical lines files."""
    sources = [
        "extended_oos_canonical.csv",
        "benashkar_2026_canonical.csv",
        "regular_season_2025_26_oddsapi.csv",
        "regular_season_2024_25_oddsapi.csv",
    ]
    dfs = []
    for fname in sources:
        p = LINES_DIR / fname
        if p.exists():
            d = pd.read_csv(p, on_bad_lines="skip")
            d["date"] = pd.to_datetime(d["date"])
            d["player_norm"] = d["player"].map(norm)
            d["stat"] = d["stat"].str.lower().str.strip()
            dfs.append(d)
    pool = (
        pd.concat(dfs, ignore_index=True)
        .drop_duplicates(subset=["player_norm", "date", "stat"])
        .reset_index(drop=True)
    )
    pool = pool.dropna(subset=["actual_value", "closing_line"])
    return pool


def analyze_signal(sub: pd.DataFrame, direction: str = "over") -> dict:
    """Compute n, mean shift, std, z, p-value, win-rate, 95% CI for a signal."""
    sub = sub.copy()
    sub["shift"] = sub["actual_value"] - sub["closing_line"]
    n = len(sub)
    if n < 5:
        return {"n": n, "mu": None, "std": None, "z": None, "p": None,
                "wr": None, "ci_lo": None, "ci_hi": None}
    mu = sub["shift"].mean()
    std = sub["shift"].std(ddof=1)
    z = mu / (std / np.sqrt(n))
    if direction == "under":
        z = -z
    p = float(1 - scipy_stats.norm.cdf(z))
    boots = [sub["shift"].sample(frac=1, replace=True).mean() for _ in range(2000)]
    ci_lo, ci_hi = np.percentile(boots, [2.5, 97.5])
    if direction == "over":
        wr = float((sub["actual_value"] > sub["closing_line"]).mean())
    else:
        wr = float((sub["actual_value"] < sub["closing_line"]).mean())
    return {
        "n": n, "mu": round(mu, 4), "std": round(std, 4),
        "z": round(z, 4), "p": round(p, 5), "wr": round(wr, 4),
        "ci_lo": round(float(ci_lo), 4), "ci_hi": round(float(ci_hi), 4),
    }


# ---------------------------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------------------------
print("[1] Loading lines pool...")
lines_pool = load_lines()
print(f"  Pooled lines: {len(lines_pool):,} rows")

print("[2] Loading atlas parquets...")
fp = pd.read_parquet(INTEL / "player_fingerprints.parquet").reset_index()
fp["player_norm"] = fp["player_name"].map(norm)

schemes = pd.read_parquet(INTEL / "defensive_schemes.parquet")
schemes["dominant_tag"] = schemes["dominant_tag"].str.strip().str.upper()

streak = pd.read_parquet(INTEL / "streak_signatures.parquet")
streak["player_norm"] = streak["player_name"].map(norm)

drift = pd.read_parquet(INTEL / "archetype_drift.parquet")
drift["player_norm"] = drift["player_name"].map(norm)

matchup = pd.read_parquet(INTEL / "matchup_deviations.parquet")
matchup["player_norm"] = matchup["player_name"].map(norm)

rest = pd.read_parquet(INTEL / "rest_cv_impact.parquet")
rest["player_norm"] = rest["player_name"].map(norm)

clutch = pd.read_parquet(INTEL / "clutch_cv_split.parquet")
clutch["player_norm"] = clutch["player_name"].map(norm)

pace = pd.read_parquet(INTEL / "pace_adjusted_cv.parquet")

print("[3] Computing candidate signals...")

# Players flagged as zero-CV (Bug 2) - always exclude from signal lists
ZERO_CV_PLAYERS = {"stephen curry", "keshad johnson"}


# ---------------------------------------------------------------------------
# DEFINE CANDIDATE FILTERS
# ---------------------------------------------------------------------------

# Scheme lookups
help_def_teams = schemes[schemes["all_tags"].str.contains("HELP DEFENSE", na=False)]["team"].tolist()
pace_ctrl_teams = schemes[schemes["all_tags"].str.contains("PACE CONTROL", na=False)]["team"].tolist()
perim_denial_teams = schemes[schemes["dominant_tag"].str.contains("PERIMETER DENIAL", na=False)]["team"].tolist()
switch_heavy_teams = schemes[schemes["all_tags"].str.contains("SWITCH HEAVY", na=False)]["team"].tolist()
drop_cov_teams = schemes[schemes["dominant_tag"].str.contains("DROP", na=False)]["team"].tolist()
paint_first_teams = schemes[schemes["dominant_tag"].str.contains("PAINT", na=False)]["team"].tolist()
iso_force_teams = schemes[schemes["all_tags"].str.contains("ISO FORCE", na=False)]["team"].tolist()
closeout_teams = schemes[schemes["all_tags"].str.contains("ACTIVE CLOSEOUTS", na=False)]["team"].tolist()

# Streak label lookups
hot_pts_players = {
    p for p in streak[streak["label_pts"] == "HOT"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}
cold_pts_players = {
    p for p in streak[streak["label_pts"] == "COLD"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}
hot_ast_players = {
    p for p in streak[streak["label_ast"] == "HOT"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}
hot_reb_players = {
    p for p in streak[streak["label_reb"] == "HOT"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}

# Fingerprint clusters
paint_heavy_players = set(
    fp[(fp["paint_dwell_pct"] > fp["paint_dwell_pct"].quantile(0.65))
       & (fp["n_cv_games"] >= 3)]["player_norm"].unique()
)
high_vel_players = set(
    fp[(fp["preshot_velocity_peak"] > fp["preshot_velocity_peak"].quantile(0.65))
       & (fp["n_cv_games"] >= 3)]["player_norm"].unique()
)
high_pa_players = set(
    fp[(fp["potential_assists"] > fp["potential_assists"].quantile(0.70))
       & (fp["n_cv_games"] >= 3)]["player_norm"].unique()
)
high_scr_players = set(
    fp[(fp["second_chance_rate"] > 0.20) & (fp["n_cv_games"] >= 3)]["player_norm"].unique()
)
perim_archetype_players = set(fp[fp["archetype_name"] == "Versatile Perimeter Player"]["player_norm"].unique())

# Drift clusters
transitioning_players = set(drift[drift["drift_tag"] == "TRANSITIONING"]["player_norm"].unique())
drift_to_interior = set(
    drift[(drift["drift_tag"] == "TRANSITIONING")
          & (drift["recent_archetype_name"].str.contains("Post|Forward", na=False))
          ]["player_norm"].unique()
)

# Clutch clusters
shrinker_players = set(
    p for p in clutch[clutch["clutch_class"] == "SHRINKER"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
)

# Matchup deviation clusters
high_touch_matchup_players = set(matchup[matchup["touches_per_game_z"] > 1.0]["player_norm"].unique())
high_space_matchup_players = set(matchup[matchup["avg_defender_distance_z"] > 1.5]["player_norm"].unique())

# Rest sensitivity
b2b_players = set(rest[rest["context"] == "B2B"]["player_norm"].unique())

# ---------------------------------------------------------------------------
# CANDIDATE DEFINITIONS
# ---------------------------------------------------------------------------
# Each entry: (name, atlas_A, atlas_B, direction, stat, player_filter, opp_team_filter, motivation)

def get_sub(player_set, team_list, stat):
    return lines_pool[
        lines_pool["player_norm"].isin(player_set)
        & lines_pool["opp"].str.upper().isin(team_list)
        & (lines_pool["stat"] == stat)
    ]


CANDIDATES = [
    # =========================================================
    # C1: HOT_PTS x HELP_DEFENSE -> OVER PTS [TOP CANDIDATE]
    # Motivation: Player on a scoring hot streak faces HELP DEFENSE which systematically
    # under-closes on shooters (positional stat: PG x HELP_DEF = +0.69, t=3.69; SF = +0.89, t=4.54)
    # Both axes compound: streak means regression hasn't hit yet; scheme means structural OVER pressure.
    # Atlas A = INT-5 (streak_signatures), Atlas B = INT-12 (defensive_schemes)
    # =========================================================
    {
        "candidate_name": "C1_HOT_PTS_x_HELP_DEFENSE_OVER_PTS",
        "atlas_A": "INT-5 (streak_signatures, label_pts=HOT)",
        "atlas_B": "INT-12 (defensive_schemes, HELP DEFENSE)",
        "direction": "OVER",
        "target_stat": "pts",
        "player_set": hot_pts_players,
        "team_list": help_def_teams,
        "motivation": (
            "INT-5 HOT_PTS label = player is producing ≥+1.5z above season avg. "
            "INT-12 HELP_DEFENSE = scheme creates open kick-out spots (PG/SF position-scheme t>3.7). "
            "Books set lines on rolling averages that lag momentum; HELP DEF compounds by releasing "
            "shooters on the strong side. Directional cleanliness: both axes push same way."
        ),
    },
    # =========================================================
    # C2: HOT_PTS x PERIMETER_DENIAL -> OVER PTS
    # Motivation: PERIMETER_DENIAL suppresses catch-shoot wings but if the player is already HOT
    # they are elevated-usage and find other scoring avenues (drives, mid-range).
    # Position-scheme: PG x PERIM_DENIAL = +0.88, t=6.84 (n=2792) — strongest single combo in corpus.
    # HOT players are by definition scoring above expectation already, PERIM_DENIAL doesn't reset that.
    # Atlas A = INT-5, Atlas B = INT-12
    # =========================================================
    {
        "candidate_name": "C2_HOT_PTS_x_PERIM_DENIAL_OVER_PTS",
        "atlas_A": "INT-5 (streak_signatures, label_pts=HOT)",
        "atlas_B": "INT-12 (defensive_schemes, PERIMETER DENIAL)",
        "direction": "OVER",
        "target_stat": "pts",
        "player_set": hot_pts_players,
        "team_list": perim_denial_teams,
        "motivation": (
            "Strongest single position-scheme interaction in atlas: PG x PERIM_DENIAL PTS = +0.879, "
            "t=6.84. HOT streak compounds because books adjust slowly to momentum surges. "
            "PERIM_DENIAL teams (POR/UTA) have historically allowed more PTS to ball-dominant guards. "
            "HOT players are generating momentum that overrides defensive suppression in the near-term."
        ),
    },
    # =========================================================
    # C3: HOT_AST x PACE_CONTROL -> OVER AST
    # Motivation: HOT assist players are facilitating at elevated rates.
    # PACE_CONTROL defenses slow the game to half-court sets which increases ISO→kick-out scenarios.
    # More ISO = more kick-out assists for the facilitator.
    # Position-scheme: PG x PACE_CONTROL AST = +0.156, t=4.34 (n=3999).
    # Atlas A = INT-5, Atlas B = INT-12
    # =========================================================
    {
        "candidate_name": "C3_HOT_AST_x_PACE_CONTROL_OVER_AST",
        "atlas_A": "INT-5 (streak_signatures, label_ast=HOT)",
        "atlas_B": "INT-12 (defensive_schemes, PACE CONTROL)",
        "direction": "OVER",
        "target_stat": "ast",
        "player_set": hot_ast_players,
        "team_list": pace_ctrl_teams,
        "motivation": (
            "INT-5 HOT_AST = facilitator is assisting at ≥+1.5z rate. PACE_CONTROL forces half-court "
            "offense, creating more isolation-kick-out sequences = more AST opportunities. "
            "Position-scheme significance: PG x PACE_CTRL AST = +0.156, t=4.34. Double compound: "
            "momentum from streak + structural increase in assist opportunities from defensive scheme."
        ),
    },
    # =========================================================
    # C4: DRIFT TRANSITIONING (INT-38) x DROP_COVERAGE (INT-12) -> OVER REB
    # Motivation: TRANSITIONING players are changing archetypes; books price them on old archetype.
    # DROP_COVERAGE keeps the big drop deep in the paint, ceding weakside rebounding.
    # If the drifting player is moving toward an interior role, they gain REB against drop.
    # Atlas A = INT-38 (archetype_drift), Atlas B = INT-12 (defensive_schemes)
    # =========================================================
    {
        "candidate_name": "C4_DRIFT_TRANSITIONING_x_DROP_COVERAGE_OVER_REB",
        "atlas_A": "INT-38 (archetype_drift, drift_tag=TRANSITIONING)",
        "atlas_B": "INT-12 (defensive_schemes, DROP COVERAGE)",
        "direction": "OVER",
        "target_stat": "reb",
        "player_set": transitioning_players,
        "team_list": drop_cov_teams,
        "motivation": (
            "INT-38 TRANSITIONING = player's CV behavioral profile is shifting archetypes over last 6-10 "
            "games (inconsistency_score < 0.4). Books price on historical archetype which lags. "
            "DROP COVERAGE teams keep the center dropped at the 3pt line, leaving weakside paint open. "
            "Players transitioning toward interior roles gain disproportionate REB vs drop because "
            "they're occupying paint positions the scheme cedes."
        ),
    },
    # =========================================================
    # C5: HIGH PRESHOT_VELOCITY (INT-1) x ACTIVE_CLOSEOUTS (INT-12) -> UNDER FG3M
    # Motivation: preshot_velocity_peak captures catch-and-shoot quickness (high = fast release C&S).
    # ACTIVE_CLOSEOUTS specifically targets late-clock scramble shooters with fast rotations.
    # High-preshot-velocity players depend on C&S windows; active closeouts eliminate those windows.
    # Atlas A = INT-1 (player_fingerprints, preshot_velocity_peak), Atlas B = INT-12
    # =========================================================
    {
        "candidate_name": "C5_HIGH_PRESHOT_VEL_x_ACTIVE_CLOSEOUTS_UNDER_FG3M",
        "atlas_A": "INT-1 (player_fingerprints, preshot_velocity_peak>65th pct)",
        "atlas_B": "INT-12 (defensive_schemes, ACTIVE CLOSEOUTS)",
        "direction": "UNDER",
        "target_stat": "fg3m",
        "player_set": high_vel_players,
        "team_list": closeout_teams,
        "motivation": (
            "INT-1 preshot_velocity_peak > 65th pct = player is a fast-release catch-and-shoot specialist. "
            "ACTIVE CLOSEOUTS defense (BKN/GSW/LAL per atlas) deploys aggressive late rotations that "
            "specifically eliminate catch-shoot windows. PG x ACTIVE_CLOSEOUTS BLK = -0.058, t=-3.94. "
            "The C&S mechanism is mechanically destroyed by this defense, regardless of player form."
        ),
    },
    # =========================================================
    # C6: HIGH POTENTIAL_ASSISTS (INT-1 >70th) x ISO_FORCE (INT-12) -> OVER AST
    # Motivation: ISO_FORCE defense isolates each offensive player, creating double-team kick-outs.
    # High-PA players (already wired to pass) see more kick-out opportunities when defense iso-forces.
    # Position-scheme: PG x ISO_FORCE AST = +0.12, t=3.49 (n=4122).
    # INT-1 PA fingerprint adds the player-level filter: only high-PA players benefit from ISO.
    # Atlas A = INT-1 (player_fingerprints, potential_assists), Atlas B = INT-12
    # =========================================================
    {
        "candidate_name": "C6_HIGH_PA_x_ISO_FORCE_OVER_AST",
        "atlas_A": "INT-1 (player_fingerprints, potential_assists>70th pct)",
        "atlas_B": "INT-12 (defensive_schemes, ISO FORCE)",
        "direction": "OVER",
        "target_stat": "ast",
        "player_set": high_pa_players,
        "team_list": iso_force_teams,
        "motivation": (
            "INT-1 potential_assists > 70th pct = player habitually creates multiple pass opportunities "
            "per possession (measured directly from CV ball-possession tracking). ISO_FORCE defense "
            "forces the opponent into isolation possessions, creating systematic kick-out scenarios. "
            "Position-scheme significance: PG x ISO_FORCE AST = +0.12 t=3.49. Both axes target the "
            "same mechanism: creation of ball movement from contested isolation attempts."
        ),
    },
    # =========================================================
    # C7: SHRINKER_CLUTCH (INT-26) x PERIMETER_DENIAL -> UNDER PTS
    # Motivation: SHRINKER players reduce their ball possession in pressure situations.
    # PERIMETER_DENIAL defense additionally clamps their primary shot creation mechanism.
    # Compound: they already shrink in clutch + opponent denies their primary shot route = UNDER PTS.
    # V8 tested ELEVATOR not SHRINKER. This is the mirror compound, untested.
    # Atlas A = INT-26 (clutch_cv_split, clutch_class=SHRINKER), Atlas B = INT-12
    # =========================================================
    {
        "candidate_name": "C7_SHRINKER_CLUTCH_x_PERIM_DENIAL_UNDER_PTS",
        "atlas_A": "INT-26 (clutch_cv_split, clutch_class=SHRINKER)",
        "atlas_B": "INT-12 (defensive_schemes, PERIMETER DENIAL)",
        "direction": "UNDER",
        "target_stat": "pts",
        "player_set": shrinker_players,
        "team_list": perim_denial_teams,
        "motivation": (
            "INT-26 SHRINKER = player's ball_possession_rate drops significantly in clutch (delta_ball_"
            "possession_rate z < -1.0). V8 tested ELEVATOR not SHRINKER—this is the opposite compound. "
            "PERIMETER_DENIAL further closes the primary shot creation avenue. Books may not discount "
            "for clutch role contraction when setting PTS lines for SHRINKER players."
        ),
    },
    # =========================================================
    # C8: B2B_REST (INT-13 all B2B players) x PACE_CONTROL -> UNDER PTS
    # Motivation: B2B players show elevated CV fatigue scores. PACE_CONTROL reduces possessions.
    # Fewer possessions + physical fatigue = compound UNDER pressure on PTS.
    # INT-13 atlas directly measures B2B CV behavioral shifts; PACE_CONTROL is the opponent modifier.
    # Atlas A = INT-13 (rest_cv_impact, context=B2B), Atlas B = INT-12
    # =========================================================
    {
        "candidate_name": "C8_B2B_REST_x_PACE_CONTROL_UNDER_PTS",
        "atlas_A": "INT-13 (rest_cv_impact, context=B2B)",
        "atlas_B": "INT-12 (defensive_schemes, PACE CONTROL)",
        "direction": "UNDER",
        "target_stat": "pts",
        "player_set": b2b_players,
        "team_list": pace_ctrl_teams,
        "motivation": (
            "INT-13 B2B context = player is on second game of back-to-back. CV fatigue_score delta "
            "is elevated (verified in atlas: mean z=0.5+). PACE_CONTROL defense independently reduces "
            "raw possessions/scoring opportunities. Both axes reduce the per-game scoring opportunity: "
            "fatigue suppresses efficiency, pace suppresses volume. Compound UNDER for high-volume scorers."
        ),
    },
    # =========================================================
    # C9: DRIFT to Post-Up (INT-38 recent=Post-Up) x ISO_FORCE (INT-12) -> OVER REB
    # Motivation: INT-38 player recently becoming a Post-Up Scorer is occupying paint more.
    # ISO_FORCE defense positions them near paint for iso attempts = more REB opportunities.
    # Position-scheme: C x ISO_FORCE REB = +0.31, t=2.42 (n=964, significant).
    # Atlas A = INT-38 (drift toward Post-Up), Atlas B = INT-12
    # =========================================================
    {
        "candidate_name": "C9_DRIFT_TO_POST_x_ISO_FORCE_OVER_REB",
        "atlas_A": "INT-38 (archetype_drift, recent_archetype=Post-Up Scorer)",
        "atlas_B": "INT-12 (defensive_schemes, ISO FORCE)",
        "direction": "OVER",
        "target_stat": "reb",
        "player_set": drift_to_interior,
        "team_list": iso_force_teams,
        "motivation": (
            "INT-38 drifting to Post-Up Scorer = CV tracking shows player is spending more frames near "
            "basket in recent games (play_type_post_pct rising). Books still price on old archetype. "
            "ISO_FORCE teams cede interior positioning as defense isolates on perimeter. "
            "Position-scheme: C x ISO_FORCE REB = +0.31, t=2.42. Compound: new interior role not "
            "yet priced + scheme cedes paint access."
        ),
    },
    # =========================================================
    # C10: HIGH MATCHUP TOUCHES_DEVIATION (INT-3 z>1) x HELP_DEFENSE -> OVER AST
    # Motivation: When a player's per-game touches rise vs a specific opponent (INT-3),
    # they are running more actions. HELP_DEFENSE creates kick-outs that convert to AST.
    # Atlas A = INT-3 (matchup_deviations, touches_per_game_z>1), Atlas B = INT-12
    # =========================================================
    {
        "candidate_name": "C10_HIGH_TOUCH_MATCHUP_x_HELP_DEF_OVER_AST",
        "atlas_A": "INT-3 (matchup_deviations, touches_per_game_z>1.0)",
        "atlas_B": "INT-12 (defensive_schemes, HELP DEFENSE)",
        "direction": "OVER",
        "target_stat": "ast",
        "player_set": high_touch_matchup_players,
        "team_list": help_def_teams,
        "motivation": (
            "INT-3 touches_per_game_z > 1.0 vs opponent = player historically runs MORE offensive "
            "actions vs this team (measured from CV tracking). HELP_DEFENSE creates kick-out moments. "
            "More touches + help-side rotations = structurally more AST opportunities. "
            "Different from V6/V8: this uses within-player matchup deviation rather than archetype."
        ),
    },
]


# ---------------------------------------------------------------------------
# COMPUTE ALL CANDIDATES
# ---------------------------------------------------------------------------
results = []
for c in CANDIDATES:
    sub = get_sub(c["player_set"], c["team_list"], c["target_stat"])
    r = analyze_signal(sub, c["direction"].lower())
    print(
        f"{c['candidate_name']}: n={r.get('n', 0)}, mu={r.get('mu')}, "
        f"z={r.get('z')}, p={r.get('p')}, wr={r.get('wr')}"
    )
    results.append({
        "candidate_name": c["candidate_name"],
        "atlas_A": c["atlas_A"],
        "atlas_B": c["atlas_B"],
        "direction": c["direction"],
        "target_stat": c["target_stat"],
        "n_games_matched": r.get("n", 0),
        "mean_stat_shift_vs_base": r.get("mu"),
        "std_shift": r.get("std"),
        "z_stat": r.get("z"),
        "p_value": r.get("p"),
        "win_rate": r.get("wr"),
        "ci_lo": r.get("ci_lo"),
        "ci_hi": r.get("ci_hi"),
        "motivation": c["motivation"],
    })

# ---------------------------------------------------------------------------
# SAVE OUTPUT
# ---------------------------------------------------------------------------
out_df = pd.DataFrame(results)
out_path = INTEL / "compound_candidates.parquet"
out_df.to_parquet(out_path, index=False)
print(f"\nSaved {len(out_df)} candidates to {out_path}")

# Print ranked summary
ranked = out_df.dropna(subset=["z_stat"]).sort_values("z_stat", ascending=False)
print("\n=== RANKED BY Z-STAT ===")
cols = ["candidate_name", "n_games_matched", "mean_stat_shift_vs_base", "z_stat", "p_value", "win_rate"]
print(ranked[cols].to_string(index=False))

# Clean up temp files
import os
for tmp in ["_tmp_analysis.py", "_tmp_analysis2.py"]:
    tp = ROOT / "scripts" / tmp
    if tp.exists():
        os.remove(tp)
