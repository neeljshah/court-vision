"""predict_service.calib_drift_monitor -- Served-calibration drift monitor.

Compares live calib_scoreboard per-sport Brier/ECE against a stored baseline
snapshot and flags calibration regression as a degraded/observability state
instead of silently shipping worse probs. No $ fields. CALIBRATION not edge.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional, Sequence

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.calib_scoreboard import MIN_HOLDOUT, ScoreboardRow  # noqa: E402

# Thresholds: ECE/Brier degradation beyond these margins triggers drift=True.
ECE_DRIFT_THRESHOLD: float = 0.02
BRIER_DRIFT_THRESHOLD: float = 0.01

_STATUS_DRIFT = "drift"
_STATUS_OK = "ok"
_STATUS_INSUFFICIENT = "INSUFFICIENT_DATA"
_STATUS_UNAVAILABLE = "unavailable"


class BaselineEntry(NamedTuple):
    """Stored baseline metrics for one sport (snapshot at a known-good checkpoint)."""
    sport: str
    brier: Optional[float]
    ece: Optional[float]
    n_holdout: int
    status: str  # "ok" or "INSUFFICIENT_DATA" at snapshot time


class DriftResult(NamedTuple):
    """Drift decision for one sport.
    status: "ok"|"drift"|"INSUFFICIENT_DATA"|"unavailable".
    drift: True=degraded; False=within tolerance; None=data insufficient/unavailable.
    """
    sport: str
    status: str
    drift: Optional[bool]
    ece_live: Optional[float]
    ece_baseline: Optional[float]
    ece_delta: Optional[float]
    brier_live: Optional[float]
    brier_baseline: Optional[float]
    brier_delta: Optional[float]
    n_holdout_live: int
    reason: str  # ASCII explanation


def save_baseline(rows: Sequence[ScoreboardRow], path: "str | Path") -> None:
    """Persist a scoreboard snapshot as the new baseline. Never raises."""
    entries = []
    for r in rows:
        entries.append({
            "sport": r.sport,
            "brier": r.brier,
            "ece": r.ece,
            "n_holdout": r.n_holdout,
            "status": r.status,
        })
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 -- never raises
        pass


def load_baseline(path: "str | Path") -> Optional[List[BaselineEntry]]:
    """Load baseline snapshot. Returns None if missing/unparseable (never raises)."""
    try:
        p = Path(path)
        if not p.exists():
            return None
        raw = json.loads(p.read_text(encoding="utf-8"))
        return [
            BaselineEntry(
                sport=e["sport"],
                brier=e.get("brier"),
                ece=e.get("ece"),
                n_holdout=int(e.get("n_holdout", 0)),
                status=e.get("status", _STATUS_INSUFFICIENT),
            )
            for e in raw
        ]
    except Exception:  # noqa: BLE001 -- never raises
        return None


def _check_one(live: ScoreboardRow, baseline: Optional[BaselineEntry]) -> DriftResult:
    """Compare one sport's live row against baseline. Never raises, stale-never-green."""
    sport = live.sport
    n_live = live.n_holdout

    # -- 1. Missing baseline
    if baseline is None:
        return DriftResult(
            sport=sport,
            status=_STATUS_UNAVAILABLE,
            drift=None,
            ece_live=live.ece,
            ece_baseline=None,
            ece_delta=None,
            brier_live=live.brier,
            brier_baseline=None,
            brier_delta=None,
            n_holdout_live=n_live,
            reason="no baseline snapshot -- save_baseline() has not been called yet",
        )

    # -- 2. Thin live data
    if live.status != "ok" or n_live < MIN_HOLDOUT:
        return DriftResult(
            sport=sport,
            status=_STATUS_INSUFFICIENT,
            drift=None,
            ece_live=live.ece,
            ece_baseline=baseline.ece,
            ece_delta=None,
            brier_live=live.brier,
            brier_baseline=baseline.brier,
            brier_delta=None,
            n_holdout_live=n_live,
            reason=(
                f"live n_holdout={n_live} < {MIN_HOLDOUT} or status={live.status!r}"
                " -- insufficient data for reliable drift signal"
            ),
        )

    # -- 3. Thin baseline data
    if baseline.status != "ok" or baseline.n_holdout < MIN_HOLDOUT:
        return DriftResult(
            sport=sport,
            status=_STATUS_INSUFFICIENT,
            drift=None,
            ece_live=live.ece,
            ece_baseline=baseline.ece,
            ece_delta=None,
            brier_live=live.brier,
            brier_baseline=baseline.brier,
            brier_delta=None,
            n_holdout_live=n_live,
            reason=(
                f"baseline n_holdout={baseline.n_holdout} < {MIN_HOLDOUT}"
                f" or baseline status={baseline.status!r}"
                " -- insufficient baseline for drift comparison"
            ),
        )

    # Both sides are ok -- compute deltas
    ece_live = live.ece
    ece_base = baseline.ece
    brier_live = live.brier
    brier_base = baseline.brier

    # Defensive: handle unexpected None in an ok-status row
    if ece_live is None or ece_base is None or brier_live is None or brier_base is None:
        return DriftResult(
            sport=sport,
            status=_STATUS_INSUFFICIENT,
            drift=None,
            ece_live=ece_live,
            ece_baseline=ece_base,
            ece_delta=None,
            brier_live=brier_live,
            brier_baseline=brier_base,
            brier_delta=None,
            n_holdout_live=n_live,
            reason="metric fields unexpectedly None despite ok status -- data integrity issue",
        )

    ece_delta = round(ece_live - ece_base, 6)
    brier_delta = round(brier_live - brier_base, 6)

    # -- 4 & 5. Drift detection
    ece_drifted = ece_delta > ECE_DRIFT_THRESHOLD
    brier_drifted = brier_delta > BRIER_DRIFT_THRESHOLD

    if ece_drifted or brier_drifted:
        parts = []
        if ece_drifted:
            parts.append(
                f"ECE degraded +{ece_delta:.4f} (threshold={ECE_DRIFT_THRESHOLD})"
            )
        if brier_drifted:
            parts.append(
                f"Brier degraded +{brier_delta:.4f} (threshold={BRIER_DRIFT_THRESHOLD})"
            )
        return DriftResult(
            sport=sport,
            status=_STATUS_DRIFT,
            drift=True,
            ece_live=ece_live,
            ece_baseline=ece_base,
            ece_delta=ece_delta,
            brier_live=brier_live,
            brier_baseline=brier_base,
            brier_delta=brier_delta,
            n_holdout_live=n_live,
            reason="DRIFT DETECTED -- " + "; ".join(parts),
        )

    # -- 6. Within tolerance
    return DriftResult(
        sport=sport,
        status=_STATUS_OK,
        drift=False,
        ece_live=ece_live,
        ece_baseline=ece_base,
        ece_delta=ece_delta,
        brier_live=brier_live,
        brier_baseline=brier_base,
        brier_delta=brier_delta,
        n_holdout_live=n_live,
        reason=(
            f"within tolerance: ECE delta={ece_delta:+.4f}, "
            f"Brier delta={brier_delta:+.4f}"
        ),
    )


