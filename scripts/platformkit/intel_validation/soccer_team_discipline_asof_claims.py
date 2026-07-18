"""Soccer team discipline (cards) as-of claims (covers the discipline/cards
resolver fail). Wraps the existing EW discipline builder for the per-match
as-of metrics, plus a light prior-only season-to-date cards rate computed
directly from the raw match_stats sidecar (spec's sanctioned "Fallback raw"
path -- match_stats yellow/red/fouls columns are 100% non-null).

Sources:
  - domains.soccer.asof_discipline_features.build_asof_disc_frame() over
    data/domains/soccer/match_stats.parquet -- prior-only EW (ALPHA-decayed)
    yellow/red/fouls per team (verified builder, "for"-only, no re-derivation
    of its internals here).
  - data/domains/soccer/matches.parquet -- event_id/date/season/home_team/
    away_team, to attach team identity, chronological order, and season.
  - data/domains/soccer/match_stats.parquet raw home_yellow/away_yellow/
    home_red/away_red columns, for the season-to-date rate only (a light,
    prior-only expanding mean within the team's current season -- same
    leak-free discipline as soccer_team_form_asof_claims.py's season stat:
    the team's own most-recent match is dropped before any window is taken).

Metrics: yellow_per_game_asof, red_per_game_asof, cards_per_game_asof
(yellow+red), fouls_per_game_asof (all light-read EW as-of, floor
n_prior>=10), plus cards_rate_season (prior-only season-to-date mean of
yellow+red, floor n_prior_season>=5).

DESCRIPTIVE only: no forecast, no market claim.

CLI:
    python -m scripts.platformkit.intel_validation.soccer_team_discipline_asof_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/soccer_team_discipline_asof_claims.jsonl \
        --output data/cache/intel_claims/soccer_team_discipline_asof_claims_validation.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from domains.soccer.asof_discipline_features import build_asof_disc_frame

REPO_ROOT = Path(__file__).resolve().parents[3]
_SOCCER_DIR = REPO_ROOT / "data" / "domains" / "soccer"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_SNAPSHOT = _OUT_DIR / "soccer_team_discipline_asof_snapshot.parquet"
_CLAIMS_OUT = _OUT_DIR / "soccer_team_discipline_asof_claims.jsonl"

EW_FLOOR = 10
SEASON_FLOOR = 5
WINDOW_TAG = "asof_last_match"

# (snapshot column, metric name, description, floor column, floor value)
_METRICS = (
    ("yellow_per_game_asof", "yellow_per_game_asof", "yellow cards per game (EW as-of), last match", "n_prior", EW_FLOOR),
    ("red_per_game_asof", "red_per_game_asof", "red cards per game (EW as-of), last match", "n_prior", EW_FLOOR),
    ("cards_per_game_asof", "cards_per_game_asof", "total cards per game (EW as-of), last match", "n_prior", EW_FLOOR),
    ("fouls_per_game_asof", "fouls_per_game_asof", "fouls per game (EW as-of), last match", "n_prior", EW_FLOOR),
    ("cards_rate_season", "cards_rate_season", "cards per game, prior matches in team's current season", "n_prior_season", SEASON_FLOOR),
)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _load_raw() -> tuple[pd.DataFrame, pd.DataFrame]:
    matches = pd.read_parquet(_SOCCER_DIR / "matches.parquet", columns=["event_id", "date", "season", "home_team", "away_team"])
    match_stats = pd.read_parquet(_SOCCER_DIR / "match_stats.parquet")
    return matches, match_stats


def build_long_frame(matches: pd.DataFrame, match_stats: pd.DataFrame) -> pd.DataFrame:
    """One row per team per match: EW as-of discipline columns (light read
    of build_asof_disc_frame) + raw yellow/red (for the season-to-date
    stat) + season, melted to team-grain."""
    disc = build_asof_disc_frame(match_stats)[
        ["event_id", "home_yellow_asof", "away_yellow_asof", "home_red_asof", "away_red_asof",
         "home_fouls_asof", "away_fouls_asof", "home_n_prior", "away_n_prior"]
    ]
    raw = match_stats[["event_id", "home_yellow", "away_yellow", "home_red", "away_red"]]
    joined = matches.merge(disc, on="event_id", how="inner").merge(raw, on="event_id", how="inner")
    joined = joined.dropna(subset=["date"])

    home = pd.DataFrame({
        "team": joined["home_team"], "date": joined["date"], "season": joined["season"],
        "yellow_per_game_asof": joined["home_yellow_asof"], "red_per_game_asof": joined["home_red_asof"],
        "fouls_per_game_asof": joined["home_fouls_asof"], "n_prior": joined["home_n_prior"],
        "cards_raw": joined["home_yellow"].astype(float) + joined["home_red"].astype(float),
    })
    away = pd.DataFrame({
        "team": joined["away_team"], "date": joined["date"], "season": joined["season"],
        "yellow_per_game_asof": joined["away_yellow_asof"], "red_per_game_asof": joined["away_red_asof"],
        "fouls_per_game_asof": joined["away_fouls_asof"], "n_prior": joined["away_n_prior"],
        "cards_raw": joined["away_yellow"].astype(float) + joined["away_red"].astype(float),
    })
    long = pd.concat([home, away], ignore_index=True)
    long["cards_per_game_asof"] = long["yellow_per_game_asof"] + long["red_per_game_asof"]
    return long.sort_values("date", kind="mergesort").reset_index(drop=True)


def build_snapshot(long_df: pd.DataFrame, season_floor: int = SEASON_FLOOR) -> pd.DataFrame:
    """One row per team: EW as-of values entering the team's chronologi-
    cally LAST match (light read), plus a prior-only season-to-date cards
    rate (that match itself is dropped before the season expanding mean is
    taken, same leak-free discipline as soccer_team_form_asof_claims.py)."""
    rows: list[dict[str, Any]] = []
    for team, grp in long_df.groupby("team", sort=False):
        grp = grp.sort_values("date", kind="mergesort").reset_index(drop=True)
        last = grp.iloc[-1]
        prior = grp.iloc[:-1]

        cur_season = grp["season"].iloc[-1]
        season_prior = prior[prior["season"] == cur_season]
        n_prior_season = len(season_prior)
        cards_rate_season = float(season_prior["cards_raw"].mean()) if n_prior_season else float("nan")

        rows.append({
            "team": str(team),
            "yellow_per_game_asof": float(last["yellow_per_game_asof"]),
            "red_per_game_asof": float(last["red_per_game_asof"]),
            "cards_per_game_asof": float(last["cards_per_game_asof"]),
            "fouls_per_game_asof": float(last["fouls_per_game_asof"]),
            "n_prior": int(last["n_prior"]),
            "n_prior_season": n_prior_season,
            "cards_rate_season": cards_rate_season,
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
        "claim_id": f"soccer_team_discipline_asof_{metric_name}_{WINDOW_TAG}",
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
            "DESCRIPTIVE discipline snapshot, not a forecast, no market claim.",
            f"min_sample floor {floor_col}>={floor_value}; below-floor teams are counted in "
            "n_excluded_below_floor, never silently dropped.",
            "EW as-of metrics (yellow/red/cards/fouls_per_game_asof) are a LIGHT READ of the "
            "existing prior-only EW discipline builder -- no window re-derived here.",
            "cards_rate_season is prior-only within the team's current season (its own most "
            "recent match is dropped before the expanding mean is taken).",
            f"{column} = {description}; snapshot parquet this store owns carries the "
            "precomputed value, formula is an identity read of that column.",
            "FULL POPULATION: every team clearing the floor is ranked, no top-N cap.",
        ],
    }


def build_all_claims(snap: pd.DataFrame) -> list[dict[str, Any]]:
    """One claim per metric -- SKIP (never emit) a metric with zero qualifiers."""
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
    parser = argparse.ArgumentParser(description="Emit soccer team discipline as-of DESCRIPTIVE ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    matches, match_stats = _load_raw()
    long_df = build_long_frame(matches, match_stats)
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
