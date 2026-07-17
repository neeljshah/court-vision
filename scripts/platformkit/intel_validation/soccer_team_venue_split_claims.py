"""Soccer team venue-split DESCRIPTIVE ranking claims (direct sibling of
nba_venue_split_claims.py -- same identity-formula snapshot pattern).

STEP-0 PREMISE: data/domains/soccer/matches.parquet already carries
home_team/away_team/fthg/ftag/ftr PER MATCH, team-grain, 25,834 rows across
six divisions (E0=EPL, E1=Championship, SP1=La Liga, I1=Serie A, F1=Ligue 1,
D1=Bundesliga), seasons 2015-2025 -- a flagged box source, so this lane is a
LIGHT READ, never a re-scrape. No per-division split: a club's rows across
whatever division(s) it occupied in this window are pooled under its team
name (promotion/relegation is not partitioned out -- noted in caveats).

Metrics (entity_key="team", all "home minus away" sign, positive = bigger
home advantage on that dimension):
  - gf_diff      = mean home goals-for/game  minus mean away goals-for/game
  - ga_diff      = mean away goals-against/game minus mean home goals-against/game
                    (flipped so positive still means "better at home")
  - winrate_diff = home win rate minus away win rate

FLOOR: n_home>=20 AND n_away>=20 per team. A single top-5-league season is
19 home + 19 away games; requiring >=20 in each filters out teams present
for only one truncated/relegated season while keeping any team with a full
season or more in the window. Below-floor teams are counted honestly in
n_excluded_below_floor, never silently dropped.

Snapshot: this lane precomputes a per-team snapshot parquet (gf_diff/
ga_diff/winrate_diff columns) and each claim's formula is an identity read
of its own column (same tautological-by-construction contract as
nba_venue_split_claims.py) because the diff itself -- not a single row --
is the claimed quantity.

DESCRIPTIVE only: no forecast, no market claim, venue effects are
market-priced.

CLI:
    python -m scripts.platformkit.intel_validation.soccer_team_venue_split_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/soccer_team_venue_split_claims.jsonl \
        --output data/cache/intel_claims/soccer_team_venue_split_claims_validation.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_SOCCER_DIR = REPO_ROOT / "data" / "domains" / "soccer"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_SNAPSHOT = _OUT_DIR / "soccer_team_venue_split_snapshot.parquet"
_CLAIMS_OUT = _OUT_DIR / "soccer_team_venue_split_claims.jsonl"

SOURCE_FILE = "matches.parquet"
FLOOR = 20
WINDOW = "matches_2015_to_2025_all_div"

# (snapshot column, metric name, human description) -- one claim per row.
_METRICS = (
    ("gf_diff", "gf_diff", "home minus away goals-for per game"),
    ("ga_diff", "ga_diff", "away minus home goals-against per game (positive = fewer conceded at home)"),
    ("winrate_diff", "winrate_diff", "home minus away win rate"),
)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _load_matches() -> pd.DataFrame:
    p = _SOCCER_DIR / SOURCE_FILE
    df = pd.read_parquet(p, columns=["home_team", "away_team", "fthg", "ftag", "ftr"])
    return df.dropna(subset=["home_team", "away_team", "fthg", "ftag", "ftr"])


def build_snapshot() -> pd.DataFrame:
    """One row per team: n_home/n_away + home/away goals-for/against/win-rate
    + the three home-minus-away diff columns claims are ranked on."""
    matches = _load_matches()

    home = matches.rename(columns={"home_team": "team", "fthg": "gf", "ftag": "ga"})[["team", "gf", "ga", "ftr"]]
    home["win"] = (home["ftr"] == "H").astype(int)
    away = matches.rename(columns={"away_team": "team", "ftag": "gf", "fthg": "ga"})[["team", "gf", "ga", "ftr"]]
    away["win"] = (away["ftr"] == "A").astype(int)

    home_agg = home.groupby("team").agg(
        n_home=("gf", "count"), home_gf_pg=("gf", "mean"),
        home_ga_pg=("ga", "mean"), home_win_rate=("win", "mean"),
    )
    away_agg = away.groupby("team").agg(
        n_away=("gf", "count"), away_gf_pg=("gf", "mean"),
        away_ga_pg=("ga", "mean"), away_win_rate=("win", "mean"),
    )
    snap = home_agg.join(away_agg, how="outer").reset_index()
    snap[["n_home", "n_away"]] = snap[["n_home", "n_away"]].fillna(0)
    snap["gf_diff"] = (snap["home_gf_pg"] - snap["away_gf_pg"]).round(4)
    snap["ga_diff"] = (snap["away_ga_pg"] - snap["home_ga_pg"]).round(4)
    snap["winrate_diff"] = (snap["home_win_rate"] - snap["away_win_rate"]).round(4)
    return snap


def write_snapshot(snap: pd.DataFrame, out_path: Path = _SNAPSHOT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snap.to_parquet(out_path, index=False)
    return out_path


def build_claim(snap: pd.DataFrame, column: str, metric_name: str, description: str) -> dict[str, Any]:
    n_considered = len(snap)
    qualifiers = snap[(snap["n_home"] >= FLOOR) & (snap["n_away"] >= FLOOR)].dropna(subset=[column]).copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values(column, ascending=False).reset_index(drop=True)

    ranking = [
        {"rank": i, "team": str(r.team), "value": round(float(getattr(r, column)), 4),
         "n_home": int(r.n_home), "n_away": int(r.n_away)}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": f"soccer_team_venue_split_{metric_name}_{WINDOW}",
        "kind": "ranking",
        "question": f"Soccer: full-population team ranking by {description}?",
        "criteria": {
            "metric": metric_name, "formula": column, "window": WINDOW,
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
            f"{column} = {description}; sign is normalized so positive always means "
            "'stronger at home' across all three venue-split metrics in this family.",
            "Pooled across six divisions (EPL/Championship/La Liga/Serie A/Ligue 1/Bundesliga) "
            "and seasons 2015-2025; a club's rows are NOT partitioned by division/season, so "
            "promotion/relegation years are pooled under one team name.",
            "raw diff columns are precomputed in the snapshot parquet this store owns; formula "
            "is an identity read of that column.",
            "FULL POPULATION: every team clearing both floors is ranked, no top-N cap.",
        ],
    }


def build_all_claims(snap: pd.DataFrame) -> list[dict[str, Any]]:
    return [build_claim(snap, column, metric_name, description) for column, metric_name, description in _METRICS]


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit soccer team venue-split DESCRIPTIVE ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    snap = build_snapshot()
    write_snapshot(snap)
    claims = build_all_claims(snap)
    out_path = write_claims(claims, Path(args.output))

    for c in claims:
        top1 = c["ranking"][0] if c["ranking"] else None
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} n_ranked={len(c['ranking'])} top1={top1}")
    print(f"wrote snapshot -> {_SNAPSHOT}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
