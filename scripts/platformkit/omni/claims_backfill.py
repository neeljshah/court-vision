"""scripts.platformkit.omni.claims_backfill -- P2-BF backfill registry verdicts into claims ledger.

Reads data/registry/signal_lab_registry.parquet and data/registry/signal_test_log/*.parquet,
converts each row into a claim via claims_ledger.add_claim(), idempotent on claim_id.
Verdicts: VALIDATED->accepted, REJECTED|rejected*->rejected; type is effect/negative.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime
from typing import Optional

import pandas as pd

from scripts.platformkit.omni.claims_ledger import (
    add_claim, make_claim_id, query, _replay_journal,
)


def _infer_season(asof_str: str) -> str:
    """Infer season from asof date string (YYYY-MM-DD). Jan-Sep is (year-1)-year, Oct-Dec is year-(year+1)."""
    try:
        d = datetime.strptime(asof_str, "%Y-%m-%d")
        # Jan-Sep (months 1-9) = earlier year season; Oct-Dec (months 10-12) = current year season
        if d.month <= 9:
            return f"{d.year - 1}-{d.year % 100:02d}"
        else:
            return f"{d.year}-{(d.year + 1) % 100:02d}"
    except (ValueError, AttributeError):
        return "unknown"


def _verdict_to_lifecycle(verdict: str) -> tuple[str, bool]:
    """Map verdict string to lifecycle state.
    Returns (lifecycle_state, is_effect_type).

    Args:
        verdict: verdict string from registry or test_log

    Returns:
        (lifecycle, is_effect) where lifecycle in {accepted, rejected, screened}
                  and is_effect=True for effect type, False for negative type.
    """
    if verdict is None or pd.isna(verdict):
        return None, None
    verdict = str(verdict).strip().upper()
    if verdict == "VALIDATED":
        return "accepted", True
    elif verdict == "REJECTED" or verdict.upper().startswith("REJECTED"):
        return "rejected", False
    else:
        return None, None


def backfill_registry(base_dir: Optional[str | pathlib.Path] = None,
                      registry_path: Optional[str | pathlib.Path] = None) -> dict:
    """Backfill signal_lab_registry.parquet into claims ledger.

    Args:
        base_dir: base directory for claims ledger (data/omni/claims/ by default)
        registry_path: path to signal_lab_registry.parquet (data/registry/signal_lab_registry.parquet by default)

    Returns dict with 'added' (count of new claims), 'skipped' (duplicates), 'failed' (unknown verdicts).
    """
    if registry_path is None:
        registry_path = pathlib.Path("data/registry/signal_lab_registry.parquet")
    registry_path = pathlib.Path(registry_path)
    if not registry_path.exists():
        return {"added": 0, "skipped": 0, "failed": 0, "error": "registry not found"}

    df = pd.read_parquet(registry_path)
    existing_ids = set(_replay_journal(base_dir).keys())

    added, skipped, failed = 0, 0, 0

    for idx, row in df.iterrows():
        lifecycle, is_effect = _verdict_to_lifecycle(row.get("verdict"))
        if lifecycle is None:
            failed += 1
            continue

        # Compose statement: name + target + metric + verdict + reason
        parts = [str(row.get("name", "")).strip()]
        target = str(row.get("target", "")).strip()
        if target:
            parts.append(f"on {target}")
        reason = str(row.get("reason", "")).strip()
        if reason:
            parts.append(f"({reason})")
        statement = " ".join(parts)

        scope = {
            "sport": "nba",  # all registry rows are NBA
            "entity_type": str(row.get("grain", "")).strip() or "unknown",
            "regime": _infer_season(str(row.get("asof", ""))),
        }

        claim_id = make_claim_id(statement, scope)
        if claim_id in existing_ids:
            skipped += 1
            continue

        claim = {
            "claim_id": claim_id,
            "statement": statement,
            "type": "effect" if is_effect else "negative",
            "scope": scope,
            "topic": str(row.get("target", "")).strip() or "unknown",
            "lifecycle": lifecycle,
            "effect": {
                "metric": str(row.get("metric", "")).strip() or "unknown",
                "size": float(row.get("oos_rel")) if pd.notna(row.get("oos_rel")) else None,
                "n": int(row.get("n")) if pd.notna(row.get("n")) else None,
                "unit": "",
            },
            "evidence": {
                "scores": {
                    "base_err": float(row.get("base_err")) if pd.notna(row.get("base_err")) else None,
                    "full_err": float(row.get("full_err")) if pd.notna(row.get("full_err")) else None,
                    "ortho": float(row.get("ortho")) if pd.notna(row.get("ortho")) else None,
                },
                "seed_check": row.get("split_half"),
            },
            "provenance": {
                "created_by_lane": "p2_backfill",
                "data_asof": str(row.get("asof", "")),
            },
        }
        try:
            add_claim(claim, base_dir)
            added += 1
            existing_ids.add(claim_id)
        except Exception as e:
            print(f"Failed to add claim {claim_id}: {e}")
            failed += 1

    return {"added": added, "skipped": skipped, "failed": failed, "source": "registry"}


def backfill_signal_test_log(base_dir: Optional[str | pathlib.Path] = None,
                             test_log_dir: Optional[str | pathlib.Path] = None) -> dict:
    """Backfill signal_test_log/*.parquet files into claims ledger.

    Args:
        base_dir: base directory for claims ledger (data/omni/claims/ by default)
        test_log_dir: path to signal_test_log directory (data/registry/signal_test_log by default)

    Returns dict with 'added' (count of new claims), 'skipped' (duplicates), 'failed' (unknown verdicts).
    """
    if test_log_dir is None:
        test_log_dir = pathlib.Path("data/registry/signal_test_log")
    test_log_dir = pathlib.Path(test_log_dir)
    if not test_log_dir.exists():
        return {"added": 0, "skipped": 0, "failed": 0, "error": "test_log dir not found"}

    existing_ids = set(_replay_journal(base_dir).keys())
    added, skipped, failed = 0, 0, 0

    for parquet_file in sorted(test_log_dir.glob("*.parquet")):
        df = pd.read_parquet(parquet_file)

        for idx, row in df.iterrows():
            lifecycle, is_effect = _verdict_to_lifecycle(row.get("verdict"))
            if lifecycle is None:
                failed += 1
                continue

            # Compose statement from hash + definition + verdict
            parts = [str(row.get("hash", "")).strip()]
            definition = str(row.get("definition", "")).strip()
            if definition:
                parts.append(definition)
            statement = " | ".join(parts)

            scope = {
                "sport": "nba",  # infer from test_log context
                "entity_type": "family",
                "regime": _infer_season(str(row.get("asof", ""))),
            }

            claim_id = make_claim_id(statement, scope)
            if claim_id in existing_ids:
                skipped += 1
                continue

            claim = {
                "claim_id": claim_id,
                "statement": statement,
                "type": "effect" if is_effect else "negative",
                "scope": scope,
                "topic": str(row.get("family_key", "")).strip() or "unknown",
                "lifecycle": lifecycle,
                "effect": {
                    "metric": "family_score",
                    "size": float(row.get("p")) if pd.notna(row.get("p")) else None,
                    "n": None,
                    "unit": "probability",
                },
                "evidence": {
                    "batch_id": str(row.get("batch_id", "")),
                },
                "provenance": {
                    "created_by_lane": "p2_backfill",
                    "data_asof": str(row.get("asof", "")),
                },
            }
            try:
                add_claim(claim, base_dir)
                added += 1
                existing_ids.add(claim_id)
            except Exception as e:
                print(f"Failed to add claim {claim_id}: {e}")
                failed += 1

    return {"added": added, "skipped": skipped, "failed": failed, "source": "signal_test_log"}


def run_backfill(base_dir: Optional[str | pathlib.Path] = None,
                 registry_path: Optional[str | pathlib.Path] = None,
                 test_log_dir: Optional[str | pathlib.Path] = None) -> dict:
    """Run full backfill: registry + signal_test_log. Returns aggregated stats."""
    results = {
        "registry": backfill_registry(base_dir, registry_path),
        "test_log": backfill_signal_test_log(base_dir, test_log_dir),
    }
    results["total_added"] = results["registry"]["added"] + results["test_log"]["added"]
    results["total_skipped"] = results["registry"]["skipped"] + results["test_log"]["skipped"]
    results["total_failed"] = results["registry"]["failed"] + results["test_log"]["failed"]
    return results


if __name__ == "__main__":
    import sys
    base_dir = sys.argv[1] if len(sys.argv) > 1 else None
    results = run_backfill(base_dir)
    print(json.dumps(results, indent=2))
