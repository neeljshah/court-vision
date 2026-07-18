"""answers.conditional_winprob_resolver -- Family 2: descriptive rest-conditioned
win-rate resolver. Answers "how does home win prob change on a back-to-back /
short rest" with an EMPIRICAL base-rate split computed straight off the public
games calendar -- NOT a new predictor, and NOT a conditional-delta path inside
winprob_dispatch.py/predict_matchup.py (which has none). Calibration-language
framing only (.claude/rules/no-edge-claims.md): a real, verifiable historical
split (P(home win) | rest bucket, with n + Wilson 95% CI so a thin cell is
visibly thin), never a market edge, never a $ number, never an invented
conditional probability -- every figure is a direct aggregate over completed
games.

Complements (never replaces) winprob_dispatch.dispatch() -- that module still
owns the ONE predictive point forecast; this module answers a DIFFERENT,
purely descriptive question ("does rest correlate with the outcome,
historically") with its own receipt.

Sources (verified columns):
  nba:    data/domains/basketball_nba/games.parquet -- NATIVE rest_days_home,
          home_b2b, home_win, home_team (verified: home b2b win-rate 0.501
          vs non-b2b 0.566).
  mlb:    data/domains/mlb/games.parquet -- rest DERIVED per-team from date
          deltas (99.9% non-null, median 1 day); target_home_win native.
  soccer: data/domains/soccer/matches.parquet -- rest DERIVED per-team from
          date deltas; home win = ftr == "H".

Rest buckets (home team's own rest before this game):
  b2b_or_1d (rest_days <= 1) / 2-3d (2-3) / 4d_plus (>= 4).
The b2b flag (0 days rest exactly) is ALSO reported standalone since it is the
literal, most-quoted split ("home win-rate falls on a back-to-back").
A derived-rest row with rest_days < 0 (e.g. a doubleheader nightcap sharing
its prior game's date) is dropped, not miscounted as a real short-rest game.

Optional `team=` scopes the population to that team's home games only -- n
shrinks fast per team, which is exactly why the Wilson CI is reported: a
thin per-team cell stays visibly thin, never silently overstated.

Run: python -m scripts.platformkit.answers.conditional_winprob_resolver nba
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re

import pandas as pd

from domains.basketball_nba import team_name_resolver as _nba_names
from scripts.platformkit.odds_provider.team_resolver import canonical as _team_canonical

FRAMING = ("descriptive base-rate delta computed off the public games calendar -- "
           "NOT a new predictor, NOT part of predict_matchup.py's model, never a market edge")

_SOURCES = {
    "nba": "data/domains/basketball_nba/games.parquet",
    "mlb": "data/domains/mlb/games.parquet",
    "soccer": "data/domains/soccer/matches.parquet",
}
_BUCKET_LABELS = ["b2b_or_1d", "2-3d", "4d_plus"]


def _wilson_ci(k: int, n: int, z: float = 1.96) -> list | None:
    """Wilson score 95% CI for a binomial rate, [lo, hi] rounded to 4dp. None
    if n==0. (Same small formula as scripts/platformkit/execution/fill_model/
    meta_label_buckets.wilson_ci -- kept local so this answers/ resolver never
    pulls in that unrelated paper-trading-ledger module.)"""
    if n == 0:
        return None
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / denom
    return [round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)]


def _rate(mask: pd.Series, home_win: pd.Series) -> dict:
    n = int(mask.sum())
    k = int(home_win[mask].sum()) if n else 0
    return {"n": n, "p_home_win": round(k / n, 4) if n else None, "ci95": _wilson_ci(k, n)}


def _derive_rest_days(df: pd.DataFrame) -> pd.Series:
    """Home team's rest days before THIS game, derived from date deltas
    across BOTH its home and away appearances in the whole (as_of-truncated)
    corpus -- vectorized, same convention schedule_context_resolver uses for
    one team at a time (game yesterday -> rest_days=0 -> b2b)."""
    home = pd.DataFrame({"date": df["date"], "team": df["home_team"], "side": "home"}, index=df.index)
    away = pd.DataFrame({"date": df["date"], "team": df["away_team"], "side": "away"}, index=df.index)
    long = pd.concat([home, away]).sort_values(["team", "date"])
    long["prev_date"] = long.groupby("team")["date"].shift(1)
    long["rest_days"] = (long["date"] - long["prev_date"]).dt.days - 1
    return long[long["side"] == "home"]["rest_days"].reindex(df.index)


def _bucket_label(rest_days: pd.Series) -> pd.Series:
    return pd.cut(rest_days, bins=[-1, 1, 3, 10_000], labels=_BUCKET_LABELS)


def _resolve_team_code(sport: str, name: str, candidates: set) -> str | None:
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


def resolve(sport: str, as_of: str | None = None, team: str | None = None) -> dict:
    sport = sport.lower()
    path = _SOURCES.get(sport)
    if path is None:
        return {"status": "not_supported", "category": "conditional_winprob", "sport": sport,
                "note": f"conditional_winprob not wired for sport '{sport}' -- available: {sorted(_SOURCES)}"}
    if not os.path.exists(path):
        return {"status": "no_data", "category": "conditional_winprob", "sport": sport,
                "source_artifact": path, "framing": FRAMING}
    df = pd.read_parquet(path)
    df = df.assign(date=pd.to_datetime(df["date"]))
    if as_of:
        df = df[df["date"] < pd.Timestamp(as_of)]

    if sport == "nba":
        rest_days = df["rest_days_home"]
        is_b2b = df["home_b2b"].astype(bool)
        home_win = df["home_win"].astype(bool)
    else:
        rest_days = _derive_rest_days(df)
        valid = rest_days.notna() & (rest_days >= 0)
        df, rest_days = df[valid], rest_days[valid]
        is_b2b = rest_days == 0
        home_win = df["target_home_win"].astype(bool) if sport == "mlb" else (df["ftr"] == "H")

    team_code = None
    if team:
        team_code = _resolve_team_code(sport, team, set(df["home_team"]))
        if team_code is None:
            return {"status": "no_data", "category": "conditional_winprob", "sport": sport,
                    "source_artifact": path, "framing": FRAMING,
                    "note": f"could not resolve team {team!r} for a home-games scope"}
        scope = df["home_team"] == team_code
        rest_days, is_b2b, home_win = rest_days[scope], is_b2b[scope], home_win[scope]

    if len(home_win) == 0:
        return {"status": "no_data", "category": "conditional_winprob", "sport": sport, "source_artifact": path,
                "framing": FRAMING, "team": team_code,
                "note": "zero rows matched after filtering (as_of/team) -- refusing, not guessing"}

    buckets = _bucket_label(rest_days)
    bucket_table = {label: _rate(buckets == label, home_win) for label in _BUCKET_LABELS}

    return {
        "status": "ok", "category": "conditional_winprob", "sport": sport, "source_artifact": path,
        "as_of": as_of if as_of else str(df["date"].max())[:10], "framing": FRAMING, "team": team_code,
        "b2b": _rate(is_b2b, home_win), "non_b2b": _rate(~is_b2b, home_win),
        "rest_buckets": bucket_table, "overall": _rate(pd.Series(True, index=home_win.index), home_win),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Query the conditional-winprob (rest-bucket) resolver directly.")
    p.add_argument("sport")
    p.add_argument("--as-of", default=None, dest="as_of")
    p.add_argument("--team", default=None)
    a = p.parse_args(argv)
    print(json.dumps(resolve(a.sport, a.as_of, a.team), indent=2, default=str))


if __name__ == "__main__":
    main()
