"""
feature_pipeline.py — Batch feature engineering wrapper.

Functions
---------
    run_features(input_csv, output_csv)               -> pd.DataFrame
    enrich_with_nba(df, game_id, season)              -> pd.DataFrame

``run_features`` is a thin call into ``feature_engineering.run()`` with
explicit paths so callers do not have to worry about the module's default
path resolution.

``enrich_with_nba`` calls ``src.data.nba_enricher.enrich()`` and then
merges any new shot-outcome / possession-result columns back onto the
tracking/features DataFrame by matching on frame number.

Usage
-----
    from src.pipeline.feature_pipeline import run_features, enrich_with_nba

    features_df = run_features("data/tracking_data.csv", "data/features.csv")
    enriched_df = enrich_with_nba(features_df, "0022401001", "2024-25")
"""

from __future__ import annotations

import os
import sys
from typing import Optional

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_DATA_DIR  = os.path.join(PROJECT_DIR, "data")
_NBA_CACHE = os.path.join(_DATA_DIR, "nba")


# ── run_features ──────────────────────────────────────────────────────────────

def run_features(
    input_csv: Optional[str] = None,
    output_csv: Optional[str] = None,
) -> pd.DataFrame:
    """
    Run the full feature engineering pipeline on a tracking CSV.

    Wraps ``src.features.feature_engineering.run()`` with explicit
    path arguments so the caller controls I/O locations rather than
    relying on the module's default path resolution.

    Args:
        input_csv:  Path to raw tracking data CSV.
                    Defaults to ``data/tracking_data.csv``.
        output_csv: Destination for engineered features CSV.
                    Defaults to ``data/features.csv``.

    Returns:
        DataFrame with all original columns plus engineered features.
        Empty DataFrame if ``input_csv`` does not exist or is empty.
    """
    if input_csv is None:
        input_csv = os.path.join(_DATA_DIR, "tracking_data.csv")
    if output_csv is None:
        output_csv = os.path.join(_DATA_DIR, "features.csv")

    if not os.path.exists(input_csv):
        return pd.DataFrame()

    from src.features.feature_engineering import run as fe_run

    # feature_engineering.run() honours explicit paths via its parameters
    return fe_run(input_path=input_csv, output_path=output_csv)


# ── enrich_with_nba ───────────────────────────────────────────────────────────

def enrich_with_nba(
    df: pd.DataFrame,
    game_id: str,
    season: str = "2024-25",
    period: int = 1,
    clip_start_sec: float = 0.0,
    fps: float = 30.0,
) -> pd.DataFrame:
    """
    Enrich a features DataFrame with NBA API shot outcomes and possession
    results.

    Calls ``src.data.nba_enricher.enrich()``, which writes updated
    ``shot_log.csv`` and ``possessions.csv`` files.  The function then
    re-reads those files and left-joins the outcome columns back onto
    ``df`` using the ``frame`` column as the join key.

    Outcome columns added (when available):
        shot_made     — 1/0 from NBA PBP (shot rows only)
        poss_result   — "scored" / "missed_shot" / "turnover" / "foul" / "unknown"
        outcome_score — 1 if possession resulted in points, else 0
        score_diff    — score differential at possession start

    Args:
        df:             Features DataFrame produced by ``run_features``.
        game_id:        NBA game ID (e.g. '0022401001').
        season:         NBA season string.
        period:         Game quarter the clip covers (1–4, or 5 for OT).
        clip_start_sec: Seconds into the quarter when the clip starts.
        fps:            Frames-per-second of the source video.

    Returns:
        Enriched DataFrame.  If enrichment fails (no network, no game_id
        in API, etc.) the original ``df`` is returned unchanged.
    """
    if df.empty:
        return df

    try:
        from src.data.nba_enricher import enrich as nba_enrich

        nba_enrich(
            game_id        = game_id,
            period         = period,
            clip_start_sec = clip_start_sec,
            fps            = fps,
        )
    except Exception as exc:
        print(f"[feature_pipeline] nba_enricher.enrich failed: {exc}")
        return df

    df = df.copy()

    # Merge shot outcomes back by frame
    shot_log_path = os.path.join(_DATA_DIR, "shot_log.csv")
    if os.path.exists(shot_log_path):
        try:
            shots = pd.read_csv(shot_log_path)
            shots = shots.rename(columns={"made": "shot_made"})
            merge_cols = [c for c in ["frame", "shot_made"] if c in shots.columns]
            if "frame" in merge_cols and "shot_made" in merge_cols:
                shots = shots[merge_cols].drop_duplicates("frame")
                df = df.merge(shots, on="frame", how="left")
        except Exception:
            pass

    # Merge possession outcomes back by frame
    possessions_path = os.path.join(_DATA_DIR, "possessions.csv")
    if os.path.exists(possessions_path):
        try:
            poss = pd.read_csv(possessions_path)
            poss_cols = [c for c in
                         ["frame", "result", "outcome_score", "score_diff"]
                         if c in poss.columns]
            if "frame" in poss_cols:
                poss = poss[poss_cols].drop_duplicates("frame")
                if "result" in poss.columns:
                    poss = poss.rename(columns={"result": "poss_result"})
                df = df.merge(poss, on="frame", how="left")
        except Exception:
            pass

    return df


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Feature engineering pipeline")
    ap.add_argument("--input",    default=None, help="Input tracking CSV")
    ap.add_argument("--output",   default=None, help="Output features CSV")
    ap.add_argument("--enrich",   action="store_true",
                    help="Also run NBA API enrichment")
    ap.add_argument("--game-id",  default="",   help="NBA game ID (for --enrich)")
    ap.add_argument("--season",   default="2024-25")
    args = ap.parse_args()

    result_df = run_features(args.input, args.output)
    print(f"Features: {len(result_df)} rows, {len(result_df.columns)} cols")

    if args.enrich and args.game_id:
        result_df = enrich_with_nba(result_df, args.game_id, args.season)
        print(f"Enriched: {len(result_df)} rows, {len(result_df.columns)} cols")
