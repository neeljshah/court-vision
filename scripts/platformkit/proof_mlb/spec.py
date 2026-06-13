"""scripts.platformkit.proof_mlb.spec — MLB ProofSpec (V1-V4 parameterization).

Expressions and strings verbatim from proof_runner.py.
ctx = league_filter: Optional[str]  ("NL" / "AL" / None).
ZERO sport-conditionals; ZERO references to tennis or soccer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.proof_common.spec import EvalWindow, ProofSpec
from domains.mlb.signals import MLBH2HSeasonSignal, MLBRestAdvantageSignal, MLBStreakFormSignal


def _load_market_frame(adapter: Any, seasons: List[int], ctx: Optional[str]) -> Optional[pd.DataFrame]:
    # Verbatim from _market_brier: filter by season COLUMN then home_league == ctx
    try:
        games = adapter._get_games(); odds = adapter._get_odds()
    except FileNotFoundError:
        return None
    games = games[games["season"].isin(seasons)]
    if ctx is not None:
        games = games[games["home_league"] == ctx]
    if games.empty or odds.empty:
        return None
    joined = games.merge(odds, on="event_id", how="inner")
    return joined if not joined.empty else None


def _outcome_market(row: Any) -> Optional[float]:
    # Verbatim: float(target_home_win) with NaN-skip
    tgt = float(row.get("target_home_win", np.nan))
    return tgt if np.isfinite(tgt) else None


def _outcome_v4(row: Any) -> Optional[int]:
    # Verbatim: int(float(...)) try/except→None-skip
    try:
        return int(float(row.get("target_home_win", np.nan)))
    except (TypeError, ValueError):
        return None


def _bundle_kwargs(ctx: Optional[str]) -> Dict[str, Any]:
    return {"league_filter": ctx}  # kwarg name the MLB adapter expects


def _filter_v4_eval(df: pd.DataFrame, ctx: Optional[str]) -> pd.DataFrame:
    # Verbatim from run_v4: home_league == ctx; identity when ctx is None
    if ctx is None:
        return df
    return df[df["home_league"] == ctx]


def _filter_v2_odds(adapter: Any, odds_df: pd.DataFrame, ctx: Optional[str]) -> pd.DataFrame:
    # Verbatim from run_v2: event-id intersection via home_league filter
    if ctx is None:
        return odds_df
    try:
        games = adapter._get_games()
        ids = set(games[games["home_league"] == ctx]["event_id"].astype(str))
        return odds_df[odds_df["event_id"].astype(str).isin(ids)]
    except Exception:
        return odds_df


def _get_frames_v4(adapter: Any) -> Tuple[pd.DataFrame, pd.DataFrame]:
    return adapter._get_games(), adapter._get_odds()  # MLB: _get_games NOT _get_matches


def _book_filename(ctx: Optional[str]) -> str:
    # Verbatim from run_v4: sfx = f"_{ctx}" if ctx else ""
    sfx = f"_{ctx}" if ctx else ""
    return f"paper_book{sfx}.json"


SPEC = ProofSpec(
    hyp_v1_name="mlb_p_home_elo_v1",
    hyp_v1_statement="MLB Elo home-win probability calibration baseline",
    hyp_v4_name="mlb_p_home_elo_v4",

    train_seasons=list(range(2010, 2018)),
    eval_windows=[
        EvalWindow("2018-19", [2018, 2019], regime_note=""),
        EvalWindow("2020-21", [2020, 2021],
                   regime_note="NOTE: 2020 COVID 60-game season included as-is."),
    ],
    all_seasons=list(range(2010, 2022)),

    signal_defs=[
        (MLBRestAdvantageSignal, "REJECT"),
        (MLBStreakFormSignal, "REJECT"),
        (MLBH2HSeasonSignal, "REJECT"),
    ],

    close_a_col="dec_close_home",
    close_b_col="dec_close_away",
    open_a_col="dec_open_home",
    open_b_col="dec_open_away",
    model_prob_col="p_home_elo",

    market_brier_key="market_devig_brier",
    market_beats_key="market_beats_model",

    v2_note=(
        "MLB moneyline has TRUE opening and closing prices "
        "(strongest V2 plumbing test); wiring-correctness ONLY."
    ),
    v2_absent_note="odds.parquet absent — V2 CLV mechanics skipped.",
    v2_skip_note_fmt="Only {n} rows with valid prices; skipped.",

    load_market_frame=_load_market_frame,
    outcome_market=_outcome_market,
    outcome_v4=_outcome_v4,
    bundle_kwargs=_bundle_kwargs,
    filter_v4_eval=_filter_v4_eval,
    filter_v2_odds=_filter_v2_odds,
    get_frames_v4=_get_frames_v4,
    book_filename=_book_filename,
)
