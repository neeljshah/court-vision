"""Per-file test for scripts.platformkit.autoloop.utilization_drift_job.

Acceptance criteria:
1. First tick (no prior snapshot): writes the baseline snapshot, watermarks,
   and reports nothing (nothing is "new" against an absent prior).
2. A column that flips to UNUSED between snapshots queues exactly one
   NEW_DARK_COLUMNS row naming it; a column that flips UNUSED->USED is not
   reported.
3. Corpus-mtime trigger: unchanged corpus -> skipped, no rebuild.
4. One sport raising is isolated -- never blocks the others.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_utilization_drift_job.py -q
"""
from __future__ import annotations

import json
import os
import time

from scripts.platformkit.autoloop import utilization_drift_job as UDJ


def test_first_tick_writes_baseline_and_reports_nothing(tmp_path):
    corpus = tmp_path / "corpus.parquet"
    corpus.write_bytes(b"x")
    corpora = {"demo_sport": [(str(corpus), "parquet")]}
    out_dir = tmp_path / "out"
    queued = []

    rows = [{"column": "a", "status": "USED"}, {"column": "b", "status": "UNUSED"}]
    watermarks: dict = {}
    out = UDJ.run_utilization_drift(watermarks, sports=["demo_sport"], out_dir=out_dir,
                                    corpora=corpora, build_fn=lambda s: rows, queue_fn=queued.append)
    assert out["demo_sport"]["status"] == "ran"
    assert out["demo_sport"]["new_unused"] == []  # no prior -> nothing "new"
    assert queued == []
    assert (out_dir / "demo_sport_stat_utilization.json").is_file()
    assert "M08_utilization_drift__demo_sport" in watermarks


def test_new_unused_column_is_reported_once(tmp_path):
    corpus = tmp_path / "corpus.parquet"
    corpus.write_bytes(b"x")
    corpora = {"demo_sport": [(str(corpus), "parquet")]}
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "demo_sport_stat_utilization.json").write_text(
        json.dumps([{"column": "a", "status": "USED"}, {"column": "b", "status": "USED"}]),
        encoding="utf-8")

    watermarks: dict = {}
    rows = [{"column": "a", "status": "USED"}, {"column": "b", "status": "UNUSED"}]
    queued = []
    out = UDJ.run_utilization_drift(watermarks, sports=["demo_sport"], out_dir=out_dir,
                                    corpora=corpora, build_fn=lambda s: rows, queue_fn=queued.append)
    assert out["demo_sport"]["new_unused"] == ["b"]
    assert queued[0]["kind"] == "NEW_DARK_COLUMNS"
    assert queued[0]["columns"] == ["b"]

    # second tick, corpus untouched -> skipped entirely
    queued.clear()
    out2 = UDJ.run_utilization_drift(watermarks, sports=["demo_sport"], out_dir=out_dir,
                                     corpora=corpora, build_fn=lambda s: rows, queue_fn=queued.append)
    assert out2["demo_sport"]["status"] == "skipped"
    assert queued == []


def test_one_sport_failure_is_isolated(tmp_path):
    corpus = tmp_path / "corpus.parquet"
    corpus.write_bytes(b"x")
    corpora = {"bad_sport": [(str(corpus), "parquet")], "good_sport": [(str(corpus), "parquet")]}
    out_dir = tmp_path / "out"

    def build_fn(sport):
        if sport == "bad_sport":
            raise RuntimeError("boom")
        return [{"column": "a", "status": "USED"}]

    watermarks: dict = {}
    out = UDJ.run_utilization_drift(watermarks, sports=["bad_sport", "good_sport"], out_dir=out_dir,
                                    corpora=corpora, build_fn=build_fn, queue_fn=lambda r: None)
    assert out["bad_sport"]["status"] == "error"
    assert out["good_sport"]["status"] == "ran"
    assert "M08_utilization_drift__bad_sport" not in watermarks
    assert "M08_utilization_drift__good_sport" in watermarks
