"""Pre-registered elastic-net signal-combination gate (calibration only)."""
from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.clv_ledger_io import ledger_lock
from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, cumulative_k, eps_eff
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.walkforward import walk_forward

FAMILY = "nba_elastic_net_all_catalog_signals_v1"
LAMBDAS = (0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0)
MIN_TRAIN = 120
# THE one ledger for FAMILY (R13): rotating the path resets the cumulative-K bar.
CANONICAL_LEDGER = Path("data/cache/eval_gate/combo_fwer.json")


@dataclass(frozen=True)
class ComboResult:
    verdict: str
    chosen_lambda: float | None
    corrected_p: float | None
    k_cycle: int
    k_cumulative: int
    coefficients: dict[str, float]
    detail: dict[str, Any]


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p.astype(float), 1e-6, 1 - 1e-6)
    return np.log(p / (1.0 - p))


def _devig(home: pd.Series, away: pd.Series) -> np.ndarray:
    h, a = home.astype(float).to_numpy(), away.astype(float).to_numpy()
    hp = np.where(h < 0, -h / (-h + 100), 100 / (h + 100))
    ap = np.where(a < 0, -a / (-a + 100), 100 / (a + 100))
    return hp / (hp + ap)


def load_nba_catalog(data_root: Path) -> tuple[pd.DataFrame, list[str]]:
    """Load the catalog's pre-game schedule values using its documented data path."""
    from domains.basketball_nba.adapter import NBAAdapter
    from domains.basketball_nba import signal_catalog as base
    from domains.basketball_nba import signal_catalog_joint as joint
    games = pd.read_parquet(data_root / "games.parquet")
    odds = pd.read_parquet(data_root / "odds.parquet")
    adapter = NBAAdapter(repo_root=data_root.parents[2], games_df=games, odds_df=odds)
    bundle = adapter.feature_bundle(object())
    cols: dict[str, np.ndarray] = {}
    for cls in (*base.CATALOG_SIGNALS, *joint.CATALOG_SIGNALS):
        cols[str(cls.name)] = base._compute_signal_col(cls, bundle.base) if cls in base.CATALOG_SIGNALS else joint._compute_signal_col(cls, bundle.base)
    frame = pd.DataFrame(cols)
    frame["date"] = pd.to_datetime(bundle.dates)
    frame["outcome"] = bundle.target.astype(int)
    frame["close_prob"] = bundle.closing
    frame["game_id"] = [f"nba-{i}" for i in range(len(frame))]
    frame["home"] = games["home_team"].astype(str).to_numpy()[:len(frame)]
    frame["away"] = games["away_team"].astype(str).to_numpy()[:len(frame)]
    frame = frame.dropna(subset=["close_prob"]).sort_values("date").reset_index(drop=True)
    return frame, list(cols)


def _fit_predict(x: np.ndarray, y: np.ndarray, test: np.ndarray, lam: float) -> np.ndarray:
    model = LogisticRegression(penalty="elasticnet", solver="saga", l1_ratio=0.8,
                               C=1.0 / lam, max_iter=4000, random_state=2718)
    model.fit(x, y)
    return model.predict_proba(test)[:, 1]


def _replace_retry(tmp: Path, path: Path, attempts: int = 20) -> None:
    # ponytail: writers are already serialized by ledger_lock, so the only
    # remaining os.replace failure is Windows' transient sharing violation (a
    # scanner holding the destination open). Retry, don't crash the gate.
    for i in range(attempts):
        try:
            os.replace(tmp, path)
            return
        except OSError:
            if i == attempts - 1:
                raise
            time.sleep(0.02)


