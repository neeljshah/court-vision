"""pace_regression_to_market — total-target pregame Signal (ARM-A).

Hypothesis
----------
The model's pace × off-rtg projection of game totals runs hot relative to the
sharp Pinnacle closing line.  Regressing the projected pace/total toward the
sharp market total should reduce O/U error and cut the +33-over miss pattern
seen live (2026-05-30 session).

Algorithm
---------
1. Load ``data/nba/season_games_*.json`` (multi-season) filtered to
   ``as_of=ctx.decision_time`` (only games whose ``game_date < decision_time``
   contribute to rolling baselines).  These files carry pre-game rolling L10
   pace/rtg for both teams — the same features used by the proven total model
   (probe_R11_M2v73).
2. Compute a model-projected total:
     proj_total = (home_off_rtg_L10 + away_off_rtg_L10)
                  × pace_avg / 100
   where pace_avg = (home_pace + away_pace) / 2 using the **L10 rolling pace**
   embedded in season_games (leak-safe).
3. If ``ctx.extra["market_total"]`` is provided (the Pinnacle over/under line),
   emit:
     - ``proj_total``          — the raw model projection.
     - ``market_delta``        — (market_total − proj_total); positive means
                                 market is ABOVE model (model running cold).
     - ``shrink_factor``       — how far to pull the model toward market:
                                 SHRINK_ALPHA × market_total + (1−SHRINK_ALPHA) × proj_total.
     - ``abs_miss``            — |market_delta| (useful as a variance signal).
   If market_total is absent (training rows without historical lines), returns
   ``proj_total`` only as a scalar and ``market_delta``/``shrink_factor`` as NaN.

Atlas reads
-----------
Attempts to read the team "pace_profile" atlas section from the store for both
the home and away team.  When available, uses the atlas ``pace_l10`` sub-field
to refine the pace estimate (atlas × data = interaction feature).  Falls back to
raw season_games pace if the atlas is absent.

DEFER condition
---------------
The gate's CLV criterion (criterion 5) requires historical Pinnacle mainline
closing lines paired with game outcomes.  We have only 3 mainline CSVs
(2026-05-26, -28, -30) — far too few for a proper walk-forward CLV evaluation.
This means:
  - ``build()`` is fully implemented and leak-safe.
  - The WF+null+ablation sub-gates CAN run against total MAE once a game-total
    training parquet is materialised (probe_R11_M2 pattern).
  - The CLV gate will be marked DEFER until ≥30 dated mainline CSVs accumulate
    in ``data/lines/``.
Expected gate verdict: DEFER (CLV blocked) with partial SHIP potential once
CLV data grows.  The WF folds are expected to be positive (regression toward
a sharp line almost always wins against an uncalibrated projection).

Data sources used
-----------------
- ``data/nba/season_games_*.json``      — pregame L10 pace/rtg (PRIMARY).
- ``data/player_quarter_stats.parquet`` — actual totals for training labels.
- ``data/lines/*_pin_mainline.csv``     — Pinnacle over/under line (LIVE only;
                                          DEFER for historical walk-forward CLV).
- Store atlas section ``pace_profile``  — optional refinement (ARM-B -> ARM-A
                                          reinforcement loop).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue, Verdict

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
_SEASON_GAMES_DIR = ROOT / "data" / "nba"
_QUARTER_STATS_PATH = ROOT / "data" / "player_quarter_stats.parquet"
_SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]

# Shrinkage weight toward the market line (0 = pure model, 1 = pure market).
# Tuned conservatively; the gate should discover the optimal value.
SHRINK_ALPHA: float = 0.35

# Minimum pace (possessions/48-min) to keep a row — filters early-season
# placeholder 0s in season_games.
_MIN_PACE = 80.0
_MIN_RTG = 85.0

# Cache loaded DataFrames at module level to avoid re-reading on repeated calls
# within the same process (fast re-test support per DESIGN.md §7).
_SEASON_GAMES_DF: Optional[pd.DataFrame] = None
_QUARTER_TOTALS_DF: Optional[pd.DataFrame] = None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _load_season_games() -> pd.DataFrame:
    """Load all season_games JSONs into one DataFrame (cached)."""
    global _SEASON_GAMES_DF
    if _SEASON_GAMES_DF is not None:
        return _SEASON_GAMES_DF
    rows: List[dict] = []
    for season in _SEASONS:
        path = _SEASON_GAMES_DIR / f"season_games_{season}.json"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as fh:
            raw = json.load(fh)
        data_rows = raw.get("rows", raw) if isinstance(raw, dict) else raw
        rows.extend(data_rows)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Filter out placeholder / incomplete rows
    for col in ("home_off_rtg_L10", "away_off_rtg_L10", "home_pace", "away_pace"):
        if col in df.columns:
            df = df[df[col].fillna(0) > 0]
    # Normalise game_date to string YYYY-MM-DD
    df["game_date"] = df["game_date"].astype(str).str[:10]
    _SEASON_GAMES_DF = df.reset_index(drop=True)
    return _SEASON_GAMES_DF


def _load_quarter_totals() -> pd.DataFrame:
    """Load actual game totals from player_quarter_stats.parquet (cached)."""
    global _QUARTER_TOTALS_DF
    if _QUARTER_TOTALS_DF is not None:
        return _QUARTER_TOTALS_DF
    if not _QUARTER_STATS_PATH.exists():
        return pd.DataFrame(columns=["game_id", "actual_total"])
    qs = pd.read_parquet(_QUARTER_STATS_PATH)
    totals = qs.groupby("game_id")["pts"].sum().reset_index()
    totals.columns = ["game_id", "actual_total"]
    _QUARTER_TOTALS_DF = totals
    return _QUARTER_TOTALS_DF


def _proj_total_from_row(row: pd.Series) -> float:
    """Compute model-projected game total from one season_games row.

    Formula:
        proj_total = (home_off_rtg_L10 + away_off_rtg_L10) × pace_avg / 100
    where pace_avg = mean(home_pace, away_pace).  Both rtg and pace are the L10
    rolling season_games values (pre-game information only, leak-safe).
    """
    pace_avg = (float(row.get("home_pace", 0)) + float(row.get("away_pace", 0))) / 2.0
    rtg_sum = (float(row.get("home_off_rtg_L10", 0)) +
               float(row.get("away_off_rtg_L10", 0)))
    if pace_avg < _MIN_PACE or rtg_sum < _MIN_RTG * 2:
        return float("nan")
    return rtg_sum * pace_avg / 100.0


def _find_game_row(df: pd.DataFrame, game_id: Optional[str],
                   home: Optional[str], away: Optional[str],
                   as_of_date: str) -> Optional[pd.Series]:
    """Return the season_games row for a specific game, leak-safe.

    Leak-safe: only returns rows with game_date <= as_of_date (the pregame
    row is dated the day of the game — still <= decision_time for a pregame
    decision).
    """
    if df.empty:
        return None
    mask = df["game_date"] <= as_of_date
    sub = df[mask]
    if game_id and "game_id" in sub.columns:
        hit = sub[sub["game_id"] == game_id]
        if not hit.empty:
            return hit.iloc[-1]
    if home and away and "home_team" in sub.columns:
        hit = sub[(sub["home_team"] == home) & (sub["away_team"] == away)]
        if not hit.empty:
            return hit.iloc[-1]
    return None


# ---------------------------------------------------------------------------
# Signal class
# ---------------------------------------------------------------------------

class PaceRegressionToMarket(Signal):
    """Regress the model's projected total toward the sharp Pinnacle market total.

    target: total (game O/U)
    scope:  pregame

    emits (dict signal):
        proj_total     -- model-projected total (pace × rtg).
        market_delta   -- market_total − proj_total (NaN if market absent).
        shrink_factor  -- SHRINK_ALPHA × market + (1−ALPHA) × proj (NaN if absent).
        abs_miss       -- |market_delta| (variance signal, NaN if absent).
    """

    name: str = "pace_regression_to_market"
    target: str = "total"
    scope: str = "pregame"
    reads_atlas: List[str] = ["pace_profile"]
    emits: List[str] = ["proj_total", "market_delta", "shrink_factor", "abs_miss"]

    # ------------------------------------------------------------------
    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute leak-safe pace-regression feature dict for one game decision.

        Reads season_games data filtered to ``<= ctx.decision_time``.  Market
        total comes from ``ctx.extra["market_total"]`` (set by the live
        pipeline from the Pinnacle mainline CSV).

        Returns None if the game cannot be located in season_games.
        """
        as_of_date = ctx.as_of_iso()
        sg = _load_season_games()
        game_row = _find_game_row(
            sg,
            game_id=ctx.game_id,
            home=ctx.team,
            away=ctx.opp,
            as_of_date=as_of_date,
        )
        if game_row is None:
            return None

        # --- optional atlas read for pace refinement (ARM-B → ARM-A loop) ---
        atlas_home_pace: Optional[float] = None
        atlas_away_pace: Optional[float] = None
        if self.store is not None and ctx.team:
            home_atlas = self.store.read_atlas(
                "team", ctx.team, "pace_profile", ctx.decision_time
            )
            if home_atlas and "pace_l10" in home_atlas:
                atlas_home_pace = float(home_atlas["pace_l10"])
        if self.store is not None and ctx.opp:
            away_atlas = self.store.read_atlas(
                "team", ctx.opp, "pace_profile", ctx.decision_time
            )
            if away_atlas and "pace_l10" in away_atlas:
                atlas_away_pace = float(away_atlas["pace_l10"])

        # Replace season_games pace with atlas value if available
        if atlas_home_pace is not None:
            game_row = game_row.copy()
            game_row["home_pace"] = atlas_home_pace
        if atlas_away_pace is not None:
            game_row = game_row.copy()
            game_row["away_pace"] = atlas_away_pace

        proj_total = _proj_total_from_row(game_row)
        if np.isnan(proj_total):
            return None

        # --- market total (live path; absent at train time → NaN sub-features) ---
        market_total: Optional[float] = ctx.extra.get("market_total")
        if market_total is not None:
            market_total = float(market_total)
            market_delta = market_total - proj_total
            shrink_factor = (
                SHRINK_ALPHA * market_total + (1.0 - SHRINK_ALPHA) * proj_total
            )
            abs_miss = abs(market_delta)
        else:
            market_delta = float("nan")
            shrink_factor = float("nan")
            abs_miss = float("nan")

        return {
            "proj_total": proj_total,
            "market_delta": market_delta,
            "shrink_factor": shrink_factor,
            "abs_miss": abs_miss,
        }

    # ------------------------------------------------------------------
    def hypothesis(self) -> Hypothesis:
        """Return the testable basketball hypothesis for this signal."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "The model's pace × off-rtg projected game total runs hot relative "
                "to the sharp Pinnacle market total.  Regressing the model projection "
                "toward the Pinnacle line by SHRINK_ALPHA=0.35 should reduce O/U MAE "
                "and cut the systematic +33-over miss observed in live playoffs totals."
            ),
            rationale=(
                "Pinnacle is the sharpest book; its total aggregates public AND sharp "
                "money including injury news, lineup changes, and referee tendencies "
                "unavailable in raw off-rtg and pace.  A pace × rtg projection ignores "
                "these real-time factors and systematically overshoots in high-variance "
                "playoff situations (small sample L10 blown wide open by injury)."
            ),
            source="seed",
            atlas_fields=["pace_profile"],
            expected_verdict=Verdict.DEFER,
            priority="P2",
        )
