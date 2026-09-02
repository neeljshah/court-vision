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


def _window(rows: List[LedgerRow], end: datetime, days: float,
            exclude_end: Optional[datetime] = None) -> List[LedgerRow]:
    """Return settled rows in [end-days, end).  If exclude_end is set, the upper
    bound becomes exclude_end (exclusive) instead of end -- used so the baseline
    and recent windows are DISJOINT and baseline is not contaminated by recent rows.
    """
    start = end - timedelta(days=days)
    upper = exclude_end if exclude_end is not None else end
    out = []
    for r in settled(rows):
        t = datetime.fromisoformat(r.ts)
        if start <= t < upper:
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

    Windows are DISJOINT:
      recent   = [now - recent_days,   now)               -- the last 7 days
      baseline = [now - baseline_days, now - recent_days) -- the prior 23 days

    This prevents the baseline Brier from being contaminated by the very recent
    rows it is compared against (which would dampen / miss real drift).

    Conservative by design: needs both windows populated, else no alert.
    """
    now = datetime.fromisoformat(now_iso)
    recent_start = now - timedelta(days=recent_days)
    # recent: [now - recent_days, now)
    recent = _window(rows, now, recent_days, exclude_end=now)
    # baseline: [now - baseline_days, now - recent_days)  -- excludes recent window
    baseline = _window(rows, recent_start, baseline_days - recent_days)
    rb, bb = brier_of(recent), brier_of(baseline)
    if rb is None or bb is None or len(baseline) < 2:
        return DriftReport(rb, bb, None, 0.0, False, len(recent), len(baseline))
    # SE of the baseline Brier (per-row squared errors)
    p = np.array([r.prob for r in baseline]); y = np.array([r.outcome for r in baseline], float)
    se = float(np.std((p - y) ** 2, ddof=1) / np.sqrt(len(baseline)))
    threshold = bb + k_sigma * se
    delta = rb - bb
    return DriftReport(rb, bb, delta, threshold, bool(rb > threshold), len(recent), len(baseline))


# --- FWER charge-ledger schema (S13) -------------------------------------------------
# A DIFFERENT file from the LedgerRow track-record above: data/cache/eval_gate/backtest_fwer.jsonl
# holds the cumulative-K charge rows written by backtest_runner._charge_ledger. Kept here so the
# writer, the loader and any future reader (results index, nightly backup) share one shape.

FWER_OPTIONAL_FIELDS = ("family", "k_family", "hypothesis_hash", "tier", "prereg_sha256")
FWER_TIERS = ("T2", "T3")


def load_fwer(path) -> List[dict]:
    """Load the FWER charge ledger; absent optional fields read back as None.

    Additive by construction: a pre-S13 row is returned exactly as written except that the
    five optional keys appear with value None, so old and new rows present one shape to readers.
    """
    rows: List[dict] = []
    try:
        with open(path, encoding="ascii") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append({**dict.fromkeys(FWER_OPTIONAL_FIELDS), **json.loads(line)})
    except FileNotFoundError:
        pass
    return rows


def next_k_family(rows: List[dict], family: Optional[str]) -> Optional[int]:
    """1 + the charges already made to `family`; first row of a family = 1, no family -> None.

    S89: COUNT, not max. Rows charged before a family was frozen each carry k_family 1
    (families of one), so a max over the aliased set would undercount. Aliases resolve
    through family_bars.FAMILY_ALIASES; with no alias the count and the max agree.
    """
    if family is None:
        return None
    from scripts.platformkit.eval_gate.family_bars import resolve_family

    target = resolve_family(family)
    return 1 + sum(1 for r in rows if r.get("k_family") is not None
                   and resolve_family(r.get("family")) == target)
