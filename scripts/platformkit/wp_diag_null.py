"""Calibrated simulation null for max loser win-probability diagnostics."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from scripts.platformkit.ingame_replay_scoreboard import discover_store, load_ticks

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_CACHE = Path(r"C:\Users\neelj\nba-ai-system\data\cache")
_QUANTILES = ("50", "75", "90", "95")
_STATS = ("p50", "p75", "p90", "p95", "p_loser_peak_ge_0_8", "p_loser_peak_ge_0_9")


def path_parameters(ticks: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract empirical pregame probabilities, path length, and move scale."""
    games: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for tick in ticks:
        games[tick["game"]].append(tick)
    paths = [sorted(group, key=lambda row: row.get("timestamp", ""))
             for group in games.values() if group]
    if not paths:
        raise ValueError("no settled game paths")
    starts = np.array([path[0]["model_prob"] for path in paths], dtype=float)
    lengths = np.array([len(path) for path in paths], dtype=int)
    moves = [abs(float(b["model_prob"]) - float(a["model_prob"]))
             for path in paths for a, b in zip(path, path[1:])]
    return {"pregame_probs": starts, "ticks": max(1, int(np.median(lengths))),
            "step_vol": float(np.median(moves)) if moves else 0.01}


def _martingale_path(p0: float, ticks: int, step_vol: float,
                     rng: np.random.Generator) -> tuple[np.ndarray, int]:
    """Use an absorbing, zero-drift random walk, then reveal its Bernoulli outcome.

    At every nonterminal tick, unequal boundary moves are selected with probabilities
    that preserve the current probability in expectation.  The final reveal is 0 or
    1, so its label is calibrated by construction.
    """
    path = np.empty(ticks, dtype=float)
    p = float(np.clip(p0, 0.0, 1.0))
    for index in range(ticks):
        path[index] = p
        if index == ticks - 1 or p in (0.0, 1.0):
            continue
        up, down = min(step_vol, 1.0 - p), min(step_vol, p)
        if up == 0.0 or down == 0.0:
            continue
        if rng.random() < down / (up + down):
            p += up
        else:
            p -= down
    outcome = int(rng.random() < p)
    return np.append(path, float(outcome)), outcome


def _statistics(peaks: np.ndarray) -> Dict[str, float]:
    return {"p" + key: float(np.quantile(peaks, int(key) / 100.0)) for key in _QUANTILES} | {
        "p_loser_peak_ge_0_8": float(np.mean(peaks >= 0.8)),
        "p_loser_peak_ge_0_9": float(np.mean(peaks >= 0.9)),
    }


def simulate_null(params: Dict[str, Any], games: int, simulations: int = 2000,
                  seed: int = 0) -> Dict[str, Any]:
    """Simulate calibrated game sets and return 95 percent simulation bands."""
    if games < 1 or simulations < 1:
        raise ValueError("games and simulations must be positive")
    starts = np.asarray(params["pregame_probs"], dtype=float)
    if starts.size == 0:
        raise ValueError("pregame_probs is empty")
    rng = np.random.default_rng(seed)
    draws = {name: np.empty(simulations, dtype=float) for name in _STATS}
    for trial in range(simulations):
        loser_peaks = []
        while len(loser_peaks) < games:
            p0 = float(starts[rng.integers(starts.size)])
            path, outcome = _martingale_path(p0, int(params["ticks"]),
                                              float(params["step_vol"]), rng)
            if outcome == 0:
                loser_peaks.append(float(path.max()))
        values = _statistics(np.asarray(loser_peaks))
        for name, value in values.items():
            draws[name][trial] = value
    return {"simulations": simulations, "games_per_draw": games,
            "bands": {name: [float(np.quantile(values, 0.025)),
                             float(np.quantile(values, 0.975))]
                      for name, values in draws.items()}}


def observed_statistics(report: Dict[str, Any]) -> Dict[str, float]:
    """Read max-loser statistics from a wp_diagnostics JSON report."""
    loser = report["max_loser_wp"]
    per_game = loser.get("per_game", [])
    peaks = np.asarray([row["max_loser_wp"] for row in per_game], dtype=float)
    if peaks.size:
        return _statistics(peaks)
    quantiles = loser.get("quantiles", {})
    count = float(report.get("game_count", report.get("loser_game_count", 0)))
    if count <= 0:
        raise ValueError("report has no max_loser_wp per_game values")
    return {"p" + key: float(quantiles[key]) for key in _QUANTILES} | {
        "p_loser_peak_ge_0_8": float(loser["above_0_8"]) / count,
        "p_loser_peak_ge_0_9": float(loser["above_0_9"]) / count,
    }


def compare(observed: Dict[str, float], null: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compare observed metrics to inclusive 95 percent simulation bands."""
    return [{"statistic": name, "observed": observed[name], "low": null["bands"][name][0],
             "high": null["bands"][name][1], "verdict":
             "INSIDE" if null["bands"][name][0] <= observed[name] <= null["bands"][name][1]
             else "OUTSIDE"} for name in _STATS]


def _latest_report(directory: Path) -> Optional[Path]:
    reports = list(directory.glob("wp_diagnostics_*.json"))
    return max(reports, key=lambda path: (path.stat().st_mtime, path.name)) if reports else None


def render(rows: Sequence[Dict[str, Any]]) -> str:
    lines = ["OBSERVED VS CALIBRATED NULL", "STATISTIC | OBSERVED | NULL_95_LOW | NULL_95_HIGH | VERDICT",
             "----------|----------|-------------|--------------|--------"]
    lines.extend("%s | %.4f | %.4f | %.4f | %s" %
                 (row["statistic"], row["observed"], row["low"], row["high"], row["verdict"])
                 for row in rows)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Calibrated null for max-loser-WP.")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE)
    parser.add_argument("--report-dir", type=Path, default=_REPO / "data" / "ab_reports")
    parser.add_argument("--simulations", type=int, default=2000)
    args = parser.parse_args(argv)
    store, report_path = discover_store(args.cache_root), _latest_report(args.report_dir)
    if store is None or report_path is None:
        print("MISSING TICK STORE OR WP DIAGNOSTICS REPORT")
        return 0
    ticks = load_ticks(store)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    peaks = report["max_loser_wp"].get("per_game", [])
    null = simulate_null(path_parameters(ticks), len(peaks), args.simulations)
    print("STORE: %s" % store)
    print("OBSERVED_REPORT: %s" % report_path)
    print(render(compare(observed_statistics(report), null)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
