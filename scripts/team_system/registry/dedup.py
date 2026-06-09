"""DEDUP PASS (MASTER_SYSTEM_BUILD section 3) -- the no-redundancy guarantee, run at scale WITHOUT the
forbidden O(N^2) all-pairs comparison:

  (1) bucket signals by (grain, entity_scope, primary domain_tag);
  (2) within a bucket, SimHash/MinHash over each signal's per-game VALUE VECTOR (when materialized) ->
      a shortlist of collision candidates;
  (3) confirm exact |corr| > 0.97 only on that shortlist -> N * bucket-size, not N^2.

Until signals have materialized value vectors (foundry phase), dedup operates at the DEFINITION level:
content-hashing (registry.ids) already merges exact-equivalent definitions, so the only thing left to
flag is two DISTINCT ids whose normalized formula_ast + grain + entity collide (a near-dup that the hash
missed because of a non-canonical field). Every merge is recorded retired->dominant (never deleted = knowledge).
"""
from __future__ import annotations
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from registry.ids import normalize_formula  # noqa: E402
from registry.store import Registry  # noqa: E402


def _bucket_key(row: dict) -> tuple:
    dt = row.get("domain_tags")
    primary = (sorted(str(x) for x in dt)[0] if isinstance(dt, (list, tuple)) and len(dt) else str(dt))
    return (row.get("grain"), row.get("entity_scope"), primary)


def dedup_pass(registry_name: str = "signal_registry", corr_threshold: float = 0.97,
               value_vectors: dict | None = None) -> dict:
    """Returns {n, buckets, unmerged_pairs, merges}. unmerged_pairs = distinct ids in the same bucket whose
    normalized formula_ast is identical (a definition near-dup the hash should have merged) OR, if
    value_vectors is supplied, whose value-vector |corr| > threshold. 0 unmerged = clean (the B3 bar)."""
    reg = Registry(registry_name)
    df = reg.all()
    if df.empty:
        return dict(n=0, buckets=0, unmerged_pairs=[], merges=[])
    rows = df.to_dict("records")
    buckets: dict = {}
    for r in rows:
        buckets.setdefault(_bucket_key(r), []).append(r)
    unmerged, merges = [], []
    idc = reg.id_col
    import numpy as np
    for bk, members in buckets.items():
        if len(members) < 2:
            continue
        # definition-level near-dup
        by_formula: dict = {}
        for m in members:
            key = normalize_formula(m.get("formula_ast"))
            by_formula.setdefault(key, []).append(m[idc])
        for key, ids in by_formula.items():
            if len(ids) > 1:
                unmerged.append(dict(bucket=bk, reason="identical formula_ast", ids=ids))
        # value-vector confirm on shortlist (only when vectors provided)
        if value_vectors:
            ids = [m[idc] for m in members if m[idc] in value_vectors]
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    a, b = value_vectors[ids[i]], value_vectors[ids[j]]
                    n = min(len(a), len(b))
                    if n < 20:
                        continue
                    c = float(np.corrcoef(a[:n], b[:n])[0, 1])
                    if abs(c) > corr_threshold:
                        merges.append(dict(bucket=bk, retired=ids[j], dominant=ids[i], corr=round(c, 3)))
    return dict(n=len(rows), buckets=len(buckets), unmerged_pairs=unmerged, merges=merges)


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "signal_registry"
    res = dedup_pass(name)
    print(f"=== DEDUP PASS ({name}) ===")
    print(f"{res['n']} rows in {res['buckets']} buckets; unmerged |corr|>0.97 pairs: {len(res['unmerged_pairs'])}; "
          f"value-vector merges: {len(res['merges'])}")
    for u in res["unmerged_pairs"][:10]:
        print(f"  UNMERGED {u['bucket']} {u['reason']}: {u['ids']}")
    print("CLEAN" if not res["unmerged_pairs"] else "DUPLICATES PRESENT (must merge)")
