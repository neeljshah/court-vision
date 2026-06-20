"""domains.basketball_nba.prop_quantile_coverage -- Empirical-quantile coverage scoreboard.

Measures whether the NBA prop empirical-quantile pricer (prop_quantile_pricer) is
well-calibrated: for each predicted central interval of nominal width W, do ~W% of
held-out realizations actually fall inside the band?

For each player-game in OOF data, the player's prior rolling window forms the
predicted empirical CDF; we check whether the realized actual falls inside the
[q_lo, q_hi] band and aggregate per-stat to get empirical vs nominal coverage.

Key invariants: leak-free (prior-only window); INSUFFICIENT_DATA when n < MIN_N;
no $ / edge / ROI / PnL fields; ASCII only; <= 300 LOC; per-file test only.

Public API::
    from domains.basketball_nba.prop_quantile_coverage import (
        run_coverage_scoreboard, INSUFFICIENT_DATA
    )
    scoreboard = run_coverage_scoreboard()   # {stat: dict | INSUFFICIENT_DATA}

Output per stat::
    {"stat": str, "n": int,
     "bands": {"50pct": {"nominal": 0.50, "empirical": float, "gap": float, "n": int}, ...},
     "pinball_loss": float, "pinball_raw": float, "pinball_beats_raw": bool,
     "any_gap_exceeds_threshold": bool, "note": str, "honest_note": str}
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Union

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

_OOF_PATH = Path("data/cache/pregame_oof.parquet")
_MIN_WINDOW = 5       # prior games required before scoring a triplet
_WINDOW = 15          # rolling window width (matches prop_sigma_calib)
MIN_N = 200           # min scored triplets per stat; fewer -> INSUFFICIENT_DATA
COVERAGE_TOL = 0.05   # |gap| threshold for any_gap_exceeds_threshold flag
_BANDS: Dict[str, float] = {"50pct": 0.50, "80pct": 0.80, "90pct": 0.90}
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
_HONEST_NOTE = (
    "Empirical-quantile coverage scoreboard. Calibration only -- no $ edge, no ROI. "
    "INSUFFICIENT_DATA < %d triplets per stat." % MIN_N
)


# ---------------------------------------------------------------------------
# Core math helpers
# ---------------------------------------------------------------------------

def _empirical_quantile(values: np.ndarray, q: float) -> float:
    """q-th quantile via linear interpolation on sorted order statistics."""
    if len(values) == 0:
        return float("nan")
    sv = np.sort(values)
    idx = q * (len(sv) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sv) - 1)
    return float(sv[lo] * (1.0 - (idx - lo)) + sv[hi] * (idx - lo))


def _pinball(actuals: np.ndarray, q_preds: np.ndarray, quantile: float) -> float:
    """Quantile (pinball) loss at level `quantile` in (0, 1)."""
    diff = actuals - q_preds
    return float(np.mean(np.maximum(quantile * diff, (quantile - 1.0) * diff)))


# ---------------------------------------------------------------------------
# Per-stat scoring
# ---------------------------------------------------------------------------

def _score_stat(
    sub: pd.DataFrame,
    bands: Dict[str, float],
    min_window: int,
    window: int,
) -> Union[str, dict]:
    """Score one stat's OOF DataFrame; return result dict or INSUFFICIENT_DATA.

    For each player, games are sorted chronologically.  Each game with >= min_window
    prior games forms a scored triplet: prior window -> predicted [q_lo, q_hi];
    actual falls inside -> covered.
    """
    sub = sub.copy()
    sub["game_date"] = pd.to_datetime(sub["game_date"])

    band_within: Dict[str, List[int]] = {k: [] for k in bands}
    band_total: Dict[str, int] = {k: 0 for k in bands}
    pinball_rows: List[tuple] = []   # (q_lo_50, q_hi_50, actual)
    raw_preds: List[float] = []
    raw_actuals: List[float] = []

    for _pid, grp in sub.groupby("player_id", sort=False):
        if len(grp) < min_window + 1:
            continue
        grp = grp.sort_values("game_date")
        actuals_arr = grp["actual"].to_numpy(dtype=float)
        preds_arr = grp["oof_pred"].to_numpy(dtype=float)

        for i in range(min_window, len(actuals_arr)):
            prior = actuals_arr[max(0, i - window):i]
            if len(prior) < min_window:
                continue
            actual_val = actuals_arr[i]

            for band_name, width in bands.items():
                lo_q = (1.0 - width) / 2.0
                q_lo = _empirical_quantile(prior, lo_q)
                q_hi = _empirical_quantile(prior, 1.0 - lo_q)
                band_within[band_name].append(int(q_lo <= actual_val <= q_hi))
                band_total[band_name] += 1

            # Pinball reference: 50% band Q25/Q75
            pinball_rows.append((
                _empirical_quantile(prior, 0.25),
                _empirical_quantile(prior, 0.75),
                actual_val,
            ))
            raw_preds.append(preds_arr[i])
            raw_actuals.append(actual_val)

    # Guard: too few triplets
    n_total = max(band_total.values()) if band_total else 0
    if n_total < MIN_N:
        log.info("prop_quantile_coverage: %d triplets < %d -> %s", n_total, MIN_N, INSUFFICIENT_DATA)
        return INSUFFICIENT_DATA

    # Band coverage results
    band_results: Dict[str, Any] = {}
    any_gap_exceeds = False
    for band_name, width in bands.items():
        n_band = band_total[band_name]
        cov = float(sum(band_within[band_name]) / n_band) if n_band > 0 else 0.0
        gap = round(cov - width, 4)
        if abs(gap) > COVERAGE_TOL:
            any_gap_exceeds = True
        band_results[band_name] = {"nominal": width, "empirical": round(cov, 4),
                                   "gap": gap, "n": n_band}

    # Pinball loss: avg of Q25 and Q75 bound losses vs Q=0.5 raw-MAE reference
    if pinball_rows:
        act_arr = np.array([r[2] for r in pinball_rows], dtype=float)
        lo_arr = np.array([r[0] for r in pinball_rows], dtype=float)
        hi_arr = np.array([r[1] for r in pinball_rows], dtype=float)
        pb_loss = round((_pinball(act_arr, lo_arr, 0.25) + _pinball(act_arr, hi_arr, 0.75)) / 2.0, 5)
        pb_raw = round(_pinball(np.array(raw_actuals, dtype=float),
                                np.array(raw_preds, dtype=float), 0.5), 5)
    else:
        pb_loss = pb_raw = float("nan")

    beats_raw = bool(
        pb_loss == pb_loss and pb_raw == pb_raw and pb_loss <= pb_raw  # nan-safe
    )

    stat_name = str(sub["stat"].iloc[0]) if len(sub) > 0 else "unknown"
    if any_gap_exceeds:
        note = ("COVERAGE GAP: at least one band has |gap| > %.0f%%. "
                "Quantile pricer may be mis-calibrated for %s." % (COVERAGE_TOL * 100, stat_name))
    else:
        note = "OK: all bands within +/-%.0f%% of nominal for %s." % (COVERAGE_TOL * 100, stat_name)

    return {
        "stat": stat_name,
        "n": n_total,
        "bands": band_results,
        "pinball_loss": pb_loss,
        "pinball_raw": pb_raw,
        "pinball_beats_raw": beats_raw,
        "any_gap_exceeds_threshold": any_gap_exceeds,
        "note": note,
        "honest_note": _HONEST_NOTE,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_coverage_scoreboard(
    oof_path: Path = _OOF_PATH,
    bands: Dict[str, float] = _BANDS,
    min_n: int = MIN_N,
    min_window: int = _MIN_WINDOW,
    window: int = _WINDOW,
    coverage_tol: float = COVERAGE_TOL,
) -> Dict[str, Union[str, dict]]:
    """Run the empirical-quantile coverage scoreboard over all stats in OOF data.

    Parameters: oof_path, bands, min_n, min_window, window, coverage_tol.
    Returns dict mapping stat -> result dict or INSUFFICIENT_DATA.
    Never raises; never writes files; no $ fields.
    """
    oof_path = Path(oof_path)
    if not oof_path.exists():
        log.warning("prop_quantile_coverage: OOF not found at %s", oof_path)
        return {}
    try:
        df = pd.read_parquet(oof_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("prop_quantile_coverage: failed to read OOF: %s", exc)
        return {}
    required = {"player_id", "stat", "oof_pred", "actual", "game_date"}
    if not required.issubset(df.columns):
        log.warning("prop_quantile_coverage: OOF missing columns %s", required - set(df.columns))
        return {}

    return {
        stat: _score_stat(sub=df[df["stat"] == stat], bands=bands,
                          min_window=min_window, window=window)
        for stat in sorted(df["stat"].unique())
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    import logging as _lg
    _lg.basicConfig(level=_lg.INFO, format="%(levelname)s %(message)s")
    scoreboard = run_coverage_scoreboard()
    if not scoreboard:
        print("No results (OOF absent or missing columns).")
        return
    hdr = f"  {'stat':<6} {'n':>6}  {'50pct':>8} {'80pct':>8} {'90pct':>8}"
    hdr += f"  {'pb_loss':>8} {'pb_raw':>7} {'beats':>5}  flag"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for stat in sorted(scoreboard):
        r = scoreboard[stat]
        if r == INSUFFICIENT_DATA:
            print(f"  {stat:<6}  INSUFFICIENT_DATA")
            continue
        assert isinstance(r, dict)
        bds = r["bands"]
        cov50 = bds.get("50pct", {}).get("empirical", float("nan"))
        cov80 = bds.get("80pct", {}).get("empirical", float("nan"))
        cov90 = bds.get("90pct", {}).get("empirical", float("nan"))
        flag = "GAP" if r["any_gap_exceeds_threshold"] else "ok"
        beats = "Y" if r["pinball_beats_raw"] else "N"
        print(f"  {stat:<6} {r['n']:>6}  {cov50:>7.1%} {cov80:>7.1%} {cov90:>7.1%}  "
              f"{r['pinball_loss']:>8.4f} {r['pinball_raw']:>7.4f} {beats:>5}  {flag}")


if __name__ == "__main__":
    _main()