def check_drift(
    live_rows: Sequence[ScoreboardRow],
    baseline: Optional[Sequence[BaselineEntry]],
) -> List[DriftResult]:
    """Compare live scoreboard rows against baseline. One DriftResult per row. Never raises."""
    baseline_map: dict[str, BaselineEntry] = {}
    if baseline is not None:
        for b in baseline:
            baseline_map[b.sport] = b

    results: List[DriftResult] = []
    for row in live_rows:
        try:
            bl = baseline_map.get(row.sport)
            results.append(_check_one(row, bl))
        except Exception as exc:  # noqa: BLE001 -- never raises
            results.append(DriftResult(
                sport=row.sport,
                status=_STATUS_UNAVAILABLE,
                drift=None,
                ece_live=None,
                ece_baseline=None,
                ece_delta=None,
                brier_live=None,
                brier_baseline=None,
                brier_delta=None,
                n_holdout_live=0,
                reason=f"unexpected error during drift check: {exc}",
            ))
    return results


def print_drift_report(results: List[DriftResult]) -> None:
    """Print ASCII drift report. No $ fields."""
    hdr = f"{'sport':<10}  {'status':<18}  {'drift':<6}  {'ece_delta':>10}  {'brier_delta':>12}  reason"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        ece_d = f"{r.ece_delta:+.5f}" if r.ece_delta is not None else "---"
        br_d = f"{r.brier_delta:+.5f}" if r.brier_delta is not None else "---"
        drift_s = "TRUE" if r.drift else ("False" if r.drift is False else "None")
        print(f"{r.sport:<10}  {r.status:<18}  {drift_s:<6}  {ece_d:>10}  {br_d:>12}  {r.reason}")
    print("\nCalibration drift monitor -- no $ edge claimed.")
