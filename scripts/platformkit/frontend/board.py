"""scripts.platformkit.frontend.board — multi-sport board builder.

HONEST: Markets efficient — NO model edge claimed.  Value = line-shopping/CLV.
Window: last_n_days | max_rows_per_sport (default 200) | future_only.
Line-shop EV: multi-book (>=2 entries) → best_line/fair_decimal-1, NOT model edge.
"""
from __future__ import annotations

import inspect
import json
import logging
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from scripts.platformkit.frontend.recal_board import recalibrated_board_rows
from src.loop.signal import Hypothesis

logger = logging.getLogger(__name__)

HONEST_NOTE = (
    "Calibrated predictions + best available market lines. "
    "Markets are efficient — NO model edge is claimed. "
    "Value shown = line-shopping / devig / CLV only."
)

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
LINE_SHOP_EV_LABEL = (
    "+EV from LINE-SHOPPING vs devigged fair — NOT a model edge. "
    "Value from picking the best book across the books list."
)


def _load_adapter(sport_id: str, repo_root: Path) -> Optional[Any]:
    reg = _SPORT_REGISTRY.get(sport_id)
    if reg is None:
        return None
    corpus_dir = repo_root / reg["corpus_dir"]
    primary = corpus_dir / reg["primary_parquet"]
    if not primary.exists():
        return None
    try:
        primary_df = pd.read_parquet(primary)
    except Exception as exc:
        logger.error("Failed to read %s: %s", primary, exc)
        return None
    odds_df: Optional[pd.DataFrame] = None
    odds_path = corpus_dir / "odds.parquet"
    if odds_path.exists():
        try:
            odds_df = pd.read_parquet(odds_path)
        except Exception:
            pass
    import importlib
    mod = importlib.import_module(reg["adapter_module"])
    cls = getattr(mod, reg["adapter_class"])
    primary_key = "games_df" if reg["primary_parquet"] == "games.parquet" else "matches_df"
    kwargs: Dict[str, Any] = {primary_key: primary_df}
    if odds_df is not None:
        kwargs["odds_df"] = odds_df
    return cls(**kwargs)

