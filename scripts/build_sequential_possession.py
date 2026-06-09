"""
INT-40: Sequential Possession Intelligence
-------------------------------------------
For each player across all CV-tracked games, detect rhythm patterns by analysing
whether a player's CV behaviour on possession N predicts possession N+1.

Outputs:
  - data/intelligence/sequential_patterns.parquet
  - data/intelligence/sequential_signatures.json
  - vault/Intelligence/Sequential_Possession_Atlas.md

Usage:
    conda activate basketball_ai
    python scripts/build_sequential_possession.py
    python scripts/build_sequential_possession.py --min-pairs 10 --max-gap 4
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path("C:/Users/neelj/nba-ai-system")
TRACKING_DIR = ROOT / "data" / "tracking"
CV_PER_GAME_PATH = ROOT / "data" / "player_cv_per_game.parquet"
INTEL_DIR = ROOT / "data" / "intelligence"
VAULT_INTEL_DIR = ROOT / "vault" / "Intelligence"

OUTPUT_PARQUET = INTEL_DIR / "sequential_patterns.parquet"
OUTPUT_JSON = INTEL_DIR / "sequential_signatures.json"
OUTPUT_ATLAS = VAULT_INTEL_DIR / "Sequential_Possession_Atlas.md"

INTEL_DIR.mkdir(parents=True, exist_ok=True)
VAULT_INTEL_DIR.mkdir(parents=True, exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────────────────
MIN_PAIRS_FLOOR = 10          # minimum sequential pairs per player to include
MAX_GAP_POSSESSIONS = 4       # max possession_id gap between consecutive pair (own-team IDs alternate ~2 apart)
MIN_FRAMES_PER_POSS = 10      # minimum frames for a possession-player group to be included
PHANTOM_PATTERN = "#?"        # substring marking unresolved player name

# Features to track across possessions
SEQ_FEATURES = ["velocity", "dribble_count", "paint_touches", "ball_poss_rate"]
SEQ_FEAT_INTERP = {
    "velocity":      "movement speed",
    "dribble_count": "dribbling volume",
    "paint_touches": "paint activity",
    "ball_poss_rate": "ball possession rate",
}

# Classification thresholds
# NOTE: velocity/dribble_count/paint_touches are heavily zero-inflated (most frames are static),
# so absolute rhythm thresholds are unreliable.  We classify on ball_poss_rate (least zero-inflated)
# using a relative approach: upper/lower 30th percentile of the player population.
# These are computed at runtime; the constants below are fallback absolute values.
MOMENTUM_THRESHOLD = 0.60  # fallback absolute threshold if relative cannot be computed
REACTIVE_THRESHOLD = 0.40  # fallback absolute threshold
# Primary classification feature — ball possession escalation is the most meaningful rhythm signal
CLASSIFICATION_FEATURE = "ball_poss_rate"
# Z-score half-width for builder/cooler boundary (|z| > 0.5 → classified)
CLASSIFICATION_Z_THRESHOLD = 0.5

# Made/scored result labels (for hot-hand analysis)
MADE_RESULTS = {"made_fg", "scored"}
MISSED_RESULTS = {"missed_fg", "missed_shot"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_phantom(name: Optional[str]) -> bool:
    """Return True if the player name is unresolved (phantom slot)."""
    if name is None or (isinstance(name, float) and np.isnan(name)):
        return True
    return PHANTOM_PATTERN in str(name)


def load_jersey_name_map(game_dir: Path) -> Tuple[Dict[str, str], str]:
    """
    Load jersey_name_map.json and return:
      - name_to_team: {player_name -> team_abbrev}
      - raw_jnm: the full dict (for fallback slot resolution)

    Supports both new format (by_team + flat) and old flat format.
    """
    jnm_path = game_dir / "jersey_name_map.json"
    if not jnm_path.exists():
        return {}, {}

    try:
        with open(jnm_path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception:
        return {}, {}

    name_to_team: Dict[str, str] = {}

    if isinstance(data, dict) and "by_team" in data:
        # New format: {"by_team": {"DEN": {"15": "Nikola Jokic"}, ...}, "flat": {...}}
        for team_abbrev, players in data["by_team"].items():
            for jersey_num, player_name in players.items():
                if player_name and not is_phantom(player_name):
                    name_to_team[player_name] = team_abbrev
    elif isinstance(data, dict):
        # Old flat format: {"0": "Max Christie", ...} - no team info available
        pass

    return name_to_team, data


def load_possessions(game_dir: Path) -> pd.DataFrame:
    """Load possessions.csv; return empty DF if not found."""
    path = game_dir / "possessions.csv"
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, low_memory=False)
        return df
    except Exception:
        return pd.DataFrame()


def load_tracking(game_dir: Path) -> pd.DataFrame:
    """
    Load tracking_data.csv with only needed columns.
    Returns empty DF if not found or too small.
    """
    path = game_dir / "tracking_data.csv"
    if not path.exists():
        return pd.DataFrame()
    if path.stat().st_size < 50_000:
        return pd.DataFrame()

    needed_cols = {
        "frame", "player_id", "player_name", "team_abbrev",
        "possession_id", "ball_possession",
        "velocity", "dribble_count", "paint_touches",
    }
    try:
        df = pd.read_csv(
            path, low_memory=False,
            usecols=lambda c: c in needed_cols,
        )
        if len(df) < 200:
            return pd.DataFrame()
        return df
    except Exception as e:
        print(f"  [WARN] Could not load {game_dir.name}: {e}")
        return pd.DataFrame()


def build_poss_map(poss_df: pd.DataFrame) -> Dict[int, Dict]:
    """
    Build {possession_id -> {"team": str, "result": str}} from possessions.csv.
    De-duplicates by taking the first record per possession_id.
    """
    if poss_df.empty:
        return {}
    dedup = poss_df.drop_duplicates("possession_id")
    cols = ["team", "result"]
    cols = [c for c in cols if c in dedup.columns]
    pmap = {}
    for _, row in dedup.iterrows():
        pid = int(row["possession_id"]) if not pd.isna(row["possession_id"]) else None
        if pid is None:
            continue
        pmap[pid] = {c: row.get(c) for c in cols}
    return pmap


# ── Step 1 + 2: Per-game per-player per-possession aggregation ────────────────

def process_game(
    game_id: str,
    name_to_team: Dict[str, str],
    poss_map: Dict[int, Dict],
    track_df: pd.DataFrame,
) -> List[Dict]:
    """
    For one game, aggregate CV stats per (player, possession) and return
    a list of dicts ready for sequential pair analysis.

    Each dict: game_id, player_name, player_team, possession_id, poss_team,
               poss_result, velocity, dribble_count, paint_touches, ball_poss_rate,
               n_frames
    """
    if track_df.empty or not poss_map:
        return []

    # Filter to resolved (non-phantom) player names
    has_name = track_df["player_name"].notna() & ~track_df["player_name"].apply(is_phantom)
    valid = track_df[has_name].copy()

    if len(valid) == 0:
        return []

    # Resolve player_team from jersey_name_map
    valid["player_team"] = valid["player_name"].map(name_to_team)

    # Aggregate per (possession_id, player_name, player_team)
    agg_dict = {
        "velocity": "mean",
        "dribble_count": "mean",
        "paint_touches": "mean",
        "ball_possession": "mean",
        "frame": "count",  # n_frames proxy
    }
    # only include columns that exist
    agg_dict = {k: v for k, v in agg_dict.items() if k in valid.columns}

    group_cols = ["possession_id", "player_name", "player_team"]
    try:
        grp = valid.groupby(group_cols).agg(agg_dict).reset_index()
    except Exception:
        return []

    grp.rename(columns={"ball_possession": "ball_poss_rate", "frame": "n_frames"}, inplace=True)

    # Ensure feature columns exist
    for feat in SEQ_FEATURES:
        if feat not in grp.columns:
            grp[feat] = np.nan

    # Add possession-level context from poss_map
    grp["poss_team"] = grp["possession_id"].apply(
        lambda pid: poss_map.get(int(pid), {}).get("team") if not pd.isna(pid) else None
    )
    grp["poss_result"] = grp["possession_id"].apply(
        lambda pid: poss_map.get(int(pid), {}).get("result") if not pd.isna(pid) else None
    )

    # Filter: only rows where player_team == poss_team (player on offensive team)
    grp = grp[
        grp["player_team"].notna() &
        grp["poss_team"].notna() &
        (grp["player_team"] == grp["poss_team"])
    ]

    # Filter: minimum frames per group
    if "n_frames" in grp.columns:
        grp = grp[grp["n_frames"] >= MIN_FRAMES_PER_POSS]

    records = []
    for _, row in grp.iterrows():
        records.append({
            "game_id": game_id,
            "player_name": row["player_name"],
            "player_team": row["player_team"],
            "possession_id": int(row["possession_id"]),
            "poss_team": row.get("poss_team"),
            "poss_result": row.get("poss_result"),
            "velocity": float(row.get("velocity", np.nan)),
            "dribble_count": float(row.get("dribble_count", np.nan)),
            "paint_touches": float(row.get("paint_touches", np.nan)),
            "ball_poss_rate": float(row.get("ball_poss_rate", np.nan)),
            "n_frames": int(row.get("n_frames", 0)),
        })

    return records


# ── Step 3: Sequential pair extraction ────────────────────────────────────────

def extract_sequential_pairs(game_records: List[Dict]) -> List[Dict]:
    """
    From per-(game, player, possession) records, extract consecutive own-team
    possession pairs for each player within each game.

    Returns list of pair dicts with delta features.
    """
    if not game_records:
        return []

    # Group by (game_id, player_name)
    player_games: Dict[Tuple, List[Dict]] = defaultdict(list)
    for rec in game_records:
        key = (rec["game_id"], rec["player_name"])
        player_games[key].append(rec)

    pairs = []
    for (game_id, player_name), recs in player_games.items():
        # Sort by possession_id within game
        recs_sorted = sorted(recs, key=lambda r: r["possession_id"])

        for i in range(len(recs_sorted) - 1):
            r1, r2 = recs_sorted[i], recs_sorted[i + 1]

            gap = r2["possession_id"] - r1["possession_id"]
            if gap < 1 or gap > MAX_GAP_POSSESSIONS:
                continue

            pair = {
                "game_id": game_id,
                "player_name": player_name,
                "player_team": r1["player_team"],
                "poss_n": r1["possession_id"],
                "poss_np1": r2["possession_id"],
                "result_n": r1.get("poss_result"),
                "result_np1": r2.get("poss_result"),
            }

            for feat in SEQ_FEATURES:
                v1 = r1.get(feat, np.nan)
                v2 = r2.get(feat, np.nan)
                pair[f"{feat}_n"] = v1
                pair[f"{feat}_np1"] = v2
                if not (np.isnan(v1) or np.isnan(v2)):
                    pair[f"d_{feat}"] = v2 - v1
                else:
                    pair[f"d_{feat}"] = np.nan

            pairs.append(pair)

    return pairs


# ── Step 4: Per-player rhythm score aggregation ────────────────────────────────

def compute_player_rhythm(all_pairs: pd.DataFrame, min_pairs: int) -> pd.DataFrame:
    """
    For each player, aggregate across all sequential pairs to compute:
      - n_pairs
      - rhythm_score_<feature>: % of pairs where feature increased
      - hot_hand_indicator: after made shot, velocity increases on next poss?
      - classification: MOMENTUM_BUILDER / REACTIVE_COOLER / NEUTRAL
    """
    if all_pairs.empty:
        return pd.DataFrame()

    records = []

    for player_name, pdf in all_pairs.groupby("player_name"):
        n_pairs = len(pdf)
        if n_pairs < min_pairs:
            continue

        rec = {"player_name": player_name, "n_pairs": n_pairs}

        # Rhythm scores per feature
        for feat in SEQ_FEATURES:
            dcol = f"d_{feat}"
            if dcol not in pdf.columns:
                rec[f"rhythm_{feat}"] = np.nan
                continue
            deltas = pdf[dcol].dropna()
            if len(deltas) < 3:
                rec[f"rhythm_{feat}"] = np.nan
                continue
            rec[f"rhythm_{feat}"] = float((deltas > 0).mean())

        # Hot-hand indicator: velocity delta after a scored possession vs missed
        if "result_n" in pdf.columns and "d_velocity" in pdf.columns:
            after_make = pdf[pdf["result_n"].isin(MADE_RESULTS)]["d_velocity"].dropna()
            after_miss = pdf[pdf["result_n"].isin(MISSED_RESULTS)]["d_velocity"].dropna()
            if len(after_make) >= 2 and len(after_miss) >= 2:
                rec["vel_after_make"] = float(after_make.mean())
                rec["vel_after_miss"] = float(after_miss.mean())
                rec["hot_hand_delta"] = rec["vel_after_make"] - rec["vel_after_miss"]
                # Positive = velocity higher after make (hot-hand signal)
                rec["hot_hand_indicator"] = rec["hot_hand_delta"] > 0
            else:
                rec["vel_after_make"] = np.nan
                rec["vel_after_miss"] = np.nan
                rec["hot_hand_delta"] = np.nan
                rec["hot_hand_indicator"] = np.nan

        # Number of games
        rec["n_games"] = pdf["game_id"].nunique()

        # Overall rhythm score: mean across features with valid data
        feat_scores = [rec[f"rhythm_{feat}"] for feat in SEQ_FEATURES
                       if not np.isnan(rec.get(f"rhythm_{feat}", np.nan))]
        rec["rhythm_overall"] = float(np.mean(feat_scores)) if feat_scores else np.nan

        # Top feature (highest rhythm score)
        valid_feats = {feat: rec[f"rhythm_{feat}"] for feat in SEQ_FEATURES
                       if not np.isnan(rec.get(f"rhythm_{feat}", np.nan))}
        if valid_feats:
            rec["top_feature"] = max(valid_feats, key=valid_feats.get)
            rec["top_rhythm_score"] = valid_feats[rec["top_feature"]]
        else:
            rec["top_feature"] = None
            rec["top_rhythm_score"] = np.nan

        # Classification deferred — computed post-hoc with relative thresholds
        rec["classification"] = "PENDING"

        # Low confidence flag
        rec["low_confidence"] = n_pairs < 20

        records.append(rec)

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # ── Relative classification on ball_poss_rate ──────────────────────────────
    # velocity/dribble/paint are zero-inflated; ball_poss_rate is the stable rhythm signal.
    # Use z-score relative to population so the labels reflect genuine spread.
    feat_col = f"rhythm_{CLASSIFICATION_FEATURE}"
    if feat_col in df.columns and df[feat_col].notna().sum() >= 3:
        mu = df[feat_col].mean()
        sigma = df[feat_col].std()
        if sigma > 0:
            z = (df[feat_col] - mu) / sigma
            df["classification"] = np.where(
                z > CLASSIFICATION_Z_THRESHOLD, "MOMENTUM_BUILDER",
                np.where(z < -CLASSIFICATION_Z_THRESHOLD, "REACTIVE_COOLER", "NEUTRAL")
            )
            df["rhythm_z_score"] = z.round(3)
        else:
            df["classification"] = "NEUTRAL"
            df["rhythm_z_score"] = 0.0
    else:
        df["classification"] = df.apply(
            lambda r: (
                "MOMENTUM_BUILDER" if r.get("rhythm_overall", 0) > MOMENTUM_THRESHOLD
                else "REACTIVE_COOLER" if r.get("rhythm_overall", 1) < REACTIVE_THRESHOLD
                else "NEUTRAL"
            ), axis=1
        )
        df["rhythm_z_score"] = np.nan

    # Overwrite INSUFFICIENT_DATA for players with too few valid feature scores
    insufficient = df[[f"rhythm_{f}" for f in SEQ_FEATURES]].isna().all(axis=1)
    df.loc[insufficient, "classification"] = "INSUFFICIENT_DATA"

    return df


# ── Step 5: Signature JSON + Atlas ────────────────────────────────────────────

def _interp_for_player(row: pd.Series, classification: str) -> str:
    """Generate a short interpretation string using ball_poss_rate as anchor signal."""
    # Primary signal: ball_poss_rate rhythm (least zero-inflated)
    bpr = row.get(f"rhythm_{CLASSIFICATION_FEATURE}", np.nan)
    pct_bpr = int(round(bpr * 100)) if not pd.isna(bpr) else None
    z = row.get("rhythm_z_score", np.nan)

    # Secondary: report top feature if different from primary
    feat = row.get("top_feature", CLASSIFICATION_FEATURE)
    feat_label = SEQ_FEAT_INTERP.get(feat, feat)
    top_score = row.get("top_rhythm_score", np.nan)
    pct_top = int(round(top_score * 100)) if not pd.isna(top_score) else None

    z_str = f"z={z:.2f}" if not pd.isna(z) else ""

    if classification == "MOMENTUM_BUILDER":
        if pct_bpr is not None:
            return f"ball-possession escalates {pct_bpr}% of possessions ({z_str}); top signal: {feat_label} ({pct_top}%)"
        return f"builds {feat_label} ({pct_top}% of possessions escalate)"
    elif classification == "REACTIVE_COOLER":
        if pct_bpr is not None:
            return f"ball-possession de-escalates {100-pct_bpr}% of possessions ({z_str})"
        return f"reverts {feat_label} ({pct_top}% escalate)"
    else:
        if pct_bpr is not None:
            return f"neutral ball-possession rhythm ({pct_bpr}% escalate, {z_str})"
        return "neutral rhythm"


def build_signatures_json(player_df: pd.DataFrame) -> Dict:
    """Build the structured signatures JSON."""
    sigs: Dict[str, List] = {
        "MOMENTUM_BUILDERS": [],
        "REACTIVE_COOLERS": [],
        "NEUTRAL": [],
        "INSUFFICIENT_DATA": [],
    }

    # Map singular parquet classification to plural JSON key
    cls_map = {
        "MOMENTUM_BUILDER": "MOMENTUM_BUILDERS",
        "REACTIVE_COOLER": "REACTIVE_COOLERS",
        "NEUTRAL": "NEUTRAL",
        "INSUFFICIENT_DATA": "INSUFFICIENT_DATA",
        "PENDING": "INSUFFICIENT_DATA",
    }

    for _, row in player_df.iterrows():
        raw_cls = str(row.get("classification", "INSUFFICIENT_DATA"))
        cls = cls_map.get(raw_cls, "INSUFFICIENT_DATA")
        entry = {
            "player": row["player_name"],
            "n_pairs": int(row["n_pairs"]),
            "n_games": int(row.get("n_games", 0)),
            "rhythm_overall": round(float(row["rhythm_overall"]), 3) if not pd.isna(row.get("rhythm_overall")) else None,
            "top_feature": row.get("top_feature"),
            "top_rhythm_score": round(float(row["top_rhythm_score"]), 3) if not pd.isna(row.get("top_rhythm_score")) else None,
        }
        for feat in SEQ_FEATURES:
            v = row.get(f"rhythm_{feat}", np.nan)
            entry[f"rhythm_{feat}"] = round(float(v), 3) if not pd.isna(v) else None
        entry["hot_hand_delta"] = round(float(row["hot_hand_delta"]), 3) if not pd.isna(row.get("hot_hand_delta")) else None
        entry["hot_hand_indicator"] = bool(row["hot_hand_indicator"]) if not pd.isna(row.get("hot_hand_indicator")) else None
        entry["rhythm_z_score"] = round(float(row["rhythm_z_score"]), 3) if not pd.isna(row.get("rhythm_z_score")) else None
        entry["low_confidence"] = bool(row.get("low_confidence", True))
        entry["interp"] = _interp_for_player(row, raw_cls)
        sigs[cls].append(entry)

    # Sort each class by rhythm_ball_poss_rate (primary classification signal) descending
    for cls in sigs:
        sigs[cls].sort(key=lambda x: -(x[f"rhythm_{CLASSIFICATION_FEATURE}"] or 0.0))

    return sigs


def build_atlas_markdown(player_df: pd.DataFrame, sigs: Dict, n_games_processed: int) -> str:
    """Build the Obsidian atlas markdown."""
    n_players = len(player_df)
    n_builders = len(sigs["MOMENTUM_BUILDERS"])
    n_coolers = len(sigs["REACTIVE_COOLERS"])
    n_neutral = len(sigs["NEUTRAL"])

    def player_table(entries: List[Dict], n: int = 10) -> str:
        if not entries:
            return "_No players qualified._\n"
        rows = ["| player | top feature | rhythm score | interp |",
                "|--------|-------------|--------------|--------|"]
        for e in entries[:n]:
            feat = e.get("top_feature") or "—"
            score = f"{e['top_rhythm_score']:.2f}" if e.get("top_rhythm_score") is not None else "—"
            interp = e.get("interp", "")
            conf = " ⚠️ low-confidence" if e.get("low_confidence") else ""
            rows.append(f"| {e['player']}{conf} | {feat} | {score} | {interp} |")
        return "\n".join(rows) + "\n"

    # Notable patterns — pick a few with extremes
    notable_lines = []
    for e in sigs["MOMENTUM_BUILDERS"][:3]:
        notable_lines.append(
            f"- **{e['player']}** (MOMENTUM_BUILDER): "
            f"{e['interp']} across {e['n_pairs']} pairs / {e['n_games']} game(s)."
        )
    for e in sigs["REACTIVE_COOLERS"][:2]:
        notable_lines.append(
            f"- **{e['player']}** (REACTIVE_COOLER): "
            f"{e['interp']} across {e['n_pairs']} pairs / {e['n_games']} game(s)."
        )
    notable = "\n".join(notable_lines) if notable_lines else "_Insufficient data for notable examples._"

    md = f"""# Sequential Possession Intelligence Atlas

