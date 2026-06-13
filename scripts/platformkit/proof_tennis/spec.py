"""scripts.platformkit.proof_tennis.spec — tennis ProofSpec (K-PR-004a).

Every value taken VERBATIM from proof_runner.py.  No sport tokens from other
domains.  No edge claims.  REJECT verdicts are recorded successes.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from scripts.platformkit.proof_common.spec import EvalWindow, ProofSpec
from domains.tennis.signals import (
    FatigueRestSignal,
    H2HResidualSignal,
    SurfaceTransitionSignal,
)

# -- leaf callables — expressions copied VERBATIM from proof_runner.py ------

def _load_market_frame(adapter: Any, seasons: Any, ctx: Any) -> Optional[pd.DataFrame]:
    """Verbatim from proof_runner._market_brier frame-build."""
    try:
        years = pd.to_datetime(adapter._get_matches()["date"]).dt.year
        m = adapter._get_matches()[years.isin(seasons)].reset_index(drop=True)
        odds = adapter._get_odds()
    except FileNotFoundError:
        return None
    if m.empty or odds.empty:
        return None
    return m.merge(odds, on="event_id", how="inner")


def _outcome_market(row: Any) -> Optional[float]:
    """Verbatim from proof_runner._market_brier loop body."""
    return 1.0 if int(row.get("winner", 0)) == 1 else 0.0


def _outcome_v4(row: Any) -> Optional[int]:
    """Verbatim from proof_runner.run_v4 — UNGUARDED, no NaN guard added."""
    return 1 if int(row.get("winner", 0)) == 1 else 0


def _bundle_kwargs(ctx: Any) -> Dict[str, Any]:
    """Tennis has no league_filter — always empty."""
    return {}


def _filter_v4_eval(df: pd.DataFrame, ctx: Any) -> pd.DataFrame:
    """Identity — tennis applies no additional filter."""
    return df


def _filter_v2_odds(adapter: Any, odds_df: pd.DataFrame, ctx: Any) -> pd.DataFrame:
    """Identity — tennis applies no additional filter."""
    return odds_df


def _get_frames_v4(adapter: Any):  # -> Tuple[pd.DataFrame, pd.DataFrame]
    """Verbatim from proof_runner.run_v4 initial data pull."""
    return (adapter._get_matches(), adapter._get_odds())


def _book_filename(ctx: Any) -> str:
    """Verbatim from proof_runner.run_v4 — always paper_book.json."""
    return "paper_book.json"


# -- SPEC -------------------------------------------------------------------

SPEC = ProofSpec(
    # -- hypotheses (verbatim from Hypothesis(...) calls in proof_runner) ----
    hyp_v1_name="tennis_elo_v1",
    hyp_v1_statement="Elo calibration baseline",
    hyp_v4_name="tennis_elo_v4",

    # -- season geometry (verbatim from module-level constants) --------------
    train_seasons=list(range(2018, 2023)),
    eval_windows=[
        EvalWindow("2023-24", [2023, 2024]),
        EvalWindow("2025-26", [2025, 2026]),
    ],
    all_seasons=list(range(2015, 2027)),

    # -- V3 signals (verbatim from run_v3 signal_defs list) ------------------
    signal_defs=[
        (FatigueRestSignal, "REJECT"),
        (SurfaceTransitionSignal, "REJECT or DEFER"),
        (H2HResidualSignal, "REJECT"),
    ],

    # -- market columns (tennis: Pinnacle devig, open==close) ----------------
    close_a_col="ps_p1",
    close_b_col="ps_p2",
    open_a_col=None,
    open_b_col=None,
    model_prob_col="p1_elo_prob",

    # -- V1 result-dict key names (verbatim from run_v1 corpus_results dict) -
    market_brier_key="pinnacle_devig_brier",
    market_beats_key="market_beats_elo",

    # -- V2 note strings (verbatim from run_v2) ------------------------------
    v2_note=(
        "tennis-data.co.uk: closing prices only — open==close by construction. "
        "CLV vs real opener requires Phase 4 (CV_DOMAIN_TENNIS, Odds API)."
    ),
    v2_absent_note=(
        "odds.parquet absent — V2 CLV mechanics skipped. "
        "Forward-capture CLV requires Phase 4 CV_DOMAIN_TENNIS."
    ),
    v2_skip_note_fmt="Only {n} rows with valid Pinnacle prices; skipped.",

    # -- leaf callables ------------------------------------------------------
    load_market_frame=_load_market_frame,
    outcome_market=_outcome_market,
    outcome_v4=_outcome_v4,
    bundle_kwargs=_bundle_kwargs,
    filter_v4_eval=_filter_v4_eval,
    filter_v2_odds=_filter_v2_odds,
    get_frames_v4=_get_frames_v4,
    book_filename=_book_filename,
)
