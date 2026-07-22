"""scripts.platformkit.analytics_showcase.comeback_atlas -- lead x time atlas
of model vs market vs realized win rate, from the existing NBA state-bucket
reliability map (calibration_grid.nba_grid output). Calibration measurement
only, never a $/ROI/edge claim.

Source: data/cache/calibration_grid/nba_reliability_map.json (built by
`python -m scripts.platformkit.calibration_grid.nba_grid`), which already
buckets every traded in-play tick by calibration_grid.buckets.nba_bucket
(lead-magnitude band x time-remaining band) and prices a sample through the
sanctioned winprob_dispatch resolver. This script only reshapes those
buckets into a 2D (lead x time) grid and renders it -- it computes nothing
new off raw ticks.

n>=30 games mask (MIN_GAMES gate, same threshold nba_grid.py already applies
via can_price): buckets below it are masked out of the heatmap and excluded
from headline numbers, never silently dropped from the JSON.

CLI: python -m scripts.platformkit.analytics_showcase.comeback_atlas
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RELIABILITY_MAP = _REPO_ROOT / "data" / "cache" / "calibration_grid" / "nba_reliability_map.json"
_OUT_JSON = Path(__file__).resolve().parent / "out" / "comeback_atlas.json"
_OUT_PNG = _REPO_ROOT / "docs" / "img" / "comeback_atlas.png"

MIN_GAMES = 30  # same gate nba_grid.py applies for can_price

# axis order matches buckets._LEAD_MAG_BANDS / _REM_BANDS (ascending)
_LEAD_ORDER = ["lead_00", "lead_+01_05", "lead_+05_10", "lead_+10_15", "lead_+15_20",
               "lead_+20_30", "lead_+30_99",
               "lead_-01_05", "lead_-05_10", "lead_-10_15", "lead_-15_20",
               "lead_-20_30", "lead_-30_99"]
_TIME_ORDER = ["rem_00_02", "rem_02_05", "rem_05_12", "rem_12_24", "rem_24_36", "rem_36_99", "ot"]

_NOVELTY = {
    "verdict": "INCREMENTAL",
    "closest_prior_work": (
        "arXiv 2606.07811 (~Jun 2026), 'When Do Markets Fully Process Public "
        "Information? Evidence from Real-Time Prediction Markets' -- Kalshi/NBA "
        "contract-minute join of market price, a state-only model, and terminal "
        "outcome; measures how fully the market has absorbed realized game state."),
    "how_ours_differs": (
        "Same three-way (model, market, outcome) join, reshaped into a 2D lead x "
        "time-remaining atlas instead of a single time-checkpoint curve, off our "
        "own held reliability-map corpus (nba_checkpoints_full.parquet via "
        "calibration_grid.nba_grid). Not a new method -- do not claim first-ever."),
}


def _parse_bucket(key: str) -> Optional[tuple]:
    parts = key.split("|")
    lead = parts[0]
    time_part = "ot" if len(parts) > 1 and parts[1] == "ot" else parts[1]
    if lead not in _LEAD_ORDER or time_part not in _TIME_ORDER:
        return None
    return lead, time_part


def build_atlas(reliability_map_path: Optional[Path] = None) -> Dict[str, Any]:
    path = reliability_map_path or _RELIABILITY_MAP
    try:
        src = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 -- fail closed with reason, never crash
        return {"edge_claimed": False, "status": "no_data",
                "note": f"reliability map unreadable at {path}: {exc}"}

    cells: List[Dict[str, Any]] = []
    n_masked = 0
    for bkt_key, row in src.get("buckets", {}).items():
        axes = _parse_bucket(bkt_key)
        if axes is None:
            continue
        lead_label, time_label = axes
        n_games = row.get("n_games", 0)
        masked = n_games < MIN_GAMES
        if masked:
            n_masked += 1
        cell = {
            "bucket": bkt_key, "lead_band": lead_label, "time_band": time_label,
            "n_games": n_games, "n_ticks": row.get("n_ticks"),
            "model_mean_prob": row.get("model_mean_prob"),
            "market_mean_prob": row.get("market_mean_prob"),
            "outcome_rate": row.get("outcome_rate"),
            "model_market_gap": (
                round(row["model_mean_prob"] - row["market_mean_prob"], 4)
                if row.get("model_mean_prob") is not None else None),
            "can_price": row.get("can_price"),
            "masked_n_lt_30": masked,
        }
        cells.append(cell)

    unmasked = [c for c in cells if not c["masked_n_lt_30"]]
    priced = [c for c in unmasked if c["model_market_gap"] is not None]
    worst = sorted(priced, key=lambda c: abs(c["model_market_gap"]), reverse=True)[:5]

    return {
        "edge_claimed": False,
        "source": str(path.relative_to(_REPO_ROOT)) if path.is_absolute() else str(path),
        "source_honest_note": src.get("honest_note"),
        "n_buckets_total": len(cells),
        "n_buckets_masked_n_lt_30": n_masked,
        "n_buckets_unmasked": len(unmasked),
        "mask_rule": f"bucket excluded from headline/heatmap when n_games < {MIN_GAMES} "
                     "(same gate nba_grid.py's can_price uses); still listed in cells "
                     "with masked_n_lt_30=true, never silently dropped.",
        "cells": cells,
        "worst_model_market_gap_unmasked": worst,
        "novelty": _NOVELTY,
        "story": (
            "Reliability map reshaped into a lead x time-remaining grid: %d state buckets, "
            "%d below the n>=30-games mask. This is a calibration atlas (model vs market vs "
            "realized frequency by game state), not an edge/ROI claim." % (len(cells), n_masked)
        ),
    }


def _render_png(atlas: Dict[str, Any], out_path: Path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False

    leads = _LEAD_ORDER
    times = _TIME_ORDER
    grid = np.full((len(leads), len(times)), np.nan)
    mask_grid = np.zeros((len(leads), len(times)), dtype=bool)
    by_pos = {(c["lead_band"], c["time_band"]): c for c in atlas["cells"]}
    for i, lead in enumerate(leads):
        for j, t in enumerate(times):
            c = by_pos.get((lead, t))
            if c is None:
                mask_grid[i, j] = True
                continue
            if c["masked_n_lt_30"] or c["model_market_gap"] is None:
                mask_grid[i, j] = True
                continue
            grid[i, j] = c["model_market_gap"]

    masked_grid = np.ma.masked_array(grid, mask=mask_grid | np.isnan(grid))
    fig, ax = plt.subplots(figsize=(9, 8))
    vmax = np.nanmax(np.abs(masked_grid)) if masked_grid.count() else 0.1
    im = ax.imshow(masked_grid, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(times))); ax.set_xticklabels(times, rotation=45, ha="right")
    ax.set_yticks(range(len(leads))); ax.set_yticklabels(leads)
    ax.set_xlabel("time-remaining band"); ax.set_ylabel("home-lead band")
    ax.set_title("Comeback atlas: model - market prob gap by (lead, time)\n"
                  "gray = masked (n_games < %d) | calibration measurement, not edge" % MIN_GAMES)
    for i in range(len(leads)):
        for j in range(len(times)):
            if mask_grid[i, j]:
                ax.add_patch(plt.Rectangle((j - .5, i - .5), 1, 1, color="0.85"))
    fig.colorbar(im, ax=ax, label="model_mean_prob - market_mean_prob")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return True


def main() -> int:
    atlas = build_atlas()
    _OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    _OUT_JSON.write_text(json.dumps(atlas, indent=2, ensure_ascii=True), encoding="utf-8")
    png_ok = _render_png(atlas, _OUT_PNG) if "cells" in atlas else False
    print(json.dumps({
        "json_out": str(_OUT_JSON), "png_out": str(_OUT_PNG) if png_ok else None,
        "n_buckets_total": atlas.get("n_buckets_total"),
        "n_buckets_masked_n_lt_30": atlas.get("n_buckets_masked_n_lt_30"),
        "story": atlas.get("story"),
    }, indent=2, ensure_ascii=True))
    return 0


def check() -> int:
    assert _OUT_JSON.exists() and _OUT_JSON.stat().st_size > 0, _OUT_JSON
    assert _OUT_PNG.exists() and _OUT_PNG.stat().st_size > 0, _OUT_PNG
    print("OK: comeback_atlas self-check passed")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(check() if "--check" in sys.argv else main())
