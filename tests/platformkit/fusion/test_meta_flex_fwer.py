"""Per-file test: meta_flex_fwer -- alpha tightens with K, BH step-up, ledger non-reset."""
from __future__ import annotations

import os

from scripts.platformkit.improve.fusion.meta_flex_fwer import (
    bh_threshold, fusion_alpha, load_k, meta_flex_k, persist_k,
)


def test_meta_flex_k_is_the_product():
    assert meta_flex_k(2, 3, 4, 2) == 48
    # each factor clamps to >=1 so a degenerate single choice does not collapse K to 0
    assert meta_flex_k(0, 3, 1, 0) == 3


def test_alpha_strictly_decreases_in_k():
    eps = 0.05
    prev = fusion_alpha(eps, 1)
    assert prev == eps
    for k in (2, 5, 50, 256):
        a = fusion_alpha(eps, k)
        assert a < prev, (k, a, prev)
        prev = a


def test_candidate_clearing_at_k1_fails_at_k50_same_p():
    eps, p = 0.05, 0.03
    assert p <= fusion_alpha(eps, 1)        # clears uncorrected
    assert p > fusion_alpha(eps, 50)        # same p does NOT clear at K=50


def test_bh_threshold_matches_hand_computed_example():
    # m=4, eps=0.05: rank bars are .0125, .025, .0375, .05. p=[.01,.02,.04,.5]:
    #   .01<=.0125 (pass), .02<=.025 (pass), .04>.0375 (fail), .5>.05 (fail)
    #   step-up keeps the LARGEST passing p -> .02
    t = bh_threshold([0.01, 0.02, 0.04, 0.5], eps=0.05)
    assert abs(t - 0.02) < 1e-12, t


def test_bh_returns_zero_when_nothing_clears():
    assert bh_threshold([0.9, 0.8, 0.7], eps=0.05) == 0.0
    assert bh_threshold([], eps=0.05) == 0.0


def test_ledger_k_is_cumulative_and_not_recomputable_downward(tmp_path):
    ledger = os.path.join(str(tmp_path), "fusion_k.jsonl")
    assert load_k(ledger, "FAMILY_STACK_OOF") == 0
    t1 = persist_k(ledger, "FAMILY_STACK_OOF", 10)
    assert t1 == 10
    t2 = persist_k(ledger, "FAMILY_STACK_OOF", 5)   # splitting cycles cannot reset
    assert t2 == 15
    assert load_k(ledger, "FAMILY_STACK_OOF") == 15
    # a later read can only ADD; the running total never shrinks
    assert load_k(ledger, "FAMILY_STACK_OOF") >= t1
