"""domains.mlb.adapter — MLBAdapter: MARKET_ONLY two-way moneyline adapter.

Gate seam: feature_bundle() returns a FeatureBundle so src.loop.gate.evaluate
runs on MLB data with ZERO kernel edits.

F5 compliance: imports ONLY stdlib, numpy, pandas, domains.mlb.*,
src.loop.gate.FeatureBundle, src.loop.signal.  Zero other domain/src imports.
PRIVATE: never tracked publicly.  SBR data for personal/research use only.
"""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Dict, List, Literal, Optional, Sequence

import numpy as np
import pandas as pd

from .config import (
    ELO_MEAN, GAMES_PARQUET, ODDS_PARQUET, AWAY_SIDE, HOME_SIDE, SPORT_ID,
    EventRef, MarketSnapshot, Outcome,
)
from .ratings import EloState, _p_home, elo_state_asof, walk_forward_elo
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

class MLBAdapter:
    """MARKET_ONLY MLB two-way moneyline adapter (sportsbookreviewsonline archive)."""

    sport: str = SPORT_ID

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        games_df: Optional[pd.DataFrame] = None,
        odds_df: Optional[pd.DataFrame] = None,
    ) -> None:
        self._root = repo_root or Path(__file__).resolve().parents[2]
        self._games: Optional[pd.DataFrame] = games_df
        self._odds: Optional[pd.DataFrame] = odds_df
        self._state_cache: Dict[dt.date, EloState] = {}

    # --- lazy loaders ---

    def _get_games(self) -> pd.DataFrame:
        if self._games is not None:
            return self._games
        path = self._root / GAMES_PARQUET
        if not path.exists():
            raise FileNotFoundError(f"games.parquet not found at {path}.")
        self._games = pd.read_parquet(path)
        return self._games

    def _get_odds(self) -> pd.DataFrame:
        if self._odds is not None:
            return self._odds
        path = self._root / ODDS_PARQUET
        if not path.exists():
            raise FileNotFoundError(f"odds.parquet not found at {path}.")
        self._odds = pd.read_parquet(path)
        return self._odds

    def _elo_as_of(self, as_of: dt.date) -> EloState:
        """Cached EloState from games strictly before as_of."""
        if as_of not in self._state_cache:
            self._state_cache[as_of] = elo_state_asof(self._get_games(), as_of)
        return self._state_cache[as_of]

    # --- protocol ---

    def list_events(self, date: dt.date) -> List[EventRef]:
        """All games on date as EventRef objects (entity_a=HOME_SIDE, entity_b=AWAY_SIDE)."""
        df = self._get_games()
        day = df[pd.to_datetime(df["date"]).dt.date == date]
        events: List[EventRef] = []
        for _, row in day.iterrows():
            events.append(EventRef(
                sport=SPORT_ID,
                event_id=str(row["event_id"]),
                start_time_utc=dt.datetime.combine(date, dt.time(12, 0)),
                entity_a=HOME_SIDE,
                entity_b=AWAY_SIDE,
                meta={
                    "home_team": str(row["home_team"]),
                    "away_team": str(row["away_team"]),
                    "season": int(row["season"]),
                    "game_seq": int(row.get("game_seq", 1)),
                    "home_league": str(row.get("home_league", "")),
                },
            ))
        return events

    def market_snapshot(
        self, event: EventRef, kind: Literal["open", "close"]
    ) -> Optional[MarketSnapshot]:
        """Moneyline snapshot; kind='open'->dec_open_*, 'close'->dec_close_*.
        Returns None when row absent or any price NA/<=1.0."""
        try:
            odds = self._get_odds()
        except FileNotFoundError:
            return None
        row_df = odds[odds["event_id"] == event.event_id]
        if row_df.empty:
            return None
        row = row_df.iloc[0]
        hc, ac = (("dec_open_home", "dec_open_away") if kind == "open"
                  else ("dec_close_home", "dec_close_away"))
        try:
            hp, ap = float(row.get(hc, np.nan)), float(row.get(ac, np.nan))
        except (TypeError, ValueError):
            return None
        if pd.isna(hp) or pd.isna(ap) or hp <= 1.0 or ap <= 1.0:
            return None
        return MarketSnapshot(event=event, kind=kind, price_a=hp, price_b=ap,
                              book="sbro_archive")

    def outcome(self, event: EventRef) -> Optional[Outcome]:
        """Settled Outcome: winner='a' if home_runs > away_runs, else 'b'."""
        try:
            df = self._get_games()
        except FileNotFoundError:
            return None
        row_df = df[df["event_id"] == event.event_id]
        if row_df.empty:
            return None
        row = row_df.iloc[0]
        hr, ar = int(row["home_runs"]), int(row["away_runs"])
        winner: Literal["a", "b"] = "a" if hr > ar else "b"
        return Outcome(
            event=event, winner=winner,
            settled_at=dt.datetime.combine(pd.to_datetime(row["date"]).date(),
                                           dt.time(23, 59)),
            meta={"home_runs": hr, "away_runs": ar},
        )

    def baseline_probability(self, event: EventRef, as_of: dt.datetime) -> float:
        """Leak-free P(home wins) via Elo; _p_home applies ELO_HFA internally."""
        state = self._elo_as_of(as_of.date())
        home, away = str(event.meta["home_team"]), str(event.meta["away_team"])
        return float(_p_home(state.elo.get(home, ELO_MEAN),
                              state.elo.get(away, ELO_MEAN)))

    def feature_bundle(
        self,
        hypothesis: Hypothesis,
        seasons: Optional[Sequence[int]] = None,
        *,
        league_filter: Optional[str] = None,
    ) -> FeatureBundle:
        """Gate-valid FeatureBundle.

        Base (6 cols, all strictly pre-game):
            [elo_home, elo_away, elo_diff_hfa, rest_days_home, rest_days_away, h2h_rate]
        signal_col = p_home_elo (Elo P(home wins)).
        target     = target_home_win in {0,1}.
        lines/closing = devigged open/close P(home); None when all-NaN.
        """
        games_df = self._get_games()

        # WARM REPLAY: replay Elo (and rest/h2h context) over the FULL corpus
        # so a non-prefix season subset (e.g. seasons=[2015]) inherits the
        # carried-forward Elo/rest/h2h history instead of replaying from a cold
        # 1500. Filter to the requested seasons / league AFTER the replay.
        wf = _add_context(walk_forward_elo(games_df))
        if seasons:
            wf = wf[wf["season"].isin(seasons)]
        if league_filter is not None:
            wf = wf[wf["home_league"] == league_filter]

        try:
            odds_df = self._get_odds()
            has_odds = True
        except FileNotFoundError:
            has_odds = False
            odds_df = pd.DataFrame()

        # Pre-merge odds: one left-merge before the loop (O(N+M) vs O(N*M)).
        # Only select the columns _devig2_home reads to avoid name collisions.
        # drop_duplicates(keep="first") replicates the original .iloc[0] behaviour.
        _ODDS_COLS = ["event_id", "dec_open_home", "dec_open_away",
                      "dec_close_home", "dec_close_away"]
        if has_odds and not odds_df.empty:
            _odds_sel = odds_df[[c for c in _ODDS_COLS if c in odds_df.columns]].copy()
            _odds_sel = _odds_sel.drop_duplicates("event_id", keep="first")
            wf = wf.merge(_odds_sel, on="event_id", how="left")
        else:
            for _c in _ODDS_COLS[1:]:
                if _c not in wf.columns:
                    wf[_c] = np.nan

        rows_base: List[List[float]] = []
        rows_sig: List[float] = []
        rows_tgt: List[float] = []
        rows_dates: List[str] = []
        rows_lines: List[float] = []
        rows_close: List[float] = []

        for _, row in wf.iterrows():
            tgt = row.get("target_home_win", np.nan)
            if pd.isna(tgt):
                continue
            # Odds columns already merged onto row (NaN when no match)
            lv = _devig2_home(row.get("dec_open_home"), row.get("dec_open_away"))
            cv = _devig2_home(row.get("dec_close_home"), row.get("dec_close_away"))
            rows_base.append([float(row["elo_home"]), float(row["elo_away"]),
                               float(row["elo_diff_hfa"]),
                               float(row.get("rest_days_home", 5.0)),
                               float(row.get("rest_days_away", 5.0)),
                               float(row.get("h2h_rate", 0.5))])
            rows_sig.append(float(row["p_home_elo"]))
            rows_tgt.append(float(tgt))
            rows_dates.append(str(pd.to_datetime(row["date"]).date()))
            rows_lines.append(lv)
            rows_close.append(cv)

        if not rows_base:
            raise ValueError(
                f"feature_bundle: no rows for seasons={list(seasons or [])}, "
                f"league_filter={league_filter!r}. "
                "Check that games.parquet covers those filters."
            )

        la = np.array(rows_lines, dtype=float)
        ca = np.array(rows_close, dtype=float)
        return FeatureBundle(
            base=np.array(rows_base, dtype=float),
            signal_col=np.array(rows_sig, dtype=float),
            target=np.array(rows_tgt, dtype=float),
            dates=rows_dates,
            lines=la if not np.all(np.isnan(la)) else None,
            closing=ca if not np.all(np.isnan(ca)) else None,
        )


