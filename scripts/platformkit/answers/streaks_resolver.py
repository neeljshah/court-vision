"""answers.streaks_resolver -- team WIN/LOSS streaks computed directly off the
public games calendar, for ONE team, scoped to a single season. Purely
descriptive over COMPLETED games (longest win streak, longest loss streak,
current streak) -- zero forecast, zero market surface, never a $ edge
(see .claude/rules/no-edge-claims.md). Complements, never replaces:
  - h2h_history_resolver: a team PAIR's series aggregate.
  - schedule_context_resolver: rest/b2b/density off the same calendar.
  - historical_result: ONE game's final score.

Sources are the SAME per-sport calendars h2h_history_resolver reads -- its
_SOURCES table (path, home_col, away_col, score_kind), _abs() clone-safe
runtime rejoin, _team_scores() and _resolve_team_code() are imported and
reused here, never re-mirrored (additive, zero risk to that tested resolver).
Coverage is therefore its three team-sports: nba / mlb / soccer. Tennis is
NOT wired -- atlas_h2h.parquet is a pairwise h2h store, not a full match log,
so a per-player season streak can't be computed honestly from it -> not_supported.

Season scope: "longest win streak THIS season" -- default is the most recent
season on file; pass as_of to pick the season containing that date (and
truncate to games strictly BEFORE it, leak-free). Season boundary matches
schedule_context_resolver: MLB = calendar year, NBA/soccer = the Aug-Jul
season-start year. A draw (soccer) is neither W nor L: it breaks a win streak
AND a loss streak, and a trailing run of draws is reported as a 'D' streak.

Zero-row / unresolvable team / absent calendar -> no_data (never fabricated),
mirroring h2h_history_resolver's honesty.

Run: python -m scripts.platformkit.answers.streaks_resolver nba Lakers
"""
from __future__ import annotations

import argparse
import json
import os
import re

import pandas as pd

from scripts.platformkit.answers.h2h_history_resolver import (
    _SOURCES, _abs, _resolve_team_code, _team_scores)

CATEGORY = "streaks"
FRAMING = "descriptive season game-log streaks over completed games -- no forecast, no market surface"

# "longest win streak for the Lakers this season" / "current streak of the
# Celtics" / "what is the Bucks winning streak" -- strip the lead-in phrase so
# the remainder is the team. ponytail: regex lead-strip, not NER -- widen only
# if a real phrasing slips past. Explicit team= kwarg always wins over this.
_LEAD_RE = re.compile(
    r"^\s*(?:what(?:'s|s| is| are)?\s+(?:the\s+)?)?"
    r"(?:longest\s+|current\s+|latest\s+)?"
    r"(?:win(?:ning)?|los(?:s|ing)|hot|cold)?\s*streaks?\s+(?:for|of|by)?\s*", re.I)
_TRAIL_RE = re.compile(
    r"\s+(?:this\s+season|right\s+now|currently|so\s+far|have|has|on)\b.*$", re.I)


def parse_team(query: str) -> str | None:
    """Strip a streak lead-in / trailing clause / leading article -> team name.
    None if nothing recognizable remains."""
    s = _LEAD_RE.sub("", query, count=1).strip().strip("?").strip()
    s = _TRAIL_RE.sub("", s).strip()
    s = re.sub(r"^the\s+", "", s, flags=re.I).strip()
    return s or None


def _season_of(sport: str, dates: pd.Series) -> pd.Series:
    """MLB season = calendar year; NBA/soccer = the year the Aug-Jul season
    STARTS. Mirrors schedule_context_resolver._season_label (kept local -- 3
    lines, avoids coupling to that module's private helper)."""
    if sport == "mlb":
        return dates.dt.year
    return dates.dt.year.where(dates.dt.month >= 8, dates.dt.year - 1)


def _longest_run(results: list[str], target: str) -> int:
    best = cur = 0
    for r in results:
        cur = cur + 1 if r == target else 0
        best = max(best, cur)
    return best


def _current_run(results: list[str]) -> dict:
    """Trailing run of the same result at the end of the (date-ordered) log."""
    if not results:
        return {"type": None, "length": 0}
    last = results[-1]
    n = 0
    for r in reversed(results):
        if r != last:
            break
        n += 1
    return {"type": last, "length": n}


