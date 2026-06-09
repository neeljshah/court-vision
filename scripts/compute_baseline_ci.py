"""compute_baseline_ci.py — Wilson 95% CI on prop hit-rates and ROI bands.

Reads data/cache/baseline_replication.json (the replicated_table) and computes:
  * Wilson 95% lower/upper bound on hit-rate per stat
  * Implied ROI lower/upper bound assuming -110 American odds (1.91 decimal)
  * Sufficiency flags: n >= 200, CI_lo_roi > 0

Writes data/cache/baseline_confidence.json.

Wilson interval (Brown/Cai/DasGupta 2001) is the standard small-sample-safe
choice — Normal approximation undercovers when p is near 0 or 1.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REP_PATH = ROOT / "data" / "cache" / "baseline_replication.json"
OUT_PATH = ROOT / "data" / "cache" / "baseline_confidence.json"

Z_95 = 1.959963984540054  # two-sided 95%
DEC_ODDS = 1.91  # -110 → payout 0.91 per unit on a win, -1.0 on a loss


def wilson_interval(k: int, n: int, z: float = Z_95) -> tuple[float, float, float]:
    """Returns (p_hat, lo, hi) on [0,1]. Returns (0,0,1) if n==0."""
    if n <= 0:
        return 0.0, 0.0, 1.0
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def roi_from_hit_rate(p: float, dec_odds: float = DEC_ODDS) -> float:
    """ROI per unit risked at flat $1 stake. Decimal odds → payout = dec_odds - 1."""
    payout = dec_odds - 1.0
    return p * payout - (1 - p) * 1.0  # in units per $1 risked


def main() -> None:
    rep = json.loads(REP_PATH.read_text(encoding="utf-8"))
    replicated = rep.get("replicated_table") or rep.get("baseline_table") or {}

    rows: dict[str, dict] = {}
    agg_n = 0
    agg_units_pt = 0.0  # at midpoint
    agg_units_lo = 0.0
    agg_units_hi = 0.0

    for stat, m in replicated.items():
        n = int(m.get("n_bets") or 0)
        hr_pct = float(m.get("hit_rate") or 0.0)
        roi_pct = float(m.get("roi_pct") or 0.0)
        k = int(round(n * hr_pct / 100.0))

        p_hat, lo, hi = wilson_interval(k, n)
        roi_pt = roi_from_hit_rate(p_hat) if n else 0.0
        roi_lo = roi_from_hit_rate(lo) if n else 0.0
        roi_hi = roi_from_hit_rate(hi) if n else 0.0

        rows[stat] = {
            "n": n,
            "k_hits": k,
            "hit_rate_pct": round(hr_pct, 3),
            "hit_rate_ci_lo_pct": round(lo * 100, 3),
            "hit_rate_ci_hi_pct": round(hi * 100, 3),
            "roi_pct_reported": round(roi_pct, 3),
            "roi_pct_from_hr_pt": round(roi_pt * 100, 3),
            "roi_pct_ci_lo": round(roi_lo * 100, 3),
            "roi_pct_ci_hi": round(roi_hi * 100, 3),
            "sufficient_sample": n >= 200,
            "ci_excludes_zero_positive": roi_lo > 0,
            "verdict": (
                "insufficient_sample" if n < 200
                else "proven_positive" if roi_lo > 0
                else "not_yet_proven"
            ),
        }
        agg_n += n
        agg_units_pt += roi_pt * n
        agg_units_lo += roi_lo * n
        agg_units_hi += roi_hi * n

    aggregate = {
        "n": agg_n,
        "roi_pct_pt": round((agg_units_pt / agg_n * 100), 3) if agg_n else 0.0,
        "roi_pct_ci_lo": round((agg_units_lo / agg_n * 100), 3) if agg_n else 0.0,
        "roi_pct_ci_hi": round((agg_units_hi / agg_n * 100), 3) if agg_n else 0.0,
    }

    out = {
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": str(REP_PATH.relative_to(ROOT)),
        "method": "wilson_95_on_hit_rate then implied_roi at decimal_odds=1.91",
        "per_stat": rows,
        "aggregate": aggregate,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
