"""scripts.platformkit.clv_ledger_canonical_index -- non-destructive dup-cluster index.

LANE-4 LEDGER HYGIENE (queue item 4): ledger_health (clv_ledger_sanity.scan_ledger)
reports a "duplicates" count keyed on a COARSE fallback key
(game_id|market|side|status|venue|date, where game_id falls back to matchup and
date falls back to a possibly-blank game_date/date field). That coarse key
conflates DISTINCT real bets that happen to share a recurring team-matchup label
across a season series or across daily in-game re-checks of an open contract.

This module NEVER rewrites the ledger (charter forbids deleting/mutating rows).
It builds a READ-THROUGH canonical-row index as a sidecar artifact:

  * canonical identity: prefer bet_id|status (pregame path); else edge_key|status
    (in-game path, which carries a per-day edge_key even when bet_id is absent);
    else fall back to the sanity checker's own coarse key so every row is still
    covered.
  * within a canonical-identity cluster of size > 1 (a GENUINE collision), pick
    the canonical row by: first-written wins (lowest ts / file order), UNLESS a
    later row is STRICTLY MORE COMPLETE (has a non-null clv_pct/clv_status where
    the earlier one is null/no_close) -- then the more-complete row wins. Ties
    keep first-written.
  * emit a dup_row -> canonical_row map (by 0-based line index into the ledger
    file) plus per-cluster metadata, so a consumer can read through the index
    without ever touching the on-disk ledger.

Also reports how many of the checker's coarse-key clusters are FALSE POSITIVES
(members have distinct canonical identity -- different real bets) vs TRUE
collisions (members share canonical identity -- genuine dup writes), as the
honest explanation for why raw dup_count will not move.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no secrets; read-only
over the ledger (never writes data/frontend/clv_ledger.jsonl); no $ field.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_ledger_canonical_index.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.platformkit.clv_ledger_sanity import _dup_key as _coarse_dup_key
from scripts.platformkit.clv_ledger_sanity import _raw_load

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_LEDGER = _REPO_ROOT / "data" / "frontend" / "clv_ledger.jsonl"
_DEFAULT_OUT = _REPO_ROOT / "data" / "frontend" / "ops" / "clv_ledger_canonical_index.json"

INDEX_VERSION = "clv_ledger_canonical_index.v1"


def _canonical_key(row: Dict[str, Any]) -> Tuple[str, ...]:
    """Best-available true identity for one row, status-folded.

    Priority: bet_id -> edge_key -> coarse sanity key (last resort, only reached
    when a row has neither -- keeps every row indexed, never dropped).
    """
    status = str(row.get("status") or "")
    bid = row.get("bet_id")
    if bid:
        return ("bid", str(bid), status)
    ek = row.get("edge_key")
    if ek:
        return ("ek", str(ek), status)
    return ("coarse", _coarse_dup_key(row))


def _completeness_score(row: Dict[str, Any]) -> int:
    """Higher = more complete. A row with a real CLV outranks a no_close row."""
    score = 0
    if row.get("clv_pct") is not None:
        score += 2
    status = row.get("clv_status")
    if status not in (None, "no_close", "INSUFFICIENT_DATA"):
        score += 1
    if row.get("outcome") is not None:
        score += 1
    return score


def build_index(path: Optional[Path] = None) -> Dict[str, Any]:
    """Build the canonical-row index. READ-ONLY; never mutates the ledger.

    Returns a dict with:
      version, ledger_path, total_rows,
      canonical_clusters   -- count of true-identity clusters with >1 member,
      dup_row_to_canonical -- {str(dup_line_idx): canonical_line_idx},
      clusters             -- [{key, canonical_idx, member_idxs, rule}],
      coarse_report        -- reconciliation against clv_ledger_sanity's coarse
                              dup count: n_coarse_clusters, n_false_positive
                              (distinct canonical identity within the coarse
                              cluster -- NOT a real dup), n_true_collision.
    """
    p = Path(path) if path is not None else _DEFAULT_LEDGER
    if not p.exists() or p.stat().st_size == 0:
        return {
            "version": INDEX_VERSION,
            "status": "INSUFFICIENT_DATA",
            "ledger_path": str(p),
            "total_rows": 0,
            "canonical_clusters": 0,
            "dup_row_to_canonical": {},
            "clusters": [],
            "coarse_report": {"n_coarse_clusters": 0, "n_false_positive": 0,
                              "n_true_collision": 0, "extra_rows_coarse": 0,
                              "extra_rows_canonical": 0},
        }
    rows = _raw_load(p)

    # Group by canonical (true) identity.
    by_canon: Dict[Tuple[str, ...], List[int]] = {}
    for idx, row in enumerate(rows):
        by_canon.setdefault(_canonical_key(row), []).append(idx)

    dup_row_to_canonical: Dict[str, int] = {}
    clusters: List[Dict[str, Any]] = []
    extra_rows_canonical = 0
    for key, idxs in by_canon.items():
        if len(idxs) <= 1:
            continue
        extra_rows_canonical += len(idxs) - 1
        # Rule: first-written wins UNLESS a later row is strictly more complete.
        canonical_idx = idxs[0]
        best_score = _completeness_score(rows[canonical_idx])
        rule = "first_written"
        for i in idxs[1:]:
            sc = _completeness_score(rows[i])
            if sc > best_score:
                canonical_idx = i
                best_score = sc
                rule = "more_complete_row"
        for i in idxs:
            if i != canonical_idx:
                dup_row_to_canonical[str(i)] = canonical_idx
        clusters.append({
            "key": "|".join(key),
            "canonical_idx": canonical_idx,
            "member_idxs": idxs,
            "rule": rule,
        })

    # Reconcile against the checker's coarse key: for each coarse cluster,
    # is it a real (canonical) collision or a false positive?
    by_coarse: Dict[str, List[int]] = {}
    for idx, row in enumerate(rows):
        by_coarse.setdefault(_coarse_dup_key(row), []).append(idx)

    n_false_positive = 0
    n_true_collision = 0
    extra_rows_coarse = 0
    for coarse_key, idxs in by_coarse.items():
        if len(idxs) <= 1:
            continue
        extra_rows_coarse += len(idxs) - 1
        canon_ids = {_canonical_key(rows[i]) for i in idxs}
        if len(canon_ids) == 1:
            n_true_collision += 1
        else:
            n_false_positive += 1

    return {
        "version": INDEX_VERSION,
        "status": "ok",
        "ledger_path": str(p),
        "total_rows": len(rows),
        "canonical_clusters": len(clusters),
        "dup_row_to_canonical": dup_row_to_canonical,
        "clusters": clusters,
        "coarse_report": {
            "n_coarse_clusters": sum(1 for v in by_coarse.values() if len(v) > 1),
            "n_false_positive": n_false_positive,
            "n_true_collision": n_true_collision,
            "extra_rows_coarse": extra_rows_coarse,
            "extra_rows_canonical": extra_rows_canonical,
        },
        "honest_note": (
            "calibration not edge; read-only index; ledger file never rewritten; "
            "dup_row_to_canonical keys/values are 0-based line indexes into "
            "ledger_path at build time"
        ),
    }


def write_index(path: Optional[Path] = None, out: Optional[Path] = None) -> Dict[str, Any]:
    """Build the index and persist it to *out* (default data/frontend/ops/...).

    Returns the built index dict. Creates parent dirs as needed. Never touches
    the ledger file itself.
    """
    result = build_index(path)
    target = Path(out) if out is not None else _DEFAULT_OUT
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=True, default=str)
    return result


def _main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Build the read-only CLV ledger canonical-row dedup index."
    )
    ap.add_argument("--ledger", default=None, help="override ledger path")
    ap.add_argument("--out", default=None, help="override output artifact path")
    a = ap.parse_args(list(argv) if argv is not None else None)
    res = write_index(
        Path(a.ledger) if a.ledger else None,
        Path(a.out) if a.out else None,
    )
    print(json.dumps(
        {k: v for k, v in res.items() if k not in ("clusters", "dup_row_to_canonical")},
        indent=2, ensure_ascii=True,
    ))
    return 0


__all__ = ["build_index", "write_index", "INDEX_VERSION"]

if __name__ == "__main__":
    raise SystemExit(_main())
