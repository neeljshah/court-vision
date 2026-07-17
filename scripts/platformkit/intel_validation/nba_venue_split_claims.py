"""NBA venue-split DESCRIPTIVE ranking claim (Depth-wave-2 Lane D).

STEP-0 PREMISE: data/domains/basketball_nba/espn_boxscores*.parquet already
carries home_abbr/away_abbr/home_score/away_score PER GAME -- a flagged
box source, so this lane is a LIGHT READ, never a PBP re-parse. Two files
are used (base espn_boxscores.parquet spans 2024-25 + 2025-26; the sibling
espn_boxscores_2024_25.parquet is a date-overlapping DUPE of the same
2024-25 games under different event_ids -- confirmed by 777/1235 date+team
key collisions -- and is skipped to avoid double-counting a team's home/away
game count). espn_boxscores_2023_24.parquet adds the earlier season (zero
date overlap with the base file).

Metric: per-team mean home points-per-game minus mean away points-per-game
(entity_key="team"), floor >=10 home AND >=10 away games. DESCRIPTIVE only:
no forecast, no market claim, venue effects are market-priced.

Snapshot: this lane precomputes a per-team snapshot parquet (raw_value =
the diff) and uses formula="raw_value" (identity, same tautological-by-
construction contract as wnba_zone_context_claims.py) because the diff
itself -- not a single row -- is the claimed quantity.

CLI:
    python -m scripts.platformkit.intel_validation.nba_venue_split_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/nba_venue_split_claims.jsonl \
        --output data/cache/intel_claims/nba_venue_split_claims_validation.json
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
_SNAPSHOT = _OUT_DIR / "nba_venue_split_snapshot.parquet"
_CLAIMS_OUT = _OUT_DIR / "nba_venue_split_claims.jsonl"

# base file (2024-25 + 2025-26, continuous) + the pre-base season only.
# espn_boxscores_2024_25.parquet is DELIBERATELY excluded -- it duplicates
# the base file's 2024-25 games under different event_ids.
SOURCE_FILES = ("espn_boxscores.parquet", "espn_boxscores_2023_24.parquet")

# normalize the base file's inconsistent abbrevs (GS/GSW, NY/NYK, SA/SAS,
# UTAH/UTA, NO/NOP, WSH/WAS) to one canonical 3-letter code per team.
ABBR_MAP = {"GS": "GSW", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "NO": "NOP", "WSH": "WAS"}
_ALLSTAR_ABBRS = {"STARS", "STRIPES"}  # not real franchises -- drop

FLOOR = 10
WINDOW = "espn_boxscores_2023_24_to_2025_26"


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _load_games() -> pd.DataFrame:
    frames = []
    for name in SOURCE_FILES:
        p = _NBA_DIR / name
        df = pd.read_parquet(p, columns=["home_abbr", "away_abbr", "home_score", "away_score"])
        frames.append(df)
    games = pd.concat(frames, ignore_index=True)
    games = games.dropna(subset=["home_abbr", "away_abbr", "home_score", "away_score"])
    games = games[~games["home_abbr"].isin(_ALLSTAR_ABBRS) & ~games["away_abbr"].isin(_ALLSTAR_ABBRS)]
    games["home_abbr"] = games["home_abbr"].replace(ABBR_MAP)
    games["away_abbr"] = games["away_abbr"].replace(ABBR_MAP)
    return games


def build_snapshot() -> pd.DataFrame:
    """One row per team: n_home/home_ppg, n_away/away_ppg, raw_value=diff."""
    games = _load_games()
    home = games.rename(columns={"home_abbr": "team", "home_score": "pts"})[["team", "pts"]]
    away = games.rename(columns={"away_abbr": "team", "away_score": "pts"})[["team", "pts"]]
    home_agg = home.groupby("team")["pts"].agg(n_home="count", home_ppg="mean")
    away_agg = away.groupby("team")["pts"].agg(n_away="count", away_ppg="mean")
    snap = home_agg.join(away_agg, how="outer").reset_index()
    snap[["n_home", "n_away"]] = snap[["n_home", "n_away"]].fillna(0)
    snap["raw_value"] = (snap["home_ppg"] - snap["away_ppg"]).round(4)
    return snap


def write_snapshot(snap: pd.DataFrame, out_path: Path = _SNAPSHOT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snap.to_parquet(out_path, index=False)
    return out_path


def build_claim(snap: pd.DataFrame) -> dict[str, Any]:
    n_considered = len(snap)
    qualifiers = snap[(snap["n_home"] >= FLOOR) & (snap["n_away"] >= FLOOR)].dropna(subset=["raw_value"]).copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values("raw_value", ascending=False).reset_index(drop=True)

    ranking = [
        {"rank": i, "team": str(r.team), "value": round(float(r.raw_value), 4),
         "n_home": int(r.n_home), "n_away": int(r.n_away)}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": f"nba_venue_split_home_minus_away_ppg_{WINDOW}",
        "kind": "ranking",
        "question": "NBA: full-population ranking by home-minus-away points-per-game split?",
        "criteria": {
            "metric": "home_minus_away_ppg", "formula": "raw_value", "window": WINDOW,
            "aggregate": None, "min_sample": {"n_home": FLOOR, "n_away": FLOOR},
            "direction": "desc", "value_precision": 4, "entity_key": "team",
        },
        "ranking": ranking,
        "source_files": [_rel(_SNAPSHOT)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            "DESCRIPTIVE home/away split, not a forecast, venue effects are market-priced, "
            "no market claim.",
            f"min_sample floor n_home>={FLOOR} AND n_away>={FLOOR}; teams below either floor "
            "are counted in n_excluded_below_floor, never silently dropped.",
            "raw_value = mean home points-per-game minus mean away points-per-game, precomputed "
            "in the snapshot parquet this store owns; formula is an identity read of that column.",
            "FULL POPULATION: every team clearing both floors is ranked, no top-N cap.",
        ],
    }


def write_claims(claim: dict[str, Any], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA venue-split DESCRIPTIVE ranking claim")
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
