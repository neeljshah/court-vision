"""Per-file tests for improve.parity_check -- train==inference feature parity.

Three invariants this file proves:
  (1) Identical train and inference dicts -> ok=True, no mismatches/zero_reads.
  (2) An injected 0.0-at-inference divergence (the most expensive bug class)
      -> ok=False, the feature is named in zero_reads.
  (3) A difference within the default tol (1e-9) -> ok=True (within tolerance).

Additional edge cases:
  (4) A non-zero divergence (not a zero-read) is caught in mismatches but NOT
      in zero_reads.
  (5) Key present in train but missing at inference -> caught (ok=False).
  (6) Key present at inference but not in train -> caught (ok=False).
  (7) Multiple injected zero-reads are all named.
  (8) A custom tol widens/narrows the acceptable band correctly.
  (9) Non-numeric feature values that differ are caught.
  (10) Empty dicts on both sides -> ok=True.

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/improve/test_parity_check.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make import work whether run via pytest from the repo root or standalone.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from improve.parity_check import parity_ok


# ---------------------------------------------------------------------------
# (1) Identical dicts -> ok
# ---------------------------------------------------------------------------


def test_identical_dicts_ok():
    feats = {"pts_l5": 22.4, "ast_l5": 7.1, "reb_l5": 5.3, "min_l5": 34.2}
    result = parity_ok(feats, feats.copy())
    assert result["ok"] is True
    assert result["mismatches"] == []
    assert result["zero_reads"] == []


def test_identical_single_feature_ok():
    result = parity_ok({"x": 0.75}, {"x": 0.75})
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# (2) Injected 0.0-at-inference divergence -> ok=False, named in zero_reads
# ---------------------------------------------------------------------------


def test_zero_read_single_feature_caught():
    """The canonical expensive bug: a feature reads 0.0 at inference but was
    non-zero at train time (e.g. wiring dropped the column).  Must appear in
    both mismatches AND zero_reads, by feature name."""
    train = {"ast_l5": 7.1, "pts_l5": 22.0}
    # Simulate pipeline that forgot to wire ast_l5 -> it reads 0.0.
    infer = {"ast_l5": 0.0, "pts_l5": 22.0}
    result = parity_ok(train, infer)

    assert result["ok"] is False
    zero_names = [m["feature"] for m in result["zero_reads"]]
    assert "ast_l5" in zero_names
    # pts_l5 agreed -> NOT in mismatches
    mismatch_names = [m["feature"] for m in result["mismatches"]]
    assert "pts_l5" not in mismatch_names


def test_zero_read_names_the_feature_exactly():
    """The zero_read entry must carry the exact feature key, train value,
    and infer value so the engineer can action it immediately."""
    train = {"blk_sigma": 1.42}
    infer = {"blk_sigma": 0.0}
    result = parity_ok(train, infer)
    assert result["ok"] is False
    assert len(result["zero_reads"]) == 1
    zr = result["zero_reads"][0]
    assert zr["feature"] == "blk_sigma"
    assert abs(zr["train"] - 1.42) < 1e-12
    assert abs(zr["infer"] - 0.0) < 1e-12
    assert zr["is_zero_read"] is True


# ---------------------------------------------------------------------------
# (3) Difference within tol -> ok (float arithmetic noise is not a wiring bug)
# ---------------------------------------------------------------------------


def test_within_tol_difference_is_ok():
    """A difference of tol/2 must not be flagged -- float serialisation noise
    should not trigger a false positive."""
    tol = 1e-9
    train = {"pts_sigma": 4.123456789}
    infer = {"pts_sigma": 4.123456789 + tol / 2}  # half a tol unit smaller
    result = parity_ok(train, infer, tol=tol)
    assert result["ok"] is True
    assert result["mismatches"] == []


def test_exactly_at_tol_boundary_is_ok():
    """Difference == tol exactly -> within tolerance (<=, not <).

    Use 0.0 as base so that 0.0 + tol == tol exactly in IEEE 754
    (no rounding error when adding tol to a non-zero base).
    """
    tol = 1e-9
    train = {"x": 0.0}
    infer = {"x": tol}   # diff == tol exactly: abs(tol - 0.0) == tol
    result = parity_ok(train, infer, tol=tol)
    # NOTE: 0.0 at train and non-zero at infer is NOT a zero_read (zero_read
    # is only flagged when INFERENCE is 0.0 but TRAIN was non-zero).
    assert result["ok"] is True


def test_just_above_tol_boundary_is_mismatch():
    """Difference == tol + epsilon -> flagged as a mismatch."""
    tol = 1e-9
    train = {"x": 1.0}
    infer = {"x": 1.0 + tol + 1e-12}
    result = parity_ok(train, infer, tol=tol)
    assert result["ok"] is False
    assert any(m["feature"] == "x" for m in result["mismatches"])


# ---------------------------------------------------------------------------
# (4) Non-zero divergence is a mismatch but NOT a zero_read
# ---------------------------------------------------------------------------


def test_nonzero_divergence_is_mismatch_not_zero_read():
    """If inference differs from train but is not 0.0, it is a mismatch but
    NOT a zero_read (the engineer sees a numeric shift, not a silent drop)."""
    train = {"reb_l5": 8.5}
    infer = {"reb_l5": 4.2}  # wrong but non-zero
    result = parity_ok(train, infer)
    assert result["ok"] is False
    assert len(result["mismatches"]) == 1
    assert result["mismatches"][0]["is_zero_read"] is False
    assert result["zero_reads"] == []


# ---------------------------------------------------------------------------
# (5) Missing key at inference
# ---------------------------------------------------------------------------


def test_key_missing_at_inference_is_caught():
    train = {"ast_l5": 7.1, "pts_l5": 22.0, "reb_l5": 5.0}
    infer = {"pts_l5": 22.0, "reb_l5": 5.0}  # ast_l5 dropped from pipeline
    result = parity_ok(train, infer)
    assert result["ok"] is False
    names = [m["feature"] for m in result["mismatches"]]
    assert "ast_l5" in names


# ---------------------------------------------------------------------------
# (6) Extra key at inference (not in train)
# ---------------------------------------------------------------------------


def test_extra_key_at_inference_is_caught():
    train = {"pts_l5": 22.0}
    infer = {"pts_l5": 22.0, "new_signal": 0.99}  # added to pipeline but not train
    result = parity_ok(train, infer)
    assert result["ok"] is False
    names = [m["feature"] for m in result["mismatches"]]
    assert "new_signal" in names


# ---------------------------------------------------------------------------
# (7) Multiple zero-reads are all named
# ---------------------------------------------------------------------------


def test_multiple_zero_reads_all_named():
    train = {"f1": 1.0, "f2": 2.5, "f3": 0.8, "f4": 3.3}
    # f2 and f4 dropped -> read 0.0 at inference
    infer = {"f1": 1.0, "f2": 0.0, "f3": 0.8, "f4": 0.0}
    result = parity_ok(train, infer)
    assert result["ok"] is False
    zero_names = {m["feature"] for m in result["zero_reads"]}
    assert zero_names == {"f2", "f4"}
    assert len(result["zero_reads"]) == 2


# ---------------------------------------------------------------------------
# (8) Custom tol
# ---------------------------------------------------------------------------


def test_custom_tol_wider_accepts_small_diff():
    train = {"x": 1.0}
    infer = {"x": 1.0 + 0.01}  # 0.01 diff
    # Default tol (1e-9) would flag this.
    assert parity_ok(train, infer)["ok"] is False
    # Custom tol=0.02 should accept it.
    assert parity_ok(train, infer, tol=0.02)["ok"] is True


# ---------------------------------------------------------------------------
# (9) Non-numeric feature values that differ are caught
# ---------------------------------------------------------------------------


def test_non_numeric_divergence_is_caught():
    train = {"regime": "regular", "score": 1.0}
    infer = {"regime": "playoffs", "score": 1.0}
    result = parity_ok(train, infer)
    assert result["ok"] is False
    names = [m["feature"] for m in result["mismatches"]]
    assert "regime" in names
    assert "score" not in names


def test_non_numeric_matching_values_ok():
    feats = {"regime": "regular"}
    result = parity_ok(feats, feats.copy())
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# (10) Empty dicts on both sides -> ok
# ---------------------------------------------------------------------------


def test_empty_dicts_ok():
    result = parity_ok({}, {})
    assert result["ok"] is True
    assert result["mismatches"] == []
    assert result["zero_reads"] == []


# ---------------------------------------------------------------------------
# Train-zero is NOT a zero_read (only inference-zero matters)
# ---------------------------------------------------------------------------


def test_train_zero_inference_nonzero_is_mismatch_not_zero_read():
    """If train had 0.0 but inference returned something non-zero, it is a plain
    mismatch (pipeline added a signal post-train), NOT a zero_read."""
    train = {"new_feat": 0.0}
    infer = {"new_feat": 1.5}
    result = parity_ok(train, infer)
    assert result["ok"] is False
    assert result["zero_reads"] == []  # inference is NOT 0.0
    assert len(result["mismatches"]) == 1


def test_both_zero_is_ok():
    """If both train and inference have 0.0 for a feature, that is fine --
    it is a feature that legitimately carries a zero for this observation."""
    result = parity_ok({"x": 0.0}, {"x": 0.0})
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# Standalone runner (python tests/improve/test_parity_check.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
