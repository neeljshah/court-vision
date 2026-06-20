"""scripts/platformkit/calib_stability.py -- Multi-seed + 2nd-corpus calibrator stability.

Promotes the served pregame recalibrator ONLY when its method choice is stable
across N random seeds AND replicates on an independent 2nd corpus.

Acceptance (pa8 BACKLOG):
  - one-seed-only win -> UNSTABLE verdict
  - method stable across all seeds + both corpora -> STABLE
  - deterministic given fixed seed list; no dollar / roi / pnl field anywhere

CALIBRATION != EDGE.  Stable calibration does NOT imply market edge.
CLI: python scripts/platformkit/calib_stability.py
"""
from __future__ import annotations

import sys
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.calibrator_zoo import select_calibrator, CALIBRATION_NOTE

__all__ = ["run_stability", "StabilityResult", "CALIBRATION_NOTE"]


class StabilityResult:
    """Verdict of a multi-seed + 2-corpus stability run.

    verdict      : "STABLE" | "UNSTABLE"
    stable_method: method name when STABLE; None when UNSTABLE
    seed_votes   : {method: count} across all seeds x corpora
    per_seed     : list of {seed, corpus_id, chosen_method, ...} rows
    is_promoted(): True only when STABLE
    """

    def __init__(self, verdict: str, stable_method: Optional[str],
                 seed_votes: Dict[str, int], per_seed: List[Dict],
                 n_seeds: int, n_corpora: int, message: str) -> None:
        self.verdict = verdict
        self.stable_method = stable_method
        self.seed_votes = seed_votes
        self.per_seed = per_seed
        self.n_seeds = n_seeds
        self.n_corpora = n_corpora
        self.message = message
        self.note = CALIBRATION_NOTE

    def as_dict(self) -> Dict:
        return {"verdict": self.verdict, "stable_method": self.stable_method,
                "seed_votes": self.seed_votes, "per_seed": self.per_seed,
                "n_seeds": self.n_seeds, "n_corpora": self.n_corpora,
                "message": self.message, "note": self.note}

    def is_promoted(self) -> bool:
        return self.verdict == "STABLE"


def _bootstrap_draw(p: np.ndarray, y: np.ndarray,
                    rng: np.random.Generator, frac: float = 0.8,
                    ) -> Tuple[np.ndarray, np.ndarray]:
    """Sorted subsample preserving temporal order (no look-ahead)."""
    n = len(p)
    k = max(1, int(n * frac))
    idx = np.sort(rng.choice(n, size=k, replace=False))
    return p[idx], y[idx]


def _split_corpus(p: np.ndarray, y: np.ndarray,
                  ) -> Tuple[Tuple[np.ndarray, np.ndarray],
                              Tuple[np.ndarray, np.ndarray]]:
    """Split into two non-overlapping temporal halves (corpora A and B)."""
    n = len(p)
    if n < 4:
        raise ValueError(f"Too few events ({n}) to split into 2 corpora")
    mid = n // 2
    return (p[:mid], y[:mid]), (p[mid:], y[mid:])


