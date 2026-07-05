"""MLB plate-discipline DESCRIPTIVE ranking claims producer (lane
mlb-plate-discipline). Emits ONE full-population ranking claim --
pitcher zone_rate -- in the SAME claims contract shape as mlb_tto_claims.py /
platoon_split_claims.py, zero code sharing with claims_validator.py.

SCOUT-FINDING CORRECTION (verified live this session, both corpus files):
the brief's requested swing/whiff derivation needs a per-pitch
`description` column with values swinging_strike*/foul*/hit_into_play*
(swing) vs called_strike/ball (no swing). That column DOES NOT EXIST on
this corpus (statcast_fuller__2022/2023.parquet) or any other on-disk
statcast file -- confirmed via `pq.ParquetFile(...).schema.names` on every
statcast_fuller/_sample/_overlap/starter_table parquet under
data/cache/statcast/. What exists instead:
  - `type` (S/B/X): S collapses CALLED strikes and SWINGING strikes into
    one code (verified: type value_counts on 2022 alone = S=331076
    B=255122 X=124311) -- cannot isolate a swing from this column alone.
  - `des`: only populated on PA-TERMINAL pitches (182,124 non-null rows
    2022-only, matching non-null `events`), and is a free-text narrative
    sentence ("Aaron Judge strikes out swinging."), not a per-pitch code.
domains/mlb/catcher_framing_index.py's own CORRECTNESS FIX section
(lines 17-32) independently reached the identical conclusion while
investigating a related metric: "There is no column on this corpus that
isolates a called strike from a swinging strike or a foul within
type=='S' ... would require a re-pull with a pitch-call/description
column ... and is NOT built here." This module does not re-attempt that
derivation; per-pitch swing/whiff/chase for pitcher_whiff_rate,
batter_chase_rate, and batter_whiff_rate are honestly reported
CORPUS_ABSENT below (see BLOCKED_DIMENSIONS), never silently skipped.

DIMENSION SHIPPED -- pitcher zone_rate: in-zone pitches / all pitches,
per pitcher. `zone` (MLB's own 1-9 in-zone / 11-14 out-of-zone
classification, the SAME primary column catcher_framing_index.py uses)
needs no swing information at all, so it is unaffected by the
description-column gap above. in_zone = 1 if zone in {1..9} else 0
(zone nulls -- 5,065/1,431,493 pitches across both seasons, ~0.35% --
dropped before aggregation, never imputed).

FLOOR: pitcher zone_rate >= 500 pitches thrown across the 2022+2023
window (module constant MIN_PITCHES_PITCHER) -- damps per-pitch noise on
a binary in/out-of-zone indicator while clearing a real, non-token
population (665/1,130 pitchers qualify; verified live this session).
WINDOW: seasons 2022+2023 (statcast_fuller__2022/2023.parquet, the same
corpus mlb_tto_claims.py/platoon_split_claims.py use). FULL POPULATION:
every pitcher clearing the floor ships (no top-N truncation); below-floor
counted honestly in n_excluded_below_floor.

CLOSED-CLASS GUARD: descriptive ranking only -- NOT a validated
predictor. MLB pregame market-efficiency + SP-fatigue predictive classes
stay CLOSED; this module makes no gate/predictive/calibration claim.

LEAK: purely descriptive/retrospective -- no forecasting claim. NETWORK:
zero. DESCRIPTIVE SPLIT ONLY -- NO MARKET/$ EDGE, NO PREDICTOR CLAIMED.
CLI: python -m scripts.platformkit.intel_validation.mlb_plate_discipline_claims
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

_STATCAST_PATHS = (
    REPO_ROOT / "data" / "cache" / "statcast" / "statcast_fuller__2022.parquet",
    REPO_ROOT / "data" / "cache" / "statcast" / "statcast_fuller__2023.parquet",
)
_GAMELOGS = REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "mlb_plate_discipline_claims.jsonl"
_ZONE_SNAPSHOT_OUT = _OUT_DIR / "mlb_plate_discipline_zone_rows.parquet"

SEASON_WINDOW = "2022_2023"
MIN_PITCHES_PITCHER = 500  # floor on the metric's own denominator (see docstring)
IN_ZONE_CODES = frozenset({1, 2, 3, 4, 5, 6, 7, 8, 9})

# Dimensions the brief requested but this corpus cannot support -- honestly
# reported (see build_blocked_report()), never silently dropped.
BLOCKED_DIMENSIONS = (
    {
        "dimension": "pitcher_whiff_rate",
        "reason": "CORPUS_ABSENT: no per-pitch `description` column "
                  "(swinging_strike*/foul*/hit_into_play*/called_strike/ball) "
                  "on statcast_fuller__2022/2023.parquet or any other on-disk "
                  "statcast file; `type` (S/B/X) collapses called+swinging "
                  "strikes into one code S, `des` is free-text and PA-terminal "
                  "only -- swings cannot be isolated per-pitch.",
    },
    {
        "dimension": "batter_chase_rate",
        "reason": "CORPUS_ABSENT: same missing swing/no-swing per-pitch "
                  "column as pitcher_whiff_rate -- chase_rate needs "
                  "swing-vs-no-swing on out-of-zone pitches, which this "
                  "corpus's type/des/events columns cannot isolate.",
    },
    {
        "dimension": "batter_whiff_rate",
        "reason": "CORPUS_ABSENT: same missing swing/no-swing per-pitch "
                  "column as pitcher_whiff_rate.",
    },
)

_CLOSED_CLASS_CAVEAT = (
    "DESCRIPTIVE SPLIT, NOT A VALIDATED PREDICTOR -- MLB pregame market-"
    "efficiency and SP-fatigue predictive classes stay CLOSED. No "
    "predictive/gate/calibration claim, ranked descriptive only."
)
_NO_EDGE_CAVEAT = "DESCRIPTIVE ranking only -- no forecasting/market/$ edge claimed."


def build_zone_rows(paths: tuple[Path, ...] = _STATCAST_PATHS) -> tuple[Path, pd.DataFrame]:
    """Load pitcher/zone rows across both seasons, drop zone-null pitches,
    derive in_zone (0/1), write the raw rows the aggregate grammar
    consumes. Returns (parquet_path, name_lookup_df)."""
    cols = ["pitcher", "zone"]
    frames = [pd.read_parquet(p, columns=cols) for p in paths]
    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["zone"])
    df["in_zone"] = df["zone"].astype(int).isin(IN_ZONE_CODES).astype("int64")

    names = pd.read_parquet(_GAMELOGS, columns=["player_id", "player"])
    name_df = names.drop_duplicates(subset=["player_id"], keep="last").rename(
        columns={"player": "player_name"})

    write_cols = df.rename(columns={"pitcher": "player_id"})[["player_id", "in_zone"]].copy()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), _ZONE_SNAPSHOT_OUT)
    return _ZONE_SNAPSHOT_OUT, name_df


def build_zone_rate_claim(name_lookup: dict[int, str]) -> dict[str, Any]:
    raw = pd.read_parquet(_ZONE_SNAPSHOT_OUT)
    stats = raw.groupby("player_id").agg(n=("in_zone", "count"), zone_rate=("in_zone", "mean"))
    stats = stats.reset_index()
    n_considered = len(stats)
    qualifiers = stats[stats["n"] >= MIN_PITCHES_PITCHER].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values("zone_rate", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        pid = int(row.player_id)
        ranking.append({
            "rank": i,
            "player_id": pid,
            "player_name": str(name_lookup.get(pid, "Unknown")),
            "value": round(float(row.zone_rate), 4),
            "n": int(row.n),
        })

    rel_source = str(_ZONE_SNAPSHOT_OUT.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": f"mlb_pitcher_zone_rate_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": "Which MLB pitchers throw the highest share of in-zone "
                    f"pitches (full qualifying population, seasons={SEASON_WINDOW})?",
        "criteria": {
            "metric": "zone_rate",
            "formula": "sum(in_zone) / count(in_zone)",
            "window": f"seasons_{SEASON_WINDOW}_mlb_plate_discipline_zone_rate",
            "window_spec": None,
            "aggregate": {"group_by": "player_id", "derived": {"n": "count(in_zone)"}},
            "min_sample": {"n": MIN_PITCHES_PITCHER},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            _CLOSED_CLASS_CAVEAT,
            "zone_rate = (in-zone pitches) / (all pitches with a resolvable "
            "zone code), per pitcher, over seasons 2022+2023. in_zone=1 when "
            "statcast's own `zone` column is 1-9 (MLB's in-zone grid cells), "
            "0 when 11-14 (out-of-zone); pitches with a null zone code "
            "(~0.35% of the corpus) are dropped before aggregation, never "
            "imputed.",
            f"min_sample floor: pitches with a resolvable zone >= {MIN_PITCHES_PITCHER} "
            f"({len(qualifiers)}/{n_considered} pitchers qualify).",
            f"FULL POPULATION: all {len(qualifiers)} pitchers clearing the floor are "
            "ranked here (no top-N truncation) -- below-floor pitchers honestly "
            "counted in n_excluded_below_floor, never silently dropped.",
            "pitcher_whiff_rate/batter_chase_rate/batter_whiff_rate were also "
            "requested for this lane but are CORPUS_ABSENT (no per-pitch "
            "swing/no-swing description column exists) -- see this module's "
            "BLOCKED_DIMENSIONS and docstring for the exact column evidence.",
            _NO_EDGE_CAVEAT,
        ],
    }


def build_blocked_report() -> dict[str, Any]:
    """Honest, non-claim report of the three requested dimensions this
    corpus cannot support -- surfaced in CLI output and returned alongside
    the shipped claim, never silently omitted."""
    return {
        "status": "CORPUS_ABSENT",
        "blocked_dimensions": list(BLOCKED_DIMENSIONS),
        "evidence": (
            "verified live: statcast_fuller__2022/2023.parquet columns = "
            "[game_pk, game_date, inning, inning_topbot, at_bat_number, "
            "pitch_number, pitcher, batter, events, release_speed, "
            "release_spin_rate, estimated_woba_using_speedangle, pitch_type, "
            "balls, strikes, outs_when_up, home_team, away_team, home_score, "
            "away_score, bat_score, post_home_score, post_away_score, "
            "launch_speed, zone, type, des, fielder_2, stand, p_throws, "
            "if_fielding_alignment, of_fielding_alignment, plate_x, plate_z, "
            "sz_top, sz_bot] -- no `description` column; `type` value_counts "
            "(2022) = S=331076 B=255122 X=124311 (S conflates called+swinging "
            "strikes); `des` non-null count = 182124 (PA-terminal only, "
            "free-text narrative, not a per-pitch code)."
        ),
    }


def build_all_claims() -> list[dict[str, Any]]:
    _, name_df = build_zone_rows()
    name_lookup = dict(zip(name_df["player_id"], name_df["player_name"]))
    return [build_zone_rate_claim(name_lookup)]


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit MLB plate-discipline descriptive ranking claims "
                    "(pitcher zone_rate); report CORPUS_ABSENT dimensions honestly"
    )
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = build_all_claims()
    out_path = write_claims(claims, Path(args.output))
    for c in claims:
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} "
              f"top1={c['ranking'][0] if c['ranking'] else None}")
    print(f"wrote {len(claims)} claims -> {out_path}")

    blocked = build_blocked_report()
    print(f"BLOCKED (corpus-absent) dimensions: "
          f"{[d['dimension'] for d in blocked['blocked_dimensions']]}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
