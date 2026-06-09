"""
INT-3: Matchup Intelligence
For each (player, opponent_team) combo with CV data, compute behavioral deviations
from the player's global baseline. Output per-(player, opp) records + per-opponent profiles.

Inputs:
  - data/nba_ai.db -> cv_features table
  - data/intelligence/player_fingerprints.parquet -> global baseline per player
  - data/nba/boxscore_<game_id>.json -> player_id -> team_abbreviation per game
  - data/nba/player_full_2024-25.json -> player_id -> name, team

Outputs:
  - data/intelligence/matchup_deviations.parquet
  - data/intelligence/opponent_imposed_profiles.json
  - vault/Intelligence/Matchup_Atlas.md
  - vault/Intelligence/Matchups/<TEAM>.md (per opponent)
"""

import os
import sys
import json
import sqlite3
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

warnings.filterwarnings("ignore")

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# --- Paths ---
BASE = Path(__file__).resolve().parent.parent
DB_PATH = BASE / "data" / "nba_ai.db"
FINGERPRINTS = BASE / "data" / "intelligence" / "player_fingerprints.parquet"
NBA_DIR = BASE / "data" / "nba"
TRACKING_DIR = BASE / "data" / "tracking"
OUT_DIR = BASE / "data" / "intelligence"
VAULT_INTEL = BASE / "vault" / "Intelligence"
VAULT_MATCHUPS = VAULT_INTEL / "Matchups"

OUT_DIR.mkdir(parents=True, exist_ok=True)
VAULT_MATCHUPS.mkdir(parents=True, exist_ok=True)

# --- CV features to analyze (reliable set from INT-1) ---
RELIABLE_FEATURES = [
    "paint_dwell_pct",
    "shot_zone_paint_pct",
    "shot_zone_mid_range_pct",
    "shot_zone_3pt_pct",
    "avg_shot_distance",
    "touches_per_game",
    "shots_per_possession",
    "possession_duration_avg",
    "second_chance_rate",
    "potential_assists",
    "preshot_velocity_peak",
    "defender_approach_speed",
    "play_type_transition_pct",
    "play_type_isolation_pct",
    "play_type_post_pct",
    "catch_shoot_pct",
    "avg_dribble_count",
    "contested_shot_rate",
    "avg_defender_distance",
]

# Additional useful CV features beyond INT-1 reliable set
# Excluded: avg_closeout_speed (100% zero), avg_contest_arm_angle (94% zero)
EXTRA_FEATURES = [
    "avg_fatigue_proxy",      # 49% zeros - usable with zero-masking
    "avg_shot_clock_at_shot", # 62% zeros - usable with zero-masking
    "avg_spacing",            # 61% zeros - usable with zero-masking
    "play_type_drive_pct",
    "made_pct",
]

ALL_FEATURES = RELIABLE_FEATURES + EXTRA_FEATURES

# Features where 0.0 means "not tracked" (sentinel) -- mask out zeros before computing stats
ZERO_SENTINEL_FEATURES = {
    "avg_spacing",
    "avg_shot_clock_at_shot",
    "avg_fatigue_proxy",
    "avg_defender_distance",  # per audit: 0.0 = no defender tracked
    "potential_assists",      # Bug 27 guard: 45.1% of CV games all-zero (xAST submodule not run)
}


# -------------------------------------------------------------
# Step 0: Load cv_features into wide format
# -------------------------------------------------------------
def load_cv_features() -> pd.DataFrame:
    """Load cv_features -> wide DataFrame indexed by (game_id, player_id)."""
    print("Loading cv_features from DB...")
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        "SELECT game_id, player_id, feature_name, feature_value FROM cv_features",
        conn,
    )
    conn.close()

    # Mask sentinel zeros for features where 0.0 means "not tracked"
    mask = df["feature_name"].isin(ZERO_SENTINEL_FEATURES) & (df["feature_value"] == 0.0)
    df.loc[mask, "feature_value"] = np.nan

    # Pivot to wide: rows=(game_id,player_id), cols=feature_name
    df_wide = df.pivot_table(
        index=["game_id", "player_id"],
        columns="feature_name",
        values="feature_value",
        aggfunc="first",
    )
    df_wide.columns.name = None
    df_wide = df_wide.reset_index()

    # Keep only numeric features we care about
    keep = ["game_id", "player_id"] + [
        f for f in ALL_FEATURES if f in df_wide.columns
    ]
    df_wide = df_wide[keep]

    print(f"  -> {len(df_wide):,} player-game rows, {len(df_wide.columns)-2} features")
    return df_wide


