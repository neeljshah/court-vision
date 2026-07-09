"""scripts.platformkit.ingame.nba_logistic_pricer -- DEPLOYABLE NBA in-game pricer,
the mechanism-ladder BASE spec frozen for shadow serving.

Same three features nba_mechanism_ladder.py's base model uses: standardized
[logit(prior_prob), signed margin, margin/sqrt(remaining_frac)]. This module does not
re-derive the spec or re-run the eval (that already happened, walk-forward, in
nba_mechanism_ladder.py -- Brier 0.07193 vs market 0.07174 on the 2025-26 held-out
fold). It only (1) fits ONCE on ALL checkpoint-corpus ticks through today (both
seasons -- a DEPLOYMENT fit, not an evaluation) and freezes the coefficients to a tiny
JSON artifact, then (2) prices a live tick from that frozen artifact -- pure math, no
corpus/sklearn/pandas dependency at serve time.

ARTIFACT: data/cache/ingame/nba_logistic_prior_v1.json (feature order, mu, sd,
intercept, coef, fit window, honest note). Human-readable, <5KB.

RUNTIME PRIOR (documented substitution): the ladder trained on
logit(first-traded market price). The live capture loop never persists a game's
first-tick market price across ticks (inplay_capture_loop / ingame_live_state have no
such cache) -- what IS already resolved per game, leak-free, is state['p0'], the
pregame MODEL prior from live_p0.live_p0_resolved (source 'PRIOR'/'PRIOR_TEAMS'). The
capture-loop wiring (inplay_capture_loop._nba_ladder_shadow) passes state['p0'] as
prior_prob. Both are pregame, leak-free, per-game scalars; they are not numerically
identical to the training feature. price() never fabricates a prior -- prior_prob=None
returns None (honest skip), matching every other shadow module's convention.

HONESTY (binding): shadow measurement only; no $/edge claim anywhere.

Fit + freeze the artifact (run manually, not on import):
  cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.ingame.nba_logistic_pricer --fit

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_nba_logistic_pricer.py -q
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_REPO = Path(__file__).resolve().parents[3]
ARTIFACT_PATH = _REPO / "data" / "cache" / "ingame" / "nba_logistic_prior_v1.json"
_EPS = 1e-6
_FEATURE_ORDER = ["logit_p0", "margin_s", "z"]


def _logit(p: float) -> float:
    p = min(max(float(p), _EPS), 1.0 - _EPS)
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    # numerically stable both directions
    if x >= 0:
        e = math.exp(-x)
        return 1.0 / (1.0 + e)
    e = math.exp(x)
    return e / (1.0 + e)


def _features(margin: float, frac_elapsed: float, prior_prob: float) -> Dict[str, float]:
    """Same transform as nba_mechanism_ladder.load_corpus: rem_frac floored at 1/96
    (an OT tick's frac_elapsed saturates at 1.0 in the live state, which floors rem the
    same way the ladder's OT-extended elapsed does -- see module test for the proof)."""
    rem = min(max(1.0 - float(frac_elapsed), 1.0 / 96.0), 1.0)
    return {
        "logit_p0": _logit(prior_prob),
        "margin_s": float(margin),
        "z": float(margin) / math.sqrt(rem),
    }


def fit(out_path: Path = ARTIFACT_PATH) -> Dict[str, Any]:
    """DEPLOYMENT fit: the ladder base spec on ALL corpus ticks (both seasons, no
    train/test split -- the held-out eval already ran in nba_mechanism_ladder.py).
    sklearn/pandas imported locally so serve-time price() needs neither."""
    from sklearn.linear_model import LogisticRegression
    from scripts.platformkit.ingame.nba_mechanism_ladder import load_corpus

    df = load_corpus()
    mu = df[_FEATURE_ORDER].mean()
    sd = df[_FEATURE_ORDER].std(ddof=0).replace(0.0, 1.0)
    X = ((df[_FEATURE_ORDER] - mu) / sd).to_numpy()
    y = df["outcome_home_win"].astype(int).to_numpy()
    clf = LogisticRegression(C=1e6, max_iter=2000)
    clf.fit(X, y)
    doc = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sport": "nba", "model": "nba_mechanism_ladder_base_v1",
        "feature_order": _FEATURE_ORDER,
        "mu": {c: float(mu[c]) for c in _FEATURE_ORDER},
        "sd": {c: float(sd[c]) for c in _FEATURE_ORDER},
        "intercept": float(clf.intercept_[0]),
        "coef": {c: float(w) for c, w in zip(_FEATURE_ORDER, clf.coef_[0])},
        "fit_window": {
            "seasons": sorted(df["season"].unique().tolist()),
            "n_ticks": int(len(df)), "n_games": int(df["game_id"].nunique()),
        },
        "prior_note": (
            "Trained on logit(first-traded market price); served with state['p0'] "
            "(leak-free pregame MODEL prior) as a documented substitution -- see "
            "module docstring."),
        "edge_claimed": False,
        "honest_note": (
            "Deployment fit of the ladder base spec (walk-forward MATCHed market on "
            "2025-26 held-out, see nba_mechanism_ladder.py); shadow-serving only, "
            "never decided on."),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(str(tmp), str(out_path))
    return doc


class NbaLogisticPricer:
    """Loads the frozen coefficient artifact once (lazy); price() is pure math after
    that -- no I/O per call. A missing/unreadable artifact -> price() always None."""

    def __init__(self, artifact_path: Path = ARTIFACT_PATH) -> None:
        self._path = Path(artifact_path)
        self._doc: Optional[Dict[str, Any]] = None
        self._broken = False

    def _ensure_loaded(self) -> bool:
        if self._doc is not None:
            return True
        if self._broken:
            return False
        try:
            self._doc = json.loads(self._path.read_text(encoding="utf-8"))
            return True
        except Exception:  # noqa: BLE001 -- a missing artifact is a clean skip, never a crash
            self._broken = True
            return False

    def price(self, margin: float, frac_elapsed: float,
             prior_prob: Optional[float]) -> Optional[float]:
        """P(home win). None on any missing input or unreadable artifact -- honest
        skip, never a fabricated 0.5 (matches every other shadow module's contract)."""
        if prior_prob is None or margin is None or frac_elapsed is None:
            return None
        if not self._ensure_loaded():
            return None
        try:
            feats = _features(margin, frac_elapsed, prior_prob)
            doc = self._doc
            z = float(doc["intercept"])
            for c in doc["feature_order"]:
                sd = float(doc["sd"][c]) or 1.0
                z += float(doc["coef"][c]) * ((feats[c] - float(doc["mu"][c])) / sd)
            return min(max(_sigmoid(z), 0.0), 1.0)
        except Exception:  # noqa: BLE001 -- pricing never raises into a caller's hot path
            return None


_SINGLETON: Optional[NbaLogisticPricer] = None


def get_pricer() -> NbaLogisticPricer:
    """Module-level singleton so repeated callers reuse one loaded artifact per process."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = NbaLogisticPricer()
    return _SINGLETON


def main(argv: Optional[list] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="nba_logistic_pricer")
    ap.add_argument("--fit", action="store_true", help="fit + freeze the coefficient artifact")
    args = ap.parse_args(argv)
    if args.fit:
        doc = fit()
        print("fit ok: n_ticks=%d n_games=%d seasons=%s -> %s" % (
            doc["fit_window"]["n_ticks"], doc["fit_window"]["n_games"],
            doc["fit_window"]["seasons"], ARTIFACT_PATH))
    else:
        print("nothing to do; pass --fit to (re)freeze the artifact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["ARTIFACT_PATH", "NbaLogisticPricer", "get_pricer", "fit"]
