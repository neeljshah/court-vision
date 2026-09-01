"""Compare stored model and market calibration around detected score changes."""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from scripts.platformkit.ingame_replay_scoreboard import candidate_dirs
from scripts.platformkit.market_lag_study import _event, load_records

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_CACHE = Path(os.environ.get(
    "NBA_CACHE_ROOT",
    os.path.join(os.environ.get("NBA_DATA_ROOT", "data"), "cache")))
_WINDOW_SECONDS = 180.0
_BOOTSTRAP_ITERS = 500
_BOOTSTRAP_SEED = 20260831


def _seconds(later: str, earlier: str) -> Optional[float]:
    """Return elapsed seconds for ISO timestamps or numeric timestamp strings."""
    try:
        return float(later) - float(earlier)
    except (TypeError, ValueError):
        try:
            return (datetime.fromisoformat(later.replace("Z", "+00:00")) -
                    datetime.fromisoformat(earlier.replace("Z", "+00:00"))).total_seconds()
        except (AttributeError, ValueError):
            return None


def _paired_briers(ticks: Iterable[Dict[str, Any]]) -> Tuple[int, Optional[float], Optional[float]]:
    pairs = [(tick["model_prob"], tick["market_prob"], tick["outcome"]) for tick in ticks
             if tick.get("model_prob") is not None and tick.get("market_prob") is not None]
    if not pairs:
        return 0, None, None
    return (len(pairs),
            sum((model - outcome) ** 2 for model, _, outcome in pairs) / len(pairs),
            sum((market - outcome) ** 2 for _, market, outcome in pairs) / len(pairs))


def _delta(ticks: Iterable[Dict[str, Any]]) -> Optional[float]:
    _, model, market = _paired_briers(ticks)
    return None if model is None or market is None else market - model


def _quantile(values: Sequence[float], fraction: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low, high = int(position), min(len(ordered) - 1, int(position) + 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _game_groups(records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    games: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        games[record["game"]].append(record)
    return {game: sorted(ticks, key=lambda tick: tick["timestamp"]) for game, ticks in games.items()}


def _classify_game(game: str, ticks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    events = [_event(game, ticks, index) for index in range(1, len(ticks))]
    events = [event for event in events if event is not None]
    if not events:
        return None
    starts = [ticks[event["event_tick"]]["timestamp"] for event in events]
    window = []
    control = []
    for tick in ticks:
        in_window = any((elapsed := _seconds(tick["timestamp"], start)) is not None and
                        0.0 <= elapsed <= _WINDOW_SECONDS for start in starts)
        (window if in_window else control).append(tick)
    return {"game": game, "sport": events[0]["sport"], "events": len(events),
            "window": window, "control": control}


def _bootstrap_ci(games: List[Dict[str, Any]]) -> Optional[List[float]]:
    if not games:
        return None
    randomizer, samples = random.Random(_BOOTSTRAP_SEED), []
    for _ in range(_BOOTSTRAP_ITERS):
        selected = [randomizer.choice(games) for _ in games]
        value = _delta(tick for game in selected for tick in game["window"])
        if value is not None:
            samples.append(value)
    low, high = _quantile(samples, .05), _quantile(samples, .95)
    return None if low is None or high is None else [low, high]


def analyze(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Report paired Brier comparisons inside and outside 180-second score windows."""
    sport_games: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for game, ticks in _game_groups(records).items():
        classified = _classify_game(game, ticks)
        if classified is not None:
            sport_games[classified["sport"]].append(classified)
    summaries = []
    for sport, games in sorted(sport_games.items()):
        window_ticks = [tick for game in games for tick in game["window"]]
        control_ticks = [tick for game in games for tick in game["control"]]
        n_ticks, model, market = _paired_briers(window_ticks)
        control_n, control_model, control_market = _paired_briers(control_ticks)
        summaries.append({"sport": sport, "n_events": sum(game["events"] for game in games),
                          "n_ticks": n_ticks, "brier_model_window": model,
                          "brier_market_window": market,
                          "delta": None if model is None or market is None else market - model,
                          "control_n_ticks": control_n, "brier_model_control": control_model,
                          "brier_market_control": control_market,
                          "control_delta": (None if control_model is None or control_market is None
                                            else control_market - control_model),
                          "window_delta_ci_90": _bootstrap_ci(games)})
    return {"window_seconds": _WINDOW_SECONDS, "bootstrap_iterations": _BOOTSTRAP_ITERS,
            "bootstrap_seed": _BOOTSTRAP_SEED, "summaries": summaries}


def _number(value: Optional[float]) -> str:
    return "-" if value is None else "%.6f" % value


def render(report: Dict[str, Any]) -> str:
    """Render an ASCII-only descriptive calibration scoreboard."""
    lines = ["SPORT | EVENTS | WINDOW_TICKS | MODEL_BRIER | MARKET_BRIER | DELTA | CONTROL_DELTA | CI90",
             "------|--------|--------------|-------------|--------------|-------|---------------|-----"]
    for row in report["summaries"]:
        interval = row["window_delta_ci_90"]
        ci = "-" if interval is None else "[%s, %s]" % (_number(interval[0]), _number(interval[1]))
        lines.append("%s | %d | %d | %s | %s | %s | %s | %s" %
                     (row["sport"], row["n_events"], row["n_ticks"], _number(row["brier_model_window"]),
                      _number(row["brier_market_window"]), _number(row["delta"]),
                      _number(row["control_delta"]), ci))
    lines += ["", "CAVEAT: Offline descriptive comparison on stored ticks; cadence bounds resolution.",
              "CAVEAT: This is NOT an edge claim. A prospective meter is the claim standard."]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare calibration around stored score-event windows.")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE)
    parser.add_argument("--output", type=Path,
                        default=_REPO / "data" / "ab_reports" / "lag_window_calibration.json")
    args = parser.parse_args(argv)
    stores, records = [], []
    for store in candidate_dirs(args.cache_root):
        loaded = load_records(store)
        if loaded:
            stores.append(store)
            records.extend(loaded)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "stores": [str(path) for path in stores],
              **analyze(records)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("STORES: " + (", ".join(str(path) for path in stores) or "NONE"))
    print(render(report))
    print("REPORT: %s" % args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
