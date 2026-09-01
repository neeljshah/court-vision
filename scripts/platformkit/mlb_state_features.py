"""Build leak-free, per-tick MLB state features from stored in-game summaries.

`pitch_count` and `times_through_order` deliberately remain continuous numeric
features.  Brill (JQAS, 2023) finds pitcher decline continuous in batters
faced, rather than a step function at times-through-order boundaries.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

import pandas as pd

from scripts.platformkit.wp_diag_series import candidate_dirs, load_records

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_CACHE = _REPO / "data" / "cache"
_BASE_OUT_COLUMNS = ["base_out_%d" % index for index in range(24)]
_FEATURE_COLUMNS = ["score_diff", "inning_progress", "leverage_proxy", "run_expectancy",
                    "balls", "strikes", "pitch_count", "times_through_order",
                    "batters_faced_continuous", "pitch_tempo_seconds",
                    "score_change_recency", *_BASE_OUT_COLUMNS]
_PA_PITCHES = 4.0


class State(TypedDict):
    home_score: Optional[float]
    away_score: Optional[float]
    inning: Optional[int]
    half: Optional[str]
    outs: Optional[int]
    base_state: Optional[int]
    run_expectancy: Optional[float]
    balls: Optional[int]
    strikes: Optional[int]
    pitch_count: Optional[float]
    times_through_order: Optional[float]


def _number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> Optional[int]:
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def _values(summary: Any) -> Dict[str, Any]:
    if isinstance(summary, dict):
        return summary
    if not isinstance(summary, str):
        return {}
    try:
        value = json.loads(summary)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    return dict(re.findall(r"([A-Za-z_]+)=([^\s]+)", summary))


def parse_state(summary: Any) -> State:
    """Parse a state summary safely; malformed or absent fields become ``None``."""
    values = _values(summary)
    count = str(values.get("count", ""))
    match = re.fullmatch(r"(\d+)-(\d+)", count)
    return {"home_score": _number(values.get("home_score")),
            "away_score": _number(values.get("away_score")),
            "inning": _integer(values.get("inning")),
            "half": str(values["half"]).lower() if values.get("half") is not None else None,
            "outs": _integer(values.get("outs")),
            "base_state": _integer(values.get("base", values.get("base_state"))),
            "run_expectancy": _number(values.get("re", values.get("run_expectancy"))),
            "balls": int(match.group(1)) if match else _integer(values.get("balls")),
            "strikes": int(match.group(2)) if match else _integer(values.get("strikes")),
            "pitch_count": _number(values.get("pitch_count")),
            "times_through_order": _number(values.get("tto", values.get("times_through_order")))}


def _timestamp_series(ticks: pd.DataFrame) -> pd.Series:
    column = "timestamp" if "timestamp" in ticks else "ts"
    if column not in ticks:
        raise KeyError("ticks_df needs timestamp or ts")
    values = ticks[column]
    parsed = (pd.to_datetime(values, unit="s", utc=True, errors="coerce")
              if pd.api.types.is_numeric_dtype(values) else pd.to_datetime(values, utc=True, errors="coerce"))
    if parsed.isna().any():
        raise ValueError("ticks_df has an invalid timestamp")
    assert parsed.is_monotonic_increasing, "ticks_df timestamps must be monotone"
    return parsed


def _state_value(value: Optional[float], default: float = 0.0) -> float:
    return default if value is None else float(value)


def game_state_features(ticks_df: pd.DataFrame) -> pd.DataFrame:
    """Return model-ready state features using only information available per tick."""
    result = ticks_df.copy().reset_index(drop=True)
    if result.empty:
        for column in _FEATURE_COLUMNS:
            result[column] = pd.Series(dtype="float64")
        return result
    timestamps = _timestamp_series(result)
    games = result["game"] if "game" in result else pd.Series("single_game", index=result.index)
    summaries = result["state_summary"] if "state_summary" in result else pd.Series(None, index=result.index)
    tempo_values: Dict[tuple[str, int, str], List[float]] = defaultdict(list)
    last_tick: Dict[tuple[str, int, str], pd.Timestamp] = {}
    prior_score: Dict[str, tuple[float, float]] = {}
    last_score_tick: Dict[str, int] = {}
    game_ticks: Dict[str, int] = defaultdict(int)
    rows: List[Dict[str, float]] = []
    for index, (game_value, summary, stamp) in enumerate(zip(games, summaries, timestamps)):
        game, state = str(game_value), parse_state(summary)
        home, away = _state_value(state["home_score"]), _state_value(state["away_score"])
        inning = int(_state_value(state["inning"]))
        half = state["half"] or "top"
        outs, base = int(_state_value(state["outs"])), int(_state_value(state["base_state"]))
        progress = float(inning) + (0.5 if half == "bottom" else 0.0)
        key = (game, inning, half)
        prior = last_tick.get(key)
        if prior is not None:
            tempo_values[key].append(max(0.0, (stamp - prior).total_seconds()))
        last_tick[key] = stamp
        score = (home, away)
        if game not in prior_score or score != prior_score[game]:
            last_score_tick[game] = game_ticks[game]
        prior_score[game] = score
        base_out = min(7, max(0, base)) * 3 + min(2, max(0, outs))
        row = {"score_diff": home - away, "inning_progress": progress,
               "leverage_proxy": abs(home - away) / max(0.5, 9.0 - progress),
               "run_expectancy": _state_value(state["run_expectancy"]),
               "balls": _state_value(state["balls"]), "strikes": _state_value(state["strikes"]),
               "pitch_count": _state_value(state["pitch_count"]),
               "times_through_order": _state_value(state["times_through_order"]),
               "batters_faced_continuous": _state_value(state["pitch_count"]) / _PA_PITCHES,
               "pitch_tempo_seconds": float(pd.Series(tempo_values[key]).median()) if tempo_values[key] else 0.0,
               "score_change_recency": float(game_ticks[game] - last_score_tick[game])}
        row.update({column: float(int(position == base_out))
                    for position, column in enumerate(_BASE_OUT_COLUMNS)})
        rows.append(row)
        game_ticks[game] += 1
    return pd.concat([result, pd.DataFrame(rows)], axis=1)


def _mlb(record: Dict[str, Any]) -> bool:
    sport = str(record.get("raw", {}).get("sport", "")).lower()
    return sport == "mlb" or str(record.get("game", "")).startswith("KXMLBGAME")


def load_mlb_ticks(cache_root: Path) -> pd.DataFrame:
    """Load MLB records through the shared normalized tick-store loader."""
    rows = []
    for store in candidate_dirs(cache_root):
        for record in load_records(store):
            if _mlb(record):
                rows.append({key: record.get(key) for key in ("game", "timestamp", "model_prob", "market_prob", "outcome")}
                            | {"state_summary": record.get("raw", {}).get("state_summary")})
    return pd.DataFrame(rows).sort_values(["timestamp", "game"], kind="stable").reset_index(drop=True) if rows else pd.DataFrame(columns=["game", "timestamp", "state_summary"])


def coverage_summary(ticks: pd.DataFrame, features: pd.DataFrame) -> str:
    """Render an ASCII-only state coverage summary."""
    present = int(ticks.get("state_summary", pd.Series(dtype=object)).notna().sum())
    parsed = sum(parse_state(value)["inning"] is not None for value in ticks.get("state_summary", []))
    return "\n".join(["MLB STATE FEATURES", "TICKS: %d" % len(ticks),
                        "STATE_SUMMARY_PRESENT: %d" % present, "STATE_PARSED: %d" % parsed,
                        "FEATURE_ROWS: %d" % len(features), "BASE_OUT_ONE_HOT_COLUMNS: 24"])


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build MLB in-game state-only feature ticks.")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=_REPO / "data" / "ab_reports" / "mlb_state_features.parquet")
    args = parser.parse_args(argv)
    ticks, features = load_mlb_ticks(args.cache_root), None
    features = game_state_features(ticks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(args.output, index=False)
    print(coverage_summary(ticks, features))
    print("OUTPUT: %s" % args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
