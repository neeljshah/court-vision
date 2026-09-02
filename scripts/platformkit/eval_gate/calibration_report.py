"""Evidence-only composition of the existing calibration diagnostics (gap S05).

The report scores every usable cached-corpus row.  Isotonic outputs are strict
expanding-window outputs: no outcome from a scored row is used in its fit.

ONE BIN-EDGE RULE (the attempt-1 defect, register gap S42): the published bin
table and the summary ECE / Murphy figures are produced from the SAME equal-width
`np.linspace(0, 1, bins + 1)` edges that `eval_gate.scoring.ece` and
`calib_decomp.decompose` bin by -- half-open [lo, hi) with a closed last bin.
Attempt 1 published a second, disagreeing table beside those summaries, so the
artifact did not reproduce itself.  `_bin_table` below is that one rule, and
`build_report` MEASURES the reproduction into `reproduction_max_abs_diff`.

Calibration, not edge.  Nothing here is charged, promoted or served.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from scripts.platformkit.calib_decomp import decompose
from scripts.platformkit.combo.corpus_cache import (
    SPORTS, StaleCorpusError, freshness_report, load_gate_corpus,
)
from scripts.platformkit.eval_gate.scoring import ece, sharpness
from scripts.platformkit.recalibration import walk_forward_recalibrate
from scripts.platformkit.regime_calibration import buckets, fit_per_regime
from scripts.platformkit.wp_diagnostics import isotonic_check, max_loser_wp

_REPO = Path(__file__).resolve().parents[3]
_OUTPUT = _REPO / "docs" / "evidence" / "calibration"
_PREDICTION_COLUMNS = ("model_prob", "pred", "prediction", "p_base")

PREREG_PATH = "docs/evidence/harness/S05_calibration_prereg_2026-09-03.md"
PREREG_SEAL = "9051BB6E3BD89F7309A799F9739C8E61EA6DB3530E52AD87666568220591DF8A"
BIN_EDGE_RULE = (
    "np.linspace(0, 1, bins + 1) equal-width edges, bin k = [lo, hi) except the "
    "last = [lo, hi] -- the SAME rule eval_gate.scoring.ece and "
    "calib_decomp.decompose bin by (gap S42)"
)
REPRODUCTION = {
    "ece": "sum_k (n_k / N) * abs(observed_win_freq_k - mean_predicted_prob_k)",
    "murphy_reliability": "sum_k (n_k / N) * (observed_win_freq_k - mean_predicted_prob_k) ** 2",
    "murphy_resolution": "sum_k (n_k / N) * (observed_win_freq_k - base_rate) ** 2",
    "murphy_uncertainty": "base_rate * (1 - base_rate)",
    "note": "sum over non-empty bins in ascending bin order; base_rate is published per report",
}


def _as_records(records: Any) -> list[dict[str, Any]]:
    if hasattr(records, "to_dict"):
        return [dict(row) for row in records.to_dict("records")]
    return [dict(row) for row in records]


def _prediction_column(rows: Sequence[Mapping[str, Any]]) -> str | None:
    for column in _PREDICTION_COLUMNS:
        if any(column in row for row in rows):
            return column
    return None


def _finite_binary(value: Any) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) in (0.0, 1.0)
    except (TypeError, ValueError):
        return False


def _bin_table(probs: Sequence[float], outcomes: Sequence[float], bins: int) -> list[dict[str, Any]]:
    """The ONE bin-edge rule -- always `bins` rows, empty bins carried as n = 0."""
    p, y = np.asarray(probs, dtype=float), np.asarray(outcomes, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    rows: list[dict[str, Any]] = []
    for k in range(bins):
        lo, hi = float(edges[k]), float(edges[k + 1])
        mask = (p >= lo) & (p < hi) if k < bins - 1 else (p >= lo) & (p <= hi)
        n_k = int(mask.sum())
        mean_p = float(p[mask].mean()) if n_k else None
        observed = float(y[mask].mean()) if n_k else None
        rows.append({"bin": "%0.1f-%0.1f" % (lo, hi), "lo": lo, "hi": hi, "n": n_k,
                    "mean_predicted_prob": mean_p, "observed_win_freq": observed,
                    "gap": (observed - mean_p) if n_k else None})
    return rows


def _from_bins(table: Sequence[Mapping[str, Any]], base_rate: float,
               total: int) -> dict[str, float]:
    """Recompute the summary figures FROM the published bins (A2 reproduction)."""
    out = {"ece": 0.0, "reliability": 0.0, "resolution": 0.0}
    for row in table:
        if not row["n"]:
            continue
        weight = row["n"] / total
        out["ece"] += weight * abs(row["gap"])
        out["reliability"] += weight * row["gap"] ** 2
        out["resolution"] += weight * (row["observed_win_freq"] - base_rate) ** 2
    return out


def _ticks(probs: Sequence[float], outcomes: Sequence[float],
           rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"model_prob": float(prob), "outcome": float(outcome),
         "game": str(row.get("event_id", index))}
        for index, (prob, outcome, row) in enumerate(zip(probs, outcomes, rows))
    ]


def _unit_groups(rows: Sequence[Mapping[str, Any]], unit_col: str | None,
                 order_by: str | None) -> tuple[list[tuple[str, list[int]]], bool, bool]:
    """Positions per corpus_unit, sorted within the unit by ``order_by`` (S50).

    Returns (groups, sort_within_unit_is_noop, partition_is_identity) -- both
    flags published so a reader sees whether the walk order actually moved.
    ponytail: the sort key is ``str(value)``; every gate corpus stores one
    ISO-ordered date dtype per column, so lexical order IS date order there.
    """
    units: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        units.setdefault(str(row.get(unit_col)) if unit_col else "ALL", []).append(index)
    groups: list[tuple[str, list[int]]] = []
    sort_noop = True
    for key, positions in units.items():
        ordered = positions
        if order_by and any(order_by in rows[index] for index in positions):
            ordered = sorted(positions, key=lambda index: str(rows[index].get(order_by)))
            sort_noop = sort_noop and ordered == positions
        groups.append((key, ordered))
    walked = [index for _, positions in groups for index in positions]
    return groups, sort_noop, walked == list(range(len(rows)))


def _unit_summary(key: str, positions: list[int], rows: Sequence[Mapping[str, Any]],
                  order_by: str | None, raw: list[float], calibrated: list[float],
                  outcomes: list[float], bins: int) -> dict[str, Any]:
    dates = [str(rows[index].get(order_by)) for index in positions] if order_by else []
    y = [outcomes[index] for index in positions]
    return {
        "corpus_unit": key, "n": len(positions),
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "ece_before": ece([raw[index] for index in positions], y, bins=bins),
        "ece_after": ece([calibrated[index] for index in positions], y, bins=bins),
    }


def _oof_per_regime(
    probs: list[float], outcomes: list[float], keys: list[str], min_n: int,
) -> list[float]:
    """Return expanding-window isotonic outputs with fit_per_regime fallback."""
    fits = fit_per_regime(probs, outcomes, keys, min_n=min_n)
    global_oof = walk_forward_recalibrate(probs, outcomes, min_history=min_n).tolist()
    calibrated = list(global_oof)
    global_fit = fits["GLOBAL"]
    for key in sorted(set(keys)):
        if fits[key] is global_fit:
            continue
        indices = [index for index, candidate in enumerate(keys) if candidate == key]
        local = walk_forward_recalibrate(
            [probs[index] for index in indices],
            [outcomes[index] for index in indices],
            min_history=min_n,
        )
        for index, value in zip(indices, local):
            calibrated[index] = float(value)
    return calibrated


def _max_loser_summary(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep the existing diagnostic's aggregate fields, not its event listing."""
    result = max_loser_wp(ticks)
    return {key: result[key] for key in ("quantiles", "above_0_8", "above_0_9")}


