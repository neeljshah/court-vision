"""S309 design arms -- one frozen calibrator scored through both shared eval-gate routes.

The forward-only arm calls ``scripts.platformkit.eval_gate.walkforward.walk_forward``.
The robustness arm calls ``scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate`` with
a symmetric one-day calendar embargo. Neither shared module is read-modified here; both
are imported and used through their public API, so their purge, embargo, vintage and
redaction contracts (including the S301 state-key guard) hold for this row.

GRAIN -- the one deliberate simplification, stated because it is load bearing: both
shared routes build every test row's train set with a per-state Python loop, which is
O(n^2) in the number of states. 465,249 tick states is not runnable through them, so the
evaluators are driven at GAME-CLUSTER grain: one evaluator state per game (1,593). Each
evaluator call emits one out-of-fold probability for EVERY tick of its test game, so the
scored series is still exactly one OOF prediction per tick per design, and the caller's
``state_key`` uniqueness assertion still holds. ``record_agreement_max_abs_error`` proves
the tick series and the evaluators' own returned records are the same numbers.

LEAK POSTURE. The test view is strict-redacted by the shared route (``strict_redaction=
True``), so an undeclared key on a test row is a LeakError rather than a silent pass. Both arms also
run with S301's ``guard_state_keys=True``, so a duplicate (game_id, state_ts) evaluator
key raises in the shared route rather than being silently scored twice. The
predictor reaches the corpus only through ``_Corpus.prob`` (market probability, carrying no
labels) for the TEST game, and through ``_Corpus.label`` for TRAIN games. The forward arm
additionally drops any train game not SETTLED strictly before the test state's timestamp:
walk_forward orders states by game start, and a game that started earlier may still be
unsettled, so this is strictly tighter than the shared route's own strict-past rule. The
CPCV arm deliberately does NOT apply that filter -- straddling the test block is the design
being measured, and the symmetric purge/embargo is what makes it honest.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from math import comb
from typing import Callable, List

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.walkforward import EMBARGO_DAYS, PURGE_HOURS, walk_forward

N_GROUPS, N_TEST_GROUPS, SYMMETRIC_EMBARGO_DAYS = 8, 2, 1
LOW, HIGH = 0.10, 0.90
TICK_COLUMNS = ("game_id", "game_date", "state_ts", "state_key", "home", "away",
                "market_prob", "outcome_home_win")


def _thresholds(model) -> tuple[list, list]:
    """The fitted isotonic interpolation points (X, y): a fold's candidate refits from these."""
    if model is None:
        return [], []
    return [float(v) for v in model.X_thresholds_], [float(v) for v in model.y_thresholds_]


def _logit(prob: np.ndarray) -> np.ndarray:
    clipped = np.clip(prob, 1e-6, 1 - 1e-6)
    return np.log(clipped / (1 - clipped))


def fit_calibrator(prob: np.ndarray, y: np.ndarray) -> tuple[tuple, dict]:
    """The frozen S272 pair: logistic incumbent, plus low/high-tail isotonic candidate."""
    if len(prob) == 0 or len(np.unique(y)) < 2:
        return (None, None, None), {"fallback_market": True}
    base = LogisticRegression(C=1e6, max_iter=500, solver="lbfgs").fit(_logit(prob).reshape(-1, 1), y)
    tails = []
    for mask in (prob <= LOW, prob >= HIGH):
        tails.append(IsotonicRegression(out_of_bounds="clip").fit(prob[mask], y[mask])
                     if mask.any() else None)
    return (base, tails[0], tails[1]), {
        "fallback_market": False, "coef": float(base.coef_[0, 0]),
        "intercept": float(base.intercept_[0]), "low_points": int((prob <= LOW).sum()),
        "high_points": int((prob >= HIGH).sum()), "train_ticks": int(len(prob))}


