"""2025-26 (additive, same-store) sibling of nba_schedule_claims.py.

Split into its own file so nba_schedule_claims.py's 2024-25 rows stay
byte-stable and that module's LOC stays at its existing cap (that module's
test file hard-monkeypatches sc._SEASON / sc._GAME_SNAPSHOT and asserts
sc.build_all_claims() returns exactly the 5 2024-25 claims -- widening it
in place would break that contract). Reuses every shared helper (snapshot
writer, three-in-four counter, mean-claim assembler, floors, the closed-
predictive caveat) from that module; only the season and its own
season-scoped snapshot paths/claim ids differ.

games.parquet's 2025-26 slice may still be in-progress for some teams --
handled honestly, no special-casing: MIN_GAMES_FLOOR (half a season)
excludes any team below it into n_excluded_below_floor, same as the
2024-25 sibling would for a hypothetical partial season.

CLI: python -m scripts.platformkit.intel_validation.nba_schedule_claims_2025_26
  (regenerates the WHOLE store: 2024-25 unchanged rows + 2025-26 additive rows)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from scripts.platformkit.intel_validation.nba_schedule_claims import (
    _CLAIMS_OUT,
    _CLOSED_CAVEAT,
    _GAMES,
    _OUT_DIR,
    _build_mean_claim,
    _rel,
    _three_in_four_counts,
    _write_parquet,
    MIN_GAMES_FLOOR,
    THREE_IN_FOUR_WINDOW_DAYS,
    build_all_claims as build_2024_25_claims,
    write_claims,
)

SEASON = "2025-26"
_SEASON_ID = SEASON.replace("-", "_")
_GAME_SNAPSHOT = _OUT_DIR / f"nba_schedule_game_dims_snapshot_{_SEASON_ID}.parquet"
_STREAK_SNAPSHOT = _OUT_DIR / f"nba_schedule_road_trip_streak_snapshot_{_SEASON_ID}.parquet"
_LONGEST_TRIP_SNAPSHOT = _OUT_DIR / f"nba_schedule_longest_road_trip_snapshot_{_SEASON_ID}.parquet"


def build_game_dims_snapshot() -> tuple[Path, pd.DataFrame]:
    """Season-2025-26 sibling of nba_schedule_claims.build_game_dims_snapshot
    -- identical derivation, own season filter + own snapshot path."""
    games = pd.read_parquet(_GAMES)
    season_games = games[games["season"] == SEASON].copy()
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
        ["game_id", "team", "date", "is_away", "rest_days", "is_b2b", "is_three_in_four", "n_games"]
    ].reset_index(drop=True)
    _write_parquet(snapshot, _GAME_SNAPSHOT)
    return _GAME_SNAPSHOT, snapshot


def build_road_trip_streak_snapshot(game_snapshot: pd.DataFrame) -> tuple[Path, pd.DataFrame]:
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


def build_back_to_back_claim(path: Path, snapshot: pd.DataFrame) -> dict[str, Any]:
    return _build_mean_claim(
        f"nba_schedule_back_to_back_rate_{_SEASON_ID}",
        f"What share of a team's {SEASON} games were on 0-days rest (back-to-back)?",
        "back_to_back_rate", "sum(is_b2b)/count(is_b2b)", "is_b2b", snapshot, path, 4,
        f"population: {SEASON} schedule on disk; floor n_games>={MIN_GAMES_FLOOR} (half "
        "season) enforced honestly -- excludes any team below it (e.g. still in progress).",
        season=SEASON,
    )


def build_avg_rest_days_claim(path: Path, snapshot: pd.DataFrame) -> dict[str, Any]:
    return _build_mean_claim(
        f"nba_schedule_avg_rest_days_{_SEASON_ID}",
        f"What is a team's average days-of-rest between {SEASON} games?",
        "avg_rest_days", "mean(rest_days)", "rest_days", snapshot, path, 4,
        "n counts VALID rest_days observations only -- first game of the season has no prior "
        "game, excluded (never zero-filled), so n is games_played-1 not games_played.",
        dropna=True, season=SEASON,
    )


def build_three_in_four_claim(path: Path, snapshot: pd.DataFrame) -> dict[str, Any]:
    return _build_mean_claim(
        f"nba_schedule_three_in_four_rate_{_SEASON_ID}",
        f"What share of a team's {SEASON} games were the 3rd+ in a trailing 4-day window?",
        "three_in_four_rate", "sum(is_three_in_four)/count(is_three_in_four)",
        "is_three_in_four", snapshot, path, 4,
        "DEFINITION: a game counts as 3-in-4 if >= 3 of the team's own games (incl. itself) "
        f"fall inside the trailing [-{THREE_IN_FOUR_WINDOW_DAYS}, 0] day window -- a "
        "schedule-density spot, not a prediction of outcome.",
        season=SEASON,
    )


def build_road_trip_avg_len_claim(path: Path, streaks: pd.DataFrame) -> dict[str, Any]:
    claim = _build_mean_claim(
        f"nba_schedule_road_trip_avg_len_{_SEASON_ID}",
        f"What was a team's average road-trip length (consecutive away games) in {SEASON}?",
        "road_trip_avg_len", "mean(streak_len)", "streak_len", streaks, path, 4,
        "n is the team's total number of distinct road-trip streaks (denominator of the "
        "mean), NOT games played -- every streak (incl. length-1) counted once.",
        season=SEASON,
    )
    claim["caveats"].insert(1, (
        "dims_corpus_absent: MILES traveled per trip needs venue lat/lon geocoding this corpus "
        "does not carry as a raw fact this lane independently derives -- honestly absent, "
        "never fabricated. Length-in-games only."
    ))
    return claim


def build_longest_road_trip_claim(streaks: pd.DataFrame) -> dict[str, Any]:
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
        "claim_id": f"nba_schedule_longest_road_trip_{_SEASON_ID}",
        "kind": "ranking",
        "question": f"What was a team's longest consecutive-away-games streak in {SEASON}?",
        "criteria": {
            "metric": "longest_road_trip", "formula": "longest_road_trip", "window": SEASON,
            "min_sample": {"n_games": MIN_GAMES_FLOOR}, "direction": "desc",
            "value_precision": 0, "entity_key": "team",
        },
        "ranking": ranking,
        "source_files": [_rel(_LONGEST_TRIP_SNAPSHOT)],
        "computed_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "value is a game COUNT (integer), not a rate. n is the team's total number of "
            "distinct road-trip streaks (incl. length-1) for cross-checking against "
            "road_trip_avg_len's n.",
            _CLOSED_CAVEAT,
        ],
    }


def build_season_claims() -> list[dict[str, Any]]:
    """The 5 nba_schedule_* claims for 2025-26 only (additive rows)."""
    game_path, game_snapshot = build_game_dims_snapshot()
    streak_path, streaks = build_road_trip_streak_snapshot(game_snapshot)
    return [
        build_back_to_back_claim(game_path, game_snapshot),
        build_avg_rest_days_claim(game_path, game_snapshot),
        build_three_in_four_claim(game_path, game_snapshot),
        build_longest_road_trip_claim(streaks),
        build_road_trip_avg_len_claim(streak_path, streaks),
    ]


def build_all_claims() -> list[dict[str, Any]]:
    """2024-25 (unchanged, via the original module) + 2025-26 (additive)."""
    return build_2024_25_claims() + build_season_claims()


def main() -> int:
    claims = build_all_claims()
    out_path = write_claims(claims, _CLAIMS_OUT)
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
