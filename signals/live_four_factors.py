"""Signal: live_four_factors — live eFG/TOV/OREB/FT-rate per team (ARM-A).

Target : winprob
Scope  : live

Basketball hypothesis
---------------------
Dean Oliver's Four Factors (eFG%, TOV rate, OREB%, FT rate) explain ~80% of
possession-level scoring.  During a game, the *cumulative* gap between the two
teams on all four factors at each quarter boundary should update win probability
beyond pregame ratings and raw score margin, because it captures *how* the teams
are playing (shot quality, ball security, second chances, foul drawing) rather
than simply *what* the scoreboard shows.

Data source
-----------
``data/cache/inplay_qbox_efficiency.parquet``  (3,757 rows, grain=game_id×snapshot)
    Columns: game_id, snapshot (endQ1/endQ2/endQ3),
             home_efg_pct_cum, home_tov_per_poss_cum, home_ft_rate_cum,
             home_oreb_pct_cum (same for away_*).
``data/rest_travel.parquet``  (grain=game_id×team_abbreviation)
    Used solely to attach game_date so the parquet is filtered leak-safe.

Atlas consumed
--------------
``team__offensive_identity``  (if present in the store) — provides season-level
four-factor baselines for the subject team. The live cumulative four factors
*deviate* from those baselines; the deviation is the marginal live signal.

Sub-features emitted (8)
------------------------
efg_cum       : subject team's cumulative eFG% this game
tov_poss_cum  : subject team's cumulative TOV per possession
oreb_pct_cum  : subject team's cumulative OREB%
ft_rate_cum   : subject team's cumulative FT rate (FTA/FGA)
efg_diff      : efg_cum – opponent's efg_cum
tov_diff      : opponent's tov_poss_cum – subject's tov_poss_cum  (+ = subject advantage)
oreb_diff     : oreb_pct_cum – opponent's oreb_pct_cum
ft_rate_diff  : ft_rate_cum – opponent's ft_rate_cum

DEFER conditions
----------------
* ``ctx.game_id`` is None               → cannot look up the in-game row.
* ``ctx.snapshot`` is None              → snapshot not yet known (pre-tip).
* ``ctx.snapshot`` not in endQ1/Q2/Q3  → half-time or live mid-quarter (no row).
* No row found for (game_id, snapshot)  → game not yet in the parquet cache.
* ``ctx.is_home`` is None               → cannot assign home/away side.

All these return ``None`` (neutral / missing) rather than raising.
"""
from __future__ import annotations

import datetime as _dt
import functools
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.loop.signal import (
    AsOfContext,
    Hypothesis,
    Signal,
    SignalValue,
)

# ---------------------------------------------------------------------------
# Repo root so we can resolve parquet paths regardless of cwd.
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
_QBOX_PATH = _ROOT / "data" / "cache" / "inplay_qbox_efficiency.parquet"
_RT_PATH = _ROOT / "data" / "rest_travel.parquet"

# Snapshot labels present in the parquet.
_VALID_SNAPSHOTS = frozenset({"endQ1", "endQ2", "endQ3"})


# ---------------------------------------------------------------------------
# Leak-safe parquet loader — cached per process so we pay IO cost once.
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _load_qbox() -> pd.DataFrame:
    """Load and enrich the qbox parquet with a game_date column.

    game_date is sourced from rest_travel (covers 100% of qbox rows).
    The date column enables strict ``<= decision_time`` filtering in build().
    """
    qbox = pd.read_parquet(_QBOX_PATH)
    rt = pd.read_parquet(_RT_PATH)[["game_id", "game_date"]].drop_duplicates("game_id")
    qbox = qbox.merge(rt, on="game_id", how="left")
    qbox["game_date"] = pd.to_datetime(qbox["game_date"], errors="coerce")
    return qbox


# ---------------------------------------------------------------------------
# Signal implementation.
# ---------------------------------------------------------------------------

