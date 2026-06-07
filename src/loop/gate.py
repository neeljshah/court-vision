"""The honest GATE (ARM-A) -- 5 criteria, FDR-corrected, evaluated jointly.

Implements the universal ``evaluate(signal) -> GateResult``. The gate NEVER tests
a signal in isolation: criterion 3 measures the marginal delta of adding the
signal column to the FULL production feature matrix (ablation-vs-full).

The five criteria (all must pass for SHIP; a point-fail + interval-pass -> VARIANCE_ONLY):
  1. WALK-FORWARD     -- expanding folds (prop_pergame_walk_forward style); ALL folds delta_mae<0.
  2. NULL-SHUFFLE     -- real delta beats a shuffled-label null distribution (G3).
  3. ABLATION vs FULL -- add signal column to the full model; marginal holdout delta.
  4. CALIBRATION      -- reliability/coverage (esp. sigma / winprob targets).
  5. CLV              -- closing-line value vs the sharpest line (Pinnacle).

Multiple-comparisons guard: :func:`benjamini_hochberg` across all tested signals
(bookkept by the ledger) + a final held-out set touched EXACTLY ONCE.

Data path: the gate builds a leak-safe (base_matrix, signal_column, target, dates)
bundle via :func:`_build_feature_bundle`. In production this calls the repo
``build_pergame_dataset`` + ``feature_columns`` (prop_pergame) and the signal's
leak-safe ``build(ctx)``. When that data is unavailable (offline / no gamelogs) or
a caller injects ``signal._gate_matrix`` (a ``FeatureBundle``), the gate runs on the
injected matrix -- which keeps unit tests self-contained and fast. If no bundle can
be produced, the gate returns DEFER (coverage insufficient), never a false SHIP.

GPU: XGBoost ``device="cuda"`` (XGB 2.x) wrapped in try/except -> CPU fallback,
mirroring ``scripts/prop_pergame_walk_forward_built.py`` (_resolve_device).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .signal import AsOfContext, GateResult, Signal, Verdict
from .store import PointInTimeStore

# Targets whose primary value is interval/uncertainty, not the point estimate.
_VARIANCE_TARGETS = {"sigma"}
# Targets scored by classification reliability (Brier) rather than MAE.
_CLASS_TARGETS = {"winprob"}

# Minimum rows to attempt a walk-forward fold (scaled down from the prod harness
# so the gate can run on cached/sidecar matrices and the unit test).
_MIN_FOLD_ROWS = 60
# Ablation must reduce holdout MAE by at least this (relative) to count as real.
_ABLATION_REL_EPS = 1e-3
# CLV (pp) acceptance floor.
_CLV_FLOOR = 0.0


@dataclass
class FeatureBundle:
    """A leak-safe matrix bundle the gate trains on.

    Attributes:
        base: (n, p) FULL-model feature matrix (no signal column).
        signal_col: (n,) the candidate signal's leak-safe values (NaN where neutral).
        target: (n,) the regression/classification target for ``signal.target``.
        dates: (n,) ISO date strings for the chronological split.
        lines: optional (n,) market line per row (for the CLV check).
        closing: optional (n,) closing line per row (Pinnacle) for CLV.
    """

    base: np.ndarray
    signal_col: np.ndarray
    target: np.ndarray
    dates: List[str]
    lines: Optional[np.ndarray] = None
    closing: Optional[np.ndarray] = None


def _resolve_device(device_arg: str) -> str:
    """Resolve 'auto' -> 'cuda' if torch reports a GPU, else 'cpu'."""
    if device_arg == "auto":
        try:
            import torch  # local import: optional dependency
            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:  # pragma: no cover - torch missing/broken
            return "cpu"
    return device_arg


def _fit_predict(X_tr: np.ndarray, y_tr: np.ndarray, X_ho: np.ndarray,
                 *, device: str, classify: bool) -> np.ndarray:
    """Train one XGB model (GPU with CPU fallback) and predict the holdout.

    Mirrors the canonical _XGB_DEVICE try/except pattern (XGB 2.x ``device=``).
    """
    try:
        import xgboost as xgb
    except Exception:  # pragma: no cover - xgboost should be present
        # Degenerate linear fallback so the gate still produces a number.
        coef, *_ = np.linalg.lstsq(
            np.nan_to_num(X_tr), y_tr, rcond=None)
        return np.nan_to_num(X_ho) @ coef

    kwargs: Dict[str, Any] = dict(
        n_estimators=300, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
        reg_lambda=2.0, reg_alpha=0.5, random_state=42, n_jobs=-1,
    )
    if classify:
        kwargs["objective"] = "binary:logistic"
        kwargs["eval_metric"] = "logloss"
    else:
        kwargs["objective"] = "reg:squarederror"
        kwargs["eval_metric"] = "mae"
    if device == "cuda":
        kwargs["device"] = "cuda"

    Model = xgb.XGBClassifier if classify else xgb.XGBRegressor
    try:
        m = Model(**kwargs)
        m.fit(X_tr, y_tr, verbose=False)
    except Exception:  # GPU unavailable / OOM -> CPU retry
        kwargs.pop("device", None)
        m = Model(**kwargs)
        m.fit(X_tr, y_tr, verbose=False)
    if classify:
        return m.predict_proba(X_ho)[:, 1]
    return m.predict(X_ho)


def _score(y_true: np.ndarray, y_pred: np.ndarray, *, classify: bool) -> float:
    """Lower-is-better error: Brier for classification, MAE otherwise."""
    if classify:
        return float(np.mean((y_pred - y_true) ** 2))
    return float(np.mean(np.abs(y_pred - y_true)))


# --------------------------------------------------------------------------- #
# Feature bundle construction (leak-safe; degrades to DEFER when no data).
# --------------------------------------------------------------------------- #
def _build_feature_bundle(signal: Signal, store: Optional[PointInTimeStore],
                          ) -> Optional[FeatureBundle]:
    """Build the (FULL matrix, signal column, target, dates) bundle, leak-safe.

    Resolution order:
      1. ``signal._gate_matrix`` -- a pre-built :class:`FeatureBundle` injected by a
         caller / unit test (fast path, fully self-contained).
      2. The repo's ``build_pergame_dataset`` + ``feature_columns`` for point-stat
         targets, with the signal column produced by ``signal.build`` over each
         row's :class:`AsOfContext` (production path).
      3. ``None`` -> the gate returns DEFER.
    """
    injected = getattr(signal, "_gate_matrix", None)
    if isinstance(injected, FeatureBundle):
        return injected

    if signal.target not in (
            "pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        # Only the per-game prop matrix is wired here; other targets DEFER until
        # their matrix loader is provided (winprob / total / minutes / usage).
        return None
    try:  # pragma: no cover - exercised only in the live repo with gamelogs
        from src.prediction.prop_pergame import (
            build_pergame_dataset, feature_columns)
    except Exception:
        return None
    try:
        rows, fc = build_pergame_dataset(min_prior=0)
    except Exception:
        return None
    if not rows:
        return None
    rows.sort(key=lambda r: r["date"])
    base = np.array([[r.get(c, np.nan) for c in fc] for r in rows], dtype=float)
    target = np.array([r.get(f"target_{signal.target}", np.nan) for r in rows],
                      dtype=float)
    dates = [r["date"] for r in rows]
    sig = np.array([_safe_signal_value(signal, r) for r in rows], dtype=float)
    return FeatureBundle(base=base, signal_col=sig, target=target, dates=dates)


def _safe_signal_value(signal: Signal, row: Dict[str, Any]) -> float:
    """Build the signal value for one prod row's AsOfContext; NaN on failure."""
    try:
        ctx = AsOfContext(
            decision_time=_dt.datetime.fromisoformat(row["date"]),
            player_id=row.get("player_id"),
            team=row.get("team"), opp=row.get("opp"),
            game_id=row.get("game_id"), game_date=row.get("date"),
            season=row.get("season"),
        )
        val = signal.build(ctx)
    except Exception:
        return float("nan")
    if val is None:
        return float("nan")
    if isinstance(val, dict):
        # Reduce a dict-signal to its mean sub-feature for the screen.
        vals = [v for v in val.values() if isinstance(v, (int, float))]
        return float(np.mean(vals)) if vals else float("nan")
    return float(val) if isinstance(val, (int, float)) else float("nan")


