"""domains.soccer.adapter — SoccerAdapter: MARKET_ONLY O/U 2.5 goals adapter.

Gate seam: feature_bundle() injects a FeatureBundle into signal._gate_matrix so
src.loop.gate.evaluate runs on soccer data with ZERO kernel edits.

F5 compliance (binding): imports ONLY stdlib, numpy, pandas, domains.soccer.*,
src.loop.gate.FeatureBundle, src.loop.signal.  ZERO imports from other domains,
src.data, src.sim, src.tracking, or src.pipeline.

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
    MATCHES_PARQUET, ODDS_PARQUET, OVER_SIDE, SPORT_ID, UNDER_SIDE,
    EventRef, MarketSnapshot, Outcome,
)
from .ratings import GoalsState, _lambdas, _p_over, goals_state_asof, walk_forward_goals
from src.loop.gate import FeatureBundle
from src.loop.signal import Hypothesis

logger = logging.getLogger(__name__)


def _verify_kernel_import_weight() -> None:
    import sys
    heavy = {"torch", "cv2", "tensorflow"}
    loaded = set(sys.modules) & heavy
    if loaded:  # pragma: no cover
        logger.warning("Heavy modules %s loaded; gate runs on CPU fallback.", loaded)


_verify_kernel_import_weight()


class SoccerAdapter:
    """MARKET_ONLY adapter for club soccer O/U 2.5 goals (football-data.co.uk).

    Parameters
    ----------
    repo_root: optional repo root (defaults to grandparent of this file).
    matches_df / odds_df: optional pre-loaded DataFrames for offline / test use.
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
        self._state_cache: Dict[dt.date, GoalsState] = {}

    # ------------------------------------------------------------------
    # Lazy loaders
    # ------------------------------------------------------------------

    def _get_matches(self) -> pd.DataFrame:
        if self._matches is not None:
            return self._matches
        path = self._root / MATCHES_PARQUET
        if not path.exists():
            raise FileNotFoundError(f"matches.parquet not found at {path}.")
        self._matches = pd.read_parquet(path)
        return self._matches

    def _get_odds(self) -> pd.DataFrame:
        if self._odds is not None:
            return self._odds
        path = self._root / ODDS_PARQUET
        if not path.exists():
            raise FileNotFoundError(f"odds.parquet not found at {path}.")
        self._odds = pd.read_parquet(path)
        return self._odds

    def _goals_as_of(self, as_of: dt.date) -> GoalsState:
        """Cached GoalsState from all matches strictly before as_of."""
        if as_of not in self._state_cache:
            self._state_cache[as_of] = goals_state_asof(self._get_matches(), as_of)
        return self._state_cache[as_of]

    # ------------------------------------------------------------------
    # MarketOnlyDomainAdapter protocol
    # ------------------------------------------------------------------

    def list_events(self, date: dt.date) -> List[EventRef]:
        """All matches on date as EventRef objects (entity_a=OVER_SIDE, entity_b=UNDER_SIDE)."""
        df = self._get_matches()
        day = df[pd.to_datetime(df["date"]).dt.date == date]
        events: List[EventRef] = []
        for _, row in day.iterrows():
            meta: Dict[str, object] = {
                "home_team": str(row["home_team"]),
                "away_team": str(row["away_team"]),
                "div": str(row.get("div", "")),
                "season": int(row["season"]) if "season" in row.index else None,
            }
            events.append(EventRef(
                sport=SPORT_ID,
                event_id=str(row["event_id"]),
                start_time_utc=dt.datetime.combine(date, dt.time(12, 0)),
                entity_a=OVER_SIDE,
                entity_b=UNDER_SIDE,
                meta=meta,
            ))
        return events

    def market_snapshot(
        self, event: EventRef, kind: Literal["open", "close"]
    ) -> Optional[MarketSnapshot]:
        """O/U 2.5 price snapshot. kind='open'->ou_prematch_*; kind='close'->ou_close_*.

        NOTE: kind='open' maps to the football-data PRE-MATCH price (a weekly/latest
        snapshot, NOT a true exchange opener). Treat it as 'earliest available price',
        not a genuine opener; do not derive CLV as close-minus-prematch from it.
        Returns None when row absent or any price <= 1.0."""
        try:
            odds = self._get_odds()
        except FileNotFoundError:
            return None
        row_df = odds[odds["event_id"] == event.event_id]
        if row_df.empty:
            return None
        row = row_df.iloc[0]
        if kind == "open":
            op_col, up_col, bk_col = "ou_prematch_over", "ou_prematch_under", "book_prematch"
        else:
            op_col, up_col, bk_col = "ou_close_over", "ou_close_under", "book_close"
        try:
            op, up = float(row.get(op_col, np.nan)), float(row.get(up_col, np.nan))
        except (TypeError, ValueError):
            return None
        if pd.isna(op) or pd.isna(up) or op <= 1.0 or up <= 1.0:
            return None
        return MarketSnapshot(
            event=event, kind=kind, price_a=op, price_b=up,
            book=str(row.get(bk_col, "unknown")),
        )

    def outcome(self, event: EventRef) -> Optional[Outcome]:
        """Settled Outcome: winner='a' if total_goals>=3 (Over), 'b' if <=2 (Under)."""
        try:
            df = self._get_matches()
        except FileNotFoundError:
            return None
        row_df = df[df["event_id"] == event.event_id]
        if row_df.empty:
            return None
        row = row_df.iloc[0]
        total = int(row["total_goals"])
        winner: Literal["a", "b"] = "a" if total >= 3 else "b"
        row_date = pd.to_datetime(row["date"]).date()
        return Outcome(
            event=event,
            winner=winner,
            settled_at=dt.datetime.combine(row_date, dt.time(23, 59)),
            meta={"total_goals": total, "home_goals": int(row["fthg"]),
                  "away_goals": int(row["ftag"])},
        )

    def baseline_probability(self, event: EventRef, as_of: dt.datetime) -> float:
        """Leak-free P(Over 2.5) via Poisson model using matches strictly before as_of."""
        state = self._goals_as_of(as_of.date())
        lam_h, lam_a = _lambdas(state, str(event.meta["home_team"]),
                                 str(event.meta["away_team"]))
        return float(_p_over(lam_h + lam_a))

    # ------------------------------------------------------------------
    # feature_bundle — the gate seam
    # ------------------------------------------------------------------

    def feature_bundle(
        self, hypothesis: Hypothesis, seasons: Sequence[int]
    ) -> FeatureBundle:
        """Gate-valid FeatureBundle for the given seasons.

        Base (5 cols, all strictly pre-match):
            [lam_home, lam_away, lam_total, rest_days_home, rest_days_away]
        signal_col = p_over25 (Poisson O/U model probability).
        target     = target_over25 ∈ {0.0, 1.0}.
        lines      = devigged pre-match P(over); closing = devigged close P(over).
        """
        matches_df = self._get_matches()
        if seasons:
            matches_df = matches_df[matches_df["season"].isin(seasons)]

        wf = walk_forward_goals(matches_df)
        wf = _add_rest_days(wf)

        try:
            odds_df = self._get_odds()
            has_odds = True
        except FileNotFoundError:
            has_odds = False
            odds_df = pd.DataFrame()

        # Pre-merge odds: one left-merge before the loop (O(N+M) vs O(N*M)).
        # Only select the columns _devig_over reads to avoid name collisions.
        # drop_duplicates(keep="first") replicates the original .iloc[0] behaviour.
        _ODDS_COLS = ["event_id", "ou_prematch_over", "ou_prematch_under",
                      "ou_close_over", "ou_close_under"]
        if has_odds and not odds_df.empty:
            _odds_sel = odds_df[[c for c in _ODDS_COLS if c in odds_df.columns]].copy()
            _odds_sel = _odds_sel.drop_duplicates("event_id", keep="first")
            wf = wf.merge(_odds_sel, on="event_id", how="left")
        else:
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
            tgt_raw = row.get("target_over25", np.nan)
            if pd.isna(tgt_raw):
                continue
            # Odds columns already merged onto row (NaN when no match)
            line_val = _devig_over(row.get("ou_prematch_over"), row.get("ou_prematch_under"))
            close_val = _devig_over(row.get("ou_close_over"), row.get("ou_close_under"))
            rows_base.append([float(row["lam_home"]), float(row["lam_away"]),
                               float(row["lam_total"]),
                               float(row.get("rest_days_home", 15.0)),
                               float(row.get("rest_days_away", 15.0))])
            rows_signal.append(float(row["p_over25"]))
            rows_target.append(float(tgt_raw))
            rows_dates.append(str(pd.to_datetime(row["date"]).date()))
            rows_lines.append(line_val)
            rows_closing.append(close_val)

        if not rows_base:
            raise ValueError(
                f"feature_bundle: no rows for seasons={list(seasons)}. "
                "Check that matches.parquet covers those seasons."
            )

        base_arr = np.array(rows_base, dtype=float)
        lines_arr = np.array(rows_lines, dtype=float)
        closing_arr = np.array(rows_closing, dtype=float)
        return FeatureBundle(
            base=base_arr,
            signal_col=np.array(rows_signal, dtype=float),
            target=np.array(rows_target, dtype=float),
            dates=rows_dates,
            lines=lines_arr if not np.all(np.isnan(lines_arr)) else None,
            closing=closing_arr if not np.all(np.isnan(closing_arr)) else None,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_rest_days(wf: pd.DataFrame) -> pd.DataFrame:
    """Add rest_days_home/away (leak-free, team-keyed, capped 30, default 15)."""
    wf = wf.copy()
    wf["_date"] = pd.to_datetime(wf["date"]).dt.date
    last_seen: Dict[str, dt.date] = {}
    rh_vals: List[float] = []
    ra_vals: List[float] = []
    for _, row in wf.iterrows():
        d, home, away = row["_date"], str(row["home_team"]), str(row["away_team"])
        rh_vals.append(min((d - last_seen[home]).days, 30) if home in last_seen else 15.0)
        ra_vals.append(min((d - last_seen[away]).days, 30) if away in last_seen else 15.0)
        last_seen[home] = d
        last_seen[away] = d
    wf["rest_days_home"] = rh_vals
    wf["rest_days_away"] = ra_vals
    wf.drop(columns=["_date"], inplace=True)
    return wf


def _devig_over(over_price: object, under_price: object) -> float:
    """Devigged P(Over 2.5): imp_over / (imp_over + imp_under). NaN if invalid."""
    try:
        op, up = float(over_price), float(under_price)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float("nan")
    if pd.isna(op) or pd.isna(up) or op <= 1.0 or up <= 1.0:
        return float("nan")
    return float((1.0 / op) / (1.0 / op + 1.0 / up))
