"""S114 -- NESTED-selection ensemble of NBA in-game hypotheses, scored OUT of sample.

Per OUTER fold (game-first-date blocks on the S86 SCREEN side, settlement purge, 1-day
embargo, 5 scored folds): split the outer TRAIN window again by game-first date; screen every
frozen hypothesis on that inner split ONLY; rank by the TRAIN-ONLY DM p; take the top-k by
DISTINCT SOURCE COLUMN (S79); fit ONE L2 logistic over them with logit(market) as an OFFSET
of FIXED coefficient 1; score the held-out fold, which the selection never saw.

S125: `purge` parses stamps to UTC before comparing -- string order is not time order. S126:
the recalibration NULL is re-fit on each k-arm's OWN rows, so the ladder compares k and not
row sets; n_fit / n_null_fit / n_scored are published per k per fold. The archived per-k table
PREDATES both fixes and must be RE-RUN before it is quoted.

A SCREEN IS A NON-FINDING: no ledger row, no prereg seal, no charge, no K consumed, and the
VERDICT side is never opened. Calibration language only. BAR = 0.004 is IMPORTED from the
S82 tier, never redefined (Q3/B10). ASCII only. Method + results:
docs/evidence/harness/S114_ingame_ensemble_2026-09-03.md -- per-file test:
python -m pytest tests/platformkit/ingame/test_s114_ingame_ensemble.py -q
"""
from __future__ import annotations

import argparse, json, time
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.combo.fwer_budget import bh_within_family
from scripts.platformkit.eval_gate.s114_ladder_stats import paired, pbo
from scripts.platformkit.eval_gate.tick_informative import attach_informative_summary
from scripts.platformkit.foundry import ingame_grammar_nba as grammar
from scripts.platformkit.foundry.ingame_screen import (BAR, EMBARGO_DAYS, MIN_TRAIN,
                                                       ROOT, _fit, utc_stamps)  # re-exported
from scripts.platformkit.foundry.ingame_screen_nba import (N_FOLDS, _dm_fast,
                                                           causal_source, load_screen)
from scripts.platformkit.foundry.screen_predictor import RIDGE, _logistic, _logit

K_VALUES: Tuple[int, ...] = (1, 3, 5, 10)
INNER_FRAC = 0.7             # share of the outer train window's ticks kept for the inner fit
Q_WITHIN = 0.05              # the frozen within-family BH level; reported, never a filter
OUT_DIR = ROOT / "data" / "cache" / "eval_gate"
STEM = "s114_ingame_ensemble"
SLIM = ["game", "y", "p_e4"]  # the only columns the inner screen reads

def _sigmoid(eta: np.ndarray) -> np.ndarray:
    return np.clip(1.0 / (1.0 + np.exp(-eta)), 0.001, 0.999)

def _anchor(frame: pd.DataFrame) -> np.ndarray:
    return np.array([_logit(p) for p in frame["p_e4"]], dtype=float)

def masked(grid: pd.DataFrame, period: pd.Series, hypothesis) -> pd.Series:
    """The hypothesis's grid column, masked to its phase when conditioned."""
    values = grid[grammar.hypothesis_column(hypothesis)]
    phase = grammar.hypothesis_phase(hypothesis)
    return grammar.conditioned(values, period, phase) if phase else values

def purge(rows: pd.DataFrame, test: pd.DataFrame, embargo_days: int = EMBARGO_DAYS):
    """S82's rule, unchanged: a train game's LAST tick precedes the fold by `embargo_days`.
    S125: parsed to UTC first -- string order is not time order, and both asserts shared it."""
    stamps, first = utc_stamps(rows["ts"]), utc_stamps(test["ts"]).min()
    last_ts = stamps.groupby(rows["game"].to_numpy()).max()
    edge = first - pd.Timedelta(days=embargo_days)
    train = rows[rows["game"].isin(last_ts.index[last_ts < edge])]
    if not train.empty:
        assert not (set(train["game"]) & set(test["game"])), "fold not game-disjoint"
        assert stamps[train.index].max() < first, "purge violated: train outlives the fold"
    return train, edge.strftime("%Y-%m-%dT%H:%M:%SZ")

def inner_split(train: pd.DataFrame, frac: float = INNER_FRAC):
    """Split the outer TRAIN window by game-first date at `frac` of its ticks -- whole games
    both sides, same purge. The inner test ranks hypotheses and is never scored."""
    day = train["game"].map(train.groupby("game")["date"].min())
    counts = day.value_counts().sort_index()
    days = list(counts.index)
    position = int(np.searchsorted(counts.cumsum().to_numpy(), frac * len(train)))
    position = min(position, len(days) - 2) if len(days) > 1 else -1
    inner_test = train.iloc[:0] if position < 0 else train[day.isin(days[position + 1:])]
    if inner_test.empty:
        return train.iloc[:0], train.iloc[:0]
    return purge(train, inner_test)[0], inner_test

