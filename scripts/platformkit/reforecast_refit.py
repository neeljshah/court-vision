"""Replay the stored corpus and refit serving isotonic calibration.

This is an offline calibration refresh.  Every replay prediction is made with
data from strictly earlier capture dates, then the serving map is fit once on
the complete reforecast set.  Calibration is not an edge claim.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from scripts.platformkit.wp_diag_oos import (
    _game_dates,
    _sport,
)
# discover_store/load_ticks physically live here; wp_diag_oos only re-exported
# them until 725a45aab dropped that re-export line (it moved to
# tick_dedupe.load_ticks_deduped). Import from the defining module.
from scripts.platformkit.ingame_replay_scoreboard import (
    discover_store,
    load_ticks,
)

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_CACHE = Path(os.environ.get(
    "NBA_CACHE_ROOT",
    os.path.join(os.environ.get("NBA_DATA_ROOT", "data"), "cache")))


def _brier(probs: Iterable[float], outcomes: Iterable[float]) -> Optional[float]:
    values = [(float(prob), float(outcome)) for prob, outcome in zip(probs, outcomes)]
    return sum((prob - outcome) ** 2 for prob, outcome in values) / len(values) if values else None


def _murphy(probs: Sequence[float], outcomes: Sequence[float]) -> Dict[str, Any]:
    """Use the available Murphy implementation, with a basic Brier fallback."""
    try:
        from scripts.platformkit import brier_decomposition as module
    except ImportError:
        try:
            from scripts.platformkit import calib_decomp as module
        except ImportError:
            return {"status": "BASIC_BRIER", "n": len(probs),
                    "brier": _brier(probs, outcomes)}
    function = getattr(module, "decompose", None)
    if function is None:
        function = getattr(module, "murphy_decomposition", None)
    if function is None:
        return {"status": "BASIC_BRIER", "n": len(probs),
                "brier": _brier(probs, outcomes)}
    return dict(function(probs, outcomes))


def _fit(prior: Sequence[Dict[str, Any]]) -> Any:
    outcomes = {float(tick["outcome"]) for tick in prior}
    if not prior or len(outcomes) < 2:
        return None
    from sklearn.isotonic import IsotonicRegression

    model = IsotonicRegression(out_of_bounds="clip")
    model.fit([float(tick["model_prob"]) for tick in prior],
              [float(tick["outcome"]) for tick in prior])
    return model


def _reforecast(ticks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Replay each game with an expanding, prior-date-only isotonic chain."""
    dates = _game_dates(ticks)
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for tick in ticks:
        grouped[str(tick["game"])].append(tick)
    games = sorted(grouped, key=lambda game: (dates[game], game))
    output: List[Dict[str, Any]] = []
    model = None
    fitted_date: Optional[str] = None
    for game in games:
        date = dates[game]
        if date != fitted_date:
            prior = [tick for tick in ticks if dates[str(tick["game"])] < date]
            model = _fit(prior)
            fitted_date = date
        for tick in sorted(grouped[game], key=lambda row: str(row["timestamp"])):
            raw = float(tick["model_prob"])
            value = raw if model is None else float(model.predict([raw])[0])
            output.append({**tick, "reforecast_prob": max(0.0, min(1.0, value))})
    return output


def _safe_tag(version_tag: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(version_tag)).strip("._")
    return value or "version"


def _fit_artifact(rows: Sequence[Dict[str, Any]], sport: str, version_tag: str,
                  output_dir: Path) -> tuple[Path, Dict[str, Any]]:
    from scripts.platformkit.serving_calibration import ServingCalibrator

    raw = [float(row["model_prob"]) for row in rows]
    reforecast = [float(row["reforecast_prob"]) for row in rows]
    outcomes = [float(row["outcome"]) for row in rows]
    calibrator = ServingCalibrator()
    calibrator.fit(reforecast, outcomes)
    x_values = calibrator.x_thresholds
    y_values = calibrator.y_thresholds
    calibrated = calibrator.apply(reforecast)
    verification = {
        "raw": {"brier": _brier(raw, outcomes), "murphy": _murphy(raw, outcomes)},
        "reforecast_calibrated": {
            "brier": _brier(calibrated, outcomes),
            "murphy": _murphy(calibrated, outcomes),
        },
    }
    artifact = {
        "sport": sport,
        "version_tag": version_tag,
        "method": "isotonic",
        "n_reforecast_ticks": len(rows),
        "x_thresholds": x_values,
        "y_thresholds": y_values,
        "breakpoints": {"x": x_values, "y": y_values},
        "verification": verification,
        "honesty": "CALIBRATION only; no edge claim implied",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / ("serving_isotonic_%s_%s.json" % (sport, _safe_tag(version_tag)))
    calibrator.save(path)
    persisted = json.loads(path.read_text(encoding="ascii"))
    persisted.update(artifact)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(persisted, indent=2, sort_keys=True) + "\n", encoding="ascii")
    temporary.replace(path)
    return path, verification


def replay_and_refit(
    version_tag: str,
    *,
    cache_root: Optional[Path] = None,
    output_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Replay the full stored tick corpus and write serving maps and ledger."""
    root = output_root or (_REPO / "data")
    store = discover_store(cache_root or _DEFAULT_CACHE)
    if store is None:
        return {"status": "NO_PARSEABLE_TICK_STORE", "version_tag": version_tag, "artifacts": []}
    ticks = load_ticks(store)
    by_sport: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in _reforecast(ticks):
        by_sport[_sport(row).lower()].append(row)
    ledger = root / "ab_reports" / "reforecast_ledger.jsonl"
    results: List[Dict[str, Any]] = []
    for sport, rows in sorted(by_sport.items()):
        if not rows:
            continue
        path, verification = _fit_artifact(rows, sport, version_tag, root / "models_calib")
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "version_tag": version_tag,
            "sport": sport,
            "artifact": str(path),
            "corpus_ticks": sum(1 for tick in ticks if _sport(tick).lower() == sport),
            "reforecast_ticks": len(rows),
            "brier_raw": verification["raw"]["brier"],
            "brier_reforecast_calibrated": verification["reforecast_calibrated"]["brier"],
            "murphy_raw": verification["raw"]["murphy"],
            "murphy_reforecast_calibrated": verification["reforecast_calibrated"]["murphy"],
            "verification": verification,
            "note": "Calibration verification only; no edge claim implied.",
        }
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a", encoding="ascii") as handle:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n")
        results.append(row)
    return {"status": "OK", "version_tag": version_tag, "artifacts": results}


__all__ = ["replay_and_refit"]
