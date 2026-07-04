"""domains.baseball_npb.adapter -- NPBAdapter: PREGAME-ONLY two-way moneyline adapter.

Gate seam: feature_bundle() -> FeatureBundle so src.loop.gate.evaluate runs on
NPB data with ZERO kernel edits, mirroring domains.basketball_wnba.adapter.
WNBAAdapter (same minimal feature_bundle surface, per lane spec).

PREGAME-ONLY this wave (no in-game predict_live -- NPB has no live PBP/base-
out-state ingest built yet; that is genuinely out of scope for this lane,
which is pregame-Elo-only per the ADAPTER build spec). baseline_probability
(pregame Elo) is the full, real, leak-free signal this adapter offers.

TIES: a tied game (home_win=None/NaN in the underlying parquet) has NO winner
-- outcome() returns None for a tied event rather than fabricating a side,
and feature_bundle() drops tied rows from the target/signal arrays entirely
(the gate consumes a {0,1} target; a tie has no such label). This matches
ratings.py/pregame_gate.py's tie-exclusion discipline.

F5: imports ONLY stdlib, numpy, pandas, domains.baseball_npb.*,
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
SPORT_ID = "baseball_npb"
HOME_SIDE, AWAY_SIDE = "HOME", "AWAY"
GAMES_PARQUET = "data/domains/npb/npb_results.parquet"


class NPBAdapter:
    """PREGAME-ONLY NPB two-way moneyline adapter (no in-game predict_live)."""

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
            raise FileNotFoundError(f"npb_results.parquet not found at {path}.")
        df = pd.read_parquet(path)
        df["season"] = df["season"].astype(str)
        self._games = df
        return self._games

    def _event_id(self, row: pd.Series) -> str:
        """Synthetic event_id: npb.jp has no numeric game id in the scraped
        page, so (date, home_team, away_team) is the stable natural key --
        the SAME key ingest_npb.ingest_season dedups on."""
        d = pd.to_datetime(row["date"]).date().isoformat()
        return f"{d}|{row['home_team']}|{row['away_team']}"

    def list_events(self, date: dt.date) -> List[Dict]:
        """All games on date as lightweight event dicts."""
        df = self._get_games()
        day = df[pd.to_datetime(df["date"]).dt.date == date]
        return [
            {"sport": SPORT_ID, "event_id": self._event_id(row),
             "start_time_utc": dt.datetime.combine(date, dt.time(0, 0)),
             "entity_a": HOME_SIDE, "entity_b": AWAY_SIDE,
             "meta": {"home_team": str(row["home_team"]),
                      "away_team": str(row["away_team"]),
                      "season": str(row["season"]),
                      "tied": bool(row.get("tied", False))}}
            for _, row in day.iterrows()
        ]

    def market_snapshot(
        self, event: object, kind: Literal["open", "close"]
    ) -> Optional[object]:
        """Always returns None: no Kalshi historical close-price capture
        exists yet for NPB (KXNPBGAME is live on Kalshi NOW, but capture only
        starts once a capture daemon is wired to it) -- honestly PENDING,
        never faked. See pregame_gate_verdict.json."""
        return None

    def outcome(self, event: object) -> Optional[object]:
        """Settled Outcome dict: winner='a' (home wins) or 'b' (away wins).

        A tied game returns None -- there is no winner to report, matching
        the ratings/gate tie-exclusion discipline (never fabricate a side)."""
        try:
            df = self._get_games()
        except FileNotFoundError:
            return None
        eid = event.get("event_id", "") if isinstance(event, dict) else getattr(event, "event_id", "")  # type: ignore[union-attr]
        for _, row in df.iterrows():
            if self._event_id(row) == str(eid):
                hw = row["home_win"]
                if pd.isna(hw):
                    return None  # tied game -- no winner
                return {"event": event, "winner": "a" if float(hw) >= 0.5 else "b",
                        "settled_at": dt.datetime.combine(
                            pd.to_datetime(row["date"]).date(), dt.time(23, 59)),
                        "meta": {"home_win": float(hw)}}
        return None

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
        Tied rows (home_win=NaN) are DROPPED from every array -- there is no
        {0,1} label for a draw.
        lines/closing = None (no Kalshi historical close-price capture exists
        yet for NPB -- honestly absent, see market_snapshot docstring).
        """
        games_df = self._get_games()
        if seasons:
            games_df = games_df[games_df["season"].isin([str(s) for s in seasons])]

        wf = walk_forward_elo(games_df.copy())

        rows_base, rows_sig, rows_tgt, rows_dates = [], [], [], []
        for _, row in wf.iterrows():
            tgt = row.get("home_win", np.nan)
            if pd.isna(tgt):
                continue  # tied game -- no {0,1} label, excluded honestly
            rows_base.append([float(row["elo_home"]), float(row["elo_away"])])
            rows_sig.append(float(row["p_home_elo"]))
            rows_tgt.append(float(tgt))
            rows_dates.append(str(pd.to_datetime(row["date"]).date()))

        if not rows_base:
            raise ValueError(
                f"feature_bundle: no rows for seasons={list(seasons or [])}, "
                f"league_filter={league_filter!r}. "
                "Check that npb_results.parquet covers those filters."
            )

        return FeatureBundle(
            base=np.array(rows_base, dtype=float),
            signal_col=np.array(rows_sig, dtype=float),
            target=np.array(rows_tgt, dtype=float),
            dates=rows_dates,
            lines=None,
            closing=None,  # no true close yet -- gate falls back to non-blocking CLV
        )


__all__ = ["NPBAdapter", "SPORT_ID"]
