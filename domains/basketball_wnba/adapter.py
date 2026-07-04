"""domains.basketball_wnba.adapter -- WNBAAdapter: two-way moneyline + in-game adapter.

Gate seam: feature_bundle() -> FeatureBundle so src.loop.gate.evaluate runs on
WNBA data with ZERO kernel edits, mirroring domains.basketball_nba.adapter.NBAAdapter.

LANE 4 (this wave): predict_live is WIRED via domains.basketball_wnba.ingame_blend
.blend_prob, now the "anchored" family (logit(p0)*w_prior(t) + k*score_diff/
sqrt(minutes_remaining)) adopted after a cross-corpus family settlement -- see
ingame_blend.py's module docstring + ingame_blend_families.py + data/domains/
wnba/ingame_blend_check.json (v2) for the fit/validate/OOS trail. This REPLACES
wave-2's fixed-constant blend (still importable, unchanged, as
ingame_blend.blend_prob_fixed_legacy) after the honest wave-2 check showed it
losing to a naive score-diff sigmoid at half/end_q3. Time-scale constants
(REG_SEC=2400.0, 4x10min) are re-derived rather than borrowing NBA's 2880.0,
and there is still no foul-state term (WNBA has no live foul-state ingest; see
ingame_blend.py module docstring for the honest degrade). baseline_probability
(pregame Elo) remains the full, real, leak-free pregame signal; predict_live
blends it with realized score state.

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
from .ingame_blend import LiveState, blend_prob, is_buzzer
from src.loop.gate import FeatureBundle
from src.loop.signal import Hypothesis

logger = logging.getLogger(__name__)
SPORT_ID = "basketball_wnba"
HOME_SIDE, AWAY_SIDE = "HOME", "AWAY"
GAMES_PARQUET = "data/domains/wnba/espn_scoreboard.parquet"


class WNBAAdapter:
    """WNBA two-way moneyline adapter: pregame Elo + in-game live blend."""

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

    def predict_live(
        self,
        home: str,
        away: str,
        as_of: dt.datetime,
        period: int,
        clock_s: float,
        home_score: float,
        away_score: float,
        *,
        neutral_site: bool = False,
    ) -> Dict:
        """In-game P(home wins) = pregame Elo prior blended with realized score
        state via domains.basketball_wnba.ingame_blend.blend_prob.

        p0 is the SAME leak-free pregame Elo probability baseline_probability(as_of)
        reports (all games strictly before as_of) -- coherent with the pregame
        signal, not a re-derivation. neutral_site is accepted for API parity with
        other domains' predict_live (soccer_intl); the Elo replay itself has no
        home-tilt term to drop for WNBA (HFA is baked into _p_home via ELO_HFA),
        so neutral_site is recorded on the output but does not alter p0 here --
        honestly reported via the neutral_site_adjusted flag (always False) rather
        than silently ignored.

        BUZZER FIX (mirrors domains.basketball_nba.test_nba_live_buzzer.py): at the
        exact final buzzer (period==4, clock_s<=0) with a DECIDED score, p_home_win
        is snapped to the EXACT 0.0/1.0 rather than the blend's asymptotic sigmoid
        value -- a finished result is deterministic, not a probabilistic forecast.
        A buzzer tie (score_diff==0 at 0:00) is NOT a buzzer per is_buzzer's
        contract (the game continues to OT) and is left to the blend (-> 0.5).
        """
        p0 = self.baseline_probability(
            {"meta": {"home_team": home, "away_team": away}}, as_of)
        state = LiveState(period=int(period), clock_s=float(clock_s),
                           home_score=float(home_score), away_score=float(away_score))
        score_diff = float(home_score) - float(away_score)
        if is_buzzer(state) and score_diff != 0.0:
            p_live = 1.0 if score_diff > 0.0 else 0.0
        else:
            p_live = blend_prob(p0, state)
        return {
            "sport": SPORT_ID, "home": home, "away": away,
            "period": int(period), "clock_s": float(clock_s),
            "score": (float(home_score), float(away_score)),
            "p_home_win": round(float(p_live), 4),
            "p_away_win": round(1.0 - float(p_live), 4),
            "pregame_p_home": round(float(p0), 4),
            "neutral_site": bool(neutral_site),
            "neutral_site_adjusted": False,
            "honest_note": (
                "In-game = pregame WNBA Elo win-prob (leak-free, as-of) blended "
                "with realized score state via the 'anchored' family logit blend "
                "(REG_SEC=2400.0, cross-corpus-selected over fixed/naive/"
                "time_scaled -- see ingame_blend_check.json v2; no foul-state "
                "term -- WNBA has no live foul feed, honestly degraded out "
                "rather than faked). Calibration only; no $ edge claimed."
            ),
        }

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