def _stamp(report: dict[str, Any], sport: str,
           order_basis: str = "POSITIONAL-ORDER") -> dict[str, Any]:
    report["prereg_path"] = PREREG_PATH
    report["prereg_seal_sha256"] = PREREG_SEAL
    report["bin_edge_rule"] = BIN_EDGE_RULE
    report["reproduction"] = REPRODUCTION
    # walk_forward_recalibrate consumes ROW ORDER, never a date, so the scoring
    # order is positional UNLESS build_report sorted the rows itself (S44
    # surfaced the column, S50 walks it). `corpus_date_column` -- what the corpus
    # CARRIES -- stays a separate key so the two facts are never conflated.
    report["order_basis"] = order_basis
    try:
        basis = freshness_report(sport)["order_basis"]
    except ValueError:
        basis = "POSITIONAL-ORDER"
    report["corpus_date_column"] = None if basis == "POSITIONAL-ORDER" else basis
    return report


def _no_metrics(sport: str, status: str, **extra: Any) -> dict[str, Any]:
    """A report that carries NO metric values, only the reason it carries none."""
    report: dict[str, Any] = {
        "sport": sport, "status": status, "verdict": status,
        "prediction_column": None, "devigged_close_column": None,
        "input_rows": None, "dropped_rows": None, "scored_rows": None,
        "base_rate": None, "reliability_bins": [], "max_loser_wp": None,
        "ece_before": None, "ece_after": None,
        "murphy_before": None, "murphy_after": None,
        "sharpness_before": None, "sharpness_after": None,
        "reproduction_max_abs_diff": None,
        "walk_unit_col": None, "walk_sort_within_unit_is_noop": None,
        "walk_partition_is_identity": None, "by_corpus_unit": None,
    }
    report.update(extra)
    return _stamp(report, sport)


