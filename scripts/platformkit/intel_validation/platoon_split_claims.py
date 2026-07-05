"""MLB platoon-split ranking claims producer (LANE platoon-index, program v2
build rank 2). Mirrors catcher_framing_claims.py's structure: emit a ranking
claim in the SAME claims contract shape, backed by
domains/mlb/platoon_split_index.py's snapshot, zero code sharing with the
validator.

METRIC: platoon_delta = (on_base_vs_l / pa_vs_l) - (on_base_vs_r / pa_vs_r),
per batter. Unlike catcher_framing_claims.py (a single-group_by aggregate),
this metric needs TWO per-hand aggregates already joined into one row per
batter -- so this claim uses the validator's PLAIN row-wise formula path
(criteria.aggregate = None), which recomputes the delta directly from the
four raw columns (pa_vs_l, on_base_vs_l, pa_vs_r, on_base_vs_r) already
present in the snapshot parquet, via safe_formula.evaluate_formula's
whitelist grammar (division + subtraction of named columns only).

SOURCE: domains/mlb/platoon_split_index.py is the domain-level index builder
(PA-ending-row definition, on-base-event set, honest data-scale finding --
see that module's docstring). Running this producer re-invokes
build_platoon_snapshot() fresh (not a stale read).

WINDOW: seasons 2022+2023 (data/cache/statcast/statcast_fuller__2022/2023.parquet
-- both an 18-day sample window per season, not full seasons).

MIN-SAMPLE FLOOR (per LANE spec): pa_vs_l >= 100 AND pa_vs_r >= 100.
DATA-SCALE STATUS IS CORPUS-DEPENDENT AND COMPUTED FRESH EVERY RUN --
NEVER HARDCODE IT HERE. `_sample_floor_caveat()` below derives the true
qualifier count (and the honest-empty sentence if it is zero) from the
live `index_report` returned by build_platoon_snapshot() at emit time, and
that derived caveat is what ships in the claim's `caveats` list -- this
docstring intentionally does not restate a snapshot of n_considered /
n_qualifying / ranking length, because those numbers move as the corpus
grows and a stale copy here would silently contradict the shipped claim.
To see the CURRENT numbers, read the live artifact:
data/cache/intel_claims/platoon_split_claims.jsonl (n_considered,
n_excluded_below_floor, caveats[1], ranking) -- or re-run this producer.
See platoon_split_index.py module docstring for the full data-scale
methodology writeup (PA definition, on-base-event set).

LEAK DISCIPLINE: purely descriptive/retrospective (a completed 2-season
statcast aggregate) -- no forecasting claim, no leak-risk window.

NETWORK: zero. Pure pandas over an already-materialized parquet.
DESCRIPTIVE/SCOUTING ONLY -- NO MARKET/$ EDGE CLAIMED.

CLI:
    python -m scripts.platformkit.intel_validation.platoon_split_claims
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

from domains.mlb.platoon_split_index import (
    MIN_PA_PER_HAND,
    SEASONS,
    build_platoon_snapshot,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "platoon_split_claims.jsonl"
_SNAPSHOT_OUT = _OUT_DIR / "platoon_split_snapshot.parquet"
_GAMELOGS = REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"

SEASON_WINDOW = "2022_2023"
TOP_N = 50


def build_snapshot() -> tuple[Path, dict]:
    """Re-run the domain index builder, write the plain-formula-friendly
    WIDE snapshot (batter, pa_vs_l, on_base_vs_l, pa_vs_r, on_base_vs_r) the
    validator recomputes platoon_delta = (on_base_vs_l/pa_vs_l) -
    (on_base_vs_r/pa_vs_r) from, row-wise."""
    wide, report = build_platoon_snapshot()
    write_cols = wide[["batter", "pa_vs_l", "on_base_vs_l", "pa_vs_r", "on_base_vs_r"]].copy()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), _SNAPSHOT_OUT)
    return _SNAPSHOT_OUT, report


def _sample_floor_caveat(index_report: dict) -> str:
    """Build the min-sample-floor caveat FROM the actual qualifier count at
    emit time (never a hardcoded corpus-state assertion). Two branches:
    0 qualifiers -> honest-empty sentence; N>0 -> true count + sample-window
    seasons covered, sourced from the live index_report."""
    n_qual = index_report["n_qualifying_batters"]
    n_considered = index_report["n_batters_considered"]
    seasons_str = "/".join(str(s) for s in index_report["seasons"])
    base = (
        f"min_sample floor: PA >= {MIN_PA_PER_HAND} vs BOTH hands "
        f"({n_qual}/{n_considered} batters qualify) -- per LANE spec."
    )
    if n_qual == 0:
        return (
            f"{base} HONEST DATA-SCALE FINDING: this corpus (seasons={seasons_str}) is a "
            "sample window in which 0 batters currently clear the floor on both hands "
            f"(max PA vs LHP any batter={index_report['max_pa_vs_l_any_batter']}, "
            f"vs RHP={index_report['max_pa_vs_r_any_batter']}); the ranking below is "
            "legitimately empty until a fuller-coverage corpus lands -- no code change "
            "needed to re-run this claim once it does."
        )
    return (
        f"{base} DATA-SCALE STATUS: {n_qual} of {n_considered} batters (seasons="
        f"{seasons_str}) clear the floor on both hands, so the ranking below is a real, "
        "non-empty result over this sample window (not a full-season corpus)."
    )


def build_ranking_claim() -> dict[str, Any]:
    out_path, index_report = build_snapshot()
    raw = pd.read_parquet(out_path)

    if _GAMELOGS.exists():
        names = pd.read_parquet(_GAMELOGS, columns=["player_id", "player"])
        name_lookup = dict(
            names.drop_duplicates(subset=["player_id"], keep="last")
            .set_index("player_id")["player"]
        )
    else:
        name_lookup = {}

    n_considered = len(raw)
    qualifiers = raw[
        (raw["pa_vs_l"] >= MIN_PA_PER_HAND) & (raw["pa_vs_r"] >= MIN_PA_PER_HAND)
    ].copy()
    n_excluded = n_considered - len(qualifiers)

    if len(qualifiers):
        qualifiers["platoon_delta"] = (
            qualifiers["on_base_vs_l"] / qualifiers["pa_vs_l"]
            - qualifiers["on_base_vs_r"] / qualifiers["pa_vs_r"]
        )
        qualifiers = qualifiers.sort_values("platoon_delta", ascending=False).reset_index(drop=True)
    top = qualifiers.head(TOP_N)

    ranking = []
    for i, row in enumerate(top.itertuples(index=False), start=1):
        bid = int(row.batter)
        ranking.append({
            "rank": i,
            "batter": bid,
            "batter_name": str(name_lookup.get(bid, "Unknown")),
            "value": round(float(row.platoon_delta), 4),
            "n": int(min(row.pa_vs_l, row.pa_vs_r)),
        })

    rel_source = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": f"mlb_platoon_split_top50_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": f"Which MLB batters show the largest platoon split "
                    f"(on-base rate vs LHP minus vs RHP, top 50, seasons={SEASON_WINDOW})?",
        "criteria": {
            "metric": "platoon_delta",
            "formula": "(on_base_vs_l / pa_vs_l) - (on_base_vs_r / pa_vs_r)",
            "window": f"seasons_{SEASON_WINDOW}_mlb",
            "window_spec": None,
            "aggregate": None,
            "min_sample": {"pa_vs_l": MIN_PA_PER_HAND, "pa_vs_r": MIN_PA_PER_HAND},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "batter",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            f"platoon_delta = on-base rate vs LHP minus on-base rate vs RHP (p_throws, "
            f"100% coverage), PA defined by events notna (NEVER des -- see "
            f"platoon_split_index.py), seasons={SEASON_WINDOW} "
            "(data/cache/statcast/statcast_fuller__2022/2023.parquet).",
            _sample_floor_caveat(index_report),
            "DESCRIPTIVE platoon-split scouting index only -- no forecasting/market/$ edge claimed.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit MLB platoon-split ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = [build_ranking_claim()]
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
