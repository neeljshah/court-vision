"""Report the calibrated per-(stat, game-time) z_mults and achieved coverage.

Builds the held-out IntervalCalibrator from .planning/ingame/eval_curve_v2.json,
prints (a) the closed-form Laplace z table that fixes the z_mult=1.0 caveat and
(b) the achieved empirical coverage of the calibrated band on a Laplace and a
heavy-tailed held-out residual sample (so the report is honest about the
worst-case where MAE alone can't pin the tail).

Usage:
    NBA_OFFLINE=1 python scripts/ingame/report_interval_coverage.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")

from src.ingame.continuous_projection import PLAYER_STATS  # noqa: E402
from src.ingame.per_second_projector import (  # noqa: E402
    DEFAULT_NOMINAL_COVERAGES,
    EVAL_CURVE_V2,
    IntervalCalibrator,
    _laplace_z_for_coverage,
)

_GRID = [
    "06min(midQ1)", "12min(endQ1)", "18min(midQ2)", "24min(endQ2/half)",
    "30min(midQ3)", "36min(endQ3)", "42min(midQ4)",
]
_N = 6000
_RNG = np.random.default_rng(20260531)


def _resids(calib, dist):
    out = {}
    for label in _GRID:
        rem = max(0.0, 48.0 - float(label.split("min")[0]))
        ps = {}
        for stat in PLAYER_STATS:
            mae = calib._mae_at(stat, rem)
            if mae <= 0:
                continue
            if dist == "laplace":
                ps[stat] = _RNG.laplace(0.0, mae, _N).tolist()
            elif dist == "gaussian":
                ps[stat] = _RNG.normal(0.0, mae * math.sqrt(math.pi / 2), _N).tolist()
            else:
                t = _RNG.standard_t(3, _N)
                t = t / float(np.mean(np.abs(t))) * mae
                ps[stat] = t.tolist()
        out[label] = ps
    return out


def main():
    lines = []
    calib = IntervalCalibrator.from_eval_curve(EVAL_CURVE_V2)
    lines.append("== z_source: %s ==" % calib.z_source)
    lines.append("")
    lines.append("CLOSED-FORM LAPLACE z (replaces flat z_mult=1.0):")
    for nom in DEFAULT_NOMINAL_COVERAGES:
        lines.append("  nominal %.0f%% -> z = -ln(1-%.2f) = %.4f"
                     % (nom * 100, nom, _laplace_z_for_coverage(nom)))
    lines.append("  (flat z=1.0 band covers 1-e^-1 = %.4f of a Laplace = ~63%%)"
                 % (1 - math.exp(-1)))
    lines.append("")

    # Per-stat per-bucket z is constant across stats in the Laplace fallback,
    # but we ALSO fit empirically so the report shows per-stat z's that adapt.
    out = {"z_source_fallback": calib.z_source}

    for dist in ("laplace", "gaussian", "heavy"):
        resids = _resids(calib, dist)
        # fallback (Laplace closed-form) coverage
        rep_fb = calib.calibrate_coverage(resids)
        # empirically fitted coverage
        fitted = calib.fit_z_from_residuals(resids)
        rep_fit = fitted.calibrate_coverage(resids)
        lines.append("=" * 64)
        lines.append("HELD-OUT RESIDUAL DIST = %s" % dist.upper())
        for nom in DEFAULT_NOMINAL_COVERAGES:
            lines.append("  --- nominal %.0f%% ---" % (nom * 100))
            pooled_fb = rep_fb["by_nominal"][float(nom)]["pooled_by_stat"]
            pooled_ft = rep_fit["by_nominal"][float(nom)]["pooled_by_stat"]
            lines.append("    stat | laplace-fallback z(42min..6min) | "
                         "fb_cov | empirical z(42..6) | fit_cov")
            for stat in PLAYER_STATS:
                fb_zs = [round(calib.z_at(stat, max(0.0, 48 - m), nominal=nom), 3)
                         for m in (6, 24, 42)]
                ft_zs = [round(fitted.z_at(stat, max(0.0, 48 - m), nominal=nom), 3)
                         for m in (6, 24, 42)]
                fbc = pooled_fb.get(stat, {}).get("pooled_achieved_coverage")
                ftc = pooled_ft.get(stat, {}).get("pooled_achieved_coverage")
                lines.append("    %-4s | %-30s | %-6s | %-18s | %s"
                             % (stat, fb_zs, fbc, ft_zs, ftc))
        out[dist] = {
            "fallback": rep_fb["by_nominal"],
            "empirical": rep_fit["by_nominal"],
        }

    Path("scripts/ingame/_coverage_report.txt").write_text(
        "\n".join(lines), encoding="utf-8")
    Path("scripts/ingame/_coverage_report.json").write_text(
        json.dumps(out, indent=2, default=float), encoding="utf-8")
    print("\n".join(lines))
    print("\nWROTE scripts/ingame/_coverage_report.txt + .json")


if __name__ == "__main__":
    main()
