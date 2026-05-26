"""L08_drift_detector.py — Model drift detection for player-prop predictions.

Reads the L07 bets ledger (data/ledger/bets.parquet), compares recent MAE
and hit-rate against trained baselines, and emits WARN/DRIFT alerts via L22.

Public API
----------
    DriftMetric           dataclass
    compute_drift(stat, window_days) -> DriftMetric | None
    run_all_drift_checks(window_days) -> list[DriftMetric]
    daily_drift_report() -> dict
    alert_on_drift(metrics) -> int

CLI:
    python L08_drift_detector.py check         # prints summary table
    python L08_drift_detector.py report [--window 7]

Environment Variables: none

Event Publication
-----------------
When a stat's drift status is "DRIFT" or "WARN", L08 publishes a
``"drift.detected"`` event via the L46 EventBus singleton (soft-imported;
failure is non-fatal and logged at DEBUG level).

Event schema::

    {
        "stat":         str,   # lowercase stat name, e.g. "pts"
        "drift_metric": float, # observed z-score
        "threshold":    float, # z-score threshold that was crossed
        "severity":     str,   # "warning" (WARN) | "error" (DRIFT)
        "window_days":  int,   # lookback window used for the check
        "detected_at":  str,   # ISO 8601 UTC timestamp
    }

Subscribers can register via::

    import scripts.execute_loop.L46_event_bus as L46
    L46.subscribe("drift.detected", handler, layer="MyLayer")
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parents[1]
sys.path.insert(0, str(_PROJECT_DIR))

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Soft-import L46 EventBus — optional; failure is non-fatal
# ---------------------------------------------------------------------------
try:
    from scripts.execute_loop import L46_event_bus as _L46  # type: ignore[import]
except Exception:  # noqa: BLE001
    _L46 = None

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_LEDGER_DIR = _PROJECT_DIR / "data" / "ledger"
_BETS_PARQUET = _LEDGER_DIR / "bets.parquet"
_BETS_CSV = _LEDGER_DIR / "bets.csv"
_WF_JSON = _PROJECT_DIR / "data" / "models" / "prop_pergame_walk_forward.json"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

_FALLBACK_MAE: dict[str, float] = {
    "pts": 4.62,
    "reb": 1.90,
    "ast": 1.36,
    "fg3m": 0.89,
    "stl": 0.72,
    "blk": 0.44,
    "tov": 0.89,
}

_EXPECTED_HIT_RATE = 0.55
_Z_WARN = 1.0
_Z_DRIFT = 2.0
_MIN_N = 30
_SIGMA_FACTOR = 0.15   # 15% of expected_mae as std-error unit

_MARKET_RE = re.compile(r"player_prop_(\w+)")


# ---------------------------------------------------------------------------
# Atomic-write helper
# ---------------------------------------------------------------------------
def _atomic_write_json(path: Path, payload: dict, indent: int = 2) -> None:
    """Write *payload* as JSON to *path* atomically via a sibling temp file.

    Uses tempfile.mkstemp + os.replace so a crashed write never leaves a
    corrupted file at the target path.  Any pre-existing file is replaced
    only after the new content is fully written and flushed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=path.name + ".",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=indent)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# DriftMetric dataclass
# ---------------------------------------------------------------------------
@dataclass
class DriftMetric:
    stat: str
    window_days: int
    n_predictions: int
    observed_mae: float
    expected_mae: float
    observed_hit_rate: float
    expected_hit_rate: float
    z_score: float
    status: str  # "OK" | "WARN" | "DRIFT" | "LOW_N" | "NO_DATA"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_ledger() -> Optional[pd.DataFrame]:
    """Return bets DataFrame or None if no file found."""
    if _BETS_PARQUET.exists():
        try:
            return pd.read_parquet(_BETS_PARQUET)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not read parquet ledger: %s — trying CSV", exc)
    if _BETS_CSV.exists():
        try:
            return pd.read_csv(_BETS_CSV, dtype=str)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not read CSV ledger: %s", exc)
    log.info("no settled bets yet")
    return None


def _load_expected_mae() -> dict[str, float]:
    """Load per-stat expected MAE from walk_forward JSON; fall back to constants."""
    if not _WF_JSON.exists():
        log.debug("walk_forward.json missing — using fallback MAE constants")
        return dict(_FALLBACK_MAE)
    try:
        with _WF_JSON.open() as fh:
            data = json.load(fh)
        # Support both {by_stat: {pts: ...}} and {pts: ...} layouts
        if "by_stat" in data:
            by_stat = data["by_stat"]
        else:
            by_stat = data
        merged = dict(_FALLBACK_MAE)
        for stat, val in by_stat.items():
            key = stat.lower()
            if key in merged:
                merged[key] = float(val)
        return merged
    except Exception as exc:  # noqa: BLE001
        log.warning("walk_forward.json parse error (%s) — using fallback", exc)
        return dict(_FALLBACK_MAE)


