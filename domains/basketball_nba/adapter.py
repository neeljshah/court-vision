"""domains.basketball_nba.adapter — NBAAdapter: MARKET_ONLY two-way moneyline adapter.

Gate seam: feature_bundle() -> FeatureBundle so src.loop.gate.evaluate runs on
NBA data with ZERO kernel edits.  F5: imports ONLY stdlib, numpy, pandas,
domains.basketball_nba.*, src.loop.gate.FeatureBundle, src.loop.signal.
PRIVATE: never tracked publicly.
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
SPORT_ID = "basketball_nba"
HOME_SIDE, AWAY_SIDE = "HOME", "AWAY"
GAMES_PARQUET = "data/domains/basketball_nba/games.parquet"
ODDS_PARQUET  = "data/domains/basketball_nba/odds.parquet"


def _verify_kernel_import_weight() -> None:
    import sys
    heavy = {"torch", "cv2", "tensorflow"}
    loaded = set(sys.modules) & heavy
    if loaded:  # pragma: no cover
        logger.warning("Heavy modules %s loaded; gate runs on CPU fallback.", loaded)


_verify_kernel_import_weight()


class NBAAdapter:
    """MARKET_ONLY NBA two-way moneyline adapter."""

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

    def list_events(self, date: dt.date) -> List[Dict]:
        """All games on date as lightweight event dicts."""
        df = self._get_games()
        day = df[pd.to_datetime(df["date"]).dt.date == date]
        return [
            {"sport": SPORT_ID, "event_id": str(r["game_id"]),
             "start_time_utc": dt.datetime.combine(date, dt.time(0, 0)),
             "entity_a": HOME_SIDE, "entity_b": AWAY_SIDE,
             "meta": {"home_team": str(r["home_team"]),
                      "away_team": str(r["away_team"]),
                      "season": str(r["season"])}}
            for _, r in day.iterrows()
        ]

    def market_snapshot(
        self, event: object, kind: Literal["open", "close"]
    ) -> Optional[object]:
        """Always returns None: NBA odds are date+team keyed, not game_id keyed.

        There is no per-event open/close snapshot to return here; closing-line
        CLV is joined by (date, home_team, away_team) inside feature_bundle().
        """
        return None

    def outcome(self, event: object) -> Optional[object]:
        """Settled Outcome dict: winner='a' (home wins) or 'b' (away wins)."""
        try:
            df = self._get_games()
        except FileNotFoundError:
            return None
        gid = event.get("event_id", "") if isinstance(event, dict) else getattr(event, "event_id", "")  # type: ignore[union-attr]
        row_df = df[df["game_id"].astype(str) == str(gid)]
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

        Base (8 cols, all strictly pre-game):
            [elo_home, elo_away, elo_diff_hfa, rest_days_home, rest_days_away,
             home_b2b, away_b2b, rolling_win10_home]
        signal_col = p_home_elo.  target = home_win {0,1}.
        lines/closing = devigged home-win prob from odds (2025-26 only; NaN elsewhere).
        """
        games_df = self._get_games()
        if seasons:
            games_df = games_df[games_df["season"].isin(seasons)]

        # walk_forward_elo calls int(season); NBA seasons are "YYYY-YY" strings.
        # Substitute start-year int for regression detection, then restore.
        games_df = games_df.copy()
        games_df["_season_orig"] = games_df["season"]
        games_df["season"] = games_df["season"].apply(_season_to_int)
        wf = _add_rolling_win10(walk_forward_elo(games_df))
        wf["season"] = wf["_season_orig"]
        wf.drop(columns=["_season_orig"], inplace=True)

        try:
            odds_df = self._get_odds()
            has_odds = not odds_df.empty
        except FileNotFoundError:
            has_odds = False
            odds_df = pd.DataFrame()

        if has_odds:
            _o = odds_df[["date", "home_team", "away_team", "home_ml", "away_ml"]].copy()
            _o["date"] = _o["date"].astype(str)
            wf["_ds"] = pd.to_datetime(wf["date"]).dt.date.astype(str)
            wf = wf.merge(_o.rename(columns={"date": "_ds"}),
                          on=["_ds", "home_team", "away_team"], how="left")
            wf.drop(columns=["_ds"], inplace=True)
        else:
            wf["home_ml"] = np.nan
            wf["away_ml"] = np.nan

        rows_base, rows_sig, rows_tgt, rows_dates, rows_lv = [], [], [], [], []
        for _, row in wf.iterrows():
            tgt = row.get("home_win", np.nan)
            if pd.isna(tgt):
                continue
            lv = _devig_am(row.get("home_ml"), row.get("away_ml"))
            rows_base.append([
                float(row["elo_home"]), float(row["elo_away"]),
                float(row["elo_diff_hfa"]),
                float(row.get("rest_days_home", 5.0)),
                float(row.get("rest_days_away", 5.0)),
                float(bool(row.get("home_b2b", False))),
                float(bool(row.get("away_b2b", False))),
                float(row.get("rolling_win10_home", 0.5)),
            ])
            rows_sig.append(float(row["p_home_elo"]))
            rows_tgt.append(float(tgt))
            rows_dates.append(str(pd.to_datetime(row["date"]).date()))
            rows_lv.append(lv)

        if not rows_base:
            raise ValueError(
                f"feature_bundle: no rows for seasons={list(seasons or [])}, "
                f"league_filter={league_filter!r}. "
                "Check that games.parquet covers those filters."
            )

        la = np.array(rows_lv, dtype=float)
        return FeatureBundle(
            base=np.array(rows_base, dtype=float),
            signal_col=np.array(rows_sig, dtype=float),
            target=np.array(rows_tgt, dtype=float),
            dates=rows_dates,
            lines=None,  # no true opener; gate falls back to non-blocking CLV
            closing=la if not np.all(np.isnan(la)) else None,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _season_to_int(season: object) -> int:
    """'2022-23' -> 2022; '2022' -> 2022."""
    s = str(season)
    return int(s.split("-")[0]) if "-" in s else (int(s) if s.isdigit() else 0)


def _am_to_decimal(american: object) -> float:
    try:
        a = float(american)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float("nan")
    if pd.isna(a) or abs(a) < 100:
        return float("nan")
    return 1.0 + (a / 100.0 if a > 0 else 100.0 / abs(a))


def _devig_am(home_am: object, away_am: object) -> float:
    """Devigged P(home wins) from American moneylines. NaN if invalid."""
    hp, ap = _am_to_decimal(home_am), _am_to_decimal(away_am)
    if pd.isna(hp) or pd.isna(ap) or hp <= 1.0 or ap <= 1.0:
        return float("nan")
    return float((1.0 / hp) / (1.0 / hp + 1.0 / ap))


def _add_rolling_win10(wf: pd.DataFrame) -> pd.DataFrame:
    """Add rolling_win10_home: trailing-10-game home win rate, strictly pre-game.

    Before any history: 0.5 prior.  After 1–9 games: expanding mean.
    After 10+ games: rolling-10 mean.  Post-game update runs AFTER snapshot.
    """
    wf = wf.copy()
    team_results: Dict[str, List[float]] = {}
    rolling: List[float] = []
    for _, row in wf.iterrows():
        home, away = str(row["home_team"]), str(row["away_team"])
        hist = team_results.get(home, [])
        rolling.append(0.5 if not hist else float(np.mean(hist[-10:])))
        hw = float(row["home_win"])
        team_results.setdefault(home, []).append(hw)
        team_results.setdefault(away, []).append(1.0 - hw)
    wf["rolling_win10_home"] = rolling
    return wf
