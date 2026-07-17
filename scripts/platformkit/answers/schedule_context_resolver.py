"""Schedule-context resolver: rest days / back-to-back / recent-games-density
for one team, computed DIRECTLY off the public games calendar -- no market
data, no prediction, descriptive schedule physics only (see module framing
note baked into every envelope below).

Reuses (read-only):
  - the games-calendar parquet paths resolver_registry.historical_result
    already reads (data/domains/<sport>/{linescores,games}.parquet) -- same
    files, mirrored here as a local table because this resolver computes a
    DIFFERENT shape (rest/b2b/density) than historical_result's final score.
  - scripts.platformkit.intel_query.ask.load_verified_claims(), scoped via
    pairs_for_claim_stores(("nba_schedule_claims.jsonl",)) to JUST that one
    store, for the nba_schedule_claims.jsonl VERIFIED rows (rest/b2b/road-trip
    rankings) -- the pinned 2024-25 numbers ride alongside the live calendar
    computation, never re-derived here. A bare load_verified_claims() call
    whole-loads EVERY store in data/cache/intel_claims (GB-scale bulk rate
    stores included) to keep a 15KB family -- see pairs_for_claim_stores'
    own docstring (the 2026-07-07 MemoryError guard compose_best.py and
    compose_profile.py already route through).

Per-sport coverage (honest): nba (linescores.parquet) and mlb (games.parquet)
only -- same two sports historical_result covers. Any other sport -> not_supported.

Team-code landmine: linescores.parquet uses ESPN-short NBA abbreviations
(GS, NO, NY, SA, UTAH, WSH) while nba_schedule_claims.jsonl uses the
3-letter codes (GSW, NOP, NYK, SAS, UTA, WAS) -- 6 of 30 teams differ.
_NBA_CLAIMS_TO_CALENDAR / its reverse let a caller pass EITHER convention.

Rest-days convention (pin this down -- off-by-one is the classic bug):
  rest_days = (as_of_date - prior_game_date).days - 1
  i.e. the count of FULL days with no game between the prior game and as_of.
  Game played yesterday -> delta=1 -> rest_days=0 -> is_b2b=True. This
  matches nba_schedule_claims.jsonl's own back_to_back_rate framing ("0-days
  rest (back-to-back)").
  games_in_last_7 counts games with date in [as_of-7d, as_of) -- the
  trailing week strictly BEFORE as_of, as_of's own game (if any) not counted.

Run: python -m scripts.platformkit.answers.schedule_context_resolver nba LAL --date 2025-11-01
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone

import pandas as pd

from scripts.platformkit.intel_query.ask import load_verified_claims, pairs_for_claim_stores

FRAMING = "schedule physics is public-calendar descriptive context, not a prediction or edge claim"

# the ONLY store this resolver reads -- loaded via pairs_for_claim_stores so a
# bare load_verified_claims() never whole-loads the other (GB-scale) stores
# under data/cache/intel_claims/ to keep this one 15KB family.
_SCHEDULE_CLAIM_STORES: tuple[str, ...] = ("nba_schedule_claims.jsonl",)

# same two (path, home_col, away_col) triples resolver_registry.historical_result
# reads -- mirrored, not imported (different resolver, same source files).
_CALENDAR_PATHS = {
    "nba": ("data/domains/basketball_nba/linescores.parquet", "home_abbr", "away_abbr"),
    "mlb": ("data/domains/mlb/games.parquet", "home_team", "away_team"),
}

_NBA_CLAIMS_TO_CALENDAR = {"GSW": "GS", "NOP": "NO", "NYK": "NY", "SAS": "SA", "UTA": "UTAH", "WAS": "WSH"}
_NBA_CALENDAR_TO_CLAIMS = {v: k for k, v in _NBA_CLAIMS_TO_CALENDAR.items()}


def _calendar_code(sport: str, team_u: str) -> str:
    return _NBA_CLAIMS_TO_CALENDAR.get(team_u, team_u) if sport == "nba" else team_u


def _claims_code(sport: str, team_u: str) -> str:
    return _NBA_CALENDAR_TO_CLAIMS.get(team_u, team_u) if sport == "nba" else team_u


def _schedule_claims(sport: str, team_claims_code: str) -> list[dict]:
    """VERIFIED nba_schedule_claims.jsonl ranking rows that mention this
    team, compact facts only (claim_id/metric/value/rank/n) -- never the
    full claim row (source_files/criteria noise stays out of the envelope).
    NBA-only: no equivalent verified schedule-claims store exists for mlb."""
    if sport != "nba":
        return []
    out = []
    verified = load_verified_claims(pairs_for_claim_stores(_SCHEDULE_CLAIM_STORES))
    for cid, row in sorted(verified.items()):
        if not cid.startswith("nba_schedule_"):
            continue
        for entry in row.get("ranking", []):
            if entry.get("team") == team_claims_code:
                out.append({"claim_id": cid, "metric": row.get("criteria", {}).get("metric"),
                             "value": entry.get("value"), "rank": entry.get("rank"),
                             "n": entry.get("n"), "n_games": entry.get("n_games")})
                break
    return out


def resolve(sport: str, team: str, date: str | None = None) -> dict:
    sport = sport.lower()
    cfg = _CALENDAR_PATHS.get(sport)
    if cfg is None:
        return {"status": "not_supported", "category": "schedule_context", "sport": sport,
                "framing": FRAMING, "note": f"schedule_context not wired for sport '{sport}' "
                                             f"-- available: {sorted(_CALENDAR_PATHS)}"}
    path, home_col, away_col = cfg
    if not os.path.exists(path):
        return {"status": "no_data", "category": "schedule_context", "sport": sport,
                "source_artifact": path, "framing": FRAMING}
    team_u = team.upper()
    calendar_team = _calendar_code(sport, team_u)
    claims_team = _claims_code(sport, team_u)
    df = pd.read_parquet(path)
    as_of = pd.Timestamp(date) if date else pd.Timestamp(datetime.now(timezone.utc).date())
    games = df[(df[home_col] == calendar_team) | (df[away_col] == calendar_team)].sort_values("date")
    if games.empty:
        return {"status": "no_data", "category": "schedule_context", "sport": sport,
                "source_artifact": path, "framing": FRAMING,
                "note": f"zero rows matched team={team!r} (calendar code {calendar_team!r})"}
    prior = games[games["date"] < as_of]
    trailing_week = games[(games["date"] >= as_of - timedelta(days=7)) & (games["date"] < as_of)]
    as_of_iso = as_of.date().isoformat()
    base = {"status": "ok", "category": "schedule_context", "sport": sport, "source_artifact": path,
            "as_of": as_of_iso, "framing": FRAMING, "team": claims_team,
            "games_in_last_7": int(len(trailing_week)),
            "schedule_claims": _schedule_claims(sport, claims_team)}
    if prior.empty:
        return {**base, "rest_days": None, "is_b2b": False, "prior_game_date": None,
                "note": "no prior game before as_of in this calendar (first game of sample, or as_of predates the corpus)"}
    prior_date = prior["date"].iloc[-1]
    rest_days = (as_of - prior_date).days - 1
    return {**base, "rest_days": int(rest_days), "is_b2b": rest_days == 0,
            "prior_game_date": prior_date.date().isoformat()}


def main(argv=None):
    p = argparse.ArgumentParser(description="Query the schedule-context resolver directly.")
    p.add_argument("sport")
    p.add_argument("team")
    p.add_argument("--date", default=None, help="YYYY-MM-DD, default today (UTC)")
    a = p.parse_args(argv)
    print(json.dumps(resolve(a.sport, a.team, a.date), indent=2, default=str))


if __name__ == "__main__":
    main()