def recal_null(train: pd.DataFrame, anchor_test: np.ndarray) -> np.ndarray:
    """S94's global recalibration `[1, logit(market)]`, fit on the outer train window."""
    design = np.column_stack([np.ones(len(train)), _anchor(train)])
    coef = _logistic(design, train["y"].to_numpy(dtype=float), ridge=RIDGE)
    return _sigmoid(coef[0] + coef[1] * anchor_test)

def screen_one(train: pd.DataFrame, test: pd.DataFrame, column: str,
               anchor_test: Optional[np.ndarray] = None) -> Optional[dict]:
    """One hypothesis fit on `train`, scored on `test`: gain over the recalibration null.
    S102's arithmetic; missing != bad -- a NaN tick falls back to the null on BOTH arms."""
    fit = _fit(train, column)
    codes, uniques = pd.factorize(test["game"], sort=False)
    if fit is None or len(uniques) < 2:
        return None
    coef, null, mu, sd = fit
    anchor = _anchor(test) if anchor_test is None else anchor_test
    x, y = test[column].to_numpy(dtype=float), test["y"].to_numpy(dtype=float)
    p_null = _sigmoid(null[0] + null[1] * anchor)
    p_c = np.where(np.isfinite(x),
                   _sigmoid(coef[0] + coef[1] * anchor + coef[2] * (x - mu) / sd), p_null)
    delta = (p_null - y) ** 2 - (p_c - y) ** 2
    return {"improvement": float(delta.mean()),
            "p_raw": float(_dm_fast(delta, codes, len(uniques))[1])}

def select_topk(screens: Sequence[dict], k: int) -> List[dict]:
    """The S79 pick rule: best-p first, at most ONE hypothesis per distinct SOURCE column."""
    ranked = sorted((s for s in screens if s["improvement"] > 0.0),
                    key=lambda s: (s["p_raw"], -s["improvement"], s["label"]))
    picked, seen = [], set()
    for screen in ranked:
        if screen["source"] not in seen:
            seen.add(screen["source"])
            picked.append(screen)
        if len(picked) >= k:
            break
    return picked

def fit_offset(design: np.ndarray, y: np.ndarray, offset: np.ndarray,
               ridge: float = RIDGE, iters: int = 25) -> np.ndarray:
    """`screen_predictor._logistic` with an offset term whose coefficient is FIXED at 1."""
    weights, eye = np.zeros(design.shape[1]), ridge * np.eye(design.shape[1])
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(design @ weights + offset)))
        step = np.linalg.solve((design * (p * (1.0 - p))[:, None]).T @ design + eye,
                               design.T @ (p - y) + ridge * weights)
        weights -= step
        if np.abs(step).max() < 1e-8:
            break
    return weights

def ensemble_fold(train: pd.DataFrame, test: pd.DataFrame, columns: Sequence[str],
                  p_null_test: np.ndarray) -> Tuple[np.ndarray, np.ndarray, dict]:
    """One L2 logistic over `columns` on the fixed market offset; scores `test`. S126: the
    NULL is RE-FIT on the k-arm's own `keep` rows and returned beside it, so the arms differ
    only by the candidate terms (fold F1 fit the null on 38,966 rows against k3/k5's 25,722,
    which made the published ladder a comparison of ROW SETS as well as of k)."""
    stack = np.column_stack([train[c].to_numpy(dtype=float) for c in columns])
    keep = np.isfinite(stack).all(axis=1)
    if int(keep.sum()) < MIN_TRAIN or train["y"][keep].nunique() < 2:
        return p_null_test, p_null_test, {"status": "UNFITTABLE", "n_fit": int(keep.sum()),
                                          "n_null_fit": int(len(train)), "n_scored": 0}
    stack, sub = stack[keep], train[keep]
    anchor = _anchor(test)
    p_null_k = recal_null(sub, anchor)               # the SAME rows the k-arm is fit on (S126)
    mu, sd = stack.mean(axis=0), np.where(stack.std(axis=0) > 0, stack.std(axis=0), 1.0)
    weights = fit_offset(np.column_stack([np.ones(len(sub)), (stack - mu) / sd]),
                         sub["y"].to_numpy(dtype=float), _anchor(sub))
    x_test = np.column_stack([test[c].to_numpy(dtype=float) for c in columns])
    finite = np.isfinite(x_test).all(axis=1)
    eta = anchor + weights[0] + np.nan_to_num((x_test - mu) / sd) @ weights[1:]
    return (np.where(finite, _sigmoid(eta), p_null_k), p_null_k,
            {"status": "OK", "n_fit": int(keep.sum()), "n_null_fit": int(keep.sum()),
             "n_scored": int(finite.sum()), "coef": [float(w) for w in weights],
             "mu": [float(v) for v in mu], "sd": [float(v) for v in sd],
             "test_coverage": float(finite.mean())})

