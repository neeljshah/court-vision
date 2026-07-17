"""WNBA zone/context ranking claims (Depth-wave-1 Lane 1: shooting/context
parity). Emits ONE full-population kind="ranking" claim PER dimension, read
straight from the EXISTING flat source snapshots the WNBA attribute engine
already writes -- data/cache/intel_claims/wnba_profile_source_<attr>.parquet
(entity_id, raw_value, n), written by domains/basketball_wnba/profiles/
claims.py:44-47. READ ONLY: this module never touches that builder.

DIMENSIONS covers the zone-shooting/context slice of the attribute engine
that has no dedicated ranking claim of its own yet (the engine's own
wnba_profile_claims.jsonl already top-10-truncates every attribute; this
store instead ranks the FULL qualifying population, same precedent as
wnba_claims.py's sibling full-population producers):

  zone_rim_efg              -- eFG% on rim-zone attempts (attribute_registry
      floor=20 zone attempts; this store's own floor is a looser n>=10,
      see FLOOR below).
  spacing                   -- lineup mean pairwise shot-location distance
      (attribute_registry floor=50 n_shots; same looser n>=10 here).
  gravity                   -- teammate eFG% lift on-court vs off-court
      (attribute_registry floor=200 teammate_fga; same looser n>=10 here).
  def_rim_efg_allowed_delta -- opponent rim eFG% allowed off-court minus
      on-court (attribute_registry floor=300 on/off minutes; same looser
      n>=10 here).

FLOOR = 10 is a DELIBERATELY LOOSER floor than each dimension's own
attribute_registry.py floor (20/50/200/300) -- this store answers "give me
every entity with a bare-minimum-reliable sample," not the attribute
engine's tighter claim-quality bar. Below-floor entities are counted in
n_excluded_below_floor, never silently dropped.

formula="raw_value" is a trivially recomputable identity over the snapshot's
own raw_value column -- same tautological-by-construction contract as
domains/basketball_wnba/profiles/claims.py and the full-pair-population
precedent in tennis_h2h_claims.py (build_ranking_claim). entity_key=
"entity_id" matches the snapshot's own column name.

CONTRACT: kind="ranking", edge_claimed=False, DESCRIPTIVE only. NETWORK: zero.

CLI:
    python -m scripts.platformkit.intel_validation.wnba_zone_context_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/wnba_zone_context_claims.jsonl \
        --output data/cache/intel_claims/wnba_zone_context_claims_validation.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_OUT_DIR = _SRC_DIR
_CLAIMS_OUT = _OUT_DIR / "wnba_zone_context_claims.jsonl"

SEASON_WINDOW = "2026"
FLOOR = 10  # deliberately looser than each dim's own attribute_registry floor

# dimension -> (question phrase, human description for caveats)
DIMENSIONS: dict[str, str] = {
    "zone_rim_efg": "eFG% on rim-zone shot attempts",
    "spacing": "lineup mean pairwise shot-location distance",
    "gravity": "teammate eFG% lift while this player is on-court vs off-court",
    "def_rim_efg_allowed_delta": "opponent rim eFG% allowed off-court minus on-court "
                                  "(higher = tighter individual rim defense)",
}


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _source_path(dim: str) -> Path:
    return _SRC_DIR / f"wnba_profile_source_{dim}.parquet"


def available_dimensions() -> list[str]:
    """Dimensions whose source snapshot actually exists and is non-empty --
    an honest PARTIAL (skip + note) if the attribute engine hasn't run for one."""
    out = []
    for dim in DIMENSIONS:
        p = _source_path(dim)
        if p.exists() and len(pd.read_parquet(p)) > 0:
            out.append(dim)
    return out


def build_claim(dim: str) -> dict[str, Any]:
    src = _source_path(dim)
    df = pd.read_parquet(src)
    n_considered = len(df)
    qualifiers = df[df["n"] >= FLOOR].dropna(subset=["raw_value"]).copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values("raw_value", ascending=False).reset_index(drop=True)

    ranking = [
        {"rank": i, "entity_id": str(r.entity_id),
         "entity_name": str(getattr(r, "entity_name", r.entity_id)),
         "value": round(float(r.raw_value), 4), "n": round(float(r.n), 2)}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    desc = DIMENSIONS[dim]
    return {
        "claim_id": f"wnba_zone_context_{dim}_full_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": f"WNBA {SEASON_WINDOW}: full-population ranking by {dim} ({desc})?",
        "criteria": {
            "metric": dim, "formula": "raw_value", "window": f"season_{SEASON_WINDOW}_wnba",
            "aggregate": None, "min_sample": {"n": FLOOR}, "direction": "desc",
            "value_precision": 4, "entity_key": "entity_id",
        },
        "ranking": ranking,
        "source_files": [_rel(src)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            f"min_sample floor n>={FLOOR} -- deliberately LOOSER than this dimension's own "
            "attribute_registry.py floor (20-300 depending on dim); below-floor entities are "
            "counted in n_excluded_below_floor, never silently dropped.",
            "FULL POPULATION: every entity clearing the floor is ranked, no top-N cap.",
            "raw_value formula: identity read of the attribute engine's own snapshot column "
            "(same tautological-by-construction contract as domains/basketball_wnba/profiles/"
            "claims.py); the source snapshot itself is READ ONLY here, never rebuilt.",
            "DESCRIPTIVE zone/context ranking only -- not a predictor of future performance, "
            "no market or dollar edge claimed.",
            "entity_name is a display field only, not part of the validated raw_value identity "
            "(falls back to entity_id for legacy name-less source snapshots).",
        ],
    }


def build_all_claims() -> list[dict[str, Any]]:
    return [build_claim(dim) for dim in available_dimensions()]


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit WNBA zone/context DESCRIPTIVE ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    skipped = [d for d in DIMENSIONS if d not in available_dimensions()]
    claims = build_all_claims()
    out_path = write_claims(claims, Path(args.output))
    for c in claims:
        top = c["ranking"][0] if c["ranking"] else None
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} n_ranked={len(c['ranking'])} "
              f"top={top}")
    if skipped:
        print(f"skipped (source missing/empty): {skipped}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
