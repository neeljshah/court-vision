"""scripts.platformkit.proof_soccer.spec — Soccer ProofSpec (V1-V4 parameterization).

Every string, season window, column name, and leaf-callable expression is
copied VERBATIM from proof_runner.py.  change_kind: new.

Zero sport tokens from other domains (no "tennis", no "mlb").
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.proof_common.spec import EvalWindow, ProofSpec
from domains.soccer.signals import (
    SoccerH2HTotalsSignal,
    SoccerRestCongestionSignal,
    SoccerTotalsFormSignal,
)


# ---------------------------------------------------------------------------
# Leaf callables — bodies are verbatim copies of logic from proof_runner.py
# ---------------------------------------------------------------------------

def _filter_seasons(df: pd.DataFrame, seasons: list) -> pd.DataFrame:
    years = pd.to_datetime(df["date"]).dt.year
    return df[years.isin(seasons)].reset_index(drop=True)


def _load_market_frame(adapter: Any, seasons: list, ctx: Any) -> Optional[pd.DataFrame]:
    """Verbatim from proof_runner._market_brier frame-build block."""
    try:
        m = _filter_seasons(adapter._get_matches(), seasons)
        odds = adapter._get_odds()
    except FileNotFoundError:
        return None
    if m.empty or odds.empty:
        return None
    joined = m.merge(odds, on="event_id", how="inner")
    return joined if not joined.empty else None


def _outcome_market(row: Any) -> Optional[float]:
    """Verbatim from proof_runner._market_brier outcome extraction."""
    tgt = float(row.get("target_over25", np.nan))
    if not np.isfinite(tgt):
        return None
    return tgt


def _outcome_v4(row: Any) -> Optional[int]:
    """Verbatim from proof_runner.run_v4 outcome extraction."""
    tgt = row.get("target_over25", np.nan)
    try:
        return int(float(tgt))
    except (TypeError, ValueError):
        return None


def _bundle_kwargs(ctx: Any) -> Dict[str, Any]:
    """No league_filter for soccer."""
    return {}


def _filter_v4_eval(df: pd.DataFrame, ctx: Any) -> pd.DataFrame:
    """Identity — no extra V4 filter in the soccer runner."""
    return df


def _filter_v2_odds(adapter: Any, odds_df: pd.DataFrame, ctx: Any) -> pd.DataFrame:
    """Identity — no extra V2 odds filter in the soccer runner."""
    return odds_df


def _get_frames_v4(adapter: Any) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Verbatim from proof_runner.run_v4: return (matches, odds)."""
    return (adapter._get_matches(), adapter._get_odds())


def _book_filename(ctx: Any) -> str:
    return "paper_book.json"


# ---------------------------------------------------------------------------
# SPEC — all values verbatim from proof_runner.py
# ---------------------------------------------------------------------------

SPEC = ProofSpec(
    # ---- identity / hypotheses -----------------------------------------------
    hyp_v1_name="soccer_p_over25_v1",
    hyp_v1_statement="Soccer O/U 2.5 Poisson calibration baseline",
    hyp_v4_name="soccer_p_over25_v4",

    # ---- season geometry (verbatim: _TRAIN_SEASONS / _EVAL_*_SEASONS / _ALL_SEASONS) --
    train_seasons=list(range(2015, 2023)),
    eval_windows=[
        EvalWindow("2023-24", [2023, 2024]),
        EvalWindow("2025", [2025]),
    ],
    all_seasons=list(range(2015, 2026)),

    # ---- V3 signals (verbatim from run_v3 signal_defs) -----------------------
    signal_defs=[
        (SoccerRestCongestionSignal, "REJECT"),
        (SoccerTotalsFormSignal, "REJECT"),
        (SoccerH2HTotalsSignal, "REJECT"),
    ],

    # ---- market geometry (verbatim column names from run_v1/_market_brier/run_v2) --
    close_a_col="ou_close_over",
    close_b_col="ou_close_under",
    open_a_col="ou_prematch_over",
    open_b_col="ou_prematch_under",
    model_prob_col="p_over25",

    # ---- V1 result-dict key names (verbatim from run_v1 corpus_results dict) -
    market_brier_key="market_devig_brier",
    market_beats_key="market_beats_model",

    # ---- note strings (verbatim from run_v2) ----------------------------------
    v2_note=(
        "football-data 'as-collected' open prices are a weekly snapshot, NOT a true "
        "exchange opener; V2 is a PLUMBING/wiring-correctness check only, zero edge meaning."
    ),
    v2_absent_note=(
        "odds.parquet absent — V2 CLV mechanics skipped. "
        "Forward-capture CLV requires live feed integration."
    ),
    v2_skip_note_fmt="Only {n} rows with all four valid O/U prices; skipped.",

    # ---- leaf callables -------------------------------------------------------
    load_market_frame=_load_market_frame,
    outcome_market=_outcome_market,
    outcome_v4=_outcome_v4,
    bundle_kwargs=_bundle_kwargs,
    filter_v4_eval=_filter_v4_eval,
    filter_v2_odds=_filter_v2_odds,
    get_frames_v4=_get_frames_v4,
    book_filename=_book_filename,
)
