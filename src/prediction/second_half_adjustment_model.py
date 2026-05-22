"""
second_half_adjustment_model.py — Player H1 vs H2 efficiency splits from PBP.

Computes:
  - Stars who exploit pre-adjustment defense: H1 pts > H2 pts
  - Closers who get late-game usage: Q4 pts disproportionately high

Uses PBP quarter-by-quarter scoring from pbp_features cache + raw PBP files.

Public API
----------
    train(seasons, force)              -> dict
    predict_half_split(player_id, season) -> dict
        -> {h1_pts_pct, h2_pts_pct, q4_pts_pct, closer_score}
"""
from __future__ import annotations

import glob
import json
import os
import pickle
import sys
from collections import defaultdict
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_NBA_CACHE  = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_PATH = os.path.join(_MODEL_DIR, "second_half_adjustment.pkl")

# Closer threshold: Q4 pts share significantly above equal distribution (0.25)
_CLOSER_THRESHOLD = 0.30
# Equal quarter distribution baseline
_EQUAL_QTR_SHARE  = 0.25


def _parse_quarter_splits(seasons: list) -> dict:
    """
    Parse PBP to get per-player per-quarter scoring.

    Returns:
        {player_id: {q1: pts, q2: pts, q3: pts, q4: pts, total: pts, games: n}}
    """
    stats: dict = defaultdict(lambda: {
        "q1": 0.0, "q2": 0.0, "q3": 0.0, "q4": 0.0, "total": 0.0, "games": 0
    })

    pbp_pattern = os.path.join(_NBA_CACHE, "pbp_*.json")
    files = glob.glob(pbp_pattern)[:500]
    game_players: set = set()

    current_game = None
    game_scorers: dict = defaultdict(lambda: {"q1": 0, "q2": 0, "q3": 0, "q4": 0})

    for fpath in files:
        try:
            data = json.load(open(fpath))
            events = data if isinstance(data, list) else data.get("playByPlay", data.get("plays", []))
            game_scorers = defaultdict(lambda: {"q1": 0, "q2": 0, "q3": 0, "q4": 0})

            for ev in events:
                if not isinstance(ev, dict):
                    continue
                evt_type = ev.get("eventMsgType") or ev.get("event_type")
                period   = int(ev.get("period", ev.get("quarter", 0)) or 0)
                pid      = ev.get("player1_id") or ev.get("playerId")
                if not pid or period < 1 or period > 4:
                    continue
                pid = int(pid)

                # Score points: made FG = type 1, FT = type 3
                if evt_type in (1, "1"):
                    desc = str(ev.get("description", "")).lower()
                    pts = 3 if "3pt" in desc or "three" in desc else 2
                    q_key = f"q{period}"
                    game_scorers[pid][q_key] += pts
                elif evt_type in (3, "3"):
                    q_key = f"q{period}"
                    game_scorers[pid][q_key] += 1

            # Accumulate into player stats
            for pid, qs in game_scorers.items():
                total = sum(qs.values())
                if total > 0:
                    stats[pid]["q1"]    += qs["q1"]
                    stats[pid]["q2"]    += qs["q2"]
                    stats[pid]["q3"]    += qs["q3"]
                    stats[pid]["q4"]    += qs["q4"]
                    stats[pid]["total"] += total
                    stats[pid]["games"] += 1

        except Exception:
            continue

    return dict(stats)


def _compute_splits(pid_stats: dict) -> dict:
    """Compute pct splits from raw quarter totals."""
    total = max(pid_stats.get("total", 0), 1)
    q1 = pid_stats.get("q1", 0)
    q2 = pid_stats.get("q2", 0)
    q3 = pid_stats.get("q3", 0)
    q4 = pid_stats.get("q4", 0)

    h1 = q1 + q2
    h2 = q3 + q4

    h1_pct = round(h1 / total, 4)
    h2_pct = round(h2 / total, 4)
    q4_pct = round(q4 / total, 4)

    # Closer score: how much Q4 share exceeds equal distribution
    # 0 = exactly equal distribution, 1 = all points in Q4
    closer_score = round(max((q4_pct - _EQUAL_QTR_SHARE) / (1.0 - _EQUAL_QTR_SHARE), 0.0), 4)

    return {
        "h1_pts_pct":   h1_pct,
        "h2_pts_pct":   h2_pct,
        "q4_pts_pct":   q4_pct,
        "closer_score": closer_score,
        "sample_games": pid_stats.get("games", 0),
    }


