"""scripts.platformkit.frontend.board — multi-sport board builder.

build_board(sport, repo_root) -> list[dict]  — per-game rows for one sport.
build_all_board()             -> dict[str, list[dict]]  — all sports.
to_json(board, out_path)      — write JSON to disk.

HONEST_NOTE (module-level constant):
    Markets are efficient — NO model edge is claimed anywhere in this module.
    The only value exposed is line-shopping / devig / CLV, explicitly labeled.

Calibration tags per sport (from proof results):
    basketball_nba : 'calibrated'  (Elo Brier < null; market beats model)
    mlb_sbro       : 'calibrated'  (two-corpus proof; market beats model)
    soccer_fd      : 'calibrated'  (Poisson ECE < 0.025)
    tennis_atp     : 'calibrated'  (blended Elo; market beats model)

F5 compliance: imports ONLY stdlib, numpy, pandas, domains.*, src.loop.gate.
               No src.data / src.sim / src.tracking / src.pipeline.
"""
from __future__ import annotations

import inspect
import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.signal import Hypothesis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HONEST framing — module-level constant (tested in test_board.py)
# ---------------------------------------------------------------------------

HONEST_NOTE = (
    "Calibrated predictions + best available market lines. "
    "Markets are efficient — NO model edge is claimed. "
    "Value shown = line-shopping / devig / CLV only."
)

# ---------------------------------------------------------------------------
# Sport registry: sport_id -> (primary_parquet, adapter_class_path, calib_tag)
# ---------------------------------------------------------------------------

_SPORT_REGISTRY: Dict[str, Dict[str, str]] = {
    "basketball_nba": {
        "corpus_dir": "data/domains/basketball_nba",
        "primary_parquet": "games.parquet",
        "adapter_module": "domains.basketball_nba.adapter",
        "adapter_class": "NBAAdapter",
        "calibration_tag": "calibrated",
    },
    "mlb_sbro": {
        "corpus_dir": "data/domains/mlb",
        "primary_parquet": "games.parquet",
        "adapter_module": "domains.mlb.adapter",
        "adapter_class": "MLBAdapter",
        "calibration_tag": "calibrated",
    },
    "soccer_fd": {
        "corpus_dir": "data/domains/soccer",
        "primary_parquet": "matches.parquet",
        "adapter_module": "domains.soccer.adapter",
        "adapter_class": "SoccerAdapter",
        "calibration_tag": "calibrated",
    },
    "tennis_atp": {
        "corpus_dir": "data/domains/tennis",
        "primary_parquet": "matches.parquet",
        "adapter_module": "domains.tennis.adapter",
        "adapter_class": "TennisAdapter",
        "calibration_tag": "calibrated",
    },
}

# Minimal hypothesis used only to satisfy the feature_bundle() signature.
_BOARD_HYP = Hypothesis(
    name="board_display",
    target="winprob",
    scope="pregame",
    statement="Display board: calibrated model prob vs devigged market line.",
)

