"""Per-file test for scripts.platformkit.autoloop.mechanism_reval_job.

Acceptance criteria:
1. Corpus-mtime trigger: no watermark yet -> due, calls every registered
   module's run(); watermark stored -> next call with unchanged mtime skips.
2. One module raising is isolated -- its sibling still runs and the domain's
   watermark still advances (a failed test never blocks the others).
3. Never edits mechanisms.md -- the job's whole surface is watermarks + the
   injected modules' own run().

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_mechanism_reval_job.py -q
"""
from __future__ import annotations

import os
import time
import types

from scripts.platformkit.autoloop import mechanism_reval_job as MRJ


def _registry(tmp_path):
    corpus = tmp_path / "corpus.parquet"
    corpus.write_bytes(b"x")
    return {"demo_sport": {"corpus": [corpus], "modules": ["demo.mod_a", "demo.mod_b"]}}, corpus


def test_first_tick_runs_all_modules_and_watermarks(tmp_path):
    reg, corpus = _registry(tmp_path)
    calls = []

    def import_fn(name):
        mod = types.SimpleNamespace()
        mod.run = lambda n=name: (calls.append(n) or [{"hypothesis": "h", "verdict": "NULL_LOCAL"}])
        return mod

    watermarks: dict = {}
    out = MRJ.run_mechanism_reval(watermarks, registry=reg, import_fn=import_fn)
    assert out["demo_sport"]["status"] == "ran"
    assert sorted(calls) == ["demo.mod_a", "demo.mod_b"]
    assert out["demo_sport"]["rows_appended"] == 2
    assert "M07_mechanism_reval__demo_sport" in watermarks

    # second call, corpus untouched -> skipped, no re-run
    calls.clear()
    out2 = MRJ.run_mechanism_reval(watermarks, registry=reg, import_fn=import_fn)
    assert out2["demo_sport"]["status"] == "skipped"
    assert calls == []

    # bump corpus mtime -> due again
    os.utime(corpus, (time.time() + 10, time.time() + 10))
    out3 = MRJ.run_mechanism_reval(watermarks, registry=reg, import_fn=import_fn)
    assert out3["demo_sport"]["status"] == "ran"


def test_one_module_failure_is_isolated_and_watermark_still_advances(tmp_path):
    reg, _corpus = _registry(tmp_path)

    def import_fn(name):
        mod = types.SimpleNamespace()
        if name == "demo.mod_a":
            def boom():
                raise RuntimeError("boom")
            mod.run = boom
        else:
            mod.run = lambda: [{"hypothesis": "h", "verdict": "CONFIRMED_LOCAL"}]
        return mod

    watermarks: dict = {}
    out = MRJ.run_mechanism_reval(watermarks, registry=reg, import_fn=import_fn)
    assert out["demo_sport"]["status"] == "ran"
    assert out["demo_sport"]["modules_ran"] == ["demo.mod_b"]
    assert out["demo_sport"]["modules_failed"][0]["module"] == "demo.mod_a"
    assert "M07_mechanism_reval__demo_sport" in watermarks  # partial success still advances


def test_missing_corpus_is_skipped_not_a_crash(tmp_path):
    missing = tmp_path / "gone.parquet"
    reg = {"demo_sport": {"corpus": [missing], "modules": ["demo.mod_a"]}}
    out = MRJ.run_mechanism_reval({}, registry=reg, import_fn=lambda n: None)
    assert out["demo_sport"]["status"] == "skipped"
    assert out["demo_sport"]["corpus_mtime"] is None
