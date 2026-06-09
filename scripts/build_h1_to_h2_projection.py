"""
INT-42 -- H1 to H2 Stat Projection Intelligence
================================================
Given halftime box stats + context (clutch tag, B2B, closer profile),
project H2 player stat output for live-betting use.

Methodology:
- H1 and H2 stats derived from player_quarter_stats.parquet (periods 1+2 vs 3+4)
- Context features from: clutch_rankings.json (INT-23), quarter_signatures.json (INT-41),
  rest_travel.parquet (INT-22 B2B)
- Per-player multiplier: base 1.0 + clutch_adj + closer_adj + b2b_adj
- Validation: projected_H2 vs actual_H2 -- compute MAE and compare to naive (H1x2) baseline
"""

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
INTEL = DATA / "intelligence"
VAULT = ROOT / "vault" / "Intelligence"

OUT_PARQUET = INTEL / "h1_h2_projections.parquet"
OUT_JSON = INTEL / "h2_projection_signals.json"
ATLAS_MD = VAULT / "H1_to_H2_Projection_Atlas.md"

# ── Multiplier constants (per spec) ─────────────────────────────────────────
BASE_MULT = 1.0
ADJ = {
    "CLOSER":    +0.10,
    "FAST_STARTER": -0.15,
    "FLAT":       0.00,
    "VARIABLE":   0.00,
    "ELEVATOR":  +0.15,   # clutch elevator + close game
    "SHRINKER":  -0.15,
    "B2B":       -0.10,
}

STATS = ["pts", "reb", "ast"]


# ── Step 1 -- Load H1 / H2 stats from player_quarter_stats ───────────────────
def load_h1_h2() -> pd.DataFrame:
    qs = pd.read_parquet(DATA / "player_quarter_stats.parquet")

    h1 = (
        qs[qs["period"].isin([1, 2])]
        .groupby(["game_id", "player_id"])[STATS + ["min"]]
        .sum()
        .rename(columns={s: f"{s}_h1" for s in STATS} | {"min": "min_h1"})
    )
    h2 = (
        qs[qs["period"].isin([3, 4])]
        .groupby(["game_id", "player_id"])[STATS + ["min"]]
        .sum()
        .rename(columns={s: f"{s}_h2" for s in STATS} | {"min": "min_h2"})
    )

    both = h1.join(h2, how="inner").reset_index()

    # Require meaningful minutes both halves (avoids DNP subs distorting averages)
    both = both[(both["min_h1"] >= 3) & (both["min_h2"] >= 3)].copy()
    return both


# ── Step 2 -- Build context feature tables ───────────────────────────────────
def load_clutch_tags() -> dict:
    """player_id -> ELEVATOR | SHRINKER | NEUTRAL"""
    with open(INTEL / "clutch_rankings.json", encoding="utf-8") as f:
        cr = json.load(f)
    mapping = {}
    for cat, tag in [("elevators", "ELEVATOR"), ("shrinkers", "SHRINKER"), ("neutrals", "NEUTRAL")]:
        for p in cr.get(cat, []):
            mapping[int(p["player_id"])] = tag
    return mapping


def load_closer_tags() -> dict:
    """player_id -> CLOSER | FAST_STARTER | FLAT | VARIABLE.
    quarter_signatures stores CV slot_ids (1-10), not NBA player_ids.
    We match via player display_name -> NBA player_id."""
    with open(INTEL / "quarter_signatures.json", encoding="utf-8") as f:
        qs = json.load(f)
    pos = pd.read_parquet(DATA / "player_positions.parquet")
    name_to_pid = {
        str(n).lower(): int(pid)
        for n, pid in zip(pos["display_name"], pos["player_id"])
    }
    mapping = {}
    for player_name, v in qs.get("players", {}).items():
        tag = v.get("tag")
        if tag is None:
            continue
        pid = name_to_pid.get(player_name.lower())
        if pid is not None:
            mapping[pid] = tag
    return mapping


