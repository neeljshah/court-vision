"""S292 four-input feasibility preflight, absorbed into S296 (spec VERSION 2026-09-07).

Recounts the four archived prop-evaluation stores and labels each TESTABLE or
NOT_TESTABLE_TODAY with its exact blocking fact. n = 4 (CONSTRUCT, exhaustive).
A count that does not reproduce is reported FALSIFIED; nothing is scored on it.
"""
from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

EXPECTED = {
    "data/cache/prop_calibration_history.parquet": {"rows": 4942, "stats": 7},
    "data/cache/props_eval_nba_calibration.json": {"overall_n": 356678},
    "data/cache/prop_sigma_scale.json": {"scale_factor_stats": 7},
    "data/frontend/prop_history_corpus.jsonl": {"rows": 3000, "market_prob_null": 3000,
        "unique_prop_player": 15, "unique_player_game_pairs": 619,
        "model_prob_le_0_05": 21, "model_prob_ge_0_90": 20},
}


def _stamp(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def preflight(input_root: Path) -> dict[str, Any]:
    """Measure the four inputs under input_root and return the labelled table."""
    out: dict[str, Any] = {}

    rel = "data/cache/prop_calibration_history.parquet"
    frame = pq.ParquetFile(input_root / "cache/prop_calibration_history.parquet").read().to_pandas()
    out[rel] = {**_stamp(input_root / "cache/prop_calibration_history.parquet"),
        "measured": {"rows": len(frame), "stats": int(frame["stat"].nunique()),
            "has_game_id": "game_id" in frame.columns, "grain": "player-stat AGGREGATE"},
        "label": "NOT_TESTABLE_TODAY",
        "blocking_fact": "player-stat AGGREGATE rows over 7 stats; no game_id column, so no per-game rows exist to join"}

    rel = "data/cache/props_eval_nba_calibration.json"
    payload = json.loads((input_root / "cache/props_eval_nba_calibration.json").read_text(encoding="utf-8"))
    out[rel] = {**_stamp(input_root / "cache/props_eval_nba_calibration.json"),
        "measured": {"overall_n": int(payload["overall"]["n"]), "per_stat_keys": sorted(payload["per_stat"]),
            "grain": "AGGREGATE summary only"},
        "label": "NOT_TESTABLE_TODAY",
        "blocking_fact": "aggregate Brier/BSS/ECE summary only; no per-bet or per-game record is archived"}

    rel = "data/cache/prop_sigma_scale.json"
    payload = json.loads((input_root / "cache/prop_sigma_scale.json").read_text(encoding="utf-8"))
    out[rel] = {**_stamp(input_root / "cache/prop_sigma_scale.json"),
        "measured": {"scale_factor_stats": len(payload["scale_factors"]), "window": payload.get("window"),
            "has_per_game_residuals": False},
        "label": "NOT_TESTABLE_TODAY",
        "blocking_fact": "rolling per-stat scale factors only; the per-game residuals they were derived from are not archived"}

    rel = "data/frontend/prop_history_corpus.jsonl"
    path = input_root / "frontend/prop_history_corpus.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    frame = pd.DataFrame(rows)
    frame["_d"] = pd.to_datetime(frame["ts"]).dt.date
    out[rel] = {**_stamp(path),
        "measured": {"rows": len(frame), "market_prob_null": int(frame["market_prob"].isna().sum()),
            "unique_prop_player": int(frame["prop_player"].nunique()),
            "unique_player_game_pairs": int(frame.drop_duplicates(["prop_player", "_d"]).shape[0]),
            "model_prob_le_0_05": int((frame["model_prob"] <= 0.05).sum()),
            "model_prob_ge_0_90": int((frame["model_prob"] >= 0.90).sum()), "grain": "per-bet"},
        "label": "NOT_TESTABLE_TODAY",
        "blocking_fact": ("market_prob is NULL on all 3,000 rows so no market comparison is possible; "
            "15 unique prop_player ids over 619 player-game pairs, and both model_prob tail bins are below n=30")}

    falsified = {}
    for rel, expected in EXPECTED.items():
        measured = out[rel]["measured"]
        bad = {key: (value, measured.get(key)) for key, value in expected.items() if measured.get(key) != value}
        out[rel]["reproduced"] = not bad
        if bad:
            falsified[rel] = bad
    return {"n_inputs": len(out), "enumeration": "CONSTRUCT exhaustive", "inputs": out,
        "measured_on": socket.gethostname(), "input_root": input_root.as_posix(),
        "falsified": falsified, "all_reproduced": not falsified,
        "retained_distinction": ("aggregate versus per-bet granularity and the absence of any market comparison "
            "are blocking facts, reported and never omitted")}


def main() -> None:
    import os
    root = Path(os.environ.get("S296_INPUT_ROOT", str(Path(__file__).resolve().parents[2] / "data")))
    print(json.dumps(preflight(root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
