"""domains.tennis.wta_corpus — Build and validate the WTA Elo corpus.

Loads cached WTA match CSVs, transforms to the same schema as ATP matches.parquet
(tour="wta"), writes ``data/domains/tennis/wta_matches.parquet`` (separate file,
never mutates the ATP parquet), and runs a walk-forward Elo validation to produce
Brier / logloss / ECE as a genuine second corpus.

HARD CONSTRAINTS (read before editing):
- Does NOT import from src/, kernel/, api/, or scripts/.
- Does NOT modify ATP matches.parquet or any existing domains/tennis file.
- WTA player IDs are independent of ATP — no contamination.
- No betting-edge claim of any kind; accuracy/calibration only.
- Sackmann data is CC BY-NC-SA — private research use only.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Read-only imports from existing tennis modules (no mutation)
from domains.tennis.ingest_sackmann import (
    MATCHES_REQUIRED_COLS,
    _normalize_surface,
    _retirement_flag,
    _round_key,
    _ROUND_DEFAULT,
    ROUND_ORDER,
)
from domains.tennis.elo_walkforward import walk_forward_elo
from domains.tennis.elo_tune import brier, logloss, ece, platt_recalibrate, _walk_forward_blend

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WTA_RAW_DIR = Path("data/domains/tennis/_raw/sackmann")
WTA_OUT_PATH = Path("data/domains/tennis/wta_matches.parquet")
TRAIN_YEAR_MAX: int = 2022   # same split used by ATP elo_tune
_EPS: float = 1e-9


# ---------------------------------------------------------------------------
# Build WTA corpus
# ---------------------------------------------------------------------------

def build_wta_corpus(
    raw_dir: str | Path = WTA_RAW_DIR,
    out_path: str | Path = WTA_OUT_PATH,
    start_year: int = 2000,
    end_year: int = 2025,
) -> pd.DataFrame:
    """Load WTA match CSVs and write wta_matches.parquet.

    Applies the identical transform as ingest_sackmann._transform_matches but
    only for tour="wta".  ATP parquet is never touched.

    Returns
    -------
    pd.DataFrame
        Transformed WTA matches in chronological sort order.
    """
    raw = Path(raw_dir)
    frames: list[pd.DataFrame] = []
    for yr in range(start_year, end_year + 1):
        p = raw / f"wta_matches_{yr}.csv"
        if not p.exists():
            continue
        try:
            df = pd.read_csv(p, dtype=str, low_memory=False)
        except Exception:
            continue
        df["_tour"] = "wta"
        frames.append(df)

    if not frames:
        raise FileNotFoundError(f"No WTA CSV files found under {raw_dir}")

    raw_df = pd.concat(frames, ignore_index=True)
    return _transform_wta(raw_df, out_path)


def _transform_wta(raw_df: pd.DataFrame, out_path: str | Path) -> pd.DataFrame:
    """Normalise raw WTA rows to the MATCHES_REQUIRED_COLS schema."""
    import datetime as dt

    df = raw_df.copy()
    tour_col = "_tour"

    winner_id = pd.to_numeric(df.get("winner_id", pd.Series(dtype="float64")), errors="coerce")
    loser_id  = pd.to_numeric(df.get("loser_id",  pd.Series(dtype="float64")), errors="coerce")

    # Stable orientation: p1 = min(winner_id, loser_id) — outcome-blind, kills ex-post label leak
    p1_is_winner = winner_id <= loser_id
    df["p1_id"] = winner_id.where(p1_is_winner, loser_id).astype("Int64")
    df["p2_id"] = loser_id.where(p1_is_winner, winner_id).astype("Int64")
    df["p1_name"] = df.get("winner_name", pd.Series(dtype=str)).where(
        p1_is_winner, df.get("loser_name", pd.Series(dtype=str))
    )
    df["p2_name"] = df.get("loser_name", pd.Series(dtype=str)).where(
        p1_is_winner, df.get("winner_name", pd.Series(dtype=str))
    )
    df["p1_rank"] = (
        pd.to_numeric(df.get("winner_rank", pd.Series(dtype="float64")), errors="coerce")
        .where(p1_is_winner,
               pd.to_numeric(df.get("loser_rank", pd.Series(dtype="float64")), errors="coerce"))
        .astype("float32")
    )
    df["p2_rank"] = (
        pd.to_numeric(df.get("loser_rank", pd.Series(dtype="float64")), errors="coerce")
        .where(p1_is_winner,
               pd.to_numeric(df.get("winner_rank", pd.Series(dtype="float64")), errors="coerce"))
        .astype("float32")
    )
    df["winner"]  = p1_is_winner.map({True: 1, False: 2}).astype("int8")
    df["date"]    = pd.to_datetime(
        df.get("tourney_date", pd.Series(dtype=str)), format="%Y%m%d", errors="coerce"
    ).dt.date
    df["surface"] = df.get("surface", pd.Series(dtype=str)).apply(_normalize_surface)
    df["best_of"] = (
        pd.to_numeric(df.get("best_of", pd.Series(dtype="float64")), errors="coerce")
        .fillna(3).astype("int8")
    )
    df["match_num"] = (
        pd.to_numeric(df.get("match_num", pd.Series(dtype="float64")), errors="coerce")
        .fillna(0).astype("int32")
    )
    df["score"]      = df.get("score", pd.Series(dtype=str)).fillna("").astype(str)
    df["retirement"] = df["score"].apply(_retirement_flag)
    df["minutes"]    = pd.to_numeric(
        df.get("minutes", pd.Series(dtype="float64")), errors="coerce"
    ).astype("float32")
    df["tour"] = df[tour_col].astype(str)

    for fld in ("tourney_id", "tourney_name", "tourney_level", "round"):
        df[fld] = df.get(fld, pd.Series(dtype=str)).fillna("").astype(str)

    def _make_event_id(row: pd.Series) -> str:
        d = row["date"].strftime("%Y%m%d") if isinstance(row["date"], dt.date) else "00000000"
        return f"{d}-{row['tour']}-{row['tourney_id']}-{row['p1_id']}-{row['p2_id']}-{row['match_num']}"

    df["event_id"] = df.apply(_make_event_id, axis=1)
    df["_round_ord"] = df["round"].apply(_round_key)
    df = df.sort_values(
        ["date", "tour", "tourney_id", "_round_ord", "match_num"],
        kind="mergesort", na_position="last",
    ).reset_index(drop=True)

    # Keep main-draw levels (same filter as ATP ingest)
    _keep = {"G", "M", "A", "F", "D", "O", "PM", ""}
    df = df[
        df["tourney_level"].isin(_keep) | df["tourney_level"].str.match(r"^\d+$", na=False)
    ].copy()

    out = df[MATCHES_REQUIRED_COLS].copy()

    if out["event_id"].duplicated().any():
        mask = out["event_id"].duplicated(keep=False)
        out.loc[mask, "event_id"] = (
            out.loc[mask, "event_id"] + "-"
            + out.loc[mask].groupby("event_id").cumcount().astype(str)
        )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(out, preserve_index=False), out_path)
    return out


# ---------------------------------------------------------------------------
# Validation: walk-forward Elo metrics on WTA corpus
# ---------------------------------------------------------------------------

def validate_wta_elo(
    wta_df: pd.DataFrame,
    train_year_max: int = TRAIN_YEAR_MAX,
    blend: float = 0.3,
) -> dict:
    """Run leak-free walk-forward Elo on wta_df; return Brier/logloss/ECE.

    Uses the SAME walk_forward_elo from elo_walkforward that the ATP validation
    uses — no special-casing for WTA.  The test set is year > train_year_max.
    Platt recalibration is also applied and reported.

    Returns
    -------
    dict with keys: n_total, n_test, year_min, year_max,
                    brier_raw, logloss_raw, ece_raw,
                    brier_recal, logloss_recal, ece_recal,
                    brier_delta, ece_delta
    """
    wf = _walk_forward_blend(wta_df, blend=blend)
    years = pd.to_datetime(wf["date"]).dt.year

    test_mask = years > train_year_max
    test = wf[test_mask].copy()

    if len(test) == 0:
        raise ValueError(f"No test rows with year > {train_year_max}")

    p_raw = test["win_prob_p1"].to_numpy(dtype=float)
    y     = (test["winner"] == 1).to_numpy(dtype=float)

    b_raw = brier(p_raw, y)
    ll_raw = logloss(p_raw, y)
    ec_raw = ece(p_raw, y)

    # Platt recalibration (leak-free: trained only on strictly-prior rows)
    recal_df = platt_recalibrate(wf, train_year_max=train_year_max)
    p_recal  = recal_df["win_prob_recal"].to_numpy(dtype=float)
    y_recal  = (recal_df["winner"] == 1).to_numpy(dtype=float)

    b_recal  = brier(p_recal, y_recal)
    ll_recal = logloss(p_recal, y_recal)
    ec_recal = ece(p_recal, y_recal)

    all_years = pd.to_datetime(wta_df["date"]).dt.year
    return {
        "n_total":       len(wta_df),
        "n_test":        len(test),
        "year_min":      int(all_years.min()),
        "year_max":      int(all_years.max()),
        "brier_raw":     b_raw,
        "logloss_raw":   ll_raw,
        "ece_raw":       ec_raw,
        "brier_recal":   b_recal,
        "logloss_recal": ll_recal,
        "ece_recal":     ec_recal,
        "brier_delta":   b_recal - b_raw,
        "ece_delta":     ec_recal - ec_raw,
    }


def load_wta_corpus(path: str | Path = WTA_OUT_PATH) -> pd.DataFrame:
    """Load wta_matches.parquet; returns DataFrame sorted chronologically."""
    df = pd.read_parquet(path)
    if "date" not in df.columns:
        return df
    df["_round_ord"] = df["round"].apply(_round_key)
    df = df.sort_values(
        ["date", "tour", "tourney_id", "_round_ord", "match_num"],
        kind="mergesort", na_position="last",
    ).reset_index(drop=True)
    return df.drop(columns=["_round_ord"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build + validate WTA Elo corpus")
    parser.add_argument("--raw-dir",  default=str(WTA_RAW_DIR))
    parser.add_argument("--out-path", default=str(WTA_OUT_PATH))
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year",   type=int, default=2025)
    parser.add_argument("--train-year-max", type=int, default=TRAIN_YEAR_MAX)
    parser.add_argument("--blend", type=float, default=0.3)
    args = parser.parse_args()

    print("Building WTA corpus …")
    wta_df = build_wta_corpus(
        raw_dir=args.raw_dir, out_path=args.out_path,
        start_year=args.start_year, end_year=args.end_year,
    )
    print(f"  {len(wta_df):,} matches  "
          f"({pd.to_datetime(wta_df['date']).dt.year.min()}–"
          f"{pd.to_datetime(wta_df['date']).dt.year.max()})")
    print(f"  Written to: {args.out_path}")

    print("\nValidating WTA Elo (walk-forward, leak-free) …")
    metrics = validate_wta_elo(wta_df, train_year_max=args.train_year_max, blend=args.blend)

    print(f"\n  Corpus: {metrics['n_total']:,} total | {metrics['n_test']:,} test "
          f"({args.train_year_max + 1}–{metrics['year_max']})")
    print(f"\n  {'Metric':<12}  {'Raw':>10}  {'Recal (Platt)':>14}")
    print(f"  {'Brier':<12}  {metrics['brier_raw']:>10.5f}  {metrics['brier_recal']:>14.5f}")
    print(f"  {'Logloss':<12}  {metrics['logloss_raw']:>10.5f}  {metrics['logloss_recal']:>14.5f}")
    print(f"  {'ECE':<12}  {metrics['ece_raw']:>10.5f}  {metrics['ece_recal']:>14.5f}")
    print(f"\n  Platt delta-Brier={metrics['brier_delta']:+.5f}  "
          f"delta-ECE={metrics['ece_delta']:+.5f}")

    print("\n  HONEST VERDICT:")
    raw_ok  = metrics["brier_raw"]  < 0.26
    recal_ok = metrics["brier_recal"] < 0.26
    verdict = ("WTA Elo is well-calibrated as a 2nd corpus"
               if raw_ok else "WTA Elo Brier elevated — calibration needs review")
    print(f"  {verdict}")
    print("  Accuracy/calibration only; no betting-edge claim.")


if __name__ == "__main__":
    _cli()