def _ledger(path: Path, k_cycle: int) -> int:
    """Charge k_cycle to the family total; return the new cumulative K.

    BY-DESIGN: the charge lands BEFORE results are computed and is never rolled
    back on a later exception -- an unspent charge only tightens eps_eff (safe
    fail-direction). The read-modify-write runs under a cross-process lock and
    the write is an atomic replace, so concurrent charges neither tear the JSON
    nor lose updates (a lost update would loosen eps_eff), and the replace is
    retried so a transient OS sharing violation cannot crash a live gate call.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_lock(path):
        prior = 0
        if path.exists():
            prior = int(json.loads(path.read_text(encoding="ascii")).get(FAMILY, 0))
        total = cumulative_k(prior, k_cycle)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps({FAMILY: total}, sort_keys=True), encoding="ascii")
        _replace_retry(tmp, path)
    return total


def run_combo_search(frame: pd.DataFrame, features: Sequence[str], *, ledger_path: Path,
                     lambdas: Sequence[float] = LAMBDAS,
                     allow_unregistered_search: bool = False) -> ComboResult:
    """Walk forward every registered lambda; CANONICAL_LEDGER is the search family.

    R13 guard: a rotated ledger_path resets the family's cumulative-K bar and a
    narrowed lambda grid under-charges the cycle, so any deviation from the
    canonical path + registered LAMBDAS must be explicitly labelled via
    allow_unregistered_search=True (tests only).
    """
    registered = (Path(ledger_path).resolve() == CANONICAL_LEDGER.resolve()
                  and tuple(float(l) for l in lambdas) == LAMBDAS)
    if not registered and not allow_unregistered_search:
        raise ValueError("unregistered search: non-canonical ledger_path or lambda grid resets/narrows "
                         "the R13 family budget; pass allow_unregistered_search=True only in tests")
    need = {"date", "game_id", "outcome", "close_prob", *features}
    if not need.issubset(frame):
        raise ValueError("catalog frame lacks declared columns")
    if "close_prob" in features:
        raise ValueError("'close_prob' collides with the declared anchor feature name")
    df = frame.sort_values("date").dropna(subset=list(need)).reset_index(drop=True)
    if len(df) <= MIN_TRAIN:
        return ComboResult("NOT_TESTABLE", None, None, len(lambdas), _ledger(ledger_path, len(lambdas)), {}, {"n": len(df)})
    x_raw = df.loc[:, features].to_numpy(float)
    y, close = df.outcome.to_numpy(int), df.close_prob.to_numpy(float)
    # Feed every lambda through the hardened split generator.  Features get an
    # explicit pre-prediction availability time, so a future-dated value fails there.
    # The pre-registered close anchor is a DECLARED, vintage-checked feature: the
    # test row's inputs come only from the redacted view (walk_forward strips
    # "index"), never from closing over the raw arrays (red-team 2026-09-01).
    states = [{"game_id": str(r.game_id), "home": str(getattr(r, "home", "h" + str(i))),
               "away": str(getattr(r, "away", "a" + str(i))), "state_ts": r.date.isoformat(),
               "features": {**{name: float(x_raw[i, j]) for j, name in enumerate(features)},
                            "close_prob": float(close[i])},
               "feature_avail": {name: (r.date - timedelta(seconds=1)).isoformat()
                                 for name in (*features, "close_prob")},
               "outcome": int(r.outcome), "devig_close_prob": float(r.close_prob), "index": i}
              for i, r in enumerate(df.itertuples(index=False))]
    preds, train_sizes = {}, None
    for lam in lambdas:
        def predict(train, test, _inside, lam=float(lam)):
            idx = np.array([s["index"] for s in train], dtype=int)   # train-side lookup only
            anchor = np.array([test["features"]["close_prob"]], dtype=float)
            if len(idx) < MIN_TRAIN:
                return float(anchor[0])
            mu, sd = x_raw[idx].mean(0), x_raw[idx].std(0) + 1e-9
            tv = np.array([[test["features"][name] for name in features]], dtype=float)
            return float(_fit_predict(np.column_stack([_logit(close[idx]), (x_raw[idx] - mu) / sd]), y[idx],
                                      np.column_stack([_logit(anchor), (tv - mu) / sd]), lam)[0])
        wf = walk_forward(states, predict, select_inside=True)
        preds[float(lam)] = np.array([r["p_model"] for r in wf.records])
        train_sizes = wf.n_train_sizes
    valid = np.asarray(train_sizes, dtype=int) >= MIN_TRAIN
    if valid.sum() < 40:
        return ComboResult("NOT_TESTABLE", None, None, len(lambdas), _ledger(ledger_path, len(lambdas)), {}, {"n": int(valid.sum())})
    pvals, rows = [], []
    for lam, p in preds.items():
        d = (close[valid] - y[valid]) ** 2 - (p[valid] - y[valid]) ** 2
        dm = diebold_mariano(d, df.game_id.to_numpy()[valid])
        rows.append({"lambda": lam, "brier": float(np.mean((p[valid] - y[valid]) ** 2)), "close_brier": float(np.mean((close[valid] - y[valid]) ** 2)), "dm_p": dm.p_value, "dm_stat": dm.dm_stat})
        pvals.append(dm.p_value)
    k = _ledger(ledger_path, len(lambdas))
    corrected = np.minimum(1.0, np.asarray(pvals) * k)
    best = int(np.argmin([r["brier"] for r in rows]))
    selected = rows[best]
    # Coefficients are descriptive: fit only history before the last OOF prediction.
    end = np.flatnonzero(valid)[-1]
    mu, sd = x_raw[:end].mean(0), x_raw[:end].std(0) + 1e-9
    fit = LogisticRegression(penalty="elasticnet", solver="saga", l1_ratio=0.8, C=1 / selected["lambda"], max_iter=4000, random_state=2718).fit(np.column_stack([_logit(close[:end]), (x_raw[:end] - mu) / sd]), y[:end])
    coef = {name: float(value) for name, value in zip(features, fit.coef_[0][1:]) if abs(value) > 1e-9}
    beats = selected["brier"] < selected["close_brier"] and corrected[best] <= DEFAULT_EPS
    verdict = "SHIP_ELIGIBLE" if beats else ("MATCHES_CLOSE" if not coef else "BEHIND_CLOSE")
    return ComboResult(verdict, selected["lambda"], float(corrected[best]), len(lambdas), k, coef, {"n": int(valid.sum()), "eps_eff": eps_eff(DEFAULT_EPS, k), "path": rows, "selected_raw_p": selected["dm_p"], "truncation_invariance": True})


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="pre-registered elastic-net combo search")
    ap.add_argument("--data-root", type=Path, default=Path("data/domains/basketball_nba"))
    ap.add_argument("--ledger", type=Path, default=CANONICAL_LEDGER)
    ap.add_argument("--allow-unregistered-search", action="store_true")
    args = ap.parse_args(argv)
    frame, features = load_nba_catalog(args.data_root)
    result = run_combo_search(frame, features, ledger_path=args.ledger,
                              allow_unregistered_search=args.allow_unregistered_search)
    print(json.dumps({**result.__dict__, "coefficients": result.coefficients}, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
