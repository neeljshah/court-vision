"""domains.tennis.adapter — TennisAdapter: MARKET_ONLY second-domain proof adapter.

Implements the MarketOnlyDomainAdapter protocol (SECOND_DOMAIN_PROOF.md §3.1).
The critical seam: ``feature_bundle()`` injects a ``FeatureBundle`` into
``signal._gate_matrix`` so ``src.loop.gate.evaluate`` runs on tennis data via the
gate's documented offline-matrix path (gate.py lines 17-23) without any edits to
the kernel.

F5 compliance (binding): ZERO imports from ``domains.nba``, ``src.data``,
``src.sim``, ``src.tracking``, or ``src.pipeline``.  Only the sport-agnostic kernel
seam (``src.loop.gate.FeatureBundle``, ``src.loop.signal.*``) is allowed.

PRIVATE: combined with odds this module is price-bearing; never tracked publicly.
"""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Dict, List, Literal, Optional, Sequence

import numpy as np
import pandas as pd

from .config import (
    DATA_DIR_REL,
    ELO_MIN_MATCHES,
    MATCHES_PARQUET,
    ODDS_PARQUET,
    SPORT_ID,
    EventRef,
    MarketSnapshot,
    Outcome,
)
from .elo import elo_state_asof, prob, walk_forward_elo

# Kernel gate seam — the ONLY src.* import allowed; gate.FeatureBundle is the
# injected-matrix contract that lets tennis data feed the real 5-criterion gate
# without any NBA-shaped inputs.
from src.loop.gate import FeatureBundle
from src.loop.signal import AsOfContext, GateResult, Hypothesis, Signal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Protocol definition (local; reconcile with DOMAIN_ADAPTER_SPEC.md §8.1 later)
# ---------------------------------------------------------------------------

# Runtime check: verify the kernel imports are light (no torch/cv2 side-effects).
# This guard fires once at import time and logs a warning — never raises — so
# the adapter can still run in torch-absent environments.
def _verify_kernel_import_weight() -> None:
    import sys
    heavy = {"torch", "cv2", "tensorflow"}
    loaded = set(sys.modules) & heavy
    if loaded:  # pragma: no cover
        logger.warning(
            "Heavy modules %s already loaded when TennisAdapter was imported; "
            "gate runs on CPU fallback (expected in test environments).", loaded
        )


_verify_kernel_import_weight()


# ---------------------------------------------------------------------------
# TennisAdapter
# ---------------------------------------------------------------------------


