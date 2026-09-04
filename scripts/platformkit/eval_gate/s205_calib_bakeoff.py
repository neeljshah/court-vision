"""S205 attempt-2 evidence-only pregame calibration bakeoff."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from scripts.platformkit.calib_decomp import decompose
from scripts.platformkit.combo.corpus_cache import load_gate_corpus
from scripts.platformkit.eval_gate.calibration_report import (
    BIN_EDGE_RULE, _as_records, _bin_table, _finite_binary, _prediction_column,
)
from scripts.platformkit.eval_gate.s205_calib_oof import EMBARGO_DAYS, calibrate
from scripts.platformkit.eval_gate.scoring import ece, sharpness
from scripts.platformkit.regime_calibration import buckets

_REPO = Path(__file__).resolve().parents[3]
_OUT = _REPO / "docs" / "evidence" / "harness"
_DATE = "2026-09-04_attempt2"
_PREREG_PATH = "docs/evidence/harness/S205_calibration_prereg_2026-09-03_attempt2.md"
_PREREG_SEAL = "4477066E64105687647CF3E55B72E25727589E8635518BEEDDABBDDE9EF8D5D2"
_EPS = 1e-6
_EXPECTED = {
    "nba": (1814, 0.024842541854003943), "mlb": (39162, 0.008076824645850213),
    "soccer": (25834, 0.009301788688995382), "tennis": (41886, 0.008403089761848824),
}


def _prepared(records: Any) -> tuple[list[dict[str, Any]], list[float], list[float], list[str], str]:
    rows, usable = _as_records(records), []
    column = _prediction_column(rows)
    if column is None:
        raise ValueError("S205 requires an existing probability column")
    for row in rows:
        try:
            probability = float(row.get(column))
        except (TypeError, ValueError):
            continue
        if _finite_binary(row.get("y")) and math.isfinite(probability):
            copied = dict(row)
            copied["model_prob"] = probability
            usable.append(copied)
    keys = buckets(usable)
    compact = [{key: row.get(key) for key in ("model_prob", "y", "event_id", "corpus_unit", "event_date")}
               for row in usable]
    return (compact, [float(row["model_prob"]) for row in compact],
            [float(row["y"]) for row in compact], keys, column)


def _loss(probs: Sequence[float], outcomes: Sequence[float]) -> float:
    p = np.clip(np.asarray(probs, dtype=float), _EPS, 1.0 - _EPS)
    y = np.asarray(outcomes, dtype=float)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log1p(-p)))


def _metrics(raw: list[float], calibrated: list[float], outcomes: list[float]) -> dict[str, Any]:
    before, after = decompose(raw, outcomes, bins=10), decompose(calibrated, outcomes, bins=10)
    table, base_rate = _bin_table(calibrated, outcomes, 10), float(np.mean(outcomes))
    redone = {"ece": 0.0, "reliability": 0.0, "resolution": 0.0}
    for row in table:
        if row["n"]:
            weight = row["n"] / len(outcomes)
            redone["ece"] += weight * abs(row["gap"])
            redone["reliability"] += weight * row["gap"] ** 2
            redone["resolution"] += weight * (row["observed_win_freq"] - base_rate) ** 2
    improves = (ece(calibrated, outcomes, bins=10) < ece(raw, outcomes, bins=10)
                and after["reliability"] < before["reliability"]
                and after["resolution"] >= before["resolution"])
    return {
        "ece": ece(calibrated, outcomes, bins=10), "murphy_reliability": after["reliability"],
        "murphy_resolution": after["resolution"], "sharpness": sharpness(calibrated),
        "log_loss": _loss(calibrated, outcomes), "reliability_bins": table,
        "resolution_tax": before["resolution"] - after["resolution"],
        "verdict": "IMPROVES" if improves else "FLATTENED",
        "reproduction_max_abs_diff": max(abs(redone["ece"] - ece(calibrated, outcomes, bins=10)),
                                           abs(redone["reliability"] - after["reliability"]),
                                           abs(redone["resolution"] - after["resolution"])),
    }


def _prediction_rows(rows: list[dict[str, Any]], raw: list[float], outcomes: list[float],
                     arms: Mapping[str, list[float]], history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for index, (row, probability, outcome) in enumerate(zip(rows, raw, outcomes)):
        item: dict[str, Any] = {
            "row_index": index, "event_id": str(row.get("event_id", index)),
            "corpus_unit": str(row.get("corpus_unit", "ALL")), "event_date": str(row.get("event_date")),
            "outcome": outcome, "raw_probability": probability, "raw_log_loss": _loss([probability], [outcome]),
            **history[index],
        }
        for arm, values in arms.items():
            item[arm + "_probability"] = values[index]
            item[arm + "_log_loss"] = _loss([values[index]], [outcome])
        result.append(item)
    return result


def _identity(sport: str) -> dict[str, Any]:
    path = _REPO / "data" / "cache" / "combo" / ("gate_corpus_" + sport + ".parquet")
    return {"path": str(path), "bytes": path.stat().st_size, "resolution": "n/a tabular",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _s05_premise(sport: str, raw: Sequence[float], outcomes: Sequence[float]) -> float:
    """Remeasure the archived attempt-1 S05 isotonic OOF premise, row for row."""
    path = _OUT / ("S205_calib_bakeoff_2026-09-04_predictions_%s.json" % sport)
    archived = json.loads(path.read_text(encoding="ascii"))
    assert len(archived) == len(raw) == len(outcomes), "S205 premise archive length drift"
    assert all(float(row["raw_probability"]) == probability and float(row["outcome"]) == outcome
               for row, probability, outcome in zip(archived, raw, outcomes)), "S205 premise row drift"
    return ece([float(row["isotonic_probability"]) for row in archived], outcomes, bins=10)


def _archive(sport: str, rows: list[dict[str, Any]]) -> str:
    path = _OUT / ("S205_calib_bakeoff_%s_predictions_%s.json" % (_DATE, sport))
    payload = {"gap": "S205", "attempt": 2, "prereg_path": _PREREG_PATH,
               "prereg_seal_sha256": _PREREG_SEAL, "bin_edge_rule": BIN_EDGE_RULE, "rows": rows}
    path.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="ascii")
    return path.relative_to(_REPO).as_posix()


def run(sport_names: Sequence[str] = ("nba", "mlb", "soccer", "tennis")) -> dict[str, Any]:
    """Run the sealed CPCV bakeoff and write its fresh, calibration-only evidence."""
    _OUT.mkdir(parents=True, exist_ok=True)
    sports: dict[str, Any] = {}
    for sport in sport_names:
        records = load_gate_corpus(sport)
        rows, raw, outcomes, keys, column = _prepared(records)
        input_rows = len(records)
        del records
        expected_n, expected_ece = _EXPECTED[sport]
        premise_diff = abs(_s05_premise(sport, raw, outcomes) - expected_ece)
        if len(rows) != expected_n or premise_diff != 0.0:
            raise RuntimeError("S205 premise falsified for %s" % sport)
        arms, history = calibrate(rows, raw, outcomes, keys)
        metrics = {name: _metrics(raw, values, outcomes) for name, values in arms.items()}
        predictions = _prediction_rows(rows, raw, outcomes, arms, history)
        sports[sport] = {
            "input": _identity(sport), "prediction_column": column, "input_rows": input_rows,
            "scored_rows": len(rows), "dropped_rows": input_rows - len(rows),
            "s05_premise_isotonic_after_ece": expected_ece, "s05_premise_abs_diff": premise_diff,
            "cpcv_isotonic_abs_diff_from_s05": abs(metrics["isotonic"]["ece"] - expected_ece),
            "arms": metrics, "prediction_path": _archive(sport, predictions),
            "fit_history_changed_values": sum(item["fit_history"] != item["row_index"] for item in predictions),
        }
    summary = {
        "gap": "S205", "attempt": 2, "prereg_path": _PREREG_PATH, "prereg_seal_sha256": _PREREG_SEAL,
        "bin_edge_rule": BIN_EDGE_RULE, "calibration_only": True,
        "evaluation": {"engine": "cpcv_evaluate", "n_groups": 8, "n_test_groups": 1,
                       "symmetric_embargo_days": EMBARGO_DAYS, "purge": "engine same-team and matchup purge"},
        "sports": sports,
    }
    (_OUT / ("S205_calib_bakeoff_%s.json" % _DATE)).write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="ascii")
    return summary


if __name__ == "__main__":
    run()
