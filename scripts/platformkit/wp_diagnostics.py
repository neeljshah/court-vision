"""Calibration diagnostics for settled in-game win-probability tick paths."""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np

from scripts.platformkit.calib_decomp import bin_edges, bin_index
from scripts.platformkit.ingame_replay_scoreboard import discover_store, load_ticks

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_CACHE = Path(os.environ.get(
    "NBA_CACHE_ROOT",
    os.path.join(os.environ.get("NBA_DATA_ROOT", "data"), "cache")))


def _brier(pairs: Iterable[tuple[float, float]]) -> Optional[float]:
    values = list(pairs)
    return (sum((prob - outcome) ** 2 for prob, outcome in values) / len(values)
            if values else None)


def _phase(tick: Dict[str, Any]) -> str:
    value = tick.get("phase")
    return str(value) if value not in (None, "") else "UNKNOWN"


def reliability(ticks: List[Dict[str, Any]], edges: Optional[Any] = None,
                legacy_bins: bool = False) -> List[Dict[str, Any]]:
    """Summarize probability bins, including a binomial uncertainty flag.

    `edges` defaults to `calib_decomp.bin_edges(10)` -- the SAME numpy edges
    `scoring.ece` and `calib_decomp.decompose` use -- so a report publishing this
    bin table beside a summary ECE or Murphy figure is self-consistent (S42).
    `legacy_bins=True` restores the pre-S42 min(bins-1, int(p*bins)) assignment,
    which disagrees with those edges on predictions landing exactly on the grid.
    """
    edge_array = bin_edges(10) if edges is None else np.asarray(edges, dtype=float)
    count = len(edge_array) - 1
    bins: List[List[Dict[str, Any]]] = [[] for _ in range(count)]
    for tick in ticks:
        prob = tick["model_prob"]
        bins[min(count - 1, int(prob * count)) if legacy_bins
             else bin_index(prob, edge_array)].append(tick)
    rows: List[Dict[str, Any]] = []
    for index, group in enumerate(bins):
        n = len(group)
        mean_prob = sum(t["model_prob"] for t in group) / n if n else None
        observed = sum(t["outcome"] for t in group) / n if n else None
        gap = observed - mean_prob if n else None
        limit = (2 * math.sqrt(mean_prob * (1 - mean_prob) / n) if n and mean_prob is not None
                 else None)
        rows.append({"bin": "%0.1f-%0.1f" % (edge_array[index], edge_array[index + 1]), "n": n,
                     "mean_predicted_prob": mean_prob, "observed_win_freq": observed,
                     "gap": gap, "flag": bool(limit is not None and abs(gap) > limit),
                     "status": "OK" if n >= 50 else "INSUFFICIENT"})
    return rows


def phase_reliability(ticks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Return reliability rows split by the provided game-phase labels."""
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for tick in ticks:
        grouped[_phase(tick)].append(tick)
    return {phase: reliability(group) for phase, group in sorted(grouped.items())}


def max_loser_wp(ticks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Measure each settled loser's largest model probability over its game path."""
    games: Dict[str, List[float]] = defaultdict(list)
    for tick in ticks:
        if tick["outcome"] == 0.0:
            games[tick["game"]].append(tick["model_prob"])
    values = [{"game": game, "max_loser_wp": max(probs)}
              for game, probs in sorted(games.items()) if probs]
    peaks = sorted(row["max_loser_wp"] for row in values)
    def quantile(q: float) -> Optional[float]:
        if not peaks:
            return None
        position = (len(peaks) - 1) * q
        low, high = int(position), math.ceil(position)
        return peaks[low] + (peaks[high] - peaks[low]) * (position - low)
    return {"per_game": values,
            "quantiles": {str(int(q * 100)): quantile(q) for q in (0.5, 0.75, 0.9, 0.95)},
            "above_0_8": sum(value > 0.8 for value in peaks),
            "above_0_9": sum(value > 0.9 for value in peaks)}


def isotonic_check(ticks: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Fit in-sample isotonic probabilities solely as a calibration diagnostic."""
    pairs = [(tick["model_prob"], tick["outcome"]) for tick in ticks]
    before = _brier(pairs)
    if not pairs or len({outcome for _, outcome in pairs}) < 2:
        return {"brier_before": before, "brier_after": None, "delta": None}
    from sklearn.isotonic import IsotonicRegression
    model = IsotonicRegression(out_of_bounds="clip")
    predictions = model.fit_transform([prob for prob, _ in pairs], [outcome for _, outcome in pairs])
    after = _brier(zip(predictions, (outcome for _, outcome in pairs)))
    return {"brier_before": before, "brier_after": after,
            "delta": before - after if before is not None and after is not None else None}


def diagnose(ticks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Produce all requested WP calibration and premature-confidence diagnostics."""
    return {"tick_count": len(ticks), "reliability": reliability(ticks),
            "phase_reliability": phase_reliability(ticks), "max_loser_wp": max_loser_wp(ticks),
            "isotonic_check": isotonic_check(ticks)}


def _number(value: Optional[float]) -> str:
    return "-" if value is None else "%.4f" % value


def _render_reliability(title: str, rows: List[Dict[str, Any]]) -> List[str]:
    lines = [title, "BIN | N | MEAN_PRED | OBSERVED | GAP | FLAG | STATUS",
             "----|---|-----------|----------|-----|------|-------"]
    for row in rows:
        lines.append("%s | %d | %s | %s | %s | %s | %s" %
                     (row["bin"], row["n"], _number(row["mean_predicted_prob"]),
                      _number(row["observed_win_freq"]), _number(row["gap"]),
                      "YES" if row["flag"] else "NO", row["status"]))
    return lines


def render(report: Dict[str, Any]) -> str:
    lines = _render_reliability("RELIABILITY OVERALL", report["reliability"])
    for phase, rows in report["phase_reliability"].items():
        lines.extend([""] + _render_reliability("RELIABILITY PHASE %s" % phase, rows))
    loser = report["max_loser_wp"]
    lines.extend(["", "MAX-LOSER-WP", "GAME | MAX_LOSER_WP", "-----|-------------"])
    lines.extend("%s | %.4f" % (row["game"], row["max_loser_wp"]) for row in loser["per_game"])
    lines.append("QUANTILES P50=%s P75=%s P90=%s P95=%s ABOVE_0.8=%d ABOVE_0.9=%d" %
                 tuple([_number(loser["quantiles"][str(q)]) for q in (50, 75, 90, 95)] +
                       [loser["above_0_8"], loser["above_0_9"]]))
    iso = report["isotonic_check"]
    lines.append("ISOTONIC CHECK: BRIER_BEFORE=%s BRIER_AFTER=%s DELTA=%s" %
                 (_number(iso["brier_before"]), _number(iso["brier_after"]), _number(iso["delta"])))
    return "\n".join(lines)


def write_report(report: Dict[str, Any], store: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / ("wp_diagnostics_%s.json" % stamp)
    path.write_text(json.dumps({"generated_at": stamp, "store": str(store), **report}, indent=2,
                               sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose settled in-game win-probability paths.")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE)
    parser.add_argument("--output-dir", type=Path, default=_REPO / "data" / "ab_reports")
    args = parser.parse_args(argv)
    store = discover_store(args.cache_root)
    if store is None:
        print("NO PARSEABLE TICK STORE")
        return 0
    report = diagnose(load_ticks(store))
    print("STORE: %s" % store)
    print(render(report))
    print("REPORT: %s" % write_report(report, store, args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