# -------------------------------------------------------------
# Step 1: Build game_id -> {team1, team2} and player -> team per game
# -------------------------------------------------------------
def build_team_mapping(cv_games: list[str]) -> tuple[dict, dict]:
    """
    Returns:
      game_teams: {game_id: [teamA, teamB]}
      player_game_team: {(game_id, player_id): team_abbrev}
    """
    print("Building team mapping from boxscore JSON files...")
    game_teams = {}
    player_game_team = {}

    games_resolved = 0
    games_missing = 0

    for gid in cv_games:
        bs_path = NBA_DIR / f"boxscore_{gid}.json"
        if not bs_path.exists():
            games_missing += 1
            continue

        try:
            with open(bs_path, encoding="utf-8") as f:
                bs = json.load(f)
        except Exception as e:
            games_missing += 1
            continue

        # New format: {game_id, players: [{player_id, team_abbreviation, ...}], teams: [...]}
        if "players" in bs and "teams" in bs:
            teams = [t["team_abbreviation"] for t in bs.get("teams", [])]
            game_teams[gid] = teams
            for p in bs["players"]:
                pid = p.get("player_id")
                team = p.get("team_abbreviation")
                if pid and team:
                    player_game_team[(gid, int(pid))] = team
            games_resolved += 1
        else:
            games_missing += 1

    print(f"  -> {games_resolved} games resolved, {games_missing} missing boxscore")
    return game_teams, player_game_team


# -------------------------------------------------------------
# Step 2: Load player baselines from player_fingerprints.parquet
# -------------------------------------------------------------
def load_baselines() -> pd.DataFrame:
    """Load per-player baseline means and std (from INT-1 fingerprints)."""
    print("Loading player baselines from player_fingerprints.parquet...")
    fp = pd.read_parquet(FINGERPRINTS)
    # Index is player_id
    fp.index.name = "player_id"
    # Keep only features that exist in both
    feat_cols = [f for f in ALL_FEATURES if f in fp.columns]
    print(f"  -> {len(fp)} players, {len(feat_cols)} feature baselines available")
    return fp


# -------------------------------------------------------------
# Step 3: Compute per-player std across all CV games (for z-scores)
# -------------------------------------------------------------
def compute_player_std(cv_wide: pd.DataFrame) -> pd.DataFrame:
    """
    Per-player std across all their CV games.
    Returns DataFrame indexed by player_id with std for each feature.
    """
    feat_cols = [f for f in ALL_FEATURES if f in cv_wide.columns]
    std_df = cv_wide.groupby("player_id")[feat_cols].std(ddof=0)
    return std_df


# -------------------------------------------------------------
# Step 4: Build player name + team lookup
# -------------------------------------------------------------
def build_player_lookup() -> dict:
    """Returns {player_id: {name, team}} from player_full JSONs."""
    lookup = {}
    for fname in ["player_full_2024-25.json", "player_full_2025-26.json"]:
        fpath = NBA_DIR / fname
        if not fpath.exists():
            continue
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        for name, info in data.items():
            pid = info.get("player_id")
            if pid:
                pid = int(pid)
                if pid not in lookup:
                    lookup[pid] = {
                        "name": info.get("full_name", name).title(),
                        "team": info.get("team", "UNK"),
                    }
    return lookup


