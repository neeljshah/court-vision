"""NBA schedule DESCRIPTOR claims (PROGRAM v3 direction, lane nba-travel-descriptive).

Emits 5 DESCRIPTIVE per-team dims for the 2024-25 season (last FULLY COMPLETE
season on disk -- 2025-26 is in-progress, 1156/1230 games, would bias the
floor): back_to_back_rate (share of games on 0-days rest), avg_rest_days
(mean days since prior game, first game excluded not zero-filled),
three_in_four_rate (share of games that are the 3rd+ in a trailing 4-day
window), longest_road_trip (max consecutive-away-game streak length),
road_trip_avg_len (mean streak length, incl. length-1). All 5 are pure
functions of (date, home_team, away_team) -- no venue geo, no odds, no outcome.

SOURCE CHOICE (verified this lane, in order): (1) data/cache/venue_history/
espn_scoreboard/nba/*.json -- the literal owned ESPN bridge corpus named in
the brief. VERIFIED (schema read): one file/date, events[].competitions[].
competitors[].homeAway + .date parse cleanly, BUT only 93 dates (2023-02-23..
2023-06-12, late-reg-season + playoffs) -> min 22 games/team, playoffs-skewed
(no true b2b in a 2-2-1-1-1 series) -> CANNOT support floor n_games>=41,
honestly insufficient. (2) data/domains/basketball_nba/games.parquet (the
sanctioned fallback glob) -- 4 full seasons, clean home_team/away_team/date,
already the schedule source 10+ platformkit modules (edge_hunt_schedule.py,
edge_hunt_scoreboard.py, nba_outcome_resolver.py, eb_base_rates.py, ...) read
read-only. 2024-25 slice = 30/30 teams x 82/82 games, zero gaps. USED here.

PREDICTIVE CLASS STAYS CLOSED (do not re-attempt): edge_hunt_schedule.py
("HUNT A") already scored b2b/3-in-4/rest-diff/long-road-trip as PREDICTIVE
signals (HOME-minus-AWAY diff) via the real eval_gate vs the Shin-devigged
close -> expected honest REJECT ("the market prices raw schedule physics").
This module re-derives the SAME facts only as SCOUTING/DESCRIPTIVE per-team
dims (no market/outcome join, no SHIP/REJECT language) -- a different
question family, not a re-attempt.

dims_corpus_absent: miles-traveled-per-trip needs venue lat/lon geocoding this
corpus lacks as a raw fact (travel_home/away are a derived distance the
closed predictive gate uses) -- honestly listed, never fabricated.
NETWORK: zero. DESCRIPTIVE / SCOUTING ONLY -- NO PREDICTIVE OR MARKET-EDGE CLAIM.

CLI: python -m scripts.platformkit.intel_validation.nba_schedule_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[3]

_GAMES = REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_SEASON = "2024-25"  # last FULLY COMPLETE season on disk (2025-26 is in-progress)

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "nba_schedule_claims.jsonl"
_GAME_SNAPSHOT = _OUT_DIR / "nba_schedule_game_dims_snapshot.parquet"
_STREAK_SNAPSHOT = _OUT_DIR / "nba_schedule_road_trip_streak_snapshot.parquet"
_LONGEST_TRIP_SNAPSHOT = _OUT_DIR / "nba_schedule_longest_road_trip_snapshot.parquet"

MIN_GAMES_FLOOR = 41  # brief-stated floor: half an 82-game season
THREE_IN_FOUR_WINDOW_DAYS = 3  # trailing [-3, 0] calendar days = a 4-day window

# Shared predictive-closure caveat for all 5 dims; each claim prepends its own DEFINITION.
_CLOSED_CAVEAT = (
    "DESCRIPTIVE schedule fact only. The PREDICTIVE version of this exact signal "
    "(HOME-minus-AWAY differential vs the Shin-devigged close) is CLOSED per "
    "scripts/platformkit/edge_hunt_schedule.py (honest REJECT, not re-attempted here). "
    "No market/$ edge claimed."
)

def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)

def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")

def _three_in_four_counts(dates: pd.Series) -> np.ndarray:
    """For each date (sorted ascending, one team's own games), count how many
    of the team's own games (incl. itself) fall in the trailing [-3, 0]
    window ending there."""
    vals = dates.values
    out = np.zeros(len(vals), dtype=np.int64)
    for i in range(len(vals)):
        window_start = vals[i] - np.timedelta64(THREE_IN_FOUR_WINDOW_DAYS, "D")
        out[i] = int(np.sum((vals >= window_start) & (vals <= vals[i])))
    return out

def build_game_dims_snapshot() -> tuple[Path, pd.DataFrame]:
    """One row per team-per-game for the season: is_b2b / rest_days /
    is_three_in_four derived from each team's own sorted date sequence.
    First game of the season -> rest_days=NaN, is_b2b=0 (never fabricated)."""
    games = pd.read_parquet(_GAMES)
    season_games = games[games["season"] == _SEASON].copy()
    season_games["date"] = pd.to_datetime(season_games["date"]).dt.normalize()

    home = season_games[["game_id", "date", "home_team"]].rename(columns={"home_team": "team"})
    home["is_away"] = 0
    away = season_games[["game_id", "date", "away_team"]].rename(columns={"away_team": "team"})
    away["is_away"] = 1
    long_df = pd.concat([home, away], ignore_index=True)
    long_df = long_df.sort_values(["team", "date"]).reset_index(drop=True)

    long_df["prev_date"] = long_df.groupby("team")["date"].shift(1)
    long_df["rest_days"] = (long_df["date"] - long_df["prev_date"]).dt.days.astype("float64")
    long_df["is_b2b"] = (long_df["rest_days"] == 1.0).astype("int64")
    long_df["tif_count"] = long_df.groupby("team")["date"].transform(_three_in_four_counts)
    long_df["is_three_in_four"] = (long_df["tif_count"] >= 3).astype("int64")
    long_df["n_games"] = long_df.groupby("team")["game_id"].transform("count").astype("int64")

    snapshot = long_df[
        ["game_id", "team", "date", "is_away", "rest_days", "is_b2b",
         "is_three_in_four", "n_games"]
    ].reset_index(drop=True)
    _write_parquet(snapshot, _GAME_SNAPSHOT)
    return _GAME_SNAPSHOT, snapshot

def build_road_trip_streak_snapshot(game_snapshot: pd.DataFrame) -> tuple[Path, pd.DataFrame]:
    """One row per (team, road-trip streak): a maximal run of consecutive
    away games. Every streak counted once (incl. length-1)."""
    df = game_snapshot.sort_values(["team", "date"]).reset_index(drop=True).copy()
    prev_is_away = df.groupby("team")["is_away"].shift(1)
    df["streak_change"] = (df["is_away"] != prev_is_away).astype("int64")
    df["streak_id"] = df.groupby("team")["streak_change"].cumsum()

    away_only = df[df["is_away"] == 1]
    streaks = away_only.groupby(["team", "streak_id"], as_index=False).agg(
        streak_len=("game_id", "count"), n_games=("n_games", "first"),
    ).reset_index(drop=True)
    _write_parquet(streaks, _STREAK_SNAPSHOT)
    return _STREAK_SNAPSHOT, streaks

def _build_mean_claim(
    claim_id: str, question: str, metric: str, formula: str,
    col: str, snapshot: pd.DataFrame, source_path: Path,
    round_digits: int, definition_caveat: str, dropna: bool = False, season: str = _SEASON,
) -> dict[str, Any]:
    """Shared builder for the 4 rate/mean dims -- SAME shape (group-by team,
    mean of one column, n_games floor, desc rank), differing only in which
    column, its formula string, and its own DEFINITION caveat."""
    working = snapshot.dropna(subset=[col]) if dropna else snapshot
    per_team = working.groupby("team", as_index=False).agg(
        value=(col, "mean"), n=(col, "count"), n_games=("n_games", "first"),
    )
    n_considered = len(per_team)
    qualifying = per_team[per_team["n_games"] >= MIN_GAMES_FLOOR].copy()
    n_excluded = n_considered - len(qualifying)
    qualifying = qualifying.sort_values("value", ascending=False).reset_index(drop=True)

    ranking = [
        {"rank": i, "team": str(r.team), "value": round(float(r.value), round_digits),
         "n": int(r.n), "n_games": int(r.n_games)}
        for i, r in enumerate(qualifying.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": claim_id,
        "kind": "ranking",
        "question": question,
        "criteria": {
            "metric": metric, "formula": formula, "window": season,
            "min_sample": {"n_games": MIN_GAMES_FLOOR}, "direction": "desc",
            "value_precision": round_digits, "entity_key": "team",
            "aggregate": {"group_by": "team", "derived": {"n_games": "mean(n_games)"}},
        },
        "ranking": ranking,
        "source_files": [_rel(source_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [definition_caveat, _CLOSED_CAVEAT],
    }

def build_back_to_back_claim(path: Path, snapshot: pd.DataFrame) -> dict[str, Any]:
    return _build_mean_claim(
        "nba_schedule_back_to_back_rate_2024_25",
        f"What share of a team's {_SEASON} games were on 0-days rest (back-to-back)?",
        "back_to_back_rate", "sum(is_b2b)/count(is_b2b)", "is_b2b", snapshot, path, 4,
        f"FULL POPULATION: all 30 teams' {_SEASON} schedule; floor n_games>={MIN_GAMES_FLOOR} "
        "excludes none this season (82/82/team) but enforced for a future partial-season.",
    )

def build_avg_rest_days_claim(path: Path, snapshot: pd.DataFrame) -> dict[str, Any]:
    return _build_mean_claim(
        "nba_schedule_avg_rest_days_2024_25",
        f"What is a team's average days-of-rest between {_SEASON} games?",
        "avg_rest_days", "mean(rest_days)", "rest_days", snapshot, path, 4,
        "n counts VALID rest_days observations only -- first game of the season has no prior "
        f"game, excluded (never zero-filled), so n is games_played-1 not games_played.",
        dropna=True,
    )

def build_three_in_four_claim(path: Path, snapshot: pd.DataFrame) -> dict[str, Any]:
    return _build_mean_claim(
        "nba_schedule_three_in_four_rate_2024_25",
        f"What share of a team's {_SEASON} games were the 3rd+ in a trailing 4-day window?",
        "three_in_four_rate", "sum(is_three_in_four)/count(is_three_in_four)",
        "is_three_in_four", snapshot, path, 4,
        "DEFINITION: a game counts as 3-in-4 if >= 3 of the team's own games (incl. itself) "
        f"fall inside the trailing [-{THREE_IN_FOUR_WINDOW_DAYS}, 0] day window -- a "
        "schedule-density spot, not a prediction of outcome.",
    )

def build_road_trip_avg_len_claim(path: Path, streaks: pd.DataFrame) -> dict[str, Any]:
    claim = _build_mean_claim(
        "nba_schedule_road_trip_avg_len_2024_25",
        f"What was a team's average road-trip length (consecutive away games) in {_SEASON}?",
        "road_trip_avg_len", "mean(streak_len)", "streak_len", streaks, path, 4,
        "n is the team's total number of distinct road-trip streaks (denominator of the "
        "mean), NOT games played -- every streak (incl. length-1) counted once.",
    )
    claim["caveats"].insert(1, (
        "dims_corpus_absent: MILES traveled per trip needs venue lat/lon geocoding this corpus "
        "does not carry as a raw fact this lane independently derives -- honestly absent, "
        "never fabricated. Length-in-games only."
    ))
    return claim

def build_longest_road_trip_claim(streaks: pd.DataFrame) -> dict[str, Any]:
    """max() isn't in the aggregate grammar (sum/mean/count/count_distinct
    only) -> NON-aggregate path over a per-team table MATERIALIZED to disk
    (bare-column formula needs a real on-disk column), like scheme_identity."""
    per_team = streaks.groupby("team", as_index=False).agg(
        longest_road_trip=("streak_len", "max"), n_games=("n_games", "first"),
        n_streaks=("streak_len", "count"),
    ).reset_index(drop=True)
    _write_parquet(per_team, _LONGEST_TRIP_SNAPSHOT)

    n_considered = len(per_team)
    qualifying = per_team[per_team["n_games"] >= MIN_GAMES_FLOOR].copy()
    n_excluded = n_considered - len(qualifying)
    qualifying = qualifying.sort_values("longest_road_trip", ascending=False).reset_index(drop=True)

    ranking = [
        {"rank": i, "team": str(r.team), "value": int(r.longest_road_trip),
         "n": int(r.n_streaks), "n_games": int(r.n_games)}
        for i, r in enumerate(qualifying.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": "nba_schedule_longest_road_trip_2024_25",
        "kind": "ranking",
        "question": f"What was a team's longest consecutive-away-games streak in {_SEASON}?",
        "criteria": {
            "metric": "longest_road_trip", "formula": "longest_road_trip", "window": _SEASON,
            "min_sample": {"n_games": MIN_GAMES_FLOOR}, "direction": "desc",
            "value_precision": 0, "entity_key": "team",
        },
        "ranking": ranking,
        "source_files": [_rel(_LONGEST_TRIP_SNAPSHOT)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "value is a game COUNT (integer), not a rate. n is the team's total number of "
            "distinct road-trip streaks (incl. length-1) for cross-checking against "
            "road_trip_avg_len's n.",
            _CLOSED_CAVEAT,
        ],
    }

def build_all_claims() -> list[dict[str, Any]]:
    game_path, game_snapshot = build_game_dims_snapshot()
    streak_path, streaks = build_road_trip_streak_snapshot(game_snapshot)
    return [
        build_back_to_back_claim(game_path, game_snapshot),
        build_avg_rest_days_claim(game_path, game_snapshot),
        build_three_in_four_claim(game_path, game_snapshot),
        build_longest_road_trip_claim(streaks),
        build_road_trip_avg_len_claim(streak_path, streaks),
    ]

def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA schedule descriptor claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = build_all_claims()
    out_path = write_claims(claims, Path(args.output))
    for c in claims:
        top1 = c["ranking"][0] if c["ranking"] else None
        print(
            f"{c['claim_id']}: n_considered={c['n_considered']} "
            f"n_excluded_below_floor={c['n_excluded_below_floor']} rows={len(c['ranking'])} "
            f"top1={top1}"
        )
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
