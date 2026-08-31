"""Score settled in-game paper-prediction ticks by game phase or tick quintile.

Read-only input discovery defaults to the private cache.  Reports are calibration
diagnostics only: lower Brier is better and no market edge is inferred.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_CACHE = Path(r"C:\Users\neelj\nba-ai-system\data\cache")
_NAME_HINTS = ("ingame_grade", "paper", "pm_paper")
_PROB_KEYS = ("model_prob", "model_probability", "probability", "prob")
_MARKET_KEYS = ("market_prob", "market_probability", "implied_prob")
_TIME_KEYS = ("ts", "timestamp", "captured_at", "created_at")
_GAME_KEYS = ("game_id", "game_key", "market_id", "event_id")
_OUTCOME_KEYS = ("outcome", "settled_outcome", "result", "label")
_PHASE_KEYS = ("game_phase", "phase", "period", "inning", "quarter")


def _value(row: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
    return next((row[key] for key in keys if row.get(key) is not None), None)


def _prob(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0.0 <= number <= 1.0 else None


def _normalise(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    model, outcome = _prob(_value(row, _PROB_KEYS)), _prob(_value(row, _OUTCOME_KEYS))
    game, stamp = _value(row, _GAME_KEYS), _value(row, _TIME_KEYS)
    if model is None or outcome not in (0.0, 1.0) or game is None or stamp is None:
        return None
    return {"game": str(game), "timestamp": str(stamp), "model_prob": model,
            "market_prob": _prob(_value(row, _MARKET_KEYS)),
            "phase": _value(row, _PHASE_KEYS)}


def _first_row(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    return value
    except OSError:
        return None
    return None


def candidate_dirs(cache_root: Path) -> List[Path]:
    """Return deterministic, named candidate stores without modifying them."""
    if not cache_root.is_dir():
        return []
    return sorted((path for path in cache_root.rglob("*") if path.is_dir()
                   and any(hint in path.name.lower() for hint in _NAME_HINTS)),
                  key=lambda path: str(path).lower())


def discover_store(cache_root: Path) -> Optional[Path]:
    """Find the first JSONL store whose ticks include a settled binary outcome."""
    for directory in candidate_dirs(cache_root):
        for path in sorted(directory.rglob("*.jsonl"), key=lambda item: str(item).lower()):
            row = _first_row(path)
            if row is not None and _normalise(row) is not None:
                return directory
    return None


def load_ticks(store: Path) -> List[Dict[str, Any]]:
    ticks: List[Dict[str, Any]] = []
    for path in sorted(store.rglob("*.jsonl"), key=lambda item: str(item).lower()):
        try:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(raw, dict):
                        tick = _normalise(raw)
                        if tick is not None:
                            tick["outcome"] = float(_value(raw, _OUTCOME_KEYS))
                            ticks.append(tick)
        except OSError:
            continue
    return ticks


def _brier(ticks: Iterable[Dict[str, Any]], field: str) -> Optional[float]:
    pairs = [(tick[field], tick["outcome"]) for tick in ticks if tick.get(field) is not None]
    if not pairs:
        return None
    return sum((prob - outcome) ** 2 for prob, outcome in pairs) / len(pairs)


def score_ticks(ticks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return one calibration row per game and phase/quintile bucket."""
    games: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for tick in ticks:
        games[tick["game"]].append(tick)
    rows: List[Dict[str, Any]] = []
    for game, game_ticks in sorted(games.items()):
        ordered = sorted(game_ticks, key=lambda tick: tick["timestamp"])
        has_phase = all(tick.get("phase") not in (None, "") for tick in ordered)
        buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for index, tick in enumerate(ordered):
            name = str(tick["phase"]) if has_phase else "Q%d" % (min(4, index * 5 // len(ordered)) + 1)
            buckets[name].append(tick)
        for bucket, group in buckets.items():
            enough = len(group) >= 30
            rows.append({"game": game, "bucket": bucket, "n": len(group),
                         "model_brier": _brier(group, "model_prob") if enough else None,
                         "market_brier": _brier(group, "market_prob") if enough else None,
                         "status": "OK" if enough else "INSUFFICIENT"})
    return rows


def render(rows: List[Dict[str, Any]]) -> str:
    lines = ["GAME | BUCKET | N | MODEL_BRIER | MARKET_BRIER | STATUS",
             "-----|--------|---|-------------|--------------|-------"]
    for row in rows:
        model = "-" if row["model_brier"] is None else "%.6f" % row["model_brier"]
        market = "-" if row["market_brier"] is None else "%.6f" % row["market_brier"]
        lines.append("%s | %s | %d | %s | %s | %s" %
                     (row["game"], row["bucket"], row["n"], model, market, row["status"]))
    return "\n".join(lines)


def write_report(rows: List[Dict[str, Any]], store: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = output_dir / ("ingame_replay_%s.json" % stamp)
    report.write_text(json.dumps({"generated_at": stamp, "store": str(store), "rows": rows},
                                 indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Replay settled in-game paper ticks.")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE)
    parser.add_argument("--output-dir", type=Path, default=_REPO / "data" / "ab_reports")
    args = parser.parse_args(argv)
    candidates = candidate_dirs(args.cache_root)
    print("CANDIDATES: " + (", ".join(str(path) for path in candidates) or "NONE"))
    store = discover_store(args.cache_root)
    if store is None:
        print("NO PARSEABLE TICK STORE")
        return 0
    rows = score_ticks(load_ticks(store))
    print("STORE: %s" % store)
    print(render(rows))
    print("REPORT: %s" % write_report(rows, store, args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
