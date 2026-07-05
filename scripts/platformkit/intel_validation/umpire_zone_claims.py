"""MLB umpire out-of-zone strike-rate ranking claims producer (arm 2 of 2,
mirrors catcher_framing_claims.py's structure exactly -- see that module for
the full metric-definition rationale, which is IDENTICAL here: ooz_strike_rate
= called-or-swung-or-fouled out-of-zone strike rate, NOT a called-strike or
zone-consistency metric, aggregated per umpire instead of per catcher).

SOURCE: domains/mlb/umpire_zone_index.py is the domain-level index builder
(reuses load_called_pitches/derive_out_of_zone from catcher_framing_index.py,
joins statcast pitches to probables.parquet by game_pk for hp_umpire_id --
see that module's docstring for the join-probe rationale and the leak-free
caveat: this is a DESCRIPTIVE/retrospective join only, not a pregame feature).
Running this producer re-invokes build_umpire_index() fresh (not a stale read
of a previously-written parquet) so the claim always reflects the current
corpus.

WINDOW: seasons 2022+2023 (data/cache/statcast/statcast_fuller__2022/2023.parquet
joined against data/domains/mlb/probables.parquet for hp_umpire_id).

MIN-SAMPLE FLOOR: n_ooz_called (out-of-zone called-or-swung pitches summed per
umpire) >= 500 -- same floor convention as catcher_framing_claims.py.

LEAK DISCIPLINE: purely descriptive/retrospective (a completed 2-season
statcast aggregate joined to a fixed historical umpire assignment) -- no
forecasting claim, no leak-risk window; NOT offered as a pregame feature (see
umpire_zone_index.py leak_free_caveat).

NETWORK: zero. Pure pandas over already-materialized parquets.
DESCRIPTIVE/SCOUTING ONLY -- NO MARKET/$ EDGE CLAIMED.

CLI:
    python -m scripts.platformkit.intel_validation.umpire_zone_claims
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

from domains.mlb.umpire_zone_index import MIN_OOZ_CALLED, build_umpire_index

REPO_ROOT = Path(__file__).resolve().parents[3]

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "umpire_zone_claims.jsonl"
_SNAPSHOT_OUT = _OUT_DIR / "umpire_zone_snapshot.parquet"

SEASON_WINDOW = "2022_2023"
TOP_N = 50


def build_snapshot() -> tuple[Path, dict, dict]:
    """Re-run the domain index builder ONCE with min_ooz_called=0 so the
    SNAPSHOT carries ALL umpires (the claim's min_sample criteria, not this
    producer, applies the real 500 floor when the validator recomputes) --
    matching catcher_framing_claims.py's precedent. The zero-floor `report`
    returned here has n_qualifying_umpires at the ZERO floor, not the 500
    floor; build_ranking_claim below computes the real floor-applied count
    itself. name_lookup is captured from this SAME call (never a second live
    call to build_umpire_index) -- a second call with a different floor can
    tie-break identical ooz_strike_rate values in a different row order,
    which would make the recomputed ranking's exact-tie ordering diverge
    from the ranking shipped here (verified live: two umpires in this corpus
    share the identical float 0.29508196721311475)."""
    qualifiers, report = build_umpire_index(min_ooz_called=0)
    name_lookup = dict(zip(qualifiers["umpire_id"], qualifiers["umpire_name"]))
    write_cols = qualifiers[["umpire_id", "n_ooz_called", "ooz_strikes"]].copy()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), _SNAPSHOT_OUT)
    return _SNAPSHOT_OUT, report, name_lookup


def build_ranking_claim() -> dict[str, Any]:
    out_path, index_report, name_lookup = build_snapshot()
    raw = pd.read_parquet(out_path)

    n_considered = len(raw)
    qualifiers = raw[raw["n_ooz_called"] >= MIN_OOZ_CALLED].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers["ooz_strike_rate"] = (
        qualifiers["ooz_strikes"] / qualifiers["n_ooz_called"]
    )
    # KNOWN LIMITATION (reported, not hidden): claims_validator.validate_claim's
    # generic recompute sorts ties with pandas' default (unstable) quicksort, so
    # an EXACT float tie in ooz_strike_rate can independently recompute in either
    # order -- verified live this session: umpire_id 427164 and 484499 share the
    # identical float 0.29508196721311475 in this corpus. A stable, explicit
    # secondary key (umpire_id ascending) makes THIS producer's own ranking
    # order deterministic across repeated runs; it does not and cannot force the
    # validator's independent recompute to agree on which of two tied entities
    # lands at the boundary rank -- that is a shared claims_validator.py
    # tie-break gap, out of this lane's scope to fix (see OWNS paths).
    qualifiers = qualifiers.sort_values(
        ["ooz_strike_rate", "umpire_id"], ascending=[False, True]
    ).reset_index(drop=True)
    top = qualifiers.head(TOP_N)

    ranking = []
    for i, row in enumerate(top.itertuples(index=False), start=1):
        uid = row.umpire_id
        ranking.append({
            "rank": i,
            "umpire_id": str(uid),
            "umpire_name": str(name_lookup.get(uid, "Unknown")),
            "value": round(float(row.ooz_strike_rate), 4),
            "n": int(row.n_ooz_called),
        })

    rel_source = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": f"mlb_umpire_zone_top50_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": f"Which MLB home-plate umpires see the highest out-of-zone STRIKE rate "
                    f"(called-or-swung-or-fouled; NOT a called-strike/zone-consistency rate -- "
                    f"top 50, seasons={SEASON_WINDOW})?",
        "criteria": {
            "metric": "ooz_strike_rate",
            "formula": "sum(ooz_strikes) / sum(n_ooz_called)",
            "window": f"seasons_{SEASON_WINDOW}_mlb",
            "window_spec": None,
            "aggregate": {
                "group_by": "umpire_id",
                "derived": {
                    "n_ooz_called": "sum(n_ooz_called)",
                    "ooz_strikes": "sum(ooz_strikes)",
                },
            },
            "min_sample": {"n_ooz_called": MIN_OOZ_CALLED},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "umpire_id",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "NOT A CALLED-STRIKE OR ZONE-CONSISTENCY METRIC: Statcast `type` has "
            "exactly three values (S/B/X) with no code isolating a called strike from "
            "a swinging strike or foul (see domains/mlb/catcher_framing_index.py "
            "CORRECTNESS FIX docstring, shared rationale). ooz_strike_rate is "
            "confounded by both batter chase/whiff behavior and the specific "
            "pitcher/batter mix each umpire happens to have worked.",
            f"ooz_strike_rate = out-of-zone strikes (called-or-swung-or-fouled) / "
            f"out-of-zone pitches with type in {{S,B}}, derived from type + zone "
            f"(NEVER des), seasons={SEASON_WINDOW}, joined to "
            "data/domains/mlb/probables.parquet by game_pk for hp_umpire_id "
            "(see domains/mlb/umpire_zone_index.py for the join-probe rationale).",
            f"min_sample floor: out-of-zone pitches >= {MIN_OOZ_CALLED} "
            f"({len(qualifiers)}/{n_considered} umpires qualify).",
            "NOT A LEAK-FREE PREGAME FEATURE: probables.parquet's umpire-assignment "
            "snapshot for these seasons is a 2026-07 backfill, not captured at-the-time "
            "of the games -- descriptive/retrospective identity join only (see "
            "umpire_zone_index.py leak_free_caveat).",
            "DESCRIPTIVE out-of-zone strike-rate only -- NOT a zone-consistency proxy, "
            "no forecasting/market/$ edge claimed.",
            "KNOWN TIE-BREAK GAP (reported, not hidden): umpire_id 427164 (Andy "
            "Fletcher) and 484499 (Manny Gonzalez) share an EXACT float "
            "ooz_strike_rate (0.29508196721311475) at ranks 8/9 in this corpus. "
            "claims_validator.validate_claim's generic aggregate-recompute sorts "
            "ties with pandas' default (non-stable-guaranteed) quicksort, so an "
            "independent recompute can order this specific tied pair opposite to "
            "the order shipped here -- values and floor-membership both still "
            "verify correctly; only the relative rank of this one exact-tied pair "
            "is not guaranteed reproducible by the shared validator. Out of this "
            "producer's scope to fix (shared claims_validator.py internals).",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit MLB umpire-zone ranking claims")
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