# -------------------------------------------------------------
# Step 5: Assemble matchup records
# -------------------------------------------------------------
def build_matchup_records(
    cv_wide: pd.DataFrame,
    game_teams: dict,
    player_game_team: dict,
    baselines: pd.DataFrame,
    player_std: pd.DataFrame,
    player_lookup: dict,
) -> pd.DataFrame:
    """
    For each (player_id, opp_team) pair with >=1 CV game, compute:
      - matchup_mean per feature
      - delta = matchup_mean - global_baseline
      - z = delta / player_std (or dataset_std as fallback)
    """
    print("Building matchup records...")

    feat_cols = [f for f in ALL_FEATURES if f in cv_wide.columns]

    # Dataset-wide std as fallback
    dataset_std = cv_wide[feat_cols].std()

    # Tag each player-game with opponent team
    records = []
    skipped_no_team = 0

    for idx, row in cv_wide.iterrows():
        gid = row["game_id"]
        pid = int(row["player_id"])

        # Get player's team in this game
        player_team = player_game_team.get((gid, pid))
        if player_team is None:
            skipped_no_team += 1
            continue

        # Get the 2 teams in this game
        teams = game_teams.get(gid, [])
        if len(teams) < 2:
            skipped_no_team += 1
            continue

        # Opponent = the other team
        opp_team = None
        for t in teams:
            if t != player_team:
                opp_team = t
                break
        if opp_team is None:
            skipped_no_team += 1
            continue

        rec = {
            "game_id": gid,
            "player_id": pid,
            "player_team": player_team,
            "opp_team": opp_team,
        }
        for f in feat_cols:
            rec[f] = row[f] if not pd.isna(row[f]) else None

        records.append(rec)

    print(f"  -> {len(records):,} player-game records mapped, {skipped_no_team} skipped (no team)")

    df = pd.DataFrame(records)
    if df.empty:
        print("ERROR: No records mapped!")
        return pd.DataFrame()

    # Group by (player_id, opp_team) -> matchup_mean
    grp = df.groupby(["player_id", "opp_team"])
    agg_dict = {f: "mean" for f in feat_cols if f in df.columns}
    agg_dict["player_team"] = "last"
    matchup_means = grp.agg({**agg_dict, "game_id": "count"}).rename(
        columns={"game_id": "n_games_vs_opp"}
    )
    matchup_means = matchup_means.reset_index()

    print(f"  -> {len(matchup_means):,} (player, opp) matchup combos")

    # Compute deltas and z-scores
    output_rows = []
    missing_baseline = 0

    for _, mrow in matchup_means.iterrows():
        pid = int(mrow["player_id"])
        opp = mrow["opp_team"]
        n_games = int(mrow["n_games_vs_opp"])

        # Player info
        pinfo = player_lookup.get(pid, {})
        pname = pinfo.get("name", f"Player_{pid}")
        # Use team from matchup (most recent)
        pteam = str(mrow.get("player_team", pinfo.get("team", "UNK")))

        # Player baseline
        if pid in baselines.index:
            baseline = baselines.loc[pid]
        else:
            missing_baseline += 1
            baseline = None

        # Player std
        if pid in player_std.index:
            pstd = player_std.loc[pid]
        else:
            pstd = None

        out = {
            "player_id": pid,
            "player_name": pname,
            "player_team": pteam,
            "opp_team": opp,
            "n_games_vs_opp": n_games,
        }

        z_scores = {}
        deviation_flags = []
        max_abs_z = 0.0

        # For sentinel-heavy features, count how many non-NaN games the player has overall
        # to avoid spurious z-scores driven by single tracked games
        player_nonzero_counts = {}
        if pid in cv_wide["player_id"].values:
            player_cv_rows = cv_wide[cv_wide["player_id"] == pid]
            for f in feat_cols:
                if f in player_cv_rows.columns:
                    player_nonzero_counts[f] = player_cv_rows[f].notna().sum()

        for f in feat_cols:
            matchup_val = mrow.get(f)
            if matchup_val is None or pd.isna(matchup_val):
                out[f"{f}_delta"] = None
                out[f"{f}_z"] = None
                continue

            # For sentinel-heavy features, require player has >= 2 tracked games overall
            # to avoid single-game outlier driving z-score
            if f in ZERO_SENTINEL_FEATURES and player_nonzero_counts.get(f, 0) < 2:
                out[f"{f}_delta"] = None
                out[f"{f}_z"] = None
                continue

            # Delta vs baseline
            has_personal_baseline = (
                baseline is not None
                and f in baseline.index
                and not pd.isna(baseline[f])
            )
            if has_personal_baseline:
                delta = matchup_val - baseline[f]
                base_val = baseline[f]
            else:
                # No baseline -> use dataset mean as proxy (non-NaN values only)
                feat_mean = cv_wide[f].dropna().mean()
                delta = matchup_val - feat_mean
                base_val = feat_mean

            # Z-score
            # Rule: only use personal_std when we also have a personal baseline.
            # If baseline is approximate (dataset mean), z must also use dataset_std
            # to avoid inflating z via tiny personal_std.
            if has_personal_baseline and pstd is not None and f in pstd.index and pstd[f] > 1e-9:
                z = delta / pstd[f]
            elif dataset_std[f] > 1e-9:
                z = delta / dataset_std[f]
            else:
                z = 0.0

            out[f"{f}_delta"] = round(delta, 4)
            out[f"{f}_z"] = round(z, 3)
            z_scores[f] = z
            if abs(z) > max_abs_z:
                max_abs_z = abs(z)

        # Deviation flags: |z| > 1.5
        for f, z in z_scores.items():
            if abs(z) > 1.5:
                direction = "^" if z > 0 else "v"
                deviation_flags.append(f"{f}{direction}({z:+.1f}sigma)")

        out["max_abs_z"] = round(max_abs_z, 3)
        out["notable_flag"] = max_abs_z > 1.5
        out["deviation_flags"] = ", ".join(deviation_flags) if deviation_flags else ""
        output_rows.append(out)

    print(f"  -> {missing_baseline} players missing from fingerprints (using dataset mean as baseline)")

    result = pd.DataFrame(output_rows)
    return result


