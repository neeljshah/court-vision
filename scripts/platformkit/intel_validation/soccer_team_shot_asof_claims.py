"""Soccer team shot/SoT/corners as-of claims (covers shots-on-target and
corners resolver fails). LIGHT READ of already-leak-free substrate -- NO
re-derivation of any rolling window here.

Sources (both PREBUILT and already as-of, per spec verification):
  - data/domains/soccer/asof_features.parquet -- home/away SoT + shots
    for/against, prior-only expanding + L10 windows (verified: computed with
    strictly-prior data BEFORE this family ever reads it).
  - domains.soccer.asof_discipline_features.build_asof_disc_frame() over
    data/domains/soccer/match_stats.parquet -- prior-only EW corners_asof
    per team (same "for"-only EW discipline builder Family 3 wraps).
  - data/domains/soccer/matches.parquet -- event_id/date/home_team/away_team
    only, to attach team identity + chronological order to the as-of rows.

Because both substrates are already prior-only as-of PER MATCH, this
producer never computes a rolling window itself: for each team it melts the
home/away rows to team-grain and takes the row from that team's chronologi-
cally LAST match -- i.e. the as-of snapshot entering their most recent
match, which by construction of the source builders excludes that match's
own result (verified in test_soccer_team_shot_asof_claims.py).

HONEST GAP: corners_against_asof is NOT built. The existing EW discipline
builder (asof_discipline_features.py) tracks a single symmetric per-team
running corners stat ("corners this team wins"), not a separate for/against
split -- there is no "corners conceded" substrate to light-read without
building new tracking logic, which is out of scope for a light-read family.
corners_for_asof is shipped; corners_against_asof is honestly omitted (no
fabricated proxy).

DESCRIPTIVE only: no forecast, no market claim.

CLI:
    python -m scripts.platformkit.intel_validation.soccer_team_shot_asof_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/soccer_team_shot_asof_claims.jsonl \
        --output data/cache/intel_claims/soccer_team_shot_asof_claims_validation.json
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
_SNAPSHOT = _OUT_DIR / "soccer_team_shot_asof_snapshot.parquet"
_CLAIMS_OUT = _OUT_DIR / "soccer_team_shot_asof_claims.jsonl"

SHOT_FLOOR = 10
CORNERS_FLOOR = 10
WINDOW_TAG = "asof_last_match"

# (snapshot column, metric name, description, floor column, floor value)
_METRICS = (
    ("sot_for_asof", "sot_for_asof", "shots-on-target for, as-of last match", "n_prior", SHOT_FLOOR),
    ("sot_against_asof", "sot_against_asof", "shots-on-target against, as-of last match", "n_prior", SHOT_FLOOR),
    ("shots_for_asof", "shots_for_asof", "shots for, as-of last match", "n_prior", SHOT_FLOOR),
    ("shots_against_asof", "shots_against_asof", "shots against, as-of last match", "n_prior", SHOT_FLOOR),
    ("sot_ratio_for_asof", "sot_ratio_for_asof", "shot-on-target ratio for, as-of last match", "n_prior", SHOT_FLOOR),
    ("sot_for_l10", "sot_for_l10", "trailing-10 shots-on-target for, as-of last match", "n_prior", SHOT_FLOOR),
    ("corners_for_asof", "corners_for_asof", "corners for (EW as-of), as-of last match", "n_prior_corners", CORNERS_FLOOR),
)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _load_joined() -> pd.DataFrame:
    matches = pd.read_parquet(_SOCCER_DIR / "matches.parquet", columns=["event_id", "date", "home_team", "away_team"])
    asof = pd.read_parquet(_SOCCER_DIR / "asof_features.parquet")
    match_stats = pd.read_parquet(_SOCCER_DIR / "match_stats.parquet")
    disc = build_asof_disc_frame(match_stats)[
        ["event_id", "home_corners_asof", "away_corners_asof", "home_n_prior", "away_n_prior"]
    ].rename(columns={"home_n_prior": "home_n_prior_corners", "away_n_prior": "away_n_prior_corners"})

    joined = matches.merge(asof, on="event_id", how="inner").merge(disc, on="event_id", how="inner")
    return joined.dropna(subset=["date"])


def build_long_frame(joined: pd.DataFrame) -> pd.DataFrame:
    """One row per team per match (home + away perspective), each row already
    carrying the PREBUILT as-of values for that team's perspective in that
    match -- no window computed here, a pure column-melt."""
    home = pd.DataFrame({
        "team": joined["home_team"], "date": joined["date"],
        "sot_for_asof": joined["home_sot_for_asof"], "sot_against_asof": joined["home_sot_against_asof"],
        "shots_for_asof": joined["home_shots_for_asof"], "shots_against_asof": joined["home_shots_against_asof"],
        "sot_ratio_for_asof": joined["home_sot_ratio_for_asof"], "sot_for_l10": joined["home_sot_for_l10"],
        "corners_for_asof": joined["home_corners_asof"],
        "n_prior": joined["home_n_prior"], "n_prior_corners": joined["home_n_prior_corners"],
    })
    away = pd.DataFrame({
        "team": joined["away_team"], "date": joined["date"],
        "sot_for_asof": joined["away_sot_for_asof"], "sot_against_asof": joined["away_sot_against_asof"],
        "shots_for_asof": joined["away_shots_for_asof"], "shots_against_asof": joined["away_shots_against_asof"],
        "sot_ratio_for_asof": joined["away_sot_ratio_for_asof"], "sot_for_l10": joined["away_sot_for_l10"],
        "corners_for_asof": joined["away_corners_asof"],
        "n_prior": joined["away_n_prior"], "n_prior_corners": joined["away_n_prior_corners"],
    })
    long = pd.concat([home, away], ignore_index=True)
    return long.sort_values("date", kind="mergesort").reset_index(drop=True)


def build_snapshot(long_df: pd.DataFrame) -> pd.DataFrame:
    """One row per team: the as-of values entering that team's chronologi-
    cally LAST match on record (light read, no re-derivation)."""
    return (
        long_df.sort_values("date", kind="mergesort")
        .groupby("team", sort=False, as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )


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
        "claim_id": f"soccer_team_shot_asof_{metric_name}_{WINDOW_TAG}",
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
            "DESCRIPTIVE as-of snapshot, not a forecast, no market claim.",
            f"min_sample floor {floor_col}>={floor_value}; below-floor teams are counted in "
            "n_excluded_below_floor, never silently dropped.",
            "LIGHT READ: substrate (asof_features.parquet / asof_discipline_features EW "
            "builder) is already prior-only as-of -- no window is re-derived here. Each "
            "team's value is read from its chronologically LAST match on record.",
            "corners_against_asof is NOT built (honest gap): the EW discipline builder "
            "tracks only a single symmetric per-team corners-won stat, no for/against split.",
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
    parser = argparse.ArgumentParser(description="Emit soccer team shot/SoT/corners as-of DESCRIPTIVE ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    long_df = build_long_frame(_load_joined())
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
