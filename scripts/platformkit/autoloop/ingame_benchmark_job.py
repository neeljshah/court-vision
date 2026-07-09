"""scripts.platformkit.autoloop.ingame_benchmark_job -- watermark-gated re-run of the
in-game MODEL-vs-MARKET benchmarks as their corpora grow (autoloop job #6, mission:
close the in-game improvement loop Claude-free).

Wraps 3 existing, already-tested modules -- never re-implements their math:
  * scripts.platformkit.ingame.state_bucket_benchmark   (MLB grade-file corpus)
  * scripts.platformkit.ingame.nba_checkpoint_benchmark  (NBA playoff-checkpoint parquet)
  * scripts.platformkit.ingame.bucket_recalibration      (MLB walk-forward recal;
    re-runs ONLY when the MLB benchmark itself re-ran -- it is downstream of it)

WATERMARK = labeled-game COUNT, not mtime (these corpora grow by whole files/rows, not
in-place edits). Cheap counts, never a full resolver pass:
  * mlb: number of *.jsonl files under data/cache/ingame_grade/mlb/ (discover_grade_files
    -- a glob, no parsing). A proxy for corpus size, matching the module's own docstring
    convention that unresolvable files are dropped inside the benchmark itself, not here.
  * nba: nunique game_id in the checkpoint parquet's own game_id column (single-column
    read, no full-frame load).

TRIGGER: a sport's benchmark reruns only when its count grew >= GROWTH_THRESHOLD (25%)
since the watermark's stored count. No prior watermark (first tick) -> any count > 0
establishes the baseline (mirrors weighting_refresh's "no watermark yet" convention in
maintenance_templates.py). A failed run is NEVER watermarked, so the next tick retries.

HONESTY: this job runs existing benchmarks and does nothing else -- it writes no new
verdict, computes no new number. Every JSON the wrapped modules write already carries
edge_claimed: False. No $/ROI field is added here.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII only; no network at import;
never writes data/registry/; never flips a flag; never edits ingame/*.py (read-only
callers via their public write_* entrypoints).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_ingame_benchmark_job.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_MLB_GRADE_DIR = _REPO / "data" / "cache" / "ingame_grade"
DEFAULT_NBA_DATA_PATH = (_REPO / "data" / "cache" / "inplay_odds" /
                         "nba_checkpoints_2025_26_playoffs.parquet")

GROWTH_THRESHOLD = 0.25   # re-run only once a corpus grew >= 25% since its watermark
_MLB_KEY = "M06_ingame_benchmarks__mlb"
_NBA_KEY = "M06_ingame_benchmarks__nba"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _due(current: int, prior: int, threshold: float = GROWTH_THRESHOLD) -> bool:
    """No watermark yet (prior<=0) -> due iff any labeled games exist. Else due iff
    the count grew by >= threshold (fractional growth), never on a flat/shrunk count."""
    if prior <= 0:
        return current > 0
    return current >= prior * (1.0 + threshold)


# -- cheap watermark counts (never a full resolver/benchmark pass) -----------------------
def count_mlb_labeled_games(grade_dir: Optional[Path] = None) -> int:
    """Cheap proxy: number of per-game grade files under ingame_grade/mlb/ (glob only,
    no parsing/resolving -- matches state_bucket_benchmark's own file-discovery helper)."""
    from scripts.platformkit.ingame.ingame_clv_aggregate import discover_grade_files
    d = Path(grade_dir) if grade_dir is not None else DEFAULT_MLB_GRADE_DIR
    return len(discover_grade_files(d, sport="mlb"))


def count_nba_checkpoint_games(data_path: Optional[Path] = None) -> int:
    """Cheap: nunique game_id read from a single parquet column. Missing/unreadable
    corpus is 0 games, never a crash (mirrors nba_checkpoint_benchmark.load_checkpoints)."""
    p = Path(data_path) if data_path is not None else DEFAULT_NBA_DATA_PATH
    if not p.is_file():
        return 0
    import pandas as pd
    try:
        col = pd.read_parquet(p, columns=["game_id"])["game_id"]
    except Exception:  # noqa: BLE001 -- unreadable/corrupt corpus is 0, not a crash
        return 0
    return int(col.nunique())


# -- default benchmark entrypoints (lazy-imported so injected mocks never pull deps) -----
def _default_mlb_benchmark() -> Dict[str, Any]:
    from scripts.platformkit.ingame.state_bucket_benchmark import write_benchmark
    return write_benchmark()


def _default_nba_benchmark() -> Dict[str, Any]:
    from scripts.platformkit.ingame.nba_checkpoint_benchmark import write_benchmark
    return write_benchmark()


def _default_mlb_recalibration() -> Dict[str, Any]:
    from scripts.platformkit.ingame.bucket_recalibration import write_recalibration
    return write_recalibration()


def run_ingame_benchmarks(watermarks: Dict[str, Any], *,
                          mlb_grade_dir: Optional[Path] = None,
                          nba_data_path: Optional[Path] = None,
                          mlb_benchmark_fn: Optional[Callable[[], Any]] = None,
                          nba_benchmark_fn: Optional[Callable[[], Any]] = None,
                          mlb_recal_fn: Optional[Callable[[], Any]] = None,
                          growth_threshold: float = GROWTH_THRESHOLD) -> Dict[str, Any]:
    """Re-run each sport's in-game benchmark iff its labeled-game count grew >=
    growth_threshold since its own watermark. Mutates `watermarks` in place (same
    convention as run_weighting_refresh) -- a failed run is never watermarked, so it
    is retried next cycle. Each sport (and MLB's downstream recalibration) is isolated:
    one raising never blocks the others."""
    mlb_run = mlb_benchmark_fn or _default_mlb_benchmark
    nba_run = nba_benchmark_fn or _default_nba_benchmark
    mlb_recal_run = mlb_recal_fn or _default_mlb_recalibration
    out: Dict[str, Any] = {}

    mlb_count = count_mlb_labeled_games(mlb_grade_dir)
    mlb_prior = int((watermarks.get(_MLB_KEY) or {}).get("n_labeled_games", 0))
    if not _due(mlb_count, mlb_prior, growth_threshold):
        out["mlb_state_bucket_benchmark"] = {"status": "skipped", "n_labeled_games": mlb_count,
                                             "watermark": mlb_prior}
        out["mlb_bucket_recalibration"] = {"status": "skipped", "reason": "mlb benchmark did not rerun"}
    else:
        try:
            mlb_run()
            watermarks[_MLB_KEY] = {"n_labeled_games": mlb_count, "last_run_ts": _now_iso()}
            out["mlb_state_bucket_benchmark"] = {"status": "ran", "n_labeled_games": mlb_count}
        except Exception as exc:  # noqa: BLE001 -- one sport failing must not block the other
            out["mlb_state_bucket_benchmark"] = {"status": "error", "error": str(exc)[:200]}
        if out["mlb_state_bucket_benchmark"]["status"] == "ran":
            try:
                mlb_recal_run()
                out["mlb_bucket_recalibration"] = {"status": "ran"}
            except Exception as exc:  # noqa: BLE001 -- recal failing must not touch the benchmark result
                out["mlb_bucket_recalibration"] = {"status": "error", "error": str(exc)[:200]}
        else:
            out["mlb_bucket_recalibration"] = {"status": "skipped", "reason": "mlb benchmark run failed"}

    nba_count = count_nba_checkpoint_games(nba_data_path)
    nba_prior = int((watermarks.get(_NBA_KEY) or {}).get("n_labeled_games", 0))
    if not _due(nba_count, nba_prior, growth_threshold):
        out["nba_checkpoint_benchmark"] = {"status": "skipped", "n_labeled_games": nba_count,
                                           "watermark": nba_prior}
    else:
        try:
            nba_run()
            watermarks[_NBA_KEY] = {"n_labeled_games": nba_count, "last_run_ts": _now_iso()}
            out["nba_checkpoint_benchmark"] = {"status": "ran", "n_labeled_games": nba_count}
        except Exception as exc:  # noqa: BLE001 -- one sport failing must not block the other
            out["nba_checkpoint_benchmark"] = {"status": "error", "error": str(exc)[:200]}

    return out


__all__ = ["GROWTH_THRESHOLD", "count_mlb_labeled_games", "count_nba_checkpoint_games",
          "run_ingame_benchmarks"]