# -------------------------------------------------------------
# Step 6: Per-opponent imposed profiles
# -------------------------------------------------------------
def build_opponent_profiles(matchup_df: pd.DataFrame, cv_wide: pd.DataFrame) -> dict:
    """
    For each opp_team, aggregate mean deviation across all players who faced them.
    Uses delta/dataset_std for cross-player comparability (not personal z-scores
    which can be inflated by tiny personal_std for edge-case players).
    Returns dict for JSON output.
    """
    print("Building per-opponent imposed profiles...")

    feat_cols = [f for f in ALL_FEATURES if f in cv_wide.columns]
    delta_cols = [f"{f}_delta" for f in feat_cols if f"{f}_delta" in matchup_df.columns]

    # Dataset-wide std for normalization (comparable across players)
    dataset_std = cv_wide[feat_cols].std()

    profiles = {}
    for opp_team, grp in matchup_df.groupby("opp_team"):
        n_player_games = grp["n_games_vs_opp"].sum()
        n_unique_players = len(grp)

        # Mean z-score across all players who faced this team
        # Use delta/dataset_std for stable cross-player comparison
        mean_z = {}
        for dc in delta_cols:
            fname = dc.replace("_delta", "")
            vals = grp[dc].dropna()
            if len(vals) > 0 and fname in dataset_std.index and dataset_std[fname] > 1e-9:
                mean_z[fname] = round(vals.mean() / dataset_std[fname], 3)

        # Sort by |mean_z| to find most impactful features
        sorted_feats = sorted(mean_z.items(), key=lambda x: abs(x[1]), reverse=True)

        # Auto-interpretation
        interpretations = []
        for fname, mz in sorted_feats[:5]:
            if abs(mz) < 0.3:
                continue
            direction = "increases" if mz > 0 else "decreases"
            clean_name = fname.replace("_", " ")
            interpretations.append(f"{direction} {clean_name} ({mz:+.2f}sigma avg)")

        interp = "; ".join(interpretations[:3]) if interpretations else "No strong imposed pattern"

        profiles[str(opp_team)] = {
            "n_player_games_observed": int(n_player_games),
            "n_unique_opponents": int(n_unique_players),
            "imposed_deviations": {k: v for k, v in sorted_feats},
            "top_imposed": {k: v for k, v in sorted_feats[:5]},
            "interpretation": interp,
        }

    print(f"  -> {len(profiles)} opponent profiles built")
    return profiles


