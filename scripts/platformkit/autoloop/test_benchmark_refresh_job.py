"""Per-file test for scripts.platformkit.autoloop.benchmark_refresh_job.

Acceptance criteria:
1. New rows < min_n/min_matches -> both skip, neither rerun fn is called.
2. New rows >= the bar -> that sport's rerun fn is called and its watermark
   advances; the other sport is unaffected.
3. A rerun raising -> that sport reports an error, watermark NOT advanced,
   the other sport unaffected.
4. No baseline artifact -> "no_baseline", never a crash.
5. Real smoke: no injection at all (real baseline/count functions) must
   never raise -- honest skip/ran/error/no_baseline only.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_benchmark_refresh_job.py -q
"""
from __future__ import annotations

from scripts.platformkit.autoloop import benchmark_refresh_job as BR

_MLB_BASE = {"n_game_files": 100, "min_n": 10, "value": 0.5, "ci95": [0.1, 0.9], "verdict": "X"}
_SOCCER_BASE = {"n_matches_total": 1000, "min_matches": 20, "verdict": "Y", "panel_b_ci": [0.0, 0.1]}


def _run(watermarks, mlb_n=100, soccer_n=1000, mlb_base=None, soccer_base=None,
         mlb_fn=None, soccer_fn=None):
    calls = []
    return BR.run_benchmark_refresh(
        watermarks,
        mlb_baseline_fn=lambda: (mlb_base if mlb_base is not None else _MLB_BASE),
        mlb_n_avail_fn=lambda: mlb_n,
        mlb_rerun_fn=mlb_fn or (lambda: calls.append("mlb")),
        soccer_baseline_fn=lambda: (soccer_base if soccer_base is not None else _SOCCER_BASE),
        soccer_n_eligible_fn=lambda min_matches: soccer_n,
        soccer_rerun_fn=soccer_fn or (lambda min_matches: calls.append("soccer")),
    ), calls


def test_below_bar_neither_reruns():
    watermarks: dict = {}
    out, calls = _run(watermarks, mlb_n=105, soccer_n=1015)  # +5 < min_n(10)/min_matches(20)
    assert calls == []
    assert out["mlb_crps"]["status"] == "skipped" and out["mlb_crps"]["n_new"] == 5
    assert out["soccer_chain"]["status"] == "skipped" and out["soccer_chain"]["n_new"] == 15
    assert BR._MLB_KEY not in watermarks and BR._SOCCER_KEY not in watermarks


def test_mlb_at_bar_reruns_soccer_untouched():
    watermarks: dict = {}
    out, calls = _run(watermarks, mlb_n=110, soccer_n=1000)  # mlb +10 == min_n; soccer +0
    assert calls == ["mlb"]
    assert out["mlb_crps"]["status"] == "ran" and out["mlb_crps"]["n_game_files"] == 110
    assert out["soccer_chain"]["status"] == "skipped"
    assert watermarks[BR._MLB_KEY]["n_game_files_at_run"] == 110
    assert BR._SOCCER_KEY not in watermarks


def test_soccer_above_bar_reruns_with_baseline_min_matches():
    watermarks: dict = {}
    seen_min_matches = []
    out, calls = _run(watermarks, mlb_n=100, soccer_n=1025,
                      soccer_fn=lambda min_matches: seen_min_matches.append(min_matches))
    assert out["soccer_chain"]["status"] == "ran" and out["soccer_chain"]["n_new"] == 25
    assert seen_min_matches == [20]  # baseline's own min_matches, not a hardcoded default
    assert watermarks[BR._SOCCER_KEY]["n_matches_at_run"] == 1025
    assert BR._MLB_KEY not in watermarks


def test_rerun_raising_is_isolated_and_watermark_not_advanced():
    watermarks: dict = {}

    def boom():
        raise RuntimeError("mlb rerun boom")

    out, calls = _run(watermarks, mlb_n=200, soccer_n=1025, mlb_fn=boom)
    assert out["mlb_crps"]["status"] == "error"
    assert "mlb rerun boom" in out["mlb_crps"]["error"]
    assert BR._MLB_KEY not in watermarks
    # soccer still ran and advanced despite mlb's failure
    assert out["soccer_chain"]["status"] == "ran"
    assert calls == ["soccer"]
    assert watermarks[BR._SOCCER_KEY]["n_matches_at_run"] == 1025


def test_no_baseline_never_crashes():
    watermarks: dict = {}
    out = BR.run_benchmark_refresh(watermarks, mlb_baseline_fn=lambda: None,
                                   soccer_baseline_fn=lambda: None)
    assert out["mlb_crps"]["status"] == "no_baseline"
    assert out["soccer_chain"]["status"] == "no_baseline"


def test_real_smoke_never_raises():
    """Real baseline/count functions, no injection at all: must never raise
    out of the job -- honest skip/ran/error/no_baseline only."""
    watermarks: dict = {}
    out = BR.run_benchmark_refresh(watermarks)
    assert out["mlb_crps"]["status"] in {"skipped", "ran", "error", "no_baseline"}
    assert out["soccer_chain"]["status"] in {"skipped", "ran", "error", "no_baseline"}
