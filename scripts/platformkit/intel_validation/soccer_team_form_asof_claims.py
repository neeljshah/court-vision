"""Soccer team recent-FORM as-of claims (HIGHEST value family, covers ~5 of
the 73 team-grain resolver fails: clean-sheet rate, form, home/away split).

Source: data/domains/soccer/matches.parquet ONLY (event_id, date, season,
home_team, away_team, fthg, ftag, ftr) -- no stats-file dependency, per spec.

LEAK-FREE / AS-OF (verified, not assumed): for each team we sort its matches
chronologically (mergesort, stable), then DROP that team's own most-recent
match before computing any trailing window -- the exact same discipline as
``.shift(1)`` over a per-match as-of column, just applied once to build the
single "current form" snapshot this family publishes (a ranking claim is one
row per team, not one row per match, so there is no need to materialize the
full per-match as-of series). A team's L10/season stat therefore NEVER
includes the outcome of the match it is "as of" -- verified in
test_soccer_team_form_asof_claims.py's as-of-shift test.

Metrics (entity_key="team", full population above floor, descriptive only):
  ppg_l10, winrate_l10, gf_l10, ga_l10, gd_l10, clean_sheet_rate_l10 --
      trailing <=10 STRICTLY PRIOR matches (all venues), floor n_prior>=10.
  clean_sheet_rate_season -- prior matches in the team's own latest season,
      floor n_prior_season>=5.
  ppg_home_l10, clean_sheet_rate_home -- trailing <=10 prior HOME matches
      only, floor n_prior_home>=10.
  ppg_away_l10, clean_sheet_rate_away -- trailing <=10 prior AWAY matches
      only, floor n_prior_away>=10.

Clean sheet: home CS = ftag==0 (conceded 0 as home team); away CS = fthg==0.
ppg: 3/1/0 for win/draw/loss from that team's own perspective.

DESCRIPTIVE only: no forecast, no market claim.

CLI:
    python -m scripts.platformkit.intel_validation.soccer_team_form_asof_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/soccer_team_form_asof_claims.jsonl \
        --output data/cache/intel_claims/soccer_team_form_asof_claims_validation.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_SOCCER_DIR = REPO_ROOT / "data" / "domains" / "soccer"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_SNAPSHOT = _OUT_DIR / "soccer_team_form_asof_snapshot.parquet"
_CLAIMS_OUT = _OUT_DIR / "soccer_team_form_asof_claims.jsonl"

SOURCE_FILE = "matches.parquet"
WINDOW = 10  # trailing-N prior matches
L10_FLOOR = 10
SEASON_FLOOR = 5
WINDOW_TAG = "trailing10_asof_corpus_end"

# (snapshot column, metric name, description, floor column, floor value)
_METRICS = (
    ("ppg_l10", "ppg_l10", "points per game over trailing 10 prior matches (all venues)", "n_prior", L10_FLOOR),
    ("winrate_l10", "winrate_l10", "win rate over trailing 10 prior matches (all venues)", "n_prior", L10_FLOOR),
    ("gf_l10", "gf_l10", "goals-for per game over trailing 10 prior matches", "n_prior", L10_FLOOR),
    ("ga_l10", "ga_l10", "goals-against per game over trailing 10 prior matches", "n_prior", L10_FLOOR),
    ("gd_l10", "gd_l10", "goal difference per game over trailing 10 prior matches", "n_prior", L10_FLOOR),
    ("clean_sheet_rate_l10", "clean_sheet_rate_l10", "clean sheet rate over trailing 10 prior matches", "n_prior", L10_FLOOR),
    ("clean_sheet_rate_season", "clean_sheet_rate_season", "clean sheet rate, prior matches in team's current season", "n_prior_season", SEASON_FLOOR),
    ("ppg_home_l10", "ppg_home_l10", "points per game, trailing 10 prior HOME matches", "n_prior_home", L10_FLOOR),
    ("ppg_away_l10", "ppg_away_l10", "points per game, trailing 10 prior AWAY matches", "n_prior_away", L10_FLOOR),
    ("clean_sheet_rate_home", "clean_sheet_rate_home", "clean sheet rate, trailing 10 prior HOME matches", "n_prior_home", L10_FLOOR),
    ("clean_sheet_rate_away", "clean_sheet_rate_away", "clean sheet rate, trailing 10 prior AWAY matches", "n_prior_away", L10_FLOOR),
)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _load_matches() -> pd.DataFrame:
    p = _SOCCER_DIR / SOURCE_FILE
    df = pd.read_parquet(p, columns=["event_id", "date", "season", "home_team", "away_team", "fthg", "ftag", "ftr"])
    return df.dropna(subset=["date", "home_team", "away_team", "fthg", "ftag", "ftr"])


def build_long_frame(matches: pd.DataFrame) -> pd.DataFrame:
    """One row per team per match (home + away perspective), globally sorted
    by date (mergesort, stable -- on-disk order is not assumed date-sorted)."""
    home = matches.rename(columns={"home_team": "team", "away_team": "opp", "fthg": "gf", "ftag": "ga"})
    home = home[["event_id", "date", "season", "team", "opp", "gf", "ga", "ftr"]].copy()
    home["venue"] = "home"
    home["pts"] = np.select([home["ftr"] == "H", home["ftr"] == "D"], [3, 1], default=0)
    home["win"] = (home["ftr"] == "H").astype(int)

    away = matches.rename(columns={"away_team": "team", "home_team": "opp", "ftag": "gf", "fthg": "ga"})
    away = away[["event_id", "date", "season", "team", "opp", "gf", "ga", "ftr"]].copy()
    away["venue"] = "away"
    away["pts"] = np.select([away["ftr"] == "A", away["ftr"] == "D"], [3, 1], default=0)
    away["win"] = (away["ftr"] == "A").astype(int)

    long = pd.concat([home, away], ignore_index=True)
    long["cs"] = (long["ga"] == 0).astype(int)
    return long.sort_values("date", kind="mergesort").reset_index(drop=True)


def _trailing_mean(prior: pd.DataFrame, col: str, window: int) -> float:
    tail = prior.tail(window)
    return float(tail[col].mean()) if len(tail) else float("nan")


def build_snapshot(long_df: pd.DataFrame, window: int = WINDOW, season_floor: int = SEASON_FLOOR) -> pd.DataFrame:
    """One row per team: the team's CURRENT form snapshot -- every trailing
    stat is computed from matches STRICTLY BEFORE the team's own most recent
    match (that match is dropped before any window is taken), so no metric
    ever leaks its own "as of" match's result."""
    rows: list[dict[str, Any]] = []
    for team, grp in long_df.groupby("team", sort=False):
        grp = grp.sort_values("date", kind="mergesort").reset_index(drop=True)
        prior = grp.iloc[:-1]  # drop the team's own latest match (leak-free as-of)
        n_prior = len(prior)

        cur_season = grp["season"].iloc[-1]
        season_prior = prior[prior["season"] == cur_season]
        n_prior_season = len(season_prior)

        home_prior_all = prior[prior["venue"] == "home"]
        away_prior_all = prior[prior["venue"] == "away"]
        n_prior_home = len(home_prior_all)
        n_prior_away = len(away_prior_all)

        trail = prior.tail(window)
        gf_l10 = _trailing_mean(prior, "gf", window)
        ga_l10 = _trailing_mean(prior, "ga", window)

        rows.append({
            "team": str(team),
            "n_prior": n_prior,
            "ppg_l10": _trailing_mean(prior, "pts", window),
            "winrate_l10": _trailing_mean(prior, "win", window),
            "gf_l10": gf_l10,
            "ga_l10": ga_l10,
            "gd_l10": (gf_l10 - ga_l10) if len(trail) else float("nan"),
            "clean_sheet_rate_l10": _trailing_mean(prior, "cs", window),
            "n_prior_season": n_prior_season,
            "clean_sheet_rate_season": float(season_prior["cs"].mean()) if n_prior_season else float("nan"),
            "n_prior_home": n_prior_home,
            "ppg_home_l10": _trailing_mean(home_prior_all, "pts", window),
            "clean_sheet_rate_home": _trailing_mean(home_prior_all, "cs", window),
            "n_prior_away": n_prior_away,
            "ppg_away_l10": _trailing_mean(away_prior_all, "pts", window),
            "clean_sheet_rate_away": _trailing_mean(away_prior_all, "cs", window),
        })
    return pd.DataFrame(rows)