def run(rows: pd.DataFrame, grid: pd.DataFrame, hypotheses: Dict[str, object],
        *, verbose: bool = True) -> dict:
    """The nested walk-forward: per-fold selection, per-fold fit, held-out scoring."""
    period = rows["period"]
    pieces, fold_records, screen_records = [], [], []
    for block in sorted(rows["game_date"].unique())[1:]:
        test = rows[rows["game_date"] == block]
        train, cut = purge(rows, test, EMBARGO_DAYS)
        if train.empty:
            fold_records.append({"fold": block, "status": "NO_TRAIN"})
            continue
        inner_train, inner_test = inner_split(train)
        started, screens = time.time(), []
        slim_train, slim_test = inner_train[SLIM], inner_test[SLIM]
        inner_anchor = _anchor(inner_test) if len(inner_test) else np.zeros(0)
        for label, hypothesis in hypotheses.items():
            values = masked(grid, period, hypothesis)
            result = screen_one(slim_train.assign(**{label: values.loc[inner_train.index]}),
                                slim_test.assign(**{label: values.loc[inner_test.index]}),
                                label, inner_anchor)
            if result is not None:
                screens.append(dict(result, label=label, source=hypothesis.feature))
        bh = bh_within_family([s["p_raw"] for s in screens], q=Q_WITHIN) if screens else None
        screen_records += [dict(s, fold=block, bh_adj_p=bh.adjusted[i] if bh else None)
                           for i, s in enumerate(screens)]
        p_null = recal_null(train, _anchor(test))
        piece = test[["game", "ts", "y", "market", "model", "informative"]].assign(
            fold=block, p_null=p_null)
        record = {"fold": block, "status": "OK", "cut": cut, "n_train": int(len(train)),
                  "n_train_games": int(train["game"].nunique()), "n_test": int(len(test)),
                  "n_inner_train": int(len(inner_train)), "n_inner_test": int(len(inner_test)),
                  "n_screened": len(screens), "n_unscored": len(hypotheses) - len(screens),
                  "n_bh_discoveries": int(sum(bh.rejected)) if bh else 0, "selected": {},
                  "fits": {}}
        for k in K_VALUES:
            labels = [s["label"] for s in select_topk(screens, k)]
            record["selected"]["k%d" % k] = labels
            columns = pd.DataFrame({l: masked(grid, period, hypotheses[l]) for l in labels})
            none = {"status": "NO_SELECTION", "n_fit": 0, "n_null_fit": len(train),
                    "n_scored": 0}
            probs, null_k, meta = ((p_null, p_null, none) if not labels else ensemble_fold(
                train.join(columns), test.join(columns), labels, p_null))
            piece["p_k%d" % k], piece["p_null_k%d" % k] = probs, null_k
            record["fits"]["k%d" % k] = meta
        fold_records.append(dict(record, seconds=time.time() - started))
        pieces.append(piece)
        if verbose:
            print("[%s] train %d/%dg inner %d/%d screened %d %.1fs" % (
                block, len(train), record["n_train_games"], len(inner_train),
                len(inner_test), len(screens), time.time() - started), flush=True)
    return {"folds": fold_records, "screens": pd.DataFrame(screen_records),
            "series": pd.concat(pieces).sort_values(["game", "ts"], kind="stable")}

