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
from .adapter_helpers import (
    _verify_kernel_import_weight,
    _add_rest_days,
    _devig_prob,
    _feature_bundle_impl,
)

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
    # feature_bundle — the gate seam (implementation in adapter_helpers)
    # ------------------------------------------------------------------ #

    def feature_bundle(
        self,
        hypothesis: Hypothesis,
        seasons: Sequence[int],
    ) -> FeatureBundle:
        """Build a gate-valid FeatureBundle for the given hypothesis.

        Delegates to ``_feature_bundle_impl`` in adapter_helpers; see that
        function for the full docstring and column contract.
        """
        return _feature_bundle_impl(self, hypothesis, seasons)
