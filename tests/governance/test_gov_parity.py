"""tests.governance.test_gov_parity -- train==inference parity as a HARD gate.

A candidate whose train and inference feature dicts agree PASSES. A 0.0-at-
inference divergence (the silent-zero wiring bug) BLOCKS. A general value
divergence BLOCKS. A missing-key divergence BLOCKS. The batch verdict is the AND
over every candidate: one divergence anywhere BLOCKS the whole stack. Run ONLY
this file (a full pytest run freezes the box):

    python -m pytest tests/governance/test_gov_parity.py -q
"""
from __future__ import annotations

import pytest

from governance import parity_check as gp


# --------------------------------------------------------------------------- #
# single candidate                                                            #
# --------------------------------------------------------------------------- #
def test_parity_holds_passes():
    train = {"home_edge": 1.5, "rest": 2.0, "pace": 99.4}
    infer = {"home_edge": 1.5, "rest": 2.0, "pace": 99.4}
    v = gp.check_candidate(train, infer, name="nba_winprob")
    assert v["ok"] is True
    assert v["blocked"] is False
    assert v["mismatches"] == []
    assert v["zero_reads"] == []
    assert v["name"] == "nba_winprob"
    assert v["version"] == gp.PARITY_GATE_VERSION


def test_zero_read_divergence_blocks():
    """A feature that trained on signal but reads 0.0 at inference BLOCKS."""
    train = {"home_edge": 1.5, "rest": 2.0}
    infer = {"home_edge": 1.5, "rest": 0.0}  # rest silently read 0.0
    v = gp.check_candidate(train, infer)
    assert v["ok"] is False
    assert v["blocked"] is True
    feats = {m["feature"] for m in v["mismatches"]}
    assert "rest" in feats
    zr = {z["feature"] for z in v["zero_reads"]}
    assert "rest" in zr, v["zero_reads"]


def test_general_value_divergence_blocks():
    train = {"home_edge": 1.5, "rest": 2.0}
    infer = {"home_edge": 1.5, "rest": 1.0}  # diverges but not a zero-read
    v = gp.check_candidate(train, infer)
    assert v["ok"] is False
    # diverges, but is NOT a silent zero (infer != 0.0).
    assert v["zero_reads"] == []
    feats = {m["feature"] for m in v["mismatches"]}
    assert "rest" in feats


def test_missing_key_divergence_blocks():
    train = {"home_edge": 1.5, "rest": 2.0}
    infer = {"home_edge": 1.5}  # rest never wired at inference
    v = gp.check_candidate(train, infer)
    assert v["ok"] is False
    feats = {m["feature"] for m in v["mismatches"]}
    assert "rest" in feats


def test_within_tolerance_passes():
    train = {"x": 1.0}
    infer = {"x": 1.0 + 1e-12}
    v = gp.check_candidate(train, infer)
    assert v["ok"] is True


# --------------------------------------------------------------------------- #
# batch (AND over candidates)                                                 #
# --------------------------------------------------------------------------- #
def test_batch_all_pass():
    cands = [
        ({"a": 1.0, "b": 2.0}, {"a": 1.0, "b": 2.0}),
        ({"c": 3.0}, {"c": 3.0}),
    ]
    v = gp.check_candidates(cands)
    assert v["ok"] is True
    assert v["blocked"] is False
    assert v["n_candidates"] == 2
    assert v["failures"] == []


def test_batch_one_failure_blocks_all():
    cands = [
        ({"a": 1.0}, {"a": 1.0}),          # passes
        ({"b": 2.0}, {"b": 0.0}),          # zero-read -> blocks the whole batch
    ]
    v = gp.check_candidates(cands)
    assert v["ok"] is False
    assert v["blocked"] is True
    assert len(v["failures"]) == 1
    assert v["failures"][0]["name"] == "candidate[1]"


def test_batch_mapping_form_names_preserved():
    cands = {
        "nba_winprob": ({"a": 1.0}, {"a": 1.0}),
        "mlb_ml": ({"b": 2.0}, {"b": 0.0}),
    }
    v = gp.check_candidates(cands)
    assert v["ok"] is False
    failed = {f["name"] for f in v["failures"]}
    assert failed == {"mlb_ml"}


def test_malformed_batch_blocks():
    v = gp.check_candidates([("only_one_element",)])  # not a (train, infer) pair
    assert v["ok"] is False
    assert v["blocked"] is True


def test_non_mapping_features_block():
    v = gp.check_candidates([("nottadict", {"a": 1.0})])
    assert v["ok"] is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