def resolve(sport: str, team: str, as_of: str | None = None) -> dict:
    sport = sport.lower()
    if sport not in _SOURCES:
        return {"status": "not_supported", "category": CATEGORY, "sport": sport,
                "framing": FRAMING,
                "note": f"streaks not wired for sport '{sport}' -- available: {sorted(_SOURCES)}"}
    path, home_col, away_col, kind = _SOURCES[sport]
    if not os.path.exists(_abs(path)):
        return {"status": "no_data", "category": CATEGORY, "sport": sport,
                "source_artifact": path, "framing": FRAMING}
    df = pd.read_parquet(_abs(path))
    df = df.assign(date=pd.to_datetime(df["date"]))
    candidates = set(df[home_col]) | set(df[away_col])
    code = _resolve_team_code(sport, team, candidates)
    if not code:
        return {"status": "no_data", "category": CATEGORY, "sport": sport, "source_artifact": path,
                "framing": FRAMING, "note": f"could not resolve team={team!r} -- refusing, not guessing"}
    sub = df[(df[home_col] == code) | (df[away_col] == code)].copy()
    if as_of:
        sub = sub[sub["date"] < pd.Timestamp(as_of)]
    if sub.empty:
        return {"status": "no_data", "category": CATEGORY, "sport": sport, "source_artifact": path,
                "framing": FRAMING,
                "note": f"zero games matched team={code!r} as_of={as_of!r} -- refusing, not guessing"}
    sub = sub.sort_values("date").assign(season=lambda d: _season_of(sport, d["date"]))
    # scope to the season the caller asked about ("this season"): as_of's season
    # if it's on file, else the most recent season present.
    target = None
    if as_of:
        cand = _season_of(sport, pd.Series([pd.Timestamp(as_of)])).iloc[0]
        if cand in set(sub["season"]):
            target = cand
    if target is None:
        target = sub["season"].iloc[-1]
    season_games = sub[sub["season"] == target].sort_values("date")
    home_score, away_score = _team_scores(season_games, kind)
    is_home = (season_games[home_col] == code).to_numpy()
    team_score = home_score.where(is_home, away_score).to_numpy()
    opp_score = away_score.where(is_home, home_score).to_numpy()
    results = ["W" if t > o else ("L" if t < o else "D") for t, o in zip(team_score, opp_score)]
    cur = _current_run(results)
    return {"status": "ok", "category": CATEGORY, "sport": sport, "source_artifact": path,
            "framing": FRAMING, "team": code, "season": str(target),
            "as_of": as_of if as_of else str(season_games["date"].iloc[-1].date()),
            "games_played": len(results),
            "record": {"W": results.count("W"), "L": results.count("L"), "D": results.count("D")},
            "longest_win_streak": _longest_run(results, "W"),
            "longest_loss_streak": _longest_run(results, "L"),
            "current_streak": cur}


def _demo() -> None:
    """Runnable self-check: the streak math is the non-trivial logic, so pin
    it against a hand-built result log (no parquet, no I/O)."""
    seq = ["W", "W", "W", "L", "L", "W", "W"]
    assert _longest_run(seq, "W") == 3, _longest_run(seq, "W")
    assert _longest_run(seq, "L") == 2, _longest_run(seq, "L")
    assert _current_run(seq) == {"type": "W", "length": 2}, _current_run(seq)
    assert _current_run([]) == {"type": None, "length": 0}
    assert _current_run(["D", "D"]) == {"type": "D", "length": 2}
    assert parse_team("longest win streak for the Lakers this season") == "Lakers", \
        parse_team("longest win streak for the Lakers this season")
    assert parse_team("what is the Celtics current streak") == "Celtics", \
        parse_team("what is the Celtics current streak")
    print("streaks_resolver self-check: OK")


def main(argv=None):
    p = argparse.ArgumentParser(description="Query the team-streaks resolver directly.")
    p.add_argument("sport")
    p.add_argument("team", nargs="?")
    p.add_argument("--as-of", default=None, dest="as_of", help="YYYY-MM-DD, truncate to games before this date")
    p.add_argument("--demo", action="store_true", help="run the in-process self-check and exit")
    a = p.parse_args(argv)
    if a.demo or not a.team:
        _demo()
        return
    print(json.dumps(resolve(a.sport, a.team, a.as_of), indent=2, default=str))


if __name__ == "__main__":
    main()
