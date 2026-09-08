"""Focused S317 v1/v2 series schema and archive rule tests."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pytest

from scripts.platformkit.eval_gate.archive_path_check import check_pair
from scripts.platformkit.ingame.series_schema import recompute_metrics, read_series, v2_row_from_tick, write_v2


def test_v1_and_v2_round_trip(tmp_path: Path) -> None:
    v1 = tmp_path / "v1.csv"
    v1.write_text("game,cluster_id,timestamp,n_ticks,loss_recal_null,loss_simulator\n1,1,1:120,1,0.1,0.2\n", encoding="utf-8")
    legacy = list(read_series(v1))[0]
    assert legacy["version"] == 1 and legacy["p_market"] is None and legacy["outcome"] is None
    tick = {"game": "1", "ts": "1700000000", "grid_target_elapsed": "120", "outcome_home_win": "1", "market_prob": "0.8", "p_null": "0.7", "p_simulator": "0.9", "loss_market": "0.04", "loss_recal_null": "0.09", "loss_simulator": "0.01", "state_key": "1:120"}
    v2 = tmp_path / "v2.csv"; assert write_v2(v2, [v2_row_from_tick(tick)]) == 1
    row = list(read_series(v2))[0]
    assert row["version"] == 2 and row["timestamp"] == "1:120" and row["timestamp_utc"].endswith("Z")


def test_hand_pinned_twelve_tick_metrics() -> None:
    rows = [{"outcome": index % 2, "p_market": 0.25 if index % 2 == 0 else 0.75, "p_null": 0.5, "p_simulator": 0.0 if index % 2 == 0 else 1.0} for index in range(12)]
    metrics = recompute_metrics(rows)
    assert metrics["n"]["value"] == 12.0
    assert metrics["market"]["brier"] == pytest.approx(0.0625)
    assert metrics["null"]["brier"] == pytest.approx(0.25)
    assert metrics["simulator"]["brier"] == pytest.approx(0.0)
    assert metrics["market"]["ece"] == pytest.approx(0.25)
    assert metrics["null"]["ece"] == pytest.approx(0.0)


def test_archive_path_check_constructed_pairs(tmp_path: Path) -> None:
    prereg = tmp_path / "prereg.md"; memo = tmp_path / "memo.md"
    prereg.write_text("input `/workspace/wt/a4/inputs/a.csv`", encoding="utf-8")
    memo.write_text("Preregistration: `" + str(prereg) + "`\nrealised `/workspace/wt/a4/inputs/a.csv`", encoding="utf-8")
    assert check_pair(memo, None)[0]["status"] == "MATCH"
    memo.write_text("Preregistration: `" + str(prereg) + "`\nrealised `/workspace/wt/a4/data/cache/eval_gate/a.csv`", encoding="utf-8")
    assert check_pair(memo, None)[0]["status"] == "MISMATCH"
    assert check_pair(tmp_path / "missing.md", prereg)[0]["status"] == "ABSENT"


def test_preregistration_seal_normalizes_crlf() -> None:
    path = Path("docs/evidence/harness/S317_series_schema_2026-09-08_preregistration.md")
    body, seal = path.read_bytes().replace(b"\r\n", b"\n").split(b"SEAL sha256 ", 1)
    assert hashlib.sha256(body).hexdigest() == seal.decode("ascii").strip()