## Methodology
For each player, analyse consecutive own-team possessions to detect rhythm patterns:
does a player's CV behaviour on possession N predict possession N+1?

**Features tracked:** velocity, dribble_count, paint_touches, ball_possession_rate
**Pair filter:** consecutive own-team possession IDs within a gap of ≤{MAX_GAP_POSSESSIONS}
**Minimum pairs:** {MIN_PAIRS_FLOOR}
**Classification basis:** `ball_poss_rate` rhythm (% of own-team possessions where ball involvement escalated N→N+1).
Velocity/dribble/paint are zero-inflated in static frames and used as secondary signals only.
**Classification cutoffs:** z-score relative to population — MOMENTUM_BUILDER (z > +{CLASSIFICATION_Z_THRESHOLD}), REACTIVE_COOLER (z < −{CLASSIFICATION_Z_THRESHOLD}), NEUTRAL otherwise.
This relative approach ensures ~30% of qualifying players appear in each tail regardless of absolute rhythm level.

## Coverage
- Games processed: {n_games_processed}
- Players with ≥{MIN_PAIRS_FLOOR} sequential pairs: **{n_players}**
- MOMENTUM_BUILDERS: **{n_builders}**
- REACTIVE_COOLERS: **{n_coolers}**
- NEUTRAL: **{n_neutral}**

