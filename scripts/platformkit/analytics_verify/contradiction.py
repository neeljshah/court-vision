"""Claims contradiction auditor.

Streams the verified-claims stores (data/cache/intel_claims/*.jsonl), normalizes
each ranking claim, and flags internal contradictions across families:
SIGN_CONFLICT, RANK_CONFLICT, VALUE_CONFLICT, STALE_PAIR (informational).
Descriptive/calibration language only -- never a $/ROI/edge claim. Read-only on
data/cache/intel_claims/. Stdlib only, memory-light: streams line-by-line and
retains only ONE canonical (latest) ranking per (family, metric, window).

Scoped limitations (see honest_note in the output report): windows compared by
EXACT string match only; each family capped at MAX_LINES_PER_FAMILY lines
(large per-entity-pointer stores republish the same ranking per pointer
entity, so a modest cap already reaches every distinct metric+window combo);
SIGN_CONFLICT = opposite arithmetic sign of value for the same
entity+metric+window (rate/skill values here, not directional forecasts).
"""
from __future__ import annotations

import argparse
import glob
import itertools
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

STORE_DIR_DEFAULT = "data/cache/intel_claims"
OUT_PATH_DEFAULT = "data/cache/analytics_verify/contradiction_report.json"
MAX_LINES_PER_FAMILY = 20000
VALUE_REL_THRESHOLD = 0.20
STALE_DAYS = 30
MAX_CONFLICTS_LISTED = 500

def _parse_dt(s: Any):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None

def discover_family_files(store_dir: str) -> list[str]:
    files = sorted(glob.glob(os.path.join(store_dir, "*.jsonl")))
    return [f for f in files if not f.endswith(".index.jsonl") and not f.endswith(".lock")]

