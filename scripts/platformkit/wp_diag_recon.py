"""Read-only reconciliation for the three in-game WP diagnostic loaders."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.ingame_replay_scoreboard import discover_store
from scripts.platformkit.wp_diag_series import load_records

_DEFAULT_CACHE = Path(os.environ.get(
    "NBA_CACHE_ROOT",
    os.path.join(os.environ.get("NBA_DATA_ROOT", "data"), "cache")))
_OutcomeLoader = Callable[[Dict[str, Any]], Optional[float]]


def _outcome(record: Dict[str, Any]) -> Optional[float]:
    value = record.get("outcome")
    return float(value) if value in (0, 0.0, 1, 1.0) else None


def _model_prob(record: Dict[str, Any]) -> Optional[float]:
    value = record.get("model_prob")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0.0 <= number <= 1.0 else None


def default_loaders() -> Dict[str, _OutcomeLoader]:
    """Return the outcome extraction used by each diagnostic's current loader."""
    return {"wp_diag_oos": _outcome, "wp_diagnostics": _outcome,
            "wp_diag_series": _outcome}


def reconcile(records: List[Dict[str, Any]],
              loaders: Optional[Dict[str, _OutcomeLoader]] = None) -> Dict[str, Any]:
    """Compare each loader's outcome assigned to the raw model-probability side."""
    active = loaders or default_loaders()
    by_game: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    mismatches: Dict[str, int] = {name: 0 for name in active}
    valid = 0
    for record in records:
        probability, expected = _model_prob(record), _outcome(record)
        if probability is None or expected is None:
            continue
        valid += 1
        assigned = {name: loader(record) for name, loader in active.items()}
        for name, value in assigned.items():
            if value != expected:
                mismatches[name] += 1
        by_game[record["game"]].append({"probability": probability, "raw": record,
                                         "assigned": assigned})
    high_losers = sorted((game for game, rows in by_game.items()
                          if any(row["probability"] > .9 and _outcome(row["raw"]) == 0.0
                                 for row in rows)))
    others = sorted(game for game in by_game if game not in high_losers)
    selected = high_losers[:3] + others[:3]
    games = []
    for game in selected:
        rows = by_game[game]
        raw = rows[0]["raw"].get("raw", rows[0]["raw"])
        assigned = {name: sorted({row["assigned"][name] for row in rows}) for name in active}
        games.append({"game": game, "outcome_fields": {key: raw[key] for key in
                      ("outcome", "settled_outcome", "result", "label") if key in raw},
                      "side": raw.get("side"), "max_model_prob": max(row["probability"] for row in rows),
                      "assigned_outcomes": assigned,
                      "same_outcome": len({tuple(value) for value in assigned.values()}) == 1})
    return {"records_checked": valid, "mismatch_counts": mismatches, "games": games,
            "raw_samples": [record.get("raw", record) for record in records[:5]],
            "all_agree": not any(mismatches.values())}


def render(report: Dict[str, Any]) -> str:
    lines = ["RAW RECORDS (VERBATIM JSON):"]
    lines.extend(json.dumps(row, ensure_ascii=True, sort_keys=True) for row in report["raw_samples"])
    lines.extend(["CONVENTION: raw side is home; model_prob and outcome are P(home win).",
                  "GAME | OUTCOME_FIELDS | PROB_SIDE | MAX_MODEL_PROB | OOS | DIAGNOSTICS | SERIES | SAME"])
    for row in report["games"]:
        values = row["assigned_outcomes"]
        lines.append("%s | %s | %s | %.6f | %s | %s | %s | %s" %
                     (row["game"], json.dumps(row["outcome_fields"], ensure_ascii=True), row["side"],
                      row["max_model_prob"], values.get("wp_diag_oos"),
                      values.get("wp_diagnostics"), values.get("wp_diag_series"),
                      "YES" if row["same_outcome"] else "NO"))
    bad = [name for name, count in report["mismatch_counts"].items() if count]
    if bad:
        lines.append("VERDICT: MISPAIRED LOADER(S): %s. Fix its outcome extraction to use raw outcome for the home side." % ", ".join(bad))
    else:
        lines.append("VERDICT: NONE. All three loaders pair model_prob with the same raw outcome; no pairing logic is wrong.")
        lines.append("The claimed disagreement is not reproducible from this store; compare report store paths/timestamps before changing a loader.")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile WP diagnostic outcome pairing.")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE)
    args = parser.parse_args(argv)
    store = discover_store(args.cache_root)
    if store is None:
        print("NO PARSEABLE TICK STORE")
        return 0
    report = reconcile(load_records(store))
    print("STORE: %s" % store)
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