def summarise(result: dict) -> dict:
    """The per-k table, the selection stability, the PBO over k, and the verdict."""
    series, folds = result["series"], result["folds"]
    y = series["y"].to_numpy(dtype=float)
    scored = [f for f in folds if f.get("status") == "OK"]
    artifact: dict = {
        "row": "S114", "verdict_side_read": False, "bar": BAR, "k_values": list(K_VALUES),
        "n_ticks": int(len(series)), "n_games": int(series["game"].nunique()),
        "brier_market": float(((series["market"] - y) ** 2).mean()),
        "brier_recal_null": float(((series["p_null"] - y) ** 2).mean()),
        "brier_model_asof": float(((series["model"] - y) ** 2).mean()), "folds": [{a: b for a, b in f.items() if a != "fits"} for f in folds],
        "fits": {f["fold"]: f["fits"] for f in scored}, "per_k": {}}
    per_fold = pd.DataFrame({c: (series[c] - y) ** 2 for c in ["market"] + [
        "p_k%d" % k for k in K_VALUES]}).groupby(series["fold"].to_numpy()).mean()
    matrix = {f: {k: float(per_fold.loc[f, "market"] - per_fold.loc[f, "p_k%d" % k])
                  for k in K_VALUES} for f in per_fold.index}
    for k in K_VALUES:
        key, column = "k%d" % k, "p_k%d" % k
        chosen = [f["selected"][key] for f in scored]
        jaccard = [len(set(a) & set(b)) / len(set(a) | set(b)) if (set(a) | set(b)) else None
                   for a, b in zip(chosen, chosen[1:])]
        stable = [j for j in jaccard if j is not None]
        arms = {"n_%s_per_fold" % n: {f["fold"]: f["fits"][key].get("n_%s" % n) for f in scored}
                for n in ("fit", "null_fit", "scored")}
        block = {"brier": float(((series[column] - y) ** 2).mean()), **arms,
                 "vs_market": paired(series, "market", column),
                 "vs_recal_null": paired(series, "p_null_%s" % key, column),   # same rows (S126)
                 "vs_k1": paired(series, "p_k1", column),
                 "selected_per_fold": {f["fold"]: s for f, s in zip(scored, chosen)},
                 "jaccard_consecutive": jaccard,
                 "jaccard_mean": float(np.mean(stable)) if stable else None}
        clears = bool(block["vs_market"]["improvement"] >= BAR
                      and block["vs_market"]["ci95"][0] > 0.0)
        beats = bool(block["vs_recal_null"]["improvement"] > 0.0
                     and (k == 1 or block["vs_k1"]["improvement"] > 0.0))
        block.update(clears_bar_vs_market=clears, beats_both_nulls=beats,
                     prereg_draft_condition=clears and beats)
        artifact["per_k"][key] = block
    artifact["pbo_over_k"] = pbo(matrix, K_VALUES) if len(matrix) >= 3 else {"pbo": None}
    artifact["per_fold_improvement_vs_market"] = matrix
    best = max(K_VALUES, key=lambda k: artifact["per_k"]["k%d" % k]["vs_market"]["improvement"])
    delta = (series["market"] - y) ** 2 - (series["p_k%d" % best] - y) ** 2
    attach_informative_summary(artifact, series.assign(d=delta), "d", ts_col="ts")
    artifact["best_k"] = best
    artifact["any_prereg_draft"] = any(b["prereg_draft_condition"]
                                       for b in artifact["per_k"].values())
    artifact["verdict"] = ("PREREG DRAFT CONDITION MET" if artifact["any_prereg_draft"]
                           else "SCREEN_NULL -- no k clears +%.3f vs the raw market" % BAR)
    return artifact

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="S114 nested in-game ensemble (NBA)")
    parser.add_argument("--limit-hypotheses", type=int, default=0)
    args = parser.parse_args(argv)
    rows = load_screen(n_folds=N_FOLDS)
    grid = grammar.build_grid(causal_source(rows))
    hypotheses = {grammar.hypothesis_label(h): h for h in grammar.enumerate_hypotheses()}
    hypotheses = dict(list(hypotheses.items())[:args.limit_hypotheses or None])
    print("rows %d / games %d / hypotheses %d" % (
        len(rows), rows["game"].nunique(), len(hypotheses)), flush=True)
    result = run(rows, grid, hypotheses)
    artifact = summarise(result)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result["series"].to_csv(OUT_DIR / ("%s_series.csv" % STEM), index=False)   # Q9
    result["screens"].to_csv(OUT_DIR / ("%s_screens.csv" % STEM), index=False)
    (OUT_DIR / ("%s.json" % STEM)).write_text(json.dumps(artifact, indent=2, default=str),
                                               encoding="ascii", errors="backslashreplace")
    print(artifact["verdict"], "| best k=%d | n=%d" % (artifact["best_k"], artifact["n_ticks"]))
    for key, b in artifact["per_k"].items():
        print("%-4s brier %.6f | vs market %+.6f %s | vs recal %+.6f | vs k1 %+.6f | J %s" % (
            key, b["brier"], b["vs_market"]["improvement"], b["vs_market"]["ci95"],
            b["vs_recal_null"]["improvement"], b["vs_k1"]["improvement"], b["jaccard_mean"]))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
