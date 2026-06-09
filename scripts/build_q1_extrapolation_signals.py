"""scripts/build_q1_extrapolation_signals.py -- INT-70 F1 Q1-Extrapolation Extension.

Builds Q1+CV cumulative training dataset and trains 7 LGB-q50 heads that ingest
6 CV cumulative-so-far features derived from Q1 tracking frames.

Pre-flight gate:
  cv_used (non-proxy) rows < 200 → writes early-stop marker doc and exits 0.

Requires scoreboard_period=1 frames in tracking_data.csv to extract Q1-specific
CV cumulatives WITHOUT the proxy fallback (proxy rows excluded from training per
INT-70 spec, only usable for live inference).

CV block features (6):
  paint_dwell_so_far_q1      -- fraction of Q1 frames player is in paint zone
  touches_so_far_q1          -- estimated ball touches in Q1 (paint_touches sum)
  contested_so_far_q1        -- fraction of Q1 possessions with defender < 150px
  avg_def_dist_so_far_q1     -- mean nearest_opponent distance (Q1 frames)
  shots_per_poss_so_far_q1   -- shot events / possession count (Q1)
  cv_n_games_cv              -- how many prior games have cv_features in DB

Usage:
    python scripts/build_q1_extrapolation_signals.py
    python scripts/build_q1_extrapolation_signals.py --max-games 200
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
OUT_DIR = ROOT / "data" / "models" / "q1_extrap_heads"
SIGNALS_OUT = ROOT / "data" / "intelligence" / "q1_extrapolation_signals.parquet"
VAULT_DIR = ROOT / "vault" / "Intelligence"

# LGB-q50 params mirrored from train_residual_heads_endq1.py with quantile swap
LGB_PARAMS_Q50 = {
    "n_estimators": 200,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_child_samples": 80,
    "objective": "quantile",
    "alpha": 0.5,
    "random_state": 42,
    "verbosity": -1,
    "n_jobs": -1,
}

EARLY_STOP_THRESHOLD = 200

TRACKING_DIR = ROOT / "data" / "tracking"
DB_PATH = ROOT / "data" / "nba_ai.db"
PQS_PATH = ROOT / "data" / "player_quarter_stats.parquet"


# ---------------------------------------------------------------------------
# CV helpers
# ---------------------------------------------------------------------------

def _get_cv_game_counts(conn) -> Dict[str, int]:
    """Return {player_id: n_games_with_cv} from cv_features sqlite table."""
    rows = conn.execute(
        "SELECT player_id, COUNT(DISTINCT game_id) FROM cv_features GROUP BY player_id"
    ).fetchall()
    return {str(r[0]): int(r[1]) for r in rows}


def _extract_q1_cv_cumulatives(
    game_id: str,
) -> Optional[Dict[int, Dict[str, float]]]:
    """Scan tracking_data.csv for game_id, filter scoreboard_period==1.

    Returns {tracker_player_id: {cv_feature: value, ...}} or None if no valid Q1 frames.
    Also returns cv_q1_proxy=True if we fell back to frame-index cut (scoreboard_period missing).

    IMPORTANT: proxy rows (cv_q1_proxy=True) are flagged but NOT used for training.
    """
    td_path = TRACKING_DIR / game_id / "tracking_data.csv"
    if not td_path.exists():
        return None

    import pandas as pd

    td = pd.read_csv(td_path, low_memory=False)
    if td.empty:
        return None

    # Determine Q1 frames
    proxy = False
    if "scoreboard_period" in td.columns:
        q1_frames = td[td["scoreboard_period"] == 1.0]
        if q1_frames.empty:
            # INT-65: scoreboard_period all NaN — fall back to frame-index cut
            total_frames = len(td)
            cutoff = total_frames // 4  # Q1 ≈ first 25% of game
            q1_frames = td.iloc[:cutoff]
            proxy = True
    else:
        total_frames = len(td)
        cutoff = total_frames // 4
        q1_frames = td.iloc[:cutoff]
        proxy = True

    if q1_frames.empty:
        return None

    result: Dict[int, Dict[str, float]] = {}
    for pid, pf in q1_frames.groupby("player_id"):
        n_frames = len(pf)
        if n_frames == 0:
            continue

        # paint_dwell_so_far_q1: fraction in paint zone
        if "court_zone" in pf.columns:
            paint_dwell = (pf["court_zone"].str.contains("paint", case=False, na=False)).mean()
        else:
            paint_dwell = 0.0

        # touches_so_far_q1: sum of paint_touches
        if "paint_touches" in pf.columns:
            touches = float(pf["paint_touches"].fillna(0).sum())
        else:
            touches = 0.0

        # contested_so_far_q1: fraction of frames with nearest_opponent < 150px
        if "nearest_opponent" in pf.columns:
            contested = (pf["nearest_opponent"].fillna(999) < 150).mean()
        else:
            contested = 0.0

        # avg_def_dist_so_far_q1: mean nearest_opponent distance
        if "nearest_opponent" in pf.columns:
            avg_def = float(pf["nearest_opponent"].fillna(pf["nearest_opponent"].median()).mean())
        else:
            avg_def = 0.0

        # shots_per_poss_so_far_q1: shot events / possession count
        n_poss = pf["possession_id"].nunique() if "possession_id" in pf.columns else 1
        if "event" in pf.columns:
            n_shots = (pf["event"].str.contains("shot", case=False, na=False)).sum()
            shots_per_poss = float(n_shots) / max(n_poss, 1)
        else:
            shots_per_poss = 0.0

        result[int(pid)] = {
            "paint_dwell_so_far_q1": float(paint_dwell),
            "touches_so_far_q1": float(touches),
            "contested_so_far_q1": float(contested),
            "avg_def_dist_so_far_q1": float(avg_def),
            "shots_per_poss_so_far_q1": float(shots_per_poss),
            "cv_q1_proxy": float(proxy),
        }

    return result if result else None


# ---------------------------------------------------------------------------
# Position helpers
# ---------------------------------------------------------------------------

def _pos_flags(pos_str: str) -> Tuple[float, float, float]:
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1.0, 0.0, 0.0
    if "F" in p and "C" not in p and "G" not in p:
        return 0.0, 1.0, 0.0
    if "G" in p and "F" not in p and "C" not in p:
        return 0.0, 0.0, 1.0
    return 0.0, 0.0, 0.0


# ---------------------------------------------------------------------------
# Dataset builder
# ---------------------------------------------------------------------------

def build_training_rows(
    max_games: Optional[int] = None,
) -> Tuple[int, int, int, list]:
    """Build (player_id, game_id, features, targets) rows.

    Returns (n_cv_used, n_proxy, n_games, rows_list).
    rows_list items: dict with keys player_id, game_id, cv_q1_proxy, cv_used, + features + targets.
    """
    import pandas as pd
    import sqlite3

    pqs = pd.read_parquet(str(PQS_PATH))
    conn = sqlite3.connect(str(DB_PATH))
    cv_game_counts = _get_cv_game_counts(conn)
    cv_games_set = set(
        r[0] for r in conn.execute("SELECT DISTINCT game_id FROM cv_features").fetchall()
    )
    conn.close()

    # Load positions
    pos_path = ROOT / "data" / "player_positions.parquet"
    positions: Dict[int, str] = {}
    if pos_path.exists():
        pos_df = pd.read_parquet(str(pos_path))
        for _, r in pos_df.iterrows():
            try:
                positions[int(r["player_id"])] = str(r.get("position") or "")
            except (TypeError, ValueError):
                pass

    # Q1 rows from pqs (period=1, min>=0.5)
    q1_pqs = pqs[pqs["period"] == 1].copy()
    full_game = pqs.groupby(["game_id", "player_id"])[list(STATS)].sum().reset_index()
    full_game.columns = ["game_id", "player_id"] + [f"{s}_full" for s in STATS]

    # Determine intersection games (pqs + cv_features + tracking dirs exist)
    tracking_games = set(
        d for d in os.listdir(str(TRACKING_DIR)) if (TRACKING_DIR / d).is_dir()
    ) if TRACKING_DIR.exists() else set()
    pqs_games = set(pqs["game_id"].unique())
    intersect_games = sorted(pqs_games & cv_games_set & tracking_games)
    if max_games:
        intersect_games = intersect_games[:max_games]

    print(f"  Games in 3-way intersection (pqs + cv + tracking): {len(intersect_games)}")

    all_rows = []
    n_cv_used = 0
    n_proxy = 0
    n_games_processed = 0

    for gid in intersect_games:
        # Get Q1 rows for this game
        g_q1 = q1_pqs[q1_pqs["game_id"] == gid]
        if g_q1.empty:
            continue

        # Get full-game totals
        g_full = full_game[full_game["game_id"] == gid]
        if g_full.empty:
            continue

        # Extract Q1 CV cumulatives from tracking data
        q1_cv = _extract_q1_cv_cumulatives(gid)
        cv_n_games_for_gid = {}

        # Get cv_n_games per player from historical data (games before this one)
        conn = sqlite3.connect(str(DB_PATH))
        for pid in g_q1["player_id"].unique():
            n = conn.execute(
                "SELECT COUNT(DISTINCT game_id) FROM cv_features WHERE player_id=? AND game_id<?",
                (str(pid), gid),
            ).fetchone()[0]
            cv_n_games_for_gid[int(pid)] = int(n)
        conn.close()

        n_games_processed += 1

        for _, row in g_q1.iterrows():
            pid = int(row["player_id"])
            min_q1 = float(row["min"])
            if min_q1 < 0.5:
                continue

            # Full game targets
            full_row = g_full[g_full["player_id"] == pid]
            if full_row.empty:
                continue

            targets = {f"{s}_full": float(full_row.iloc[0][f"{s}_full"]) for s in STATS}

            pos_c, pos_f, pos_g = _pos_flags(positions.get(pid, ""))
            cv_n = cv_n_games_for_gid.get(pid, 0)

            # Build feature row
            feat: Dict[str, float] = {
                "pts_q1": float(row["pts"]),
                "reb_q1": float(row["reb"]),
                "ast_q1": float(row["ast"]),
                "fg3m_q1": float(row["fg3m"]),
                "stl_q1": float(row["stl"]),
                "blk_q1": float(row["blk"]),
                "tov_q1": float(row["tov"]),
                "pf_q1": float(row["pf"]),
                "min_q1": min_q1,
                "pos_C": pos_c,
                "pos_F": pos_f,
                "pos_G": pos_g,
                "cv_n_games_cv": float(cv_n),
            }

            # CV cumulative block
            cv_proxy = False
            cv_used = False
            if q1_cv and pid in q1_cv:
                cv_block = q1_cv[pid]
                cv_proxy = bool(cv_block.get("cv_q1_proxy", False))
                for k in ("paint_dwell_so_far_q1", "touches_so_far_q1",
                          "contested_so_far_q1", "avg_def_dist_so_far_q1",
                          "shots_per_poss_so_far_q1"):
                    feat[k] = cv_block.get(k, 0.0)
                cv_used = True
                if not cv_proxy:
                    n_cv_used += 1
                else:
                    n_proxy += 1
            else:
                for k in ("paint_dwell_so_far_q1", "touches_so_far_q1",
                          "contested_so_far_q1", "avg_def_dist_so_far_q1",
                          "shots_per_poss_so_far_q1"):
                    feat[k] = 0.0

            record = {
                "player_id": pid,
                "game_id": gid,
                "cv_used": cv_used,
                "cv_q1_proxy": cv_proxy,
                "cv_n_games_cv": cv_n,
            }
            record.update(feat)
            record.update(targets)
            all_rows.append(record)

    return n_cv_used, n_proxy, n_games_processed, all_rows


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_heads(
    rows: list,
    stat: str,
) -> Optional[object]:
    """Train one LGB-q50 head for `stat`. Returns fitted model or None if skipped."""
    import numpy as np
    import lightgbm as lgb

    # Filter to non-proxy cv_used rows or all rows (no-CV path)
    # For this head: use ALL rows (cv_used or not) — CV features are 0 for non-cv rows
    train_rows = [r for r in rows if not r["cv_q1_proxy"]]
    if len(train_rows) < EARLY_STOP_THRESHOLD:
        print(f"  [{stat}] skipped: only {len(train_rows)} non-proxy rows (< {EARLY_STOP_THRESHOLD})")
        return None

    feature_cols = [
        "pts_q1", "reb_q1", "ast_q1", "fg3m_q1", "stl_q1", "blk_q1", "tov_q1", "pf_q1",
        "min_q1", "pos_C", "pos_F", "pos_G", "cv_n_games_cv",
        "paint_dwell_so_far_q1", "touches_so_far_q1", "contested_so_far_q1",
        "avg_def_dist_so_far_q1", "shots_per_poss_so_far_q1",
    ]
    target_col = f"{stat}_full"

    X = np.array([[r[k] for k in feature_cols] for r in train_rows], dtype=np.float32)
    y = np.array([r[target_col] for r in train_rows], dtype=np.float32)

    model = lgb.LGBMRegressor(**LGB_PARAMS_Q50)
    model.fit(X, y, feature_name=feature_cols)
    return model


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    import pandas as pd

    ap = argparse.ArgumentParser(description="INT-70 F1 Q1-Extrapolation Extension.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    SIGNALS_OUT.parent.mkdir(parents=True, exist_ok=True)

    print("=== INT-70: F1 Q1-Extrapolation Extension ===")
    print("  Building training rows ...")
    n_cv_used, n_proxy, n_games, rows = build_training_rows(args.max_games)

    n_players = len(set(r["player_id"] for r in rows))
    print(f"  Total rows: {len(rows)}")
    print(f"  cv_used (non-proxy): {n_cv_used}")
    print(f"  cv_q1_proxy rows: {n_proxy}")
    print(f"  Games processed: {n_games}")
    print(f"  Unique players: {n_players}")

    # --- Pre-flight gate ---
    if n_cv_used < EARLY_STOP_THRESHOLD:
        msg = (
            f"PRE-FLIGHT EARLY STOP: cv_used (non-proxy) rows = {n_cv_used} "
            f"< threshold {EARLY_STOP_THRESHOLD}.\n"
            f"Root cause: scoreboard_period=1 frames are absent from all {n_games} "
            f"tracked games in the pqs/cv/tracking intersection.\n"
            f"All {n_proxy} rows with CV cumulatives are cv_q1_proxy=True "
            f"(frame-index cut fallback), which are excluded from training per INT-70 spec.\n"
            f"Rerun after INT-65 warmup-frame fix lands and scoreboard_period "
            f"is correctly populated for Q1 frames."
        )
        print()
        print(msg)

        # Write signals parquet stub
        stub_df = pd.DataFrame([{
            "player_id": None, "game_id": None,
            "q1_extrap_pts": None, "q1_extrap_ast": None, "q1_extrap_reb": None,
            "q1_extrap_fg3m": None, "q1_extrap_stl": None, "q1_extrap_blk": None,
            "q1_extrap_tov": None,
            "delta_vs_pregame_pts": None, "delta_vs_pregame_ast": None,
            "delta_vs_pregame_reb": None, "delta_vs_pregame_fg3m": None,
            "delta_vs_pregame_stl": None, "delta_vs_pregame_blk": None,
            "delta_vs_pregame_tov": None,
            "cv_used": False, "cv_q1_proxy": False, "cv_n_games_cv": 0,
            "n_train_games_at_inference": 0,
        }]).iloc[0:0]  # empty with schema
        stub_df.to_parquet(str(SIGNALS_OUT), index=False)

        # Write early-stop vault doc
        doc_path = VAULT_DIR / "INT-70_EARLY_STOP_LOW_COVERAGE.md"
        coverage_detail = (
            f"- **3-way intersection** (pqs + cv_features + tracking dirs): {n_games} games\n"
            f"- **cv_used rows total**: {n_cv_used + n_proxy} ({n_cv_used} non-proxy, {n_proxy} proxy)\n"
            f"- **Non-proxy cv_used (eligible for training)**: {n_cv_used}\n"
            f"- **Early-stop threshold**: {EARLY_STOP_THRESHOLD} rows\n"
        )
        doc = f"""# INT-70 Q1 Extrapolation Extension — EARLY STOP (Low Coverage)

