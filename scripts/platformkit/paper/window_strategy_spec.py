"""Offline absorption-window paper strategy specification and simulator.

This is a benchmark only.  It records hypothetical entries after score events;
it does not arm a live daemon, place wagers, or claim an edge.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from sklearn.isotonic import IsotonicRegression

from scripts.platformkit.market_lag_study import (_event, _seconds, _sport, candidate_dirs,
                                                   load_records)
from scripts.platformkit.wp_diag_oos import _game_dates, walk_forward_isotonic
_REPO = Path(__file__).resolve().parents[3]
_DEFAULT_CACHE = Path(r"C:\Users\neelj\nba-ai-system\data\cache")
_DEFAULT_OUTPUT = _REPO / "data" / "ab_reports" / "window_strategy_replay.json"


@dataclass(frozen=True)
class WindowStrategySpec:
    """Parameters for the score-event absorption benchmark."""

    threshold: float = 0.05
    window_s: float = 159.0
    horizon_ticks: int = 10
def _time_key(value: Any) -> tuple:
    try:
        return (0, float(value))
    except (TypeError, ValueError):
        return (1, str(value))


def _mean(values: Sequence[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None
def _prior_model(ticks: List[Dict[str, Any]], dates: Dict[str, str], game: str,
                cache: Dict[str, Optional[IsotonicRegression]]) -> Optional[IsotonicRegression]:
    if game in cache:
        return cache[game]
    entry_date = dates[game]
    prior_games = {name for name, date in dates.items() if date < entry_date}
    train = [tick for tick in ticks if tick["game"] in prior_games]
    if not train or len({tick["outcome"] for tick in train}) < 2:
        cache[game] = None
        return None
    model = IsotonicRegression(out_of_bounds="clip")
    model.fit([tick["model_prob"] for tick in train], [tick["outcome"] for tick in train])
    cache[game] = model
    return model
def _entry_for_event(game: str, ticks: List[Dict[str, Any]], fit_ticks: List[Dict[str, Any]], event_tick: int,
                     dates: Dict[str, str], spec: WindowStrategySpec,
                     models: Dict[str, Optional[IsotonicRegression]]) -> Optional[Dict[str, Any]]:
    model = _prior_model(fit_ticks, dates, game, models)
    if model is None:
        return None
    event_time = ticks[event_tick]["timestamp"]
    for index in range(event_tick, len(ticks)):
        elapsed = _seconds(ticks[index]["timestamp"], event_time)
        if elapsed is None or elapsed < 0:
            continue
        if elapsed > spec.window_s:
            break
        market = ticks[index].get("market_prob")
        raw_model = ticks[index].get("model_prob")
        if market is None or raw_model is None:
            continue
        corrected = float(model.predict([raw_model])[0])
        gap = corrected - market
        if abs(gap) < spec.threshold:
            continue
        direction = 1.0 if gap > 0 else -1.0
        plus_index = index + spec.horizon_ticks
        market_plus = (ticks[plus_index].get("market_prob")
                       if plus_index < len(ticks) else None)
        clv = (direction * (market_plus - market)
               if market_plus is not None else None)
        outcome = float(ticks[index]["outcome"])
        return {"game": game, "sport": _sport(ticks[event_tick]["raw"], game).lower(),
                "event_tick": event_tick, "entry_tick": index,
                "event_elapsed_s": float(elapsed), "entry_game_date": dates[game],
                "entry_market_prob": float(market), "recalibrated_prob": corrected,
                "raw_model_prob": float(raw_model), "direction": int(direction),
                "outcome": outcome, "win": bool(outcome == (1.0 if direction > 0 else 0.0)),
                "market_prob_plus_10_ticks": market_plus, "clv_proxy_prob_units": clv,
                "exit": "settle"}
    return None


def _summary(sport: str, entries: List[Dict[str, Any]], events: int) -> Dict[str, Any]:
    entry_brier = _mean([(row["recalibrated_prob"] - row["outcome"]) ** 2 for row in entries])
    market_brier = _mean([(row["entry_market_prob"] - row["outcome"]) ** 2 for row in entries])
    clv = _mean([row["clv_proxy_prob_units"] for row in entries
                 if row["clv_proxy_prob_units"] is not None])
    return {"sport": sport, "n_events": events, "n_entries": len(entries),
            "entry_brier": entry_brier, "market_brier": market_brier,
            "mean_clv_proxy_prob_units": clv,
            "n_with_clv_proxy": sum(row["clv_proxy_prob_units"] is not None for row in entries),
            "win_rate": _mean([float(row["win"]) for row in entries])}


def simulate(records: List[Dict[str, Any]], spec: Optional[WindowStrategySpec] = None) -> Dict[str, Any]:
    """Replay score events using only strict-prior isotonic calibration."""
    spec = spec or WindowStrategySpec()
    if spec.threshold < 0 or spec.window_s < 0 or spec.horizon_ticks < 1:
        raise ValueError("threshold/window_s must be nonnegative and horizon_ticks positive")
    games: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        games[record["game"]].append({**record, "raw": record.get("raw") or {}})
    dates = _game_dates(records)
    entries: List[Dict[str, Any]] = []
    event_counts: Dict[str, int] = defaultdict(int)
    calibration: Dict[str, Any] = {}
    fit_by_sport: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        fit_by_sport[_sport(record.get("raw") or {}, record["game"]).lower()].append(record)
    models: Dict[str, Optional[IsotonicRegression]] = {}
    for game, raw_ticks in sorted(games.items()):
        ticks = sorted(raw_ticks, key=lambda tick: _time_key(tick["timestamp"]))
        events = [_event(game, ticks, index) for index in range(1, len(ticks))]
        events = [event for event in events if event is not None]
        if not events:
            continue
        sport = str(events[0]["sport"]).lower()
        event_counts[sport] += len(events)
        for event in events:
            row = _entry_for_event(game, ticks, fit_by_sport[sport], event["event_tick"], dates, spec, models)
            if row is not None:
                entries.append(row)
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in entries:
        grouped[row["sport"]].append(row)
    # Keep the established walk-forward report alongside per-entry fits as an audit trail.
    by_sport: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_sport[_sport(record.get("raw") or {}, record["game"]).lower()].append(record)
    for sport, group in by_sport.items():
        calibration[sport] = walk_forward_isotonic(group)
    sports = sorted(set(event_counts) | set(grouped))
    return {"spec": asdict(spec), "entries": entries,
            "by_sport": {sport: _summary(sport, grouped[sport], event_counts[sport]) for sport in sports},
            "calibration_oos": calibration,
            "honest_verdict": {
                "status": "NEGATIVE_EXPECTED_UNTIL_CONDITIONING_IMPROVES",
                "finding": "lag_window_calibration: current model LOSES in-window",
                "benchmark_purpose": "Conditioning lane must flip this benchmark before live arming.",
                "live_arming": "DISARMED: require a positive prospective month first.",
                "edge_claim": False}}


def replay(records: List[Dict[str, Any]], threshold: float = 0.05,
           window_s: float = 159.0) -> Dict[str, Any]:
    """Compatibility entry point for the offline paper replay."""
    return simulate(records, WindowStrategySpec(threshold=threshold, window_s=window_s))


def render(report: Dict[str, Any]) -> str:
    lines = ["SPORT | EVENTS | ENTRIES | ENTRY_BRIER | MARKET_BRIER | MEAN_CLV_UNITS | WIN_RATE"]
    for row in report["by_sport"].values():
        fmt = lambda value: "-" if value is None else "%.6f" % value
        lines.append("%s | %d | %d | %s | %s | %s | %s" %
                     (row["sport"], row["n_events"], row["n_entries"], fmt(row["entry_brier"]),
                      fmt(row["market_brier"]), fmt(row["mean_clv_proxy_prob_units"]),
                      fmt(row["win_rate"])))
    verdict = report["honest_verdict"]
    lines.extend(["", "VERDICT: %s" % verdict["status"], "FINDING: %s" % verdict["finding"],
                  "LIVE ARMING: %s" % verdict["live_arming"], "EDGE CLAIM: FALSE"])
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Replay the offline absorption-window paper strategy.")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--threshold", type=float, default=0.05)
    parser.add_argument("--window-s", type=float, default=159.0)
    args = parser.parse_args(argv)
    stores, records = [], []
    for store in candidate_dirs(args.cache_root):
        loaded = load_records(store)
        if loaded:
            stores.append(store)
            records.extend(loaded)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "stores": [str(path) for path in stores],
              **replay(records, args.threshold, args.window_s)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(render(report))
    print("REPORT: %s" % args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