# -------------------------------------------------------------
# Step 7: Notable matchup discoveries
# -------------------------------------------------------------
def find_notable_matchups(matchup_df: pd.DataFrame, cv_wide: pd.DataFrame, top_n: int = 20) -> list:
    """Find top extreme (player, opp) deviations with >=2 games."""
    feat_cols = [f for f in ALL_FEATURES if f in cv_wide.columns]
    z_cols = [f"{f}_z" for f in feat_cols if f"{f}_z" in matchup_df.columns]

    # Expand to one row per feature, find max |z|
    rows = []
    for _, r in matchup_df[matchup_df["n_games_vs_opp"] >= 2].iterrows():
        for zc in z_cols:
            z_val = r.get(zc)
            if z_val is None or pd.isna(z_val):
                continue
            if abs(z_val) < 1.5:
                continue
            fname = zc.replace("_z", "")
            delta_col = f"{fname}_delta"
            delta = r.get(delta_col)
            rows.append({
                "player_id": r["player_id"],
                "player_name": r["player_name"],
                "player_team": r["player_team"],
                "opp_team": r["opp_team"],
                "n_games": r["n_games_vs_opp"],
                "feature": fname,
                "z_score": z_val,
                "delta": delta,
                "abs_z": abs(z_val),
            })

    if not rows:
        return []

    df = pd.DataFrame(rows).sort_values("abs_z", ascending=False)
    top = df.head(top_n)

    # Load baselines for claims
    baselines = pd.read_parquet(FINGERPRINTS)

    results = []
    for _, r in top.iterrows():
        pid = int(r["player_id"])
        fname = r["feature"]
        z = r["z_score"]
        direction = "higher" if z > 0 else "lower"
        clean_feat = fname.replace("_", " ")

        # Build baseline value context
        baseline_val = None
        if pid in baselines.index and fname in baselines.columns:
            baseline_val = baselines.loc[pid, fname]

        # Compute matchup value
        delta = r["delta"]
        if baseline_val is not None and delta is not None and not pd.isna(delta):
            matchup_val = baseline_val + delta
            claim = (
                f"{r['player_name']} vs {r['opp_team']}: {clean_feat} {z:+.1f}sigma "
                f"(matchup {matchup_val:.2f} vs baseline {baseline_val:.2f}) -- "
                f"{r['n_games']} games"
            )
        else:
            claim = (
                f"{r['player_name']} vs {r['opp_team']}: {clean_feat} {z:+.1f}sigma "
                f"({direction} than usual) -- {r['n_games']} games"
            )

        results.append({
            **r.to_dict(),
            "claim": claim,
        })

    return results


