"""Post-ship decay monitors (S17) -- REPORT ONLY, nothing here disables anything.

Three monitors over settled forward rows:
  (a) calibration decay -- composes ledger.drift_report() UNTOUCHED, with its SE
      widened to the clustered effective sample size (see _widen below).
  (b) crowding        -- trailing-30-day mean |prob - p_close| collapsing vs the
      first-30-day mean.
  (c) regime drift    -- chi-square on regime_calibration.buckets() shares,
      monitored window vs fitting window.

The ESS gate runs FIRST: rho is estimated from the MONITORED window's own rows
(never a stored constant); n_eff < 30 makes every monitor INSUFFICIENT so a thin
window can never raise an alarm.

Rows are mappings (a LedgerRow joined to p_close + regime fields), carrying at
least: ts (ISO), prob, outcome (0/1). Optional: p_close, game_id, game_phase.

Calibration language only. An ALARM means "recalibration is worth looking at",
never a monetary statement of any kind.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional, Sequence

import pandas as pd
from scipy import stats

from scripts.platformkit.eval_gate.ledger import LedgerRow, drift_report
from scripts.platformkit.ingame.gap_effective_n import (
    effective_sample_size,
    intraclass_correlation,
)
from scripts.platformkit.regime_calibration import buckets

INSUFFICIENT = "INSUFFICIENT"
OK = "OK"
ALARM = "ALARM"

MIN_N_EFF = 30.0
CROWDING_RATIO = 0.5
REGIME_ALPHA = 0.05
MIN_EXPECTED_CELL = 5.0
_OTHER = "OTHER"


@dataclass(frozen=True)
class Monitor:
    status: str
    stat: Optional[float]
    n: int
    n_eff: Optional[float]
    threshold: Optional[float]
    note: str


def _settled(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [r for r in rows if r.get("outcome") in (0, 1) and r.get("prob") is not None]


def _ts(row: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(str(row["ts"]))


def _ess_frame(rows: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """game/loss frame for the real intraclass_correlation signature.

    Rows without a game_id fall back to their own index, which yields singleton
    clusters -> rho 0.0 -> n_eff == n (no free inflation, no free deflation).
    """
    return pd.DataFrame(
        {
            "game": [str(r.get("game_id", "row%d" % i)) for i, r in enumerate(rows)],
            "loss": [(float(r["prob"]) - float(r["outcome"])) ** 2 for r in rows],
        }
    )


def _widen(report: Any, deff: float, k_sigma: float) -> Optional[float]:
    """Re-inflate drift_report's own SE to the clustered ESS.

    drift_report computes threshold = baseline_brier + k_sigma * SE, with SE
    assuming n_baseline INDEPENDENT rows.  Under clustering the true SE is
    larger by sqrt(design_effect).  We recover its SE from its own output --
    SE = (threshold - baseline_brier) / k_sigma -- and re-inflate it, so the
    function itself is composed, never edited, and never re-implemented here.
    """
    if report.baseline_brier is None or report.delta is None or k_sigma <= 0:
        return None
    se = (report.threshold - report.baseline_brier) / k_sigma
    return report.baseline_brier + k_sigma * se * math.sqrt(max(deff, 1.0))


def _calibration_monitor(rows, now_iso: str, n_eff: float, deff: float) -> Monitor:
    ledger_rows = [
        LedgerRow(
            ts=str(r["ts"]), sport=str(r.get("sport", "")), market=str(r.get("market", "")),
            inputs_hash="", prob=float(r["prob"]), outcome=int(r["outcome"]),
        )
        for r in rows
    ]
    report = drift_report(ledger_rows, now_iso, 7.0, 30.0, k_sigma=1.0)
    widened = _widen(report, deff, 1.0)
    if widened is None or report.recent_brier is None:
        return Monitor(INSUFFICIENT, None, len(rows), n_eff, None,
                       "drift_report windows not both populated")
    alarm = report.recent_brier > widened
    return Monitor(
        ALARM if alarm else OK, report.recent_brier, len(rows), n_eff, widened,
        "recent vs baseline Brier; SE widened by sqrt(deff)=%.3f" % math.sqrt(max(deff, 1.0)),
    )


def _crowding_monitor(rows, now_iso: str, n_eff: float) -> Monitor:
    priced = [r for r in rows if r.get("p_close") is not None]
    if not priced:
        return Monitor(INSUFFICIENT, None, 0, n_eff, None, "no p_close on any row")
    now = datetime.fromisoformat(now_iso)
    first_start = min(_ts(r) for r in priced)
    first = [r for r in priced if _ts(r) < first_start + timedelta(days=30)]
    trailing = [r for r in priced if _ts(r) >= now - timedelta(days=30)]
    if not first or not trailing or first_start + timedelta(days=30) > now - timedelta(days=30):
        return Monitor(INSUFFICIENT, None, len(priced), n_eff, None,
                       "first-30d and trailing-30d windows overlap or are empty")
    gap = lambda w: sum(abs(float(r["prob"]) - float(r["p_close"])) for r in w) / len(w)
    first_gap, trailing_gap = gap(first), gap(trailing)
    threshold = CROWDING_RATIO * first_gap
    return Monitor(
        ALARM if trailing_gap < threshold else OK, trailing_gap, len(priced), n_eff, threshold,
        "trailing-30d mean |prob - p_close| vs %.2f x first-30d (%.5f)" % (CROWDING_RATIO, first_gap),
    )


def _merge_small(obs: dict[str, int], exp: dict[str, float]) -> tuple[list[float], list[float]]:
    """Merge every cell whose EXPECTED count is < 5 into a single OTHER cell.

    If OTHER itself cannot reach 5 expected the chi-square is not valid (a zero
    expected cell would divide by zero), so return nothing and let the caller
    report INSUFFICIENT rather than an alarm off an unusable cell.
    """
    keep = [k for k in obs if exp.get(k, 0.0) >= MIN_EXPECTED_CELL]
    other_o = sum(v for k, v in obs.items() if k not in keep)
    other_e = sum(v for k, v in exp.items() if k not in keep)
    o = [float(obs[k]) for k in keep]
    e = [exp[k] for k in keep]
    if other_o or other_e:
        if other_e < MIN_EXPECTED_CELL:
            return [], []
        o.append(float(other_o))
        e.append(other_e)
    return o, e


def _regime_monitor(rows, fit_window_rows, n_eff: float) -> Monitor:
    if not fit_window_rows:
        return Monitor(INSUFFICIENT, None, len(rows), n_eff, None, "no fitting-window rows")
    def shaped(window):
        out = []
        for r in window:
            d = dict(r)
            d.setdefault("model_prob", float(r["prob"]))
            out.append(d)
        return out

    # ponytail: one buckets() call PER WINDOW. A single call over the concatenated
    # union looks better but is wrong -- buckets() assigns confidence terciles by
    # rank and breaks ties by list position, so whichever window is concatenated
    # first is pushed into the lower terciles and a stable pair alarms falsely.
    # The cost is that terciles are window-relative, so a pure confidence-
    # distribution shift is invisible here; phase / rest / month drift still is.
    # Upgrade path: cut the terciles once on the fitting window and apply those
    # fixed edges to both, which needs a bucket API that accepts edges.
    fit_keys = buckets(shaped(fit_window_rows))
    mon_keys = buckets(shaped(rows))
    obs: dict[str, int] = {}
    for k in mon_keys:
        obs[k] = obs.get(k, 0) + 1
    fit_counts: dict[str, int] = {}
    for k in fit_keys:
        fit_counts[k] = fit_counts.get(k, 0) + 1
    exp = {k: len(mon_keys) * fit_counts.get(k, 0) / len(fit_keys) for k in obs}
    o, e = _merge_small(obs, exp)
    if len(o) < 2:
        return Monitor(INSUFFICIENT, None, len(rows), n_eff, None,
                       "fewer than 2 cells with expected >= %d after OTHER merge" % MIN_EXPECTED_CELL)
    scale = sum(o) / sum(e) if sum(e) else 0.0
    if scale <= 0:
        return Monitor(INSUFFICIENT, None, len(rows), n_eff, None, "empty expected distribution")
    p = float(stats.chisquare(o, [v * scale for v in e]).pvalue)
    return Monitor(
        ALARM if p < REGIME_ALPHA else OK, p, len(rows), n_eff, REGIME_ALPHA,
        "chi-square on %d regime cells, monitored vs fitting window" % len(o),
    )


def monitor_all(
    rows: Sequence[Mapping[str, Any]],
    now_iso: str,
    fit_window_rows: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Monitor]:
    """Run all three decay monitors. Report-only: an ALARM disables nothing."""
    settled = _settled(rows)
    names = ("calibration_decay", "crowding", "regime_drift")
    if not settled:
        return {n: Monitor(INSUFFICIENT, None, 0, None, None, "no settled rows") for n in names}
    frame = _ess_frame(settled)
    rho = intraclass_correlation(frame, "game", "loss")
    ess = effective_sample_size(frame, "game", "loss")
    n_eff, deff = float(ess["n_eff"]), float(ess["design_effect"])
    if n_eff < MIN_N_EFF:
        note = "ESS gate: n_eff %.2f < %.0f (rho %.3f) -- no alarm possible" % (n_eff, MIN_N_EFF, rho)
        return {n: Monitor(INSUFFICIENT, None, len(settled), n_eff, MIN_N_EFF, note) for n in names}
    return {
        "calibration_decay": _calibration_monitor(settled, now_iso, n_eff, deff),
        "crowding": _crowding_monitor(settled, now_iso, n_eff),
        "regime_drift": _regime_monitor(settled, _settled(fit_window_rows), n_eff),
    }


def write_report(rows, now_iso: str, fit_window_rows=(), out_path: Optional[str] = None) -> dict:
    """Serialise monitor_all. out_path defaults to None -- writes nothing.

    ponytail: no default path on purpose; docs/evidence/calibration/ is written
    only once S17 is ARMED (after S20 has >= 200 settled rows).
    """
    result = {k: asdict(v) for k, v in monitor_all(rows, now_iso, fit_window_rows).items()}
    payload = {"as_of": now_iso, "report_only": True, "monitors": result}
    if out_path:
        with open(out_path, "w", encoding="ascii") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
    return payload
