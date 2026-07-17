"""domains.basketball_wnba.profiles.claims -- top-10-per-attribute ranking
claims over the WNBA attribute engine, same claims-contract shape as
domains/mlb/profiles/claims.py: a dedicated source snapshot per attribute
(entity_id, raw_value, n) + formula="raw_value" (a trivially recomputable
identity), so THIS store's own re-validation is tautological by construction.
The honest cross-check signal is attribute_registry.py's `status` field
(VALIDATED_CLAIM vs DESCRIPTIVE), which reflects independent corroboration
by wnba_player_form_claims.jsonl / wnba_lineup_claims.jsonl -- NOT this
file's validator verdict.

CLI: python -m domains.basketball_wnba.profiles.claims
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.basketball_wnba.profiles.attribute_registry import ATTRIBUTES
from domains.basketball_wnba.profiles.build_profiles import _BUILDERS, _FRAME_LOADERS

REPO_ROOT = Path(__file__).resolve().parents[3]
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "wnba_profile_claims.jsonl"

TOP_N = 10


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def build_claim(attr: str) -> dict[str, Any]:
    spec = ATTRIBUTES[attr]
    raw = _BUILDERS[attr](_FRAME_LOADERS[attr]())
    n_considered = len(raw)
    floor = spec["floor"]

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    src_path = _OUT_DIR / f"wnba_profile_source_{attr}.parquet"
    src_cols = raw[["entity_id", "entity_name", "raw_value", "n"]].reset_index(drop=True)
    pq.write_table(pa.Table.from_pandas(src_cols, preserve_index=False), src_path)

    qualifiers = raw[raw["n"] >= floor].sort_values("raw_value", ascending=False).head(TOP_N)
    n_excluded = n_considered - int((raw["n"] >= floor).sum())

    ranking = [
        {"rank": i, "entity_id": str(r.entity_id), "entity_name": str(r.entity_name),
         "value": round(float(r.raw_value), 4), "n": round(float(r.n), 2)}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": f"wnba_profile_{attr}_2026",
        "kind": "ranking",
        "question": f"WNBA 2026: top {TOP_N} {spec['entity']}s by {attr} ({spec['description']})?",
        "criteria": {
            "metric": attr, "formula": "raw_value", "window": "season_2026", "aggregate": None,
            "min_sample": {"n": floor}, "top_n": TOP_N, "direction": "desc",
            "value_precision": 4, "entity_key": "entity_id",
        },
        "ranking": ranking, "source_files": [_rel(src_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered, "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            f"status={spec['status']} / weight_ledger_family={spec['weight_ledger_family']} "
            "(see attribute_registry.py for the exact independent-corroboration rule).",
            f"min_sample floor: n>={floor} ({len(qualifiers)} of {n_considered - n_excluded} "
            f"qualifiers shown, top-{TOP_N} truncation, not the full qualifying population).",
            "raw_value formula: " + spec["formula"] + ".",
            "DESCRIPTIVE attribute ranking only -- no forecasting/market/$ edge claimed.",
        ],
    }


def build_all_claims() -> list[dict[str, Any]]:
    return [build_claim(attr) for attr in ATTRIBUTES]


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
