"""scripts.platformkit.live_read_cli — CLI / demo-state plumbing for live_read.

Split out of scripts.platformkit.live_read (LOC budget). The load-bearing build/render
functions stay in live_read.py; this module only owns the argparse front-end and the
hardcoded per-sport demo GameState construction.

CLI:
    python -m scripts.platformkit.live_read --sport nba --demo
(re-exported from live_read.__main__ so the documented entry point is unchanged.)
"""
from __future__ import annotations

import argparse
import json
from typing import List, Optional

from scripts.platformkit.live_repricer import GameState
from scripts.platformkit.live_read import build_live_read, render_markdown

# Per-sport pregame params for --demo (sport-appropriate priors, not NBA defaults).
_DEMO_PARAMS = {
    "nba": {"mu_home": 114, "mu_away": 112},
    "mlb": {"lam_home": 4.6, "lam_away": 4.3},
    "soccer": {"lam_home": 1.6, "lam_away": 1.2},
    "tennis": {"best_of": 3, "p_set": 0.55},
}
# Sane per-sport mid-event demo states (elapsed, home, away; in-progress).
_SANE = {
    "nba": (24.0, 58, 50), "mlb": (5.0, 3, 2),
    "soccer": (60.0, 1, 1), "tennis": (1.0, 1, 0),
}


def _cli(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="live_read: in-game re-priced surface + brain concepts; no edge.")
    ap.add_argument("--sport", default="nba")
    ap.add_argument("--elapsed", type=float, default=24.0)
    ap.add_argument("--home", type=int, default=58)
    ap.add_argument("--away", type=int, default=50)
    ap.add_argument("--demo", action="store_true", help="use sport-appropriate demo params")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    sport = a.sport.lower()
    # The --elapsed/--home/--away defaults are NBA-shaped; fed raw to other sports they
    # make nonsensical states. If untouched, substitute a sane per-sport mid-event demo.
    untouched = (a.elapsed == 24.0 and a.home == 58 and a.away == 50)
    elapsed = a.elapsed
    home, away = a.home, a.away
    if untouched and sport in _SANE:
        elapsed, home, away = _SANE[sport]
    extra = {}
    if sport == "mlb":
        extra = {"innings_played": elapsed}
    elif sport == "tennis":
        sets_to_win = int(_DEMO_PARAMS["tennis"]["best_of"]) // 2 + 1
        home = max(0, min(home, sets_to_win - 1))
        away = max(0, min(away, sets_to_win - 1))
        extra = {"sets_1": home, "sets_2": away}
    state = GameState(sport=sport, elapsed_minutes=elapsed,
                      home_score=home, away_score=away,
                      pregame_params=_DEMO_PARAMS.get(sport, {}) if a.demo else {},
                      extra=extra)
    read = build_live_read(sport, state)
    if a.json:
        print(json.dumps(read, indent=2, default=str))
    else:
        print(render_markdown(read))
    return 0