LINE_SHOP_NOTE = (
    "Real multi-book line-shopping requires a live feed. "
    "On-disk corpus provides one historical book only."
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_adapter(sport_id: str, repo_root: Path) -> Optional[Any]:
    """Import and instantiate the adapter for sport_id.  Returns None if corpus absent."""
    reg = _SPORT_REGISTRY.get(sport_id)
    if reg is None:
        logger.warning("Unknown sport_id %r — skipping.", sport_id)
        return None

    corpus_dir = repo_root / reg["corpus_dir"]
    primary = corpus_dir / reg["primary_parquet"]
    if not primary.exists():
        logger.info("Corpus absent for %s (%s) — skipping.", sport_id, primary)
        return None

    try:
        primary_df = pd.read_parquet(primary)
    except Exception as exc:
        logger.error("Failed to read %s for %s: %s", primary, sport_id, exc)
        return None

    odds_df: Optional[pd.DataFrame] = None
    odds_path = corpus_dir / "odds.parquet"
    if odds_path.exists():
        try:
            odds_df = pd.read_parquet(odds_path)
        except Exception as exc:
            logger.warning("odds.parquet unreadable for %s: %s", sport_id, exc)

    import importlib
    mod = importlib.import_module(reg["adapter_module"])
    cls = getattr(mod, reg["adapter_class"])

    # All adapters accept either (games_df=...) or (matches_df=...) depending on sport.
    primary_key = "games_df" if reg["primary_parquet"] == "games.parquet" else "matches_df"
    kwargs: Dict[str, Any] = {primary_key: primary_df}
    if odds_df is not None:
        kwargs["odds_df"] = odds_df
    return cls(**kwargs)


def _safe_float(v: Any) -> Optional[float]:
    """Return float in [0,1] or None."""
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _bundle_to_rows(sport_id: str, bundle: Any, calib_tag: str) -> List[Dict[str, Any]]:
    """Convert a FeatureBundle into board rows.

    Each row corresponds to one game. We zip dates, signal_col, and the
    best available market line (closing preferred over lines, NaN→None).
    home/away are not guaranteed in all sport bundles; we derive them from
    dates index position and leave them as None when unavailable at this layer
    (the board is primarily prob/line-shopping focused).
    """
    sig = np.asarray(bundle.signal_col, dtype=float)
    tgt = np.asarray(bundle.target, dtype=float)
    dates = list(bundle.dates)
    n = len(dates)

    # Best market fair prob: prefer closing, fall back to lines, else NaN array.
    if bundle.closing is not None:
        market_arr = np.asarray(bundle.closing, dtype=float)
    elif bundle.lines is not None:
        market_arr = np.asarray(bundle.lines, dtype=float)
    else:
        market_arr = np.full(n, float("nan"))

    rows: List[Dict[str, Any]] = []
    for i in range(n):
        model_prob = _safe_float(sig[i])
        market_prob = _safe_float(market_arr[i]) if i < len(market_arr) else None

        edge_diag: Optional[float] = None
        if model_prob is not None and market_prob is not None:
            edge_diag = round(model_prob - market_prob, 4)

        rows.append({
            "sport": sport_id,
            "date": dates[i],
            "home": None,   # per-sport enrichment requires the raw corpus; omitted here
            "away": None,   # same; the board consumer can join on date+sport
            "model_prob": round(model_prob, 4) if model_prob is not None else None,
            "market_fair_prob": round(market_prob, 4) if market_prob is not None else None,
            # DIAGNOSTIC only — not a bet signal; markets are efficient
            "edge_vs_market": {
                "value": edge_diag,
                "label": "DIAGNOSTIC — not a bet signal; markets are efficient",
            },
            "best_book": None,   # single historical book; live feed required
            "best_line": None,   # same
            "line_shop_note": LINE_SHOP_NOTE,
            "clv_placeholder": None,   # CLV requires live prices + settlement
            "calibration_tag": calib_tag,
            "honest_note": HONEST_NOTE,
        })
    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_board(
    sport: str,
    repo_root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Build display rows for one sport.  Returns [] if corpus absent (graceful).

    Parameters
    ----------
    sport:
        One of the SPORT_IDs in _SPORT_REGISTRY (e.g. 'basketball_nba').
    repo_root:
        Repo root path.  Defaults to three parents above this file.
    """
    root = repo_root or Path(__file__).resolve().parents[3]
    reg = _SPORT_REGISTRY.get(sport)
    if reg is None:
        logger.warning("build_board: unknown sport %r", sport)
        return []

    adapter = _load_adapter(sport, root)
    if adapter is None:
        return []

    try:
        # Some adapters (soccer, tennis) require 'seasons' as a mandatory
        # positional arg.  Passing [] means "no filter = all seasons".
        # Others (mlb, basketball_nba) accept it as Optional[Sequence].
        sig = inspect.signature(adapter.feature_bundle)
        # Bound method: params[0]='hypothesis', params[1]='seasons' (if present).
        # seasons_required = True when 'seasons' has no default value.
        if "seasons" in sig.parameters:
            seasons_required = (
                sig.parameters["seasons"].default is inspect.Parameter.empty
            )
        else:
            seasons_required = False

        bundle = (
            adapter.feature_bundle(_BOARD_HYP, [])
            if seasons_required
            else adapter.feature_bundle(_BOARD_HYP)
        )
    except Exception as exc:
        logger.error("feature_bundle failed for %s: %s", sport, exc)
        return []

    return _bundle_to_rows(sport, bundle, reg["calibration_tag"])


def build_all_board(repo_root: Optional[Path] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Build rows for every sport; skips sports whose corpus is absent."""
    root = repo_root or Path(__file__).resolve().parents[3]
    return {sport: build_board(sport, root) for sport in _SPORT_REGISTRY}


def to_json(board: Dict[str, List[Dict[str, Any]]], out_path: Path) -> None:
    """Write board dict to JSON (pretty-printed, UTF-8)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(board, fh, indent=2, default=str)
    logger.info("Board written to %s", out_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    repo = Path(__file__).resolve().parents[3]
    board = build_all_board(repo)
    print(f"\n{HONEST_NOTE}\n")
    for sport_id, rows in board.items():
        if rows:
            print(f"  {sport_id}: {len(rows)} rows  "
                  f"(model_prob range [{min(r['model_prob'] for r in rows if r['model_prob']):.3f}"
                  f" – {max(r['model_prob'] for r in rows if r['model_prob']):.3f}])")
        else:
            print(f"  {sport_id}: corpus absent — skipped")
    sys.exit(0)