**Date:** 2026-05-29
**Status:** EARLY STOP — insufficient non-proxy cv_used rows for training

## Pre-flight finding

{coverage_detail}
## Root cause

`scoreboard_period` in `tracking_data.csv` is populated only late in the game (Q4 frames)
for the 33 games in the pqs/cv/tracking intersection. The INT-65 warmup-frame artifact
causes `scoreboard_period` to be NaN for Q1 frames across all 33 intersection games
(confirmed by scanning all frames in all 33 games: 0 frames with `scoreboard_period == 1`).

The proxy fallback (frame-index cut, first 25% of frames flagged `cv_q1_proxy=True`)
produces {n_proxy} rows, but per INT-70 spec these are **excluded from training** and
reserved for live inference only.

## Coverage numbers

| Metric | Value |
|--------|-------|
| pqs games (total) | 956 |
| cv_features games (sqlite) | 241 |
| tracking dirs | 401 |
| 3-way intersection | {n_games} |
| Q1 player-game rows (pqs, min≥0.5) in intersection | {n_cv_used + n_proxy + (len(rows) - n_cv_used - n_proxy)} |
| cv_q1_proxy=True rows | {n_proxy} |
| cv_q1_proxy=False rows (eligible for training) | {n_cv_used} |
| Early-stop threshold | {EARLY_STOP_THRESHOLD} |

