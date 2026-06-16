"""Headless calibration-drift monitor (blueprint X3 PART B).

Per (sport, market, layer): compare the recent 7-day Brier to a 30-day rolling baseline.
ALERT (exit code 2) when recent Brier RISES > k_sigma * SE(baseline) -- a measurable
calibration degradation that a cron / `-p` run can detect. FAIL-QUIET (exit 0, no alert)
when either window is unpopulated, so a sparse ledger never cries wolf.

The sigma logic mirrors the VERIFIED eval_gate/ledger.py drift_report core. This monitor
NEVER mutates a prediction row -- it only reads, then appends to a separate drift_log.parquet
and rewrites drift_report.md. It reports Brier only -- never a probability, never a $ figure.
"""
from __future__ import annotations
import os
import pathlib
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import numpy as np
import pandas as pd

try:  # package import when run as `-m scripts.platformkit.ledger...`
    from scripts.platformkit.ledger.ledger import (
        read_ledger, _store_paths, _HAVE_PARQUET)
except ImportError:  # direct-script / sys.path-injected (per-file test) fallback
    from ledger import read_ledger, _store_paths, _HAVE_PARQUET

_REPO = pathlib.Path(__file__).resolve().parents[3]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _parse(s):
    try:
        return datetime.fromisoformat(str(s)).replace(tzinfo=None)
    except Exception:
        return None


def _brier(sub: pd.DataFrame) -> Optional[float]:
    if sub.empty:
        return None
    p = sub["calibrated_prob"].to_numpy(float)
    y = sub["outcome"].to_numpy(float)
    return float(np.mean((p - y) ** 2))


def _window(g: pd.DataFrame, end: datetime, days: float) -> pd.DataFrame:
    start = end - timedelta(days=days)
    ts = g["_ts"]
    return g[(ts >= start) & (ts <= end)]


def check_group(g: pd.DataFrame, now: datetime, recent_days: float = 7.0,
                baseline_days: float = 30.0, k_sigma: float = 1.0) -> Optional[dict]:
    """Return an alert dict if recent Brier exceeds baseline by >k_sigma SE; else None.

    Fail-quiet: returns None (no alert) unless BOTH windows are populated (baseline n>=2).
    """
    recent = _window(g, now, recent_days)
    baseline = _window(g, now, baseline_days)
    rb, bb = _brier(recent), _brier(baseline)
    if rb is None or bb is None or len(baseline) < 2:
        return None
    p = baseline["calibrated_prob"].to_numpy(float)
    y = baseline["outcome"].to_numpy(float)
    se = float(np.std((p - y) ** 2, ddof=1) / np.sqrt(len(baseline)))
    threshold = bb + k_sigma * se
    if rb > threshold:
        return {"recent_brier": rb, "baseline_brier": bb, "se": se,
                "threshold": threshold, "n_recent": int(len(recent)),
                "n_baseline": int(len(baseline))}
    return None


def run_drift(df: pd.DataFrame, now: Optional[datetime] = None,
              k_sigma: float = 1.0) -> List[dict]:
    """Evaluate every (sport, market, layer) group; return the list of alert rows."""
    now = now or _now()
    alerts: List[dict] = []
    if df.empty:
        return alerts
    df = df[df["outcome"].notna()].copy()
    if df.empty:
        return alerts
    df["_ts"] = df["graded_at"].fillna(df["pred_ts"]).map(_parse)
    df = df[df["_ts"].notna()]
    for (sport, market, layer), g in df.groupby(["sport", "market", "layer"]):
        a = check_group(g, now, k_sigma=k_sigma)
        if a:
            a.update({"sport": sport, "market": market, "layer": layer,
                      "checked_at": now.isoformat()})
            alerts.append(a)
    return alerts


def _append_drift_log(alerts: List[dict], base_dir: Optional[str]) -> None:
    store, _ = _store_paths(base_dir)
    log = store.parent / ("drift_log.parquet" if _HAVE_PARQUET else "drift_log.jsonl")
    new = pd.DataFrame(alerts) if alerts else pd.DataFrame(
        [{"checked_at": _now().isoformat(), "sport": None, "market": None,
          "layer": None}])
    if log.exists():
        old = pd.read_parquet(log) if log.suffix == ".parquet" else pd.read_json(log, lines=True)
        new = pd.concat([old, new], ignore_index=True)
    tmp = log.with_suffix(log.suffix + ".tmp")
    if log.suffix == ".parquet":
        new.to_parquet(tmp, index=False)
    else:
        new.to_json(tmp, orient="records", lines=True)
    os.replace(tmp, log)


def _write_report(alerts: List[dict], base_dir: Optional[str]) -> None:
    store, _ = _store_paths(base_dir)
    md = store.parent / "drift_report.md"
    lines = ["# Calibration drift report", "",
             f"checked_at: {_now().isoformat()}",
             "Reports Brier only -- no probabilities, no $ figures.", ""]
    if not alerts:
        lines.append("No drift alerts (calibration stable or windows unpopulated).")
    else:
        lines.append(f"{len(alerts)} ALERT(S) -- recent Brier rose > 1 sigma vs baseline:")
        for a in alerts:
            lines.append(f"- {a['sport']}/{a['market']}/{a['layer']}: "
                         f"recent={a['recent_brier']:.4f} baseline={a['baseline_brier']:.4f} "
                         f"thr={a['threshold']:.4f} (n_recent={a['n_recent']})")
    md.write_text("\n".join(lines) + "\n", encoding="ascii")


def main(base_dir: Optional[str] = None, k_sigma: float = 1.0,
         now: Optional[datetime] = None) -> int:
    df = read_ledger(base_dir=base_dir)
    alerts = run_drift(df, now=now, k_sigma=k_sigma)
    _append_drift_log(alerts, base_dir)
    _write_report(alerts, base_dir)
    print(f"drift_check: {len(alerts)} alert(s).")
    return 2 if alerts else 0


if __name__ == "__main__":
    raise SystemExit(main())
