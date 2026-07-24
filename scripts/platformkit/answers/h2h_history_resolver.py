"""answers.h2h_history_resolver -- historical head-to-head AGGREGATE for a
team/player PAIR across their completed games (all-time, or truncated to
`as_of` for walk-forward-safe use). Complements, never replaces:
  - resolver_registry.historical_result: ONE game's final score.
  - matchup_preview (_MATCHUP_PREVIEW_KEYWORDS "h2h"/"head-to-head"): the
    PREDICTIVE preview fan-out (win_prob + profiles + schedule).
This resolver answers the SERIES-level question instead: games played,
win/loss (+draw) split, mean/cumulative run-goal-point differential, last-N
form, and (tennis) a per-surface split. Purely descriptive over COMPLETED
games -- zero forecast, zero market surface, never a $ edge (no-edge-claims).

Sources (verified columns, docs/research/organization-sprint spec):
  nba:    data/domains/basketball_nba/linescores.parquet (home_abbr, away_abbr,
          home_q*/away_q*, date) -- the SAME file+method historical_result
          already reads (score = quarter columns summed). games.parquet was
          spec'd as an alternative NBA source, but its only VERIFIED columns
          are home_team/away_team/home_win/date/season -- no confirmed score
          column, so a cross-file join would risk a silently-misaligned
          differential. linescores.parquet is the proven, already-working
          source for NBA score data; using it here avoids that risk entirely.
  mlb:    data/domains/mlb/games.parquet (home_team, away_team, home_runs,
          away_runs, date) -- run differential native.
  soccer: data/domains/soccer/matches.parquet (home_team, away_team, fthg,
          ftag, date) -- goal differential native.
  tennis: data/domains/tennis/atlas_h2h.parquet (p1_name, p2_name, winner,
          surface, date) -- prebuilt per-match pair store (domains/tennis/
          atlas_persist.persist_h2h), wrapped/queried directly, never rebuilt.

Leak-free: `as_of` truncates to games strictly BEFORE that date -- any
downstream walk-forward claim usage stays truncation-honest.
Zero-row -> no_data (never fabricated), mirroring historical_result's honesty.

Run: python -m scripts.platformkit.answers.h2h_history_resolver mlb Yankees "Red Sox"
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]


def _abs(rel: str) -> str:
    """Rejoin a repo-relative source path against the runtime repo root so
    reads never depend on the process cwd (the MCP server pins none). The
    source_artifact fields keep the repo-relative string -- only the read
    resolves to absolute."""
    p = Path(rel)
    return str(p) if p.is_absolute() else str(_REPO / p)

from domains.basketball_nba import team_name_resolver as _nba_names
from scripts.platformkit.odds_provider.team_resolver import canonical as _team_canonical

FRAMING = "purely descriptive over completed games -- no forecast, no market surface"
_LAST_N = 5

# (path, home_col, away_col, score_kind) -- score_kind picks how to derive
# each game's (home_score, away_score) below. Mirrors (does not import) the
# path tables resolver_registry._HIST_PATHS / schedule_context_resolver's
# _CALENDAR_PATHS mirror the same convention: same files, local copy because
# this resolver computes a DIFFERENT shape (series aggregate, not one score
# or rest/b2b).
_SOURCES = {
    "nba": ("data/domains/basketball_nba/linescores.parquet", "home_abbr", "away_abbr", "quarters"),
    "mlb": ("data/domains/mlb/games.parquet", "home_team", "away_team", "runs"),
    "soccer": ("data/domains/soccer/matches.parquet", "home_team", "away_team", "goals"),
}
_TENNIS_PATH = "data/domains/tennis/atlas_h2h.parquet"


def _team_scores(df: pd.DataFrame, kind: str) -> tuple[pd.Series, pd.Series]:
    if kind == "quarters":
        home = df[[c for c in df.columns if c.startswith("home_q")]].sum(axis=1)
        away = df[[c for c in df.columns if c.startswith("away_q")]].sum(axis=1)
    elif kind == "runs":
        home, away = df["home_runs"], df["away_runs"]
    else:  # goals
        home, away = df["fthg"], df["ftag"]
    return home.astype(int), away.astype(int)


def _resolve_team_code(sport: str, name: str, candidates: set) -> str | None:
    """Same free-text -> corpus-code resolution schedule_context_resolver.resolve()
    already uses (exact/upper match -> NBA alias table -> cross-sport
    canonicalizer scan) -- mirrored here, not imported, because that helper is
    inlined inside resolve() there rather than exposed as its own function."""
    name_stripped = re.sub(r"^the\s+", "", name.strip(), flags=re.I)
    if name_stripped in candidates:
        return name_stripped
    upper = name_stripped.upper()
    if upper in candidates:
        return upper
    if sport == "nba":
        full = _nba_names.resolve(name_stripped)
        if full and full in candidates:
            return full
    target_key = _team_canonical(sport, name_stripped)
    for code in candidates:
        if _team_canonical(sport, code) == target_key:
            return code
    return None


def _series_aggregate(sub: pd.DataFrame, home_col: str, away_col: str,
                       team_a: str, team_b: str, as_of: str | None) -> dict:
    sub = sub.sort_values("date")
    a_is_home = sub[home_col] == team_a
    a_score = sub["home_score"].where(a_is_home, sub["away_score"])
    b_score = sub["away_score"].where(a_is_home, sub["home_score"])
    diff_pair = a_score - b_score
    diff_home = sub["home_score"] - sub["away_score"]
    wins_a = int((diff_pair > 0).sum())
    wins_b = int((diff_pair < 0).sum())
    draws = int((diff_pair == 0).sum())
    n = len(sub)
    tail = sub.tail(_LAST_N).iloc[::-1]
    last_n_form = [{
        "date": str(r["date"])[:10],
        "result": "W" if a_score.loc[i] > b_score.loc[i] else ("L" if a_score.loc[i] < b_score.loc[i] else "D"),
        "score": f"{int(a_score.loc[i])}-{int(b_score.loc[i])}",
    } for i, r in tail.iterrows()]
    series_leader = team_a if wins_a > wins_b else (team_b if wins_b > wins_a else None)
    return {
        "games_played": n, "wins_a": wins_a, "wins_b": wins_b, "draws": draws,
        "series_leader": series_leader,
        "differential_pair_perspective_mean": round(float(diff_pair.mean()), 2),
        "differential_pair_perspective_cumulative": int(diff_pair.sum()),
        "differential_home_perspective_mean": round(float(diff_home.mean()), 2),
        "differential_home_perspective_cumulative": int(diff_home.sum()),
        "last_n_form": last_n_form,
        "as_of": as_of if as_of else str(sub["date"].max())[:10],
    }


def _resolve_team_sport(sport: str, team_a: str, team_b: str, as_of: str | None) -> dict:
    path, home_col, away_col, kind = _SOURCES[sport]
    if not os.path.exists(_abs(path)):
        return {"status": "no_data", "category": "h2h_history", "sport": sport,
                "source_artifact": path, "framing": FRAMING}
    df = pd.read_parquet(_abs(path))
    df = df.assign(date=pd.to_datetime(df["date"]))
    candidates = set(df[home_col]) | set(df[away_col])
    code_a = _resolve_team_code(sport, team_a, candidates)
    code_b = _resolve_team_code(sport, team_b, candidates)
    if not (code_a and code_b):
        return {"status": "no_data", "category": "h2h_history", "sport": sport, "source_artifact": path,
                "framing": FRAMING,
                "note": f"could not resolve team(s) team_a={team_a!r} ({code_a}) team_b={team_b!r} ({code_b})"}
    mask = ((df[home_col] == code_a) & (df[away_col] == code_b)) | \
           ((df[home_col] == code_b) & (df[away_col] == code_a))
    sub = df[mask].copy()
    if as_of:
        sub = sub[sub["date"] < pd.Timestamp(as_of)]
    if sub.empty:
        return {"status": "no_data", "category": "h2h_history", "sport": sport, "source_artifact": path,
                "framing": FRAMING,
                "note": f"zero rows matched team_a={code_a!r} team_b={code_b!r} as_of={as_of!r} -- refusing, not guessing"}
    home_score, away_score = _team_scores(sub, kind)
    sub = sub.assign(home_score=home_score, away_score=away_score)
    agg = _series_aggregate(sub, home_col, away_col, code_a, code_b, as_of)
    return {"status": "ok", "category": "h2h_history", "sport": sport, "source_artifact": path,
            "framing": FRAMING, "team_a": code_a, "team_b": code_b, **agg}


def _resolve_tennis(team_a: str, team_b: str, as_of: str | None) -> dict:
    if not os.path.exists(_abs(_TENNIS_PATH)):
        return {"status": "no_data", "category": "h2h_history", "sport": "tennis",
                "source_artifact": _TENNIS_PATH, "framing": FRAMING}
    df = pd.read_parquet(_abs(_TENNIS_PATH))
    df = df.assign(date=pd.to_datetime(df["date"]))
    names = pd.unique(pd.concat([df["p1_name"], df["p2_name"]]))

    def _match_name(q: str) -> str | None:
        ql = q.strip().lower()
        for c in names:
            if str(c).strip().lower() == ql:
                return c
        for c in names:
            cl = str(c).strip().lower()
            if ql in cl or cl.split()[-1] == ql.split()[-1]:
                return c
        return None

    name_a, name_b = _match_name(team_a), _match_name(team_b)
    if not (name_a and name_b):
        return {"status": "no_data", "category": "h2h_history", "sport": "tennis",
                "source_artifact": _TENNIS_PATH, "framing": FRAMING,
                "note": f"could not resolve player(s) team_a={team_a!r} team_b={team_b!r}"}
    mask = ((df["p1_name"] == name_a) & (df["p2_name"] == name_b)) | \
           ((df["p1_name"] == name_b) & (df["p2_name"] == name_a))
    sub = df[mask].copy()
    if as_of:
        sub = sub[sub["date"] < pd.Timestamp(as_of)]
    if sub.empty:
        return {"status": "no_data", "category": "h2h_history", "sport": "tennis",
                "source_artifact": _TENNIS_PATH, "framing": FRAMING,
                "note": f"zero rows matched team_a={name_a!r} team_b={name_b!r} as_of={as_of!r} -- refusing, not guessing"}
    sub = sub.sort_values("date")
    a_won = ((sub["p1_name"] == name_a) & (sub["winner"] == 1)) | ((sub["p2_name"] == name_a) & (sub["winner"] == 2))
    wins_a = int(a_won.sum())
    wins_b = int(len(sub) - wins_a)
    surface_split: dict[str, dict] = {}
    for surf, grp in sub.groupby("surface"):
        surface_split[str(surf)] = {"n": int(len(grp)), "wins_a": int(a_won.loc[grp.index].sum())}
    tail = sub.tail(_LAST_N).iloc[::-1]
    last_n_form = [{"date": str(r["date"])[:10],
                     "winner": name_a if a_won.loc[i] else name_b,
                     "surface": str(r.get("surface", ""))} for i, r in tail.iterrows()]
    series_leader = name_a if wins_a > wins_b else (name_b if wins_b > wins_a else None)
    return {"status": "ok", "category": "h2h_history", "sport": "tennis", "source_artifact": _TENNIS_PATH,
            "framing": FRAMING, "team_a": name_a, "team_b": name_b,
            "games_played": int(len(sub)), "wins_a": wins_a, "wins_b": wins_b, "draws": 0,
            "series_leader": series_leader, "surface_split": surface_split, "last_n_form": last_n_form,
            "as_of": as_of if as_of else str(sub["date"].max())[:10],
            "note": "tennis atlas_h2h.parquet carries no set-score margin -- no point differential for this sport"}


def resolve(sport: str, team_a: str, team_b: str, as_of: str | None = None) -> dict:
    sport = sport.lower()
    if sport == "tennis":
        return _resolve_tennis(team_a, team_b, as_of)
    if sport not in _SOURCES:
        return {"status": "not_supported", "category": "h2h_history", "sport": sport,
                "note": f"h2h_history not wired for sport '{sport}' -- available: "
                        f"{sorted(list(_SOURCES) + ['tennis'])}"}
    return _resolve_team_sport(sport, team_a, team_b, as_of)


def main(argv=None):
    p = argparse.ArgumentParser(description="Query the h2h-history resolver directly.")
    p.add_argument("sport")
    p.add_argument("team_a")
    p.add_argument("team_b")
    p.add_argument("--as-of", default=None, dest="as_of", help="YYYY-MM-DD, truncate to games before this date")
    a = p.parse_args(argv)
    print(json.dumps(resolve(a.sport, a.team_a, a.team_b, a.as_of), indent=2, default=str))


if __name__ == "__main__":
    main()
