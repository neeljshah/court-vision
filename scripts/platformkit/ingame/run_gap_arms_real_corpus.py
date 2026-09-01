"""Run the preregistered in-game gap arms on the stored real corpus."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from scripts.platformkit.ingame import gap_blend_arm, gap_offset_arm, gap_regime_arm
from scripts.platformkit.ingame_replay_scoreboard import discover_store
from scripts.platformkit.ingame_state_lift import _window_ids
from scripts.platformkit.mlb_state_features import _FEATURE_COLUMNS, drop_unparsed, game_state_features
from scripts.platformkit.wp_diag_series import load_records

_BASELINE_TICKS = 144424
_BASELINE_WINDOW_TICKS = 14802


def _load_ticks(store: Path) -> tuple[List[Dict[str, Any]], pd.DataFrame]:
    """Load canonical MLB observations and their same-row state features."""
    canonical = store / "mlb"
    if not canonical.is_dir():
        raise ValueError("expected canonical MLB store: %s" % canonical)
    canonical_ticks = load_records(canonical)
    feature_source = pd.DataFrame([{**tick, "state_summary": tick["raw"].get("state_summary")}
                                   for tick in canonical_ticks]).sort_values(
        ["timestamp", "game"], kind="stable").reset_index(drop=True)
    features = game_state_features(feature_source)
    features = drop_unparsed(features)
    features = features[["game", "timestamp", "state_parsed", "parse_quality", *_FEATURE_COLUMNS]]
    features = features.drop_duplicates(["game", "timestamp"], keep="first")
    usable_keys = set(zip(features["game"], features["timestamp"]))
    # The cache contains a cloned ``mlb_clean`` tree.  Retaining it would make
    # the feature join many-to-one, so score the canonical real observations once.
    ticks, seen = [], set()
    for tick in canonical_ticks:
        key = (tick["game"], tick["timestamp"])
        if key not in usable_keys or key in seen:
            continue
        seen.add(key)
        ticks.append({**tick, "state_summary": tick["raw"].get("state_summary")})
    for row_id, tick in enumerate(ticks):
        tick["_row_id"] = row_id
        tick["in_window"] = False
    window_ids = _window_ids(ticks)
    for tick in ticks:
        tick["in_window"] = tick["_row_id"] in window_ids
    return ticks, features


def _assert_walk_forward(report: Dict[str, Any]) -> None:
    """Fail closed unless every scored fold ends before its real test date."""
    for fold in report.get("folds", []):
        if fold.get("status") != "OK":
            continue
        if "train_date_max" in fold:
            assert fold["train_date_max"] < fold["test_date_min"]


def _attach_blend_signal(ticks: List[Dict[str, Any]], features: pd.DataFrame) -> List[Dict[str, Any]]:
    """Attach E4's preregistered observed score-differential state signal."""
    signal = features.set_index(["game", "timestamp"])["score_diff"].to_dict()
    rows = []
    for tick in ticks:
        value = signal[(tick["game"], tick["timestamp"])]
        if pd.notna(value):
            rows.append({**tick, "state_signal": float(value)})
    return rows


def evaluate(cache_root: Path, bootstrap_iterations: int = 300) -> Dict[str, Any]:
    """Evaluate E1, E2, and E4 using strict prior-date walk-forward splits."""
    store = discover_store(cache_root)
    if store is None:
        raise ValueError("no parseable tick store under %s" % cache_root)
    ticks, features = _load_ticks(store)
    assert "market_prob" not in features.columns
    assert all("market" not in column.lower() for column in features.columns)
    blend = gap_blend_arm.evaluate(_attach_blend_signal(ticks, features), bootstrap_iterations=bootstrap_iterations)
    regime = gap_regime_arm.evaluate(ticks, bootstrap_iterations=bootstrap_iterations)
    offset = gap_offset_arm.evaluate(ticks, features, bootstrap_iterations=bootstrap_iterations)
    for report in (blend, regime, offset):
        _assert_walk_forward(report)
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "store": str(store),
            "n_ticks": len(ticks), "n_window_ticks": sum(tick["in_window"] for tick in ticks),
            "baseline_corpus": {"n_ticks": _BASELINE_TICKS, "n_window_ticks": _BASELINE_WINDOW_TICKS,
                                "matches": len(ticks) == _BASELINE_TICKS and
                                sum(tick["in_window"] for tick in ticks) == _BASELINE_WINDOW_TICKS},
            "e4_guarded_logit_blend": blend, "e2_regime": regime, "e1_offset": offset}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run preregistered gap arms on the real corpus.")
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--bootstrap-iterations", type=int, default=300)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.cache_root, args.bootstrap_iterations)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print("REPORT: %s" % args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
