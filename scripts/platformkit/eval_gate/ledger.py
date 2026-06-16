"""Track-record ledger + calibration-drift monitor (blueprint X3 / mcp-and-ledger).

Self-contained (numpy + stdlib). An APPEND-ONLY log of every prediction (and its eventual outcome)
is the trust moat: an auditable, timestamped calibration record a skeptic can replay. The drift
monitor flags when recent calibration degrades vs a rolling baseline (catches silent data drift).

It logs probabilities + outcomes and reports Brier/ECE only -- it never logs or implies a dollar
edge / ROI / units. JSONL on disk so appends are atomic-ish and the file is human-auditable.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import List, Optional
import numpy as np


@dataclass(frozen=True)
class LedgerRow:
    ts: str                 # ISO datetime the prediction was made
    sport: str
    market: str             # e.g. "ml_home", "total", "ingame_wp"
    inputs_hash: str        # hash of the feature vector (reproducibility, no raw PII)
    prob: float             # the calibrated probability emitted
    outcome: Optional[int] = None   # 0/1 once settled; None while pending


def append_row(path: str, row: LedgerRow) -> None:
    """Append one JSONL record. Append-only -> never rewrites history."""
    with open(path, "a", encoding="ascii") as f:
        f.write(json.dumps(asdict(row), ensure_ascii=True) + "\n")


def load(path: str) -> List[LedgerRow]:
    rows: List[LedgerRow] = []
    try:
        with open(path, encoding="ascii") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(LedgerRow(**json.loads(line)))
    except FileNotFoundError:
        pass
    return rows


def settled(rows: List[LedgerRow]) -> List[LedgerRow]:
    return [r for r in rows if r.outcome in (0, 1)]


def _window(rows: List[LedgerRow], end: datetime, days: float) -> List[LedgerRow]:
    start = end - timedelta(days=days)
    out = []
    for r in settled(rows):
        t = datetime.fromisoformat(r.ts)
        if start <= t <= end:
            out.append(r)
    return out


def brier_of(rows: List[LedgerRow]) -> Optional[float]:
    if not rows:
        return None
    p = np.array([r.prob for r in rows], dtype=float)
    y = np.array([r.outcome for r in rows], dtype=float)
    return float(np.mean((p - y) ** 2))


@dataclass
class DriftReport:
    recent_brier: Optional[float]
    baseline_brier: Optional[float]
    delta: Optional[float]
    threshold: float
    alert: bool
    n_recent: int
    n_baseline: int


def drift_report(rows: List[LedgerRow], now_iso: str, recent_days: float = 7.0,
                 baseline_days: float = 30.0, k_sigma: float = 1.0) -> DriftReport:
    """Alert if recent Brier exceeds the rolling baseline by > k_sigma * SE(baseline).

    Conservative by design: needs both windows populated, else no alert (fail-quiet, not fail-loud).
    """
    now = datetime.fromisoformat(now_iso)
    recent = _window(rows, now, recent_days)
    baseline = _window(rows, now, baseline_days)
    rb, bb = brier_of(recent), brier_of(baseline)
    if rb is None or bb is None or len(baseline) < 2:
        return DriftReport(rb, bb, None, 0.0, False, len(recent), len(baseline))
    # SE of the baseline Brier (per-row squared errors)
    p = np.array([r.prob for r in baseline]); y = np.array([r.outcome for r in baseline], float)
    se = float(np.std((p - y) ** 2, ddof=1) / np.sqrt(len(baseline)))
    threshold = bb + k_sigma * se
    delta = rb - bb
    return DriftReport(rb, bb, delta, threshold, bool(rb > threshold), len(recent), len(baseline))