## Top 10 MOMENTUM_BUILDERS (consistent rhythm escalation)
{player_table(sigs["MOMENTUM_BUILDERS"])}

## Top 10 REACTIVE_COOLERS (consistent rhythm reversion)
{player_table(sigs["REACTIVE_COOLERS"])}

## NEUTRAL Players
{player_table(sigs["NEUTRAL"])}

## Notable Patterns
{notable}

## Betting Implications
- **Live betting:** momentum builders with good Q1 → bet OVER on Q4 stats (they sustain tempo)
- **Pre-bet:** reactive cooler arriving on a hot streak → likely reverts, consider fade
- **Hot-hand check:** players with positive `hot_hand_delta` maintain velocity after makes — compound with clutch label (INT-23) for strongest Q4 bets
- **Combine with:** INT-8 (in-game momentum) — momentum builder + INT-8 signal = highest-conviction live prop

## Honest Caveats
- Single-possession CV stats are noisy; 10-pair floor is permissive (prefer 30+ pairs)
- "Consecutive own-team possessions" filter skips mixed-team frames; turnovers/fouls disrupt sequences
- Phantom slots (unresolved player_id) are excluded but may thin coverage for games with poor OCR
- `team_abbrev` in tracking_data occasionally mis-assigned; corrected via jersey_name_map.json `by_team`
- Games without `by_team` structure in jersey_name_map (old format) contribute zero player pairs
- Velocity column has zero-inflation in static frames; rhythm scores for velocity are biased toward 0% (stasis → stasis)
"""
    return md


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="INT-40: Sequential Possession Intelligence")
    p.add_argument("--min-pairs", type=int, default=MIN_PAIRS_FLOOR,
                   help=f"Minimum sequential pairs per player (default {MIN_PAIRS_FLOOR})")
    p.add_argument("--max-gap", type=int, default=MAX_GAP_POSSESSIONS,
                   help=f"Max possession_id gap for consecutive pairs (default {MAX_GAP_POSSESSIONS})")
    return p.parse_args()


def main():
    args = parse_args()
    min_pairs = args.min_pairs
    max_gap = args.max_gap

    print("=" * 60)
    print("INT-40: Sequential Possession Intelligence")
    print("=" * 60)

    # ── Discover games ─────────────────────────────────────────────────────────
    if not TRACKING_DIR.exists():
        print(f"[ERROR] Tracking directory not found: {TRACKING_DIR}")
        sys.exit(1)

    all_game_dirs = sorted(
        d for d in TRACKING_DIR.iterdir()
        if d.is_dir() and (d / "tracking_data.csv").exists()
    )
    print(f"Found {len(all_game_dirs)} game directories with tracking_data.csv")

    # ── Process each game ──────────────────────────────────────────────────────
    all_game_records: List[Dict] = []
    n_games_processed = 0
    n_games_skipped = 0

    for game_dir in all_game_dirs:
        game_id = game_dir.name

        # Load jersey_name_map — skip if no by_team (can't determine player team)
        name_to_team, jnm_raw = load_jersey_name_map(game_dir)
        if not name_to_team:
            n_games_skipped += 1
            continue

        # Load possessions.csv
        poss_df = load_possessions(game_dir)
        if poss_df.empty:
            n_games_skipped += 1
            continue

        poss_map = build_poss_map(poss_df)
        if not poss_map:
            n_games_skipped += 1
            continue

        # Load tracking data
        track_df = load_tracking(game_dir)
        if track_df.empty:
            n_games_skipped += 1
            continue

        # Process game
        records = process_game(game_id, name_to_team, poss_map, track_df)
        if records:
            all_game_records.extend(records)
            n_games_processed += 1
            if n_games_processed % 20 == 0:
                print(f"  Processed {n_games_processed} games, {len(all_game_records)} possession-player records...")
        else:
            n_games_skipped += 1

    print(f"\nGame processing complete: {n_games_processed} processed, {n_games_skipped} skipped")
    print(f"Total possession-player records: {len(all_game_records)}")

    if not all_game_records:
        print("[ERROR] No records collected. Check that tracking_data.csv files have player_name column.")
        sys.exit(1)

    # ── Extract sequential pairs ───────────────────────────────────────────────
    print("\nExtracting sequential possession pairs...")
    all_pairs = extract_sequential_pairs(all_game_records)
    print(f"Total sequential pairs: {len(all_pairs)}")

    if not all_pairs:
        print("[ERROR] No sequential pairs found. Data may lack enough consecutive own-team possessions.")
        sys.exit(1)

    pairs_df = pd.DataFrame(all_pairs)

    # ── Compute per-player rhythm scores ──────────────────────────────────────
    print("\nComputing per-player rhythm scores...")
    player_df = compute_player_rhythm(pairs_df, min_pairs=min_pairs)
    print(f"Players with ≥{min_pairs} pairs: {len(player_df)}")

    if player_df.empty:
        print(f"[WARN] No players meet the {min_pairs}-pair threshold. "
              f"Total pairs available: {len(pairs_df)}. "
              f"Try --min-pairs 5.")
        # Still write empty outputs
        player_df = pd.DataFrame(columns=["player_name", "n_pairs", "classification"])

    # ── Save parquet ───────────────────────────────────────────────────────────
    player_df.to_parquet(OUTPUT_PARQUET, index=False)
    print(f"\nSaved: {OUTPUT_PARQUET}")

    # ── Build signatures JSON ─────────────────────────────────────────────────
    sigs = build_signatures_json(player_df)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(sigs, f, indent=2, ensure_ascii=False)
    print(f"Saved: {OUTPUT_JSON}")

    # ── Build Atlas markdown ───────────────────────────────────────────────────
    atlas_md = build_atlas_markdown(player_df, sigs, n_games_processed)
    with open(OUTPUT_ATLAS, "w", encoding="utf-8") as f:
        f.write(atlas_md)
    print(f"Saved: {OUTPUT_ATLAS}")

    # ── Final report ───────────────────────────────────────────────────────────
    n_builders = len(sigs["MOMENTUM_BUILDERS"])
    n_coolers = len(sigs["REACTIVE_COOLERS"])
    n_neutral = len(sigs["NEUTRAL"])

    print("\n" + "=" * 60)
    print("## INT-40 Sequential Possession — Final Report")
    print("=" * 60)

    print(f"""
