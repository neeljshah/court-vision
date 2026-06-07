"""src/prediction/live_context.py — assemble tonight's same-day context for the
live_adjustment layer from the odds-websocket mainline feed.

Reads data/lines/<date>_<book>_mainline.csv (book preference pin>dk>fd>bov) and
returns, per game, the consensus game TOTAL and |SPREAD| — the inputs the
live_adjustment pace/blowout terms need. Team names in the feed are full
("Oklahoma City Thunder"); we map them to canonical abbrevs via game_matcher's
table so callers can look up by the abbrev they already use (e.g. "OKC", "SAS").

Everything is best-effort: any missing file / unparseable row yields None, so the
adjustment degrades to a no-op rather than raising on a quiet night.
"""
from __future__ import annotations

import csv
import logging
import statistics
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Tuple

log = logging.getLogger(__name__)

# Module-level counter incremented each time a CSV row is dropped because a
# team name could not be resolved to an NBA abbreviation.
_dropped_row_count: int = 0

_ROOT = Path(__file__).resolve().parent.parent.parent
_LINES_DIR = _ROOT / "data" / "lines"
_BOOK_PREF = ("pin", "dk", "fd", "bov", "betrivers")

try:
    from src.data.game_matcher import _LABEL_TO_ABBREV as _LABEL
except Exception:  # pragma: no cover - defensive
    _LABEL = {}

# nicknames the last-word heuristic gets wrong (two-word nicknames etc.)
_FULLNAME_FIX = {
    "trail blazers": "POR", "portland trail blazers": "POR",
}


def _abbrev_from_full(name: str) -> Optional[str]:
    if not name:
        return None
    n = name.strip().lower()
    if n in _FULLNAME_FIX:
        return _FULLNAME_FIX[n]
    # try whole tokens (nickname is usually the last word)
    toks = n.split()
    for cand in (toks[-1] if toks else n, n):
        if cand in _LABEL:
            return _LABEL[cand]
    # last-two-words joined ("trail blazers")
    if len(toks) >= 2 and " ".join(toks[-2:]) in _FULLNAME_FIX:
        return _FULLNAME_FIX[" ".join(toks[-2:])]
    return None


def _mainline_path(date: str) -> Optional[Path]:
    for bk in _BOOK_PREF:
        p = _LINES_DIR / f"{date}_{bk}_mainline.csv"
        if p.exists():
            return p
    return None


@lru_cache(maxsize=8)
def load_mainline(date: str) -> Dict[frozenset, Dict[str, float]]:
    """game (frozenset of the two team abbrevs) -> {total, spread_abs}."""
    path = _mainline_path(date)
    out: Dict[frozenset, Dict[str, float]] = {}
    if path is None:
        return out
    totals: Dict[frozenset, list] = {}
    spreads: Dict[frozenset, list] = {}
    try:
        for r in csv.DictReader(open(path, encoding="utf-8")):
            global _dropped_row_count
            mt = (r.get("market_type") or "").lower()
            ha = _abbrev_from_full(r.get("home_team", ""))
            aa = _abbrev_from_full(r.get("away_team", ""))
            if not ha or not aa:
                _dropped_row_count += 1
                log.warning(
                    "live_context: unresolved team name(s) in %s — "
                    "home=%r->%r away=%r->%r; row dropped. total_dropped=%d",
                    path.name,
                    r.get("home_team"), ha,
                    r.get("away_team"), aa,
                    _dropped_row_count,
                )
                continue
            key = frozenset((ha, aa))
            try:
                line = float(r.get("line"))
            except (TypeError, ValueError):
                continue
            if mt in ("total", "totals") and line > 100:  # game total, not alt o/u
                totals.setdefault(key, []).append(line)
            elif mt in ("spread", "spreads"):
                spreads.setdefault(key, []).append(abs(line))
    except Exception:
        return out
    for key in set(totals) | set(spreads):
        rec: Dict[str, float] = {}
        if totals.get(key):
            rec["total"] = float(statistics.median(totals[key]))
        if spreads.get(key):
            # mainline spread ≈ the most common (modal) |line|; median is a robust proxy
            rec["spread_abs"] = float(statistics.median(spreads[key]))
        out[key] = rec
    return out


def context_for_team(team_abbrev: str, opp_abbrev: str, date: str
                     ) -> Tuple[Optional[float], Optional[float]]:
    """Return (game_total, game_spread_abs) for the team's game, or (None, None)."""
    if not team_abbrev or not opp_abbrev:
        return None, None
    rec = load_mainline(date).get(frozenset((team_abbrev.upper(), opp_abbrev.upper())))
    if not rec:
        return None, None
    return rec.get("total"), rec.get("spread_abs")


@lru_cache(maxsize=4)
def _latest_team_state(season: str) -> Dict[str, Dict[str, float]]:
    """abbrev -> {pace, def} = the team's most recent as-of ratings this season,
    from data/nba/season_games_<season>.json (a good pre-game estimate of where a
    team's pace/defense sits today). Empty dict on any failure."""
    import json
    p = _ROOT / "data" / "nba" / f"season_games_{season}.json"
    out: Dict[str, Dict[str, float]] = {}
    try:
        rows = json.loads(p.read_text(encoding="utf-8")).get("rows", [])
    except Exception:
        return out
    for r in rows:  # rows are chronological; later rows overwrite -> latest as-of
        for side in ("home", "away"):
            t = r.get(f"{side}_team")
            pace = r.get(f"{side}_pace")
            if t and pace is not None:
                out[t] = {"pace": float(pace),
                          "def": float(r.get(f"{side}_def_rtg") or 112.0)}
    return out


def team_pace_def(team_abbrev: str, season: str = "2025-26"
                 ) -> Tuple[Optional[float], Optional[float]]:
    """Latest as-of (pace, def_rtg) for a team, or (None, None)."""
    rec = _latest_team_state(season).get((team_abbrev or "").upper())
    return (rec["pace"], rec["def"]) if rec else (None, None)


def context_for_opponent(opp_abbrev: str, date: str
                        ) -> Tuple[Optional[float], Optional[float]]:
    """Find the unique slate game containing *opp_abbrev* and return its
    (game_total, |spread|). Convenient when the caller knows the opponent but not
    the player's own team; |spread| is symmetric so the player's side is moot.
    Returns (None, None) if zero or multiple games match.
    """
    if not opp_abbrev:
        return None, None
    opp = opp_abbrev.upper()
    matches = [rec for key, rec in load_mainline(date).items() if opp in key]
    if len(matches) != 1:
        return None, None
    return matches[0].get("total"), matches[0].get("spread_abs")
