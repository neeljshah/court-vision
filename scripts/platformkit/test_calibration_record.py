"""Per-file test for scripts.platformkit.calibration_record.

Offline + deterministic, < 60s. Asserts the trust invariants:
  - reliability bins partition the data (per-bin n sums to total n);
  - the SPARSE flag fires exactly when n < 30;
  - every numeric row in the rendered output carries a SOURCE badge;
  - NO retracted measurement-artifact number appears in the output;
  - --png is guarded: no-raise when matplotlib is stubbed absent.
"""
from __future__ import annotations

import re
import sys
import time

import numpy as np

from scripts.platformkit import calibration_record as CR

# the documented retracted artifacts -- must NEVER appear in generated output
_RETRACTED = ("+18.38", "18.38", "0.119", "+54", "54%", "78.11", "8.94", "54.57")


def test_bins_partition_and_sparse_flag():
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 200)
    y = (rng.uniform(0, 1, 200) < p).astype(float)
    rows = CR.reliability_bins(p, y, n_bins=10)
    assert sum(r["n"] for r in rows) == len(p)          # exact partition
    for r in rows:
        assert r["sparse"] == (r["n"] < CR.SPARSE_N)     # flag fires iff n<30
        assert 0.0 <= r["pred"] <= 1.0 and 0.0 <= r["obs"] <= 1.0
        assert r["lo"] < r["hi"]


def test_sparse_boundary():
    # exactly 30 in one bin -> NOT sparse; 29 -> sparse
    p = np.full(30, 0.55)
    y = np.ones(30)
    rows = CR.reliability_bins(p, y)
    hit = [r for r in rows if r["n"] == 30]
    assert hit and not hit[0]["sparse"]
    rows29 = CR.reliability_bins(p[:29], y[:29])
    hit29 = [r for r in rows29 if r["n"] == 29]
    assert hit29 and hit29[0]["sparse"]


def test_output_every_numeric_row_badged_and_no_retracted():
    t0 = time.time()
    body = "\n".join(CR.build_sections())
    assert time.time() - t0 < 60.0
    badges = (CR.BADGE_MODEL, CR.BADGE_MARKET, CR.BADGE_ANCHOR)
    # every markdown data row that contains a numeric value carries a badge
    for line in body.splitlines():
        if not line.startswith("| "):
            continue
        if re.search(r"\|.*\d\.\d", line) and "bin |" not in line and "---" not in line:
            assert any(b in line for b in badges), f"unbadged numeric row: {line}"
    # no retracted artifact anywhere in the output
    for bad in _RETRACTED:
        assert bad not in body, f"retracted number leaked into output: {bad}"
    # market-efficient is a first-class, visible verdict
    assert "MARKET-EFFICIENT HERE" in body
    assert "edge_claimed=False" in body


def test_ascii_only():
    body = "\n".join(CR.build_sections())
    body.encode("ascii")   # raises if any non-ASCII slipped in


def test_png_guarded_no_raise_when_absent(monkeypatch):
    # simulate matplotlib being unavailable -> helper returns a note, never raises
    import builtins
    real_import = builtins.__import__

    def _blocked(name, *a, **k):
        if name == "matplotlib" or name.startswith("matplotlib."):
            raise ImportError("stubbed absent")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _blocked)
    recs = {"x": (np.array([0.5, 0.6]), np.array([0.5, 0.6]), np.array([1.0, 0.0]))}
    msg = CR._maybe_png(recs)
    assert "skipped" in msg and "matplotlib" in msg


def test_deterministic():
    a = "\n".join(CR.build_sections())
    b = "\n".join(CR.build_sections())
    assert a == b


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