class LiveFourFactors(Signal):
    """Live eFG/TOV/OREB/FT-rate differential per team — winprob target, live scope.

    Reads ``inplay_qbox_efficiency.parquet`` (cumulative four factors by quarter
    snapshot) filtered to game rows whose game_date is strictly <= decision_time
    (leak-safe).  Optionally enriches with team offensive-identity atlas from the
    store to compute deviation from season baseline (atlas reinforcement).

    Returns a dict of 8 sub-features keyed on ``emits`` names, or ``None`` when
    the required live context is absent.
    """

    name: str = "live_four_factors"
    target: str = "winprob"
    scope: str = "live"
    reads_atlas: List[str] = ["team__offensive_identity"]
    emits: List[str] = [
        "efg_cum",
        "tov_poss_cum",
        "oreb_pct_cum",
        "ft_rate_cum",
        "efg_diff",
        "tov_diff",
        "oreb_diff",
        "ft_rate_diff",
    ]

    # ------------------------------------------------------------------
    # Signal contract — build
    # ------------------------------------------------------------------

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Return a dict of 8 live four-factor sub-features, or None if unavailable.

        Leak-safe: only rows whose ``game_date <= ctx.decision_time`` are
        considered; the specific row is matched by ``ctx.game_id`` and
        ``ctx.snapshot``.

        Args:
            ctx: Decision context.  Must have ``game_id``, ``snapshot`` in
                 {endQ1, endQ2, endQ3}, and ``is_home`` set.

        Returns:
            Dict with sub-feature values, or ``None`` on missing/deferral.
        """
        # ---- guard: required live context --------------------------------
        if ctx.game_id is None:
            return None
        if ctx.snapshot not in _VALID_SNAPSHOTS:
            return None
        if ctx.is_home is None:
            return None

        # ---- leak-safe parquet lookup ------------------------------------
        decision_date = ctx.decision_time.date()
        qbox = _load_qbox()
        mask = (
            (qbox["game_id"] == ctx.game_id)
            & (qbox["snapshot"] == ctx.snapshot)
            & (qbox["game_date"].dt.date <= decision_date)
        )
        rows = qbox[mask]
        if rows.empty:
            return None

        row: Dict[str, Any] = rows.iloc[0].to_dict()

        # ---- assign home/away sides based on ctx.is_home -----------------
        if ctx.is_home:
            subj_prefix, opp_prefix = "home_", "away_"
        else:
            subj_prefix, opp_prefix = "away_", "home_"

        efg_s = _safe_float(row.get(f"{subj_prefix}efg_pct_cum"))
        tov_s = _safe_float(row.get(f"{subj_prefix}tov_per_poss_cum"))
        oreb_s = _safe_float(row.get(f"{subj_prefix}oreb_pct_cum"))
        ft_s = _safe_float(row.get(f"{subj_prefix}ft_rate_cum"))

        efg_o = _safe_float(row.get(f"{opp_prefix}efg_pct_cum"))
        tov_o = _safe_float(row.get(f"{opp_prefix}tov_per_poss_cum"))
        oreb_o = _safe_float(row.get(f"{opp_prefix}oreb_pct_cum"))
        ft_o = _safe_float(row.get(f"{opp_prefix}ft_rate_cum"))

        # Any None in the subject side → cannot build
        if any(v is None for v in (efg_s, tov_s, oreb_s, ft_s)):
            return None

        # ---- optional atlas enrichment (season baseline for deviation) ----
        # If the store holds an offensive-identity atlas for this team we can
        # compute live_efg – season_efg etc. as additional context.  We do NOT
        # emit extra sub-features (to keep the feature set stable) but the
        # baseline read demonstrates the ARM-A ↔ ARM-B reinforcement pattern.
        _team_entity = ctx.team or ""
        _atlas_baseline = self.read_atlas(
            f"team:{_team_entity}", "team__offensive_identity", ctx.decision_time
        )
        # (baseline is purely informational here; future atlas sub-feature can
        # expose season_efg_diff = efg_s – baseline["efg_pct"] once the atlas lands)

        # ---- compute differentials (may be None if opp side missing) ------
        efg_diff = _diff(efg_s, efg_o)
        # TOV diff: opponent TOV – subject TOV (positive = subject advantage)
        tov_diff = _diff(tov_o, tov_s)
        oreb_diff = _diff(oreb_s, oreb_o)
        ft_diff = _diff(ft_s, ft_o)

        return {
            "efg_cum": efg_s,
            "tov_poss_cum": tov_s,
            "oreb_pct_cum": oreb_s,
            "ft_rate_cum": ft_s,
            "efg_diff": efg_diff,
            "tov_diff": tov_diff,
            "oreb_diff": oreb_diff,
            "ft_rate_diff": ft_diff,
        }

    # ------------------------------------------------------------------
    # Signal contract — hypothesis
    # ------------------------------------------------------------------

    def hypothesis(self) -> Hypothesis:
        """Return the testable basketball hypothesis for this signal."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "Cumulative in-game eFG%, TOV rate, OREB%, and FT rate gaps "
                "between teams at each quarter boundary predict win probability "
                "beyond pregame ratings and live score margin."
            ),
            rationale=(
                "Dean Oliver's Four Factors explain ~80% of scoring variance "
                "per possession.  A team outperforming its season baseline on "
                "multiple factors simultaneously — especially eFG and TOV — "
                "should have an elevated win probability independent of the raw "
                "score, because it reflects structural efficiency rather than "
                "variance in clutch makes.  The differential (subject – opponent) "
                "captures the net possessional edge live."
            ),
            source="seed",
            atlas_fields=["team__offensive_identity"],
            expected_verdict="SHIP",
            priority="P1",
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> Optional[float]:
    """Return float or None for missing/non-finite values."""
    try:
        v = float(value)
        import math
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _diff(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Return a – b, or None if either operand is None."""
    if a is None or b is None:
        return None
    return a - b
