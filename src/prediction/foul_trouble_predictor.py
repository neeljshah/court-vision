"""
foul_trouble_predictor.py — M05: Predict foul trouble probability and minute impact.

Inputs: historical foul rate per player (PBP), opponent foul-drawing rate, ref tendency
Output: foul_out_prob, expected_foul_count, min_reduction_if_foul_trouble

Public API
----------
    train(season)                           -> dict (metrics)
    predict_foul_trouble(player_id, feats)  -> dict
"""

from __future__ import annotations

import glob
import json
import logging
import math
import os
import pickle
import sys
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "foul_trouble.pkl")

log = logging.getLogger(__name__)

# Personal foul event type in PBP
_PBP_FOUL_EVTTYPE = 6
_FOUL_OUT_LIMIT = 6


def _extract_foul_rates(seasons: list[str]) -> dict:
    """
    Extract per-player foul rates from PBP data.
    Returns {player_id: {avg_fouls_per_game, foul_out_rate, games_played}}.
    """
    foul_games: dict[int, list] = {}

    for season in seasons:
        pbp_files = glob.glob(os.path.join(_NBA_CACHE, f"pbp_*.json"))
        season_count = 0
        for fpath in pbp_files[:500]:  # sample for speed
            try:
                with open(fpath) as f:
                    plays = json.load(f)
                if not isinstance(plays, list):
                    continue

                # Count fouls per player in this game
                game_fouls: dict[int, int] = {}
                for play in plays:
                    if play.get("EVENTMSGTYPE") == _PBP_FOUL_EVTTYPE:
                        pid = play.get("PLAYER1_ID")
                        if pid and int(pid) > 0:
                            game_fouls[int(pid)] = game_fouls.get(int(pid), 0) + 1

                for pid, fcount in game_fouls.items():
                    if pid not in foul_games:
                        foul_games[pid] = []
                    foul_games[pid].append(fcount)
                season_count += 1
            except Exception:
                continue

    result: dict = {}
    for pid, foul_list in foul_games.items():
        if len(foul_list) < 5:
            continue
        arr = np.array(foul_list)
        result[str(pid)] = {
            "avg_fouls_per_game": float(np.mean(arr)),
            "foul_out_rate":      float(np.mean(arr >= _FOUL_OUT_LIMIT)),
            "pct_2plus":          float(np.mean(arr >= 2)),
            "pct_3plus":          float(np.mean(arr >= 3)),
            "games_played":       len(foul_list),
        }
    return result


def train(seasons: Optional[list[str]] = None) -> dict:
    """Train foul trouble predictor from PBP data."""
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    log.info("Training foul trouble predictor...")
    foul_rates = _extract_foul_rates(seasons)

    if not foul_rates:
        log.warning("No foul data found — saving empty model")
        foul_rates = {}

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump({"foul_rates": foul_rates, "version": "1.0"}, f)

    log.info("Foul trouble model trained: %d players", len(foul_rates))
    return {"players": len(foul_rates)}


