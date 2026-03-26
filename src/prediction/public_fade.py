"""
public_fade.py -- Phase E3: Fade heavily bet public sides.

Detects when public money is heavily skewed on one side of a prop or game,
creating a contrarian edge opportunity.

Signals:
  - >70% public bets on one side → fade signal
  - Sharp money (line movement against public) confirms fade
  - High-profile players attract inefficient public pricing

Public API
----------
    get_fade_signals(season)          -> list[dict]
    score_public_fade(game_id)        -> dict
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

# Public skew threshold — above this % bet on one side, consider fade
_PUBLIC_SKEW_THRESHOLD = 0.70

# Min line movement in wrong direction to confirm sharp reversal
_SHARP_LINE_MOVE_THRESHOLD = 0.5


def _load_public_data(season: str) -> list:
    """Load public betting percentage data if available."""
    path = os.path.join(PROJECT_DIR, "data", "external", f"public_betting_{season}.json")
    if os.path.exists(path):
        try:
            return json.load(open(path))
        except Exception:
            pass
    return []


def score_public_fade(
    game_id: str,
    season: str = "2024-25",
) -> dict:
    """
    Score the public fade opportunity for a game.

    Returns:
        {
            "game_id":          str,
            "fade_score":       float,    # 0-1 how strong the contrarian signal is
            "public_pct_home":  float,    # fraction of bets on home side
            "sharp_signal":     bool,     # sharp money going against public
            "recommendation":   str,      # "Fade Home" | "Fade Away" | "No Signal"
        }
    """
    public_data = _load_public_data(season)
    game_data = next((g for g in public_data if g.get("game_id") == game_id), None)

    if not game_data:
        return {
            "game_id":         game_id,
            "fade_score":      0.0,
            "public_pct_home": 0.5,
            "sharp_signal":    False,
            "recommendation":  "No Data",
        }

    home_pct = float(game_data.get("home_bet_pct", 0.5))
    line_open = float(game_data.get("open_spread", 0))
    line_current = float(game_data.get("current_spread", 0))

    # Sharp signal: public on home but line moved toward away
    sharp_home_fade = home_pct > _PUBLIC_SKEW_THRESHOLD and (line_current - line_open) > _SHARP_LINE_MOVE_THRESHOLD
    sharp_away_fade = (1 - home_pct) > _PUBLIC_SKEW_THRESHOLD and (line_open - line_current) > _SHARP_LINE_MOVE_THRESHOLD

    fade_score = 0.0
    recommendation = "No Signal"

    if sharp_home_fade:
        fade_score = (home_pct - _PUBLIC_SKEW_THRESHOLD) * 3.0 + 0.3
        recommendation = "Fade Home"
    elif sharp_away_fade:
        fade_score = ((1 - home_pct) - _PUBLIC_SKEW_THRESHOLD) * 3.0 + 0.3
        recommendation = "Fade Away"
    elif home_pct > _PUBLIC_SKEW_THRESHOLD:
        fade_score = (home_pct - _PUBLIC_SKEW_THRESHOLD) * 2.0
        recommendation = "Mild Fade Home"
    elif (1 - home_pct) > _PUBLIC_SKEW_THRESHOLD:
        fade_score = ((1 - home_pct) - _PUBLIC_SKEW_THRESHOLD) * 2.0
        recommendation = "Mild Fade Away"

    return {
        "game_id":         game_id,
        "fade_score":      round(min(fade_score, 1.0), 4),
        "public_pct_home": round(home_pct, 3),
        "sharp_signal":    sharp_home_fade or sharp_away_fade,
        "recommendation":  recommendation,
        "line_movement":   round(line_current - line_open, 1),
    }


def get_fade_signals(
    season:      str = "2024-25",
    min_score:   float = 0.20,
    game_ids:    Optional[list] = None,
) -> list:
    """
    Return all public fade signals for today's games.

    Returns:
        list of {game_id, fade_score, public_pct_home, recommendation}
        sorted by fade_score descending.
    """
    public_data = _load_public_data(season)
    if not public_data:
        return []

    if game_ids:
        public_data = [g for g in public_data if g.get("game_id") in game_ids]

    results = []
    for entry in public_data:
        gid = entry.get("game_id", "")
        if gid:
            r = score_public_fade(gid, season)
            if r["fade_score"] >= min_score:
                results.append(r)

    results.sort(key=lambda x: -x["fade_score"])
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-id", default=None)
    parser.add_argument("--season",  default="2024-25")
    args = parser.parse_args()

    if args.game_id:
        import json
        result = score_public_fade(args.game_id, args.season)
        print(json.dumps(result, indent=2))
    else:
        signals = get_fade_signals(args.season)
        if not signals:
            print("[public_fade] No signals found (data/external/public_betting_*.json missing)")
        for s in signals:
            print(f"  {s['game_id']}  fade={s['fade_score']:.3f}  "
                  f"{s['recommendation']}  public_home={s['public_pct_home']:.0%}")