def load_b2b_flags() -> pd.DataFrame:
    """Returns DataFrame with game_id, team_abbreviation, is_b2b"""
    rt = pd.read_parquet(DATA / "rest_travel.parquet")
    return rt[["game_id", "team_abbreviation", "is_b2b"]].copy()


def load_player_names() -> dict:
    """player_id -> display_name"""
    pos = pd.read_parquet(DATA / "player_positions.parquet")
    return dict(zip(pos["player_id"], pos["display_name"]))


def load_team_lookup() -> pd.DataFrame:
    """Returns game_id + player_id -> team_abbreviation using player_pf"""
    pf = pd.read_parquet(DATA / "player_pf.parquet")
    return pf[["game_id", "player_id", "team_abbreviation"]].drop_duplicates()


# ── Step 3 -- Assemble per-game rows with context ────────────────────────────
def build_dataset() -> pd.DataFrame:
    df = load_h1_h2()

    clutch_map = load_clutch_tags()
    closer_map = load_closer_tags()
    b2b_df = load_b2b_flags()
    names_map = load_player_names()
    team_lu = load_team_lookup()

    # Attach team
    df = df.merge(team_lu, on=["game_id", "player_id"], how="left")

    # Attach B2B flag (team-level)
    b2b_df["is_b2b"] = b2b_df["is_b2b"].fillna(0).astype(int)
    df = df.merge(b2b_df, on=["game_id", "team_abbreviation"], how="left")
    df["is_b2b"] = df["is_b2b"].fillna(0).astype(int)

    # Attach context tags
    df["clutch_tag"] = df["player_id"].map(clutch_map).fillna("NEUTRAL")
    df["closer_tag"] = df["player_id"].map(closer_map).fillna("FLAT")
    df["player_name"] = df["player_id"].map(names_map).fillna(df["player_id"].astype(str))

    return df


# ── Step 4 -- Compute per-row multiplier ─────────────────────────────────────
def compute_multiplier(row: pd.Series) -> float:
    mult = BASE_MULT
    mult += ADJ.get(row["clutch_tag"], 0.0)
    mult += ADJ.get(row["closer_tag"], 0.0)
    if row["is_b2b"] == 1:
        mult += ADJ["B2B"]
    return max(mult, 0.4)   # floor -- never project negative