def _filter_settled(df: pd.DataFrame, window_days: int) -> pd.DataFrame:
    """Keep rows with status WON/LOST/PUSH settled within window_days."""
    valid_statuses = {"WON", "LOST", "PUSH"}
    mask_status = df["status"].str.upper().isin(valid_statuses)

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    cutoff_iso = cutoff.isoformat()

    # settled_at_iso column may be missing or all-empty
    if "settled_at_iso" not in df.columns:
        return df[mask_status]

    settled_col = df["settled_at_iso"].astype(str)
    mask_date = settled_col >= cutoff_iso
    return df[mask_status & mask_date]


def _extract_stat(market: str) -> Optional[str]:
    """Return lowercase stat from 'player_prop_pts' style market string."""
    m = _MARKET_RE.search(str(market))
    return m.group(1).lower() if m else None


def _classify_status(n: int, z: float) -> str:
    if n == 0:
        return "NO_DATA"
    if n < _MIN_N:
        return "LOW_N"
    if abs(z) >= _Z_DRIFT:
        return "DRIFT"
    if abs(z) >= _Z_WARN:
        return "WARN"
    return "OK"


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------
def compute_drift(stat: str, window_days: int = 7) -> Optional[DriftMetric]:
    """Compute drift for a single stat over window_days.

    Returns DriftMetric or None if the ledger cannot be loaded.
    """
    df = _load_ledger()
    if df is None:
        return None

    expected_mae_by_stat = _load_expected_mae()
    expected_mae = expected_mae_by_stat.get(stat.lower(), _FALLBACK_MAE.get(stat.lower(), 1.0))

    settled = _filter_settled(df, window_days)
    if settled.empty:
        return DriftMetric(
            stat=stat,
            window_days=window_days,
            n_predictions=0,
            observed_mae=0.0,
            expected_mae=expected_mae,
            observed_hit_rate=0.0,
            expected_hit_rate=_EXPECTED_HIT_RATE,
            z_score=0.0,
            status="NO_DATA",
        )

    # Filter to this stat via market column
    if "market" not in settled.columns:
        return DriftMetric(
            stat=stat,
            window_days=window_days,
            n_predictions=0,
            observed_mae=0.0,
            expected_mae=expected_mae,
            observed_hit_rate=0.0,
            expected_hit_rate=_EXPECTED_HIT_RATE,
            z_score=0.0,
            status="NO_DATA",
        )

    stat_mask = settled["market"].apply(
        lambda m: _extract_stat(m) == stat.lower()
    )
    stat_rows = settled[stat_mask].copy()

    n = len(stat_rows)
    if n == 0:
        return DriftMetric(
            stat=stat,
            window_days=window_days,
            n_predictions=0,
            observed_mae=0.0,
            expected_mae=expected_mae,
            observed_hit_rate=0.0,
            expected_hit_rate=_EXPECTED_HIT_RATE,
            z_score=0.0,
            status="NO_DATA",
        )

    # MAE: skip rows where model_q50 is NaN / missing
    def _flt(v):
        try:
            f = float(v)
            return None if (f != f) else f  # NaN check
        except (TypeError, ValueError):
            return None

    errors: list[float] = []
    for _, row in stat_rows.iterrows():
        q50 = _flt(row.get("model_q50"))
        actual = _flt(row.get("actual_value"))
        if q50 is None or actual is None:
            continue
        errors.append(abs(actual - q50))

    observed_mae = float(sum(errors) / len(errors)) if errors else 0.0

    # Hit rate: WON / (WON + LOST), exclude PUSH
    n_won = int((stat_rows["status"].str.upper() == "WON").sum())
    n_lost = int((stat_rows["status"].str.upper() == "LOST").sum())
    decisive = n_won + n_lost
    observed_hit_rate = n_won / decisive if decisive > 0 else 0.0

    # Z-score guard: expected_mae <= 0 → z=0, OK
    if expected_mae <= 0:
        z = 0.0
    else:
        sigma = expected_mae * _SIGMA_FACTOR
        z = (observed_mae - expected_mae) / sigma

    status = _classify_status(n, z)

    return DriftMetric(
        stat=stat,
        window_days=window_days,
        n_predictions=n,
        observed_mae=round(observed_mae, 4),
        expected_mae=round(expected_mae, 4),
        observed_hit_rate=round(observed_hit_rate, 4),
        expected_hit_rate=_EXPECTED_HIT_RATE,
        z_score=round(z, 4),
        status=status,
    )


