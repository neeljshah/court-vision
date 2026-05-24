"""predict_player.py — actually use the model. CLI for live prop predictions.

Loads the production prop_pergame stack + quantile heads and prints
predictions + 80% intervals + L5 baseline + claimed edge per stat for ONE
player playing ONE opponent. The honest end-user surface — what you'd
actually run before a game to decide bets.

Usage:
    # By player name (NBA full_name lookup)
    python scripts/predict_player.py --name "Nikola Jokic" --opp DEN --home --rest 2
    python scripts/predict_player.py --name "Anthony Edwards" --opp PHX --away --rest 1

    # By player_id
    python scripts/predict_player.py --pid 203999 --opp LAL --home

Output (one row per stat):
    stat  | prediction | L5_avg | edge   | q10  q90  | recommended bet @ -110
    PTS   | 26.3       | 28.1   | -1.8   | 18  35    | UNDER 28.1 (62.7% modelled hit)
    ...
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_prediction_row, predict_pergame, _MIN_PLAYED, _num,
    _parse_date, _ewma,
)
from src.prediction.prop_quantiles import (  # noqa: E402
    predict_pergame_quantiles,
)


def _strip_accents(s: str) -> str:
    """Drop non-ASCII diacritics so 'Jokic' matches 'Nikola Jokic'."""
    import unicodedata  # noqa: PLC0415
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _resolve_player_id(name: str):
    """NBA full_name → player_id via nba_api static index. Diacritic-insensitive."""
    try:
        from nba_api.stats.static import players  # noqa: PLC0415
    except Exception as e:
        print(f"  [warn] nba_api unavailable: {e}")
        return None
    needle = _strip_accents(name).lower()
    candidates = players.get_players()
    for p in candidates:
        if _strip_accents(p["full_name"]).lower() == needle:
            return int(p["id"])
    # Fuzzy fallback: substring match (accent-stripped)
    for p in candidates:
        if needle in _strip_accents(p["full_name"]).lower():
            return int(p["id"])
    return None


def _detect_current_season() -> str:
    """NBA season string for today's date: 'YYYY-YY'.

    Season starts in October. From Oct 1 onward the season is current_year/(current_year+1).
    Before October it's the (current_year-1)/current_year season ending.
    """
    now = datetime.now()
    if now.month >= 10:
        start = now.year
    else:
        start = now.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _player_l5_l10(player_id: int, season: str, gamelog_dir: str) -> dict:
    """Quick L5 / L10 means per stat from the player's gamelog (no leak — uses
    all available cached games as 'prior')."""
    import glob
    import json
    path = os.path.join(gamelog_dir, f"gamelog_{player_id}_{season}.json")
    if not os.path.exists(path):
        # Fall back to previous season if this season's not cached
        for try_season in (season, f"{int(season[:4])-1}-{int(season[5:])-1:02d}"):
            p = os.path.join(gamelog_dir, f"gamelog_{player_id}_{try_season}.json")
            if os.path.exists(p):
                path = p
                break
        else:
            return {}
    try:
        games = json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}
    played = [g for g in games if _num(g.get("MIN")) >= _MIN_PLAYED]
    if not played:
        return {}
    box = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M",
           "stl": "STL", "blk": "BLK", "tov": "TOV"}
    out = {}
    for stat, col in box.items():
        vals = [_num(g.get(col)) for g in played]
        out[f"l5_{stat}"]  = round(sum(vals[-5:]) / max(1, len(vals[-5:])), 2)
        out[f"l10_{stat}"] = round(sum(vals[-10:]) / max(1, len(vals[-10:])), 2)
        out[f"ewma_{stat}"] = round(_ewma(vals), 2)
    return out


def main():
    ap = argparse.ArgumentParser()
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--name", help="Player NBA full name (e.g. 'Nikola Jokic')")
    grp.add_argument("--pid",  type=int, help="Player ID (NBA stats.com)")
    ap.add_argument("--opp", required=True, help="Opponent team abbrev (e.g. LAL)")
    ven = ap.add_mutually_exclusive_group()
    ven.add_argument("--home", action="store_true", help="Player's team is HOME (default)")
    ven.add_argument("--away", action="store_true", help="Player's team is AWAY")
    ap.add_argument("--rest", type=float, default=2.0, help="Days rest (default 2)")
    ap.add_argument("--season", default=None, help="Season override (e.g. '2024-25'). Default: current.")
    args = ap.parse_args()

    season = args.season or _detect_current_season()
    pid = args.pid
    name = args.name
    if pid is None:
        pid = _resolve_player_id(name)
        if pid is None:
            print(f"  [fail] could not resolve player name '{name}' — try --pid instead.")
            sys.exit(1)
    elif name is None:
        name = f"player_id={pid}"

    is_home = not args.away
    gamelog_dir = os.path.join(PROJECT_DIR, "data", "nba")
    model_dir = os.path.join(PROJECT_DIR, "data", "models")

    print(f"\n  Player: {name}  (id={pid})")
    print(f"  Game:   {'home' if is_home else 'away'} vs {args.opp}    season={season}    rest={args.rest}d\n")

    row = build_prediction_row(pid, args.opp, season, is_home=is_home,
                               rest_days=args.rest, gamelog_dir=gamelog_dir)
    if row is None:
        print(f"  [fail] no gamelog cached for player_id={pid} season={season}.")
        sys.exit(2)

    l5 = _player_l5_l10(pid, season, gamelog_dir)

    print(f"  {'stat':4s} | {'pred':>6s} | {'L5':>5s} | {'L10':>5s} | {'edge':>6s} | {'q10':>5s} {'q90':>5s} | bet @ -110")
    print(f"  -----+--------+-------+-------+--------+-----------+-------------------")
    for stat in STATS:
        pred = predict_pergame(stat, row, model_dir)
        if pred is None:
            print(f"  {stat.upper():4s} | (no model)")
            continue
        l5_val = l5.get(f"l5_{stat}", None)
        l10_val = l5.get(f"l10_{stat}", None)
        edge = (pred - l5_val) if l5_val is not None else None
        qint = predict_pergame_quantiles(stat, row, model_dir) or {}
        q10 = qint.get("q10", "—")
        q90 = qint.get("q90", "—")
        q10_s = f"{q10:.1f}" if isinstance(q10, (int, float)) else q10
        q90_s = f"{q90:.1f}" if isinstance(q90, (int, float)) else q90
        l5s  = f"{l5_val:.1f}" if l5_val is not None else "—"
        l10s = f"{l10_val:.1f}" if l10_val is not None else "—"
        edge_s = f"{edge:+.2f}" if edge is not None else "—"
        # Bet recommendation: if |edge| > 0.5 stat unit, suggest the side
        bet = ""
        if edge is not None:
            if edge > 0.5:
                bet = f"OVER  line~{l5_val:.1f}"
            elif edge < -0.5:
                bet = f"UNDER line~{l5_val:.1f}"
            else:
                bet = "  (no edge)"
        print(f"  {stat.upper():4s} | {pred:6.2f} | {l5s:>5s} | {l10s:>5s} | {edge_s:>6s} | {q10_s:>5s} {q90_s:>5s} | {bet}")
    print()


if __name__ == "__main__":
    main()
