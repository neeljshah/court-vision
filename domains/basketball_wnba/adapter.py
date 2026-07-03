"""domains.basketball_wnba.adapter -- WNBAAdapter: PREGAME-ONLY two-way moneyline adapter.

Gate seam: feature_bundle() -> FeatureBundle so src.loop.gate.evaluate runs on
WNBA data with ZERO kernel edits, mirroring domains.basketball_nba.adapter.NBAAdapter.

PREGAME-ONLY this wave (in-game live blend deferred -- see not_done in the wave
report): domains.basketball_nba.ingame_blend_plive hardcodes NBA's 48-minute
(4x12) regulation length (_REG_SEC = 2880.0) and consumes a live PBP foul-state
feed (players dict with team/pf) that this wave does not build for WNBA (WNBA
plays 4x10-minute quarters, a different _REG_SEC, and needs its OWN foul-state
ingest before that blend could be safely reused). predict_live is therefore
ABSENT here rather than silently reusing NBA's clock constant. baseline_probability
(pregame Elo) is the full, real, leak-free signal this adapter offers.

F5: imports ONLY stdlib, numpy, pandas, domains.basketball_wnba.*,
src.loop.gate.FeatureBundle, src.loop.signal. PRIVATE: never tracked publicly.
"""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Dict, List, Literal, Optional, Sequence

import numpy as np
import pandas as pd

from .elo_config import ELO_MEAN
from .ratings import walk_forward_elo
from src.loop.gate import FeatureBundle
from src.loop.signal import Hypothesis

logger = logging.getLogger(__name__)
SPORT_ID = "basketball_wnba"
HOME_SIDE, AWAY_SIDE = "HOME", "AWAY"
GAMES_PARQUET = "data/domains/wnba/espn_scoreboard.parquet"


class WNBAAdapter:
    """PREGAME-ONLY WNBA two-way moneyline adapter (no in-game predict_live)."""

    sport: str = SPORT_ID

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        games_df: Optional[pd.DataFrame] = None,
    ) -> None:
        self._root = repo_root or Path(__file__).resolve().parents[2]
        self._games: Optional[pd.DataFrame] = games_df

    def _get_games(self) -> pd.DataFrame:
        if self._games is not None:
            return self._games
        path = self._root / GAMES_PARQUET
        if not path.exists():
            raise FileNotFoundError(f"espn_scoreboard.parquet not found at {path}.")
        df = pd.read_parquet(path)
        df["season"] = df["season"].astype(str)
        self._games = df
        return self._games

    def list_events(self, date: dt.date) -> List[Dict]:
        """All games on date as lightweight event dicts."""
        df = self._get_games()
        day = df[pd.to_datetime(df["date"]).dt.date == date]
        return [
            {"sport": SPORT_ID, "event_id": str(row["event_id"]),
             "start_time_utc": dt.datetime.combine(date, dt.time(0, 0)),
             "entity_a": HOME_SIDE, "entity_b": AWAY_SIDE,
             "meta": {"home_team": str(row["home_team"]),
                      "away_team": str(row["away_team"]),
                      "season": str(row["season"])}}
            for _, row in day.iterrows()
        ]

    def market_snapshot(
        self, event: object, kind: Literal["open", "close"]
    ) -> Optional[object]:
        """Always returns None: no Kalshi historical close data exists yet for
        WNBA (capture only starts once the kalshi_series_spec entry goes live) --
        this is honestly PENDING, never faked. See pregame_gate_verdict.json."""
        return None

    def outcome(self, event: object) -> Optional[object]:
        """Settled Outcome dict: winner='a' (home wins) or 'b' (away wins)."""
        try:
            df = self._get_games()
        except FileNotFoundError:
            return None
        eid = event.get("event_id", "") if isinstance(event, dict) else getattr(event, "event_id", "")  # type: ignore[union-attr]
        row_df = df[df["event_id"].astype(str) == str(eid)]
        if row_df.empty:
            return None
        row = row_df.iloc[0]
        hw = float(row["home_win"])
        return {"event": event, "winner": "a" if hw >= 0.5 else "b",
                "settled_at": dt.datetime.combine(
                    pd.to_datetime(row["date"]).date(), dt.time(23, 59)),
                "meta": {"home_win": hw}}

    def baseline_probability(self, event: object, as_of: dt.datetime) -> float:
        """Leak-free P(home wins) via Elo (all games strictly before as_of)."""
        from .ratings import replay, _p_home
        state = replay(self._get_games(), until=as_of.date())
        meta = event.get("meta", {}) if isinstance(event, dict) else getattr(event, "meta", {})  # type: ignore[union-attr]
        return float(_p_home(state.elo.get(str(meta.get("home_team", "")), ELO_MEAN),
                              state.elo.get(str(meta.get("away_team", "")), ELO_MEAN)))

    def feature_bundle(
        self,
        hypothesis: Hypothesis,
        seasons: Optional[Sequence[str]] = None,
        *,
        league_filter: Optional[str] = None,
    ) -> FeatureBundle:
        """Gate-valid FeatureBundle.

        Base (2 cols, strictly pre-game): [elo_home, elo_away].
        signal_col = p_home_elo. target = home_win {0,1}.
        lines/closing = None (no Kalshi historical close data exists yet for
        WNBA -- honestly absent, see market_snapshot docstring).
        """
        games_df = self._get_games()
        if seasons:
            games_df = games_df[games_df["season"].isin([str(s) for s in seasons])]

        wf = walk_forward_elo(games_df.copy())

        rows_base, rows_sig, rows_tgt, rows_dates = [], [], [], []
        for _, row in wf.iterrows():
            tgt = row.get("home_win", np.nan)
            if pd.isna(tgt):
                continue
            rows_base.append([float(row["elo_home"]), float(row["elo_away"])])
            rows_sig.append(float(row["p_home_elo"]))
            rows_tgt.append(float(tgt))
            rows_dates.append(str(pd.to_datetime(row["date"]).date()))

        if not rows_base:
            raise ValueError(
                f"feature_bundle: no rows for seasons={list(seasons or [])}, "
                f"league_filter={league_filter!r}. "
                "Check that espn_scoreboard.parquet covers those filters."
            )

        return FeatureBundle(
            base=np.array(rows_base, dtype=float),
            signal_col=np.array(rows_sig, dtype=float),
            target=np.array(rows_tgt, dtype=float),
            dates=rows_dates,
            lines=None,
            closing=None,  # no true close yet -- gate falls back to non-blocking CLV
        )


__all__ = ["WNBAAdapter", "SPORT_ID"]
