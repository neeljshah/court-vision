"""CSCV probability of backtest overfitting (Bailey/Borwein/Lopez de Prado/Zhu 2014).

Re-slices an ALREADY-COMPUTED out-of-fold prediction matrix combinatorially --
no model refitting inside the core routine. Contrast with
scripts.platformkit.cpcv.probability_of_backtest_overfitting, which is CPCV-
over-date-groups with per-path model *refitting* via ``_fit_score``. Different
mechanism, distinctly named (``cscv_pbo``) so the two never collide if both
get imported together.

Diagnostic only: reports a PBO number, never a SHIP/REJECT verdict and never a
dollar-edge claim (see .claude/rules/no-edge-claims.md).
"""
from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.eval_gate import combo_search
from scripts.platformkit.eval_gate.walkforward import walk_forward

DEFAULT_S_BLOCKS = 16
DEFAULT_MAX_SPLITS = 1000
DEFAULT_SEED = 2718          # matches combo_search.py's LogisticRegression random_state convention


@dataclass(frozen=True)
class CSCVResult:
    pbo: float
    n_splits: int
    n_configs: int
    n_obs: int
    s_blocks: int
    logit_lambdas: list[float]
    omegas: list[float]
    is_best_idx: list[int]        # config column index chosen IS-best, per split
    detail: dict


def _check_s_blocks(s_blocks: int) -> None:
    """Shared guard: an odd s_blocks would make the OOS complement a different
    size than the IS half, which breaks the CSCV null (rank no longer uniform)."""
    if s_blocks < 2 or s_blocks % 2:
        raise ValueError("s_blocks must be an even integer >= 2")


def contiguous_blocks(n_obs: int, s_blocks: int = DEFAULT_S_BLOCKS) -> list[np.ndarray]:
    """Row indices [0, n_obs) split into s_blocks contiguous, time-ordered blocks.

    Same block-building convention as cpcv.cpcv_splits (cpcv.py:51), but over a
    positional row index rather than distinct calendar dates. Blocks are NEVER
    shuffled: each is an ascending run of ADJACENT rows, so no split interleaves
    rows across a time boundary.
    """
    _check_s_blocks(s_blocks)
    if n_obs < s_blocks:
        raise ValueError("n_obs must be >= s_blocks")
    return np.array_split(np.arange(n_obs), s_blocks)


