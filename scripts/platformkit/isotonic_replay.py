"""Offline walk-forward isotonic replay for stored MLB in-game paths."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from scripts.platformkit.ingame_replay_scoreboard import discover_store, load_ticks
from scripts.platformkit.wp_diag_oos import _folds, _game_dates, walk_forward_isotonic

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_CACHE = Path(r"C:\Users\neelj\nba-ai-system\data\cache")
_QUANTILES = (0.0, 0.25, 0.5, 0.75, 0.9, 1.0)


def _brier(rows: Iterable[Dict[str, Any]], field: str) -> Optional[float]:
    values = [(row[field], row["outcome"]) for row in rows if row.get(field) is not None]
    return sum((prob - outcome) ** 2 for prob, outcome in values) / len(values) if values else None


def _quantile(values: Sequence[float], percentile: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    low, high = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _reliability(rows: Sequence[Dict[str, Any]], field: str) -> List[Dict[str, Any]]:
    bins: List[List[Dict[str, Any]]] = [[] for _ in range(10)]
    for row in rows:
        if row.get(field) is not None:
            bins[min(9, int(row[field] * 10))].append(row)
    return [{"bin": "%0.1f-%0.1f" % (i / 10, (i + 1) / 10), "n": len(group),
             "mean_probability": (sum(x[field] for x in group) / len(group) if group else None),
             "observed_win_freq": (sum(x["outcome"] for x in group) / len(group) if group else None)}
            for i, group in enumerate(bins)]


def _oos_paths(ticks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach predictions fit strictly on earlier capture dates, fold-for-fold."""
    dates, output = _game_dates(ticks), []
    for train_dates, test_dates in _folds(list(dates.values())):
        train_games = {game for game, date in dates.items() if date in train_dates}
        test_games = {game for game, date in dates.items() if date in test_dates}
        train = [tick for tick in ticks if tick["game"] in train_games]
        test = [tick for tick in ticks if tick["game"] in test_games]
        if not train or not test or len({tick["outcome"] for tick in train}) < 2:
            continue
        from sklearn.isotonic import IsotonicRegression
        model = IsotonicRegression(out_of_bounds="clip")
        model.fit([tick["model_prob"] for tick in train], [tick["outcome"] for tick in train])
        for tick, prediction in zip(test, model.predict([tick["model_prob"] for tick in test])):
            output.append({**tick, "isotonic_prob": float(prediction)})
    return output


def replay(ticks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build KXMLBGAME-only OOS corrected paths and their calibration evidence."""
    mlb = [tick for tick in ticks if tick["game"].startswith("KXMLBGAME")]
    corrected = _oos_paths(mlb)
    baseline = walk_forward_isotonic(mlb)["pooled"]
    raw_brier, corrected_brier = _brier(corrected, "model_prob"), _brier(corrected, "isotonic_prob")
    if raw_brier is not None and abs(raw_brier - baseline["brier_before"]) > 1e-12:
        raise AssertionError("OOS Brier differs from wp_diag_oos pooled result")
    games: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in corrected:
        games[row["game"]].append(row)
    loser_peaks = [(max(row["model_prob"] for row in group), game)
                   for game, group in games.items() if group and group[0]["outcome"] == 0.0]
    selected = [game for _, game in sorted(loser_peaks, reverse=True)[:6]]
    raw_peaks = [max(row["model_prob"] for row in group) for group in games.values()
                 if group and group[0]["outcome"] == 0.0]
    corrected_peaks = [max(row["isotonic_prob"] for row in group) for group in games.values()
                       if group and group[0]["outcome"] == 0.0]
    return {"rows": corrected, "selected_games": selected,
            "summary": {"game_count": len(games), "oos_tick_count": len(corrected),
                        "oos_brier": {"raw": raw_brier, "corrected": corrected_brier,
                                      "wp_diag_oos_raw": baseline["brier_before"],
                                      "consistency_tolerance": 1e-12},
                        "loser_peak_quantiles": {"quantiles": list(_QUANTILES),
                            "raw": [_quantile(raw_peaks, q) for q in _QUANTILES],
                            "corrected": [_quantile(corrected_peaks, q) for q in _QUANTILES]},
                        "reliability": {"raw": _reliability(corrected, "model_prob"),
                                        "corrected": _reliability(corrected, "isotonic_prob")}}}


def write_artifacts(result: Dict[str, Any], output_dir: Path) -> Path:
    """Write only requested offline replay artifacts, one CSV for each selected game."""
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = set(result["selected_games"])
    for game in sorted(selected):
        path = output_dir / (game + ".csv")
        rows = sorted((row for row in result["rows"] if row["game"] == game), key=lambda row: row["timestamp"])
        with path.open("w", newline="", encoding="ascii") as handle:
            writer = csv.DictWriter(handle, fieldnames=["ts", "raw_model_prob", "isotonic_prob", "market_prob", "outcome"])
            writer.writeheader()
            writer.writerows({"ts": row["timestamp"], "raw_model_prob": row["model_prob"],
                              "isotonic_prob": row["isotonic_prob"], "market_prob": row["market_prob"],
                              "outcome": row["outcome"]} for row in rows)
    summary = output_dir / "summary.json"
    summary.write_text(json.dumps({"selected_games": result["selected_games"], **result["summary"]}, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return summary


def render(result: Dict[str, Any]) -> str:
    summary = result["summary"]
    brier = summary["oos_brier"]
    lines = ["OFFLINE MLB ISOTONIC REPLAY", "METRIC | RAW | CORRECTED", "OOS BRIER | %.6f | %.6f" %
             (brier["raw"], brier["corrected"]), "LOSER PEAK QUANTILES", "Q | RAW | CORRECTED"]
    lines.extend("%.2f | %.6f | %.6f" % (q, raw, corrected) for q, raw, corrected in
                 zip(summary["loser_peak_quantiles"]["quantiles"], summary["loser_peak_quantiles"]["raw"],
                     summary["loser_peak_quantiles"]["corrected"]))
    lines.append("CORRECTED GAMES: " + (", ".join(result["selected_games"]) or "NONE"))
    lines.append("LIVE PATH UNCHANGED: OFFLINE REPLAY EVIDENCE ONLY")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Replay MLB paths with walk-forward isotonic calibration.")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE)
    parser.add_argument("--output-dir", type=Path, default=_REPO / "data" / "ab_reports" / "corrected_paths")
    args = parser.parse_args(argv)
    store = discover_store(args.cache_root)
    if store is None:
        print("NO PARSEABLE TICK STORE")
        print("LIVE PATH UNCHANGED: OFFLINE REPLAY EVIDENCE ONLY")
        return 0
    result = replay(load_ticks(store))
    summary = write_artifacts(result, args.output_dir)
    print(render(result))
    print("SUMMARY: %s" % summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