def train(seasons: list = None, force: bool = False) -> dict:
    """
    Build per-player half/quarter split model from PBP data.

    Saves: data/models/second_half_adjustment.pkl
    Returns: {n_players, avg_q4_pct, n_closers}
    """
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    os.makedirs(_MODEL_DIR, exist_ok=True)

    if not force and os.path.exists(_MODEL_PATH):
        print("[second_half] Model exists. Use force=True to retrain.")
        return {}

    print("[second_half] Parsing PBP quarter splits...")
    quarter_stats = _parse_quarter_splits(seasons)

    # Also incorporate PBP features cache for richer per-game data
    model_data = {}
    for pid, raw in quarter_stats.items():
        model_data[int(pid)] = _compute_splits(raw)

    # Augment with pbp_features cache where available
    for season in seasons:
        pbp_feat_path = os.path.join(_NBA_CACHE, f"pbp_features_{season}.json")
        if os.path.exists(pbp_feat_path):
            try:
                pbp_feats = json.load(open(pbp_feat_path))
                for pid_str, row in pbp_feats.items():
                    pid = int(pid_str)
                    if pid not in model_data:
                        model_data[pid] = {
                            "h1_pts_pct":   0.50,
                            "h2_pts_pct":   0.50,
                            "q4_pts_pct":   float(row.get("q4_pts_share", 0.25)),
                            "closer_score": max(float(row.get("q4_pts_share", 0.25)) - 0.25, 0.0) / 0.75,
                            "sample_games": 0,
                        }
            except Exception:
                pass

    with open(_MODEL_PATH, "wb") as f:
        pickle.dump(model_data, f)

    n = len(model_data)
    avg_q4 = sum(v["q4_pts_pct"] for v in model_data.values()) / n if n > 0 else 0.25
    n_closers = sum(1 for v in model_data.values() if v["closer_score"] > 0.2)
    print(f"  [second_half] {n} players, avg_q4_pct={avg_q4:.3f}, closers={n_closers}")
    return {"n_players": n, "avg_q4_pct": round(avg_q4, 4), "n_closers": n_closers}


def predict_half_split(
    player_id: int,
    season: str = "2024-25",
) -> dict:
    """
    Predict player's H1/H2/Q4 scoring distribution.

    Falls back to PBP features cache, then equal distribution.

    Returns:
        {h1_pts_pct, h2_pts_pct, q4_pts_pct, closer_score}
    """
    default = {
        "h1_pts_pct":   0.50,
        "h2_pts_pct":   0.50,
        "q4_pts_pct":   0.25,
        "closer_score": 0.0,
    }

    # Try trained model
    if os.path.exists(_MODEL_PATH):
        try:
            with open(_MODEL_PATH, "rb") as f:
                model_data = pickle.load(f)
            player = model_data.get(int(player_id))
            if player:
                return {k: player[k] for k in ("h1_pts_pct", "h2_pts_pct", "q4_pts_pct", "closer_score")}
        except Exception:
            pass

    # Fallback: PBP features cache
    try:
        path = os.path.join(_NBA_CACHE, f"pbp_features_{season}.json")
        d = json.load(open(path))
        row = d.get(str(player_id), {})
        if row:
            q4_pct = float(row.get("q4_pts_share", 0.25))
            return {
                "h1_pts_pct":   0.50,
                "h2_pts_pct":   0.50,
                "q4_pts_pct":   q4_pct,
                "closer_score": round(max(q4_pct - 0.25, 0.0) / 0.75, 4),
            }
    except Exception:
        pass

    return default


# ── 2H prop bets from a blowout signal (task 19.5-04) ────────────────────────

def produce_2h_prop_bets(
    blowout_signal: dict,
    players: list,
    season: str = "2024-25",
) -> list:
    """Produce second-half prop bets from a blowout signal.

    In a blowout both teams' starters sit while the bench mob plays:
      * starters  -> 2H alt-UNDER (minutes capped by garbage time)
      * bench     -> 2H alt-OVER  (unexpected garbage-time minutes)

    Args:
        blowout_signal: A BLOWOUT signal from garbage_time_detector.detect_blowout.
        players:        [{player_id, player_name, team, role}], role in
                        {"starter", "bench"}.
        season:         Season for the H1/H2 split lookup.

    Returns:
        List of 2H prop-bet dicts (player_id, team, half="2H", stat="pts",
        recommendation, h2_pts_pct, reason).
    """
    if not blowout_signal or blowout_signal.get("event") != "BLOWOUT":
        return []

    affected = {blowout_signal.get("leading_team"), blowout_signal.get("trailing_team")}
    affected.discard(None)

    bets = []
    for p in players:
        if p.get("team") not in affected:
            continue
        role = str(p.get("role", "starter")).lower()
        is_starter = role == "starter"

        try:
            split = predict_half_split(int(p.get("player_id", 0)), season)
            h2_pct = split.get("h2_pts_pct", 0.50)
        except Exception:  # noqa: BLE001
            h2_pct = 0.50

        bets.append({
            "player_id":      p.get("player_id"),
            "player_name":    p.get("player_name", ""),
            "team":           p.get("team"),
            "half":           "2H",
            "stat":           "pts",
            "recommendation": "alt_under" if is_starter else "alt_over",
            "h2_pts_pct":     round(float(h2_pct), 4),
            "reason": (
                f"blowout ({blowout_signal.get('point_differential')} pts) — "
                + ("starter minutes capped by garbage time"
                   if is_starter else "bench-mob garbage-time minutes")
            ),
        })
    return bets


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--player-id", type=int, default=2544)
    ap.add_argument("--season", default="2024-25")
    args = ap.parse_args()
    if args.train:
        r = train(force=args.force)
        print(json.dumps(r, indent=2))
    else:
        r = predict_half_split(args.player_id, args.season)
        print(json.dumps(r, indent=2))