def enumerate_split_indices(s_blocks: int = DEFAULT_S_BLOCKS, max_splits: int = DEFAULT_MAX_SPLITS,
                           seed: int = DEFAULT_SEED) -> list[tuple[int, ...]]:
    """All C(s_blocks, s_blocks//2) IS-half block combinations (complement = OOS half).

    Deterministic enumeration order via itertools.combinations. When the full
    count exceeds max_splits, deterministically subsample exactly max_splits
    combos with a seeded RNG, then sort the sampled positions so output order
    is reproducible for a fixed seed.
    """
    _check_s_blocks(s_blocks)
    if max_splits < 1:
        raise ValueError("max_splits must be at least 1")  # size=0 -> mean of [] -> silent nan PBO
    # ponytail: enumerates all C(s,s/2) BEFORE subsampling. s_blocks=16 -> 12870
    # tuples (cheap); the cost doubles every +2 blocks (s=24 -> 2.7M tuples, ~1GB).
    # Upgrade path if anyone needs s_blocks > 20: rejection-sample combos directly.
    all_combos = list(itertools.combinations(range(s_blocks), s_blocks // 2))
    if len(all_combos) <= max_splits:
        return all_combos
    positions = np.sort(np.random.default_rng(seed).choice(len(all_combos), size=max_splits, replace=False))
    return [all_combos[i] for i in positions]


def cscv_pbo(pred_matrix: np.ndarray, outcome: Sequence[int] | np.ndarray, *,
            s_blocks: int = DEFAULT_S_BLOCKS, max_splits: int = DEFAULT_MAX_SPLITS,
            seed: int = DEFAULT_SEED) -> CSCVResult:
    """CSCV PBO over a precomputed OOF prediction matrix.

    pred_matrix: (n_obs, n_configs) OOF predicted probabilities; ROW ORDER = the
                 chronological order predictions were produced in (this function
                 does not sort -- caller/adapter guarantees time order).
    outcome:     (n_obs,) binary outcomes aligned to pred_matrix's rows.

    Raises ValueError if n_configs < 2, pred_matrix.shape[0] != len(outcome),
    or n_obs < s_blocks.
    """
    pred_matrix = np.asarray(pred_matrix, dtype=float)
    outcome_arr = np.asarray(outcome, dtype=float)
    if pred_matrix.ndim != 2:
        raise ValueError("pred_matrix must be 2-D (n_obs, n_configs)")
    n_obs, n_configs = pred_matrix.shape
    if n_configs < 2:
        raise ValueError("cscv_pbo needs at least 2 candidate configs")
    if n_obs != len(outcome_arr):
        raise ValueError("pred_matrix.shape[0] must match len(outcome)")
    blocks = contiguous_blocks(n_obs, s_blocks)  # also enforces n_obs >= s_blocks
    # Fail loud, never quietly: np.argmin SELECTS a NaN column as IS-best, its OOS
    # rank is NaN, and `nan <= 0` is False -- so a single NaN silently drags PBO
    # toward 0 (the reassuring direction) with no warning. Same for a caller who
    # passes logits or a non-binary outcome: the Brier, and the PBO, are garbage.
    if not (np.isfinite(pred_matrix).all() and np.isfinite(outcome_arr).all()):
        raise ValueError("pred_matrix/outcome contain NaN or inf")
    if pred_matrix.min() < 0.0 or pred_matrix.max() > 1.0:
        raise ValueError("pred_matrix must hold probabilities in [0, 1]")
    if not np.isin(outcome_arr, (0.0, 1.0)).all():
        raise ValueError("outcome must be binary 0/1")
    splits = enumerate_split_indices(s_blocks, max_splits, seed)
    logit_lambdas: list[float] = []
    omegas: list[float] = []
    is_best_idx: list[int] = []
    for combo in splits:
        is_rows = np.concatenate([blocks[b] for b in combo])
        oos_rows = np.concatenate([blocks[b] for b in range(s_blocks) if b not in combo])
        is_brier = ((pred_matrix[is_rows] - outcome_arr[is_rows, None]) ** 2).mean(axis=0)
        oos_brier = ((pred_matrix[oos_rows] - outcome_arr[oos_rows, None]) ** 2).mean(axis=0)
        best = int(np.argmin(is_brier))
        # ascending Brier -> better OOS performance -> higher rank (ties averaged).
        # rank is in [1, n_configs], so the (n_configs + 1) denominator keeps omega
        # strictly inside (0, 1) -- the logit below can never be +/-inf. All-tied
        # configs land on the median rank -> omega 0.5 -> lam 0.0, counted as
        # overfit by the `<= 0` convention (conservative on the degenerate tie).
        rank = pd.Series(-oos_brier).rank(method="average")
        omega = float(rank.iloc[best]) / (n_configs + 1)
        lam = float(np.log(omega / (1.0 - omega)))
        logit_lambdas.append(lam)
        omegas.append(omega)
        is_best_idx.append(best)
    pbo = float(np.mean(np.asarray(logit_lambdas) <= 0.0))
    return CSCVResult(pbo=pbo, n_splits=len(splits), n_configs=n_configs, n_obs=n_obs, s_blocks=s_blocks,
                      logit_lambdas=logit_lambdas, omegas=omegas, is_best_idx=is_best_idx,
                      detail={"seed": seed, "max_splits": max_splits})


# ponytail: _logit/_fit_predict duplicate combo_search.py:35-37,70-74 (both private
# there, so this adapter cannot import them) and build_pred_matrix's per-lambda loop
# duplicates the state-dict + predict-closure shape at combo_search.py:100-114 --
# deliberate ~20-line duplication, not a call into combo_search internals. Ceiling: if
# combo_search's feature/state schema changes, mirror the change here too. Upgrade
# path: hoist both into a shared public helper in combo_search.py (human-gated edit)
# once a second caller needs it.
def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p.astype(float), 1e-6, 1 - 1e-6)
    return np.log(p / (1.0 - p))


def _fit_predict(x: np.ndarray, y: np.ndarray, test: np.ndarray, lam: float) -> np.ndarray:
    model = LogisticRegression(penalty="elasticnet", solver="saga", l1_ratio=0.8,
                               C=1.0 / lam, max_iter=4000, random_state=DEFAULT_SEED)
    model.fit(x, y)
    return model.predict_proba(test)[:, 1]


def build_pred_matrix(frame: pd.DataFrame, features: Sequence[str], *,
                      lambdas: Sequence[float] = combo_search.LAMBDAS,
                      min_train: int = combo_search.MIN_TRAIN,
                      s_blocks: int = DEFAULT_S_BLOCKS
                      ) -> tuple[np.ndarray, np.ndarray, list[float]]:
    """Adapter: build the (n_obs, n_configs) OOF matrix cscv_pbo needs from a
    combo_search-style catalog frame (combo_search.load_nba_catalog's output).

    Reuses only combo_search's public surface: load_nba_catalog, LAMBDAS,
    MIN_TRAIN. Never imports a combo_search name starting with "_".

    Train/test membership depends only on `states` (dates/teams), not on
    lambda, so every lambda's wf.n_train_sizes is identical -- the valid-row
    mask is computed once: valid = train_sizes >= min_train.

    Returns (pred_matrix, outcome, used_lambdas), all restricted to the shared
    valid mask so every column aligns to the same observation subset.

    Raises ValueError if valid.sum() < s_blocks (not enough OOF rows to form
    blocks).
    """
    # Materialize: `lambdas` is iterated twice below, so a generator would leave
    # the second pass empty. Duplicates would become byte-identical config columns.
    lambdas = [float(lam) for lam in lambdas]
    if len(lambdas) < 2 or len(set(lambdas)) != len(lambdas):
        raise ValueError("lambdas must be >= 2 distinct values")
    need = {"date", "game_id", "outcome", "close_prob", *features}
    if not need.issubset(frame):
        raise ValueError("catalog frame lacks declared columns")
    df = frame.sort_values("date").dropna(subset=list(need)).reset_index(drop=True)
    x_raw = df.loc[:, features].to_numpy(float)
    y, close = df.outcome.to_numpy(int), df.close_prob.to_numpy(float)
    states = [{"game_id": str(r.game_id), "home": str(getattr(r, "home", "h" + str(i))),
               "away": str(getattr(r, "away", "a" + str(i))), "state_ts": r.date.isoformat(),
               "features": {name: float(x_raw[i, j]) for j, name in enumerate(features)},
               "feature_avail": {name: (r.date - timedelta(seconds=1)).isoformat() for name in features},
               "outcome": int(r.outcome), "devig_close_prob": float(r.close_prob), "index": i}
              for i, r in enumerate(df.itertuples(index=False))]
    preds: dict[float, np.ndarray] = {}
    train_sizes = None
    for lam in lambdas:
        def predict(train, test, _inside, lam=float(lam)):
            idx = np.array([s["index"] for s in train], dtype=int)
            if len(idx) < min_train:
                return float(close[test["index"]])
            mu, sd = x_raw[idx].mean(0), x_raw[idx].std(0) + 1e-9
            return float(_fit_predict(np.column_stack([_logit(close[idx]), (x_raw[idx] - mu) / sd]), y[idx],
                                      np.column_stack([_logit(close[[test["index"]]]),
                                                       (x_raw[[test["index"]]] - mu) / sd]), lam)[0])
        wf = walk_forward(states, predict, select_inside=True)
        preds[float(lam)] = np.array([r["p_model"] for r in wf.records])
        train_sizes = wf.n_train_sizes
    valid = np.asarray(train_sizes, dtype=int) >= min_train
    if int(valid.sum()) < s_blocks:
        raise ValueError("not enough OOF rows ({0}) to form {1} blocks".format(int(valid.sum()), s_blocks))
    pred_matrix = np.column_stack([preds[lam][valid] for lam in lambdas])
    return pred_matrix, y[valid], lambdas


def main(argv: Sequence[str] | None = None) -> int:
    """--data-root/--s-blocks/--max-splits/--seed; prints the CSCVResult as json.

    Diagnostic number only -- no SHIP/REJECT wrapping here.
    """
    ap = argparse.ArgumentParser(description="CSCV probability of backtest overfitting (diagnostic)")
    ap.add_argument("--data-root", type=Path, default=Path("data/domains/basketball_nba"))
    ap.add_argument("--s-blocks", type=int, default=DEFAULT_S_BLOCKS)
    ap.add_argument("--max-splits", type=int, default=DEFAULT_MAX_SPLITS)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args(argv)
    frame, features = combo_search.load_nba_catalog(args.data_root)
    pred_matrix, outcome, used = build_pred_matrix(frame, features, s_blocks=args.s_blocks)
    result = cscv_pbo(pred_matrix, outcome, s_blocks=args.s_blocks, max_splits=args.max_splits, seed=args.seed)
    print(json.dumps({"pbo": result.pbo, "n_splits": result.n_splits, "n_configs": result.n_configs,
                      "n_obs": result.n_obs, "s_blocks": result.s_blocks, "lambdas": used,
                      "detail": result.detail}, sort_keys=True))  # per-split arrays stay on the object
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
