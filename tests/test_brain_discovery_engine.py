"""P-loop — the deterministic LLM-free feature-discovery engine (src/loop/discovery.py).

Proves the closed-loop proposer: enumerate -> cheap-screen -> the EXISTING honest gate decides. The
load-bearing safety property is that **a pure-noise target produces NO SHIP** — the gate (FDR + null-shuffle
+ all-folds-improve + ablation) filters the enumerated candidates; discovery only proposes, it never decides.
Self-contained: synthetic matrices, CPU, no 101K-row build.
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)                       # for `src.loop.*`
sys.path.insert(0, os.path.join(ROOT, "src"))  # for `loop.*` if needed

from src.loop.discovery import (  # noqa: E402
    TransformSpec, enumerate_specs, _apply, _screen_score, discover_from_matrix, DiscoveredSignal,
)
from src.loop.signal import Verdict  # noqa: E402


def _synth(n=600, p=5, seed=0):
    rng = np.random.default_rng(seed)
    base = rng.normal(size=(n, p))
    fc = [f"f{i}" for i in range(p)]
    dates = [f"2025-01-{1 + (i % 27):02d}" for i in range(n)]  # sortable ISO-ish
    return base, fc, dates, rng


# --------------------------------------------------------------------------- specs / apply

def test_apply_transforms_are_pure_functions():
    cols = {"a": np.array([1.0, 2.0, 3.0]), "b": np.array([2.0, 4.0, 8.0])}
    assert np.allclose(_apply(TransformSpec("interact", ("a", "b")), cols), [2, 8, 24])
    assert np.allclose(_apply(TransformSpec("diff", ("a", "b")), cols), [-1, -2, -5])
    assert np.allclose(_apply(TransformSpec("square", ("a",)), cols), [1, 4, 9])
    r = _apply(TransformSpec("ratio", ("a", "b")), cols)
    assert r[0] > 0 and np.all(np.isfinite(r))


def test_enumerate_is_deterministic_and_family_deduped():
    base, fc, _, _ = _synth()
    target = base[:, 0] * 2.0 + np.random.default_rng(1).normal(size=base.shape[0])
    s1 = enumerate_specs(fc, base, target)
    s2 = enumerate_specs(fc, base, target)
    assert [s.name for s in s1] == [s.name for s in s2]          # deterministic
    fks = [s.family_key() for s in s1]
    assert len(fks) == len(set(fks))                              # family-deduped
    # passing the seen families excludes them all
    assert enumerate_specs(fc, base, target, seen_families=set(fks)) == []


def test_screen_surfaces_real_signal_and_rejects_collinear():
    base, fc, _, rng = _synth(seed=2)
    target = base[:, 0] * base[:, 1] + 0.1 * rng.normal(size=base.shape[0])  # planted interaction
    interact = base[:, 0] * base[:, 1]
    assert _screen_score(interact, target, base) > 0.2            # planted transform surfaces
    # a candidate identical to a base column is collinear -> rejected (-1)
    assert _screen_score(base[:, 0].copy(), target, base) == -1.0
    # a constant candidate is degenerate -> rejected
    assert _screen_score(np.ones(base.shape[0]), target, base) == -1.0


# --------------------------------------------------------------------------- end-to-end gate

def test_discovered_signal_uses_injected_bundle():
    from src.loop.gate import FeatureBundle
    base, fc, dates, rng = _synth(seed=3)
    cand = base[:, 0] * base[:, 1]
    b = FeatureBundle(base=base, signal_col=cand, target=base[:, 2], dates=dates)
    sig = DiscoveredSignal(TransformSpec("interact", ("f0", "f1")), "pts", b)
    assert sig._gate_matrix is b and sig.target == "pts"
    assert sig.hypothesis().source == "discovery"


def test_discover_runs_the_gate_and_noise_does_not_ship():
    # PURE NOISE target: independent of every base column and transform -> the honest gate must SHIP nothing.
    base, fc, dates, rng = _synth(n=700, p=5, seed=7)
    noise_target = rng.normal(size=base.shape[0])
    res = discover_from_matrix(base, noise_target, fc, dates, "pts", top_k=3, device="cpu")
    assert len(res) >= 1                                          # the pipeline ran the gate
    assert all(r.gate.verdict != Verdict.DEFER for r in res)      # real verdicts (data was sufficient)
    assert all(r.gate.verdict != Verdict.SHIP for r in res)      # SAFETY: noise never ships


def test_discover_screens_then_gates_a_planted_transform():
    base, fc, dates, rng = _synth(n=700, p=5, seed=11)
    # target driven by a transform the base columns don't trivially expose: a ratio.
    target = base[:, 0] / (np.abs(base[:, 1]) + 1.0) + 0.2 * rng.normal(size=base.shape[0])
    res = discover_from_matrix(base, target, fc, dates, "pts", top_k=4, device="cpu")
    assert res, "engine produced no gated candidates"
    # every gated candidate carries a real verdict and a screen score that beat the orthogonality filter
    assert all(r.screen_score > 0 for r in res)
    assert all(r.gate.verdict in (Verdict.SHIP, Verdict.VARIANCE_ONLY, Verdict.REJECT) for r in res)
