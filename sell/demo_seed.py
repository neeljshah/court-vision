"""sell.demo_seed -- seed a deterministic, read-only demo dataset.

Writes a canned snapshot + a sample signed TrackRecord under
data/frontend/sell/demo/ so a buyer sees a populated, honest UI without
touching real data or the network.

HONESTY RULES (binding):
  * Every number is DETERMINISTIC (seeded with fixed inputs; same output on
    every run) -- never random, never fabricated.
  * No dollar / ROI / P&L / $-edge field on any output artifact.
  * edge_claimed is hard False on every TrackRecord.
  * The calibration block carries status="demo_seed" to make provenance
    obvious; real numbers are never presented as live results.
  * The seed is IDEMPOTENT: calling it twice produces the identical files.

INVARIANTS: <=300 LOC; ASCII only; no secrets in code; no I/O to network;
never writes data/registry/; build only under sell/.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from sell.trackrecord_schema import (
    TRACKRECORD_SCHEMA_VERSION,
    DEFAULT_METHODOLOGY_NOTE,
    TrackRecord,
)

# ---------------------------------------------------------------------------
# Output path (readable; never writes data/registry/)
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parent.parent
DEMO_DIR: Path = Path(
    os.environ.get("SELL_DEMO_DIR", str(_REPO / "data" / "frontend" / "sell" / "demo"))
)

# ---------------------------------------------------------------------------
# Deterministic demo constants (no network, no randomness).
# All numbers below are LABELLED as demo-seed provenance.
# ---------------------------------------------------------------------------
_DEMO_GENERATED_AT = "2026-06-18T12:00:00Z"

_DEMO_GAMES: List[Dict[str, Any]] = [
    {
        "game_id": "DEMO_NBA_20260101_BOS_NYK",
        "sport": "nba",
        "home": "New York Knicks",
        "away": "Boston Celtics",
        "tipoff": "2026-01-01T19:30:00Z",
        "pregame_probs": {
            "home_ml": 0.52,
            "away_ml": 0.48,
        },
        "leak_guard": {"in_sample": False},
        "note": "demo-seed: canned game; not a live prediction",
        "provenance": "demo_seed",
    },
    {
        "game_id": "DEMO_NBA_20260102_GSW_LAL",
        "sport": "nba",
        "home": "Los Angeles Lakers",
        "away": "Golden State Warriors",
        "tipoff": "2026-01-02T20:00:00Z",
        "pregame_probs": {
            "home_ml": 0.47,
            "away_ml": 0.53,
        },
        "leak_guard": {"in_sample": False},
        "note": "demo-seed: canned game; not a live prediction",
        "provenance": "demo_seed",
    },
    {
        "game_id": "DEMO_NBA_20260103_MIL_PHI",
        "sport": "nba",
        "home": "Philadelphia 76ers",
        "away": "Milwaukee Bucks",
        "tipoff": "2026-01-03T18:00:00Z",
        "pregame_probs": {
            "home_ml": 0.44,
            "away_ml": 0.56,
        },
        "leak_guard": {"in_sample": False},
        "note": "demo-seed: canned game; not a live prediction",
        "provenance": "demo_seed",
    },
]

_DEMO_TRACK_RECORD: Dict[str, Any] = {
    "generated_at": _DEMO_GENERATED_AT,
    "window": "demo-seed (not a live result)",
    "n_settled": 0,
    "mean_clv_pct": None,
    "pct_beat_close": None,
    "n_true_close": 0,
    "n_proxy_close": 0,
    "by_sport": {
        "nba": {
            "n": 0,
            "mean_clv_pct": None,
            "pct_beat_close": None,
            "n_true_close": 0,
            "n_proxy_close": 0,
        }
    },
    "calibration": {
        "brier": None,
        "ece": None,
        "status": "demo_seed",
        "note": "real calibration numbers load from the live CLV ledger on a live session",
    },
    "methodology_note": DEFAULT_METHODOLOGY_NOTE,
    "edge_claimed": False,
    "schema_version": TRACKRECORD_SCHEMA_VERSION,
    "provenance": "demo_seed",
}

_DEMO_SNAPSHOT: Dict[str, Any] = {
    "schema_version": "1.0.0",
    "sport": "nba",
    "generated_at": _DEMO_GENERATED_AT,
    "status": "demo",
    "predictions": _DEMO_GAMES,
    "markets": [],
    "edges": [],
    "honest_note": (
        "DEMO SEED -- these are canned deterministic records, not live predictions. "
        "No dollar edge is claimed. CLV is the honest yardstick on a live session. "
        "edge_claimed=false always."
    ),
    "note": "demo_seed; idempotent; no network; no real data",
    "provenance": "demo_seed",
}


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    """Write *obj* as JSON to *path* atomically (write-then-rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=True), encoding="ascii")
    tmp.replace(path)


def seed(demo_dir: Path = DEMO_DIR) -> Dict[str, Path]:
    """Seed the demo dataset under *demo_dir*. Idempotent.

    Returns a dict mapping artifact names to their written paths.
    """
    demo_dir = Path(demo_dir)
    written: Dict[str, Path] = {}

    snapshot_path = demo_dir / "snapshot.json"
    _write_json(snapshot_path, _DEMO_SNAPSHOT)
    written["snapshot"] = snapshot_path

    tr_path = demo_dir / "track_record.json"
    tr_obj = TrackRecord.from_dict(_DEMO_TRACK_RECORD)
    _write_json(tr_path, tr_obj.to_dict())
    written["track_record"] = tr_path

    readme_path = demo_dir / "README.txt"
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.write_text(
        "DEMO SEED -- generated by sell.demo_seed\n"
        "\n"
        "These are canned deterministic records. No real money, no live\n"
        "predictions, no dollar-edge claims.\n"
        "\n"
        "Files:\n"
        "  snapshot.json    -- canned game predictions (demo provenance)\n"
        "  track_record.json -- sample TrackRecord (n_settled=0; demo status)\n"
        "\n"
        "To seed: python -m sell.demo_seed\n"
        "PUBLIC DEPLOY IS HUMAN-GATED. See docs/sell/DEPLOY.md.\n",
        encoding="ascii",
    )
    written["readme"] = readme_path

    return written


def main() -> int:
    """Entry point: seed and print the written paths."""
    demo_dir = Path(os.environ.get("SELL_DEMO_DIR", str(DEMO_DIR)))
    written = seed(demo_dir)
    for name, path in written.items():
        print("demo_seed | wrote %s -> %s" % (name, path), flush=True)
    print("demo_seed | done (idempotent; no network; no $ numbers)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
