"""Leak-safe live shadow evaluation for champion/challenger forecasts.

Predictions are append-only until an outcome is later settled.  Comparison is
evidence only: a PROMOTE verdict is written for a human or orchestrator to
review, and this module never changes serving configuration or feature flags.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from scripts.platformkit.brier_decomposition import decompose


DATA_ROOT = Path(os.environ.get("NBA_DATA_ROOT", "data"))
MIN_SETTLED_ROWS = 200
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_SEED = 20260831


def _report_dir() -> Path:
    return DATA_ROOT / "ab_reports"


def _registry_path() -> Path:
    return _report_dir() / "challengers.json"


def _ledger_path() -> Path:
    return _report_dir() / "shadow_ledger.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp(value: object) -> str:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    return str(value)


def _parse_timestamp(value: object) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _prob(value: object, label: str) -> float:
    result = float(value)
    if not np.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError("{0} must be a finite probability in [0, 1]".format(label))
    return result


def _read_registry() -> dict[str, dict[str, Any]]:
    path = _registry_path()
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("challengers"), dict):
        raw = raw["challengers"]
    if not isinstance(raw, dict):
        raise ValueError("challengers.json must contain a challenger mapping")
    return {str(name): dict(value) for name, value in raw.items()}


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _read_ledger() -> list[dict[str, Any]]:
    path = _ledger_path()
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("shadow ledger lines must be JSON objects")
            records.append(record)
    return records


def _write_ledger(records: list[dict[str, Any]]) -> None:
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("".join(json.dumps(record, sort_keys=True, allow_nan=False) + "\n" for record in records),
                          encoding="utf-8")
    temporary.replace(path)


def register_challenger(name: str, predict_fn_import_path: str, config: Mapping[str, Any]) -> dict[str, Any]:
    """Register challenger metadata without enabling or promoting the model."""
    if not name or not isinstance(name, str):
        raise ValueError("name must be a non-empty string")
    if not predict_fn_import_path or not isinstance(predict_fn_import_path, str):
        raise ValueError("predict_fn_import_path must be a non-empty string")
    challengers = _read_registry()
    entry = {"predict_fn_import_path": predict_fn_import_path, "config": dict(config),
             "registered_at": _utc_now()}
    challengers[name] = entry
    _write_json(_registry_path(), {"challengers": challengers})
    return entry


def log_shadow(ts: object, market_key: str, champion_prob: float,
               challenger_probs: Mapping[str, float], market_prob: float) -> dict[str, Any]:
    """Append forecasts before the outcome is known; return the ledger row."""
    if not isinstance(challenger_probs, Mapping):
        raise ValueError("challenger_probs must be a mapping")
    record: dict[str, Any] = {
        "ts": _timestamp(ts), "market_key": str(market_key),
        "champion_prob": _prob(champion_prob, "champion_prob"),
        "challenger_probs": {str(name): _prob(prob, "challenger_prob")
                              for name, prob in challenger_probs.items()},
        "market_prob": _prob(market_prob, "market_prob"), "outcome": None,
    }
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
    return record


def settle_shadow(market_key: str, outcome: int) -> int:
    """Fill the outcome on matching, previously unsettled market rows only."""
    if outcome not in (0, 1):
        raise ValueError("outcome must be binary")
    records = _read_ledger()
    updated = 0
    for record in records:
        if str(record.get("market_key")) == str(market_key) and record.get("outcome") is None:
            record["outcome"] = int(outcome)
            record["settled_at"] = _utc_now()
            updated += 1
    if updated:
        _write_ledger(records)
    return updated


def _bootstrap_ci(champion: np.ndarray, challenger: np.ndarray, outcomes: np.ndarray) -> tuple[float, float]:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    indices = rng.integers(0, len(outcomes), size=(BOOTSTRAP_SAMPLES, len(outcomes)))
    deltas = np.mean((challenger[indices] - outcomes[indices]) ** 2, axis=1)
    deltas -= np.mean((champion[indices] - outcomes[indices]) ** 2, axis=1)
    return float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))


def _comparison(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    usable = [row for row in rows if name in row.get("challenger_probs", {})]
    champion = np.asarray([_prob(row["champion_prob"], "champion_prob") for row in usable], dtype=float)
    challenger = np.asarray([_prob(row["challenger_probs"][name], "challenger_prob") for row in usable], dtype=float)
    outcomes = np.asarray([row["outcome"] for row in usable], dtype=float)
    result: dict[str, Any] = {"challenger": name, "n_settled": int(len(usable)), "verdict": "HOLD"}
    if len(usable) < MIN_SETTLED_ROWS:
        result["reason"] = "INSUFFICIENT_SETTLED_ROWS"
        return result
    champion_decomp = decompose(champion, outcomes)
    challenger_decomp = decompose(challenger, outcomes)
    ci_low, ci_high = _bootstrap_ci(champion, challenger, outcomes)
    delta = float(challenger_decomp["brier"] - champion_decomp["brier"])
    result.update({"champion": champion_decomp, "challenger": challenger_decomp,
                   "delta_brier": delta, "bootstrap_ci": {"low": ci_low, "high": ci_high},
                   "reliability_not_worse": challenger_decomp["reliability"] <= champion_decomp["reliability"]})
    if challenger_decomp["reliability"] > champion_decomp["reliability"]:
        result["reason"] = "RELIABILITY_WORSE"
    elif ci_low <= 0.0 <= ci_high:
        result["reason"] = "CI_INCLUDES_ZERO"
    elif delta >= 0.0:
        result["reason"] = "CHALLENGER_BRIER_NOT_BETTER"
    elif ci_high >= 0.0:
        result["reason"] = "CI_NOT_EXCLUDING_ZERO"
    else:
        result["verdict"] = "PROMOTE"
        result["reason"] = "LIVE_SHADOW_SUPERIORITY_CONFIRMED_HUMAN_GATE_REQUIRED"
    return result


def compare(window_days: int = 14) -> dict[str, Any]:
    """Compare registered/live challengers on the same recent settled rows.

    PROMOTE is only a written recommendation.  A human or orchestrator must
    separately review and enact any promotion; no serving state is changed.
    """
    if window_days < 1:
        raise ValueError("window_days must be positive")
    all_rows = _read_ledger()
    dated = [(row, _parse_timestamp(row["ts"])) for row in all_rows if row.get("outcome") in (0, 1)]
    anchor = max((stamp for _, stamp in dated), default=datetime.now(timezone.utc))
    cutoff = anchor - timedelta(days=window_days)
    rows = [row for row, stamp in dated if cutoff <= stamp <= anchor]
    registered = set(_read_registry())
    logged = {name for row in rows for name in row.get("challenger_probs", {})}
    report: dict[str, Any] = {
        "window_days": int(window_days), "window_start": cutoff.isoformat(), "window_end": anchor.isoformat(),
        "n_settled_rows": int(len(rows)), "human_gate_required": True,
        "promotion_note": "PROMOTE is evidence only; a human/orchestrator must approve any serving change.",
        "challengers": {name: _comparison(rows, name) for name in sorted(registered | logged)},
    }
    _write_json(_report_dir() / "shadow_comparison.json", report)
    return report


if __name__ == "__main__":
    print("shadow_challenger provides registry, logging, settlement, and comparison APIs")
