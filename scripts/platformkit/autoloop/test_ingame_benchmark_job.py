"""Per-file test for scripts.platformkit.autoloop.ingame_benchmark_job.

Acceptance criteria:
1. No growth since the watermark -> neither benchmark runs.
2. >=25% growth since the watermark -> the grown sport's benchmark runs and its
   watermark advances; MLB reruns also trigger bucket_recalibration.
3. A benchmark raising -> that sport reports an error dict, watermark NOT advanced,
   and the other sport (and MLB's recal) is unaffected.
4. First tick (no prior watermark) with labeled games present -> establishes baseline
   (runs once, unconditional on "growth").

All benchmark/recalibration entrypoints are injected mocks -- no real benchmark or
production file is ever touched.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_ingame_benchmark_job.py -q
"""
from __future__ import annotations

from scripts.platformkit.autoloop import ingame_benchmark_job as IB


def _mlb_files(tmp_path, n):
    d = tmp_path / "mlb"
    d.mkdir(exist_ok=True)
    for i in range(n):
        (d / ("game_%03d.jsonl" % i)).write_text("{}\n", encoding="utf-8")
    return tmp_path


def _run(tmp_path, watermarks, n_mlb, n_nba, mlb_fn=None, nba_fn=None, recal_fn=None):
    grade_dir = _mlb_files(tmp_path, n_mlb)
    return IB.run_ingame_benchmarks(
        watermarks, mlb_grade_dir=grade_dir,
        mlb_benchmark_fn=mlb_fn or (lambda: {"ok": True}),
        nba_benchmark_fn=nba_fn or (lambda: {"ok": True}),
        mlb_recal_fn=recal_fn or (lambda: {"ok": True}),
        # nba count is mocked directly via count_nba_checkpoint_games monkeypatch below
    )


def test_no_growth_neither_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(IB, "count_nba_checkpoint_games", lambda p=None: 10)
    watermarks = {IB._MLB_KEY: {"n_labeled_games": 8}, IB._NBA_KEY: {"n_labeled_games": 10}}
    calls = []
    out = _run(tmp_path, watermarks, n_mlb=8, n_nba=10,
              mlb_fn=lambda: calls.append("mlb"), nba_fn=lambda: calls.append("nba"))
    assert calls == []
    assert out["mlb_state_bucket_benchmark"]["status"] == "skipped"
    assert out["nba_checkpoint_benchmark"]["status"] == "skipped"
    assert out["mlb_bucket_recalibration"]["status"] == "skipped"


def test_25pct_growth_triggers_mlb_and_recal(tmp_path, monkeypatch):
    monkeypatch.setattr(IB, "count_nba_checkpoint_games", lambda p=None: 10)
    watermarks = {IB._MLB_KEY: {"n_labeled_games": 8}, IB._NBA_KEY: {"n_labeled_games": 10}}
    calls = []
    out = _run(tmp_path, watermarks, n_mlb=10, n_nba=10,  # 8 -> 10 == +25%
              mlb_fn=lambda: calls.append("mlb"), recal_fn=lambda: calls.append("recal"),
              nba_fn=lambda: calls.append("nba"))
    assert calls == ["mlb", "recal"]
    assert out["mlb_state_bucket_benchmark"]["status"] == "ran"
    assert out["mlb_bucket_recalibration"]["status"] == "ran"
    assert out["nba_checkpoint_benchmark"]["status"] == "skipped"
    assert watermarks[IB._MLB_KEY]["n_labeled_games"] == 10
    assert watermarks[IB._NBA_KEY]["n_labeled_games"] == 10  # untouched


def test_benchmark_raising_is_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(IB, "count_nba_checkpoint_games", lambda p=None: 20)
    watermarks = {IB._MLB_KEY: {"n_labeled_games": 8}, IB._NBA_KEY: {"n_labeled_games": 10}}
    calls = []

    def boom():
        raise RuntimeError("mlb benchmark boom")

    out = _run(tmp_path, watermarks, n_mlb=10, n_nba=20,  # both due (+25%, +100%)
              mlb_fn=boom, recal_fn=lambda: calls.append("recal"),
              nba_fn=lambda: calls.append("nba"))
    assert out["mlb_state_bucket_benchmark"]["status"] == "error"
    assert "mlb benchmark boom" in out["mlb_state_bucket_benchmark"]["error"]
    # recal never called -- benchmark run failed, so recal is skipped not attempted
    assert "recal" not in calls
    assert out["mlb_bucket_recalibration"]["status"] == "skipped"
    # mlb watermark NOT advanced (retry next cycle); nba unaffected and DID advance
    assert watermarks[IB._MLB_KEY]["n_labeled_games"] == 8
    assert out["nba_checkpoint_benchmark"]["status"] == "ran"
    assert calls == ["nba"]
    assert watermarks[IB._NBA_KEY]["n_labeled_games"] == 20


def test_first_tick_no_watermark_establishes_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(IB, "count_nba_checkpoint_games", lambda p=None: 0)
    watermarks: dict = {}
    calls = []
    out = _run(tmp_path, watermarks, n_mlb=3, n_nba=0,
              mlb_fn=lambda: calls.append("mlb"), recal_fn=lambda: calls.append("recal"),
              nba_fn=lambda: calls.append("nba"))
    assert calls == ["mlb", "recal"]
    assert out["mlb_state_bucket_benchmark"]["status"] == "ran"
    assert watermarks[IB._MLB_KEY]["n_labeled_games"] == 3
    # nba count is 0 -> not due even with no prior watermark
    assert out["nba_checkpoint_benchmark"]["status"] == "skipped"
    assert IB._NBA_KEY not in watermarks


def test_count_helpers_never_raise_on_missing_paths(tmp_path):
    assert IB.count_mlb_labeled_games(tmp_path / "does_not_exist") == 0
    assert IB.count_nba_checkpoint_games(tmp_path / "missing.parquet") == 0