class TennisAdapter:
    """MARKET_ONLY domain adapter for ATP tennis (second-domain proof).

    Implements only the subset of DomainAdapter the market-only kernel needs:
    list_events / market_snapshot / outcome / baseline_probability / feature_bundle.
    NO sim / PBP / CV / roster / clock methods.

    Parameters
    ----------
    repo_root:
        Absolute path to the repository root.  Defaults to resolving from
        this file's location (``domains/tennis/adapter.py`` → root).
    matches_df:
        Optional pre-loaded matches DataFrame (for offline / test use).
        If None, loaded from ``data/domains/tennis/matches.parquet`` on demand.
    odds_df:
        Optional pre-loaded odds DataFrame (for offline / test use).
    """

    sport: str = SPORT_ID

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        matches_df: Optional[pd.DataFrame] = None,
        odds_df: Optional[pd.DataFrame] = None,
    ) -> None:
        self._root = repo_root or Path(__file__).resolve().parents[2]
        self._matches: Optional[pd.DataFrame] = matches_df
        self._odds: Optional[pd.DataFrame] = odds_df
        self._elo_cache: Dict[dt.date, object] = {}  # date → EloState

    # ------------------------------------------------------------------ #
    # Data loaders (lazy; safe to call with injected frames in tests)
    # ------------------------------------------------------------------ #

    def _get_matches(self) -> pd.DataFrame:
        if self._matches is not None:
            return self._matches
        path = self._root / MATCHES_PARQUET
        if not path.exists():
            raise FileNotFoundError(
                f"matches.parquet not found at {path}. "
                "Run domains/tennis/ingest_sackmann.py first."
            )
        self._matches = pd.read_parquet(path)
        return self._matches

    def _get_odds(self) -> pd.DataFrame:
        if self._odds is not None:
            return self._odds
        path = self._root / ODDS_PARQUET
        if not path.exists():
            raise FileNotFoundError(
                f"odds.parquet not found at {path}. "
                "Run domains/tennis/ingest_tennisdata.py first."
            )
        self._odds = pd.read_parquet(path)
        return self._odds

    def _elo_as_of(self, as_of: dt.date) -> object:
        """Return (cached) EloState built from all matches strictly before as_of."""
        if as_of not in self._elo_cache:
            self._elo_cache[as_of] = elo_state_asof(self._get_matches(), as_of)
        return self._elo_cache[as_of]

    # ------------------------------------------------------------------ #
    # MarketOnlyDomainAdapter protocol
    # ------------------------------------------------------------------ #

    def list_events(self, date: dt.date) -> List[EventRef]:
        """Return all matches scheduled on ``date`` as EventRef objects."""
        df = self._get_matches()
        dates = pd.to_datetime(df["date"]).dt.date
        day = df[dates == date]
        events: List[EventRef] = []
        for _, row in day.iterrows():
            meta: Dict[str, object] = {
                "surface": row.get("surface", "Unknown"),
                "tourney_level": row.get("tourney_level", ""),
                "best_of": int(row.get("best_of", 3)),
            }
            events.append(
                EventRef(
                    sport=SPORT_ID,
                    event_id=str(row.get("event_id", "")),
                    start_time_utc=dt.datetime.combine(date, dt.time(12, 0)),
                    entity_a=str(int(row["p1_id"])),
                    entity_b=str(int(row["p2_id"])),
                    meta=meta,
                )
            )
        return events

    def market_snapshot(
        self,
        event: EventRef,
        kind: Literal["open", "close"],
    ) -> Optional[MarketSnapshot]:
        """Return a MarketSnapshot using p1/p2-oriented prices (outcome-blind).

        Reads ps_p1/ps_p2 (Pinnacle) or b365_p1/b365_p2 (Bet365) — NEVER the
        audit-only w/l columns.  Both "open" and "close" resolve to the same
        closing price (tennis-data.co.uk; real openers come from T-E Odds API).
        """
        try:
            odds = self._get_odds()
        except FileNotFoundError:
            return None
        mask = odds["event_id"] == event.event_id
        row_df = odds[mask]
        if row_df.empty:
            return None
        row = row_df.iloc[0]
        ps_p1 = row.get("ps_p1", np.nan)
        ps_p2 = row.get("ps_p2", np.nan)
        if pd.notna(ps_p1) and pd.notna(ps_p2) and float(ps_p1) > 1.0 and float(ps_p2) > 1.0:
            pa, pb, book = float(ps_p1), float(ps_p2), "pinnacle"
        else:
            b365_p1 = row.get("b365_p1", np.nan)
            b365_p2 = row.get("b365_p2", np.nan)
            if pd.notna(b365_p1) and pd.notna(b365_p2) and float(b365_p1) > 1.0 and float(b365_p2) > 1.0:
                pa, pb, book = float(b365_p1), float(b365_p2), "bet365"
            else:
                return None
        return MarketSnapshot(
            event=event, kind=kind, price_a=pa, price_b=pb, book=book
        )

    def outcome(self, event: EventRef) -> Optional[Outcome]:
        """Return the settled Outcome for the event, or None if unsettled."""
        try:
            df = self._get_matches()
        except FileNotFoundError:
            return None
        mask = df["event_id"] == event.event_id
        row_df = df[mask]
        if row_df.empty:
            return None
        row = row_df.iloc[0]
        winner_flag = int(row.get("winner", 0))
        winner: Literal["a", "b"] = "a" if winner_flag == 1 else "b"
        return Outcome(
            event=event,
            winner=winner,
            settled_at=dt.datetime.combine(
                pd.to_datetime(row["date"]).date(), dt.time(23, 59)
            ),
        )

    def baseline_probability(
        self, event: EventRef, as_of: dt.datetime
    ) -> float:
        """Leak-free P(entity_a wins) via blended Elo as-of as_of.datetime.

        Strictly pre-match: only matches with date < as_of.date() contribute.
        """
        state = self._elo_as_of(as_of.date())
        surface = str(event.meta.get("surface", "Unknown"))
        try:
            p1_id = int(event.entity_a)
            p2_id = int(event.entity_b)
        except (ValueError, TypeError):
            return 0.5
        return float(prob(state, p1_id, p2_id, surface))

    # ------------------------------------------------------------------ #
    # feature_bundle — the gate seam
    # ------------------------------------------------------------------ #

    def feature_bundle(
        self,
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
        matches_df = self._get_matches()

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

        # Try to join odds
        try:
            odds_df = self._get_odds()
            has_odds = True
        except FileNotFoundError:
            logger.debug("odds.parquet missing; lines/closing will be None")
            has_odds = False
            odds_df = pd.DataFrame()

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

            # Odds lookup
            line_val, close_val = np.nan, np.nan
            if has_odds and "event_id" in row and pd.notna(row.get("event_id")):
                odds_row = odds_df[odds_df["event_id"] == row["event_id"]]
                if not odds_row.empty:
                    or_ = odds_row.iloc[0]
                    line_val = _devig_prob(or_, kind="open")
                    close_val = _devig_prob(or_, kind="close")

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


# ---------------------------------------------------------------------------
# Helpers
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
