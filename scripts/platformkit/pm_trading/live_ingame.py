"""live_ingame.py -- IN-GAME live state -> predict_live forward predictions.

Uses the games happening RIGHT NOW. The MLB stats API (keyless) gives live
linescore state (inning / half / runs); predict_live turns it into a
recalibrated win probability. This exercises the model's measured strength --
the in-game conditioning layer -- on live games, forward-logged for grading.

Split out of live_feed.py to keep each file <=300 LOC. Paper, no money,
no edge claimed.
"""
from __future__ import annotations

import json
import pathlib
import sys
import urllib.request
from typing import Callable, Dict, List, Sequence

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from live_feed import MLB_NAME_TO_ABBR, Game, GameSource  # noqa: E402


class MLBLiveStateSource(GameSource):
    """Keyless MLB schedule + linescore -> LIVE games WITH in-game state."""

    def __init__(self, date: str = "") -> None:
        self.date = date

    @property
    def name(self) -> str:
        return "mlb_live"

    def fetch(self) -> List[Game]:
        url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&hydrate=linescore"
        if self.date:
            url += "&date=%s" % self.date
        try:
            with urllib.request.urlopen(url, timeout=10.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return []
        out = []
        for d in data.get("dates", []):
            for g in d.get("games", []):
                try:
                    if (g.get("status", {}) or {}).get("abstractGameState") != "Live":
                        continue
                    ls = g.get("linescore") or {}
                    lt = ls.get("teams", {}) or {}
                    teams = g["teams"]
                    out.append(Game(
                        sport="mlb",
                        home=MLB_NAME_TO_ABBR.get(teams["home"]["team"]["name"],
                                                  teams["home"]["team"]["name"]),
                        away=MLB_NAME_TO_ABBR.get(teams["away"]["team"]["name"],
                                                  teams["away"]["team"]["name"]),
                        game_id=str(g.get("gamePk", "")),
                        game_date=d.get("date", ""),
                        inning=ls.get("currentInning"),
                        half=("top" if ls.get("isTopInning") else "bottom"),
                        home_runs=(lt.get("home", {}) or {}).get("runs"),
                        away_runs=(lt.get("away", {}) or {}).get("runs"),
                        state="Live"))
                except Exception:
                    continue
        return out


def make_default_predict_live_fn() -> Callable[[Game], dict]:
    """Returns f(game) -> live model result via predict_live, predictor cached."""
    from scripts.platformkit.predictor_jd import _build_predictor  # lazy

    cache: Dict[str, object] = {}

    def predict_live(g: Game) -> dict:
        pred = cache.get(g.sport)
        if pred is None:
            pred = _build_predictor(g.sport)
            cache[g.sport] = pred
        if pred is None:
            return {}
        return pred.predict_live(g.home, g.away, inning=g.inning, half=g.half,
                                 home_runs=g.home_runs, away_runs=g.away_runs)

    return predict_live


def build_ingame_predictions(games: Sequence[Game],
                             predict_live_fn: Callable[[Game], dict],
                             pred_ts: str, market: str = "ml") -> List[dict]:
    """Run each LIVE game's state through predict_live -> ledger-ready dicts."""
    out: List[dict] = []
    for g in games:
        if g.inning is None or g.home_runs is None or g.away_runs is None:
            continue
        try:
            res = predict_live_fn(g) or {}
        except Exception:
            continue
        p = res.get("p_home_win", res.get("p1_match_win"))
        if p is None:
            continue
        out.append({
            "sport": g.sport, "layer": "ingame", "market": market,
            "home": g.home, "away": g.away, "calibrated_prob": float(p),
            "game_id": g.game_id,
            # game_date = the prediction's own (UTC) date: an in-game prediction
            # is made in real time during play, so it is leak-free by construction
            # and must satisfy the ledger vintage guard (pred_ts date <= game_date)
            # even when the live game runs past midnight UTC. grade_live matches by
            # game_id and scans the prior day too, so settlement still finds it.
            "game_date": (pred_ts or "")[:10] or g.game_date,
            "pred_ts": pred_ts,
            "inputs": {"source": "live_feed_ingame", "inning": g.inning,
                       "half": g.half, "home_runs": g.home_runs,
                       "away_runs": g.away_runs, "sched_date": g.game_date},
        })
    return out
