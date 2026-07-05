"""MLB times-through-order (TTO) DESCRIPTIVE ranking claims producer (lane
mlb-tto). Derives times_faced per (game_pk, pitcher, batter), buckets TTO
1/2/3+, emits per-bucket wOBA-against rankings PLUS a TTO3-minus-TTO1 delta
ranking -- SAME claims contract shape as mlb_pitcher_claims.py /
catcher_framing_claims.py, zero code sharing with claims_validator.py.

CLOSED-CLASS GUARD: mlb_sp_within_start_fatigue is a CLOSED predictive class
(2 designs, terminal -- scripts/platformkit/ingame/sp_fatigue_gate_mlb.py). NO
predictive/gate/calibration claim here -- DESCRIPTIVE SPLIT ONLY (see
_CLOSED_CLASS_CAVEAT, restated in every claim's caveats).

DERIVATION (mechanical, in the side parquet): dedup pitch rows to one per
(game_pk, at_bat_number) -- max(pitch_number), carrying the PA's terminal
`events`/`estimated_woba_using_speedangle` (182,506/182,506 PAs recover this
way; 84 genuinely truncated PAs drop out naturally); times_faced =
1-indexed cumcount of (game_pk, pitcher, batter) ordered by at_bat_number
within game; tto_bucket: 1/2/3+.

METRIC: pa_value = estimated_woba_using_speedangle where present (statcast's
xwOBA composite; NO raw woba_value/woba_denom columns exist -- confirmed
absent), ELSE an events-based on-base indicator for the ~1% of PAs xwoba
omits (intent_walk/sac_bunt/catcher_interf/truncated_pa). One numeric column
the aggregate grammar mean()-reduces per bucket, no special casing. Delta
claim reuses the same per-bucket values via the plain row-wise formula path
(mirrors platoon_split_claims.py's delta pattern).

FLOOR: >=60 PA in EACH of TTO1 and TTO3+ (module constant; damps per-PA
noise on a binary/xwOBA-scale metric while clearing a real, non-starter-
only population -- a PA-count floor on the metric's own denominator).
WINDOW: seasons 2022+2023 (statcast_fuller__2022/2023.parquet). FULL
POPULATION: every pitcher clearing the floor ships (no top-N truncation);
below-floor honestly counted in n_excluded_below_floor.

LEAK: purely descriptive/retrospective -- no forecasting claim. NETWORK:
zero. DESCRIPTIVE SPLIT ONLY -- NO MARKET/$ EDGE, NO PREDICTOR CLAIMED.
CLI: python -m scripts.platformkit.intel_validation.mlb_tto_claims
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
_CLAIMS_OUT = _OUT_DIR / "mlb_tto_claims.jsonl"
_BUCKET_SNAPSHOT_OUT = _OUT_DIR / "mlb_tto_bucket_pa_rows.parquet"
_DELTA_SNAPSHOT_OUT = _OUT_DIR / "mlb_tto_delta_snapshot.parquet"

SEASON_WINDOW = "2022_2023"
TTO_BUCKETS = ("1", "2", "3+")
MIN_PA_PER_BUCKET = 60  # floor on the metric's own denominator, per bucket (see docstring)

_ON_BASE_EVENTS = frozenset({"single", "double", "triple", "home_run", "walk", "hit_by_pitch", "intent_walk"})
_OBP_DENOM_EVENTS = _ON_BASE_EVENTS | frozenset({  # + plain-out events (no sac/interf/truncated)
    "field_out", "strikeout", "force_out", "grounded_into_double_play", "field_error",
    "double_play", "fielders_choice", "fielders_choice_out", "strikeout_double_play",
    "triple_play",
})

_CLOSED_CLASS_CAVEAT = (
    "DESCRIPTIVE SPLIT, NOT A VALIDATED PREDICTOR -- fatigue gate CLOSED "
    "(mlb_sp_within_start_fatigue is a closed predictive class, 2 designs, "
    "terminal). No predictive/gate/calibration claim, ranked descriptive only."
)
_NO_EDGE_CAVEAT = "DESCRIPTIVE ranking only -- no forecasting/market/$ edge claimed."
_BUCKET_LABELS = {"1": "TTO1 (first time through)", "2": "TTO2 (second time through)",
                  "3+": "TTO3+ (third-or-later time through)"}


def _tto_bucket(times_faced: int) -> str:
    if times_faced == 1:
        return "1"
    if times_faced == 2:
        return "2"
    return "3+"


def build_tto_pa_rows(paths: tuple[Path, ...] = _STATCAST_PATHS) -> tuple[Path, pd.DataFrame]:
    """Dedup pitch-level statcast rows to one row per PA, derive
    times_faced/tto_bucket/pa_value, write the raw rows the aggregate
    grammar consumes. Returns (parquet_path, name_lookup_df)."""
    cols = ["game_pk", "at_bat_number", "pitcher", "batter", "events",
            "estimated_woba_using_speedangle", "pitch_number"]
    frames = [pd.read_parquet(p, columns=cols) for p in paths]
    df = pd.concat(frames, ignore_index=True)

    pa_rows = df.sort_values(["game_pk", "at_bat_number", "pitch_number"]).groupby(
        ["game_pk", "at_bat_number"], as_index=False
    ).tail(1)
    pa_rows = pa_rows.sort_values(["game_pk", "pitcher", "batter", "at_bat_number"])
    pa_rows["times_faced"] = pa_rows.groupby(["game_pk", "pitcher", "batter"]).cumcount() + 1
    pa_rows["tto_bucket"] = pa_rows["times_faced"].map(_tto_bucket)

    obp_num = pa_rows["events"].isin(_ON_BASE_EVENTS).astype("float64")
    has_obp_denom = pa_rows["events"].isin(_OBP_DENOM_EVENTS)
    pa_value = pa_rows["estimated_woba_using_speedangle"].astype("float64")
    fallback_mask = pa_value.isna() & has_obp_denom
    pa_value = pa_value.where(~fallback_mask, obp_num)
    pa_rows["pa_value"] = pa_value
    pa_rows = pa_rows.dropna(subset=["pa_value"])

    names = pd.read_parquet(_GAMELOGS, columns=["player_id", "player"])
    name_df = names.drop_duplicates(subset=["player_id"], keep="last").rename(
        columns={"player": "player_name"})

    # rename pitcher->player_id: matches criteria.entity_key/aggregate.group_by everywhere below.
    write_cols = pa_rows.rename(columns={"pitcher": "player_id"})[["player_id", "tto_bucket", "pa_value"]].copy()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), _BUCKET_SNAPSHOT_OUT)
    return _BUCKET_SNAPSHOT_OUT, name_df


def _bucket_group_stats(raw: pd.DataFrame, bucket: str) -> pd.DataFrame:
    """Per-pitcher (n, mean pa_value) for ONE tto_bucket -- the same grouping
    the validator's aggregate grammar independently re-derives."""
    sub = raw[raw["tto_bucket"] == bucket]
    g = sub.groupby("player_id").agg(n=("pa_value", "count"), mean_val=("pa_value", "mean"))
    return g.reset_index()


