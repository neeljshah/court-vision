"""Tennis leak-free as-of serve claims producer "tennis_serve_asof"
(2026-07-18 build spec): the only current serve-dominance leaderboard
(tennis_profile_claims__serve_dominance) is career-descriptive from
match_stats and includes each player's own match outcome -- NOT leak-free.
tennis_claims_v4 covers as-of ace_rate/double_fault/first_serve_in BY
SURFACE only, and does not cover first_serve_win, second_serve_win, or
bp_saved as-of. This family closes that gap.

STEP-0 PREMISE (verified via python -c column dumps): asof_features.parquet
(30616x18, ATP-only -- verified zero WTA overlap the same way asof_meta was)
carries p1_1st_win_asof/p1_2nd_win_asof/p1_bp_saved_asof (+p2_*) and a SHARED
p1_n_prior/p2_n_prior (one running-match count feeds all three metrics, same
"several metrics share one floor column" idiom as tennis_claims_v3.py's
return SourceSpec). No surface split, no WTA -- stated as scope, not a gap
this family papers over.

RESHAPE: same wide(p1_/p2_)->long(one row per player per match) join against
the matches spine for date/name, then keep each player's LAST as-of row
within the season window -- IDENTICAL idiom to tennis_hold_claims.py's
_reshape_long/_season_snapshot (reused verbatim in shape, reimplemented here
only because it needs 3 metric columns per row instead of hold_pct_asof's 1).

LEAK DISCIPLINE: every *_asof column is already a leak-free TRAILING feature
(each row is player state BEFORE that match, per domains/tennis/asof_features.py's
own future-leak assertion). Taking a player's LAST snapshot in-window adds no
new leak -- walk-forward-clean by construction, same reasoning tennis_hold_claims
already states.

MIN-SAMPLE FLOOR: n_prior >= 50, same precedent as tennis_hold_claims.py.
NETWORK: zero. ACCURACY ONLY -- NO MARKET EDGE CLAIMED.

CLI:
    python -m scripts.platformkit.intel_validation.tennis_serve_asof_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[3]
_ATP_MATCHES = REPO_ROOT / "data" / "domains" / "tennis" / "matches.parquet"
_ATP_FEATURES = REPO_ROOT / "data" / "domains" / "tennis" / "asof_features.parquet"

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "tennis_serve_asof_claims.jsonl"
_SNAPSHOT_OUT = _OUT_DIR / "tennis_serve_asof_snapshot_atp.parquet"

SEASON_WINDOW = "2025"  # last complete on-disk season, same precedent as tennis_hold_claims
MIN_N_PRIOR = 50

# raw asof_features column suffix -> public metric name (the snapshot parquet
# is written under the PUBLIC name so criteria.formula can be a bare column
# reference -- same "formula IS the column name" convention as hold_pct_asof).
_METRIC_MAP: dict[str, tuple[str, str]] = {
    "first_serve_win_pct_asof": ("1st_win_asof", "first-serve points won"),
    "second_serve_win_pct_asof": ("2nd_win_asof", "second-serve points won"),
    "bp_saved_pct_asof": ("bp_saved_asof", "break points saved"),
}
_RAW_COLS = [raw for raw, _ in _METRIC_MAP.values()]


def _reshape_long(matches: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Join the match spine against asof_features, melt p1_/p2_ into one row
    per player per match: player_id, player_name, date, n_prior, + the 3
    raw metric columns."""
    spine = matches[["event_id", "date", "p1_id", "p2_id", "p1_name", "p2_name"]].copy()
    feat_cols = ["event_id"] + [f"p1_{c}" for c in _RAW_COLS] + [f"p2_{c}" for c in _RAW_COLS] + \
        ["p1_n_prior", "p2_n_prior"]
    joined = spine.merge(features[feat_cols], on="event_id", how="inner")
    keep = ["player_id", "player_name", "date", "n_prior"] + _RAW_COLS
    p1 = joined.rename(columns={"p1_id": "player_id", "p1_name": "player_name", "p1_n_prior": "n_prior",
                                 **{f"p1_{c}": c for c in _RAW_COLS}})[keep]
    p2 = joined.rename(columns={"p2_id": "player_id", "p2_name": "player_name", "p2_n_prior": "n_prior",
                                 **{f"p2_{c}": c for c in _RAW_COLS}})[keep]
    long_df = pd.concat([p1, p2], ignore_index=True)
    long_df["player_id"] = pd.to_numeric(long_df["player_id"], errors="coerce")
    long_df = long_df.dropna(subset=["player_id"])
    long_df["player_id"] = long_df["player_id"].astype("int64")
    long_df["date"] = pd.to_datetime(long_df["date"])
    return long_df