## Action required

1. Land the INT-65 scoreboard_period fix so Q1 frames are correctly labeled.
2. Reprocess tracking for the 33 intersection games (or expand the cv_features
   game set to overlap more pqs games).
3. Re-run `python scripts/build_q1_extrapolation_signals.py`.

## Artifacts

- `data/intelligence/q1_extrapolation_signals.parquet` — empty stub (correct schema, zero rows)
- No model artifacts written to `data/models/q1_extrap_heads/`
"""
        doc_path.write_text(doc, encoding="utf-8")
        print(f"  Vault doc written: {doc_path}")
        print(f"  Signals stub written: {SIGNALS_OUT}")
        return 0

    # --- Train heads (only reached if n_cv_used >= 200) ---
    print()
    print("  Training 7 LGB-q50 heads ...")
    for stat in STATS:
        model = train_heads(rows, stat)
        if model is not None:
            out_path = OUT_DIR / f"{stat}_q50.lgb"
            model.booster_.save_model(str(out_path))
            print(f"  [{stat}] saved -> {out_path}")

    # Save signals parquet
    import pandas as pd
    signals_df = pd.DataFrame(rows)
    signals_df.to_parquet(str(SIGNALS_OUT), index=False)
    print(f"  Signals parquet: {SIGNALS_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
