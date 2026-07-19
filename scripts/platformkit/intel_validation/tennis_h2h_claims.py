"""Tennis head-to-head (H2H) pair-keyed ranking claims (mission spine 5, lane
tennis-h2h-fullpairs).

Emits FULL PAIR-POPULATION descriptive career head-to-head claims from the
wave-52 persisted data/cache/tennis_atlas/h2h.parquet (30616 match rows,
p1_id < p2_id canonically ordered per pair): for EVERY distinct (p1_id,p2_id)
pair above the min_sample floor, h2h_win_share (wins_p1 / meetings) and
h2h_meetings, in the SAME pair-keyed claims contract shape proven by
scripts/platformkit/intel_validation/test_claims_validator_pairkey.py
(criteria.entity_key = [p1_id, p2_id], a LIST of columns) -- the FIRST
production producer to exercise that path (previously fixture-only).

WHY A PRE-AGGREGATED SIDE PARQUET (not criteria.aggregate): h2h.parquet is
MATCH-level (one row per match played, not per pair). The claims contract's
criteria.aggregate.group_by path in aggregate_recompute.recompute_aggregate
takes a single group_by COLUMN (a bare string), not a list -- it cannot
group by a (p1_id, p2_id) pair. Rather than touch that independent-validator
module (RAILS: claims_validator.py / verdict_claims_validator.py are
UNMODIFIED), this producer follows the SAME precedent as
tennis_hold_claims.py: pre-aggregate to a per-pair side parquet
(data/cache/intel_claims/tennis_h2h_pairs_atp.parquet, columns p1_id, p2_id,
wins_p1, meetings) and go through the validator's PLAIN (non-aggregate)
formula path, which already supports a list entity_key. The validator still
independently recomputes wins_p1/meetings straight off that on-disk parquet
(zero import of this producer module) -- it just recomputes from
pre-materialized per-pair sums rather than re-deriving them from raw match
rows, matching how tennis_hold_claims.py's snapshot parquet works today.

MIN-SAMPLE FLOOR: meetings >= 3 -- a defensible floor against 1-2-meeting
noise (dominance ratios like 1/1=100% or 1/2=50% are not a meaningful
"who usually wins this pair" signal); STATED explicitly in the claim's
min_sample and caveats. Every pair below the floor is honestly counted in
n_excluded_below_floor, never silently dropped from n_considered.

TOUR SPLIT: h2h.parquet's corpus_id column is 100% "sackmann_atp_matches_
parquet" in this checkout (verified) -- this producer emits ONE ATP claim.
No WTA rows exist in this parquet to split by tour; if a future corpus_id
value appears this module would need a WTA branch added, not fabricated now.

CANONICAL PAIR ORDERING: h2h.parquet already has p1_id < p2_id for 100% of
rows (verified) -- no reversed-pair merge/renormalization is needed; wins_p1
is simply "wins by the numerically-lower player_id" for that ordered pair.

NETWORK: zero. Pure pandas over an already-materialized parquet.
DESCRIPTIVE career head-to-head only -- NOT a predictor, no market/$ edge.

CLI:
    python -m scripts.platformkit.intel_validation.tennis_h2h_claims
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

_H2H_SOURCE = REPO_ROOT / "data" / "cache" / "tennis_atlas" / "h2h.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "tennis_h2h_claims.jsonl"
_PAIR_PARQUET_OUT = _OUT_DIR / "tennis_h2h_pairs_atp.parquet"

MIN_MEETINGS = 3  # floor: below this, dominance ratios (1/1, 1/2) are noise, not signal


def build_pair_table(h2h: pd.DataFrame) -> pd.DataFrame:
    """One row per distinct (p1_id, p2_id) pair: wins_p1 (matches won by the
    numerically-lower player_id in that ordered pair) and meetings (total
    matches played between them). p1_id < p2_id for every input row
    (verified on-disk invariant of h2h.parquet), so no reversed-pair merge
    is needed -- straight groupby."""
    grouped = h2h.groupby(["p1_id", "p2_id"], as_index=False).agg(
        meetings=("winner", "size"),
        wins_p1=("winner", lambda s: int((s == 1).sum())),
    )
    return grouped


def _name_lookup(h2h: pd.DataFrame) -> dict[int, str]:
    names: dict[int, str] = {}
    for id_col, name_col in (("p1_id", "p1_name"), ("p2_id", "p2_name")):
        sub = h2h[[id_col, name_col]].dropna()
        for pid, name in zip(sub[id_col], sub[name_col]):
            names[int(pid)] = str(name)
    return names


def build_ranking_claim() -> dict[str, Any]:
    h2h = pd.read_parquet(_H2H_SOURCE)
    pairs = build_pair_table(h2h)
    n_considered = len(pairs)
    n_excluded = int((pairs["meetings"] < MIN_MEETINGS).sum())

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_cols = pairs[["p1_id", "p2_id", "wins_p1", "meetings"]].copy()
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), _PAIR_PARQUET_OUT)

    qualifiers = pairs[pairs["meetings"] >= MIN_MEETINGS].copy()
    qualifiers["h2h_win_share"] = qualifiers["wins_p1"] / qualifiers["meetings"]
    # tie-break: value DESC, THEN pair entity_key (p1_id, p2_id) ASC -- matches
    # claims_validator.py's generic recompute tie-break, see tennis_ranking_claims.py docstring.
    qualifiers = qualifiers.sort_values(["h2h_win_share", "p1_id", "p2_id"],
                                         ascending=[False, True, True]).reset_index(drop=True)
    # FULL PAIR POPULATION: every qualifying pair above the floor gets a row
    # (no head(N) slice) -- below-floor pairs are already counted in
    # n_excluded above, never dropped from n_considered.

    names = _name_lookup(h2h)
    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        p1_id, p2_id = int(row.p1_id), int(row.p2_id)
        ranking.append({
            "rank": i,
            "p1_id": p1_id,
            "p2_id": p2_id,
            "p1_name": names.get(p1_id, "Unknown"),
            "p2_name": names.get(p2_id, "Unknown"),
            "value": round(float(row.h2h_win_share), 4),
            "n": int(row.meetings),
        })

    rel_source = str(_PAIR_PARQUET_OUT.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": "tennis_h2h_win_share_atp_fullpairs",
        "kind": "ranking",
        "question": (
            "For every ATP pair with a real head-to-head history, what is each pair's "
            "career h2h win share (full pair population)?"
        ),
        "criteria": {
            "metric": "h2h_win_share",
            "formula": "wins_p1 / meetings",
            "window": "career_asof_2025",
            "min_sample": {"meetings": MIN_MEETINGS},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": ["p1_id", "p2_id"],
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "DESCRIPTIVE career head-to-head only -- NOT a predictor of a future match; "
            "no market/$ edge claimed.",
            f"min_sample floor meetings>={MIN_MEETINGS} -- below this, a pair's win share "
            "(e.g. 1/1 or 1/2) reflects one or two matches, not a meaningful career h2h "
            "pattern; below-floor pairs are counted in n_excluded_below_floor, never dropped.",
            "ATP tour only: this parquet's corpus_id is 100% sackmann_atp_matches_parquet in "
            "this checkout (verified) -- no WTA rows exist here to split by tour.",
            "p1_id < p2_id is the on-disk canonical pair ordering (verified 100% of rows); "
            "wins_p1 counts matches won by the numerically-lower player_id in that pair, "
            "not a 'home'/'favorite' designation.",
            "FULL PAIR POPULATION: every qualifying pair above the floor is ranked (no top-N "
            "slice); pairs below the floor are counted in n_excluded_below_floor, never dropped "
            "from n_considered.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit tennis H2H full-pair-population ranking claims (ATP)")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claim = build_ranking_claim()
    out_path = write_claims([claim], Path(args.output))
    print(
        f"{claim['claim_id']}: n_considered={claim['n_considered']} "
        f"n_excluded_below_floor={claim['n_excluded_below_floor']} "
        f"top1={claim['ranking'][0] if claim['ranking'] else None}"
    )
    print(f"wrote 1 claim -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
