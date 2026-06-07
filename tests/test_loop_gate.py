"""Unit test for src.loop.gate -- the universal honest GATE.

Self-contained (no gamelogs / no network): each candidate signal injects a
synthetic leak-safe :class:`FeatureBundle` via ``signal._gate_matrix`` so the gate
runs fast and offline. The matrix is built so that:

  * the KNOWN-GOOD signal column carries real, target-aligned information that the
    FULL base features do NOT already contain -> must SHIP, and
  * the NOISE signal column is pure random noise -> must REJECT.

Run:
    python -m pytest tests/test_loop_gate.py -q
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.loop.gate import (  # noqa: E402
    FeatureBundle, benjamini_hochberg, evaluate)
from src.loop.signal import (  # noqa: E402
    AsOfContext, Hypothesis, Signal, Verdict)


def _dates(n: int) -> list:
    base = np.datetime64("2024-10-22")
    return [str((base + np.timedelta64(int(i // 12), "D"))) for i in range(n)]


def _make_bundle(*, n: int = 1400, p: int = 8, useful: bool, seed: int) -> FeatureBundle:
    """Build a synthetic leak-safe matrix.

    base: p weakly-predictive features. The TRUE target depends on base + an extra
    latent term. If ``useful``, the signal column reveals that latent term (so it
    adds marginal information on top of the full model); otherwise it is noise.
    """
    rng = np.random.default_rng(seed)
    base = rng.normal(size=(n, p))
    latent = rng.normal(size=n)  # info NOT in base
    noise = rng.normal(size=n) * 0.5
    target = (base @ rng.normal(size=p) * 0.4) + 2.5 * latent + noise
    if useful:
        signal_col = latent + rng.normal(size=n) * 0.15  # high-SNR view of latent
    else:
        signal_col = rng.normal(size=n)  # uninformative
    return FeatureBundle(base=base, signal_col=signal_col, target=target,
                         dates=_dates(n))


class _StubSignal(Signal):
    """A signal whose value is irrelevant (matrix is injected); satisfies the ABC."""

    target = "pts"
    scope = "pregame"

    def __init__(self, name: str, bundle: FeatureBundle) -> None:
        super().__init__(store=None)
        self.name = name
        self._gate_matrix = bundle

    def build(self, ctx: AsOfContext):
        return 0.0

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(name=self.name, target=self.target, scope=self.scope,
                          statement="test signal")


def test_known_good_signal_ships():
    sig = _StubSignal("known_good", _make_bundle(useful=True, seed=7))
    res = evaluate(sig, device="cpu", n_splits=4)
    assert res.verdict == Verdict.SHIP, (res.verdict, res.reason, res.wf_folds)
    assert res.wf_all_improve and all(d < 0 for d in res.wf_folds)
    assert res.ablation_pass and res.ablation_delta < 0
    assert res.null_pass and res.fdr_pass


def test_noise_signal_rejected():
    sig = _StubSignal("pure_noise", _make_bundle(useful=False, seed=11))
    res = evaluate(sig, device="cpu", n_splits=4)
    assert res.verdict == Verdict.REJECT, (res.verdict, res.reason, res.wf_folds)
    assert not (res.wf_all_improve and res.null_pass and res.ablation_pass)


def test_no_matrix_defers():
    class _Bare(Signal):
        name = "bare"
        target = "winprob"  # no wired matrix loader -> DEFER

        def build(self, ctx):
            return None

        def hypothesis(self):
            return Hypothesis(name="bare", target="winprob", scope="pregame",
                              statement="x")

    res = evaluate(_Bare(), device="cpu")
    assert res.verdict == Verdict.DEFER


def test_benjamini_hochberg_basic():
    # one clearly-significant, rest null -> only the significant survives at q=0.10
    flags = benjamini_hochberg([0.001, 0.6, 0.8, 0.4], q=0.10)
    assert flags[0] is True
    assert flags[1:] == [False, False, False]
    # all null -> none survive
    assert benjamini_hochberg([0.9, 0.8, 0.7], q=0.10) == [False, False, False]
    # NaN/None handled
    assert benjamini_hochberg([None, float("nan")]) == [False, False]


if __name__ == "__main__":
    test_benjamini_hochberg_basic()
    test_no_matrix_defers()
    test_known_good_signal_ships()
    test_noise_signal_rejected()
    print("ok")
