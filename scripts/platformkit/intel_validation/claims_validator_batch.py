"""Batch/vectorized + memory-bounded claims recompute + validation (spec
sec 3, additive). Split out of claims_validator.py for the <=300 LOC/file
rail; re-exported as `claims_validator.validate_claims_file_batched`.

Never weakens the honest per-claim path: `validate_claim`/`validate_claims_file`
in claims_validator.py are UNCHANGED ground truth. This module groups claims
sharing a recompute key -- (source_files, formula, window, entity_key,
direction, value_precision, min_sample, aggregate, window_spec) -- so each
group's snapshot loads ONCE and its formula evaluates ONCE (vectorized), and
streams the input jsonl by byte offset (docstring below) so the whole file
is never held parsed in RAM. Verdicts are byte-for-byte identical to looping
(parity test in test_claims_validator.py). CLI: none -- imported only.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from scripts.platformkit.intel_validation.aggregate_recompute import recompute_aggregate
from scripts.platformkit.intel_validation.claims_validator import (
    ClaimVerdict,
    FormulaError,
    ValidationSummary,
    TOLERANCE,
    _apply_min_sample_floors,
    _entity_id_str,
    _entity_key,
    _load_source_frame,
)
from scripts.platformkit.intel_validation.safe_formula import evaluate_formula_vectorized


def _recompute_group(
    df: pd.DataFrame,
    criteria: dict[str, Any],
    entity_key: Any,
    min_sample: dict[str, Any],
) -> tuple[pd.DataFrame | None, Any, int, str | None]:
    """SAME recompute rule as `validate_claim`'s inline logic, but the plain
    (non-aggregate) branch uses `evaluate_formula_vectorized` (one pass per
    group, not one `.apply` per claim); aggregate branch unchanged (already
    groupby-vectorized). Returns (recomputed_df_or_None, id_col, n_excluded,
    error_reason_or_None)."""
    formula = criteria.get("formula")
    if criteria.get("aggregate"):
        try:
            table = recompute_aggregate(df, criteria)
            recomputed, n_excluded = _apply_min_sample_floors(table, min_sample)
        except FormulaError as e:
            return None, None, 0, f"aggregate recompute error: {e}"
        except Exception as e:  # noqa: BLE001 -- fail closed, never silently skip
            return None, None, 0, f"aggregate recompute error: {e}"
        # Zero/non-finite denominator entities never enter a ranking -- SAME
        # fix as claims_validator.py's inline aggregate branch (parity is
        # this module's contract, see module docstring).
        finite_mask = np.isfinite(recomputed["_value"].astype(float))
        n_excluded += int((~finite_mask).sum())
        recomputed = recomputed[finite_mask]
        id_col = criteria["aggregate"]["group_by"]
        if id_col != entity_key:
            return None, None, 0, (
                f"entity_key={entity_key!r} does not match aggregate.group_by={id_col!r}"
            )
        return recomputed, id_col, n_excluded, None

    try:
        filtered, n_excluded = _apply_min_sample_floors(df, min_sample)
    except FormulaError as e:
        return None, None, 0, f"min_sample floor error: {e}"

    if filtered.empty:
        return None, None, 0, "no rows survive min_sample floors"

    try:
        values = evaluate_formula_vectorized(formula, filtered)
    except FormulaError as e:
        return None, None, 0, f"formula not executable: {e}"
    except Exception as e:  # noqa: BLE001 -- fail closed as UNVERIFIABLE, never silently skip
        return None, None, 0, f"formula evaluation error: {e}"

    recomputed = filtered.copy()
    recomputed["_value"] = values
    key_cols = entity_key if isinstance(entity_key, list) else [entity_key]
    if not all(c in recomputed.columns for c in key_cols):
        return None, None, 0, f"no {entity_key!r} column(s) in source data"
    return recomputed, entity_key, n_excluded, None


def _compare_claim_to_recomputed(
    claim: dict[str, Any],
    criteria: dict[str, Any],
    recomputed: pd.DataFrame,
    entity_key: Any,
    id_col: Any,
    n_excluded: int,
) -> ClaimVerdict:
    """IDENTICAL tolerance/MISMATCH/n_excluded_below_floor rule as
    `validate_claim`'s inline compare loop, run once per claim against a
    recompute already built by `_recompute_group` (shared across the group).
    Sorting happens here (cheap, per-group) -- direction/value_precision are
    part of the group key, so every claim in a group agrees on the sort."""
    claim_id = claim.get("claim_id", "<missing-id>")
    metric = criteria.get("metric")
    min_sample = criteria.get("min_sample", {}) or {}
    direction = criteria.get("direction", "desc")
    claimed_ranking = claim.get("ranking", [])

    ascending = direction == "asc"
    recomputed = recomputed.sort_values("_value", ascending=ascending).reset_index(drop=True)

    for claimed_row in sorted(claimed_ranking, key=lambda r: r["rank"]):
        rank = claimed_row["rank"]
        idx = rank - 1
        if idx < 0 or idx >= len(recomputed):
            return ClaimVerdict(
                claim_id,
                "MISMATCH",
                reason=f"claimed rank {rank} exceeds recomputed pool size {len(recomputed)}",
                first_divergence={"rank": rank, "claimed": claimed_row, "recomputed": None},
            )
        recomputed_row = recomputed.iloc[idx]
        if isinstance(id_col, list):
            recomputed_id = _entity_id_str({c: recomputed[c].iloc[idx] for c in id_col}, id_col)
            claimed_id = _entity_id_str(claimed_row, id_col)
        else:
            recomputed_id = recomputed[id_col].iloc[idx]
            claimed_id = claimed_row.get(entity_key)
        if str(recomputed_id) != str(claimed_id):
            return ClaimVerdict(
                claim_id,
                "MISMATCH",
                reason=f"rank {rank}: claimed {entity_key}={claimed_id} recomputed {entity_key}={recomputed_id}",
                first_divergence={
                    "rank": rank,
                    "claimed": claimed_row,
                    "recomputed": {str(entity_key): recomputed_id, "value": float(recomputed_row["_value"])},
                },
            )
        recomputed_value = float(recomputed_row["_value"])
        precision = criteria.get("value_precision")
        if precision is not None:
            recomputed_value = round(recomputed_value, int(precision))
        claimed_value = float(claimed_row.get("value", math.nan))
        if math.isnan(claimed_value) or abs(recomputed_value - claimed_value) > TOLERANCE:
            return ClaimVerdict(
                claim_id,
                "MISMATCH",
                reason=(
                    f"rank {rank}: claimed value={claimed_value} recomputed value={recomputed_value} "
                    f"(tolerance={TOLERANCE})"
                ),
                first_divergence={
                    "rank": rank,
                    "claimed": claimed_row,
                    "recomputed": {str(entity_key): recomputed_id, "value": recomputed_value},
                },
            )
        claimed_n = claimed_row.get("n")
        if claimed_n is not None:
            for col, floor in min_sample.items():
                if col in recomputed_row and recomputed_row[col] < floor:
                    return ClaimVerdict(
                        claim_id,
                        "MISMATCH",
                        reason=f"rank {rank}: min_sample floor violated for column {col!r}",
                        first_divergence={"rank": rank, "claimed": claimed_row, "recomputed": None},
                    )

    claimed_n_excluded = claim.get("n_excluded_below_floor")
    if claimed_n_excluded is not None and int(claimed_n_excluded) != int(n_excluded):
        return ClaimVerdict(
            claim_id,
            "MISMATCH",
            reason=f"n_excluded_below_floor claimed={claimed_n_excluded} recomputed={n_excluded}",
            first_divergence={
                "rank": None,
                "claimed": {"n_excluded_below_floor": claimed_n_excluded},
                "recomputed": {"n_excluded_below_floor": n_excluded},
            },
        )

    return ClaimVerdict(claim_id, "VERIFIED", reason=f"metric={metric} matched within tolerance")


def _recompute_key(claim: dict[str, Any]) -> tuple:
    """Claims sharing this key share ONE snapshot load + ONE recompute:
    (source_files, formula, window, entity_key, direction, value_precision,
    min_sample), plus `aggregate`/`window_spec` folded in as sorted-json
    strings so two claims only ever share a group when `_recompute_group`
    would produce the identical recompute for both."""
    criteria = claim.get("criteria", {})
    entity_key = _entity_key(criteria)
    entity_key_t = tuple(entity_key) if isinstance(entity_key, list) else entity_key
    min_sample = criteria.get("min_sample", {}) or {}
    return (
        tuple(claim.get("source_files", [])),
        criteria.get("formula"),
        criteria.get("window"),
        entity_key_t,
        criteria.get("direction", "desc"),
        criteria.get("value_precision"),
        frozenset(min_sample.items()),
        json.dumps(criteria.get("aggregate"), sort_keys=True),
        json.dumps(criteria.get("window_spec"), sort_keys=True),
    )


def _read_claim_at(f, offset: int) -> dict[str, Any]:
    """Seek + parse exactly one claim line from an already-open text file."""
    f.seek(offset)
    return json.loads(f.readline())


def _mark_group_unverifiable(f, group_positions: list, results: dict[int, ClaimVerdict], reason: str) -> None:
    for idx, group_offset in group_positions:
        claim = _read_claim_at(f, group_offset)
        results[idx] = ClaimVerdict(claim.get("claim_id", "<missing-id>"), "UNVERIFIABLE", reason=reason)


def validate_claims_file_batched(path) -> ValidationSummary:
    """ADDITIVE fast path (spec sec 3): SAME per-claim verdict as looping
    `claims_validator.validate_claim` (parity test), but claims sharing a
    recompute key load their snapshot + evaluate their formula ONCE per group.

    STREAMING two-pass by byte offset, so a several-hundred-MB claims jsonl
    never sits fully parsed in RAM: pass 1 streams line-by-line, computes
    each claim's recompute key (or its immediate UNVERIFIABLE verdict), and
    records only its byte offset under that key (first-seen group order),
    dropping the parsed claim; pass 2 re-seeks and re-parses ONLY one
    group's lines at a time, loads its source frame once, recomputes once,
    compares, then discards before the next group. Peak memory is O(largest
    group + one source frame). Details reassembled by original line index."""
    summary = ValidationSummary(generated_at=datetime.now(timezone.utc).isoformat())
    n_lines = 0
    results: dict[int, ClaimVerdict] = {}
    groups: dict[tuple, list[tuple[int, int]]] = {}  # key -> [(line_idx, byte_offset), ...]

    with open(path, "r", encoding="ascii", errors="strict") as f:
        offset = f.tell()
        line = f.readline()
        while line:
            stripped = line.strip()
            if not stripped:
                offset = f.tell()
                line = f.readline()
                continue
            claim = json.loads(stripped)
            idx = n_lines
            n_lines += 1
            if claim.get("kind") in ("gate_verdict", "verdict"):
                # SAME dispatch as claims_validator.validate_claim (parity is
                # this module's contract): verdict-kind claims check against
                # their cited verdict_file, never the formula recompute path.
                from scripts.platformkit.intel_validation.verdict_claim_check import validate_verdict_claim
                results[idx] = validate_verdict_claim(claim)
            elif not claim.get("criteria", {}).get("formula"):
                results[idx] = ClaimVerdict(
                    claim.get("claim_id", "<missing-id>"), "UNVERIFIABLE", reason="criteria.formula missing"
                )
            else:
                groups.setdefault(_recompute_key(claim), []).append((idx, offset))
            offset = f.tell()
            line = f.readline()

        for group_positions in groups.values():
            first_claim = _read_claim_at(f, group_positions[0][1])
            criteria = first_claim.get("criteria", {})
            entity_key = _entity_key(criteria)
            min_sample = criteria.get("min_sample", {}) or {}
            source_files = first_claim.get("source_files", [])

            try:
                df = _load_source_frame(source_files)
            except FileNotFoundError as e:
                _mark_group_unverifiable(f, group_positions, results, f"source file missing: {e}")
                continue

            recomputed, id_col, n_excluded, err = _recompute_group(df, criteria, entity_key, min_sample)
            if err is not None:
                _mark_group_unverifiable(f, group_positions, results, err)
                continue

            for idx, group_offset in group_positions:
                claim = _read_claim_at(f, group_offset)
                results[idx] = _compare_claim_to_recomputed(
                    claim, claim.get("criteria", {}), recomputed, entity_key, id_col, n_excluded
                )
            del df, recomputed

    for idx in range(n_lines):
        verdict = results[idx]
        summary.n_claims += 1
        if verdict.verdict == "VERIFIED":
            summary.n_verified += 1
        elif verdict.verdict == "MISMATCH":
            summary.n_mismatch += 1
        else:
            summary.n_unverifiable += 1
        summary.details.append(
            {
                "claim_id": verdict.claim_id,
                "verdict": verdict.verdict,
                "reason": verdict.reason,
                "first_divergence": verdict.first_divergence,
            }
        )
    return summary
