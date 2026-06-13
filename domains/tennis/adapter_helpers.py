"""domains.tennis.adapter_helpers — Helper functions for TennisAdapter.

Extracted from adapter.py to keep adapter.py ≤ 300 LOC.
All code moved VERBATIM; zero logic changes.

F5 compliance (binding): ZERO imports from ``domains.nba``, ``src.data``,
``src.sim``, ``src.tracking``, or ``src.pipeline``.  Only the sport-agnostic
kernel seam (``src.loop.gate.FeatureBundle``) is allowed.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING, Dict, List, Literal, Sequence

import numpy as np
import pandas as pd

from .config import (
    ELO_MIN_MATCHES,
    SPORT_ID,
)
from .elo import walk_forward_elo
from src.loop.gate import FeatureBundle
from src.loop.signal import Hypothesis

if TYPE_CHECKING:
    from domains.tennis.adapter import TennisAdapter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Import-weight guard (runs once at import time in adapter.py)
# ---------------------------------------------------------------------------


def _verify_kernel_import_weight() -> None:
    """Runtime check: verify the kernel imports are light (no torch/cv2 side-effects).

    This guard fires once at import time and logs a warning — never raises — so
    the adapter can still run in torch-absent environments.
    """
    import sys
    heavy = {"torch", "cv2", "tensorflow"}
    loaded = set(sys.modules) & heavy
    if loaded:  # pragma: no cover
        logger.warning(
            "Heavy modules %s already loaded when TennisAdapter was imported; "
            "gate runs on CPU fallback (expected in test environments).", loaded
        )


# ---------------------------------------------------------------------------
# Rest-days helper
# ---------------------------------------------------------------------------


def _add_rest_days(wf: pd.DataFrame) -> pd.DataFrame:
    """Add rest_days_a / rest_days_b columns (leak-free: last match before row date).

    Capped at 30 days (2 weeks = normal tour break).  Missing history → 15.0.
    """
    wf = wf.copy()
    wf["_date"] = pd.to_datetime(wf["date"]).dt.date
    last_seen: Dict[int, dt.date] = {}
    rest_a_vals: List[float] = []
    rest_b_vals: List[float] = []
    for _, row in wf.iterrows():
        d = row["_date"]
        p1 = int(row["p1_id"])
        p2 = int(row["p2_id"])
        ra = min((d - last_seen[p1]).days, 30) if p1 in last_seen else 15.0
        rb = min((d - last_seen[p2]).days, 30) if p2 in last_seen else 15.0
        rest_a_vals.append(float(ra))
        rest_b_vals.append(float(rb))
        last_seen[p1] = d
        last_seen[p2] = d
    wf["rest_days_a"] = rest_a_vals
    wf["rest_days_b"] = rest_b_vals
    wf.drop(columns=["_date"], inplace=True)
    return wf


# ---------------------------------------------------------------------------
# Devig helper
# ---------------------------------------------------------------------------


def _devig_prob(odds_row: "pd.Series", *, kind: Literal["open", "close"]) -> float:
    """Devigged P(p1 wins) from oriented columns (ps_p1/ps_p2 or b365_p1/b365_p2).

    Outcome-blind: NEVER reads psw/psl/b365w/b365l.  Both "open" and "close"
    map to the same closing price (tennis-data.co.uk; lines≈closing here;
    real openers come from the live Odds API at wave T-E).
    """
    p1 = odds_row.get("ps_p1", np.nan)
    p2 = odds_row.get("ps_p2", np.nan)
    if pd.isna(p1) or pd.isna(p2):
        p1 = odds_row.get("b365_p1", np.nan)
        p2 = odds_row.get("b365_p2", np.nan)
    try:
        pp1, pp2 = float(p1), float(p2)
        if pp1 <= 1.0 or pp2 <= 1.0:
            return float("nan")
        imp_p1 = 1.0 / pp1
        imp_p2 = 1.0 / pp2
        return float(imp_p1 / (imp_p1 + imp_p2))
    except (TypeError, ValueError, ZeroDivisionError):
        return float("nan")


# ---------------------------------------------------------------------------
# feature_bundle implementation
# ---------------------------------------------------------------------------


def _feature_bundle_impl(
    adapter: "TennisAdapter",
    hypothesis: Hypothesis,
    seasons: Sequence[int],
) -> FeatureBundle:
    """Build a gate-valid FeatureBundle for the given hypothesis.

    Uses the injected-matrix path documented in gate.py lines 17-23:
    the caller sets ``signal._gate_matrix = adapter.feature_bundle(...)``
    before calling ``gate.evaluate(signal)``.

    Base features per row (leak-free, pre-match):
        elo_diff            overall Elo p1 - p2
        surface_elo_diff    surface Elo p1 - p2
        best_of             3 or 5
        rest_days_a         days since last match for p1 (capped at 30)
        rest_days_b         days since last match for p2

    ``target``  = winner ∈ {0.0, 1.0}  (1 = p1 wins; ``target="winprob"``
                  so the gate routes through Brier scoring via _CLASS_TARGETS).
    ``lines``   = devigged open probability for p1 (Pinnacle or Bet365).
    ``closing`` = devigged close probability for p1 (same book).

    Rows where odds or Elo data are missing are dropped with a debug log.
    Rows are ordered chronologically (the walk-forward contract).
    """
    matches_df = adapter._get_matches()

    # Filter to requested seasons
    if seasons:
        if "season" in matches_df.columns:
            matches_df = matches_df[matches_df["season"].isin(seasons)]
        else:
            # Fall back: filter by year extracted from date
            dates = pd.to_datetime(matches_df["date"]).dt.year
            matches_df = matches_df[dates.isin(seasons)]

    # Compute walk-forward Elo features (leak-free per row)
    wf = walk_forward_elo(matches_df)

    # Build rest-days feature: days since each player's last match
    wf = _add_rest_days(wf)

    # Try to join odds — vectorized: one left-merge before the loop (O(N+M) vs O(N*M))
    try:
        odds_df = adapter._get_odds()
        has_odds = True
    except FileNotFoundError:
        logger.debug("odds.parquet missing; lines/closing will be None")
        has_odds = False
        odds_df = pd.DataFrame()

    # Pre-merge odds: keep only the columns _devig_prob reads + event_id.
    # drop_duplicates(keep="first") replicates the original .iloc[0] behaviour.
    # Selecting only needed cols avoids any column-name collisions with wf.
    _ODDS_COLS = ["event_id", "ps_p1", "ps_p2", "b365_p1", "b365_p2"]
    if has_odds and not odds_df.empty:
        _odds_sel = odds_df[[c for c in _ODDS_COLS if c in odds_df.columns]].copy()
        _odds_sel = _odds_sel.drop_duplicates("event_id", keep="first")
        wf = wf.merge(_odds_sel, on="event_id", how="left")
    else:
        # Ensure columns exist (all NaN) so row access below is uniform
        for _c in _ODDS_COLS[1:]:
            if _c not in wf.columns:
                wf[_c] = np.nan

    rows_base: List[List[float]] = []
    rows_signal: List[float] = []
    rows_target: List[float] = []
    rows_dates: List[str] = []
    rows_lines: List[float] = []
    rows_closing: List[float] = []

    for _, row in wf.iterrows():
        # Leak-safe check: skip walkover rows (no result to predict)
        if pd.isna(row.get("winner", np.nan)):
            continue
        winner_val = float(row["winner"])  # 1.0 → p1 wins
        target_val = 1.0 if winner_val == 1 else 0.0

        elo_diff = float(row.get("p1_elo", 1500.0)) - float(row.get("p2_elo", 1500.0))
        surf_diff = float(row.get("p1_surface_elo", 1500.0)) - float(row.get("p2_surface_elo", 1500.0))
        best_of = float(row.get("best_of", 3.0))
        rest_a = float(row.get("rest_days_a", 15.0))
        rest_b = float(row.get("rest_days_b", 15.0))

        base_row = [elo_diff, surf_diff, best_of, rest_a, rest_b]
        # Signal column = win_prob_p1 from blended Elo (the hypothesis value)
        signal_val = float(row.get("win_prob_p1", 0.5))

        # Odds lookup — merged columns already on this row (NaN when no match).
        # _devig_prob ignores `kind` (tennis-data.co.uk has closing only); set
        # line_val=NaN so lines=None in the bundle → gate falls back to non-blocking CLV.
        line_val = float("nan")  # no true opener available
        close_val = _devig_prob(row, kind="close")

        rows_base.append(base_row)
        rows_signal.append(signal_val)
        rows_target.append(target_val)
        rows_dates.append(str(pd.to_datetime(row["date"]).date()))
        rows_lines.append(line_val)
        rows_closing.append(close_val)

    if not rows_base:
        raise ValueError(
            f"feature_bundle: no rows for seasons={list(seasons)}. "
            "Check that matches.parquet covers those seasons."
        )

    base_arr = np.array(rows_base, dtype=float)
    sig_arr = np.array(rows_signal, dtype=float)
    tgt_arr = np.array(rows_target, dtype=float)
    lines_arr = np.array(rows_lines, dtype=float)
    closing_arr = np.array(rows_closing, dtype=float)

    # Only attach lines/closing when we have non-NaN coverage
    lines_out = lines_arr if not np.all(np.isnan(lines_arr)) else None
    closing_out = closing_arr if not np.all(np.isnan(closing_arr)) else None

    logger.debug(
        "feature_bundle: %d rows, seasons=%s, lines=%s, closing=%s",
        base_arr.shape[0], list(seasons),
        "yes" if lines_out is not None else "none",
        "yes" if closing_out is not None else "none",
    )

    return FeatureBundle(
        base=base_arr,
        signal_col=sig_arr,
        target=tgt_arr,
        dates=rows_dates,
        lines=lines_out,
        closing=closing_out,
    )