# -------------------------------------------------------------
# Step 8: Write Vault outputs
# -------------------------------------------------------------
def write_matchup_atlas(
    matchup_df: pd.DataFrame,
    opp_profiles: dict,
    notable: list,
    coverage: dict,
):
    """Write vault/Intelligence/Matchup_Atlas.md"""
    print("Writing Matchup_Atlas.md...")

    n_combos = len(matchup_df)
    n_combos_2plus = len(matchup_df[matchup_df["n_games_vs_opp"] >= 2])
    n_notable = len(matchup_df[matchup_df["notable_flag"] == True])
    n_opp_10plus = sum(
        1 for v in opp_profiles.values() if v["n_player_games_observed"] >= 10
    )

    # Top 20 most extreme matchups table
    top20 = (
        matchup_df[matchup_df["n_games_vs_opp"] >= 2]
        .sort_values("max_abs_z", ascending=False)
        .head(20)
    )

    lines = [
        "# INT-3: Matchup Intelligence Atlas",
        "",
        f"*Generated: 2026-05-28*",
        "",
        "## Coverage",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Player-games with team mapping resolved | {coverage['resolved']:,} / {coverage['total']:,} |",
        f"| Unique CV games analyzed | {coverage['cv_games']:,} |",
        f"| (player, opp) combos with >=1 game | {n_combos:,} |",
        f"| (player, opp) combos with >=2 games (reliable) | {n_combos_2plus:,} |",
        f"| Combos with notable deviation (|z| > 1.5) | {n_notable:,} |",
        f"| Opponent teams with >=10 player-games observed | {n_opp_10plus} / 30 |",
        "",
        "## Top 20 Most Extreme Matchups (>=2 games vs opponent)",
        "",
        "| Player | Opp | Max |z| | n_games | Top Deviation Flags |",
        "|--------|-----|--------|---------|---------------------|",
    ]

    for _, r in top20.iterrows():
        flags = str(r.get("deviation_flags", ""))[:80]
        lines.append(
            f"| {r['player_name']} | {r['opp_team']} | {r['max_abs_z']:.2f} | "
            f"{r['n_games_vs_opp']} | {flags} |"
        )

    lines += [
        "",
        "## Top Notable Matchup Claims (>=2 games, |z| > 1.5)",
        "",
    ]
    for n in notable[:20]:
        lines.append(f"- {n['claim']}")

    lines += [
        "",
        "## Per-Opponent Imposed Profile Summary",
        "",
        "*How each team affects opposing players' CV behaviors on average*",
        "",
        "| Team | Players Obs | Games Obs | Top Imposed Effect |",
        "|------|-------------|-----------|-------------------|",
    ]

    for team, prof in sorted(opp_profiles.items()):
        top_effect = ""
        if prof["top_imposed"]:
            feat, z = next(iter(prof["top_imposed"].items()))
            top_effect = f"{feat.replace('_',' ')} {z:+.2f}sigma"
        lines.append(
            f"| {team} | {prof['n_unique_opponents']} | "
            f"{prof['n_player_games_observed']} | {top_effect} |"
        )

    lines += [
        "",
        "## How to Query",
        "",
        "```python",
        "import pandas as pd",
        "df = pd.read_parquet('data/intelligence/matchup_deviations.parquet')",
        "",
        "# Extreme matchups vs BOS",
        "df.query(\"opp_team == 'BOS' and max_abs_z > 1.5\")",
        "",
        "# All matchups for a player",
        "df[df['player_name'].str.contains('Curry')]",
        "",
        "# Players BOS affects the most (paint deviation)",
        "df.query(\"opp_team == 'BOS'\").sort_values('paint_dwell_pct_z')",
        "```",
        "",
        "## Honest Caveats",
        "",
        "- **(player, opp) combos with n=1 game are noisy** -- treat as directional signal only",
        "- **Attribution uncertainty**: CV player_id resolution depends on boxscore cross-reference; "
        "~70% of CV tracking slots resolve to NBA IDs per prior audits. Unresolved players are excluded.",
        "- **Small sample per opponent**: most opponents have 1-5 games of CV data, not a full 82-game season. "
        "Imposed profiles reflect the tracked sample, not full-season tendencies.",
        "- **Cross-season aggregation**: players traded mid-season have CV from both team contexts; "
        "player_team column reflects the most recent mapping.",
        "- **Sentinel values**: `avg_defender_distance = 0.0` appears as a sentinel in some games "
        "(no defender tracked) -- not a true '0 feet away'. May inflate defender_approach_speed z-scores.",
        "- **Causality**: a player having unusual stats vs a team could reflect opponent defense, "
        "game script, roster matchups, or sample variance. Intelligence claim, not causal proof.",
        "",
        "## Files",
        "",
        "- `scripts/build_matchup_intel.py` -- this pipeline",
        "- `data/intelligence/matchup_deviations.parquet` -- queryable (player, opp) records",
        "- `data/intelligence/opponent_imposed_profiles.json` -- per-opponent style summary",
        f"- `vault/Intelligence/Matchups/*.md` -- {len(opp_profiles)} per-opponent files",
    ]

    out_path = VAULT_INTEL / "Matchup_Atlas.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  -> Written: {out_path}")


