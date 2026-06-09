"""
INT-19 Per-Game CV Signature Similarity
=========================================
For each (player_id, game_id) in cv_features, find the 5 most-similar historical
(player_id, game_id) records based on cosine similarity over 14 reliable CV features.

Temporal leakage protection: only prior games (game_date < target date) are candidates.

Outputs:
  data/intelligence/game_similarity_index.parquet   - one row per (player, game)
  data/intelligence/game_neighbors.json             - top-5 per record, fast lookup
  vault/Intelligence/Game_Similarity.md             - usage guide + examples
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path("C:/Users/neelj/nba-ai-system")
CV_PATH     = ROOT / "data/player_cv_per_game.parquet"
QS_PATH     = ROOT / "data/player_quarter_stats.parquet"
GL_DIR      = ROOT / "data/nba"
SEASON_DIR  = ROOT / "data/nba"
OUT_DIR     = ROOT / "data/intelligence"
VAULT_INT   = ROOT / "vault/Intelligence"

OUT_DIR.mkdir(parents=True, exist_ok=True)
VAULT_INT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# 14 reliable CV features for per-game similarity
# Selected: <60% null rate; covers spatial, velocity, fatigue, and proximity dims
# ---------------------------------------------------------------------------
CV_FEATURES: List[str] = [
    "cvb_avg_defender_dist",    # defender proximity (2.3% null -> median impute)
    "cvb_avg_spacing",          # team spacing proxy
    "cvb_off_ball_dist",        # off-ball movement distance
    "cvb_avg_velocity",         # average movement speed
    "cvb_paint_pressure_own",   # paint occupancy own team (56.8% null -> 0 impute)
    "cvb_paint_pressure_opp",   # paint occupancy opponent (56.8% null -> 0 impute)
    "cvb_fatigue_score",        # cumulative fatigue proxy
    "cvb_paint_time_pct",       # fraction of frames in paint (1.2% null -> median)
    "cvb_near_basket_pct",      # fraction near basket
    "cvb_avg_dist_to_basket",   # average court position
    "cvb_pose_coverage_pct",    # pose detection coverage
    "cvb_jump_frequency",       # jump activity rate
    "minutes_proxy",            # estimated court time
    "n_frames",                 # tracking depth (quality proxy)
]

# Note: spec mentions 19 features, but the per-game parquet only has 14 features
# with <60% null rate. Higher-null features (velocity_q4_dropoff, contest_arm_mean,
# close_to_basket_pct, off_ball_dist_std, passes/dribbles/contested per100) are
# 93-99% null and excluded to prevent imputation from dominating similarity.

TOP_K = 5
MIN_FRAMES = 100  # skip very short-tracked entries (noisy CV signature)


# ---------------------------------------------------------------------------
# Step 0 — Build stat lookup from gamelogs
# ---------------------------------------------------------------------------

def _parse_gl_date(d: str) -> Optional[str]:
    """'Apr 13, 2025' -> '2025-04-13'"""
    try:
        return datetime.strptime(d.strip(), "%b %d, %Y").strftime("%Y-%m-%d")
    except Exception:
        return None


def _parse_matchup_team(m: str) -> Optional[str]:
    """'SAS vs. TOR' or 'SAS @ PHX' -> player's team abbrev"""
    if " vs. " in m:
        return m.split(" vs. ")[0].strip()
    if " @ " in m:
        return m.split(" @ ")[0].strip()
    return None


def build_date_team_lookup() -> Dict[Tuple[str, str], str]:
    """Return {(game_date, team_abbrev): game_id} from all season_games JSON files."""
    mapping: Dict[Tuple[str, str], str] = {}
    for sf in sorted(SEASON_DIR.glob("season_games_*.json")):
        with open(sf, encoding="utf-8") as f:
            data = json.load(f)
        for row in data.get("rows", []):
            gid = row.get("game_id")
            gdate = row.get("game_date")
            if not gid or not gdate:
                continue
            if "home_team" in row:
                mapping[(gdate, row["home_team"])] = gid
                mapping[(gdate, row["away_team"])] = gid
    return mapping


