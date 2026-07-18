"""NBA rest-context (schedule/fatigue-conditioned player splits) DESCRIPTIVE
claim family.

Per-player rest state is computed LEAK-FREE from that player's OWN prior
game date within the same season: b2b = exactly 1 day gap (played on
consecutive calendar dates), rest2plus = >=2 days gap. A player's first game
of a season has no prior date -- unknown rest -- and is excluded from both
buckets (never silently counted).

PREREG floors (declared before any player was scored): >=10 b2b games AND
>=20 rest2plus games AND >=100 total FGA (b2b+rest2plus combined) -- the
same population backs all three claims below. Below-floor players are
counted in n_excluded_below_floor, never silently dropped.

Three claims per season (2024-25 and 2025-26):
  1. b2b_ts_drop     = TS%(b2b) - TS%(rest2plus)          [asc: biggest drop first]
  2. b2b_min_delta   = min_pg(b2b) - min_pg(rest2plus)    [desc: biggest bump first]
  3. b2b_pts36_delta = pts_per36(b2b) - pts_per36(rest2plus) [desc: most resilient first]

Identity-formula snapshot pattern (mirrors nba_rest_adjusted_form_claims.py):
the diff itself is the claimed quantity, precomputed into a snapshot parquet
this store owns, so claims_validator.py recomputes via a plain column-name
formula ("b2b_ts_drop" etc.) with zero custom machinery.

CAVEAT (all three claims): schedule assignment is NOT random -- opponent
strength and venue correlate with schedule density (e.g. road trips cluster
b2b games), so these are DESCRIPTIVE splits, never a causal fatigue effect.

CLI:
    python -m scripts.platformkit.intel_validation.nba_rest_context_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/nba_rest_context_claims.jsonl \
        --output data/cache/intel_claims/nba_rest_context_claims_validation.json
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
_NBA_DIR = REPO_ROOT / "data" / "domains" / "basketball_nba"
_BOX_PATH = _NBA_DIR / "player_boxscores.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "nba_rest_context_claims.jsonl"

_BOX_COLS = ["game_id", "date", "season", "player_id", "player_name", "min", "pts", "fga", "fta"]

FLOOR_B2B = 10
FLOOR_REST = 20
FLOOR_FGA = 100
SEASONS = ("2024-25", "2025-26")

SCHEDULE_CAVEAT = (
    "schedule assignment is NOT random: opponent strength and venue correlate "
    "with schedule density (e.g. road trips cluster back-to-backs), so this is "
    "a DESCRIPTIVE split, not a causal fatigue effect."
)
FLOOR_CAVEAT = (
    f"min_sample floor n_b2b>={FLOOR_B2B} AND n_rest2plus>={FLOOR_REST} AND "
    f"fga_total>={FLOOR_FGA} (b2b+rest2plus combined); players below any floor "
    "are counted in n_excluded_below_floor, never silently dropped."
)
REST_DEF_CAVEAT = (
    "rest state computed from each player's OWN prior game date within the "
    "same season: b2b = exactly 1 day gap, rest2plus = >=2 days gap; a "
    "player's season-opener row has no prior date and is excluded from both "
    "buckets (unknown rest, never counted either way)."
)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _snapshot_path(season: str) -> Path:
    return _OUT_DIR / f"nba_rest_context_snapshot_{season.replace('-', '_')}.parquet"


def load_boxscores(path: Path = _BOX_PATH) -> pd.DataFrame:
    df = pd.read_parquet(path, columns=_BOX_COLS)
    missing = [c for c in _BOX_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"player_boxscores.parquet missing columns: {missing}")
    return df


def _rest_bucket_rows(box: pd.DataFrame, season: str) -> pd.DataFrame:
    """One row per (player, game) within `season`, with a b2b/rest2plus
    bucket derived from the gap to that player's own PRIOR game date
    (season-scoped -- never crosses a season boundary). Opener rows (no
    prior date) and any non-1/non-2+ gap (e.g. same-day duplicate row) are
    dropped from bucketing, never silently counted into either bucket."""
    rows = box[box["season"] == season].copy()
    rows = rows.sort_values(["player_id", "date", "game_id"])
    rows["prev_date"] = rows.groupby("player_id")["date"].shift(1)
    rows = rows.dropna(subset=["prev_date"])
    gap_days = (rows["date"] - rows["prev_date"]).dt.days
    rows["bucket"] = np.where(gap_days == 1, "b2b", np.where(gap_days >= 2, "rest2plus", "other"))
    return rows[rows["bucket"] != "other"]


def _agg_bucket(rows: pd.DataFrame, bucket: str) -> pd.DataFrame:
    sub = rows[rows["bucket"] == bucket]
    g = sub.groupby(["player_id", "player_name"], as_index=False).agg(
        n=("game_id", "nunique"), pts=("pts", "sum"), fga=("fga", "sum"),
        fta=("fta", "sum"), minutes=("min", "sum"),
    )
    suffix = bucket
    return g.rename(columns={
        "n": f"n_{suffix}", "pts": f"pts_{suffix}", "fga": f"fga_{suffix}",
        "fta": f"fta_{suffix}", "minutes": f"min_{suffix}",
    })


def build_snapshot(box: pd.DataFrame, season: str) -> pd.DataFrame:
    """One row per player: b2b/rest2plus counts+sums, TS%/min-per-game/
    pts-per-36 for each bucket, and the three claimed deltas. Zero-denominator
    entities (e.g. n_b2b=0) get NaN rate columns -- dropped by the floor
    filter downstream, never imputed."""
    rows = _rest_bucket_rows(box, season)
    b2b = _agg_bucket(rows, "b2b")
    rest = _agg_bucket(rows, "rest2plus")
    snap = b2b.merge(rest, on=["player_id", "player_name"], how="outer")
    count_cols = ["n_b2b", "pts_b2b", "fga_b2b", "fta_b2b", "min_b2b",
                  "n_rest2plus", "pts_rest2plus", "fga_rest2plus", "fta_rest2plus", "min_rest2plus"]
    snap[count_cols] = snap[count_cols].fillna(0.0)

    def _ts(pts: pd.Series, fga: pd.Series, fta: pd.Series) -> pd.Series:
        denom = 2 * (fga + 0.44 * fta)
        return pts / denom.replace(0, np.nan)

    snap["ts_b2b"] = _ts(snap["pts_b2b"], snap["fga_b2b"], snap["fta_b2b"])
    snap["ts_rest2plus"] = _ts(snap["pts_rest2plus"], snap["fga_rest2plus"], snap["fta_rest2plus"])
    snap["min_pg_b2b"] = snap["min_b2b"] / snap["n_b2b"].replace(0, np.nan)
    snap["min_pg_rest2plus"] = snap["min_rest2plus"] / snap["n_rest2plus"].replace(0, np.nan)
    snap["pts36_b2b"] = snap["pts_b2b"] / snap["min_b2b"].replace(0, np.nan) * 36
    snap["pts36_rest2plus"] = snap["pts_rest2plus"] / snap["min_rest2plus"].replace(0, np.nan) * 36
    snap["fga_total"] = snap["fga_b2b"] + snap["fga_rest2plus"]

    snap["b2b_ts_drop"] = (snap["ts_b2b"] - snap["ts_rest2plus"]).round(4)
    snap["b2b_min_delta"] = (snap["min_pg_b2b"] - snap["min_pg_rest2plus"]).round(4)
    snap["b2b_pts36_delta"] = (snap["pts36_b2b"] - snap["pts36_rest2plus"]).round(4)
    return snap.reset_index(drop=True)


def write_snapshot(snap: pd.DataFrame, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snap.to_parquet(out_path, index=False)
    return out_path


_METRIC_SPECS = [
    # (metric_col, direction, label, question)
    ("b2b_ts_drop", "asc", "b2b TS%% drop",
     "Which qualifying players have the biggest true-shooting drop on "
     "back-to-backs vs 2+ days rest?"),
    ("b2b_min_delta", "desc", "b2b minutes delta",
     "Which qualifying players see the biggest minutes-per-game change on "
     "back-to-backs vs 2+ days rest?"),
    ("b2b_pts36_delta", "desc", "b2b-resilient scoring (pts/36 delta)",
     "Which qualifying players are the most back-to-back-resilient scorers "
     "(smallest/most-positive pts-per-36 change vs 2+ days rest)?"),
]


def build_claims_for_season(snap: pd.DataFrame, season: str, snapshot_path: Path) -> list[dict[str, Any]]:
    n_considered = len(snap)
    floored = snap[
        (snap["n_b2b"] >= FLOOR_B2B) & (snap["n_rest2plus"] >= FLOOR_REST) & (snap["fga_total"] >= FLOOR_FGA)
    ].copy()
    n_excluded = n_considered - len(floored)
    rel_source = _rel(snapshot_path)

    claims = []
    for metric_col, direction, label, question in _METRIC_SPECS:
        pool = floored.dropna(subset=[metric_col]).copy()
        pool = pool.sort_values(metric_col, ascending=(direction == "asc")).reset_index(drop=True)
        ranking = [
            {
                "rank": i, "player_id": int(row.player_id), "player_name": str(row.player_name),
                "value": round(float(getattr(row, metric_col)), 4),
                "n": int(row.n_b2b), "n_b2b": int(row.n_b2b), "n_rest2plus": int(row.n_rest2plus),
                "fga_total": int(row.fga_total),
            }
            for i, row in enumerate(pool.itertuples(index=False), start=1)
        ]
        claims.append({
            "claim_id": f"nba_rest_context_{metric_col}_{season}",
            "kind": "ranking",
            "question": f"{question} ({season})",
            "criteria": {
                "metric": metric_col, "formula": metric_col, "window": f"season_{season}_nba",
                "window_spec": None, "aggregate": None,
                "min_sample": {"n_b2b": FLOOR_B2B, "n_rest2plus": FLOOR_REST, "fga_total": FLOOR_FGA},
                "direction": direction, "value_precision": 4, "entity_key": "player_id",
            },
            "ranking": ranking,
            "source_files": [rel_source],
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "n_considered": n_considered,
            "n_excluded_below_floor": n_excluded,
            "edge_claimed": False,
            "caveats": [
                "DESCRIPTIVE_ONLY -- schedule/fatigue-conditioned split, no forecasting/market claim.",
                SCHEDULE_CAVEAT,
                FLOOR_CAVEAT,
                REST_DEF_CAVEAT,
                f"{label} = precomputed snapshot column, formula is an identity read of that column.",
            ],
        })
    return claims


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    """Empty-ranking claims are never written (mirrors nba_teammate_context_
    claims.py's skip idiom): a zero-qualifier season must not emit a
    vacuous ranking claim -- it is SKIP-printed and dropped."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kept = [c for c in claims if c["ranking"]]
    for claim in claims:
        if not claim["ranking"]:
            print(f"SKIP {claim['claim_id']}: 0 of {claim['n_considered']} "
                  "players clear the floors -- claim not emitted")
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in kept:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA rest-context DESCRIPTIVE ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    parser.add_argument("--season", type=str, default=None, help="single season override; default emits both SEASONS")
    args = parser.parse_args(argv)

    try:
        box = load_boxscores()
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"NO_DATA: {_BOX_PATH} unavailable ({exc}); nba_rest_context skipped, no artifact written.")
        return 0

    seasons = [args.season] if args.season else list(SEASONS)
    all_claims: list[dict[str, Any]] = []
    for season in seasons:
        snap = build_snapshot(box, season)
        snap_path = _snapshot_path(season)
        write_snapshot(snap, snap_path)
        claims = build_claims_for_season(snap, season, snap_path)
        all_claims.extend(claims)
        for claim in claims:
            top = claim["ranking"][0] if claim["ranking"] else None
            print(f"{claim['claim_id']}: n_considered={claim['n_considered']} "
                  f"n_excluded_below_floor={claim['n_excluded_below_floor']} "
                  f"top={top['player_name'] if top else None} value={top['value'] if top else None}")

    out_path = write_claims(all_claims, Path(args.output))
    print(f"wrote {len(all_claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