def write_snapshot(snap: pd.DataFrame, out_path: Path = _SNAPSHOT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snap.to_parquet(out_path, index=False)
    return out_path


def build_claim(snap: pd.DataFrame, column: str, metric_name: str, description: str,
                 floor_col: str, floor_value: int) -> dict[str, Any]:
    n_considered = len(snap)
    qualifiers = snap[snap[floor_col] >= floor_value].dropna(subset=[column]).copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values(column, ascending=False).reset_index(drop=True)

    ranking = [
        {"rank": i, "team": str(r.team), "value": round(float(getattr(r, column)), 4),
         floor_col: int(getattr(r, floor_col))}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": f"soccer_team_form_asof_{metric_name}_{WINDOW_TAG}",
        "kind": "ranking",
        "question": f"Soccer: full-population team ranking by {description}?",
        "criteria": {
            "metric": metric_name, "formula": column, "window": WINDOW_TAG,
            "aggregate": None, "min_sample": {floor_col: floor_value},
            "direction": "desc", "value_precision": 4, "entity_key": "team",
        },
        "ranking": ranking,
        "source_files": [_rel(_SNAPSHOT)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            "DESCRIPTIVE current-form snapshot, not a forecast, no market claim.",
            f"min_sample floor {floor_col}>={floor_value}; below-floor teams are counted in "
            "n_excluded_below_floor, never silently dropped.",
            "AS-OF/leak-free: every trailing stat is computed from matches STRICTLY BEFORE "
            "the team's own most recent match (that match is dropped before any window is "
            "taken) -- the snapshot never includes the outcome it is 'as of'.",
            f"{column} = {description}; snapshot parquet this store owns carries the "
            "precomputed value, formula is an identity read of that column.",
            "Pooled across six divisions (EPL/Championship/La Liga/Serie A/Ligue 1/Bundesliga) "
            "and seasons 2015-2026; a club's rows are not partitioned by division.",
            "FULL POPULATION: every team clearing the floor is ranked, no top-N cap.",
        ],
    }


def build_all_claims(snap: pd.DataFrame) -> list[dict[str, Any]]:
    """One claim per metric -- but SKIP (never emit) any metric where zero
    teams clear its floor; an empty ranking is not a claim the validator can
    confirm, and the honest move is to omit it rather than publish a
    zero-row 'claim'."""
    claims = [build_claim(snap, col, name, desc, floor_col, floor_val)
              for col, name, desc, floor_col, floor_val in _METRICS]
    return [c for c in claims if c["ranking"]]


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit soccer team form-as-of DESCRIPTIVE ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    long_df = build_long_frame(_load_matches())
    snap = build_snapshot(long_df)
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