def _load_model() -> dict:
    if os.path.exists(_MODEL_PATH):
        try:
            with open(_MODEL_PATH, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    # Auto-train if missing
    log.info("foul_trouble.pkl not found — training now")
    train()
    if os.path.exists(_MODEL_PATH):
        with open(_MODEL_PATH, "rb") as f:
            return pickle.load(f)
    return {"foul_rates": {}}


_MODEL_CACHE: Optional[dict] = None


def predict_foul_trouble(player_id: int, features: dict) -> dict:
    """
    Predict foul trouble probability for tonight.

    Returns:
        foul_out_prob:      probability of fouling out
        expected_foul_count: expected fouls in game
        min_reduction:      expected minutes lost to foul trouble
    """
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        _MODEL_CACHE = _load_model()

    foul_rates = _MODEL_CACHE.get("foul_rates", {})
    rates = foul_rates.get(str(player_id), {})

    # Historical base rate
    avg_fouls = rates.get("avg_fouls_per_game", 2.5)
    foul_out_rate = rates.get("foul_out_rate", 0.03)

    # Adjust for opponent foul-drawing tendency
    opp_foul_draw = float(features.get("opp_foul_draw_rate", 1.0))
    ref_foul_adj  = float(features.get("ref_foul_adj", 1.0))

    adj_fouls = avg_fouls * opp_foul_draw * ref_foul_adj
    adj_fout  = foul_out_rate * opp_foul_draw * ref_foul_adj

    # Minute reduction if in foul trouble:
    # Coaches restrict 3-foul players — estimate ~4 min lost per foul above 3
    pct_3plus = rates.get("pct_3plus", 0.25)
    min_reduction = pct_3plus * 4.0 * max(adj_fouls - 2.5, 0.0)

    return {
        "foul_out_prob":       min(float(adj_fout), 0.5),
        "expected_foul_count": round(float(adj_fouls), 2),
        "min_reduction":       round(float(min_reduction), 2),
        "pct_3plus":           round(float(pct_3plus), 3),
    }


# ── live foul-trouble detection (task 19.5-01) ───────────────────────────────

# A player is in foul trouble at this many fouls; Q2 is the exploitable window
# because pre-game props were priced before any in-game foul information.
_FOUL_TROUBLE_COUNT = 3
_FOUL_TROUBLE_PERIOD = 2
# Minute-driven counting stats whose pre-game lines a foul-trouble bench hurts.
_AFFECTED_STATS = ["pts", "reb", "ast"]
# Usage share at/above which a player counts as a "star" worth fading.
_STAR_USAGE = 0.20


def _is_star(player: dict) -> bool:
    """A player counts as a star via an explicit flag or a high usage share."""
    if player.get("is_star"):
        return True
    return float(player.get("usage", 0.0) or 0.0) >= _STAR_USAGE


def _primary_beneficiary(players: list, star: dict) -> Optional[dict]:
    """Highest-usage teammate not himself in foul trouble — absorbs the minutes."""
    team = star.get("team")
    candidates = [
        p for p in players
        if p.get("team") == team
        and p.get("player_id") != star.get("player_id")
        and int(p.get("fouls", 0) or 0) < _FOUL_TROUBLE_COUNT
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: float(p.get("usage", p.get("minutes", 0.0)) or 0.0))


def monitor_foul_trouble(players: list, period: Optional[int] = None) -> list:
    """Scan a live box score and emit foul-trouble bet recommendations.

    When a star records 3 fouls in Q2, his pre-game props are stale: emit an
    alt-under on his counting stats and an alt-over on the primary beneficiary
    who absorbs the freed-up minutes.

    Args:
        players: Live box-score rows — dicts with player_id, player_name,
                 team, fouls, usage/minutes, optional is_star, optional period.
        period:  Current quarter (1–4).  Falls back to each row's "period".

    Returns:
        List of recommendation dicts (FOUL_TROUBLE alt-under + paired
        FOUL_TROUBLE_BENEFICIARY alt-over).  Empty when nothing qualifies.
    """
    recs: list = []
    for player in players:
        p_period = period if period is not None else int(player.get("period", 0) or 0)
        fouls = int(player.get("fouls", 0) or 0)
        if not (fouls >= _FOUL_TROUBLE_COUNT and p_period == _FOUL_TROUBLE_PERIOD):
            continue
        if not _is_star(player):
            continue

        recs.append({
            "event": "FOUL_TROUBLE",
            "player_id": player.get("player_id"),
            "player_name": player.get("player_name", ""),
            "team": player.get("team", ""),
            "fouls": fouls,
            "period": p_period,
            "recommendation": "alt_under",
            "stats": list(_AFFECTED_STATS),
            "reason": (f"{player.get('player_name','star')} has {fouls} fouls in "
                       f"Q{p_period} — bench risk caps his minutes"),
        })

        beneficiary = _primary_beneficiary(players, player)
        if beneficiary is not None:
            recs.append({
                "event": "FOUL_TROUBLE_BENEFICIARY",
                "player_id": beneficiary.get("player_id"),
                "player_name": beneficiary.get("player_name", ""),
                "team": beneficiary.get("team", ""),
                "recommendation": "alt_over",
                "stats": list(_AFFECTED_STATS),
                "linked_to": player.get("player_id"),
                "reason": (f"absorbs minutes/usage while "
                           f"{player.get('player_name','the star')} sits"),
            })
    return recs


def validate_foul_trouble_signal(historical_events: list) -> dict:
    """Validate the foul-trouble signal against labelled historical events.

    Each event is ``{"players": [...], "period": int, "clv": float}`` where
    ``clv`` is the realised closing-line value of the bet the detector would
    have fired.  The signal passes when it fired on the event and CLV > 0 on
    at least 60% of the events it fired on.

    Returns ``{"n_events", "n_fired", "n_clv_positive", "clv_positive_rate",
    "pass"}``.
    """
    n_fired = n_clv_positive = 0
    for ev in historical_events:
        recs = monitor_foul_trouble(ev.get("players", []), ev.get("period"))
        if not recs:
            continue
        n_fired += 1
        if float(ev.get("clv", 0.0)) > 0:
            n_clv_positive += 1
    rate = (n_clv_positive / n_fired) if n_fired else 0.0
    return {
        "n_events": len(historical_events),
        "n_fired": n_fired,
        "n_clv_positive": n_clv_positive,
        "clv_positive_rate": round(rate, 4),
        "pass": n_fired > 0 and rate >= 0.60,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        metrics = train()
        print("Trained:", metrics)
