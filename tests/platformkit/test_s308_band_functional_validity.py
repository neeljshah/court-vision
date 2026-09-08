"""Focused S308 seal and nested-label-isolation checks."""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate import s101_aci_coverage as s101
from scripts.platformkit.eval_gate import s308_band_functional_validity as s308


def test_s308_seal_and_outer_labels_cannot_change_calibration_band() -> None:
    raw = s308.PREREG.read_bytes().replace(b"\r\n", b"\n")
    prefix, declared = raw.split(b"SEAL_SHA256:", 1)
    assert hashlib.sha256(prefix).hexdigest() == declared.strip().decode("ascii")
    calibration = pd.DataFrame({
        "p": np.linspace(0.05, 0.95, 1600), "y": np.tile([0.0, 1.0], 800),
        "cell": ["P1"] * 1600, "game": ["c%04d" % i for i in range(1600)],
        "date": ["2025-01-01"] * 1600, "ts": ["2025-01-01T00:00:00"] * 1600,
        "period_bucket": ["P1"] * 1600,
    })
    outer = pd.DataFrame({
        "p": [0.2, 0.8], "y": [0.0, 1.0], "cell": ["P1", "P1"],
        "game": ["outer_a", "outer_b"], "date": ["2025-02-01", "2025-02-01"],
        "ts": ["2025-02-01T00:00:00", "2025-02-01T00:01:00"],
        "period_bucket": ["P1", "P1"],
    })
    changed = outer.assign(y=[1.0, 0.0])
    first, fit = s101.run_fold(calibration, outer, "p", 0.10)
    second, fit_changed = s101.run_fold(calibration, changed, "p", 0.10)
    assert fit == fit_changed
    assert np.allclose(first["p"], second["p"])
    assert np.allclose(first["lo_static"], second["lo_static"])
    assert np.allclose(first["hi_static"], second["hi_static"])
    # Positive control: the SAME comparison does move when the CALIBRATION labels move,
    # so the assertions above measure label isolation, not determinism.
    moved = calibration.assign(y=np.ones(len(calibration)))
    control, fit_moved = s101.run_fold(moved, outer, "p", 0.10)
    assert s101.calibrate(moved, "p", 0.10) != s101.calibrate(calibration, "p", 0.10)
    assert fit_moved["pooled_half_width"] != fit["pooled_half_width"]
    assert not np.allclose(first["lo_static"], control["lo_static"])
