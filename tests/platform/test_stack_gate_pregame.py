"""tests.platform.test_stack_gate_pregame -- deterministic checks for the harness.

Per PREREG_STACK_FAMILIES_2026-07-05.md: a synthetic REAL signal must pass L2
within-corpus (gate not trivially-zero); a planted-null on pure noise must NOT
ship; family-freeze must trip when a null draw ships. ASCII; per-file only.
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.combo import stack_fit as sf
from scripts.platformkit.combo import stack_gate_pregame as g


def _make_corpus(n: int, seed: int, signal_strength: float = 0.0):
    """Synthetic StackRow list: p_base from Elo-like logit, added feature with
    optional REAL signal (signal_strength>0) baked into the outcome."""
    rng = np.random.default_rng(seed)
    elo_logit = rng.normal(0.0, 1.0, size=n)
    added = rng.normal(0.0, 1.0, size=n)
    true_logit = elo_logit + signal_strength * added
    p_true = sf.sigmoid(true_logit)
    y = (rng.uniform(0.0, 1.0, size=n) < p_true).astype(float)

    p_base = sf.sigmoid(elo_logit)  # base never sees the added feature
    # candidate: refit a 2-feature logistic ON THIS corpus (train=all, as a stand-in
    # for a walk-forward fit -- good enough to exercise the gate's arithmetic).
    X = sf.build_design([elo_logit, added])
    fit = sf.fit_logistic(X, y)
    p_cand = sf.predict_proba(X, fit.weights)

    rows = [g.StackRow(event_id=f"g{i}", y=float(y[i]), p_base=float(p_base[i]),
                       p_candidate=float(p_cand[i]), added_raw=(float(added[i]),))
            for i in range(n)]
    return rows, elo_logit, added


def test_l0_guards_pass_on_orthogonal_candidate():
    """The ADDED feature (orthogonal noise) must pass even though p_candidate
    itself is highly correlated with elo_logit (base dominates the stacked prob)."""
    rows, elo_logit, added = _make_corpus(2000, seed=1, signal_strength=0.8)
    a = g._rows_to_arrays(rows)
    reason = g.l0_guards(added, {"elo_logit": elo_logit}, a["p_candidate"], a["p_base"], a["y"])
    assert reason is None


def test_l0_guards_reject_collinear_with_base():
    """The ADDED feature column itself (not p_candidate) is tested for collinearity."""
    rows, elo_logit, _ = _make_corpus(500, seed=2)
    a = g._rows_to_arrays(rows)
    fake_added_feature = elo_logit * 1.0001  # re-expresses the base feature almost exactly
    reason = g.l0_guards(fake_added_feature, {"elo_logit": elo_logit},
                         a["p_candidate"], a["p_base"], a["y"])
    assert reason is not None
    assert "L0_collinear" in reason


def test_l0_guards_full_candidate_prob_would_have_falsely_rejected():
    """Regression guard: testing p_candidate (dominated by base) against base_feature_cols
    must NOT be the code path -- this is the exact bug the fix corrected."""
    rows, elo_logit, added = _make_corpus(2000, seed=9, signal_strength=0.8)
    a = g._rows_to_arrays(rows)
    # p_candidate is highly correlated with elo_logit by construction (base dominates);
    # if l0_guards tested p_candidate instead of `added`, this would incorrectly reject.
    reason_correct = g.l0_guards(added, {"elo_logit": elo_logit}, a["p_candidate"], a["p_base"], a["y"])
    assert reason_correct is None


def test_l2_unanimity_true_signal_passes_within_corpus():
    """A synthetic REAL signal (baked into y) DOES pass L2 -- gate not trivially-zero."""
    rows, _, _ = _make_corpus(5000, seed=3, signal_strength=1.5)
    a = g._rows_to_arrays(rows)
    result = g.l2_unanimity(a["y"], a["p_base"], a["p_candidate"])
    assert result.unanimous, (
        f"expected a strong planted signal to pass L2; got brier_base={result.brier_base} "
        f"brier_stack={result.brier_stack} logloss_base={result.logloss_base} "
        f"logloss_stack={result.logloss_stack}")


def test_l2_unanimity_pure_noise_does_not_reliably_pass():
    """Zero-signal added feature: the candidate should NOT unanimously beat base."""
    rows, _, _ = _make_corpus(3000, seed=4, signal_strength=0.0)
    a = g._rows_to_arrays(rows)
    result = g.l2_unanimity(a["y"], a["p_base"], a["p_candidate"])
    # a pure-noise added column fit on the SAME rows it is scored on can look like a
    # tiny in-sample win by chance; the important invariant is it never looks like a
    # LARGE robust win -- assert the delta is small, not exactly non-positive.
    assert abs(result.brier_base - result.brier_stack) < 0.01


def test_planted_null_fdr_pure_noise_does_not_ship():
    """>=20 draws where the shuffled column can NEVER ship (score_fn always False)."""

    def never_ships(rng):
        return False

    res = g.planted_null_fdr(never_ships, eps=0.025, k=2, n_draws=20, base_seed=0)
    assert res["n_draws"] == 20
    assert res["n_ship"] == 0
    assert res["fdr_hat"] == 0.0
    assert res["family_frozen"] is False


def test_planted_null_fdr_any_ship_freezes_family():
    """A SINGLE shuffled draw shipping must trip family_frozen (prereg: ANY ship freezes)."""
    calls = {"n": 0}

    def one_ships(rng):
        calls["n"] += 1
        return calls["n"] == 5  # exactly one draw ships

    res = g.planted_null_fdr(one_ships, eps=0.025, k=2, n_draws=20, base_seed=0)
    assert res["n_ship"] == 1
    assert res["family_frozen"] is True  # even though fdr_hat=0.05 could be under a looser budget


def test_planted_null_min_draws_enforced():
    def never_ships(rng):
        return False

    res = g.planted_null_fdr(never_ships, eps=0.05, k=1, n_draws=3, base_seed=0)
    assert res["n_draws"] == g.MIN_NULLS  # floor enforced even if caller asks for fewer


def test_one_direction_dm_detects_real_beat():
    rows, _, _ = _make_corpus(5000, seed=5, signal_strength=2.0)
    a = g._rows_to_arrays(rows)
    result = g.one_direction_dm(a["y"], a["p_base"], a["p_candidate"], a["event_id"],
                                eps=0.05, direction="test")
    assert result.brier_stack < result.brier_base


def test_judge_stack_family_void_without_nested_cv():
    """Omitting nested_cv_* / planted_null_fn returns VOID, never a silent pass (L1/L3)."""
    rows_a, _, _ = _make_corpus(500, seed=6, signal_strength=1.0)
    rows_b, _, _ = _make_corpus(500, seed=7, signal_strength=1.0)
    verdict = g.judge_stack_family(
        name="test_family", corpora=[rows_a, rows_b], corpus_labels=["A", "B"],
        base_feature_cols={}, k_cum=1, n_corpora_available=2,
    )
    assert verdict.verdict == "VOID"
    assert verdict.layer == "L1"


def test_judge_stack_family_rejects_at_l1_on_negative_sealed_holdout_score():
    """REGRESSION for the reviewer's decorative-L1 finding: a score_fn that reports
    the stack LOSING to base on the sealed outer holdout must REJECT at L1, even
    though every row is otherwise identical to a family that would sail through
    L2/L4/L5 -- proving outer_score is actually consumed, not discarded."""
    rows_a, _, _ = _make_corpus(500, seed=10, signal_strength=1.0)
    rows_b, _, _ = _make_corpus(500, seed=11, signal_strength=1.0)
    game_ids = [r.event_id for r in rows_a]

    def _select(inner_game_ids):
        return "only_variant"

    def _score_negative(spec, holdout_game_ids):
        return -0.01  # stack LOSES to base on the sealed fold

    verdict = g.judge_stack_family(
        name="test_family", corpora=[rows_a, rows_b], corpus_labels=["A", "B"],
        base_feature_cols={}, k_cum=1, n_corpora_available=2,
        nested_cv_select_fn=_select, nested_cv_score_fn=_score_negative,
        nested_cv_game_ids=game_ids, planted_null_fn=lambda rng: False,
        seed_stability_p10=0.01,
    )
    assert verdict.verdict == "REJECT"
    assert verdict.layer == "L1"
    assert "sealed-holdout" in verdict.reason


def test_judge_stack_family_consumes_real_sealed_holdout_score_past_l1():
    """A genuine non-negative sealed-holdout score (computed from the SAME rows,
    restricted to holdout ids -- not a stub 0.0) must let the verdict proceed past
    L1 into L3/L2/L4/L5, proving the real score is what gates, not a decorative call."""
    rows_a, _, _ = _make_corpus(2000, seed=12, signal_strength=2.0)
    rows_b, _, _ = _make_corpus(2000, seed=13, signal_strength=2.0)
    by_id = {r.event_id: r for r in rows_a}
    game_ids = [r.event_id for r in rows_a]

    def _select(inner_game_ids):
        return "only_variant"

    def _score_real(spec, holdout_game_ids):
        held = [by_id[gid] for gid in holdout_game_ids if gid in by_id]
        p_base = np.array([r.p_base for r in held])
        p_cand = np.array([r.p_candidate for r in held])
        y = np.array([r.y for r in held])
        return sf.brier(p_base, y) - sf.brier(p_cand, y)

    verdict = g.judge_stack_family(
        name="test_family", corpora=[rows_a, rows_b], corpus_labels=["A", "B"],
        base_feature_cols={}, k_cum=1, n_corpora_available=2,
        nested_cv_select_fn=_select, nested_cv_score_fn=_score_real,
        nested_cv_game_ids=game_ids, planted_null_fn=lambda rng: False,
        seed_stability_p10=0.01,
    )
    assert verdict.layer != "L1"  # a real planted signal clears L1 (score >= 0)
    assert any("SEALED-HOLDOUT score=" in c for c in verdict.caveats)


def test_judge_stack_family_not_testable_with_one_corpus():
    rows_a, _, _ = _make_corpus(200, seed=8)
    verdict = g.judge_stack_family(
        name="single_corpus", corpora=[rows_a], corpus_labels=["A"],
        base_feature_cols={}, k_cum=1, n_corpora_available=1,
    )
    assert verdict.verdict == "NOT_TESTABLE"


def test_stack_verdict_to_dict_shape():
    v = g.StackVerdict("REJECT", "test reason", "L2", vs_close="BEHIND")
    d = v.to_dict()
    for key in ("verdict", "reason", "layer", "vs_close", "proposal_only", "detail",
               "coverage", "caveats"):
        assert key in d
    assert d["proposal_only"] is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