def _read_first_record(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                return json.loads(line)
    except (OSError, json.JSONDecodeError):
        return None
    return None

def is_usable_schema(rec: dict | None) -> tuple[bool, str]:
    if rec is None:
        return False, "unreadable or empty"
    kind = rec.get("kind")
    if kind not in ("ranking", "descriptive"):
        return False, f"kind={kind!r} (expected ranking/descriptive)"
    if "criteria" not in rec or "claim_id" not in rec:
        return False, "missing criteria/claim_id"
    if kind == "ranking" and "ranking" not in rec and "claims" not in rec:
        return False, "ranking kind missing ranking/claims list"
    return True, "ok"

def _entity_key_fields(criteria: dict) -> tuple:
    ek = criteria.get("entity_key")
    if ek is None:
        return ()
    if isinstance(ek, str):
        return (ek,)
    return tuple(ek)

def _normalize_ranking(rec: dict, entity_fields: tuple) -> list[dict]:
    if rec.get("kind") == "descriptive":
        entity = tuple(rec.get(k) for k in entity_fields) if entity_fields else (rec.get("claim_id"),)
        val = rec.get("value")
        return [{"entity": entity, "value": val, "rank": 1}] if val is not None else []
    items = rec.get("ranking") or rec.get("claims") or []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        val = it.get("value")
        if val is None:
            continue
        if entity_fields:
            entity = tuple(it.get(k) for k in entity_fields)
        else:
            entity = (it.get("entity") or it.get("player_id") or it.get("team_id"),)
        out.append({"entity": entity, "value": val, "rank": it.get("rank")})
    return out

def stream_family(path: str, family: str, max_lines: int) -> dict[tuple, dict]:
    """Return {(metric, window): canonical latest-claim entry} for one family."""
    groups: dict[tuple, dict] = {}
    n = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            n += 1
            if n > max_lines:
                break
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("kind") not in ("ranking", "descriptive"):
                continue
            criteria = rec.get("criteria") or {}
            metric, window = criteria.get("metric"), criteria.get("window")
            if not metric or not window:
                continue
            key, computed_at = (metric, window), rec.get("computed_at")
            entry = groups.get(key)
            if entry is None:
                entity_fields = _entity_key_fields(criteria)
                groups[key] = {
                    "family": family, "claim_id": rec.get("claim_id"),
                    "computed_at_min": computed_at, "computed_at_max": computed_at,
                    "direction": criteria.get("direction"), "entity_fields": entity_fields,
                    "ranking": _normalize_ranking(rec, entity_fields),
                }
                continue
            if computed_at and (entry["computed_at_min"] is None or computed_at < entry["computed_at_min"]):
                entry["computed_at_min"] = computed_at
            if computed_at and (entry["computed_at_max"] is None or computed_at > entry["computed_at_max"]):
                entry["computed_at_max"] = computed_at
                entry["ranking"] = _normalize_ranking(rec, entry["entity_fields"])
                entry["claim_id"] = rec.get("claim_id")
    return groups

def _rank_of(ranking: list[dict]) -> dict:
    """entity -> (position 1-based, value)"""
    return {r["entity"]: (i + 1, r["value"]) for i, r in enumerate(ranking)}

def _stale_days(entry: dict) -> float | None:
    lo, hi = _parse_dt(entry["computed_at_min"]), _parse_dt(entry["computed_at_max"])
    return None if lo is None or hi is None else abs((hi - lo).total_seconds()) / 86400.0

def find_conflicts(comparable: dict[tuple, dict[str, dict]]) -> tuple[list[dict], dict]:
    conflicts: list[dict] = []
    counts = {"SIGN_CONFLICT": 0, "RANK_CONFLICT": 0, "VALUE_CONFLICT": 0, "STALE_PAIR": 0}
    n_pairs = 0

    def add(kind, entity, metric, window, fam_a, cid_a, fam_b, cid_b, detail):
        counts[kind] += 1
        if len(conflicts) < MAX_CONFLICTS_LISTED:
            conflicts.append({
                "kind": kind, "entity": entity, "metric": metric, "window": window,
                "family_a": fam_a, "claim_id_a": cid_a, "family_b": fam_b, "claim_id_b": cid_b,
                "detail": detail,
            })
    for (metric, window), by_family in comparable.items():
        for family, entry in by_family.items():
            spread = _stale_days(entry)
            if spread is not None and spread > STALE_DAYS:
                add("STALE_PAIR", entry["ranking"][0]["entity"] if entry["ranking"] else None,
                    metric, window, family, entry["claim_id"], family, entry["claim_id"],
                    f"computed_at spread {spread:.1f}d within family's own claim history")
        fams = list(by_family.keys())
        if len(fams) < 2:
            continue
        for fam_a, fam_b in itertools.combinations(fams, 2):
            n_pairs += 1
            ea, eb = by_family[fam_a], by_family[fam_b]
            ra, rb = ea["ranking"], eb["ranking"]
            if not ra or not rb:
                continue
            if ra[0]["entity"] != rb[0]["entity"]:
                add("RANK_CONFLICT", ra[0]["entity"], metric, window, fam_a, ea["claim_id"], fam_b, eb["claim_id"],
                    f"rank1 mismatch: {fam_a}={ra[0]['entity']!r} vs {fam_b}={rb[0]['entity']!r}")
            pos_a, pos_b = _rank_of(ra), _rank_of(rb)
            common = set(pos_a) & set(pos_b)
            list_len = max(len(ra), len(rb))
            for entity in common:
                (rank_a, val_a), (rank_b, val_b) = pos_a[entity], pos_b[entity]
                if abs(rank_a - rank_b) > list_len / 2.0:
                    add("RANK_CONFLICT", entity, metric, window, fam_a, ea["claim_id"], fam_b, eb["claim_id"],
                        f"rank {rank_a} vs {rank_b} (list_len={list_len})")
                try:
                    va, vb = float(val_a), float(val_b)
                except (TypeError, ValueError):
                    continue
                if va != 0 and vb != 0 and (va > 0) != (vb > 0):
                    add("SIGN_CONFLICT", entity, metric, window, fam_a, ea["claim_id"], fam_b, eb["claim_id"],
                        f"value {va} vs {vb} (opposite sign)")
                rel = abs(va - vb) / max(abs(va), abs(vb), 1e-9)
                if rel > VALUE_REL_THRESHOLD:
                    add("VALUE_CONFLICT", entity, metric, window, fam_a, ea["claim_id"], fam_b, eb["claim_id"],
                        f"value {va} vs {vb} (rel diff {rel:.2%})")

            cross_spread_a, cross_spread_b = ea["computed_at_max"], eb["computed_at_max"]
            dta, dtb = _parse_dt(cross_spread_a), _parse_dt(cross_spread_b)
            if dta and dtb and abs((dta - dtb).total_seconds()) / 86400.0 > STALE_DAYS:
                add("STALE_PAIR", None, metric, window, fam_a, ea["claim_id"], fam_b, eb["claim_id"],
                    f"cross-family computed_at gap {abs((dta - dtb).days)}d")

    return conflicts, {"counts": counts, "n_comparable_pairs": n_pairs}

def run(store_dir: str = STORE_DIR_DEFAULT, out_path: str = OUT_PATH_DEFAULT,
        max_lines: int = MAX_LINES_PER_FAMILY) -> dict:
    files = discover_family_files(store_dir)
    families_scanned: list[str] = []
    families_skipped: list[dict] = []
    comparable: dict[tuple, dict[str, dict]] = {}
    n_claims = 0

    for path in files:
        family = os.path.basename(path)[: -len(".jsonl")]
        first = _read_first_record(path)
        usable, reason = is_usable_schema(first)
        if not usable:
            families_skipped.append({"family": family, "reason": reason})
            continue
        groups = stream_family(path, family, max_lines)
        families_scanned.append(family)
        n_claims += len(groups)
        for key, entry in groups.items():
            comparable.setdefault(key, {})[family] = entry

    conflicts, stats = find_conflicts(comparable)
    counts = stats["counts"]

    by_family_consistency: dict[str, dict] = {}
    for (metric, window), by_family in comparable.items():
        size = len(by_family)
        for family in by_family:
            rec = by_family_consistency.setdefault(family, {"n_claims": 0, "n_conflicts": 0, "n_pairs": 0})
            rec["n_claims"] += 1
            rec["n_pairs"] += max(size - 1, 0) + 1  # +1 for its own stale self-check
    for c in conflicts:
        for fam in (c["family_a"], c["family_b"]):
            if fam in by_family_consistency:
                by_family_consistency[fam]["n_conflicts"] += 1
    for family, rec in by_family_consistency.items():
        rec["consistency"] = round(1.0 - rec["n_conflicts"] / max(rec["n_pairs"], 1), 4)

    n_index_files = len(glob.glob(os.path.join(store_dir, "*.index.jsonl")))
    total_jsonl = len(glob.glob(os.path.join(store_dir, "*.jsonl")))
    non_index_total = total_jsonl - n_index_files
    coverage = round(len(families_scanned) / max(non_index_total, 1), 4)

    report = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "edge_claimed": False,
        "honest_note": (
            "DESCRIPTIVE consistency audit only -- no market/$ edge claimed. Windows compared "
            f"by exact string match only. Each family capped at {max_lines} lines (large "
            "per-entity-pointer stores republish the same ranking per pointer entity; the cap "
            "reaches every distinct metric+window combo near the top of the file but does not "
            "guarantee full-file coverage). Only the LATEST snapshot per (family, metric, window) "
            "feeds SIGN/RANK/VALUE conflicts; historical snapshots inform STALE_PAIR spread only. "
            "SIGN_CONFLICT = opposite arithmetic sign of value for the same entity+metric+window. "
            f"Schema coverage: {len(families_scanned)}/{non_index_total} non-index claim families "
            f"usable ({coverage:.0%}); {n_index_files} *.index.jsonl pointer files and "
            f"{len(families_skipped)} schema-mismatched files excluded."
        ),
        "families_scanned": sorted(families_scanned),
        "families_skipped": families_skipped,
        "n_claims": n_claims,
        "n_comparable_pairs": stats["n_comparable_pairs"],
        "conflicts": conflicts,
        "by_family_consistency": by_family_consistency,
        "n_conflicts_by_kind": counts,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(out_path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    os.replace(tmp, out_path)

    print(
        f"contradiction_report: families={len(families_scanned)}/{non_index_total} "
        f"claims={n_claims} pairs={stats['n_comparable_pairs']} "
        f"conflicts={sum(counts.values())} "
        f"(sign={counts['SIGN_CONFLICT']} rank={counts['RANK_CONFLICT']} "
        f"value={counts['VALUE_CONFLICT']} stale={counts['STALE_PAIR']}) -> {out_path}"
    )
    return report

def main() -> None:
    ap = argparse.ArgumentParser(description="Claims contradiction auditor")
    ap.add_argument("--store-dir", default=STORE_DIR_DEFAULT)
    ap.add_argument("--out", default=OUT_PATH_DEFAULT)
    ap.add_argument("--max-lines-per-family", type=int, default=MAX_LINES_PER_FAMILY)
    args = ap.parse_args()
    run(args.store_dir, args.out, args.max_lines_per_family)

if __name__ == "__main__":
    main()
