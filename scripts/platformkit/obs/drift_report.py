"""drift_report.py — Daily drift and calibration report for the platform observatory.

Wraps the EXISTING drift detector (src/prediction/drift_detector.DriftDetector) and
calibration scorers into a daily Obsidian vault note at vault/Models/Drift Report.md.

Metrics computed on rolling windows from cached prediction data:
    * PIT (Probability Integral Transform) uniformity — residual distribution check
    * Interval coverage — fraction of actuals inside [q10, q90]
    * Brier score (binary over/under) — mean squared calibration error
    * Feature-level drift flags from the existing DriftDetector

Design constraints
------------------
    * Descriptive ONLY — no auto-action, no flag flips, no edge language.
    * Runs OFFLINE on cached parquets; never touches the network.
    * Writes/updates exactly ONE vault note (idempotent: reruns overwrite the same file).
    * Graceful degradation when any cached file is absent (logs a warning, exits 0).
    * No torch / GPU imports. No FastAPI boot.
    * Python 3.9 compatible.

Usage
-----
    python scripts/platformkit/obs/drift_report.py            # writes vault note
    python -m scripts.platformkit.obs.drift_report            # same via module
    from scripts.platformkit.obs.drift_report import build_report, write_vault_note
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — thresholds for flagging in the descriptive report
# ---------------------------------------------------------------------------

BRIER_WARN: float = 0.28      # Brier > this = note in report (market-average ~0.25)
COVERAGE_TARGET: float = 0.80  # nominal 80% interval target
COVERAGE_TOLERANCE: float = 0.03  # flag if |actual - target| > this
PIT_CHI_WARN: float = 0.05    # chi-sq p-value below this = non-uniform flag
ROLLING_WINDOW_DAYS: int = 30  # rolling window for per-window metrics

# Vault note anchor — used to detect and overwrite an existing note idempotently
_BANNER: str = "<!-- N-OBS-003 drift-report -->"

# ---------------------------------------------------------------------------
# Repo root resolution (matches health_snapshot pattern)
# ---------------------------------------------------------------------------


def _find_repo_root() -> Path:
    """Walk up from __file__ until a directory containing CLAUDE.md is found."""
    candidate = Path(__file__).resolve()
    for _ in range(10):
        candidate = candidate.parent
        if (candidate / "CLAUDE.md").exists():
            return candidate
    return Path(__file__).resolve().parents[3]  # fallback


REPO_ROOT: Path = _find_repo_root()

_CALIBRATION_FRAME = REPO_ROOT / "data" / "cache" / "calibration_frame.parquet"
_CAL_HISTORY = REPO_ROOT / "data" / "cache" / "prop_calibration_history.parquet"
_DRIFT_LOG = REPO_ROOT / "data" / "models" / "feature_drift_log.json"
_VAULT_NOTE = REPO_ROOT / "vault" / "Models" / "Drift Report.md"

# ---------------------------------------------------------------------------
# Re-export public API from helper modules so existing import paths resolve
# ---------------------------------------------------------------------------

# Ensure the obs/ directory is on sys.path for sibling imports
_OBS_DIR = Path(__file__).resolve().parent
if str(_OBS_DIR) not in sys.path:
    sys.path.insert(0, str(_OBS_DIR))

from drift_report_metrics import (  # noqa: E402
    _brier_binary,
    _brier_raw,
    _interval_coverage,
    _pit_uniformity,
)
from drift_report_compute import (  # noqa: E402
    _compute_coverage_metrics,
    _compute_drift_summary,
    _compute_point_metrics,
)
from drift_report_render import (  # noqa: E402
    _render_stat_table,
    render_vault_note,
)

# ---------------------------------------------------------------------------
# Data loading helpers — all gracefully degrade on absence
# ---------------------------------------------------------------------------


def _load_calibration_frame() -> Optional[Any]:
    """Load calibration_frame.parquet; return None if absent or unreadable."""
    if not _CALIBRATION_FRAME.exists():
        log.warning("calibration_frame.parquet not found at %s — skipping point metrics",
                    _CALIBRATION_FRAME)
        return None
    try:
        import pandas as pd  # noqa: PLC0415
        return pd.read_parquet(str(_CALIBRATION_FRAME))
    except Exception as exc:
        log.warning("Could not load calibration_frame.parquet: %s", exc)
        return None


def _load_cal_history() -> Optional[Any]:
    """Load prop_calibration_history.parquet; return None if absent."""
    if not _CAL_HISTORY.exists():
        log.warning("prop_calibration_history.parquet not found — skipping coverage metrics")
        return None
    try:
        import pandas as pd  # noqa: PLC0415
        return pd.read_parquet(str(_CAL_HISTORY))
    except Exception as exc:
        log.warning("Could not load prop_calibration_history.parquet: %s", exc)
        return None


def _load_drift_log() -> Dict[str, Any]:
    """Load feature_drift_log.json; return empty dict if absent."""
    if not _DRIFT_LOG.exists():
        return {}
    try:
        with open(str(_DRIFT_LOG), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log.warning("Could not load feature_drift_log.json: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Main report builder
# ---------------------------------------------------------------------------


def build_report() -> Dict[str, Any]:
    """Build the full drift report dict from all available cached data.

    Pure and side-effect-free.  Missing data sources degrade gracefully.

    Returns:
        JSON-serialisable dict with keys:
            generated_at, data_sources, point_metrics,
            coverage_metrics, drift_metrics, all_flags.
    """
    generated_at = datetime.now(timezone.utc).isoformat()

    # Load all sources
    cal_df = _load_calibration_frame()
    cal_hist_df = _load_cal_history()
    drift_log = _load_drift_log()

    data_sources: Dict[str, str] = {
        "calibration_frame": "present" if cal_df is not None else "absent",
        "prop_calibration_history": "present" if cal_hist_df is not None else "absent",
        "feature_drift_log": "present" if drift_log else "absent",
    }

    # Compute metrics
    point_metrics: Dict[str, Any]
    if cal_df is not None:
        point_metrics = _compute_point_metrics(cal_df)
    else:
        point_metrics = {
            "window_days": ROLLING_WINDOW_DAYS,
            "n_total": 0,
            "per_stat": {},
            "flags": [],
            "note": "calibration_frame absent — no point metrics",
        }

    coverage_metrics: Dict[str, Any]
    if cal_hist_df is not None:
        coverage_metrics = _compute_coverage_metrics(cal_hist_df)
    else:
        coverage_metrics = {
            "per_stat": {},
            "flags": [],
            "note": "prop_calibration_history absent — no coverage metrics",
        }

    drift_metrics = _compute_drift_summary(drift_log)

    # Aggregate all flags
    all_flags: List[str] = (
        point_metrics.get("flags", [])
        + coverage_metrics.get("flags", [])
        + drift_metrics.get("flags", [])
    )

    return {
        "generated_at": generated_at,
        "data_sources": data_sources,
        "point_metrics": point_metrics,
        "coverage_metrics": coverage_metrics,
        "drift_metrics": drift_metrics,
        "all_flags": all_flags,
    }


# ---------------------------------------------------------------------------
# write_vault_note — thin wrapper that injects the default path
# ---------------------------------------------------------------------------


def write_vault_note(report: Dict[str, Any], out_path: Optional[Path] = None) -> Path:
    """Atomically write/update the vault note.

    Idempotent: reruns overwrite the same file.  The banner comment at the
    top of the file (_BANNER) is the identity anchor.

    Args:
        report:   Output of build_report().
        out_path: Override for the output path (default: _VAULT_NOTE).

    Returns:
        Path where the note was written.
    """
    from drift_report_render import write_vault_note as _write  # noqa: PLC0415
    return _write(report, out_path=out_path, _vault_note_default=_VAULT_NOTE)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Build drift report and write vault note; exit 0 on graceful degradation."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    report = build_report()
    sources = report.get("data_sources", {})
    all_absent = all(v == "absent" for v in sources.values())

    if all_absent:
        log.warning(
            "All cached prediction files absent — no metrics to report. "
            "Run the prediction pipeline first to populate data/cache/. "
            "Exiting 0."
        )
        # Write a minimal stub note so the vault path exists
        stub_report: Dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_sources": sources,
            "point_metrics": {"window_days": ROLLING_WINDOW_DAYS, "n_total": 0,
                              "per_stat": {}, "flags": [],
                              "note": "all sources absent"},
            "coverage_metrics": {"per_stat": {}, "flags": []},
            "drift_metrics": {"model_count": 0, "flagged_models": [],
                              "n_flagged": 0, "flags": []},
            "all_flags": [],
        }
        out = write_vault_note(stub_report)
        print(f"Stub vault note written (no data): {out}")
        return

    out = write_vault_note(report)
    flag_count = len(report.get("all_flags", []))
    print(f"Drift report written: {out}  ({flag_count} flag(s))")
    if flag_count:
        for flag in report["all_flags"]:
            print(f"  FLAG: {flag}")


if __name__ == "__main__":
    # Allow both `python scripts/platformkit/obs/drift_report.py`
    # and `python -m scripts.platformkit.obs.drift_report`
    sys.path.insert(0, str(REPO_ROOT))
    main()
