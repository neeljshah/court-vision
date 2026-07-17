"""NBA rest-adjusted-form DESCRIPTIVE ranking claim (light-lane, mirrors
nba_venue_split_claims.py exactly -- commit 4e06c720).

STEP-0 PREMISE: same flagged box source as nba_venue_split_claims.py
(data/domains/basketball_nba/espn_boxscores.parquet + the 2023_24 sibling),
now also reading `date` -- already a per-game column, so still a LIGHT READ,
never a PBP re-parse. espn_boxscores_2024_25.parquet stays excluded (LANDMINE:
it duplicates the base file's 2024-25 games under different event_ids).

Metric: per team, mean points-per-game on 0-1 days rest (b2b/short) minus
mean points-per-game on 2+ days rest (entity_key="team"), rest computed from
consecutive game dates per team (rest_days = gap_in_days - 1; a next-day game
is rest_days=0). Floor: >=8 games in EACH bucket, teams below either floor
are counted in n_excluded_below_floor, never silently dropped. DESCRIPTIVE
only: schedule effects are public-calendar and market-priced, no forecast,
no market claim.

Snapshot: identity formula="raw_value" (same tautological-by-construction
contract as nba_venue_split_claims.py) because the diff itself -- not a
single row -- is the claimed quantity.

CLI:
    python -m scripts.platformkit.intel_validation.nba_rest_adjusted_form_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/nba_rest_adjusted_form_claims.jsonl \
        --output data/cache/intel_claims/nba_rest_adjusted_form_claims_validation.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_NBA_DIR = REPO_ROOT / "data" / "domains" / "basketball_nba"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_SNAPSHOT = _OUT_DIR / "nba_rest_adjusted_form_snapshot.parquet"
_CLAIMS_OUT = _OUT_DIR / "nba_rest_adjusted_form_claims.jsonl"

# base file (2024-25 + 2025-26, continuous) + the pre-base season only.
# espn_boxscores_2024_25.parquet is DELIBERATELY excluded -- it duplicates
# the base file's 2024-25 games under different event_ids.
SOURCE_FILES = ("espn_boxscores.parquet", "espn_boxscores_2023_24.parquet")

# same abbrev normalization as nba_venue_split_claims.py.
ABBR_MAP = {"GS": "GSW", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "NO": "NOP", "WSH": "WAS"}
_ALLSTAR_ABBRS = {"STARS", "STRIPES"}  # not real franchises -- drop

FLOOR = 8
SHORT_REST_MAX_DAYS = 1  # rest_days <= 1 -> short/b2b bucket, else long-rest bucket
WINDOW = "espn_boxscores_2023_24_to_2025_26"


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _load_games() -> pd.DataFrame:
    frames = []
    for name in SOURCE_FILES:
        p = _NBA_DIR / name
        df = pd.read_parquet(p, columns=["date", "home_abbr", "away_abbr", "home_score", "away_score"])
        frames.append(df)
    games = pd.concat(frames, ignore_index=True)
    games = games.dropna(subset=["date", "home_abbr", "away_abbr", "home_score", "away_score"])
    games = games[~games["home_abbr"].isin(_ALLSTAR_ABBRS) & ~games["away_abbr"].isin(_ALLSTAR_ABBRS)]
    games["home_abbr"] = games["home_abbr"].replace(ABBR_MAP)
    games["away_abbr"] = games["away_abbr"].replace(ABBR_MAP)
    return games


def _team_game_log(games: pd.DataFrame) -> pd.DataFrame:
    """One row per (team, game): date, pts. Concat of the home and away sides."""
    home = games.rename(columns={"home_abbr": "team", "home_score": "pts"})[["team", "date", "pts"]]
    away = games.rename(columns={"away_abbr": "team", "away_score": "pts"})[["team", "date", "pts"]]
    log = pd.concat([home, away], ignore_index=True)
    log = log.sort_values(["team", "date"]).drop_duplicates(subset=["team", "date"])
    return log


def build_snapshot() -> pd.DataFrame:
    """One row per team: n_short/short_ppg (0-1 days rest), n_long/long_ppg
    (2+ days rest), raw_value=diff. A team's first game has no prior date --
    unknown rest -- and is excluded from bucketing (not counted either way)."""
    games = _load_games()
    log = _team_game_log(games)
    log["prev_date"] = log.groupby("team")["date"].shift(1)
    log = log.dropna(subset=["prev_date"])
    log["rest_days"] = (log["date"] - log["prev_date"]).dt.days - 1
    log["bucket"] = log["rest_days"].apply(lambda r: "short" if r <= SHORT_REST_MAX_DAYS else "long")

    short = log[log["bucket"] == "short"].groupby("team")["pts"].agg(n_short="count", short_ppg="mean")
    long_ = log[log["bucket"] == "long"].groupby("team")["pts"].agg(n_long="count", long_ppg="mean")
    snap = short.join(long_, how="outer").reset_index()
    snap[["n_short", "n_long"]] = snap[["n_short", "n_long"]].fillna(0)
    snap["raw_value"] = (snap["short_ppg"] - snap["long_ppg"]).round(4)
    return snap


def write_snapshot(snap: pd.DataFrame, out_path: Path = _SNAPSHOT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snap.to_parquet(out_path, index=False)
    return out_path


def build_claim(snap: pd.DataFrame) -> dict[str, Any]:
    n_considered = len(snap)
    qualifiers = snap[(snap["n_short"] >= FLOOR) & (snap["n_long"] >= FLOOR)].dropna(subset=["raw_value"]).copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values("raw_value", ascending=True).reset_index(drop=True)

    ranking = [
        {"rank": i, "team": str(r.team), "value": round(float(r.raw_value), 4),
         "n_short": int(r.n_short), "n_long": int(r.n_long)}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": f"nba_rest_adjusted_form_short_minus_long_rest_ppg_{WINDOW}",
        "kind": "ranking",
        "question": "NBA: full-population ranking by short-rest-minus-long-rest points-per-game split?",
        "criteria": {
            "metric": "short_minus_long_rest_ppg", "formula": "raw_value", "window": WINDOW,
            "aggregate": None, "min_sample": {"n_short": FLOOR, "n_long": FLOOR},
            "direction": "asc", "value_precision": 4, "entity_key": "team",
        },
        "ranking": ranking,
        "source_files": [_rel(_SNAPSHOT)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            "DESCRIPTIVE rest-split, schedule effects are public-calendar and market-priced, "
            "not a forecast, no market claim.",
            f"min_sample floor n_short>={FLOOR} AND n_long>={FLOOR}; teams below either floor "
            "are counted in n_excluded_below_floor, never silently dropped.",
            f"rest bucket: short = 0-{SHORT_REST_MAX_DAYS} days rest (b2b/short turnaround), "
            "long = 2+ days rest; rest_days computed from consecutive game dates per team, "
            "a team's first game in the window has unknown rest and is excluded from bucketing.",
            "raw_value = mean short-rest points-per-game minus mean long-rest points-per-game, "
            "precomputed in the snapshot parquet this store owns; formula is an identity read "
            "of that column.",
            "FULL POPULATION: every team clearing both floors is ranked, no top-N cap. Sorted "
            "ascending (most negative = biggest b2b/short-rest scoring dropoff, first).",
        ],
    }


def write_claims(claim: dict[str, Any], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA rest-adjusted-form DESCRIPTIVE ranking claim")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    snap = build_snapshot()
    write_snapshot(snap)
    claim = build_claim(snap)
    out_path = write_claims(claim, Path(args.output))

    top3 = claim["ranking"][:3]
    print(f"{claim['claim_id']}: n_considered={claim['n_considered']} "
          f"n_excluded_below_floor={claim['n_excluded_below_floor']} n_ranked={len(claim['ranking'])}")
    print(f"top3={top3}")
    print(f"wrote snapshot -> {_SNAPSHOT}")
    print(f"wrote claim -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
