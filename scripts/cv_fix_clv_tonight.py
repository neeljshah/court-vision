"""
cv_fix_clv_tonight.py — CLV expectation analysis for tonight's slate.

For tonight's Game 7 OKC@SAS (gid 0042500317, date 2026-05-30) this script:
  1. Loads our model's q50 projections from predictions_cache_2026-05-30.parquet
  2. Loads multi-book lines (fd, dk, bov, pin, betrivers) and computes the
     consensus (median) current line per player/stat
  3. Computes our "fair line" = q50 projection (the market-neutral implied line
     based purely on our model's median prediction)
  4. Computes book dispersion = max(lines) - min(lines) across books as a proxy
     for how "soft" / movable the line is (wide gap → books disagree → sharp
     money not yet fully priced in → more likely to move)
  5. Tries the CLV XGBoost model from src/prediction/clv_predictor.py; if
     unavailable (pkl not yet trained), falls back to a heuristic using
     our_edge and line trajectory from Pinnacle time-series data
  6. Emits data/cache/cv_fix/clv_tonight_2026-05-30.json and prints top bets

CLV signal labels:
  'we_are_early'    — model says OVER and line is likely to move up (our side),
                      OR model says UNDER and line is likely to move down
  'market_agrees'   — line already matches our model; limited residual value
  'no_edge'         — model has no meaningful edge vs current consensus line

Heuristic details (fallback when pkl absent):
  - our_edge = (our_fair_line - consensus_line) / consensus_line  [signed]
    positive = we project OVER, line is below our fair value
    negative = we project UNDER, line is above our fair value
  - pinnacle_delta = recent Pinnacle vig-drift relative to opening
    (juice toward OVER means sharp money on OVER → supports we_are_early for us
     if we also project OVER)
  - book_dispersion threshold: > 0.5 = soft line
  - we_are_early if: |our_edge| > 3% AND dispersion is soft AND Pinnacle
    trajectory consistent with our side (or no trajectory data available and
    edge is strong)
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PREDICTIONS_PARQUET = ROOT / "data" / "cache" / "predictions_cache_2026-05-30.parquet"
OUT_DIR = ROOT / "data" / "cache" / "cv_fix"
OUT_FILE = OUT_DIR / "clv_tonight_2026-05-30.json"

DATE = "2026-05-30"
GID = "0042500317"

# Books to load (standard column schema: player_name, stat, line, over_price,
# under_price). BOV has extra cols but we only need the five above.
BOOK_FILES: Dict[str, Path] = {
    "fd":        ROOT / "data" / "lines" / f"{DATE}_fd.csv",
    "dk":        ROOT / "data" / "lines" / f"{DATE}_dk.csv",
    "bov":       ROOT / "data" / "lines" / f"{DATE}_bov.csv",
    "pin":       ROOT / "data" / "lines" / f"{DATE}_pin.csv",
    "betrivers": ROOT / "data" / "lines" / f"{DATE}_betrivers.csv",
}

# Pinnacle file doubles as a time-series for trajectory analysis
PIN_TS_FILE = ROOT / "data" / "lines" / f"{DATE}_pin.csv"

# Stats tracked in predictions cache
TRACKED_STATS = {"pts", "reb", "ast", "fg3m", "stl", "blk", "tov"}

# Edge thresholds for signal labelling
EDGE_EARLY_MIN = 0.03       # |edge| > 3% → meaningful disagreement
EDGE_AGREES_MAX = 0.015     # |edge| < 1.5% → market already there
DISPERSION_SOFT = 0.5       # max-min across books > 0.5 = soft/movable


# ── helpers ───────────────────────────────────────────────────────────────────

def _american_to_prob(odds: float) -> float:
    """Convert American odds to no-vig implied probability (single side)."""
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def _read_book(path: Path, book_name: str) -> pd.DataFrame:
    """Read a book CSV robustly; returns empty DataFrame on failure."""
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, on_bad_lines="skip", low_memory=False)
    except Exception as exc:
        print(f"  [WARN] could not read {path.name}: {exc}")
        return pd.DataFrame()

    # BOV has 'is_alt_line' col — drop alt lines to keep main lines only
    if "is_alt_line" in df.columns:
        df = df[df["is_alt_line"].astype(str).str.lower() != "true"].copy()

    needed = {"player_name", "stat", "line", "over_price", "under_price"}
    if not needed.issubset(df.columns):
        return pd.DataFrame()

    df = df[list(needed)].copy()
    df["book"] = book_name
    df["line"] = pd.to_numeric(df["line"], errors="coerce")
    df["over_price"] = pd.to_numeric(df["over_price"], errors="coerce")
    df["under_price"] = pd.to_numeric(df["under_price"], errors="coerce")
    df = df.dropna(subset=["line"])
    df["stat"] = df["stat"].str.lower().str.strip()

    # Normalise player names: strip whitespace
    df["player_name"] = df["player_name"].str.strip()

    return df


def _build_consensus(book_dfs: List[pd.DataFrame]) -> pd.DataFrame:
    """
    Stack all book lines; for each (player_name, stat) compute:
      - consensus_line  : median line across books
      - max_line, min_line
      - book_dispersion : max - min
      - n_books         : how many books offered this prop
      - latest_over_price, latest_under_price (from Pinnacle if present, else first)
    """
    if not book_dfs:
        return pd.DataFrame()

    all_df = pd.concat(book_dfs, ignore_index=True)
    all_df = all_df[all_df["stat"].isin(TRACKED_STATS)]

    # Keep one row per (player, stat, book) — take the last captured (highest
    # line if same-book duplicates exist, which pin has at the same timestamp)
    grp = all_df.groupby(["player_name", "stat", "book"], sort=False)
    # For the same player/stat/book pick the row whose line is the median
    def _pick_main(sub: pd.DataFrame) -> pd.Series:
        med = sub["line"].median()
        idx = (sub["line"] - med).abs().idxmin()
        return sub.loc[idx]

    deduped = grp.apply(_pick_main).reset_index(drop=True)

    # Consensus aggregation
    agg = (
        deduped.groupby(["player_name", "stat"])
        .agg(
            consensus_line=("line", "median"),
            max_line=("line", "max"),
            min_line=("line", "min"),
            n_books=("book", "nunique"),
        )
        .reset_index()
    )
    agg["book_dispersion"] = agg["max_line"] - agg["min_line"]

    # Attach Pinnacle's most-recent over/under price for edge calculation
    pin_rows = deduped[deduped["book"] == "pin"][
        ["player_name", "stat", "over_price", "under_price"]
    ].copy()
    agg = agg.merge(pin_rows, on=["player_name", "stat"], how="left")

    return agg


def _build_pinnacle_trajectory(pin_ts_path: Path) -> pd.DataFrame:
    """
    From the Pinnacle time-series CSV compute, per (player_name, stat):
      - open_vig_over  : implied prob at first timestamp
      - latest_vig_over: implied prob at last timestamp
      - pin_delta      : latest_vig_over - open_vig_over
                         positive → money flowing to OVER (books pricing it higher)
                         negative → money flowing to UNDER
    Returns empty DataFrame if file missing.
    """
    if not pin_ts_path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(pin_ts_path, low_memory=False)
    except Exception:
        return pd.DataFrame()

    needed = {"captured_at", "player_name", "stat", "over_price", "under_price"}
    if not needed.issubset(df.columns):
        return pd.DataFrame()

    df["stat"] = df["stat"].str.lower().str.strip()
    df = df[df["stat"].isin(TRACKED_STATS)].copy()
    df["over_price"] = pd.to_numeric(df["over_price"], errors="coerce")
    df["under_price"] = pd.to_numeric(df["under_price"], errors="coerce")
    df["player_name"] = df["player_name"].str.strip()
    df = df.dropna(subset=["over_price", "under_price"])
    df["captured_at"] = pd.to_datetime(df["captured_at"], errors="coerce", utc=True)
    df = df.dropna(subset=["captured_at"])
    df = df.sort_values("captured_at")

    def _vig_over(over_p: float, under_p: float) -> float:
        p_over  = _american_to_prob(over_p)
        p_under = _american_to_prob(under_p)
        total   = p_over + p_under
        if total <= 0:
            return 0.5
        return p_over / total   # no-vig over prob

    records = []
    for (player, stat), sub in df.groupby(["player_name", "stat"], sort=False):
        if len(sub) < 2:
            continue
        first = sub.iloc[0]
        last  = sub.iloc[-1]
        v_open   = _vig_over(first["over_price"], first["under_price"])
        v_latest = _vig_over(last["over_price"], last["under_price"])
        records.append({
            "player_name": player,
            "stat":        stat,
            "pin_delta":   round(v_latest - v_open, 4),
            "n_pin_ticks": len(sub),
        })

    return pd.DataFrame(records) if records else pd.DataFrame()


def _load_predictions() -> pd.DataFrame:
    """Load q50 projections from today's predictions cache."""
    if not PREDICTIONS_PARQUET.exists():
        print(f"[ERROR] predictions cache missing: {PREDICTIONS_PARQUET}")
        return pd.DataFrame()
    df = pd.read_parquet(PREDICTIONS_PARQUET)
    df["stat"] = df["stat"].str.lower().str.strip()
    df["player_name"] = df["player_name"].str.strip()
    return df[["player_name", "stat", "q50"]].rename(columns={"q50": "our_fair_line"})