def apply_projections(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["multiplier"] = df.apply(compute_multiplier, axis=1)

    for stat in STATS:
        df[f"proj_{stat}_h2"] = (df[f"{stat}_h1"] * df["multiplier"]).round(2)
        df[f"naive_{stat}_h2"] = (df[f"{stat}_h1"] * 1.0).round(2)  # naive = repeat H1
        df[f"err_proj_{stat}"] = (df[f"proj_{stat}_h2"] - df[f"{stat}_h2"]).abs()
        df[f"err_naive_{stat}"] = (df[f"naive_{stat}_h2"] - df[f"{stat}_h2"]).abs()

    return df


# ── Step 5 -- Per-player aggregation ─────────────────────────────────────────
def aggregate_per_player(df: pd.DataFrame) -> pd.DataFrame:
    records = []

    for pid, grp in df.groupby("player_id"):
        n = len(grp)
        if n < 2:
            continue

        name = grp["player_name"].iloc[0]
        clutch = grp["clutch_tag"].iloc[0]
        closer = grp["closer_tag"].iloc[0]
        b2b_rate = grp["is_b2b"].mean()
        base_mult = grp["multiplier"].mean()

        row = {
            "player_id": pid,
            "player_name": name,
            "n_games": n,
            "clutch_tag": clutch,
            "closer_tag": closer,
            "b2b_rate": round(b2b_rate, 3),
            "base_multiplier": round(base_mult, 4),
            "clutch_adj": ADJ.get(clutch, 0.0),
            "closer_adj": ADJ.get(closer, 0.0),
            "b2b_adj": ADJ["B2B"] * b2b_rate,
        }

        for stat in STATS:
            mae_proj = grp[f"err_proj_{stat}"].mean()
            mae_naive = grp[f"err_naive_{stat}"].mean()
            improvement_pct = (
                (mae_naive - mae_proj) / mae_naive * 100 if mae_naive > 0 else 0.0
            )
            row[f"MAE_proj_{stat}"] = round(mae_proj, 4)
            row[f"MAE_naive_{stat}"] = round(mae_naive, 4)
            row[f"improvement_pct_{stat}"] = round(improvement_pct, 2)

        # Composite MAE across all stats (PTS weighted 2x for betting relevance)
        row["MAE_projected"] = round(
            (2 * row["MAE_proj_pts"] + row["MAE_proj_reb"] + row["MAE_proj_ast"]) / 4, 4
        )
        row["MAE_naive"] = round(
            (2 * row["MAE_naive_pts"] + row["MAE_naive_reb"] + row["MAE_naive_ast"]) / 4, 4
        )
        row["improvement_pct_composite"] = round(
            (row["MAE_naive"] - row["MAE_projected"]) / row["MAE_naive"] * 100
            if row["MAE_naive"] > 0 else 0.0, 2
        )

        records.append(row)

    return pd.DataFrame(records).sort_values("MAE_projected")


# ── Step 6 -- League-wide multiplier patterns ────────────────────────────────
def league_patterns(df: pd.DataFrame) -> dict:
    patterns = {}

    # B2B effect on H2 vs H1
    b2b_games = df[df["is_b2b"] == 1]
    non_b2b = df[df["is_b2b"] == 0]

    for stat in STATS:
        if len(b2b_games) > 0 and len(non_b2b) > 0:
            b2b_ratio = (b2b_games[f"{stat}_h2"] / b2b_games[f"{stat}_h1"].replace(0, np.nan)).median()
            norm_ratio = (non_b2b[f"{stat}_h2"] / non_b2b[f"{stat}_h1"].replace(0, np.nan)).median()
            patterns[f"b2b_{stat}_h2_vs_h1_ratio"] = round(float(b2b_ratio), 3)
            patterns[f"normal_{stat}_h2_vs_h1_ratio"] = round(float(norm_ratio), 3)

    # Clutch elevator effect
    elev = df[df["clutch_tag"] == "ELEVATOR"]
    shrink = df[df["clutch_tag"] == "SHRINKER"]
    for stat in ["pts"]:
        if len(elev) > 0:
            patterns[f"elevator_{stat}_h2_vs_h1_ratio"] = round(
                float((elev[f"{stat}_h2"] / elev[f"{stat}_h1"].replace(0, np.nan)).median()), 3
            )
        if len(shrink) > 0:
            patterns[f"shrinker_{stat}_h2_vs_h1_ratio"] = round(
                float((shrink[f"{stat}_h2"] / shrink[f"{stat}_h1"].replace(0, np.nan)).median()), 3
            )

    # Closer vs fast_starter
    closer = df[df["closer_tag"] == "CLOSER"]
    fs = df[df["closer_tag"] == "FAST_STARTER"]
    for stat in ["pts"]:
        if len(closer) > 0:
            patterns[f"closer_{stat}_h2_vs_h1_ratio"] = round(
                float((closer[f"{stat}_h2"] / closer[f"{stat}_h1"].replace(0, np.nan)).median()), 3
            )
        if len(fs) > 0:
            patterns[f"fast_starter_{stat}_h2_vs_h1_ratio"] = round(
                float((fs[f"{stat}_h2"] / fs[f"{stat}_h1"].replace(0, np.nan)).median()), 3
            )

    # Overall H2/H1 ratio
    for stat in STATS:
        patterns[f"league_{stat}_h2_vs_h1_ratio"] = round(
            float((df[f"{stat}_h2"] / df[f"{stat}_h1"].replace(0, np.nan)).median()), 3
        )

    return patterns


# ── Step 7 -- Build JSON signals ─────────────────────────────────────────────
def build_signals(per_player: pd.DataFrame, patterns: dict) -> dict:
    top25_predictable = (
        per_player.nsmallest(25, "MAE_projected")[
            ["player_name", "n_games", "MAE_projected", "MAE_naive",
             "improvement_pct_composite", "clutch_tag", "closer_tag"]
        ]
        .to_dict(orient="records")
    )

    top25_volatile = (
        per_player.nlargest(25, "MAE_projected")[
            ["player_name", "n_games", "MAE_projected", "MAE_naive",
             "improvement_pct_composite", "clutch_tag", "closer_tag"]
        ]
        .to_dict(orient="records")
    )

    return {
        "generated": pd.Timestamp.now().isoformat(),
        "total_players_profiled": int(len(per_player)),
        "league_patterns": patterns,
        "top25_most_predictable": top25_predictable,
        "top25_most_volatile": top25_volatile,
    }


# ── Step 8 -- Write Atlas markdown ───────────────────────────────────────────
def write_atlas(
    per_player: pd.DataFrame,
    patterns: dict,
    n_games: int,
    n_players: int,
):
    VAULT.mkdir(parents=True, exist_ok=True)

    top10_pred = per_player.nsmallest(10, "MAE_projected")
    top10_vol = per_player.nlargest(10, "MAE_projected")

    def pct_str(v):
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:.1f}%"

    def ratio_str(key):
        v = patterns.get(key)
        if v is None:
            return "N/A"
        pct = (v - 1.0) * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}%"

    top10_pred_rows = "\n".join(
        f"| {r['player_name']} | {r['n_games']} | {r['MAE_proj_pts']:.3f} | {r['MAE_naive_pts']:.3f} | {pct_str(r['improvement_pct_pts'])} |"
        for _, r in top10_pred.iterrows()
    )
    top10_vol_rows = "\n".join(
        f"| {r['player_name']} | {r['n_games']} | {r['MAE_proj_pts']:.3f} |"
        for _, r in top10_vol.iterrows()
    )

    atlas = f"""# H1 to H2 Stat Projection Atlas

## Methodology
At halftime, project H2 stats using H1 stats x context modifiers (clutch tag, B2B, closer/fast-starter profile).

**Formula:** `projected_H2 = H1_stat x multiplier`
where `multiplier = 1.0 + clutch_adj + closer_adj + b2b_adj`

| Modifier | Tag | Adjustment |
|---|---|---|
| Q4 closer | CLOSER | +0.10 |
| Fast starter | FAST_STARTER | -0.15 |
| Clutch elevator | ELEVATOR | +0.15 |
| Clutch shrinker | SHRINKER | -0.15 |
| Back-to-back | B2B | -0.10 |
| Neutral/flat | NEUTRAL/FLAT | 0.00 |

## Coverage
- Games with H1+H2 data: {n_games}
- Players profiled: {n_players}
- Source: `data/player_quarter_stats.parquet` (periods 1+2 = H1, 3+4 = H2)
- Context: `clutch_rankings.json` (INT-23), `quarter_signatures.json` (INT-41), `rest_travel.parquet` (INT-22)

## Top 10 most-predictable players (use projections with confidence)
| Player | Games | Proj MAE (PTS) | Naive MAE (PTS) | Improvement |
|---|---|---|---|---|
{top10_pred_rows}

## Top 10 most-volatile players (projections uncertain -- widen confidence interval)
| Player | Games | Proj MAE (PTS) |
|---|---|---|
{top10_vol_rows}

## League-wide H2/H1 ratio patterns
| Context | PTS H2 vs H1 | Interpretation |
|---|---|---|
| League average | {ratio_str("league_pts_h2_vs_h1_ratio")} | Baseline second-half scoring change |
| B2B games | {ratio_str("b2b_pts_h2_vs_h1_ratio")} | Fatigue effect |
| Normal rest | {ratio_str("normal_pts_h2_vs_h1_ratio")} | Control group |
| Clutch elevator | {ratio_str("elevator_pts_h2_vs_h1_ratio")} | Late-game risers |
| Clutch shrinker | {ratio_str("shrinker_pts_h2_vs_h1_ratio")} | Late-game faders |
| Q4 closer | {ratio_str("closer_pts_h2_vs_h1_ratio")} | Closers ramp in H2 |
| Fast starter | {ratio_str("fast_starter_pts_h2_vs_h1_ratio")} | Starters fade in H2 |

## How to use (live betting at halftime)
1. Pull halftime box score -- get H1 pts/reb/ast for the target player
2. Identify player context: is this a B2B? Is the player a clutch elevator/shrinker? Closer or fast-starter?
3. Apply multiplier from the per-player table (`data/intelligence/h1_h2_projections.parquet`)
4. Compare projected H2 stat to sportsbook H2 prop line
5. **Bet if |projection - line| / line > 5%**
6. Size with INT-16 x INT-39 Kelly stack

## Multiplier lookup quick reference
```
projected_H2 = H1_stat x multiplier

Default (no tags):         multiplier = 1.00
ELEVATOR + CLOSER:         multiplier = 1.25  (biggest upside)
ELEVATOR + CLOSER + B2B:   multiplier = 1.15
SHRINKER + FAST_STARTER:   multiplier = 0.70  (biggest fade)
B2B only:                  multiplier = 0.90
CLOSER only:               multiplier = 1.10
```

## Honest caveats
- **H2 = full game stats − H1** is an approximation; minutes distribution differs by quarter
- Minimum filter: >=3 minutes each half (filters DNP/injured out early)
- Multipliers are heuristic constants from design spec; sample size too small for ML-fitting
- Clutch tag coverage: {len(patterns.get('league_pts_h2_vs_h1_ratio', 0) and [])} (42 players); closer tag: 9 players -- most players fall back to NEUTRAL/FLAT
- Per-player MAE confidence increases with n_games -- trust players with 10+ games more

## Files
- `data/intelligence/h1_h2_projections.parquet` -- per-player projection table
- `data/intelligence/h2_projection_signals.json` -- top-25 predictable + volatile + league patterns
- `scripts/build_h1_to_h2_projection.py` -- this pipeline
"""
    ATLAS_MD.write_text(atlas, encoding="utf-8")
    print(f"Atlas written: {ATLAS_MD}")


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("INT-42 | H1 to H2 Projection Intelligence")
    print("=" * 55)

    print("\nStep 1 -- Loading H1/H2 stats from player_quarter_stats...")
    df = build_dataset()
    print(f"  Valid player-game rows: {len(df):,}")
    print(f"  Unique games: {df['game_id'].nunique():,}")
    print(f"  Unique players: {df['player_id'].nunique():,}")
    n_games = df['game_id'].nunique()

    print("\nStep 2 -- Applying H1toH2 multipliers...")
    df = apply_projections(df)

    # Sanity check: show multiplier distribution
    mult_desc = df["multiplier"].describe()
    print(f"  Multiplier stats: min={mult_desc['min']:.3f} mean={mult_desc['mean']:.3f} max={mult_desc['max']:.3f}")

    context_counts = df.groupby(["clutch_tag","closer_tag","is_b2b"]).size().reset_index(name="n")
    b2b_count = df["is_b2b"].sum()
    elevator_count = (df["clutch_tag"] == "ELEVATOR").sum()
    shrinker_count = (df["clutch_tag"] == "SHRINKER").sum()
    closer_count = (df["closer_tag"] == "CLOSER").sum()
    fs_count = (df["closer_tag"] == "FAST_STARTER").sum()
    print(f"  B2B rows: {b2b_count:,} ({b2b_count/len(df)*100:.1f}%)")
    print(f"  Elevator rows: {elevator_count:,} | Shrinker rows: {shrinker_count:,}")
    print(f"  Closer rows: {closer_count:,} | FastStarter rows: {fs_count:,}")

    print("\nStep 3 -- Aggregating per-player projection coefficients...")
    per_player = aggregate_per_player(df)
    print(f"  Players with >=2 games profiled: {len(per_player):,}")
    n_players = len(per_player)

    print("\nStep 4 -- Computing league-wide multiplier patterns...")
    patterns = league_patterns(df)
    for k, v in sorted(patterns.items()):
        print(f"  {k}: {v}")

    print("\nStep 5 -- Writing outputs...")

    # Parquet
    INTEL.mkdir(parents=True, exist_ok=True)
    per_player.to_parquet(OUT_PARQUET, index=False)
    print(f"  Parquet: {OUT_PARQUET}")

    # JSON signals
    signals = build_signals(per_player, patterns)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(signals, f, indent=2, default=str)
    print(f"  JSON: {OUT_JSON}")

    # Atlas
    write_atlas(per_player, patterns, n_games, n_players)

    # ── Final report ──────────────────────────────────────────────────────
    top3_pred = per_player.nsmallest(3, "MAE_projected")
    top3_vol = per_player.nlargest(3, "MAE_projected")

    print("\n" + "=" * 55)
    print("INT-42 H1 to H2 Projection -- Final Report")
    print("=" * 55)

    print(f"\nCoverage:")
    print(f"  Games with H1+H2 data: {n_games}")
    print(f"  Players with projections: {n_players}")

    print(f"\nTop 3 most-predictable (lowest composite MAE):")
    for _, r in top3_pred.iterrows():
        print(
            f"  {r['player_name']:<28} PTS MAE={r['MAE_proj_pts']:.3f} "
            f"(naive={r['MAE_naive_pts']:.3f}) games={r['n_games']}"
        )

    print(f"\nTop 3 most-volatile (caution):")
    for _, r in top3_vol.iterrows():
        print(
            f"  {r['player_name']:<28} PTS MAE={r['MAE_proj_pts']:.3f} games={r['n_games']}"
        )

    # League patterns summary
    lp = patterns
    b2b_pct = (lp.get("b2b_pts_h2_vs_h1_ratio", 1.0) - 1.0) * 100
    elev_pct = (lp.get("elevator_pts_h2_vs_h1_ratio", 1.0) - 1.0) * 100
    closer_pct = (lp.get("closer_pts_h2_vs_h1_ratio", 1.0) - 1.0) * 100
    fs_pct = (lp.get("fast_starter_pts_h2_vs_h1_ratio", 1.0) - 1.0) * 100
    league_pct = (lp.get("league_pts_h2_vs_h1_ratio", 1.0) - 1.0) * 100

    print(f"\nLeague-wide multiplier patterns (PTS H2 vs H1, median):")
    print(f"  League average:    {league_pct:+.1f}%")
    print(f"  B2B effect:        {b2b_pct:+.1f}%")
    print(f"  Clutch elevator:   {elev_pct:+.1f}%")
    print(f"  Q4 closer:         {closer_pct:+.1f}%")
    print(f"  Fast starter:      {fs_pct:+.1f}%")

    print(f"\nFiles:")
    print(f"  scripts/build_h1_to_h2_projection.py")
    print(f"  vault/Intelligence/H1_to_H2_Projection_Atlas.md")
    print(f"  data/intelligence/h1_h2_projections.parquet")
    print(f"  data/intelligence/h2_projection_signals.json")

    print(f"\nHow to use at halftime:")
    print(f"  1. Get H1 box score (pts/reb/ast) from live feed")
    print(f"  2. Apply per-player multiplier from h1_h2_projections.parquet")
    print(f"  3. Compare to sportsbook H2 line -- bet if discrepancy >5%")
    print(f"  4. Compound with INT-16 x INT-39 Kelly sizing stack")

    print(f"\nHonest caveats:")
    print(f"  - H2 derived as full_game - H1 (not directly measured)")
    print(f"  - Clutch tags cover only 42 players; closer tags only 9")
    print(f"  - Multipliers are heuristic (could be ML-tuned with more CV games)")
    print(f"  - Per-player MAE most reliable for players with 10+ games")

    print("\nDone.")


if __name__ == "__main__":
    main()