def write_opponent_files(
    matchup_df: pd.DataFrame,
    opp_profiles: dict,
):
    """Write vault/Intelligence/Matchups/<TEAM>.md for each opponent."""
    print("Writing per-opponent vault files...")

    feat_cols = [f for f in ALL_FEATURES if f in matchup_df.columns or f"{f}_z" in matchup_df.columns]

    count = 0
    for opp_team, prof in sorted(opp_profiles.items()):
        opp_df = matchup_df[matchup_df["opp_team"] == opp_team].copy()
        n_obs = prof["n_player_games_observed"]
        n_players = prof["n_unique_opponents"]
        sample_warn = n_obs < 10

        lines = [
            f"# Matchup Intelligence: vs {opp_team}",
            "",
            f"*{n_players} players observed, {n_obs} total player-games*",
        ]

        if sample_warn:
            lines += [
                "",
                f"> **Sample Warning**: Only {n_obs} player-games observed vs {opp_team}. "
                "Profile is directional at best.",
            ]

        lines += [
            "",
            "## Imposed Profile",
            "",
            "*How {opp_team} affects opposing players' CV behaviors (mean z-score across all opponents)*".format(opp_team=opp_team),
            "",
            "| Feature | Mean Imposed Deviation (sigma) |",
            "|---------|---------------------------|",
        ]

        for feat, z in sorted(prof["imposed_deviations"].items(), key=lambda x: abs(x[1]), reverse=True):
            if abs(z) < 0.15:
                continue
            direction = "^ more" if z > 0 else "v less"
            clean = feat.replace("_", " ")
            lines.append(f"| {clean} | {z:+.2f}sigma ({direction}) |")

        lines += [
            "",
            f"**Interpretation:** {prof['interpretation']}",
            "",
            "## Top Player Matchup Deviations vs " + opp_team,
            "",
        ]

        # Players with notable deviations (>=1 game), sorted by max_abs_z
        top_players = opp_df.sort_values("max_abs_z", ascending=False).head(10)

        if len(top_players) == 0:
            lines.append("*No notable matchup deviations found.*")
        else:
            lines += [
                "| Player | n_games | Max |z| | Top Deviation |",
                "|--------|---------|---------|---------------|",
            ]
            for _, r in top_players.iterrows():
                flags = str(r.get("deviation_flags", ""))[:70] or "none"
                n_warn = " ! n=1" if r["n_games_vs_opp"] == 1 else ""
                lines.append(
                    f"| {r['player_name']} | {r['n_games_vs_opp']}{n_warn} | "
                    f"{r['max_abs_z']:.2f} | {flags} |"
                )

        # Per-feature breakdown for top 5 players (>=2 games)
        reliable_players = opp_df[opp_df["n_games_vs_opp"] >= 2].sort_values(
            "max_abs_z", ascending=False
        ).head(5)

        if len(reliable_players) > 0:
            lines += ["", "## Per-Player Feature Breakdown (>=2 games only)", ""]
            for _, r in reliable_players.iterrows():
                lines += [f"### {r['player_name']} ({r['n_games_vs_opp']} games vs {opp_team})", ""]
                lines += ["| Feature | Delta | z-score |", "|---------|-------|---------|"]
                for f in feat_cols:
                    zcol = f"{f}_z"
                    dcol = f"{f}_delta"
                    if zcol not in r.index:
                        continue
                    z = r.get(zcol)
                    d = r.get(dcol)
                    if z is None or pd.isna(z) or abs(z) < 0.5:
                        continue
                    z_str = f"{z:+.2f}sigma"
                    d_str = f"{d:+.3f}" if d is not None and not pd.isna(d) else "N/A"
                    clean = f.replace("_", " ")
                    marker = " <- notable" if abs(z) > 1.5 else ""
                    lines.append(f"| {clean} | {d_str} | {z_str}{marker} |")
                lines.append("")

        out_path = VAULT_MATCHUPS / f"{opp_team}.md"
        out_path.write_text("\n".join(lines), encoding="utf-8")
        count += 1

    print(f"  -> {count} opponent vault files written")