def build_bucket_claim(bucket: str, name_lookup: dict[int, str]) -> dict[str, Any]:
    raw = pd.read_parquet(_BUCKET_SNAPSHOT_OUT)
    stats = _bucket_group_stats(raw, bucket)
    n_considered = len(stats)
    qualifiers = stats[stats["n"] >= MIN_PA_PER_BUCKET].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values("mean_val", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        pid = int(row.player_id)
        ranking.append({
            "rank": i,
            "player_id": pid,
            "player_name": str(name_lookup.get(pid, "Unknown")),
            "value": round(float(row.mean_val), 4),
            "n": int(row.n),
        })

    bucket_label, bucket_slug = _BUCKET_LABELS[bucket], bucket.replace("+", "plus")
    rel_source = str(_BUCKET_SNAPSHOT_OUT.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": f"mlb_tto_woba_against_bucket{bucket_slug}_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": f"Which MLB pitchers allow the highest wOBA-against in {bucket_label} "
                    f"(full qualifying population, seasons={SEASON_WINDOW})?",
        "criteria": {
            "metric": "woba_against",
            "formula": "mean(pa_value)",
            "window": f"seasons_{SEASON_WINDOW}_mlb_tto_bucket_{bucket_slug}",
            # kind="season" is a generic col==value slice (apply_window_spec) -- reused to filter 1 bucket.
            "window_spec": {"kind": "season", "season_col": "tto_bucket", "season": bucket},
            "aggregate": {"group_by": "player_id", "derived": {"n": "count(pa_value)"}},
            "min_sample": {"n": MIN_PA_PER_BUCKET},
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
            f"woba_against = mean(pa_value) over plate appearances in {bucket_label}, "
            "where pa_value = estimated_woba_using_speedangle (statcast's xwOBA composite) "
            "when present, else an events-based on-base indicator for the small subset "
            "(~1%) xwoba omits (intent_walk/sac_bunt/catcher_interf/truncated_pa).",
            "times_faced derived by cumcounting (game_pk, pitcher, batter) plate "
            "appearances ordered by at_bat_number within the game; tto_bucket: "
            "1=first meeting, 2=second, 3+=third-or-later.",
            f"min_sample floor: PA in this bucket >= {MIN_PA_PER_BUCKET} "
            f"({len(qualifiers)}/{n_considered} pitchers qualify).",
            f"FULL POPULATION: all {len(qualifiers)} pitchers clearing the floor are "
            "ranked here (no top-N truncation) -- below-floor pitchers honestly counted "
            "in n_excluded_below_floor, never silently dropped.",
            _NO_EDGE_CAVEAT,
        ],
    }


def build_delta_claim(name_lookup: dict[int, str]) -> dict[str, Any]:
    """TTO3+ minus TTO1 wOBA-against delta, per pitcher. Plain row-wise
    formula path (mirrors platoon_split_claims.py's delta pattern): one row
    per pitcher with both bucket means + both bucket ns already joined."""
    raw = pd.read_parquet(_BUCKET_SNAPSHOT_OUT)
    t1 = _bucket_group_stats(raw, "1").rename(columns={"n": "n_tto1", "mean_val": "tto1_value"})
    t3 = _bucket_group_stats(raw, "3+").rename(columns={"n": "n_tto3plus", "mean_val": "tto3plus_value"})
    joined = t1.merge(t3, on="player_id", how="inner")
    n_considered = len(joined)

    # ship the FULL unfiltered joined table (platoon_split_index.py precedent) -- min_sample excludes downstream.
    write_cols = joined[["player_id", "n_tto1", "tto1_value", "n_tto3plus", "tto3plus_value"]].copy()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), _DELTA_SNAPSHOT_OUT)

    floor_mask = (joined["n_tto1"] >= MIN_PA_PER_BUCKET) & (joined["n_tto3plus"] >= MIN_PA_PER_BUCKET)
    qualifiers = joined[floor_mask].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers["delta"] = qualifiers["tto3plus_value"] - qualifiers["tto1_value"]
    qualifiers = qualifiers.sort_values("delta", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        pid = int(row.player_id)
        ranking.append({
            "rank": i,
            "player_id": pid,
            "player_name": str(name_lookup.get(pid, "Unknown")),
            "value": round(float(row.delta), 4),
            "n": int(min(row.n_tto1, row.n_tto3plus)),
        })

    rel_source = str(_DELTA_SNAPSHOT_OUT.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": f"mlb_tto_woba_delta_3plus_minus_1_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": "Which MLB pitchers see the largest wOBA-against INCREASE from "
                    f"TTO1 to TTO3+ (full qualifying population, seasons={SEASON_WINDOW})?",
        "criteria": {
            "metric": "tto_delta",
            "formula": "tto3plus_value - tto1_value",
            "window": f"seasons_{SEASON_WINDOW}_mlb_tto_delta",
            "window_spec": None,
            "aggregate": None,
            "min_sample": {"n_tto1": MIN_PA_PER_BUCKET, "n_tto3plus": MIN_PA_PER_BUCKET},
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
            "tto_delta = (mean wOBA-against in TTO3+) - (mean wOBA-against in TTO1), "
            "per pitcher, over seasons 2022+2023 -- a positive value means the pitcher "
            "was worse (higher wOBA allowed) the third-or-later time through the order "
            "than the first, in this 2-season sample; NOT a forecast of future starts.",
            f"min_sample floor: PA >= {MIN_PA_PER_BUCKET} in EACH of TTO1 and TTO3+ "
            f"({len(qualifiers)}/{n_considered} pitchers qualify in both buckets).",
            f"FULL POPULATION: all {len(qualifiers)} pitchers clearing the floor in BOTH "
            "buckets are ranked here (no top-N truncation) -- below-floor pitchers "
            "honestly counted in n_excluded_below_floor, never silently dropped.",
            _NO_EDGE_CAVEAT,
        ],
    }


def build_all_claims() -> list[dict[str, Any]]:
    _, name_df = build_tto_pa_rows()
    name_lookup = dict(zip(name_df["player_id"], name_df["player_name"]))
    claims = [build_bucket_claim(b, name_lookup) for b in TTO_BUCKETS]
    claims.append(build_delta_claim(name_lookup))
    return claims


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit MLB times-through-order descriptive ranking claims")
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