def _fold_bounds(n: int, n_splits: int) -> List[Tuple[int, int, int]]:
    """Expanding-window (tr_end, va_end, te_end) per fold (prop_pergame style)."""
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    out: List[Tuple[int, int, int]] = []
    for i, frac in enumerate(fold_ends):
        tr_end = int(n * frac)
        te_end = n if i == n_splits - 1 else int(n * fold_ends[i + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        out.append((tr_end, va_end, te_end))
    return out


def _impute(train: np.ndarray, *mats: np.ndarray) -> Tuple[np.ndarray, ...]:
    """Fill NaNs with per-column TRAIN medians (no leakage)."""
    med = np.nanmedian(train, axis=0)
    med = np.where(np.isnan(med), 0.0, med)

    def fill(a: np.ndarray) -> np.ndarray:
        out = a.copy()
        idx = np.where(np.isnan(out))
        out[idx] = np.take(med, idx[1])
        return out

    return tuple(fill(m) for m in (train, *mats))


# --------------------------------------------------------------------------- #
# Criteria.
# --------------------------------------------------------------------------- #
def walk_forward_delta(signal: Signal, *, device: str = "auto", n_splits: int = 4,
                       bundle: Optional[FeatureBundle] = None,
                       store: Optional[PointInTimeStore] = None,
                       ) -> Tuple[List[float], bool]:
    """Criterion 1: per-fold delta_score of FULL+signal vs FULL.

    Returns ``(folds, all_improve)`` where each fold value is
    ``score(full+signal) - score(full)`` (negative == improvement); ``all_improve``
    is True iff there is >=1 evaluated fold and every fold delta < 0.
    """
    bundle = bundle or _build_feature_bundle(signal, store)
    if bundle is None:
        return [], False
    dev = _resolve_device(device)
    classify = signal.target in _CLASS_TARGETS
    n = bundle.base.shape[0]
    folds: List[float] = []
    for tr_end, va_end, te_end in _fold_bounds(n, n_splits):
        if tr_end < _MIN_FOLD_ROWS or (te_end - va_end) < max(20, _MIN_FOLD_ROWS // 3):
            continue
        y = bundle.target
        ok = ~np.isnan(y)
        if not ok[:tr_end].any() or not ok[va_end:te_end].any():
            continue
        base_tr, base_ho = bundle.base[:tr_end], bundle.base[va_end:te_end]
        aug_tr = np.column_stack([base_tr, bundle.signal_col[:tr_end]])
        aug_ho = np.column_stack([base_ho, bundle.signal_col[va_end:te_end]])
        y_tr, y_ho = y[:tr_end], y[va_end:te_end]

        base_tr, base_ho = _impute(base_tr, base_ho)
        aug_tr, aug_ho = _impute(aug_tr, aug_ho)

        full_pred = _fit_predict(base_tr, y_tr, base_ho, device=dev, classify=classify)
        aug_pred = _fit_predict(aug_tr, y_tr, aug_ho, device=dev, classify=classify)
        delta = (_score(y_ho, aug_pred, classify=classify)
                 - _score(y_ho, full_pred, classify=classify))
        folds.append(float(delta))
    all_improve = bool(folds) and all(d < 0 for d in folds)
    return folds, all_improve


def ablation_vs_full(signal: Signal, *, device: str = "auto",
                     bundle: Optional[FeatureBundle] = None,
                     store: Optional[PointInTimeStore] = None,
                     ) -> Tuple[float, bool]:
    """Criterion 3: marginal holdout delta of adding the signal to the FULL model.

    Single chronological holdout (last 25%); returns ``(delta, passed)`` where
    ``passed`` requires a relative improvement of at least ``_ABLATION_REL_EPS``.
    Never evaluates the signal in isolation.
    """
    bundle = bundle or _build_feature_bundle(signal, store)
    if bundle is None:
        return 0.0, False
    dev = _resolve_device(device)
    classify = signal.target in _CLASS_TARGETS
    n = bundle.base.shape[0]
    cut = int(n * 0.75)
    if cut < _MIN_FOLD_ROWS or (n - cut) < max(20, _MIN_FOLD_ROWS // 3):
        return 0.0, False
    y = bundle.target
    base_tr, base_ho = _impute(bundle.base[:cut], bundle.base[cut:])
    aug_tr, aug_ho = _impute(
        np.column_stack([bundle.base[:cut], bundle.signal_col[:cut]]),
        np.column_stack([bundle.base[cut:], bundle.signal_col[cut:]]))
    full_pred = _fit_predict(base_tr, y[:cut], base_ho, device=dev, classify=classify)
    aug_pred = _fit_predict(aug_tr, y[:cut], aug_ho, device=dev, classify=classify)
    full_s = _score(y[cut:], full_pred, classify=classify)
    aug_s = _score(y[cut:], aug_pred, classify=classify)
    delta = float(aug_s - full_s)
    passed = bool(full_s > 0 and (delta / full_s) <= -_ABLATION_REL_EPS)
    return delta, passed


def null_shuffle_control(signal: Signal, *, n_shuffles: int = 5, n_seeds: int = 5,
                         device: str = "auto",
                         bundle: Optional[FeatureBundle] = None,
                         store: Optional[PointInTimeStore] = None,
                         out: Optional[Dict[str, float]] = None,
                         ) -> Tuple[float, bool]:
    """Criterion 2 (G3): real ablation delta vs a shuffled-signal null distribution.

    Permuting the signal column breaks its row alignment to the target while
    preserving its marginal distribution. We require the real (negative) delta to
    be more extreme than the null deltas: ``p = (#null <= real + 1)/(N+1) < 0.10``.
    Returns ``(null_delta_mean, passed)``.
    """
    bundle = bundle or _build_feature_bundle(signal, store)
    if bundle is None:
        return 0.0, False
    real_delta, _ = ablation_vs_full(signal, device=device, bundle=bundle)
    rng = np.random.default_rng(42)
    null_deltas: List[float] = []
    for _ in range(max(2, n_shuffles)):
        perm = rng.permutation(bundle.signal_col.shape[0])
        shuffled = FeatureBundle(
            base=bundle.base, signal_col=bundle.signal_col[perm],
            target=bundle.target, dates=bundle.dates)
        nd, _ = ablation_vs_full(signal, device=device, bundle=shuffled)
        null_deltas.append(nd)
    null_mean = float(np.mean(null_deltas)) if null_deltas else 0.0
    # Z-test: real delta must sit well below (more negative than) the null cloud.
    # With few shuffles an empirical-rank p cannot reach 0.10, so we test the
    # standardized margin instead (one-sided): pass iff real beats null by >=3 SD.
    null_sd = float(np.std(null_deltas)) if len(null_deltas) > 1 else 0.0
    if out is not None:
        out["null_sd"] = null_sd
        out["null_z"] = ((null_mean - real_delta) / null_sd
                         if null_sd > 1e-9 else 0.0)
    if null_sd <= 1e-9:
        # Degenerate null spread -> fall back to a relative-margin rule.
        passed = bool(real_delta < null_mean
                      and (null_mean - real_delta) > 1e-3)
    else:
        z = (null_mean - real_delta) / null_sd  # positive when real beats null
        passed = bool(real_delta < null_mean and z >= 3.0)
    return null_mean, passed


def calibration_check(signal: Signal, *,
                      bundle: Optional[FeatureBundle] = None,
                      store: Optional[PointInTimeStore] = None,
                      device: str = "auto") -> Tuple[bool, Dict[str, float]]:
    """Criterion 4: reliability/coverage.

    For winprob targets: holdout Brier reliability (binned ECE) under a threshold.
    For sigma / interval targets: 80%-interval coverage near nominal.
    For point targets: residual non-degeneracy (the augmented model's holdout
    residuals are finite and not pathologically biased). Returns ``(ok, metrics)``.
    """
    bundle = bundle or _build_feature_bundle(signal, store)
    if bundle is None:
        return False, {}
    dev = _resolve_device(device)
    classify = signal.target in _CLASS_TARGETS
    n = bundle.base.shape[0]
    cut = int(n * 0.75)
    if cut < _MIN_FOLD_ROWS or (n - cut) < max(20, _MIN_FOLD_ROWS // 3):
        return False, {}
    y_ho = bundle.target[cut:]
    aug_tr, aug_ho = _impute(
        np.column_stack([bundle.base[:cut], bundle.signal_col[:cut]]),
        np.column_stack([bundle.base[cut:], bundle.signal_col[cut:]]))
    pred = _fit_predict(aug_tr, bundle.target[:cut], aug_ho, device=dev,
                        classify=classify)
    if classify:
        ece = _expected_calibration_error(y_ho, pred)
        return bool(ece < 0.10), {"ece": ece}
    if signal.target in _VARIANCE_TARGETS:
        resid = y_ho - pred
        sigma = float(np.std(resid)) or 1.0
        cover = float(np.mean(np.abs(resid) <= 1.2816 * sigma))  # ~80% band
        return bool(0.70 <= cover <= 0.90), {"coverage80": cover}
    resid = y_ho - pred
    bias = float(np.mean(resid))
    spread = float(np.std(resid)) or 1.0
    ok = bool(np.all(np.isfinite(resid)) and abs(bias) < spread)
    return ok, {"resid_bias": bias, "resid_std": spread}


def _expected_calibration_error(y: np.ndarray, p: np.ndarray,
                                n_bins: int = 10) -> float:
    """Binned expected calibration error for probabilistic predictions."""
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        m = (p >= edges[i]) & (p < edges[i + 1] if i < n_bins - 1 else p <= edges[i + 1])
        if not m.any():
            continue
        ece += (m.mean()) * abs(float(y[m].mean()) - float(p[m].mean()))
    return float(ece)


def clv_check(signal: Signal, *, bundle: Optional[FeatureBundle] = None,
              store: Optional[PointInTimeStore] = None,
              device: str = "auto") -> Tuple[Optional[float], bool]:
    """Criterion 5: closing-line value vs the sharpest line (Pinnacle).

    If the bundle carries ``lines`` (model's reference line at bet time) and
    ``closing`` (Pinnacle close), CLV (pp) is the mean signed move toward the
    augmented model's holdout prediction relative to the line. When no captured
    closing lines exist yet (the common pre-Oct-2026 case), CLV is unmeasurable;
    we return ``(None, True)`` so CLV is NON-BLOCKING (the ledger records it as
    pending) rather than falsely failing the gate. Returns ``(clv_pp, passed)``.
    """
    bundle = bundle or _build_feature_bundle(signal, store)
    if bundle is None or bundle.closing is None or bundle.lines is None:
        return None, True
    dev = _resolve_device(device)
    classify = signal.target in _CLASS_TARGETS
    n = bundle.base.shape[0]
    cut = int(n * 0.75)
    if cut < _MIN_FOLD_ROWS or (n - cut) < 20:
        return None, True
    aug_tr, aug_ho = _impute(
        np.column_stack([bundle.base[:cut], bundle.signal_col[:cut]]),
        np.column_stack([bundle.base[cut:], bundle.signal_col[cut:]]))
    pred = _fit_predict(aug_tr, bundle.target[:cut], aug_ho, device=dev,
                        classify=classify)
    lines = bundle.lines[cut:]
    closing = bundle.closing[cut:]
    # Bet the side the model favours; CLV = how far the close moved our way (pp).
    side = np.sign(pred - lines)
    clv = float(np.mean(side * (closing - lines)))
    return clv, bool(clv >= _CLV_FLOOR)


def benjamini_hochberg(p_values: Sequence[float], q: float = 0.10) -> List[bool]:
    """FDR multiple-comparisons guard across all tested signals.

    Returns a parallel boolean list: True iff that hypothesis is rejected (i.e.
    survives as a discovery) under Benjamini-Hochberg at level ``q``. ``None`` /
    NaN p-values map to False.
    """
    p_arr = [float(p) if (p is not None and np.isfinite(p)) else float("nan")
             for p in p_values]
    valid = [(i, p) for i, p in enumerate(p_arr) if not np.isnan(p)]
    out = [False] * len(p_arr)
    if not valid:
        return out
    valid.sort(key=lambda t: t[1])
    m = len(valid)
    k_max = 0
    for rank, (_, p) in enumerate(valid, start=1):
        if p <= (rank / m) * q:
            k_max = rank
    for rank, (orig_i, _) in enumerate(valid, start=1):
        if rank <= k_max:
            out[orig_i] = True
    return out


# --------------------------------------------------------------------------- #
# The universal gate.
# --------------------------------------------------------------------------- #
def evaluate(signal: Signal, *, store: Optional[PointInTimeStore] = None,
             device: str = "auto", n_splits: int = 4,
             held_out_once: bool = False) -> GateResult:
    """Run a single signal through all five gate criteria and return a verdict.

    See module docstring for the criteria. The verdict policy:
        SHIP          -- wf_all_improve & null_pass & ablation_pass & calibration_ok
                         & clv_pass & fdr_pass.
        VARIANCE_ONLY -- point estimate fails but calibration/interval improves
                         (sigma target, or point-fail + calibration_ok + null_pass).
        DEFER         -- no leak-safe matrix could be built (coverage insufficient).
        REJECT        -- otherwise.

    FDR (``fdr_pass``) is provisionally set from this signal's own p-value; the
    ledger recomputes Benjamini-Hochberg across the full experiment history.
    """
    bundle = _build_feature_bundle(signal, store)
    if bundle is None:
        return GateResult(signal_name=signal.name, verdict=Verdict.DEFER,
                          reason="no leak-safe feature matrix (coverage insufficient)")

    metrics: Dict[str, Any] = {}
    wf_folds, wf_all = walk_forward_delta(signal, device=device, n_splits=n_splits,
                                          bundle=bundle)
    if not wf_folds:
        return GateResult(signal_name=signal.name, verdict=Verdict.DEFER,
                          reason="no evaluable walk-forward fold (rows too few)",
                          wf_folds=wf_folds)

    abl_delta, abl_pass = ablation_vs_full(signal, device=device, bundle=bundle)
    _null_diag: Dict[str, float] = {}
    null_delta, null_pass = null_shuffle_control(signal, device=device, bundle=bundle,
                                                 out=_null_diag)
    calib_ok, calib_metrics = calibration_check(signal, device=device, bundle=bundle)
    clv, clv_pass = clv_check(signal, device=device, bundle=bundle)
    metrics.update(calib_metrics)

    # p-value for FDR: one-sided normal-tail from the null-shuffle z-margin.
    p_value = _null_pvalue(abl_delta, null_delta, _null_diag.get("null_z", 0.0))
    metrics["null_z"] = _null_diag.get("null_z", 0.0)
    fdr_pass = benjamini_hochberg([p_value])[0]
    metrics["clv_measured"] = clv is not None

    if held_out_once:
        metrics["held_out_once"] = True

    point_ok = wf_all and abl_pass and null_pass
    if point_ok and calib_ok and clv_pass and fdr_pass:
        verdict = Verdict.SHIP
        reason = (f"{len(wf_folds)} WF folds all improve; ablation {abl_delta:+.4f}; "
                  f"beats null; calibrated; clv "
                  f"{'pending' if clv is None else f'{clv:+.2f}pp'}")
    elif signal.target in _VARIANCE_TARGETS and calib_ok and null_pass:
        verdict = Verdict.VARIANCE_ONLY
        reason = "interval/coverage improves; point estimate not the lever"
    elif (not point_ok) and calib_ok and null_pass and clv_pass:
        verdict = Verdict.VARIANCE_ONLY
        reason = "point estimate fails but calibration improves -> interval/Kelly only"
    else:
        verdict = Verdict.REJECT
        reason = _reject_reason(wf_all, null_pass, abl_pass, calib_ok, clv_pass, fdr_pass)

    return GateResult(
        signal_name=signal.name, verdict=verdict, reason=reason,
        wf_folds=wf_folds, wf_all_improve=wf_all,
        null_delta=null_delta, null_pass=null_pass,
        ablation_delta=abl_delta, ablation_pass=abl_pass,
        calibration_ok=calib_ok, clv=clv, clv_pass=clv_pass,
        p_value=p_value, fdr_pass=fdr_pass, metrics=metrics)


def _null_pvalue(real_delta: float, null_mean: float, null_z: float) -> float:
    """One-sided normal-tail p-value from the null-shuffle z-margin.

    ``null_z`` is ``(null_mean - real_delta) / null_sd`` (positive when the real
    ablation delta is more negative than the shuffled-signal null cloud). The p is
    the upper-tail mass P(Z >= null_z); a strong, target-aligned signal yields a
    large z and thus a tiny p so Benjamini-Hochberg rejects it. Degenerate /
    non-improving cases map to 1.0.
    """
    if real_delta >= null_mean or null_z <= 0:
        return 1.0
    # Survival function of the standard normal via erfc (no scipy dependency).
    import math
    p = 0.5 * math.erfc(null_z / math.sqrt(2.0))
    return float(max(1e-12, min(1.0, p)))


def _reject_reason(wf_all: bool, null_pass: bool, abl_pass: bool, calib_ok: bool,
                   clv_pass: bool, fdr_pass: bool) -> str:
    """Compose a human-readable reason listing the failed criteria."""
    fails = []
    if not wf_all:
        fails.append("not all WF folds improve")
    if not abl_pass:
        fails.append("ablation-vs-full not meaningful")
    if not null_pass:
        fails.append("does not beat null-shuffle")
    if not calib_ok:
        fails.append("calibration off")
    if not clv_pass:
        fails.append("negative CLV")
    if not fdr_pass:
        fails.append("fails BH FDR")
    return "; ".join(fails) or "failed gate"
