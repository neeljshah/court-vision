"""domains.mlb.matchup.platoon_context -- the FINER, pitch-type-level platoon
layer. domains/mlb/platoon_split_index.py already ships a per-batter,
hand-only (p_throws) platoon_delta descriptive index -- this module does NOT
duplicate it. It adds the layer that index lacks: within a batter's (or
pitcher's) qualifying hand-cell, the breakdown BY PITCH TYPE (e.g. "this lefty
mashes fastballs from RHP but chases sliders from RHP").

FLOOR (per LANE spec, matches platoon_split_index.py's MIN_PA_PER_HAND):
a batter must have >=100 PA against a given p_throws hand (summed across ALL
pitch types) before that (batter, hand) cell's pitch-type breakdown ships --
same floor discipline, just gating a finer breakdown instead of a single
delta. Symmetric floor for pitchers vs batter stand.

WINDOW: seasons 2022+2023 (statcast_fuller__2022/2023.parquet -- full
seasons, see pitch_mix_profiles.py CORPUS LIMIT note re: the 2022/2023 files
being full-season now, not the 18-day sample platoon_split_index.py's
docstring describes).

METRICS per (entity, hand, pitch_type) cell: n_pa, on_base_rate, k_rate.
No whiff metric here -- same per-pitch swing/take gap documented in
pitch_mix_profiles.py; on_base_rate/k_rate are outcome-of-terminal-pitch
rates, not swing rates.

NETWORK: zero. DESCRIPTIVE ONLY -- NO MARKET/$ EDGE CLAIMED.

CLI: python -m domains.mlb.matchup.platoon_context
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATCAST = {
    2022: _REPO_ROOT / "data" / "cache" / "statcast" / "statcast_fuller__2022.parquet",
    2023: _REPO_ROOT / "data" / "cache" / "statcast" / "statcast_fuller__2023.parquet",
}
_OUT_DIR = _REPO_ROOT / "data" / "domains" / "mlb" / "matchup"
_BATTER_OUT = _OUT_DIR / "batter_platoon_pitch.parquet"
_PITCHER_OUT = _OUT_DIR / "pitcher_platoon_pitch.parquet"
_REPORT_OUT = _OUT_DIR / "platoon_context_report.json"

SEASONS = (2022, 2023)
MIN_PA_PER_HAND = 100  # per LANE spec: min_sample >= 100 PA per (entity, hand) cell
_K_EVENTS = {"strikeout", "strikeout_double_play"}
_ON_BASE_EVENTS = {"single", "double", "triple", "home_run", "walk", "intent_walk", "hit_by_pitch"}
_COLS = ["batter", "pitcher", "stand", "p_throws", "pitch_type", "events"]


def load_pa_rows(seasons: tuple = SEASONS) -> pd.DataFrame:
    frames = []
    for season in seasons:
        df = pd.read_parquet(_STATCAST[season], columns=_COLS)
        df["season"] = season
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    pa_rows = combined[combined["events"].notna()].copy()
    pa_rows = pa_rows[pa_rows["pitch_type"].notna() & (pa_rows["pitch_type"] != "None")]
    pa_rows["on_base"] = pa_rows["events"].isin(_ON_BASE_EVENTS).astype(int)
    pa_rows["is_k"] = pa_rows["events"].isin(_K_EVENTS).astype(int)
    return pa_rows


def _fine_platoon(pa_rows: pd.DataFrame, entity_col: str, hand_col: str,
                   min_pa_per_hand: int) -> tuple[pd.DataFrame, dict]:
    """Shared shape for both directions: floor on the (entity, hand) marginal,
    then break the qualifying cells down by pitch_type."""
    marginal = pa_rows.groupby([entity_col, hand_col]).size().rename("n_pa_hand").reset_index()
    n_considered = len(marginal)
    qualifying_cells = marginal[marginal["n_pa_hand"] >= min_pa_per_hand][[entity_col, hand_col]]
    n_qualifying = len(qualifying_cells)

    fine = pa_rows.merge(qualifying_cells, on=[entity_col, hand_col])
    fine_agg = fine.groupby([entity_col, hand_col, "pitch_type"]).agg(
        n_pa=("events", "size"),
        n_on_base=("on_base", "sum"),
        n_k=("is_k", "sum"),
    ).reset_index()
    fine_agg["on_base_rate"] = fine_agg["n_on_base"] / fine_agg["n_pa"]
    fine_agg["k_rate"] = fine_agg["n_k"] / fine_agg["n_pa"]

    report = {
        "entity_col": entity_col,
        "hand_col": hand_col,
        "min_pa_per_hand_floor": min_pa_per_hand,
        "n_hand_cells_considered": n_considered,
        "n_hand_cells_qualifying": n_qualifying,
        "n_hand_cells_excluded_below_floor": n_considered - n_qualifying,
        "n_fine_rows": int(len(fine_agg)),
    }
    return fine_agg, report


def build_batter_platoon_pitch(pa_rows: Optional[pd.DataFrame] = None,
                                min_pa_per_hand: int = MIN_PA_PER_HAND) -> tuple[pd.DataFrame, dict]:
    if pa_rows is None:
        pa_rows = load_pa_rows()
    return _fine_platoon(pa_rows, "batter", "p_throws", min_pa_per_hand)


def build_pitcher_platoon_pitch(pa_rows: Optional[pd.DataFrame] = None,
                                 min_pa_per_hand: int = MIN_PA_PER_HAND) -> tuple[pd.DataFrame, dict]:
    if pa_rows is None:
        pa_rows = load_pa_rows()
    return _fine_platoon(pa_rows, "pitcher", "stand", min_pa_per_hand)


def write_context(batter_fine: pd.DataFrame, pitcher_fine: pd.DataFrame,
                   batter_report: dict, pitcher_report: dict) -> dict:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(batter_fine, preserve_index=False), _BATTER_OUT)
    pq.write_table(pa.Table.from_pandas(pitcher_fine, preserve_index=False), _PITCHER_OUT)

    report = {
        "component": "platoon_context",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "seasons": list(SEASONS),
        "batter_by_p_throws": batter_report,
        "pitcher_by_stand": pitcher_report,
        "descriptive_only": True,
        "edge_claimed": False,
    }
    with open(_REPORT_OUT, "w", encoding="ascii", errors="strict") as f:
        json.dump(report, f, indent=2)
    return report


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Build MLB pitch-type-level platoon context")
    parser.parse_args(argv)

    pa_rows = load_pa_rows()
    batter_fine, batter_report = build_batter_platoon_pitch(pa_rows)
    pitcher_fine, pitcher_report = build_pitcher_platoon_pitch(pa_rows)
    report = write_context(batter_fine, pitcher_fine, batter_report, pitcher_report)

    print(f"batter(p_throws) hand-cells: qualifying={batter_report['n_hand_cells_qualifying']}"
          f"/{batter_report['n_hand_cells_considered']} fine_rows={batter_report['n_fine_rows']}")
    print(f"pitcher(stand) hand-cells: qualifying={pitcher_report['n_hand_cells_qualifying']}"
          f"/{pitcher_report['n_hand_cells_considered']} fine_rows={pitcher_report['n_fine_rows']}")
    print(f"wrote -> {_BATTER_OUT}")
    print(f"wrote -> {_PITCHER_OUT}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