def build_game_id_to_date() -> Dict[str, str]:
    """Return {game_id: game_date} from all season_games JSON files."""
    mapping: Dict[str, str] = {}
    for sf in sorted(SEASON_DIR.glob("season_games_*.json")):
        with open(sf, encoding="utf-8") as f:
            data = json.load(f)
        for row in data.get("rows", []):
            gid = row.get("game_id")
            gdate = row.get("game_date")
            if gid and gdate:
                mapping[gid] = gdate
    return mapping


def load_stat_lookup(date_team: Dict[Tuple[str, str], str]) -> pd.DataFrame:
    """
    Load all gamelog JSON files and resolve each row to a game_id.
    Returns DataFrame: [nba_player_id, game_id, target_pts, target_reb, target_ast,
                        target_fg3m, target_stl, target_blk, target_tov]
    """
    rows = []
    gl_files = list(GL_DIR.glob("gamelog_*_*.json"))
    print(f"  Loading {len(gl_files)} gamelog files ...")

    for fp in gl_files:
        # Parse nba_player_id from filename: gamelog_{player_id}_{season}.json
        parts = fp.stem.split("_")  # ['gamelog', pid, season]
        try:
            nba_pid = int(parts[1])
        except (IndexError, ValueError):
            continue

        try:
            with open(fp, encoding="utf-8") as f:
                gl = json.load(f)
        except Exception:
            continue

        for row in gl:
            d = _parse_gl_date(str(row.get("GAME_DATE", "")))
            team = _parse_matchup_team(str(row.get("MATCHUP", "")))
            if not d or not team:
                continue
            gid = date_team.get((d, team))
            if not gid:
                continue
            rows.append(
                {
                    "nba_player_id": nba_pid,
                    "game_id": gid,
                    "target_pts": row.get("PTS"),
                    "target_reb": row.get("REB"),
                    "target_ast": row.get("AST"),
                    "target_fg3m": row.get("FG3M"),
                    "target_stl": row.get("STL"),
                    "target_blk": row.get("BLK"),
                    "target_tov": row.get("TOV"),
                }
            )

    stats = pd.DataFrame(rows)
    # Deduplicate: if a player appears twice for same game (multi-season overlap), keep first
    stats = stats.drop_duplicates(subset=["nba_player_id", "game_id"], keep="first")
    print(f"  Stat rows: {len(stats)} | players: {stats['nba_player_id'].nunique()} | games: {stats['game_id'].nunique()}")
    return stats


# ---------------------------------------------------------------------------
# Step 1 — Build feature matrix
# ---------------------------------------------------------------------------

def build_feature_matrix(cv: pd.DataFrame) -> pd.DataFrame:
    """
    Filter and clean cv per-game data.
    Returns DataFrame with CV_FEATURES columns, indexed by integer position,
    plus metadata columns.
    """
    df = cv.copy()

    # Require sufficient tracking depth
    df = df[df["n_frames"] >= MIN_FRAMES].copy()
    print(f"  After n_frames >= {MIN_FRAMES} filter: {len(df)} records")

    # Impute missing values
    for col in CV_FEATURES:
        if col not in df.columns:
            df[col] = 0.0
            continue
        if col in ("cvb_paint_pressure_own", "cvb_paint_pressure_opp"):
            df[col] = df[col].fillna(0.0)
        else:
            median_val = df[col].median()
            df[col] = df[col].fillna(median_val if not np.isnan(median_val) else 0.0)

    # Convert to float
    for col in CV_FEATURES:
        df[col] = df[col].astype(float)

    return df.reset_index(drop=True)


def zscore_normalize(df: pd.DataFrame) -> np.ndarray:
    """Z-score each CV_FEATURE column. Zero-variance columns set to 0."""
    X = df[CV_FEATURES].values.astype(np.float64)
    means = X.mean(axis=0)
    stds = X.std(axis=0)
    stds[stds < 1e-9] = 1.0  # avoid division by zero
    return (X - means) / stds


