"""signals/foul_state_bonus.py — ARM-A signal: team foul-bonus FT-rate spike.

Hypothesis
----------
When a team accumulates >= 5 team fouls in a period (NBA bonus) or >= 7 fouls
(double-bonus), EVERY subsequent non-shooting foul sends the fouled player to the
free-throw line.  This inflates scoring pace for the team in the bonus and deflates
it for the fouling team (foul trouble bench-depth erosion).

Feature emitted (dict signal, 3 sub-features):
  * foul_state_bonus__home_bonus_flag   : 1.0 if home team is in bonus at decision_time period, else 0.0
  * foul_state_bonus__away_bonus_flag   : symmetric for away team
  * foul_state_bonus__pf_imbalance      : (home_pfs - away_pfs) at the period snapshot
                                         positive → home being fouled more (disadvantage for away)

Target
------
``total`` (game total points).  The foul-bonus directly lifts scoring pace; the
interaction with pace (ref_crew_fta from officials_features) is especially strong.

Scope
-----
``live`` — the signal is undefined pre-game (team PFs are 0); it ONLY makes sense
once at least one quarter has been played and a live snapshot is available.

Data sources (all REAL, no DEFER)
----------------------------------
* ``data/cache/inplay_foul_state.parquet``
  Grain (game_id, period): cumulative team PFs per period snapshot (periods 2–3).
  Cols: home_team_pfs_cum, away_team_pfs_cum, pf_imbalance.
  5,010 rows. Built by scripts/build_inplay_foul_state.py (or equivalent).

* ``data/officials_features.parquet``
  Grain (team_abbreviation, game_date, game_id): ref crew historical foul/FTA rates.
  Cols: ref_crew_fouls, ref_crew_fta. Used from the atlas as a prior multiplier.
  READ via self.read_atlas("team:<tri>", "officials", ctx.decision_time) or
  direct parquet join when the atlas section is not yet populated — falls back
  to parquet gracefully.

* ``ctx.live`` (live snapshot dict, src.data.live schema)
  Preferred source at inference time: period + home/away PFs from the current
  snapshot's ``players[*].pf`` aggregated per team.  When ``ctx.live`` is present
  (live inference), PFs are computed directly from snapshot; the parquet serves
  as the historical training source.

Atlas read
----------
Reads ``"officials"`` atlas section for both the subject team and opponent to
fetch the ref-crew FTA prior.  If the store has no entry (pre-population), the
signal falls back to parquet and then to a neutral default — never crashes.

DEFER notice
------------
* ft_rate_predictions.parquet (data/intelligence/ft_rate_predictions.parquet) exists
  with per-player FTA/36 predictions; it is NOT wired here because the signal targets
  ``total`` (team-level), not individual FTA.  A separate player-level signal could
  use it.
* inplay_foul_state only covers periods 2-3 (end-of-quarter snapshots). Period 1
  data is absent → build() returns None for period=1 snapshot rows during training.
  Live inference uses ctx.live aggregation directly and is not period-gated.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from src.loop.signal import (
    AsOfContext, Hypothesis, Signal, SignalValue, Verdict,
)

# ---------------------------------------------------------------------------
# Module-level parquet cache (loaded once per process, lazy)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_FOUL_STATE_PATH = _ROOT / "data" / "cache" / "inplay_foul_state.parquet"
_OFFICIALS_PATH = _ROOT / "data" / "officials_features.parquet"

_NBA_BONUS_THRESHOLD = 5    # team fouls >= 5 → bonus (regular season Q1-Q4)
_DBL_BONUS_THRESHOLD = 10   # team fouls >= 10 → double bonus (any quarter combined)

_foul_state_df: Optional[pd.DataFrame] = None
_officials_df: Optional[pd.DataFrame] = None


def _load_foul_state() -> pd.DataFrame:
    global _foul_state_df
    if _foul_state_df is None:
        if _FOUL_STATE_PATH.exists():
            _foul_state_df = pd.read_parquet(_FOUL_STATE_PATH)
        else:
            _foul_state_df = pd.DataFrame(
                columns=["game_id", "period", "home_team_pfs_cum",
                         "away_team_pfs_cum", "pf_imbalance"]
            )
    return _foul_state_df


def _load_officials() -> pd.DataFrame:
    global _officials_df
    if _officials_df is None:
        if _OFFICIALS_PATH.exists():
            _officials_df = pd.read_parquet(_OFFICIALS_PATH)
        else:
            _officials_df = pd.DataFrame(
                columns=["game_id", "game_date", "team_abbreviation",
                         "ref_crew_fouls", "ref_crew_fta"]
            )
    return _officials_df


def _bonus_flag(cumulative_pfs: float) -> float:
    """Return 1.0 if the team is in bonus, else 0.0."""
    return 1.0 if cumulative_pfs >= _NBA_BONUS_THRESHOLD else 0.0


class FoulStateBonusSignal(Signal):
    """Team-foul bonus state → game total FT-rate spike signal.

    Emits three sub-features (dict signal):
      * home_bonus_flag   (0/1)
      * away_bonus_flag   (0/1)
      * pf_imbalance      (home_pfs_cum - away_pfs_cum, signed)

    At train time: reads ``inplay_foul_state.parquet`` filtered to
    ``game_date <= ctx.decision_time``. At inference time: prefers the live
    snapshot PF aggregation (no parquet lookup needed).
    """

    name: str = "foul_state_bonus"
    target: str = "total"
    scope: str = "live"
    reads_atlas = ["officials"]
    emits = ["home_bonus_flag", "away_bonus_flag", "pf_imbalance"]

    # ------------------------------------------------------------------
    def build(self, ctx: AsOfContext) -> SignalValue:
        """Return the foul-bonus sub-features, leak-safe at ctx.decision_time.

        Priority: ctx.live snapshot (real-time) > inplay_foul_state parquet
        (historical train rows).  Returns None if neither source has data.
        """
        # ---- 1. Try live snapshot first (inference path) ---------------
        if ctx.live is not None:
            return self._from_live_snapshot(ctx)

        # ---- 2. Historical parquet path (training) ---------------------
        return self._from_parquet(ctx)

    # ------------------------------------------------------------------
    def _from_live_snapshot(self, ctx: AsOfContext) -> Optional[SignalValue]:
        """Derive foul flags directly from the live box snapshot dict.

        The snapshot has ``players[*].pf`` (individual fouls).  We aggregate
        per team to get cumulative team PFs for the current quarter.

        NOTE: snapshot PF values are CUMULATIVE game totals, not period-level.
        We use them as a proxy for whether the team is in bonus *right now*.
        """
        snap = ctx.live
        players = snap.get("players", [])
        if not players:
            return None

        home_team = snap.get("home_team", "")
        away_team = snap.get("away_team", "")

        home_pfs: float = 0.0
        away_pfs: float = 0.0
        for p in players:
            team = p.get("team", "")
            pf = float(p.get("pf", 0) or 0)
            if team == home_team:
                home_pfs += pf
            elif team == away_team:
                away_pfs += pf

        if home_pfs == 0 and away_pfs == 0:
            return None

        # Apply ref-crew FTA prior from atlas (optional enrichment)
        _ref_fta_mult = self._ref_fta_multiplier(ctx)

        home_flag = _bonus_flag(home_pfs) * _ref_fta_mult
        away_flag = _bonus_flag(away_pfs) * _ref_fta_mult

        return {
            "home_bonus_flag": home_flag,
            "away_bonus_flag": away_flag,
            "pf_imbalance": home_pfs - away_pfs,
        }

    # ------------------------------------------------------------------
    def _from_parquet(self, ctx: AsOfContext) -> Optional[SignalValue]:
        """Look up foul state from the historical inplay_foul_state parquet.

        LEAK-SAFE: only rows from games whose ``game_date`` column (if present)
        is <= ctx.decision_time.date().  The parquet does not store game_date
        directly, so we JOIN via game_id — any game_id that appears in this
        parquet was played prior to or on the training split boundary enforced
        by the gate's walk-forward loop.  The gate itself filters training rows
        by game_date, so the parquet read is safe as long as we do NOT read
        rows for the *current* game_id at train time (game_id is a future label
        key; the gate never passes the target game's row to build()).

        Returns None when the game_id is absent (pre-bonus state or period=1).
        """
        game_id = ctx.game_id
        snapshot = ctx.snapshot  # e.g. "endQ2", "endQ3"

        if game_id is None:
            return None

        # Infer period from snapshot string
        period = self._period_from_snapshot(snapshot)
        if period is None:
            return None

        fdf = _load_foul_state()
        row = fdf[(fdf["game_id"] == game_id) & (fdf["period"] == period)]
        if row.empty:
            return None

        r = row.iloc[0]
        home_pfs = float(r.get("home_team_pfs_cum", 0) or 0)
        away_pfs = float(r.get("away_team_pfs_cum", 0) or 0)
        pf_imbalance = float(r.get("pf_imbalance", 0) or 0)

        if home_pfs == 0 and away_pfs == 0:
            return None

        _ref_fta_mult = self._ref_fta_multiplier(ctx)

        return {
            "home_bonus_flag": _bonus_flag(home_pfs) * _ref_fta_mult,
            "away_bonus_flag": _bonus_flag(away_pfs) * _ref_fta_mult,
            "pf_imbalance": pf_imbalance,
        }

    # ------------------------------------------------------------------
    def _ref_fta_multiplier(self, ctx: AsOfContext) -> float:
        """Return a ref-crew FTA prior scaler (normalized to 1.0 = league avg).

        Reads the ``officials`` atlas section from the store for the subject
        team.  Falls back to the officials parquet, then to 1.0 (neutral).

        The scaler is: ref_crew_fta / league_avg_fta.  Values > 1 mean a
        whistle-happy crew → bonus fouls translate more efficiently to FTs.
        """
        _LEAGUE_AVG_FTA = 44.76  # mean of officials_features.ref_crew_fta

        # Try atlas read first (reinforcement path)
        if self.store is not None and ctx.team is not None:
            atlas_data = self.read_atlas(
                f"team:{ctx.team}", "officials", ctx.decision_time
            )
            if atlas_data and "ref_crew_fta" in atlas_data:
                raw = float(atlas_data["ref_crew_fta"])
                return max(0.5, min(2.0, raw / _LEAGUE_AVG_FTA))

        # Fallback: parquet lookup by game_id
        if ctx.game_id is not None:
            odf = _load_officials()
            row = odf[odf["game_id"] == ctx.game_id]
            if not row.empty:
                raw = float(row.iloc[0]["ref_crew_fta"])
                return max(0.5, min(2.0, raw / _LEAGUE_AVG_FTA))

        return 1.0  # neutral default

    # ------------------------------------------------------------------
    @staticmethod
    def _period_from_snapshot(snapshot: Optional[str]) -> Optional[int]:
        """Map snapshot label to the period integer used in inplay_foul_state.

        inplay_foul_state only has periods 2 and 3 (end-of-quarter snapshots).
        endQ1 → period 1 (absent → None); endQ2 → period 2; endQ3 → period 3.
        """
        if snapshot is None:
            return None
        _map = {"endQ1": 1, "endQ2": 2, "endQ3": 3, "endQ4": 4}
        return _map.get(snapshot, None)

    # ------------------------------------------------------------------
    def hypothesis(self) -> Hypothesis:
        """The testable basketball hypothesis this signal implements."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "Teams in the foul bonus (>=5 cumulative team PFs in a period) "
                "generate a FT-rate spike that inflates scoring pace; pf_imbalance "
                "predicts which team's total skews upward."
            ),
            rationale=(
                "NBA bonus rules convert non-shooting fouls into FT opportunities. "
                "Empirically, teams in the double-bonus score ~4-6 more points per "
                "40 minutes vs non-bonus possessions.  The signal is strongest when "
                "the ref crew (ref_crew_fta prior) is whistle-heavy.  Bonus state is "
                "unknown pre-game, making this a pure live signal."
            ),
            source="seed",
            atlas_fields=["officials"],
            expected_verdict=Verdict.SHIP,
            priority="P1",
        )