def _season_snapshot(long_df: pd.DataFrame, season: str) -> pd.DataFrame:
    """Restrict to the season window, keep each player's LAST (most
    recent-dated) as-of row within that window -- one row per player."""
    season_year = int(season)
    in_season = long_df[long_df["date"].dt.year == season_year].copy()
    in_season = in_season.sort_values("date", kind="mergesort")
    return in_season.groupby("player_id", as_index=False).tail(1).reset_index(drop=True)


def build_snapshot(matches_path: Path = _ATP_MATCHES, features_path: Path = _ATP_FEATURES,
                    out_path: Path = _SNAPSHOT_OUT) -> tuple[Path, pd.DataFrame]:
    """Build + write the season snapshot parquet (public metric-name columns).
    Returns (parquet_path, snapshot_df)."""
    matches = pd.read_parquet(matches_path)
    features = pd.read_parquet(features_path)
    long_df = _reshape_long(matches, features)
    snapshot = _season_snapshot(long_df, SEASON_WINDOW)
    public_cols = {raw: public for public, (raw, _) in _METRIC_MAP.items()}
    snapshot = snapshot.rename(columns=public_cols)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_cols = snapshot[["player_id", "player_name", "n_prior", *_METRIC_MAP.keys()]].copy()
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), out_path)
    return out_path, snapshot


def build_metric_claim(metric_name: str, out_path: Path, snapshot: pd.DataFrame) -> dict[str, Any]:
    n_considered = len(snapshot)
    qualifiers = snapshot.dropna(subset=[metric_name])
    qualifiers = qualifiers[qualifiers["n_prior"] >= MIN_N_PRIOR]
    n_excluded = n_considered - len(qualifiers)
    # tie-break: value DESC, THEN player_id ASC -- matches claims_validator.py's
    # generic recompute tie-break, see tennis_ranking_claims.py docstring.
    ranked = qualifiers.sort_values([metric_name, "player_id"], ascending=[False, True]).reset_index(drop=True)
    rel_source = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
    ranking = [
        {"rank": i + 1, "player_id": int(row.player_id), "player_name": str(row.player_name),
         "value": round(float(getattr(row, metric_name)), 4), "n": int(row.n_prior)}
        for i, row in enumerate(ranked.itertuples(index=False))
    ]
    label = _METRIC_MAP[metric_name][1]
    return {
        "claim_id": f"tennis_serve_asof_{metric_name}_atp_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": f"Who leads the ATP tour in leak-free as-of {label} (full population, season={SEASON_WINDOW})?",
        "criteria": {
            "metric": metric_name, "formula": metric_name, "window": f"season_{SEASON_WINDOW}_atp",
            "min_sample": {"n_prior": MIN_N_PRIOR}, "direction": "desc", "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            f"{metric_name} is a leak-free TRAILING as-of prior (domains/tennis/asof_features.py); "
            f"each player's row is their LAST as-of snapshot within season={SEASON_WINDOW} (their most "
            "recent trailing rate, not a season-average recompute).",
            f"min_sample floor n_prior>={MIN_N_PRIOR} (running matches-in-history feeding the trailing "
            "average) -- same floor precedent as tennis_hold_claims.py.",
            "ATP only, overall (no surface split, no WTA) -- asof_features.parquet carries neither on disk.",
            "FULL POPULATION: every qualifying player above the floor is ranked (no top-N slice); "
            "below-floor players are counted in n_excluded_below_floor, never dropped.",
            "DESCRIPTIVE/accuracy ranking only -- no market/$ edge claimed.",
        ],
    }


def build_all_claims() -> list[dict[str, Any]]:
    out_path, snapshot = build_snapshot()
    return [build_metric_claim(metric_name, out_path, snapshot) for metric_name in _METRIC_MAP]


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit tennis leak-free as-of serve claims (ATP)")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = build_all_claims()
    out_path = write_claims(claims, Path(args.output))
    for c in claims:
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} "
              f"top1={c['ranking'][0] if c['ranking'] else None}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