def run_stability(
    raw_probs: Sequence[float],
    outcomes: Sequence[float],
    *,
    seeds: Optional[List[int]] = None,
    min_history: int = 50,
    refit_every: int = 1,
    methods: Optional[List[str]] = None,
    bootstrap_frac: float = 0.8,
    require_2nd_corpus: bool = True,
) -> StabilityResult:
    """Multi-seed + 2nd-corpus calibrator stability check.

    For each seed: bootstrap-draw corpus_A, call select_calibrator.
    Also run select_calibrator on corpus_B (independent 2nd corpus).

    STABLE iff all valid seeds agree on the same method AND corpus_B
    (when require_2nd_corpus=True) also agrees.  Single-seed-only wins
    are UNSTABLE artifacts.  CALIBRATION != EDGE.
    """
    p = np.asarray(raw_probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    active_seeds: List[int] = seeds if seeds is not None else [0, 1, 2, 3, 4]

    try:
        (pA, yA), (pB, yB) = _split_corpus(p, y)
    except ValueError as exc:
        return StabilityResult(
            verdict="UNSTABLE", stable_method=None, seed_votes={}, per_seed=[],
            n_seeds=0, n_corpora=2,
            message=f"Cannot split corpora: {exc}. CALIBRATION != EDGE.",
        )

    per_seed: List[Dict] = []
    seed_votes: Dict[str, int] = {}

    for seed in active_seeds:
        rng = np.random.default_rng(seed)
        try:
            pd, yd = _bootstrap_draw(pA, yA, rng, frac=bootstrap_frac)
            if len(pd) <= min_history:
                per_seed.append({"seed": seed, "corpus_id": "A_bootstrap",
                                  "chosen_method": "SKIP_TOO_SMALL",
                                  "n": int(len(pd)), "n_eval": 0})
                continue
            res = select_calibrator(pd, yd, min_history=min_history,
                                     refit_every=refit_every, methods=methods)
            method = res["chosen_method"]
            per_seed.append({"seed": seed, "corpus_id": "A_bootstrap",
                              "chosen_method": method, "n": int(len(pd)),
                              "n_eval": res["n_eval"]})
            seed_votes[method] = seed_votes.get(method, 0) + 1
        except Exception as exc:  # noqa: BLE001
            per_seed.append({"seed": seed, "corpus_id": "A_bootstrap",
                              "chosen_method": "ERROR", "error": str(exc)})

    valid_rows = [r for r in per_seed
                  if r["chosen_method"] not in ("SKIP_TOO_SMALL", "ERROR")]
    n_valid = len(valid_rows)

    if n_valid == 0:
        return StabilityResult(
            verdict="UNSTABLE", stable_method=None, seed_votes=seed_votes,
            per_seed=per_seed, n_seeds=len(active_seeds), n_corpora=2,
            message="No valid seed evals (all skipped/errored). CALIBRATION != EDGE.",
        )

    seed_method_set = {r["chosen_method"] for r in valid_rows}
    all_agree = len(seed_method_set) == 1
    seed_winner = list(seed_method_set)[0] if all_agree else None

    corpus_b_method: Optional[str] = None
    corpus_b_row: Optional[Dict] = None
    if require_2nd_corpus:
        try:
            if len(pB) <= min_history:
                corpus_b_row = {"seed": "n/a", "corpus_id": "B_holdout",
                                "chosen_method": "SKIP_TOO_SMALL",
                                "n": int(len(pB)), "n_eval": 0}
            else:
                res_b = select_calibrator(pB, yB, min_history=min_history,
                                           refit_every=refit_every, methods=methods)
                corpus_b_method = res_b["chosen_method"]
                corpus_b_row = {"seed": "n/a", "corpus_id": "B_holdout",
                                "chosen_method": corpus_b_method,
                                "n": int(len(pB)), "n_eval": res_b["n_eval"]}
                seed_votes[corpus_b_method] = seed_votes.get(corpus_b_method, 0) + 1
        except Exception as exc:  # noqa: BLE001
            corpus_b_row = {"seed": "n/a", "corpus_id": "B_holdout",
                            "chosen_method": "ERROR", "error": str(exc)}
        if corpus_b_row is not None:
            per_seed.append(corpus_b_row)

    if not all_agree:
        verdict, stable_method = "UNSTABLE", None
        message = (f"Seeds disagree: {sorted(seed_method_set)}. "
                   f"Single-seed win is an artifact. NOT promoted. CALIBRATION != EDGE.")
    elif require_2nd_corpus and corpus_b_method is not None and corpus_b_method != seed_winner:
        verdict, stable_method = "UNSTABLE", None
        message = (f"Seeds agree on '{seed_winner}' but corpus_B chose '{corpus_b_method}'. "
                   f"Replication on 2nd corpus required. NOT promoted. CALIBRATION != EDGE.")
    elif require_2nd_corpus and (corpus_b_row is None
                                  or corpus_b_row.get("chosen_method") == "SKIP_TOO_SMALL"):
        verdict, stable_method = "UNSTABLE", None
        message = "corpus_B too small for replication. NOT promoted. CALIBRATION != EDGE."
    else:
        verdict, stable_method = "STABLE", seed_winner
        n_agreed = 1 + (1 if require_2nd_corpus and corpus_b_method == seed_winner else 0)
        message = (f"'{stable_method}' wins on {n_valid} seeds AND {n_agreed}/2 corpora. "
                   f"STABLE -- ready for promotion. CALIBRATION != EDGE.")

    return StabilityResult(
        verdict=verdict, stable_method=stable_method, seed_votes=seed_votes,
        per_seed=per_seed, n_seeds=len(active_seeds), n_corpora=2, message=message,
    )


def _main() -> int:
    rng = np.random.default_rng(99)
    N = 600
    true_p = rng.uniform(0.3, 0.7, N)
    raw = np.clip(np.where(true_p >= 0.5,
                            0.5 + (true_p - 0.5) * 2.0,
                            0.5 - (0.5 - true_p) * 2.0), 0.01, 0.99)
    outcomes = rng.binomial(1, true_p).astype(float)
    result = run_stability(raw, outcomes, seeds=[0, 1, 2, 3, 4], min_history=50)
    d = result.as_dict()
    print(f"\nNOTE: {CALIBRATION_NOTE}")
    print(f"Verdict       : {d['verdict']}")
    print(f"Stable method : {d['stable_method']}")
    print(f"Is promoted   : {result.is_promoted()}")
    print(f"Message       : {d['message']}")
    print(f"Seed votes    : {d['seed_votes']}")
    for row in d["per_seed"]:
        print(f"  {row}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