# -------------------------------------------------------------
# Main
# -------------------------------------------------------------
def main():
    print("=" * 60)
    print("INT-3: Matchup Intelligence")
    print("=" * 60)

    # Load cv_features
    cv_wide = load_cv_features()
    cv_games = cv_wide["game_id"].unique().tolist()

    # Team mapping
    game_teams, player_game_team = build_team_mapping(cv_games)

    # Player baselines
    baselines = load_baselines()

    # Player std
    player_std = compute_player_std(cv_wide)

    # Player name/team lookup
    player_lookup = build_player_lookup()

    # Coverage stats
    total_player_games = len(cv_wide)
    resolved = sum(
        1
        for _, row in cv_wide.iterrows()
        if (row["game_id"], int(row["player_id"])) in player_game_team
        and row["game_id"] in game_teams
    )
    coverage = {
        "total": total_player_games,
        "resolved": resolved,
        "cv_games": len(cv_games),
    }
    print(f"\nCoverage: {resolved:,} / {total_player_games:,} player-games mapped to teams")

    # Build matchup records
    matchup_df = build_matchup_records(
        cv_wide, game_teams, player_game_team, baselines, player_std, player_lookup
    )

    if matchup_df.empty:
        print("ERROR: No matchup records built. Check team mapping coverage.")
        sys.exit(1)

    # Save parquet
    parquet_path = OUT_DIR / "matchup_deviations.parquet"
    matchup_df.to_parquet(parquet_path, index=False)
    print(f"\nSaved matchup_deviations.parquet: {len(matchup_df):,} rows -> {parquet_path}")

    # Opponent profiles
    opp_profiles = build_opponent_profiles(matchup_df, cv_wide)

    # Save JSON
    json_path = OUT_DIR / "opponent_imposed_profiles.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(opp_profiles, f, indent=2)
    print(f"Saved opponent_imposed_profiles.json: {len(opp_profiles)} teams -> {json_path}")

    # Notable matchups
    notable = find_notable_matchups(matchup_df, cv_wide, top_n=20)

    # Vault outputs
    write_matchup_atlas(matchup_df, opp_profiles, notable, coverage)
    write_opponent_files(matchup_df, opp_profiles)

    # Final report
    n_combos = len(matchup_df)
    n_2plus = len(matchup_df[matchup_df["n_games_vs_opp"] >= 2])
    n_notable = len(matchup_df[matchup_df["notable_flag"] == True])
    n_opp_teams = len(opp_profiles)
    n_opp_10plus = sum(1 for v in opp_profiles.values() if v["n_player_games_observed"] >= 10)

    print("\n" + "=" * 60)
    print("INT-3 COMPLETE")
    print("=" * 60)
    print(f"Player-games with team mapping resolved: {resolved:,} / {total_player_games:,}")
    print(f"(player, opp) combos: {n_combos:,} total, {n_2plus:,} with >=2 games")
    print(f"Notable deviations (|z| > 1.5): {n_notable:,} combos")
    print(f"Opponent teams: {n_opp_teams} observed, {n_opp_10plus} with >=10 player-games")

    print("\nTop 10 most extreme matchups (>=2 games):")
    top10 = (
        matchup_df[matchup_df["n_games_vs_opp"] >= 2]
        .sort_values("max_abs_z", ascending=False)
        .head(10)
    )
    for _, r in top10.iterrows():
        flags = str(r.get("deviation_flags", ""))[:60]
        print(
            f"  {r['player_name']:25s} vs {r['opp_team']} | z={r['max_abs_z']:.2f} "
            f"| n={r['n_games_vs_opp']} | {flags}"
        )

    print("\nPer-opponent imposed profile highlights:")
    # Find team with most negative paint deviation
    paint_z = {t: p["imposed_deviations"].get("paint_dwell_pct", 0) for t, p in opp_profiles.items()}
    tightest = min(paint_z, key=lambda t: paint_z[t]) if paint_z else "N/A"
    most_paint_allowing = max(paint_z, key=lambda t: paint_z[t]) if paint_z else "N/A"
    transition_z = {t: p["imposed_deviations"].get("play_type_transition_pct", 0) for t, p in opp_profiles.items()}
    fastest = max(transition_z, key=lambda t: transition_z[t]) if transition_z else "N/A"
    contested_z = {t: p["imposed_deviations"].get("contested_shot_rate", 0) for t, p in opp_profiles.items()}
    most_contested = max(contested_z, key=lambda t: contested_z[t]) if contested_z else "N/A"

    print(f"  Limits paint most (paint_dwell_pct v): {tightest} ({paint_z.get(tightest, 0):+.2f}sigma)")
    print(f"  Allows paint most (paint_dwell_pct ^): {most_paint_allowing} ({paint_z.get(most_paint_allowing, 0):+.2f}sigma)")
    print(f"  Most transition-forcing: {fastest} ({transition_z.get(fastest, 0):+.2f}sigma)")
    print(f"  Highest contested shot rate forced: {most_contested} ({contested_z.get(most_contested, 0):+.2f}sigma)")

    print(f"\nFiles written:")
    print(f"  {parquet_path}")
    print(f"  {json_path}")
    print(f"  {VAULT_INTEL / 'Matchup_Atlas.md'}")
    print(f"  {VAULT_MATCHUPS}/<team>.md ({n_opp_teams} files)")


if __name__ == "__main__":
    main()