def build_report(records: Any, sport: str, *, bins: int = 10, min_n: int = 200,
                 order_by: str | None = None, unit_col: str | None = None) -> dict:
    """Build one sport's evidence report from every finite/binary corpus row.

    ``order_by`` / ``unit_col`` (gap S50) are OPT-IN and default OFF: given both,
    rows are partitioned by ``unit_col``, stable-sorted within each unit by
    ``order_by`` and recalibrated PER UNIT, so no isotonic history crosses a
    corpus_unit boundary. Bins/ECE/Murphy/sharpness aggregate over the union
    unchanged (all four are order-free); per-unit ECE and date ranges are added.
    Default OFF because that split is NOT a no-op on the three already-
    chronological corpora -- it withholds the first unit's history from the
    second, and splits soccer's six interleaved divisions. Deltas: S50 memo.
    """
    rows = _as_records(records)
    prediction_column = _prediction_column(rows)
    usable: list[dict[str, Any]] = []
    for row in rows:
        if prediction_column is None:
            continue
        if not _finite_binary(row.get("y")):
            continue
        try:
            prediction = float(row.get(prediction_column))
        except (TypeError, ValueError):
            continue
        if math.isfinite(prediction):
            copied = dict(row)
            copied["model_prob"] = prediction
            usable.append(copied)
    dropped_rows = len(rows) - len(usable)
    if len(usable) < min_n:
        return _no_metrics(
            sport, "INSUFFICIENT", prediction_column=prediction_column,
            input_rows=len(rows), dropped_rows=dropped_rows, scored_rows=len(usable),
            min_n=min_n, shortfall=max(0, min_n - len(usable)))

    raw = [float(row["model_prob"]) for row in usable]
    outcomes = [float(row["y"]) for row in usable]
    keys = buckets(usable)
    # Default OFF collapses to ONE group in row order, i.e. the pre-S50 call.
    walked = bool(order_by and unit_col)
    groups, sort_noop, identity = _unit_groups(
        usable, unit_col if walked else None, order_by if walked else None)
    calibrated = [0.0] * len(usable)
    for _, positions in groups:
        local = _oof_per_regime([raw[i] for i in positions], [outcomes[i] for i in positions],
                                [keys[i] for i in positions], min_n)
        for index, value in zip(positions, local):
            calibrated[index] = float(value)
    raw_ticks = _ticks(raw, outcomes, usable)
    murphy_before = decompose(raw, outcomes, bins=bins)
    murphy_after = decompose(calibrated, outcomes, bins=bins)
    ece_before, ece_after = ece(raw, outcomes, bins=bins), ece(calibrated, outcomes, bins=bins)
    base_rate = float(np.mean(outcomes))
    table_before = _bin_table(raw, outcomes, bins)
    table_after = _bin_table(calibrated, outcomes, bins)

    # A2: the artifact must reproduce ITSELF from its own published bins.
    checks = []
    for table, summary_ece, murphy in ((table_before, ece_before, murphy_before),
                                       (table_after, ece_after, murphy_after)):
        redone = _from_bins(table, base_rate, len(usable))
        checks += [abs(redone["ece"] - summary_ece),
                   abs(redone["reliability"] - murphy["reliability"]),
                   abs(redone["resolution"] - murphy["resolution"])]

    improves = (
        ece_after < ece_before
        and murphy_after["reliability"] < murphy_before["reliability"]
        and murphy_after["resolution"] >= murphy_before["resolution"]
    )
    return _stamp({
        "sport": sport,
        "status": "OK",
        "prediction_column": prediction_column,
        "devigged_close_column": next(
            (column for column in ("p_devig_close", "devigged_close")
             if any(column in row for row in rows)),
            None,
        ),
        "input_rows": len(rows),
        "dropped_rows": dropped_rows,
        "scored_rows": len(usable),
        "base_rate": base_rate,
        "regime_keys": "scripts.platformkit.regime_calibration.buckets",
        "recalibration": ("walk_forward_recalibrate expanding inner folds; "
                          "fit_per_regime GLOBAL fallback below min_n"),
        "reliability_bins": table_before,
        "reliability_bins_after": table_after,
        "max_loser_wp": _max_loser_summary(raw_ticks),
        "diagnostic_in_sample_isotonic": isotonic_check(raw_ticks),
        "ece_before": ece_before,
        "ece_after": ece_after,
        "murphy_before": {k: murphy_before[k] for k in ("reliability", "resolution", "uncertainty")},
        "murphy_after": {k: murphy_after[k] for k in ("reliability", "resolution", "uncertainty")},
        "sharpness_before": sharpness(raw),
        "sharpness_after": sharpness(calibrated),
        "reproduction_max_abs_diff": max(checks),
        "verdict": "IMPROVES" if improves else "FLATTENED",
        # S50: what the walk actually did, never inferred from the column's presence.
        "walk_unit_col": unit_col if walked else None,
        "walk_sort_within_unit_is_noop": sort_noop if walked else None,
        "walk_partition_is_identity": identity if walked else None,
        "by_corpus_unit": [
            _unit_summary(key, positions, usable, order_by if walked else None,
                          raw, calibrated, outcomes, bins)
            for key, positions in groups
        ] if walked else None,
    }, sport, "event_date" if walked else "POSITIONAL-ORDER")