# ---------------------------------------------------------------------------
# Step 2 — Pairwise cosine similarity
# ---------------------------------------------------------------------------

def cosine_similarity_matrix(X_norm: np.ndarray) -> np.ndarray:
    """Return N×N cosine similarity matrix (1=identical, -1=opposite)."""
    norms = np.linalg.norm(X_norm, axis=1, keepdims=True)
    norms[norms < 1e-9] = 1e-9
    Xn = X_norm / norms
    return Xn @ Xn.T  # N×N


# ---------------------------------------------------------------------------
# Step 3 — Per-record top-5 neighbors
# ---------------------------------------------------------------------------

def find_neighbors(
    df: pd.DataFrame,
    cos_sim: np.ndarray,
    stats_df: pd.DataFrame,
) -> List[dict]:
    """
    For each (player_id, game_id) record i:
      - Filter candidates to game_date < df.iloc[i]['game_date'] (temporal safety)
      - Top-5 by cosine similarity: overall (cross-player)
      - Top-5 by cosine similarity: same player only

    Returns list of dicts, one per record.
    """
    dates = pd.to_datetime(df["game_date"])
    nba_ids = df["nba_player_id"].values
    game_ids = df["game_id"].values
    player_names = df["player_name"].values
    n = len(df)

    # Build stat lookup: (nba_player_id, game_id) -> (pts, reb, ast)
    stat_map: Dict[Tuple, dict] = {}
    for _, row in stats_df.iterrows():
        key = (int(row["nba_player_id"]), str(row["game_id"]))
        stat_map[key] = {
            "pts": row["target_pts"],
            "reb": row["target_reb"],
            "ast": row["target_ast"],
        }

    results = []
    for i in range(n):
        target_date = dates.iloc[i]
        target_nba_id = nba_ids[i]

        # Temporal mask: only strictly earlier games are valid neighbors
        earlier_mask = dates < target_date  # boolean array, shape N

        # Cosine similarities for row i, masking self and future
        sim_row = cos_sim[i].copy()
        sim_row[i] = -2.0  # mask self

        # ── Top-5 overall (cross-player, any earlier game) ──────────────────
        overall_sims = sim_row.copy()
        overall_sims[~earlier_mask] = -2.0
        overall_order = np.argsort(-overall_sims)  # descending

        top5_overall = []
        for j in overall_order:
            if len(top5_overall) >= TOP_K:
                break
            if overall_sims[j] <= -1.5:
                break
            nb_nba_id = nba_ids[j]
            nb_gid = str(game_ids[j])
            stat_key = (int(nb_nba_id), nb_gid) if not pd.isna(nb_nba_id) else None
            stat_out = stat_map.get(stat_key, {}) if stat_key else {}
            top5_overall.append(
                {
                    "rank": len(top5_overall) + 1,
                    "player_name": str(player_names[j]),
                    "nba_player_id": int(nb_nba_id) if not pd.isna(nb_nba_id) else None,
                    "game_id": nb_gid,
                    "game_date": str(dates.iloc[j].date()),
                    "cosine_similarity": round(float(overall_sims[j]), 4),
                    "outcome_pts": stat_out.get("pts"),
                    "outcome_reb": stat_out.get("reb"),
                    "outcome_ast": stat_out.get("ast"),
                }
            )

        # ── Top-5 same-player ────────────────────────────────────────────────
        if pd.isna(target_nba_id):
            same_player_mask = np.zeros(n, dtype=bool)
        else:
            same_player_mask = np.array(
                [(not pd.isna(x) and int(x) == int(target_nba_id)) for x in nba_ids],
                dtype=bool,
            )

        sp_sims = sim_row.copy()
        sp_sims[~earlier_mask] = -2.0
        sp_sims[~same_player_mask] = -2.0
        sp_order = np.argsort(-sp_sims)

        top5_same = []
        for j in sp_order:
            if len(top5_same) >= TOP_K:
                break
            if sp_sims[j] <= -1.5:
                break
            nb_gid = str(game_ids[j])
            stat_key = (int(nba_ids[j]), nb_gid) if not pd.isna(nba_ids[j]) else None
            stat_out = stat_map.get(stat_key, {}) if stat_key else {}
            top5_same.append(
                {
                    "rank": len(top5_same) + 1,
                    "player_name": str(player_names[j]),
                    "nba_player_id": int(nba_ids[j]) if not pd.isna(nba_ids[j]) else None,
                    "game_id": nb_gid,
                    "game_date": str(dates.iloc[j].date()),
                    "cosine_similarity": round(float(sp_sims[j]), 4),
                    "outcome_pts": stat_out.get("pts"),
                    "outcome_reb": stat_out.get("reb"),
                    "outcome_ast": stat_out.get("ast"),
                }
            )

        # ── Compute neighbor mean outcomes (overall top-5 only) ──────────────
        pts_vals = [nb["outcome_pts"] for nb in top5_overall if nb["outcome_pts"] is not None]
        reb_vals = [nb["outcome_reb"] for nb in top5_overall if nb["outcome_reb"] is not None]
        ast_vals = [nb["outcome_ast"] for nb in top5_overall if nb["outcome_ast"] is not None]
        neighbor_mean_pts = float(np.mean(pts_vals)) if pts_vals else None
        neighbor_mean_reb = float(np.mean(reb_vals)) if reb_vals else None
        neighbor_mean_ast = float(np.mean(ast_vals)) if ast_vals else None

        max_sim = float(top5_overall[0]["cosine_similarity"]) if top5_overall else None

        results.append(
            {
                "player_name": str(player_names[i]),
                "nba_player_id": int(target_nba_id) if not pd.isna(target_nba_id) else None,
                "game_id": str(game_ids[i]),
                "game_date": str(dates.iloc[i].date()),
                "n_overall_neighbors": len(top5_overall),
                "n_same_player_neighbors": len(top5_same),
                "top5_neighbors_overall": json.dumps(top5_overall),
                "top5_neighbors_same_player": json.dumps(top5_same),
                "neighbor_mean_pts": neighbor_mean_pts,
                "neighbor_mean_reb": neighbor_mean_reb,
                "neighbor_mean_ast": neighbor_mean_ast,
                "max_similarity_score": max_sim,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Step 4 — Output files
# ---------------------------------------------------------------------------

def save_outputs(results: List[dict]) -> None:
    """Save parquet index and JSON neighbors file."""
    df_out = pd.DataFrame(results)

    # Parquet
    parquet_path = OUT_DIR / "game_similarity_index.parquet"
    df_out.to_parquet(parquet_path, index=False)
    print(f"  Saved game_similarity_index.parquet ({len(df_out)} rows)")

    # JSON: {player_id_game_id: full record with parsed lists}
    neighbors_dict: dict = {}
    for row in results:
        key = f"{row['nba_player_id']}_{row['game_id']}"
        entry = {k: v for k, v in row.items() if k not in ("top5_neighbors_overall", "top5_neighbors_same_player")}
        entry["top5_neighbors_overall"] = json.loads(row["top5_neighbors_overall"])
        entry["top5_neighbors_same_player"] = json.loads(row["top5_neighbors_same_player"])
        neighbors_dict[key] = entry

    json_path = OUT_DIR / "game_neighbors.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(neighbors_dict, f, indent=2, ensure_ascii=False)
    print(f"  Saved game_neighbors.json ({len(neighbors_dict)} keys)")


# ---------------------------------------------------------------------------
# Step 5 — Vault note
# ---------------------------------------------------------------------------

def _pick_examples(results: List[dict], stats_df: pd.DataFrame) -> List[dict]:
    """Pick 5 interesting examples for the vault note."""
    df = pd.DataFrame(results)

    # Examples with high max_similarity and stat outcomes available
    good = df[
        df["max_similarity_score"].notna()
        & (df["neighbor_mean_pts"].notna())
        & (df["n_overall_neighbors"] >= 3)
    ].copy()

    good = good.sort_values("max_similarity_score", ascending=False)
    examples = []
    seen_names = set()
    for _, row in good.iterrows():
        name = row["player_name"]
        if name in seen_names or "?" in str(name) or "#" in str(name):
            continue
        seen_names.add(name)
        examples.append(row)
        if len(examples) >= 5:
            break

    return examples


def write_vault_note(results: List[dict], stats_df: pd.DataFrame, n_records: int, n_no_close: int, n_very_close: int) -> None:
    """Write vault/Intelligence/Game_Similarity.md"""
    examples = _pick_examples(results, stats_df)
    n_pairs = n_records * (n_records - 1) // 2

    ex_lines = []
    for k, ex in enumerate(examples, 1):
        top5 = json.loads(ex["top5_neighbors_overall"])
        sp5 = json.loads(ex["top5_neighbors_same_player"])
        ex_lines.append(f"### Example {k}: {ex['player_name']} — game {ex['game_id']} ({ex['game_date']})")
        if top5:
            nb = top5[0]
            ex_lines.append(
                f"- **Most similar prior game (cross-player):** {nb['player_name']} — game {nb['game_id']} ({nb['game_date']}), "
                f"cos_sim={nb['cosine_similarity']:.3f}"
            )
            outcome_parts = []
            if nb["outcome_pts"] is not None:
                outcome_parts.append(f"{nb['outcome_pts']:.0f} PTS")
            if nb["outcome_reb"] is not None:
                outcome_parts.append(f"{nb['outcome_reb']:.0f} REB")
            if nb["outcome_ast"] is not None:
                outcome_parts.append(f"{nb['outcome_ast']:.0f} AST")
            if outcome_parts:
                ex_lines.append(f"  - Outcome in that game: {', '.join(outcome_parts)}")
        if sp5:
            nb = sp5[0]
            ex_lines.append(
                f"- **Most similar same-player prior game:** game {nb['game_id']} ({nb['game_date']}), "
                f"cos_sim={nb['cosine_similarity']:.3f}"
            )
            outcome_parts = []
            if nb["outcome_pts"] is not None:
                outcome_parts.append(f"{nb['outcome_pts']:.0f} PTS")
            if nb["outcome_reb"] is not None:
                outcome_parts.append(f"{nb['outcome_reb']:.0f} REB")
            if nb["outcome_ast"] is not None:
                outcome_parts.append(f"{nb['outcome_ast']:.0f} AST")
            if outcome_parts:
                ex_lines.append(f"  - Outcome in that game: {', '.join(outcome_parts)}")
        mean_parts = []
        if ex["neighbor_mean_pts"] is not None:
            mean_parts.append(f"{ex['neighbor_mean_pts']:.1f} PTS")
        if ex["neighbor_mean_reb"] is not None:
            mean_parts.append(f"{ex['neighbor_mean_reb']:.1f} REB")
        if ex["neighbor_mean_ast"] is not None:
            mean_parts.append(f"{ex['neighbor_mean_ast']:.1f} AST")
        if mean_parts:
            ex_lines.append(f"- **Neighbor mean (top-5 overall):** {', '.join(mean_parts)}")
        ex_lines.append("")

    content = f"""# Per-Game CV Signature Similarity

## What this is
For any (player, game), find the 5 most-similar historical games using cosine similarity
over 14 reliable CV behavioral features. Use cases:
- **Analytics**: "this game is like X vs Y" narrative
- **Prediction baseline**: neighbor outcomes inform expected stats
- **Anomaly check**: no close matches → flag prediction uncertainty

## Methodology
- 14 reliable CV features per (player, game) from player_cv_per_game.parquet
- Features: defender_dist, spacing, off_ball_dist, velocity, paint_pressure (own/opp),
  fatigue_score, paint_time_pct, near_basket_pct, dist_to_basket, pose_coverage_pct,
  jump_frequency, minutes_proxy, n_frames
- Cosine similarity (magnitude-independent playstyle match)
- **Temporal leakage protection**: only game_date < target date are eligible neighbors
- Top 5 overall (cross-player) + top 5 same-player

## Query examples (Python)
```python
import json
neighbors = json.load(open('data/intelligence/game_neighbors.json'))
key = '201939_0022500006'  # nba_player_id_game_id
print(neighbors[key]['top5_neighbors_overall'])
```

```python
import pandas as pd
idx = pd.read_parquet('data/intelligence/game_similarity_index.parquet')
row = idx[(idx['nba_player_id'] == 201939) & (idx['game_id'] == '0022500006')].iloc[0]
print('Neighbor mean PTS:', row['neighbor_mean_pts'])
print('Max similarity:', row['max_similarity_score'])
```

## Examples

{chr(10).join(ex_lines)}
## How to use
- **Game analytics**: surface comps for AI chat (\"similar to X in 2025-26\")
- **Prediction overlay**: neighbor stat means as alternative baseline for predictions
- **Confidence proxy**: max_similarity < 0.8 means no close historical match → flag low confidence

## Coverage stats
- (player, game) records indexed: {n_records}
- Pairwise similarities computed: {n_pairs:,}
- Records with no close match (max_similarity < 0.8): {n_no_close}
- Records with very close match (max_similarity > 0.95): {n_very_close}

## Honest caveats
- 11.8% CV coverage limits historical comp pool to ~{n_records} records across ~78 games
- Same 9 pipeline bugs from CV_Pipeline_Bug_Roadmap.md affect signature quality
- Cosine similarity treats unit-inconsistent features equally (BUG 9 cross-season scale)
- "Similar CV signature" does not equal "similar outcome" — neighbor outcomes are noisy
- paint_pressure_own/opp are 56.8% null (imputed to 0) — flattens dimension for ~half of records
- n_frames included as quality proxy; very short clips may produce noisy signatures

## File locations
- `data/intelligence/game_similarity_index.parquet` — one row per (player, game)
- `data/intelligence/game_neighbors.json` — top-5 neighbors per record, JSON lookup
"""

    path = VAULT_INT / "Game_Similarity.md"
    path.write_text(content, encoding="utf-8")
    print(f"  Wrote vault/Intelligence/Game_Similarity.md")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("INT-19 Per-Game CV Signature Similarity")
    print("=" * 60)

    # ── [1] Build lookups ───────────────────────────────────────────────────
    print("\n[1/5] Building game date and stat lookups ...")
    game_id_to_date = build_game_id_to_date()
    date_team_lookup = build_date_team_lookup()
    print(f"  game_id_to_date: {len(game_id_to_date)} entries")
    print(f"  date_team_lookup: {len(date_team_lookup)} entries")

    stats_df = load_stat_lookup(date_team_lookup)

    # ── [2] Load and prep CV data ───────────────────────────────────────────
    print("\n[2/5] Loading CV per-game data ...")
    cv_raw = pd.read_parquet(CV_PATH)
    cv_raw["game_date"] = cv_raw["game_id"].map(game_id_to_date)

    # Require game_date
    cv_raw = cv_raw[cv_raw["game_date"].notna()].copy()
    print(f"  CV rows with game_date: {len(cv_raw)}")

    # Build feature matrix (filter n_frames, impute nulls)
    df = build_feature_matrix(cv_raw)
    print(f"  Feature matrix: {df.shape[0]} records × {len(CV_FEATURES)} features")

    # ── [3] Normalize + compute cosine similarity ───────────────────────────
    print("\n[3/5] Z-score normalizing and computing pairwise cosine similarity ...")
    X_norm = zscore_normalize(df)
    cos_sim = cosine_similarity_matrix(X_norm)
    n = len(df)
    n_pairs = n * (n - 1) // 2
    print(f"  {n} records -> {n_pairs:,} pairwise similarities")

    # ── [4] Per-record top-5 neighbors ─────────────────────────────────────
    print("\n[4/5] Computing top-5 neighbors per record (temporal filter) ...")
    results = find_neighbors(df, cos_sim, stats_df)

    # ── [5] Save outputs ────────────────────────────────────────────────────
    print("\n[5/5] Saving outputs ...")
    save_outputs(results)

    # ── Summary stats ───────────────────────────────────────────────────────
    df_out = pd.DataFrame(results)
    max_sims = df_out["max_similarity_score"].dropna()
    n_no_close = int((max_sims < 0.8).sum())
    n_very_close = int((max_sims > 0.95).sum())
    avg_max = float(max_sims.mean()) if len(max_sims) > 0 else 0.0

    write_vault_note(results, stats_df, n, n_no_close, n_very_close)

    # ── Final report ────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("INT-19 Per-Game CV Similarity — Final Report")
    print("=" * 60)

    print(f"\nCoverage:")
    print(f"  (player, game) records indexed:  {n}")
    print(f"  Pairwise similarities computed:  {n_pairs:,}")
    print(f"  Average max-similarity:          {avg_max:.4f}")
    print(f"  No close match (max_sim < 0.80): {n_no_close}")
    print(f"  Very close match (max_sim > 0.95): {n_very_close}")

    with_nb = int(df_out["n_overall_neighbors"].gt(0).sum())
    with_sp_nb = int(df_out["n_same_player_neighbors"].gt(0).sum())
    with_stat = int(df_out["neighbor_mean_pts"].notna().sum())
    print(f"\nNeighbor coverage:")
    print(f"  Records with >= 1 overall neighbor:      {with_nb}")
    print(f"  Records with >= 1 same-player neighbor:  {with_sp_nb}")
    print(f"  Records with stat outcomes available:    {with_stat}")

    # Show a few interesting example comps
    print("\nSample historical comp findings:")
    examples_df = df_out[
        df_out["max_similarity_score"].notna()
        & df_out["neighbor_mean_pts"].notna()
        & ~df_out["player_name"].str.contains("[#?]", na=True)
    ].nlargest(5, "max_similarity_score")

    for _, ex_row in examples_df.iterrows():
        top5 = json.loads(ex_row["top5_neighbors_overall"])
        if top5:
            nb = top5[0]
            outcome_str = ""
            if nb["outcome_pts"] is not None:
                outcome_str = f" -> {nb['outcome_pts']:.0f}pts/{nb.get('outcome_reb', 'N/A')}reb/{nb.get('outcome_ast', 'N/A')}ast"
            print(
                f"  {ex_row['player_name']} ({ex_row['game_id']}) -> "
                f"most similar: {nb['player_name']} ({nb['game_id']}, sim={nb['cosine_similarity']:.3f}){outcome_str}"
            )

    print(f"\nFiles:")
    print(f"  scripts/build_game_similarity.py")
    print(f"  vault/Intelligence/Game_Similarity.md")
    print(f"  data/intelligence/game_similarity_index.parquet")
    print(f"  data/intelligence/game_neighbors.json")

    print(f"\nHow to use:")
    print(f"  AI chat: surface comp games for narrative ('this game is like X vs Y')")
    print(f"  Prediction baseline: use neighbor_mean_pts/reb/ast as alternative baseline")
    print(f"  Anomaly flag: max_similarity < 0.8 = no historical match = uncertainty signal")

    print(f"\nHonest caveats:")
    print(f"  Limited comp pool at current CV coverage (~{n} records across ~78 games)")
    print(f"  Cross-season scale issues affect comparisons")
    print(f"  Similarity != outcome predictability — neighbor outcomes are noisy")
    print(f"  paint_pressure 56.8% null imputed to 0 — flattens that dimension")

    print("\nDone.")


if __name__ == "__main__":
    main()
