"""Independent claims validator (Lane B).

Reads claim rows in the SHARED CLAIMS CONTRACT JSONL shape, independently
recomputes each ranking claim's metric straight from its declared
source_files + criteria.formula using pandas (no import of the producer
module), and reports VERIFIED / MISMATCH / UNVERIFIABLE per claim.

criteria.entity_key names the ranking-entity id column (defaults to
'player_id' for back-compat) so non-basketball sports can publish ranking
claims keyed on e.g. pitcher_id / team_id through the SAME contract.

CLI:
    python -m scripts.platformkit.intel_validation.claims_validator <claims.jsonl>
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts.platformkit.intel_validation.aggregate_recompute import recompute_aggregate
from scripts.platformkit.intel_validation.safe_formula import FormulaError, evaluate_formula

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = REPO_ROOT / "data" / "frontend" / "ops" / "intel_claims_validation.json"
TOLERANCE = 1e-9 * 10  # "1e-9-ish" per spec; guards against float round-trip noise


@dataclass
class ClaimVerdict:
    claim_id: str
    verdict: str  # VERIFIED | MISMATCH | UNVERIFIABLE
    reason: str = ""
    first_divergence: dict[str, Any] | None = None


@dataclass
class ValidationSummary:
    component: str = "intel_claims_validation"
    generated_at: str = ""
    n_claims: int = 0
    n_verified: int = 0
    n_mismatch: int = 0
    n_unverifiable: int = 0
    edge_claimed: bool = False
    details: list[dict[str, Any]] = field(default_factory=list)


def _load_claims(path: Path) -> list[dict[str, Any]]:
    rows = []
    with open(path, "r", encoding="ascii", errors="strict") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _load_source_frame(source_files: list[str]) -> pd.DataFrame:
    """Load and concat all declared parquet source files, relative to repo root."""
    frames = []
    for rel in source_files:
        p = REPO_ROOT / rel
        if not p.exists():
            raise FileNotFoundError(str(rel))
        frames.append(pd.read_parquet(p))
    if not frames:
        raise FileNotFoundError("no source_files declared")
    return pd.concat(frames, ignore_index=True)


def _apply_min_sample_floors(df: pd.DataFrame, min_sample: dict[str, Any]) -> tuple[pd.DataFrame, int]:
    """Apply column >= floor filters. Returns (filtered_df, n_excluded)."""
    before = len(df)
    mask = pd.Series(True, index=df.index)
    for col, floor in min_sample.items():
        if col not in df.columns:
            raise FormulaError(f"min_sample column not present: {col!r}")
        mask &= df[col] >= floor
    filtered = df[mask]
    return filtered, before - len(filtered)


def _entity_key(claim_or_criteria: dict[str, Any]) -> Any:
    """criteria.entity_key names the ranking-entity id column (e.g.
    player_id / pitcher_id / team_id). Defaults to 'player_id' for
    back-compat with every claim published before this field existed.
    ALSO accepts a LIST of columns (e.g. [p1_id, p2_id]) for pair-keyed
    entities (e.g. tennis H2H); the scalar path is unchanged."""
    return claim_or_criteria.get("entity_key", "player_id")


def _native(x: Any) -> Any:
    """numpy scalar -> native python. numpy>=2 reprs np.int64(1) inside a
    tuple, so str(tuple) comparison false-mismatched identical ids (caught
    2026-07-18: wnba_lineup rank-1 'mismatch' with byte-identical values)."""
    return x.item() if hasattr(x, "item") else x


def _entity_id_str(row: Any, entity_key: Any) -> str:
    """Stringify the entity id for comparison. entity_key list -> tuple of
    the named columns (pair-keyed); scalar -> the single column value."""
    if isinstance(entity_key, list):
        return str(tuple(_native(row[c]) for c in entity_key))
    return str(_native(row[entity_key]))


def validate_claim(claim: dict[str, Any]) -> ClaimVerdict:
    claim_id = claim.get("claim_id", "<missing-id>")
    if claim.get("kind") in ("gate_verdict", "verdict"):
        # Non-ranking verdict claims verify against their cited verdict_file
        # artifact instead of a formula recompute (checker lives in
        # verdict_claim_check.py -- this module is over the LOC cap already).
        from scripts.platformkit.intel_validation.verdict_claim_check import validate_verdict_claim
        return validate_verdict_claim(claim)
    criteria = claim.get("criteria", {})
    formula = criteria.get("formula")
    metric = criteria.get("metric")
    min_sample = criteria.get("min_sample", {}) or {}
    direction = criteria.get("direction", "desc")
    source_files = claim.get("source_files", [])
    claimed_ranking = claim.get("ranking", [])
    entity_key = _entity_key(criteria)

    if not formula:
        return ClaimVerdict(claim_id, "UNVERIFIABLE", reason="criteria.formula missing")

    try:
        df = _load_source_frame(source_files)
    except FileNotFoundError as e:
        return ClaimVerdict(claim_id, "UNVERIFIABLE", reason=f"source file missing: {e}")

    if criteria.get("aggregate"):
        # Contract-extension path: floors + formula apply to PER-GROUP DERIVED
        # columns recomputed from raw rows via the declared aggregate grammar.
        try:
            table = recompute_aggregate(df, criteria)
            recomputed, n_excluded = _apply_min_sample_floors(table, min_sample)
        except FormulaError as e:
            return ClaimVerdict(claim_id, "UNVERIFIABLE", reason=f"aggregate recompute error: {e}")
        except Exception as e:  # noqa: BLE001 -- fail closed, never silently skip
            return ClaimVerdict(claim_id, "UNVERIFIABLE", reason=f"aggregate recompute error: {e}")
        # Zero/non-finite denominator entities (e.g. ast_to_tov with
        # sum(tov)==0) never enter a ranking -- same honest-exclusion idiom
        # the producer applies (claims_factory._build_dim_claim), folded
        # into the same n_excluded count so the independent recompute stays
        # consistent with what a non-NaN-emitting producer would publish.
        finite_mask = np.isfinite(recomputed["_value"].astype(float))
        n_excluded += int((~finite_mask).sum())
        recomputed = recomputed[finite_mask]
        id_col = criteria["aggregate"]["group_by"]
        if id_col != entity_key:
            return ClaimVerdict(
                claim_id, "UNVERIFIABLE",
                reason=f"entity_key={entity_key!r} does not match aggregate.group_by={id_col!r}",
            )
        # An empty survivors table with an empty claimed ranking is an honest
        # floor-driven empty result -- verified via the n_excluded check below.
    else:
        try:
            filtered, n_excluded = _apply_min_sample_floors(df, min_sample)
        except FormulaError as e:
            return ClaimVerdict(claim_id, "UNVERIFIABLE", reason=f"min_sample floor error: {e}")

        if filtered.empty:
            return ClaimVerdict(claim_id, "UNVERIFIABLE", reason="no rows survive min_sample floors")

        try:
            values = evaluate_formula(formula, filtered)
        except FormulaError as e:
            return ClaimVerdict(claim_id, "UNVERIFIABLE", reason=f"formula not executable: {e}")
        except Exception as e:  # noqa: BLE001 -- fail closed as UNVERIFIABLE, never silently skip
            return ClaimVerdict(claim_id, "UNVERIFIABLE", reason=f"formula evaluation error: {e}")

        recomputed = filtered.copy()
        recomputed["_value"] = values
        key_cols = entity_key if isinstance(entity_key, list) else [entity_key]
        if not all(c in recomputed.columns for c in key_cols):
            return ClaimVerdict(claim_id, "UNVERIFIABLE", reason=f"no {entity_key!r} column(s) in source data")
        id_col = entity_key

    ascending = direction == "asc"
    recomputed = recomputed.sort_values("_value", ascending=ascending).reset_index(drop=True)

    # Compare rank-by-rank against the claimed ranking.
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
        # take the id from the COLUMN(S), not the row Series -- a mixed-dtype
        # row gets upcast to float64, which would corrupt int64 ids (1630198.0)
        if isinstance(id_col, list):
            recomputed_id = _entity_id_str({c: recomputed[c].iloc[idx] for c in id_col}, id_col)
            claimed_id = _entity_id_str(claimed_row, id_col)
        else:
            recomputed_id = recomputed[id_col].iloc[idx]
            claimed_id = claimed_row.get(entity_key)
        # allow int/str id mismatch (e.g. 101 vs "101") but not a different entity
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
            # The contract declares claimed values rounded to this many decimal
            # places; round the recompute identically before the tight compare.
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

    # Also check the claimed n_excluded_below_floor if present.
    claimed_n_excluded = claim.get("n_excluded_below_floor")
    if claimed_n_excluded is not None and int(claimed_n_excluded) != int(n_excluded):
        return ClaimVerdict(
            claim_id,
            "MISMATCH",
            reason=(
                f"n_excluded_below_floor claimed={claimed_n_excluded} recomputed={n_excluded}"
            ),
            first_divergence={
                "rank": None,
                "claimed": {"n_excluded_below_floor": claimed_n_excluded},
                "recomputed": {"n_excluded_below_floor": n_excluded},
            },
        )

    return ClaimVerdict(claim_id, "VERIFIED", reason=f"metric={metric} matched within tolerance")


def validate_claims_file(path: Path) -> ValidationSummary:
    claims = _load_claims(path)
    summary = ValidationSummary(generated_at=datetime.now(timezone.utc).isoformat())
    for claim in claims:
        verdict = validate_claim(claim)
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


def _json_numpy_default(obj: Any) -> Any:
    """json.dump default= hook: a MISMATCH first_divergence block can carry a
    raw numpy scalar straight off a pandas column (e.g. recomputed_id from an
    int64 entity_key column) -- convert it to the equivalent Python int/float
    instead of crashing with TypeError. No other type is special-cased."""
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def write_summary(summary: ValidationSummary, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "component": summary.component,
        "generated_at": summary.generated_at,
        "n_claims": summary.n_claims,
        "n_verified": summary.n_verified,
        "n_mismatch": summary.n_mismatch,
        "n_unverifiable": summary.n_unverifiable,
        "edge_claimed": summary.edge_claimed,
        "details": summary.details,
    }
    # The predictive_validity stamp (predictive_validity/artifacts.py) lives in
    # this same file and is produced by a DIFFERENT, slower pipeline -- carry it
    # over so every re-validation cycle (the pod loop rewrites these every 20
    # min) does not silently clobber it.
    try:
        prior = json.loads(output_path.read_text(encoding="ascii"))
        if isinstance(prior, dict) and "predictive_validity" in prior:
            payload["predictive_validity"] = prior["predictive_validity"]
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    with open(output_path, "w", encoding="ascii", errors="strict") as f:
        json.dump(payload, f, indent=2, default=_json_numpy_default)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independent intel claims validator")
    parser.add_argument("claims_jsonl", type=str, help="path to claims JSONL file")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    claims_path = Path(args.claims_jsonl)
    if not claims_path.exists():
        print(f"UNVERIFIABLE: claims file not found: {claims_path}")
        return 1

    summary = validate_claims_file(claims_path)
    write_summary(summary, Path(args.output))

    print(
        f"n_claims={summary.n_claims} verified={summary.n_verified} "
        f"mismatch={summary.n_mismatch} unverifiable={summary.n_unverifiable}"
    )
    for d in summary.details:
        print(f"  {d['claim_id']}: {d['verdict']} -- {d['reason']}")
    return 0 if summary.n_mismatch == 0 else 2


if __name__ == "__main__":
    sys.exit(main())


def validate_claims_file_batched(path: Path) -> ValidationSummary:
    """Re-export: the batch/vectorized fast path (spec sec 3) lives in
    claims_validator_batch.py (split out for the 300-LOC/file rail; that
    module imports FROM here, so this import is deferred to call time to
    avoid a circular import). Everything above this line is the ORIGINAL,
    untouched per-claim path -- unaffected by this addition."""
    from scripts.platformkit.intel_validation.claims_validator_batch import (
        validate_claims_file_batched as _batched,
    )
    return _batched(path)
