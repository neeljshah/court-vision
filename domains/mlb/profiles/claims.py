"""domains.mlb.profiles.claims -- top-15-per-attribute-per-season ranking
claims over the attribute engine, SAME claims-contract shape as
nba_player_interaction_claims.py (validator-compatible ranking-claim
grammar: plain row-wise formula="raw_value" on a dedicated source snapshot,
min_sample={"n": floor}, entity_key="entity_id").

Zero re-derivation of the metric itself: reuses build_profiles.py's own
per-attribute _BUILDERS dispatch on the SAME season frame the profile
parquet was built from, so a claim's ranking and the profile parquet's
raw_value for the same (attribute, season, entity) are numerically
identical by construction, not by a second, possibly-diverging formula.

CLI: python -m domains.mlb.profiles.claims
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.mlb.profiles.attribute_registry import ATTRIBUTES
from domains.mlb.profiles.build_profiles import (
    LEADERBOARD_BUILDERS, LEADERBOARD_YEARS, SEASONS, _BUILDERS, load_name_lookup, load_season,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "mlb_profile_claims.jsonl"

TOP_N = 15


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _claim_from_raw(attr: str, window: str, raw: pd.DataFrame,
                     name_lookup: dict[int, str]) -> dict[str, Any]:
    """Shared claim-assembly, decoupled from HOW `raw` was built (pitch-frame
    vs leaderboard CSV) -- both build_claim and build_claim_leaderboard funnel
    through here so a claim's shape never diverges by source."""
    spec = ATTRIBUTES[attr]
    n_considered = len(raw)
    floor = spec["floor"]

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    src_path = _OUT_DIR / f"mlb_profile_source_{attr}_{window}.parquet"
    src_cols = raw[["entity_id", "raw_value", "n"]].reset_index(drop=True)
    pq.write_table(pa.Table.from_pandas(src_cols, preserve_index=False), src_path)

    qualifiers = raw[raw["n"] >= floor].sort_values("raw_value", ascending=False).head(TOP_N)
    n_excluded = n_considered - int((raw["n"] >= floor).sum())

    ranking = [
        {"rank": i, "entity_id": int(r.entity_id),
         "entity_name": str(name_lookup.get(int(r.entity_id), str(int(r.entity_id)))),
         "value": round(float(r.raw_value), 4), "n": int(r.n)}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": f"mlb_profile_{attr}_{window}",
        "kind": "ranking",
        "question": f"MLB {window}: top {TOP_N} {spec['entity']}s by {attr} ({spec['description']})?",
        "criteria": {
            "metric": attr, "formula": "raw_value",
            "window": f"season_{window}", "aggregate": None,
            "min_sample": {"n": floor}, "top_n": TOP_N,
            "direction": "desc", "value_precision": 4, "entity_key": "entity_id",
        },
        "ranking": ranking, "source_files": [_rel(src_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered, "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            f"status={spec['status']} (see attribute_registry.py: VALIDATED_MECHANISM = built on a "
            "REPLICATED prereg ledger mechanism; VALIDATED_CLAIM = backed by a green claims store; "
            "DESCRIPTIVE = a real split with no replicated causal mechanism behind it).",
            f"min_sample floor: n>={floor} ({len(qualifiers)} of {n_considered - n_excluded} "
            "qualifiers shown, top-15 truncation, not the full qualifying population).",
            "raw_value formula: " + spec["formula"] + ".",
            "DESCRIPTIVE attribute ranking only -- no forecasting/market/$ edge claimed.",
        ],
    }


def build_claim(attr: str, season: str, frame: pd.DataFrame,
                 name_lookup: dict[int, str]) -> dict[str, Any]:
    return _claim_from_raw(attr, season, _BUILDERS[attr](frame), name_lookup)


def build_claim_leaderboard(attr: str, year: str, name_lookup: dict[int, str]) -> dict[str, Any]:
    return _claim_from_raw(attr, year, LEADERBOARD_BUILDERS[attr](year), name_lookup)


def build_all_claims() -> list[dict[str, Any]]:
    name_lookup = load_name_lookup()
    claims = []
    for season in SEASONS:
        frame = load_season(season)
        for attr in _BUILDERS:
            claims.append(build_claim(attr, season, frame, name_lookup))
    for year in LEADERBOARD_YEARS:
        for attr in LEADERBOARD_BUILDERS:
            claims.append(build_claim_leaderboard(attr, year, name_lookup))
    return claims


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main() -> int:
    claims = build_all_claims()
    out_path = write_claims(claims)
    for c in claims:
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} n_ranked={len(c['ranking'])}")
    print(f"wrote {len(claims)} claims -> {out_path}")

    from scripts.platformkit.intel_validation.validate_store import validate_and_write
    result = validate_and_write(str(out_path))
    print(f"validation: {result['n_verified']}/{result['n_claims']} verified, "
          f"{result['n_mismatch']} mismatch, {result['n_unverifiable']} unverifiable "
          f"-> {result['out']}")
    return 0 if (result["n_mismatch"] == 0 and result["n_unverifiable"] == 0) else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