# --- module-level helpers ---

def _add_context(wf: pd.DataFrame) -> pd.DataFrame:
    """Append leak-free context cols (snapshot pre-game, update post-game).

    Added: rest_days_home, rest_days_away (capped 10, default 5),
           recent_win10_home (trailing-10 win rate; NaN if <10 games),
           h2h_rate (home-win rate vs this away-team; default 0.5),
           h2h_n (count of prior meetings).
    """
    wf = wf.copy()
    wf["_date"] = pd.to_datetime(wf["date"]).dt.date
    last_seen: Dict[str, dt.date] = {}
    team_results: Dict[str, List[float]] = {}
    h2h: Dict[frozenset, List[float]] = {}

    rh, ra, w10, hr_rate, hr_n = [], [], [], [], []
    for _, row in wf.iterrows():
        d, home, away = row["_date"], str(row["home_team"]), str(row["away_team"])
        rh.append(min((d - last_seen[home]).days, 10) if home in last_seen else 5.0)
        ra.append(min((d - last_seen[away]).days, 10) if away in last_seen else 5.0)
        hist = team_results.get(home, [])
        w10.append(float(np.mean(hist[-10:])) if len(hist) >= 10 else float("nan"))
        pk: frozenset = frozenset([home, away])
        ph = h2h.get(pk, [])
        hr_n.append(len(ph))
        hr_rate.append(float(np.mean(ph)) if ph else 0.5)
        # post-game update
        last_seen[home] = last_seen[away] = d
        hw = 1.0 if float(row["home_runs"]) > float(row["away_runs"]) else 0.0
        team_results.setdefault(home, []).append(hw)
        team_results.setdefault(away, []).append(1.0 - hw)
        h2h.setdefault(pk, []).append(hw)

    wf["rest_days_home"] = rh
    wf["rest_days_away"] = ra
    wf["recent_win10_home"] = w10
    wf["h2h_rate"] = hr_rate
    wf["h2h_n"] = hr_n
    wf.drop(columns=["_date"], inplace=True)
    return wf


def _devig2_home(home_dec: object, away_dec: object) -> float:
    """Devigged P(home wins) = imp_home / (imp_home + imp_away). NaN if invalid."""
    try:
        hp, ap = float(home_dec), float(away_dec)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float("nan")
    if pd.isna(hp) or pd.isna(ap) or hp <= 1.0 or ap <= 1.0:
        return float("nan")
    return float((1.0 / hp) / (1.0 / hp + 1.0 / ap))
