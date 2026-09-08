"""Focused S316 tick and preregistration checks."""
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from scripts.platformkit.ingame.s316_mc_cross_env import (TICK_COLUMNS, _compact,
                                                          compare_tick_series)

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/harness/S316_mc_cross_env_2026-09-08_preregistration.md"


def _ticks(p_delta: float = 0.0) -> pd.DataFrame:
    rows = []
    for index, key in enumerate(("401:a", "402:b")):
        row = {column: float(index) / 4.0 for column in TICK_COLUMNS}
        row["state_key"] = key
        row["p_simulator"] += p_delta if index == 1 else 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def test_tick_comparer_uses_pinned_state_keys_and_threshold() -> None:
    comparison = compare_tick_series(_ticks(), _ticks(2e-9))
    assert math.isclose(comparison["p_simulator"]["max_abs_delta"], 2e-9, abs_tol=1e-18)
    assert comparison["p_simulator"]["ticks_gt_1e9"] == 1
    assert comparison["market_prob"] == {"max_abs_delta": 0.0, "ticks_gt_1e9": 0}


def test_compact_moves_per_game_fill_detail_into_a_csv(tmp_path: Path) -> None:
    summary = {"n_ticks": 180, "fills": [{"game": "401", "league_mean_field": "ft_rate_q50"}]}
    _compact(summary, tmp_path)
    written = json.loads((tmp_path / "S287_summary.json").read_text(encoding="ascii"))
    assert "fills" in written and written["n_ticks"] == 180
    assert written["fills_csv"]["rows"] == 1
    assert list(pd.read_csv(tmp_path / "S287_fills.csv").game) == [401]


def test_preregistration_seal_normalizes_crlf_before_hashing() -> None:
    normalized = PREREG.read_bytes().replace(b"\r\n", b"\n")
    before, line = normalized.rsplit(b"SEAL sha256 ", 1)
    assert line.strip().decode("ascii") == hashlib.sha256(before).hexdigest()