### Coverage
- Games processed: {n_games_processed}
- Total possession-player records: {len(all_game_records)}
- Total sequential pairs: {len(pairs_df)}
- Players with ≥{min_pairs} pairs: {len(player_df)}
  - MOMENTUM_BUILDERS: {n_builders}
  - REACTIVE_COOLERS: {n_coolers}
  - NEUTRAL: {n_neutral}
""")

    # Top 5 momentum builders
    builders = sigs["MOMENTUM_BUILDERS"][:5]
    coolers = sigs["REACTIVE_COOLERS"][:5]

    if builders:
        print("### Top 5 MOMENTUM_BUILDERS")
        print(f"{'player':<30} {'bpr_rhythm':>10}  {'z':>6}  story")
        print("-" * 75)
        for e in builders:
            bpr = e.get(f"rhythm_{CLASSIFICATION_FEATURE}")
            score = f"{bpr:.2f}" if bpr is not None else "—"
            z_val = e.get("rhythm_z_score")
            z_str = f"{z_val:+.2f}" if z_val is not None else "—"
            conf = " ⚠️" if e.get("low_confidence") else ""
            print(f"{e['player']:<30} {score:>10}  {z_str:>6}  {e['interp']}{conf}")

    if coolers:
        print("\n### Top 5 REACTIVE_COOLERS")
        print(f"{'player':<30} {'bpr_rhythm':>10}  {'z':>6}  story")
        print("-" * 75)
        for e in coolers:
            bpr = e.get(f"rhythm_{CLASSIFICATION_FEATURE}")
            score = f"{bpr:.2f}" if bpr is not None else "—"
            z_val = e.get("rhythm_z_score")
            z_str = f"{z_val:+.2f}" if z_val is not None else "—"
            conf = " ⚠️" if e.get("low_confidence") else ""
            print(f"{e['player']:<30} {score:>10}  {z_str:>6}  {e['interp']}{conf}")

    print(f"""
### Files
- scripts/build_sequential_possession.py
- {OUTPUT_ATLAS}
- {OUTPUT_PARQUET}
- {OUTPUT_JSON}

### How to use
- Live in-game: momentum builder with good Q1 → bet OVER on Q4 stats
- Pre-bet: reactive cooler on a hot streak → likely reverts, consider fade
- Combine with INT-8 (in-game momentum) and INT-23 (clutch) for strongest bets

### Honest caveats
- Noisy at low pair counts (<20 pairs) — flagged as low_confidence
- Possession-level CV aggregation has limits (zero-inflation in static frames)
- Phantom slots inflate noise; games with old jersey_name_map format (no by_team) excluded
""")


if __name__ == "__main__":
    main()
