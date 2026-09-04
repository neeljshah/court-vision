"""Focused formula and preregistration checks for S278."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pandas as pd

from scripts.platformkit.s278_pooled_power_rescreen import MDE_Z80, mde80_from_losses


ROOT = Path(__file__).resolve().parents[2]


def _seal(path: Path) -> str:
    text = path.read_bytes().replace(b"\r\n", b"\n")
    before, marker, _after = text.partition(b"Seal SHA-256: ")
    assert marker
    return hashlib.sha256(before).hexdigest()


def test_s278_fixture_mde80_and_prereg_seals() -> None:
    loss_null = pd.Series([0.09, 0.25, 0.36, 0.64])
    loss_candidate = pd.Series([0.04, 0.16, 0.25, 0.49])
    clusters = pd.Series(["a", "a", "b", "b"])
    deltas = pd.Series([0.07, 0.13])
    expected = MDE_Z80 * deltas.std(ddof=1) / math.sqrt(2)
    assert math.isclose(mde80_from_losses(loss_null, loss_candidate, clusters), expected,
                        rel_tol=0.0, abs_tol=1e-15)
    for screen in ("S82", "S119"):
        prereg = ROOT / "docs" / "evidence" / "harness" / ("S278_%s_prereg_2026-09-04.md" % screen)
        normalized = prereg.read_bytes().replace(b"\r\n", b"\n")
        stated = normalized.decode("ascii").split("Seal SHA-256: ", 1)[1].splitlines()[0]
        assert stated == _seal(prereg)