# ---------------------------------------------------------------------------
# Run all stats
# ---------------------------------------------------------------------------
def run_all_drift_checks(window_days: int = 7) -> list[DriftMetric]:
    """Return DriftMetric for every stat in _STATS."""
    metrics: list[DriftMetric] = []
    for stat in _STATS:
        dm = compute_drift(stat, window_days=window_days)
        if dm is not None:
            metrics.append(dm)
    return metrics


# ---------------------------------------------------------------------------
# Daily report
# ---------------------------------------------------------------------------
def daily_drift_report(window_days: int = 7) -> dict:
    """Build report dict and persist to data/ledger/drift_report_<date>.json."""
    metrics = run_all_drift_checks(window_days=window_days)
    n_drift = sum(1 for m in metrics if m.status == "DRIFT")
    n_warn = sum(1 for m in metrics if m.status == "WARN")
    n_ok = sum(1 for m in metrics if m.status == "OK")

    # Publish drift.detected events for WARN / DRIFT metrics via L46
    if _L46 is not None:
        iso_ts = datetime.now(timezone.utc).isoformat()
        for m in metrics:
            if m.status not in ("DRIFT", "WARN"):
                continue
            severity = "error" if m.status == "DRIFT" else "warning"
            threshold = _Z_DRIFT if m.status == "DRIFT" else _Z_WARN
            try:
                _L46.publish(
                    "drift.detected",
                    source="L8",
                    payload={
                        "stat": m.stat,
                        "drift_metric": m.z_score,
                        "threshold": threshold,
                        "severity": severity,
                        "window_days": m.window_days,
                        "detected_at": iso_ts,
                    },
                )
            except Exception:  # noqa: BLE001
                log.debug("L46 publish failed (non-fatal)", exc_info=True)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": window_days,
        "metrics": [asdict(m) for m in metrics],
        "n_drift": n_drift,
        "n_warn": n_warn,
        "n_ok": n_ok,
    }

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = _LEDGER_DIR / f"drift_report_{today}.json"
    try:
        _atomic_write_json(out_path, report)
        log.info("drift report written: %s", out_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not write drift report: %s", exc)

    return report


# ---------------------------------------------------------------------------
# Alert dispatch
# ---------------------------------------------------------------------------
def alert_on_drift(metrics: list[DriftMetric]) -> int:
    """Send alerts for DRIFT/WARN metrics. Returns count of alerts sent."""
    try:
        from scripts.execute_loop.L22_alerting import send_drift_alert  # type: ignore[import]
    except ImportError:
        log.warning("L22_alerting not available — skipping drift alerts")
        return 0

    sent = 0
    for m in metrics:
        if m.status in ("DRIFT", "WARN"):
            try:
                ok = send_drift_alert(
                    m.stat,
                    m.observed_mae,
                    m.expected_mae,
                    m.window_days,
                )
                if ok:
                    sent += 1
                    log.info(
                        "drift alert sent: stat=%s status=%s z=%.2f",
                        m.stat, m.status, m.z_score,
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning("alert_on_drift: send failed for %s: %s", m.stat, exc)
    return sent


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------
def _print_table(metrics: list[DriftMetric]) -> None:
    hdr = (
        f"  {'stat':<6}  {'n':>5}  {'obs_mae':>8}  {'exp_mae':>8}  "
        f"{'z':>6}  {'hit_rt':>7}  {'status'}"
    )
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for m in metrics:
        print(
            f"  {m.stat:<6}  {m.n_predictions:>5}  {m.observed_mae:>8.4f}  "
            f"{m.expected_mae:>8.4f}  {m.z_score:>6.2f}  "
            f"{m.observed_hit_rate:>6.3f}  {m.status}"
        )


def _cli_check(args) -> None:  # noqa: ARG001
    metrics = run_all_drift_checks(window_days=args.window)
    if not metrics:
        print("[L08] no drift data")
        return
    n_drift = sum(1 for m in metrics if m.status == "DRIFT")
    n_warn = sum(1 for m in metrics if m.status == "WARN")
    print(f"[L08] drift check — window={args.window}d  "
          f"drift={n_drift}  warn={n_warn}")
    _print_table(metrics)


def _cli_report(args) -> None:
    report = daily_drift_report(window_days=args.window)
    print(
        f"[L08] report written — "
        f"n_drift={report['n_drift']}  "
        f"n_warn={report['n_warn']}  "
        f"n_ok={report['n_ok']}"
    )
    _print_table([DriftMetric(**m) for m in report["metrics"]])


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="L08_drift_detector")
    p.add_argument("--window", type=int, default=7, help="lookback days (default 7)")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="Print drift summary table")
    p_check.add_argument("--window", type=int, default=7)
    p_check.set_defaults(func=_cli_check)

    p_report = sub.add_parser("report", help="Write JSON report + print table")
    p_report.add_argument("--window", type=int, default=7)
    p_report.set_defaults(func=_cli_report)

    args = p.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
