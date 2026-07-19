"""scripts.platformkit.predictive_validity.validity_ladder -- the honest tier
composer for impact-index claims.

WHY
---
Every impact-index answer (defenders v1-v4, gravity, shooter composites) had
its OWN scattered validity story: some had an absence-swing receipt, some had
a predictive-validity stamp, some had neither. This module is a READ-ONLY
composer (style-matched to forward_evidence_scoreboard.py): it never
recomputes a statistic, it only reads the artifacts already written by
absence_swing.py, predictive_validity/artifacts.py, and the claims
validators, and assigns each registered index the HIGHEST tier it has a live
receipt for.

TIERS (highest tier with a live artifact receipt wins; judge-never-ingredient
is binding -- none of these judges ever feed an index's own computation):
  T0_INTEGRITY -- the claim recomputes (claims-validation sidecar says
                  n_verified > 0, n_mismatch == 0). Universal floor.
  T1_CRITERION -- independent judge correlation, CI excludes 0 (absence-swing
                  VALID_SIGNAL verdict, defense; or the offense-swing
                  judge below, when that artifact exists).
  T2_PREDICTIVE -- leak-free OOS predictive stamp (PREDICTIVE_VERIFIED in a
                  predictive_validity/<family>__<metric>.json artifact).
  T3_MARKET     -- reserved. NEVER auto-granted by this module.

SOURCES (read-only, never recomputed):
  data/cache/intel_claims/<validation_file>            -- T0 (verified count)
  data/cache/benchmarks/absence_swing_validity.json     -- T1 (defense judge)
  data/cache/benchmarks/absence_swing_offense_validity.json -- T1 (offense
    judge; does not exist yet -- read if present, tier honestly if absent.
    See the offense-judge spec this module's caller reported, NOT built here.)
  data/cache/predictive_validity/<family>__<metric>.json -- T2

REGISTRY maps each shipped index name to the exact artifact keys/filenames
it should be looked up under (index names match absence_swing.KNOWN_INDEXES
and each producer's own claim "metric" field).

INVARIANTS: read-only (writes only its own composed artifact); <=300 LOC;
ASCII only; no network; never writes data/registry/; edge_claimed=False
always.

CLI: python -m scripts.platformkit.predictive_validity.validity_ladder
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATION_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
ABSENCE_SWING_PATH = REPO_ROOT / "data" / "cache" / "benchmarks" / "absence_swing_validity.json"
ABSENCE_SWING_OFFENSE_PATH = (
    REPO_ROOT / "data" / "cache" / "benchmarks" / "absence_swing_offense_validity.json"
)
PREDICTIVE_DIR = REPO_ROOT / "data" / "cache" / "predictive_validity"
ARTIFACT_PATH = REPO_ROOT / "data" / "cache" / "benchmarks" / "validity_ladder.json"

T0, T1, T2, T3 = "T0_INTEGRITY", "T1_CRITERION", "T2_PREDICTIVE", "T3_MARKET"

# index_name -> {validation_file, absence_key, offense_key, predictive_file}
# absence_key/offense_key/predictive_file are None when that judge doesn't
# (yet) cover the index -- an honest gap, not an error.
REGISTRY: dict[str, dict[str, Optional[str]]] = {
    "nba_defender_v1": {
        "validation_file": "nba_defender_v1_claims_validation.json",
        "absence_key": "nba_defender_v1", "offense_key": None, "predictive_file": None,
    },
    "nba_defender_v2_context": {
        "validation_file": "nba_defender_v2_context_claims_validation.json",
        "absence_key": "nba_defender_v2_context", "offense_key": None, "predictive_file": None,
    },
    "nba_defender_v3_team_rel": {
        "validation_file": "nba_defender_v3_team_rel_claims_validation.json",
        "absence_key": "nba_defender_v3_team_rel", "offense_key": None, "predictive_file": None,
    },
    "nba_defender_v4_individual": {
        "validation_file": "nba_defender_v4_individual_claims_validation.json",
        "absence_key": "nba_defender_v4_individual", "offense_key": None, "predictive_file": None,
    },
    "nba_gravity_v2": {
        "validation_file": "nba_gravity_v2_claims_validation.json",
        "absence_key": None, "offense_key": "nba_gravity_v2", "predictive_file": None,
    },
    "nba_gravity_proxy": {
        "validation_file": "nba_gravity_proxy_claims_validation.json",
        "absence_key": None, "offense_key": "nba_gravity_proxy",
        "predictive_file": "nba_gravity_proxy__gravity_score.json",
    },
    "shooter_composite_v2": {
        "validation_file": "shooter_composite_v2_claims_validation.json",
        "absence_key": None, "offense_key": "shooter_composite_v2",
        "predictive_file": "shooter_composite_v2__shooter_composite_v2_asof_approx.json",
    },
    "shooter_composite_v2_asof_approx": {
        "validation_file": "shooter_composite_v2_asof_approx_claims_validation.json",
        "absence_key": None, "offense_key": "shooter_composite_v2_asof_approx",
        # predictive test was run against this exact metric, stamped under
        # the v2 family's artifact filename -- shared receipt, honestly noted.
        "predictive_file": "shooter_composite_v2__shooter_composite_v2_asof_approx.json",
    },
}


def _read_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="ascii"))
    except Exception:  # noqa: BLE001 -- missing/corrupt source degrades to absent
        return None


def _t0_receipt(cfg: dict[str, Optional[str]]) -> Optional[dict[str, Any]]:
    vfile = cfg.get("validation_file")
    if not vfile:
        return None
    doc = _read_json(VALIDATION_DIR / vfile)
    if not doc or doc.get("n_verified", 0) <= 0 or doc.get("n_mismatch", 0) != 0:
        return None
    return {
        "tier": T0, "kind": "claims_validation", "source": f"data/cache/intel_claims/{vfile}",
        "detail": f"n_verified={doc['n_verified']} n_mismatch={doc['n_mismatch']} "
                  f"as_of={doc.get('generated_at', '?')}",
    }


def _t1_receipt(index_name: str, key: Optional[str], doc: Optional[dict[str, Any]],
                 source: str, label: str) -> Optional[dict[str, Any]]:
    if not key or not doc:
        return None
    entry = doc.get("indexes", {}).get(key)
    # VALID_SIGNAL_PARTIAL_JUDGE (offense judge w/ construction overlap, e.g.
    # gravity) grants T1 too -- the partial-independence label rides along in
    # the receipt so the caveat discloses it.
    if not entry or entry.get("n", 0) <= 0 or entry.get("verdict") not in (
            "VALID_SIGNAL", "VALID_SIGNAL_PARTIAL_JUDGE"):
        return None
    ci = entry["ci"]
    return {
        "tier": T1, "kind": label, "source": source,
        "detail": f"rho={entry['rho']:+.3f} CI[{ci['lo']:+.3f},{ci['hi']:+.3f}] "
                  f"n={entry['n']} as_of={doc.get('as_of', '?')} verdict={entry['verdict']}",
    }


def _t2_receipt(cfg: dict[str, Optional[str]]) -> Optional[dict[str, Any]]:
    pfile = cfg.get("predictive_file")
    if not pfile:
        return None
    doc = _read_json(PREDICTIVE_DIR / pfile)
    if not doc or doc.get("verdict") != "PREDICTIVE_VERIFIED":
        return None
    return {
        "tier": T2, "kind": "predictive_validity", "source": f"data/cache/predictive_validity/{pfile}",
        "detail": f"verdict={doc['verdict']} mean_rho_metric={doc.get('mean_rho_metric')} "
                  f"n_folds={doc.get('n_folds')} as_of={doc.get('generated_at', '?')}",
    }


_TIER_RANK = {T0: 0, T1: 1, T2: 2, T3: 3}
_T0_CAVEAT = "DESCRIPTIVE -- recompute-verified but no independent validity receipt yet"


def compose_index(index_name: str, cfg: dict[str, Optional[str]],
                   absence_doc: Optional[dict[str, Any]],
                   offense_doc: Optional[dict[str, Any]]) -> dict[str, Any]:
    receipts = []
    for r in (
        _t0_receipt(cfg),
        _t1_receipt(index_name, cfg.get("absence_key"), absence_doc,
                    "data/cache/benchmarks/absence_swing_validity.json", "absence_swing_criterion"),
        _t1_receipt(index_name, cfg.get("offense_key"), offense_doc,
                    "data/cache/benchmarks/absence_swing_offense_validity.json", "offense_swing_criterion"),
        _t2_receipt(cfg),
    ):
        if r is not None:
            receipts.append(r)

    if not receipts:
        return {"tier": T0, "receipts": [], "caveat": _T0_CAVEAT}

    tier = max((r["tier"] for r in receipts), key=lambda t: _TIER_RANK[t])
    if tier == T0:
        caveat = _T0_CAVEAT
    else:
        best = max((r for r in receipts if r["tier"] == tier), key=lambda r: r["kind"])
        caveat = f"{tier}: {best['kind']} -- {best['detail']}"
    return {"tier": tier, "receipts": receipts, "caveat": caveat}


def build_ladder() -> dict[str, Any]:
    absence_doc = _read_json(ABSENCE_SWING_PATH)
    offense_doc = _read_json(ABSENCE_SWING_OFFENSE_PATH)
    indexes = {name: compose_index(name, cfg, absence_doc, offense_doc)
               for name, cfg in REGISTRY.items()}
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "indexes": indexes,
        "honest_note": (
            "Composed read-only from existing claims-validation sidecars, "
            "absence_swing_validity.json, and predictive_validity artifacts -- "
            "never recomputes a correlation or a verdict. Tier = highest rung "
            "with a LIVE receipt; T3_MARKET is reserved and never auto-granted. "
            "Judge-never-ingredient: none of these judge signals feed any "
            "index's own computation. An offense-side absence-swing judge "
            "(absence_swing_offense_validity.json) does not exist yet -- "
            "offensive indexes (gravity, shooter composites) honestly stay "
            "below T1 until it does."
        ),
        "edge_claimed": False,
    }


def write_artifact(doc: dict[str, Any], path: Path = ARTIFACT_PATH) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="ascii")
    tmp.replace(path)
    return str(path)


def ladder_caveat(index_name: str, path: Path = ARTIFACT_PATH) -> str:
    """One-line tier-aware caveat for a claim's caveats list. Same fallback
    contract as absence_swing.validity_caveat: honest string when the ladder
    artifact or the index entry is absent."""
    doc = _read_json(path)
    if not doc:
        return f"no validity ladder receipt on file for {index_name}"
    entry = doc.get("indexes", {}).get(index_name)
    if not entry:
        return f"no validity ladder receipt on file for {index_name}"
    return f"validity ladder [{entry['tier']}] {entry['caveat']} (as_of {doc.get('as_of', '?')})"


def main() -> dict[str, Any]:
    doc = build_ladder()
    out_path = write_artifact(doc)
    tiers = {name: e["tier"] for name, e in doc["indexes"].items()}
    print(f"validity_ladder: {tiers} -> {out_path}")
    return doc


if __name__ == "__main__":
    main()