def predict_calibrator(models: tuple, prob: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (incumbent, candidate) probabilities for one game's ticks."""
    base_model, low, high = models
    if base_model is None:
        return prob.copy(), prob.copy()
    base = base_model.predict_proba(_logit(prob).reshape(-1, 1))[:, 1]
    candidate = base.copy()
    for model, mask in ((low, prob <= LOW), (high, prob >= HIGH)):
        if model is not None and mask.any():        # a fold can hold no tail ticks
            candidate[mask] = model.predict(prob[mask])
    return base, candidate


class _Corpus:
    """Per-game tick arrays. `prob` carries NO labels; `label` is the train-side channel."""

    def __init__(self, ticks: pd.DataFrame) -> None:
        self.pos: dict[str, np.ndarray] = {}
        self.prob: dict[str, np.ndarray] = {}
        self.label: dict[str, np.ndarray] = {}
        self.start: dict[str, str] = {}
        self.settle: dict[str, str] = {}
        for gid, part in ticks.groupby("game_id", sort=False):
            self.pos[gid] = part.index.to_numpy()
            self.prob[gid] = part["market_prob"].to_numpy(float)
            self.label[gid] = part["outcome_home_win"].to_numpy(float)
            self.start[gid] = str(part["state_ts"].min())
            self.settle[gid] = str(part["state_ts"].max())


def _states(corpus: _Corpus, meta: pd.DataFrame) -> List[dict]:
    """One walk_forward-shaped state per game, anchored at the game's first tick.

    The declared feature is the count of games already SETTLED at that anchor -- a
    strictly-past quantity, so it satisfies assert_vintage honestly. Every key here is
    either in walkforward.TEST_VIEW_KEYS or in its settled deny-list, which is what lets
    the caller ask for strict redaction with no allow_keys escape hatch.
    """
    settles = sorted(corpus.settle.values())
    states = []
    for gid, row in meta.iterrows():
        start = corpus.start[gid]
        avail = str(pd.Timestamp(start) - pd.Timedelta(seconds=1))
        states.append({
            "game_id": gid, "state_ts": start, "home": str(row.home), "away": str(row.away),
            "game_date": str(row.game_date), "outcome": int(row.outcome),
            "features": {"prior_settled_games": bisect_left(settles, start)},
            "feature_avail": {"prior_settled_games": avail}})
    return states


class _Predictor:
    """Shared-evaluator predict_fn. One fit per DISTINCT train set, single-entry cached.

    The cache key is the exact tuple of train game ids, so a reuse can never be a different
    train set (a length/date key could collide). It holds one entry only: CPCV reuses one
    train set for every test row of a path, while walk_forward's train set genuinely changes
    every step, and keeping 1,593 fitted isotonic models alive would cost gigabytes.
    """

    def __init__(self, corpus: _Corpus, arm: str, settled_only: bool) -> None:
        self.corpus, self.arm, self.settled_only = corpus, arm, settled_only
        self.key: tuple | None = None
        self.models: tuple = (None, None, None)
        self.params: dict = {"fallback_market": True}
        self.out: dict[str, list] = defaultdict(list)
        self.folds: List[dict] = []
        self.fits = 0

    def __call__(self, train: List[dict], test_view: dict, select_inside: bool) -> float:
        gid, ts = test_view["game_id"], test_view["state_ts"]
        ids = [s["game_id"] for s in train]
        if self.settled_only:
            ids = [g for g in ids if self.corpus.settle[g] < ts]
        key = tuple(ids)
        if key != self.key:
            if ids:
                prob = np.concatenate([self.corpus.prob[g] for g in ids])
                labels = np.concatenate([self.corpus.label[g] for g in ids])
            else:
                prob = labels = np.zeros(0)
            self.models, self.params = fit_calibrator(prob, labels)
            self.key, self.fits = key, self.fits + 1
            self.folds.append(self._fold(ids, len(train), gid, ts))
        self.folds[-1]["test_game_ids"].append(gid)
        base, candidate = predict_calibrator(self.models, self.corpus.prob[gid])
        self.out[gid].append((base, candidate))
        return float(candidate.mean())

    def _fold(self, ids: List[str], n_train: int, gid: str, ts: str) -> dict:
        """One archived fit: new fields, the attempt-1 aliases, membership and the tails."""
        settle = max((self.corpus.settle[g] for g in ids), default="")
        date = str(ts)[:10]
        low_x, low_y = _thresholds(self.models[1])
        high_x, high_y = _thresholds(self.models[2])
        return {
            "arm": self.arm, "fit_index": self.fits, "n_train_games": len(ids),
            "n_train_states_from_evaluator": n_train, "max_train_settle": settle,
            "first_test_game": gid, "first_test_state_ts": ts,
            "purge": "shared %s purge: %dh same team, %dd same matchup" % (
                self.arm, PURGE_HOURS, EMBARGO_DAYS),
            "embargo_days": SYMMETRIC_EMBARGO_DAYS if not self.settled_only else 0,
            "symmetric_embargo": not self.settled_only,
            "train_rule": ("settled strictly before the test state timestamp"
                           if self.settled_only else "symmetric CPCV path, both sides"),
            # attempt-1 fold field names, RETAINED as aliases beside the new ones
            "fold_date": date, "min_test_date": date, "max_train_date": settle[:10],
            "train_games": len(ids), "forward_only": self.settled_only,
            "cpcv_group": "2024-25" if date < "2025-07-01" else "2025-26",
            # exact membership + the fitted candidate tails: every fold refits from this
            "train_game_ids": list(ids), "test_game_ids": [],
            "isotonic_low_x": low_x, "isotonic_low_y": low_y,
            "isotonic_high_x": high_x, "isotonic_high_y": high_y,
            **self.params}


def _finalize(folds: List[dict], corpus: _Corpus) -> List[dict]:
    """Fill each fold's test membership and counts once every test row has been scored."""
    for fold in folds:
        test = list(dict.fromkeys(fold["test_game_ids"]))
        fold["test_game_ids"] = test
        fold["test_games"] = len(test)
        fold["test_ticks"] = int(sum(len(corpus.prob[g]) for g in test))
    return folds


def _collect(frame: pd.DataFrame, corpus: _Corpus, predictor: _Predictor, records: List[dict],
             prefix: str, expected_paths: int) -> float:
    """Average a game's per-path OOF predictions onto its ticks; return record agreement."""
    baseline = np.full(len(frame), np.nan)
    candidate = np.full(len(frame), np.nan)
    for gid, runs in predictor.out.items():
        assert len(runs) == expected_paths, "%s: game %s scored on %d paths" % (prefix, gid, len(runs))
        pos = corpus.pos[gid]
        baseline[pos] = np.mean([run[0] for run in runs], axis=0)
        candidate[pos] = np.mean([run[1] for run in runs], axis=0)
    assert not np.isnan(candidate).any() and not np.isnan(baseline).any(), "unscored ticks"
    frame["p_%s_baseline" % prefix] = baseline
    frame["p_%s_candidate" % prefix] = candidate
    per_game = pd.Series(candidate, index=frame["game_id"].to_numpy()).groupby(level=0).mean()
    reported = pd.DataFrame(records).groupby("game_id")["p_model"].mean()
    return float(np.max(np.abs(per_game.reindex(reported.index).to_numpy() - reported.to_numpy())))


def evaluate_designs(ticks: pd.DataFrame) -> tuple[pd.DataFrame, List[dict], dict]:
    """Score one frozen calibrator through walk_forward AND cpcv_evaluate on the same ticks.

    ``ticks`` carries TICK_COLUMNS. Returns (ticks + p_/loss_ columns for both arms, the
    fold/parameter archive, the provenance dict). Forward-only is the deployment headline;
    CPCV is the labelled robustness companion. No promotion, no dollar quantity.
    """
    missing = [c for c in TICK_COLUMNS if c not in ticks.columns]
    assert not missing, "evaluate_designs missing columns %s" % missing
    frame = ticks.reset_index(drop=True).copy()
    frame["game_id"] = frame["game_id"].astype(str)
    corpus = _Corpus(frame)
    meta = frame.groupby("game_id", sort=False).agg(
        home=("home", "first"), away=("away", "first"), game_date=("game_date", "first"),
        outcome=("outcome_home_win", "first"))
    states = _states(corpus, meta)

    forward = _Predictor(corpus, "forward", True)
    forward_result = walk_forward(states, forward, True, strict_redaction=True,
                                  guard_state_keys=True)
    design = _Predictor(corpus, "cpcv", False)
    cpcv_records = cpcv_evaluate(states, design, n_groups=N_GROUPS, n_test_groups=N_TEST_GROUPS,
                                 embargo_days=SYMMETRIC_EMBARGO_DAYS, strict_redaction=True,
                                 guard_state_keys=True)

    paths_per_game = comb(N_GROUPS - 1, N_TEST_GROUPS - 1)
    agreement = max(
        _collect(frame, corpus, forward, forward_result.records, "forward", 1),
        _collect(frame, corpus, design, cpcv_records, "cpcv", paths_per_game))
    assert agreement <= 1e-9, "arm records disagree with the tick series by %g" % agreement

    y = frame["outcome_home_win"].to_numpy(float)
    for prefix in ("forward", "cpcv"):
        for side in ("baseline", "candidate"):
            frame["loss_%s_%s" % (prefix, side)] = (frame["p_%s_%s" % (prefix, side)] - y) ** 2
    frame["evaluator_records"] = 1

    splits = pd.DataFrame(cpcv_records).groupby("split_id").agg(
        test_games=("game_id", "nunique"), n_train_states=("n_train", "max"))
    provenance = {
        "grain": "game_cluster: one evaluator state per game, one OOF probability per tick",
        "n_states": len(states), "n_ticks": int(len(frame)),
        "record_agreement_max_abs_error": agreement,
        "forward": {"evaluator": "scripts.platformkit.eval_gate.walkforward.walk_forward",
                    "records": len(forward_result.records), "fits": forward.fits,
                    "select_inside": bool(forward_result.select_inside),
                    "strict_redaction": True, "guard_state_keys": True, "purge_hours": PURGE_HOURS,
                    "matchup_embargo_days": EMBARGO_DAYS, "symmetric_embargo": False,
                    "train_rule": "settled strictly before the test state timestamp",
                    "min_train_states": int(min(forward_result.n_train_sizes)),
                    "max_train_states": int(max(forward_result.n_train_sizes))},
        "cpcv": {"evaluator": "scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate",
                 "records": len(cpcv_records), "fits": design.fits, "n_groups": N_GROUPS,
                 "n_test_groups": N_TEST_GROUPS, "paths": int(len(splits)),
                 "paths_per_game": paths_per_game, "strict_redaction": True, "guard_state_keys": True,
                 "symmetric_embargo_days": SYMMETRIC_EMBARGO_DAYS, "symmetric_embargo": True,
                 "purge_hours": PURGE_HOURS, "matchup_embargo_days": EMBARGO_DAYS,
                 "split_test_games": splits["test_games"].astype(int).tolist(),
                 "split_train_states": splits["n_train_states"].astype(int).tolist()}}
    return frame, _finalize(forward.folds + design.folds, corpus), provenance
