"""Versioned per-state calibration-series I/O and reproducible metrics."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Mapping

from scripts.platformkit.eval_gate.scoring import brier, ece

V2_FIELDS = (
    "game_id", "elapsed_s", "timestamp_utc", "timestamp_reason", "p_market",
    "p_null", "p_simulator", "outcome", "loss_market", "loss_null",
    "loss_simulator", "timestamp",
)


def _float(row: Mapping[str, str], key: str) -> float | None:
    value = row.get(key, "")
    return float(value) if value not in ("", None) else None


def _utc(value: str) -> tuple[str | None, str | None]:
    if not value:
        return None, "source tick has no ts"
    return datetime.fromtimestamp(float(value), timezone.utc).isoformat().replace("+00:00", "Z"), None


def v2_row_from_tick(row: Mapping[str, str]) -> dict[str, object]:
    """Map one committed S287-style selected tick to the additive v2 schema."""
    game = str(row["game"])
    elapsed = int(float(row.get("grid_target_elapsed") or row["elapsed"]))
    timestamp_utc, timestamp_reason = _utc(str(row.get("ts", "")))
    return {
        "game_id": game,
        "elapsed_s": elapsed,
        "timestamp_utc": timestamp_utc,
        "timestamp_reason": timestamp_reason,
        "p_market": _float(row, "market_prob"),
        "p_null": _float(row, "p_null"),
        "p_simulator": _float(row, "p_simulator"),
        "outcome": int(row["outcome_home_win"]),
        "loss_market": _float(row, "loss_market"),
        "loss_null": _float(row, "loss_recal_null"),
        "loss_simulator": _float(row, "loss_simulator"),
        "timestamp": row.get("state_key") or f"{game}:{elapsed}",
    }


def write_v2(path: Path, rows: Iterable[Mapping[str, object]]) -> int:
    """Write v2 rows with the legacy timestamp key retained verbatim."""
    count = 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=V2_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in V2_FIELDS})
            count += 1
    return count


def read_series(path: Path) -> Iterator[dict[str, object]]:
    """Read v1 or v2; v1 probabilities and outcome remain unavailable as null."""
    with path.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            if "p_market" not in raw:
                yield {
                    "version": 1, "game_id": raw.get("game"), "elapsed_s": None,
                    "timestamp_utc": None, "timestamp_reason": "v1 has no tick timestamp",
                    "p_market": None, "p_null": None, "p_simulator": None, "outcome": None,
                    "loss_market": None, "loss_null": raw.get("loss_recal_null"),
                    "loss_simulator": raw.get("loss_simulator"), "timestamp": raw.get("timestamp"),
                }
            else:
                row: dict[str, object] = {field: raw.get(field) or None for field in V2_FIELDS}
                row["version"] = 2
                row["elapsed_s"] = int(str(row["elapsed_s"]))
                row["outcome"] = int(str(row["outcome"]))
                for field in ("p_market", "p_null", "p_simulator", "loss_market", "loss_null", "loss_simulator"):
                    row[field] = float(str(row[field])) if row[field] is not None else None
                yield row


def recompute_metrics(rows: Iterable[Mapping[str, object]], bins: int = 10) -> dict[str, dict[str, float]]:
    """Recompute Brier and equal-width ECE only when v2 probabilities are present."""
    records = list(rows)
    if not records or any(row.get("outcome") is None for row in records):
        raise ValueError("v2 probabilities and outcomes are required for recomputation")
    outcomes = [float(row["outcome"]) for row in records]
    result: dict[str, dict[str, float]] = {"n": {"value": float(len(records))}}
    for arm, field in (("market", "p_market"), ("null", "p_null"), ("simulator", "p_simulator")):
        probabilities = [float(row[field]) for row in records if row.get(field) is not None]
        if len(probabilities) != len(outcomes):
            raise ValueError(f"missing {field} values")
        result[arm] = {"brier": brier(probabilities, outcomes), "ece": ece(probabilities, outcomes, bins)}
    return result