def _try_clv_model(
    our_edge: float,
    pin_delta: float,
    book_dispersion: float,
) -> Optional[float]:
    """
    Attempt to call src/prediction/clv_predictor.predict_clv_prob().
    Returns P(closing line moves our way) in [0,1], or None if model unavailable.

    Features mapped:
      our_edge              → our_edge
      pin_delta             → pinnacle_delta   (Pinnacle vig drift, proxy)
      book_dispersion       → public_pct       (soft market ≈ high public %, rough proxy)
      0.0                   → time_to_game     (unknown live)
      1.0                   → lineup_freshness (unknown live, assume fresh)
      pin_delta             → line_movement_last_2h
    """
    try:
        from src.prediction.clv_predictor import predict_clv_prob
        features = {
            "our_edge":             our_edge,
            "pinnacle_delta":       pin_delta,
            "public_pct":           min(book_dispersion, 1.0),
            "time_to_game":         0.0,
            "lineup_freshness":     1.0,
            "line_movement_last_2h": pin_delta,
        }
        return predict_clv_prob(features)
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _classify_signal(
    our_edge: float,
    book_dispersion: float,
    pin_delta: float,
    clv_prob: Optional[float],
) -> str:
    """
    Classify CLV signal:
      - If XGB model returned a probability, use it:
          clv_prob >= 0.55 → 'we_are_early'
          clv_prob <= 0.45 → 'no_edge'
          else             → 'market_agrees'
      - Heuristic fallback:
          |our_edge| > EDGE_EARLY_MIN AND (dispersion soft OR pin_delta consistent)
              → 'we_are_early'
          |our_edge| < EDGE_AGREES_MAX → 'market_agrees'
          else → 'no_edge'
    """
    if clv_prob is not None:
        if clv_prob >= 0.55:
            return "we_are_early"
        if clv_prob <= 0.45:
            return "no_edge"
        return "market_agrees"

    # Heuristic
    edge_abs = abs(our_edge)
    if edge_abs < EDGE_AGREES_MAX:
        return "market_agrees"

    soft_market = book_dispersion > DISPERSION_SOFT
    # pin_delta consistent with our side:
    #   our_edge > 0 (we project over) → want pin_delta > 0 (sharp over money)
    #   our_edge < 0 (we project under) → want pin_delta < 0 (sharp under money)
    pin_consistent = (our_edge > 0 and pin_delta >= 0) or \
                     (our_edge < 0 and pin_delta <= 0)

    if edge_abs > EDGE_EARLY_MIN and (soft_market or pin_consistent):
        return "we_are_early"

    return "no_edge"


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"=== CLV Tonight: {DATE} — Game 7 OKC@SAS ({GID}) ===\n")

    # 1. Load projections
    pred_df = _load_predictions()
    if pred_df.empty:
        print("[FATAL] No projection data — cannot proceed.")
        return
    print(f"  Projections loaded: {len(pred_df)} player/stat rows")

    # 2. Load book lines
    book_dfs: List[pd.DataFrame] = []
    for book, path in BOOK_FILES.items():
        df = _read_book(path, book)
        if not df.empty:
            print(f"  {book:12s}: {len(df)} rows")
            book_dfs.append(df)
        else:
            print(f"  {book:12s}: MISSING or empty — skipped")

    consensus_df = _build_consensus(book_dfs)
    if consensus_df.empty:
        print("[FATAL] No consensus lines built — cannot proceed.")
        return
    print(f"\n  Consensus lines: {len(consensus_df)} player/stat pairs")

    # 3. Load Pinnacle time-series trajectory
    traj_df = _build_pinnacle_trajectory(PIN_TS_FILE)
    if not traj_df.empty:
        print(f"  Pinnacle trajectory: {len(traj_df)} player/stat series")
    else:
        print("  Pinnacle trajectory: unavailable (using pin_delta=0.0)")

    # 4. Merge everything
    merged = pred_df.merge(consensus_df, on=["player_name", "stat"], how="inner")
    if not traj_df.empty:
        merged = merged.merge(
            traj_df[["player_name", "stat", "pin_delta"]],
            on=["player_name", "stat"],
            how="left",
        )
    if "pin_delta" not in merged.columns:
        merged["pin_delta"] = 0.0
    merged["pin_delta"] = merged["pin_delta"].fillna(0.0)

    print(f"  Merged rows: {len(merged)}\n")

    # 5. Compute our_edge and signals
    # our_edge = (our_fair_line - consensus_line) / consensus_line
    # (+) → we project more than the market line (favour OVER)
    # (−) → we project less than the market line (favour UNDER)
    merged["our_edge"] = np.where(
        merged["consensus_line"] > 0,
        (merged["our_fair_line"] - merged["consensus_line"]) / merged["consensus_line"],
        0.0,
    )

    # Attempt CLV model (will be None for most rows if pkl missing)
    clv_prob_col = []
    for _, row in merged.iterrows():
        prob = _try_clv_model(
            our_edge=float(row["our_edge"]),
            pin_delta=float(row["pin_delta"]),
            book_dispersion=float(row["book_dispersion"]),
        )
        clv_prob_col.append(prob)
    merged["clv_prob"] = clv_prob_col

    model_used = "xgb_clv" if any(p is not None for p in clv_prob_col) else "heuristic"
    print(f"  CLV model: {model_used}")

    merged["clv_signal"] = merged.apply(
        lambda r: _classify_signal(
            our_edge=r["our_edge"],
            book_dispersion=r["book_dispersion"],
            pin_delta=r["pin_delta"],
            clv_prob=r["clv_prob"],
        ),
        axis=1,
    )

    # 6. Build output JSON
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    output: Dict = {}
    for _, row in merged.iterrows():
        player_key = row["player_name"].lower().replace(" ", "_").replace("'", "")
        stat_key   = row["stat"]

        if player_key not in output:
            output[player_key] = {}

        entry: Dict = {
            "our_fair_line":   round(float(row["our_fair_line"]), 3),
            "current_line":    round(float(row["consensus_line"]), 2),
            "our_edge_pct":    round(float(row["our_edge"]) * 100, 2),
            "book_dispersion": round(float(row["book_dispersion"]), 2),
            "n_books":         int(row["n_books"]),
            "pin_delta":       round(float(row["pin_delta"]), 4),
            "clv_signal":      row["clv_signal"],
        }
        if row["clv_prob"] is not None:
            entry["clv_prob"] = round(float(row["clv_prob"]), 4)

        output[player_key][stat_key] = entry

    with open(OUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Output written: {OUT_FILE}\n")

    # 7. Print top 'we_are_early' bets ranked by |our_edge|
    early = merged[merged["clv_signal"] == "we_are_early"].copy()
    early["abs_edge"] = early["our_edge"].abs()
    early = early.sort_values("abs_edge", ascending=False)

    # For the display, split into:
    #   "quality" = both fair line and consensus line are >= 1.0
    #               (avoids near-zero props where edge% is degenerate)
    #   "zero_proj" = our fair < 1.0 (model predicts essentially 0 for blk/stl
    #                  alt lines — still logged in JSON but noted separately)
    early_quality = early[
        (early["our_fair_line"] >= 1.0) & (early["consensus_line"] >= 1.0)
    ]
    early_zero = early[
        (early["our_fair_line"] < 1.0) | (early["consensus_line"] < 1.0)
    ]

    print("=" * 68)
    print("  TOP 'we_are_early' BETS — QUALITY (fair >= 1.0 & mkt >= 1.0)")
    print("=" * 68)
    if early_quality.empty:
        print("  (none found)")
    else:
        fmt = "  {:<30s} {:>5s}  fair={:>6.2f}  mkt={:>6.2f}  edge={:>+6.1f}%  disp={:.2f}  pin_delta={:+.3f}"
        for _, r in early_quality.iterrows():
            side = "OVER" if r["our_edge"] > 0 else "UNDER"
            print(fmt.format(
                f"{r['player_name']} {r['stat'].upper()}",
                side,
                r["our_fair_line"],
                r["consensus_line"],
                r["our_edge"] * 100,
                r["book_dispersion"],
                r["pin_delta"],
            ))

    print()
    print(f"  (plus {len(early_zero)} near-zero projection props in JSON — blk/stl alt lines)")
    print(f"  (zero-projection rows still labelled 'we_are_early' in JSON but use caution)")

    print()
    print("=" * 68)
    print("  SIGNAL SUMMARY")
    print("=" * 68)
    counts = merged["clv_signal"].value_counts()
    for sig, cnt in counts.items():
        print(f"  {sig:<20s}: {cnt}")

    print()
    print(f"  CLV model used : {model_used}")
    print(f"  Output file    : {OUT_FILE}")


if __name__ == "__main__":
    main()
