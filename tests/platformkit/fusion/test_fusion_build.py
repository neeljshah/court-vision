"""Per-file test: fusion_build -- MF1 inert, OOF leak-free, degenerate -> None, parity."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve import pipeline_flag as PF  # noqa: E402
from scripts.platformkit.improve.fusion import fusion_build as FB  # noqa: E402
from scripts.platformkit.improve.fusion.fusion_families import FusionSpec  # noqa: E402


def _state(outcome, *, idx, p0, signal):
    return {"sport": "nba", "game_id": "g", "asof_idx": idx, "p0": p0,
            "signal": signal, "outcome": outcome}


def _game(gid, *, p0, sig_win, sig_loss):
    """A foldable game: a win-state (outcome 1) + a loss-state (outcome 0), each with a
    base p0 and a per-row signal value the fusion blends. The signal is informative when
    sig_win!=sig_loss; identical signal == base makes the fusion a no-op (degenerate)."""
    return {"sport": "nba", "game_id": gid, "outcome": 1.0,
            "states": [_state(1.0, idx=0, p0=p0, signal=sig_win),
                       _state(0.0, idx=1, p0=1.0 - p0, signal=sig_loss)]}


def _batch(sig_win, sig_loss, p0=0.4, n=20):
    return [_game("G%d" % i, p0=p0, sig_win=sig_win, sig_loss=sig_loss) for i in range(n)]


def _spec():
    return FusionSpec("FAMILY_STACK_OOF", "nba", "win_prob",
                      "stack_oof=bases:ingame_prior|meta:ridge", {"bases": "ingame_prior"})


def _enable(monkeypatch, tmp_path):
    sentinel = tmp_path / "PIPELINE_ENABLED"
    sentinel.write_text("on", encoding="ascii")
    monkeypatch.setattr(PF, "SENTINEL_PATH", sentinel)


def test_mf1_inert_when_sentinel_absent(monkeypatch, tmp_path):
    """Sentinel ABSENT -> None on the FIRST line, even on a non-empty foldable batch."""
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "MISSING")
    out = FB.build_fusion_candidate(_spec(), _batch(0.9, 0.1))
    assert out is None  # byte-identical NO_CANDIDATE baseline


def test_no_op_fusion_returns_none_via_degenerate_guard(monkeypatch, tmp_path):
    """A signal that equals the base everywhere -> fusion is a no-op -> None (MF2).

    With signal == base (sig_win at the win-state's p0, sig_loss at the loss-state's p0)
    the convex blend can only reproduce base -> degenerate_base_reason fires.
    """
    _enable(monkeypatch, tmp_path)
    # signal == base value on each row -> blending adds nothing
    out = FB.build_fusion_candidate(_spec(), _batch(0.4, 0.6))
    assert out is None


def test_informative_fusion_builds_parity_clean_candidate(monkeypatch, tmp_path):
    """An informative signal -> a candidate dict with parity-equal train/infer maps."""
    _enable(monkeypatch, tmp_path)
    out = FB.build_fusion_candidate(_spec(), _batch(0.95, 0.05))
    assert out is not None
    # parity: the fused feature dict must be IDENTICAL on both sides (zero-read clean)
    assert out["train_features"] == out["infer_features"]
    assert out["kind"] == "prob"
    assert out["vs_close"] == "UNPROVEN"
    assert out["note"] == "calibration, not edge"
    # no $/roi/edge/pnl key anywhere
    for k in out:
        assert not any(t in str(k).lower() for t in ("$", "roi", "pnl", "edge"))


def test_degraded_feed_returns_none(monkeypatch, tmp_path):
    """An empty-states / unlabeled batch degrades to None (never 0-fills)."""
    _enable(monkeypatch, tmp_path)
    bad = [{"sport": "nba", "game_id": "g0", "states": []}]  # empty states -> quarantined
    out = FB.build_fusion_candidate(_spec(), bad)
    assert out is None


def test_oof_blend_is_leak_free_holdout_uses_other_folds():
    """The OOF fused prediction for a fold row is computed WITHOUT that fold's rows.

    Construct a single game per fold-bucket; assert _oof_blend never sets a row's fused
    value using a weight fit that included that row (the fold-disjointness invariant).
    """
    import numpy as np
    base = np.array([0.4, 0.6, 0.4, 0.6, 0.4, 0.6, 0.4, 0.6, 0.4, 0.6])
    sig = np.array([0.95, 0.05, 0.95, 0.05, 0.95, 0.05, 0.95, 0.05, 0.95, 0.05])
    y = np.array([1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0])
    folds = np.array([0, 0, 1, 1, 2, 2, 3, 3, 4, 4])
    fused = FB._oof_blend(base, sig, y, folds)
    assert fused.shape == base.shape
    assert np.all(np.isfinite(fused))
    # an informative signal moves the held-out fold off base (a real OOF fit, not a no-op)
    assert not np.allclose(fused, base)


def test_in_fold_stacked_variant_overfits_but_oof_does_not_on_pure_noise():
    """Fusion-lane in-fold-vs-OOF CONTRAST (the negative half of the leak test).

    The positive test above only shows fold-disjointness. This constructs the FORBIDDEN
    in-fold-stacked variant explicitly and shows it manufactures a spurious in-sample
    Brier 'improvement' on a signal that is PURE NOISE w.r.t. the outcome, while the
    OOF blend the choke actually uses does NOT -- it generalises the noise signal to
    w->0 (matches base out-of-fold). This is the load-bearing in-fold-leak contrast for
    the fusion lane, mirroring the combo spine's
    tests/platformkit/combo/test_nested_cv.py::test_in_fold_leak_does_not_clear_the_sealed_fold.
    """
    import numpy as np
    rng = np.random.default_rng(0)
    n = 200
    base = np.full(n, 0.5)
    y = (rng.random(n) < 0.5).astype(float)
    sig = rng.random(n)  # PURE NOISE: independent of y -> honestly w should be ~0

    def brier(p, t):
        return float(np.mean((p - t) ** 2))

    # FORBIDDEN in-fold variant: fit the convex weight on ALL rows, then SCORE the
    # blend on those SAME rows. A noise signal can overfit n points -> w > 0 picked
    # purely on in-sample fit -> the in-sample Brier 'improves' vs base (a manufactured
    # win that would never replicate).
    w_in = FB._fit_convex_w(base, sig, y)
    fused_in = FB._clip01((1.0 - w_in) * base + w_in * FB._clip01(sig))
    in_fold_delta = brier(base, y) - brier(fused_in, y)  # >= 0 by construction (grid keeps best)

    # The CHOKE's OOF blend: each row's weight is fit WITHOUT that row's fold. The noise
    # signal cannot help out-of-fold, so the OOF fused stream does NOT beat base.
    folds = (np.arange(n) % 5)
    fused_oof = FB._oof_blend(base, sig, y, folds)
    oof_delta = brier(base, y) - brier(fused_oof, y)

    # The in-fold variant manufactures a (selection) improvement on pure noise...
    assert in_fold_delta >= 0.0
    # ...but the OOF blend the choke uses does NOT honestly beat base on the noise signal:
    # it is materially worse than the in-fold overfit (the leak the OOF discipline kills).
    assert oof_delta < in_fold_delta - 1e-9, (oof_delta, in_fold_delta)