def _safe_float(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None

def _compute_line_shop_ev(
    books: List[Dict[str, Any]],
    market_fair_prob: Optional[float],
) -> tuple:
    """Return (best_book, best_line, line_shop_ev, note).  Needs >=2 valid books."""
    valid = [
        b for b in books
        if isinstance(b, dict) and "book" in b and "decimal_odds" in b
        and b["decimal_odds"] is not None
    ]
    if len(valid) < 2:
        return None, None, None, LINE_SHOP_NOTE
    best = max(valid, key=lambda b: float(b["decimal_odds"]))
    best_book: str = str(best["book"])
    best_decimal: float = float(best["decimal_odds"])
    line_shop_ev: Optional[float] = None
    if market_fair_prob is not None and market_fair_prob > 0:
        fair_decimal = 1.0 / market_fair_prob
        line_shop_ev = round(best_decimal / fair_decimal - 1, 6)
    return best_book, best_decimal, line_shop_ev, LINE_SHOP_EV_LABEL


def _bundle_to_rows(sport_id: str, bundle: Any, calib_tag: str) -> List[Dict[str, Any]]:
    """Convert a FeatureBundle into board rows (one per game).  calibration != edge."""
    sig, dyn_tag = recalibrated_board_rows(sport_id, bundle)  # leak-free recal; tag is dynamic
    dates = list(bundle.dates)
    n = len(dates)
    if bundle.closing is not None:
        market_arr = np.asarray(bundle.closing, dtype=float)
    elif bundle.lines is not None:
        market_arr = np.asarray(bundle.lines, dtype=float)
    else:
        market_arr = np.full(n, float("nan"))
    per_game_books: Optional[List[Any]] = getattr(bundle, "books", None)
    rows: List[Dict[str, Any]] = []
    for i in range(n):
        model_prob = _safe_float(sig[i])
        market_prob = _safe_float(market_arr[i]) if i < len(market_arr) else None
        edge_diag: Optional[float] = None
        if model_prob is not None and market_prob is not None:
            edge_diag = round(model_prob - market_prob, 4)
        game_books = (
            per_game_books[i]
            if per_game_books is not None and i < len(per_game_books)
            else None
        )
        if game_books and len(game_books) >= 2:
            best_book, best_line, line_shop_ev, shop_note = _compute_line_shop_ev(
                game_books, market_prob
            )
        else:
            best_book, best_line, line_shop_ev, shop_note = None, None, None, LINE_SHOP_NOTE
        rows.append({
            "sport": sport_id,
            "date": dates[i],
            "home": None,
            "away": None,
            "model_prob": round(model_prob, 4) if model_prob is not None else None,
            "market_fair_prob": round(market_prob, 4) if market_prob is not None else None,
            "edge_vs_market": {
                "value": edge_diag,
                "label": "DIAGNOSTIC — not a bet signal; markets are efficient",
            },
            "best_book": best_book,
            "best_line": best_line,
            "line_shop_ev": line_shop_ev,
            "line_shop_note": shop_note,
            "clv_placeholder": None,
            "calibration_tag": dyn_tag,
            "honest_note": HONEST_NOTE,
        })
    return rows


def _apply_window(
    rows: List[Dict[str, Any]],
    last_n_days: Optional[int],
    max_rows_per_sport: Optional[int],
    future_only: bool,
) -> List[Dict[str, Any]]:
    """Apply window/filter logic to rows for one sport.

    Priority: future_only > last_n_days > max_rows_per_sport > no filter.
    future_only uses corpus_max_date as "now" (corpora are historical).
    """
    if not rows:
        return rows
    date_strs = [str(r.get("date", "")) for r in rows]
    corpus_max_date = max((d for d in date_strs if d), default="")
    if future_only:
        return [r for r, d in zip(rows, date_strs) if d > corpus_max_date]
    if last_n_days is not None:
        try:
            cutoff_dt = datetime.strptime(corpus_max_date, "%Y-%m-%d") - timedelta(days=last_n_days)
            cutoff = cutoff_dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            cutoff = ""
        return [r for r, d in zip(rows, date_strs) if d >= cutoff]
    if max_rows_per_sport is not None:
        indexed = sorted(enumerate(rows), key=lambda t: date_strs[t[0]], reverse=True)
        top_n = indexed[:max_rows_per_sport]
        top_n_asc = sorted(top_n, key=lambda t: date_strs[t[0]])
        return [r for _, r in top_n_asc]
    return rows


def build_board(
    sport: str,
    repo_root: Optional[Path] = None,
    *,
    last_n_days: Optional[int] = None,
    max_rows_per_sport: Optional[int] = 200,
    future_only: bool = False,
) -> List[Dict[str, Any]]:
    """Build display rows for one sport.  Returns [] if corpus absent.

    last_n_days: keep rows >= corpus_max_date - N days (priority over max_rows).
    max_rows_per_sport: keep most-recent N rows (default 200). Pass None to disable.
    future_only: keep rows > corpus_max_date (highest priority; 0 rows on historical).
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
        sig = inspect.signature(adapter.feature_bundle)
        seasons_required = (
            "seasons" in sig.parameters
            and sig.parameters["seasons"].default is inspect.Parameter.empty
        )
        bundle = (
            adapter.feature_bundle(_BOARD_HYP, [])
            if seasons_required
            else adapter.feature_bundle(_BOARD_HYP)
        )
    except Exception as exc:
        logger.error("feature_bundle failed for %s: %s", sport, exc)
        return []
    rows = _bundle_to_rows(sport, bundle, reg["calibration_tag"])
    return _apply_window(rows, last_n_days, max_rows_per_sport, future_only)


def build_all_board(
    repo_root: Optional[Path] = None,
    *,
    last_n_days: Optional[int] = None,
    max_rows_per_sport: Optional[int] = 200,
    future_only: bool = False,
) -> Dict[str, List[Dict[str, Any]]]:
    """Build rows for every sport; skips absent corpora."""
    root = repo_root or Path(__file__).resolve().parents[3]
    return {
        sport: build_board(
            sport, root,
            last_n_days=last_n_days,
            max_rows_per_sport=max_rows_per_sport,
            future_only=future_only,
        )
        for sport in _SPORT_REGISTRY
    }


def to_json(board: Dict[str, List[Dict[str, Any]]], out_path: Path) -> None:
    """Write board dict to JSON (pretty-printed, UTF-8)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(board, fh, indent=2, default=str)
    logger.info("Board written to %s", out_path)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    repo = Path(__file__).resolve().parents[3]
    board = build_all_board(repo)
    print(f"\n{HONEST_NOTE}\n")
    for sport_id, rows in board.items():
        if rows:
            print(f"  {sport_id}: {len(rows)} rows")
        else:
            print(f"  {sport_id}: corpus absent — skipped")
    sys.exit(0)
