"""Emit a reproducible baseline lock for settled in-game tick calibration."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from scripts.platformkit.ingame_replay_scoreboard import discover_store, load_ticks

_PRIOR_DELTA_BRIER = -0.047
_MATCH_TOLERANCE = 0.005
_MIN_GAP_EFFECTIVE_N = 30
_DEFAULT_CACHE = Path(os.environ.get(
    "NBA_CACHE_ROOT", r"C:\Users\neelj\nba-ai-system\data\cache"))


def _brier(ticks: Iterable[Dict[str, Any]], field: str) -> Optional[float]:
    pairs = [(float(tick[field]), float(tick["outcome"])) for tick in ticks
             if tick.get(field) is not None]
    if not pairs:
        return None
    return sum((probability - outcome) ** 2 for probability, outcome in pairs) / len(pairs)


def _file_hash(paths: List[Path], store: Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(store).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _source_rows(paths: Iterable[Path]) -> int:
    count = 0
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            count += sum(1 for _ in handle)
    return count


def _verdict(delta_brier: Optional[float], gap_effective_n: int) -> str:
    if delta_brier is None or gap_effective_n < _MIN_GAP_EFFECTIVE_N:
        return "INSUFFICIENT"
    return "MATCH" if abs(delta_brier - _PRIOR_DELTA_BRIER) <= _MATCH_TOLERANCE else "BEHIND"


def summarize(store: Path) -> Dict[str, Any]:
    """Score the store and return its deterministic calibration fingerprint."""
    paths = sorted(store.rglob("*.jsonl"), key=lambda path: path.as_posix().lower())
    ticks = load_ticks(store)
    eligible = [tick for tick in ticks if tick.get("market_prob") is not None]
    stamps = [str(tick["timestamp"]) for tick in eligible]
    model_brier = _brier(eligible, "model_prob")
    market_brier = _brier(eligible, "market_prob")
    delta_brier = (market_brier - model_brier
                   if model_brier is not None and market_brier is not None else None)
    gap_effective_n = len({str(tick["game"]) for tick in eligible})
    return {
        "corpus": {
            "file_count": len(paths),
            "source_row_count": _source_rows(paths),
            "settled_tick_count": len(ticks),
            "eligible_tick_count": len(eligible),
            "game_count": gap_effective_n,
            "date_range": {"min": min(stamps)[:10] if stamps else None,
                           "max": max(stamps)[:10] if stamps else None},
            "file_hash": _file_hash(paths, store),
        },
        "prior_delta_brier": _PRIOR_DELTA_BRIER,
        "model_brier": model_brier,
        "market_brier": market_brier,
        "delta_brier": delta_brier,
        "gap_effective_n": gap_effective_n,
        "verdict": _verdict(delta_brier, gap_effective_n),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Lock the settled-tick Brier baseline.")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE)
    args = parser.parse_args(argv)
    store = discover_store(args.cache_root)
    if store is None:
        report: Dict[str, Any] = {"corpus": {"file_count": 0, "source_row_count": 0,
                                  "settled_tick_count": 0, "eligible_tick_count": 0,
                                  "game_count": 0, "date_range": {"min": None, "max": None},
                                  "file_hash": None}, "prior_delta_brier": _PRIOR_DELTA_BRIER,
                                  "model_brier": None, "market_brier": None, "delta_brier": None,
                                  "gap_effective_n": 0, "verdict": "INSUFFICIENT"}
    else:
        report = {"store": str(store), **summarize(store)}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
