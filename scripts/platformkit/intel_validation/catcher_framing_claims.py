"""MLB catcher out-of-zone strike-rate ranking claims producer (program v2
build rank 1, catcher-arm). Mirrors
scripts/platformkit/intel_validation/mlb_pitcher_claims.py's structure: emit
a FULL-POPULATION ranking claim (every catcher clearing the min_sample floor,
no top-N truncation -- see mlb-fullpop lane) in the SAME claims contract
shape, backed by the domains/mlb/catcher_framing_index.py index parquet,
zero code sharing between producer and validator.

METRIC (RELABELED after FIX ROUND): ooz_strike_rate = ooz_strikes /
n_ooz_called -- out-of-zone STRIKE rate, called-OR-swung-OR-fouled. Statcast
`type` has exactly three values (S/B/X) with NO code isolating a called
strike from a swinging strike or foul; there is no `description` column on
this corpus to split them either (see catcher_framing_index.py CORRECTNESS
FIX docstring for the full writeup, incl. the ~92%-swings/~8%-called split
found on the des-covered subset). THIS IS THEREFORE NOT A CALLED-STRIKE OR
FRAMING METRIC -- it is confounded by batter chase/whiff behavior and is
reported as a plain out-of-zone strike-rate descriptive, not a framing proxy.
It is a plain per-catcher aggregate the validator's criteria.aggregate
grammar (sum()/sum() division) can recompute directly from the index
parquet's raw per-catcher counts -- no ranking/sorting happens before the
validator re-derives it.

SOURCE: domains/mlb/catcher_framing_index.py is the domain-level index
builder (derives strike/out-of-zone from type+zone, NEVER des -- see that
module's docstring for the full correctness-trap writeup); this module only
reshapes its output into the claims contract's ranking shape. Running this
producer re-invokes build_catcher_index() fresh (not a stale read of a
previously-written parquet) so the claim always reflects the current corpus.

WINDOW: seasons 2022+2023 (data/cache/statcast/statcast_fuller__2022/2023.parquet
-- the only on-disk fuller-statcast seasons with zone/type/fielder_2 coverage).

MIN-SAMPLE FLOOR: n_ooz_called (out-of-zone called-or-swung pitches summed
per catcher) >= 500 -- the metric's own denominator; see
catcher_framing_index.py for the corpus-level floor derivation (54/107
catchers qualify at this floor -- the caveat string below is generated from
the ACTUAL floor-applied qualifier count, not a zero-floor read; see FIX
ROUND note in build_ranking_claim).

LEAK DISCIPLINE: purely descriptive/retrospective (a completed 2-season
statcast aggregate) -- no forecasting claim, no leak-risk window.

NETWORK: zero. Pure pandas over an already-materialized parquet.
DESCRIPTIVE/SCOUTING ONLY -- NO MARKET/$ EDGE CLAIMED.

CLI:
    python -m scripts.platformkit.intel_validation.catcher_framing_claims
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

from domains.mlb.catcher_framing_index import (
    MIN_OOZ_CALLED,
    SEASONS,
    build_catcher_index,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "catcher_framing_claims.jsonl"
_SNAPSHOT_OUT = _OUT_DIR / "catcher_framing_snapshot.parquet"

SEASON_WINDOW = "2022_2023"
# FULL-POPULATION FIX: every catcher above the min_sample floor ships (no
# top-N truncation) -- below-floor catchers are honestly counted in
# n_excluded_below_floor, never silently dropped. See mlb-fullpop lane.


def build_snapshot() -> tuple[Path, dict]:
    """Re-run the domain index builder, write the aggregate-grammar-friendly
    snapshot parquet (catcher_id, n_ooz_called, ooz_strikes) the validator
    recomputes ooz_strike_rate = sum()/sum() from.

    NOTE (FIX ROUND): this is called with min_ooz_called=0 so the SNAPSHOT
    carries ALL 107 catchers (the claim's min_sample criteria, not this
    producer, applies the real 500 floor when the validator recomputes) --
    matching mlb_pitcher_claims.py's precedent. The zero-floor `report`
    returned here therefore has n_qualifying_catchers=107 (a ZERO-floor
    count) and MUST NOT be used for any "N/M catchers qualify at the 500
    floor" caveat text -- build_ranking_claim below computes that count
    itself from the FLOOR-APPLIED `qualifiers` frame, not from this report."""
    qualifiers, report = build_catcher_index(min_ooz_called=0)  # keep ALL catchers here;
    # the claim's min_sample criteria (not this producer) applies the floor,
    # matching mlb_pitcher_claims.py's precedent of shipping the full raw
    # per-entity table and letting the validator's floor do the excluding.
    write_cols = qualifiers[["catcher_id", "n_ooz_called", "ooz_strikes"]].copy()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), _SNAPSHOT_OUT)
    return _SNAPSHOT_OUT, report


def build_ranking_claim() -> dict[str, Any]:
    out_path, index_report = build_snapshot()
    raw = pd.read_parquet(out_path)

    names = pd.read_parquet(
        REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet",
        columns=["player_id", "player"],
    )
    name_lookup = dict(
        names.drop_duplicates(subset=["player_id"], keep="last")
        .set_index("player_id")["player"]
    )

    n_considered = len(raw)
    qualifiers = raw[raw["n_ooz_called"] >= MIN_OOZ_CALLED].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers["ooz_strike_rate"] = (
        qualifiers["ooz_strikes"] / qualifiers["n_ooz_called"]
    )
    qualifiers = qualifiers.sort_values("ooz_strike_rate", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        cid = int(row.catcher_id)
        ranking.append({
            "rank": i,
            "catcher_id": cid,
            "catcher_name": str(name_lookup.get(cid, "Unknown")),
            "value": round(float(row.ooz_strike_rate), 4),
            "n": int(row.n_ooz_called),
        })

    # FIX ROUND: n_qualifying_catchers/n_catchers_considered for the caveat text
    # MUST come from THIS function's floor-applied `qualifiers`/`n_considered`
    # (the real MIN_OOZ_CALLED=500 floor), NOT from index_report -- that report
    # was built with min_ooz_called=0 (see build_snapshot docstring) and its
    # n_qualifying_catchers is a ZERO-floor count (107/107), not the 500-floor
    # count (54/107). Using index_report here reproduced the mismatched-stat bug.
    rel_source = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": f"mlb_catcher_framing_top50_{SEASON_WINDOW}",  # claim_id kept stable (identifier, not a population statement)
        "kind": "ranking",
        "question": f"Which MLB catchers see the highest out-of-zone STRIKE rate "
                    f"(called-or-swung-or-fouled; NOT a called-strike/framing rate -- "
                    f"full qualifying population, seasons={SEASON_WINDOW})?",
        "criteria": {
            "metric": "ooz_strike_rate",
            "formula": "sum(ooz_strikes) / sum(n_ooz_called)",
            # NOTE: derived keys above are named n_ooz_called/ooz_strikes (not
            # the raw source columns) to match the min_sample floor key -- the
            # validator's aggregate grammar applies min_sample to DERIVED columns.
            "window": f"seasons_{SEASON_WINDOW}_mlb",
            "window_spec": None,
            "aggregate": {
                "group_by": "catcher_id",
                "derived": {
                    "n_ooz_called": "sum(n_ooz_called)",
                    "ooz_strikes": "sum(ooz_strikes)",
                },
            },
            "min_sample": {"n_ooz_called": MIN_OOZ_CALLED},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "catcher_id",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "NOT A CALLED-STRIKE OR FRAMING METRIC: Statcast `type` has exactly "
            "three values (S/B/X) with no code isolating a called strike from a "
            "swinging strike or foul, and this corpus has no `description` column "
            "to split them (see domains/mlb/catcher_framing_index.py CORRECTNESS "
            "FIX docstring: on the subset with des coverage, ~92% of out-of-zone "
            "type=='S' pitches are swings, only ~8% are genuine called strikes). "
            "ooz_strike_rate is confounded by BATTER chase/whiff behavior.",
            f"ooz_strike_rate = out-of-zone strikes (called-or-swung-or-fouled) / "
            f"out-of-zone pitches with type in {{S,B}}, derived from type + zone "
            f"(NEVER des -- des covers only 9.8% of called pitches on this corpus, "
            "see catcher_framing_index.py), "
            f"seasons={SEASON_WINDOW} (data/cache/statcast/statcast_fuller__2022/2023.parquet).",
            f"min_sample floor: out-of-zone pitches >= {MIN_OOZ_CALLED} "
            f"({len(qualifiers)}/{n_considered} catchers qualify) -- a defensible "
            "floor against small-sample noise.",
            f"zone-vs-geometric-plate_x/z cross-check agreement="
            f"{index_report['zone_vs_geometric_agreement_frac']:.4f} (reported, not substituted).",
            f"FULL POPULATION: all {len(qualifiers)} catchers clearing the min_sample floor "
            "are ranked here (no top-N truncation) -- below-floor catchers are honestly "
            "counted in n_excluded_below_floor, never silently dropped.",
            "DESCRIPTIVE out-of-zone strike-rate only -- NOT a framing proxy, no "
            "forecasting/market/$ edge claimed.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit MLB catcher-framing ranking claims")
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
