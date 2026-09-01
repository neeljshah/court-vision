"""Evaluate shadow eligibility before any arm can be considered for serving."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from scripts.platformkit.ingame.arm_registry import FEATURE_MANIFEST, MARKET_GUARD, verdict
from scripts.platformkit.ingame_replay_scoreboard import discover_store, load_ticks

ARM_NAMES = ("gap_blend", "gap_offset", "gap_regime")


def _manifest_rows(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [row for row in rows if all(row.get(name) is not None for name in FEATURE_MANIFEST)]


def evaluate(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Return gate evidence; absent joined inputs are an honest hard stop."""
    ticks = list(rows)
    joined = _manifest_rows(ticks)
    officials = sum(bool(row.get("officials")) for row in ticks)
    base = {"cache_ticks": len(ticks), "manifest_ticks": len(joined),
            "officials_nonempty_rows": officials, "market_guard": MARKET_GUARD,
            "walk_forward": False, "truncation_invariant": False,
            "corpora": 0, "null_shuffle_z": None}
    reports = {}
    for name in ARM_NAMES:
        reports[name] = {**base, "verdict": verdict(None, None, 0, None, False)}
    return {"feature_manifest": list(FEATURE_MANIFEST), "officials_excluded": True,
            "arms": reports}


def main() -> int:
    store = discover_store(Path(r"C:\Users\neelj\nba-ai-system\data\cache"))
    rows = load_ticks(store) if store else []
    print(json.dumps(evaluate(rows), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