def _unavailable(sport: str, error: Exception) -> dict[str, Any]:
    """A loader refusal. It counts as a MISS against the 4/4 bar, never an exemption."""
    return _no_metrics(sport, "INPUT_UNAVAILABLE", reason=str(error))


def main(argv: Sequence[str] | None = None) -> int:
    """Write one dated JSON calibration artifact for every gate corpus.

    `--per-unit` (S50) writes the SEPARATE `*_reliability_per_unit_*.json` family
    instead -- a different measurement, so it never overwrites the S05b files.
    """
    per_unit = "--per-unit" in (list(argv) if argv is not None else sys.argv[1:])
    walk = {"order_by": "event_date", "unit_col": "corpus_unit"} if per_unit else {}
    suffix = "_per_unit" if per_unit else ""
    _OUTPUT.mkdir(parents=True, exist_ok=True)
    for sport in SPORTS:
        try:
            report = build_report(load_gate_corpus(sport), sport, **walk)
        except StaleCorpusError as error:
            report = _unavailable(sport, error)
        output = _OUTPUT / f"{sport}_reliability{suffix}_2026-09-03.json"
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("%s: %s rows; prediction=%s; verdict=%s; reproduction_max_abs_diff=%s" % (
            sport, report["scored_rows"], report["prediction_column"],
            report["verdict"], report["reproduction_max_abs_diff"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
