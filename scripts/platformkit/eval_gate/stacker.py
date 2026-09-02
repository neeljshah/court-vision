"""scripts.platformkit.eval_gate.stacker -- S06 nested-CV stacker over OOF gap arms.

Meta-weights fit on INNER CPCV folds (cpcv_evaluate, 8/2/embargo 1); verdict scored on an
OUTER expanding GAME-FIRST-DATE walk-forward, per-fold game-disjoint asserted (pre-flight
S06_OOF_PREFLIGHT_2026-09-03). Absent arm = MASK, never 0.5; fallback arm until the inner
folds hold MIN_TRAIN rows; fold fits keyed by frozenset(train game_ids), never id(train)
(RT-2). SEAL -> CHARGE -> compute (Q1/Q2). Calibration only. ASCII. Prereg:
docs/evidence/harness/S06_STACKER_PREREG_2026-09-03.md.
Per-file test: python -m pytest scripts/platformkit/eval_gate/test_stacker.py -q
"""
from __future__ import annotations

import hashlib, json, math, re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.combo.fwer_budget import min_corpora_eff
from scripts.platformkit.combo.stack_fit import build_design, fit_logistic, logit, sigmoid
from scripts.platformkit.eval_gate.backtest_runner import _charge_ledger
from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.deflated_metrics import deflated_p
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.pbo import cscv_pbo
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size

REPO = Path(__file__).resolve().parents[3]
LEDGER = REPO / "data" / "cache" / "eval_gate" / "backtest_fwer.jsonl"
PREREG = REPO / "docs" / "evidence" / "harness" / "S06_STACKER_PREREG_2026-09-03.md"
SPEC_ID, START, END = "scripts.platformkit.eval_gate.stacker:mlb_stack_v1", "2026-06-28", "2026-07-12"
BAR = 0.004                        # paired Brier improvement bar; never moves (Q3)
INCUMBENT = 0.2070329295167757     # e4_blend paired ALL-TICKS Brier (pre-flight sec 4)
MIN_TRAIN, MIN_REGIME, MIN_PATTERN = 1000, 200, 200
_INNING = re.compile(r"inning=(\d+)")
Series = List[Optional[float]]

def _finite(v: Any) -> bool:
    return v is not None and math.isfinite(float(v))

def brier(p: Sequence[float], y: Sequence[float]) -> float:
    pa, ya = np.asarray(p, float), np.asarray(y, float); return float(np.mean((pa - ya) ** 2)) if len(pa) else float("nan")  # noqa: E702

def inning_bucket(tick: Mapping[str, Any]) -> str:
    """Regime key: hedge_trial_runner._inning's buckets, reproduced verbatim."""
    m = _INNING.search(str(tick.get("state_summary") or ""))
    return ("unknown" if not m else "early_1_3" if int(m.group(1)) <= 3
            else "mid_4_6" if int(m.group(1)) <= 6 else "late_7plus")

def _first_dates(ticks) -> Dict[str, str]:
    first: Dict[str, str] = {}
    for t in ticks:
        g, d = str(t["game"]), str(t["timestamp"])[:10]; first[g] = min(first.get(g, d), d)  # noqa: E702
    return first

def fit_meta(arm_preds: np.ndarray, y: np.ndarray, *, method: str = "logit_ridge",
             regime: Optional[np.ndarray] = None) -> np.ndarray:
    """Logit-ridge meta-weights over FINITE (n, k) arm preds -> (k+1,) intercept first;
    with `regime`, one row per sorted unique regime (< MIN_REGIME rows -> pooled)."""
    if method != "logit_ridge": raise ValueError("unknown method %r" % method)  # noqa: E701
    mat, yy = np.asarray(arm_preds, float), np.asarray(y, float)
    X = build_design([logit(mat[:, j]) for j in range(mat.shape[1])])
    pooled = fit_logistic(X, yy).weights
    if regime is None: return pooled  # noqa: E701
    reg = np.asarray([str(r) for r in regime])
    return np.vstack([fit_logistic(X[reg == k], yy[reg == k]).weights
                      if int((reg == k).sum()) >= MIN_REGIME else pooled for k in sorted(set(reg))])

def _pattern_fits(mat, y, regimes):
    # pattern P fit on every row where ALL of P's arms are finite (supersets included)
    finite, reg = np.isfinite(mat), np.asarray([str(r) for r in regimes])
    fits: Dict[tuple, Dict[str, np.ndarray]] = {}
    for pat in {tuple(np.flatnonzero(row)) for row in finite}:
        rows = finite[:, list(pat)].all(axis=1) if pat else np.zeros(len(mat), bool)
        if int(rows.sum()) < MIN_PATTERN: continue  # noqa: E701
        sub, yy, rr = mat[np.ix_(rows, list(pat))], y[rows], reg[rows]
        X = build_design([logit(sub[:, j]) for j in range(sub.shape[1])])
        entry = {"__pool__": fit_logistic(X, yy).weights}
        for key in sorted(set(rr)):
            if int((rr == key).sum()) >= MIN_REGIME: entry[key] = fit_logistic(X[rr == key], yy[rr == key]).weights  # noqa: E701
        fits[pat] = entry
    return fits

def _predict_one(vals, regime, fits, fallback_idx, raw_idx):
    # largest fitted pattern that is a SUBSET of the available arms; masked, never 0.5
    avail, best = set(np.flatnonzero(np.isfinite(vals))), None
    for pat in fits:
        if set(pat) <= avail and (best is None or len(pat) > len(best)): best = pat  # noqa: E701
    if best is None: return float(vals[fallback_idx if np.isfinite(vals[fallback_idx]) else raw_idx])  # noqa: E701
    w = fits[best].get(regime, fits[best]["__pool__"])
    return float(np.clip(sigmoid(np.array([float(np.concatenate(([1.0], logit(vals[list(best)]))) @ w)]))[0], 0.0, 1.0))

def stack_predictor(arm_names: Sequence[str], *, fallback: str):
    """cpcv_evaluate-shaped predictor: per-pattern/per-regime meta weights fit on the purged
    train states' ticks; fits cached under frozenset(train game_ids) (content fold id, RT-2)."""
    names = list(arm_names)
    f_idx, r_idx = names.index(fallback), names.index("raw_model")

    def predictor(train: List[dict], test: dict, _select_inside: bool) -> float:
        key = frozenset(s["game_id"] for s in train)
        if key not in predictor.fold_fits:
            mats, fits = [np.asarray(s["features"]["arm_rows"], float) for s in train], {}
            if mats and sum(len(m) for m in mats) >= MIN_TRAIN:
                y = np.concatenate([np.full(len(m), float(s["outcome"])) for m, s in zip(mats, train)])
                fits = _pattern_fits(np.vstack(mats), y, [r for s in train for r in s["features"]["regime_rows"]])
            predictor.fold_fits[key] = fits
        mid = int(test["features"]["mid"])
        vals = np.asarray(test["features"]["arm_rows"], float)[mid]
        return _predict_one(vals, str(test["features"]["regime_rows"][mid]), predictor.fold_fits[key], f_idx, r_idx)

    predictor.fold_fits = {}; return predictor  # noqa: E702

def _states(ticks, arms, regimes, game_idx):
    names, states = list(arms), []
    for gid, raw_idx in game_idx.items():
        idx = sorted(raw_idx, key=lambda i: str(ticks[i]["timestamp"]))
        mat = np.array([[float(arms[n][i]) if _finite(arms[n][i]) else np.nan for n in names] for i in idx])
        last = datetime.fromisoformat(str(ticks[idx[-1]]["timestamp"]).replace("Z", "+00:00"))
        code = str(gid).rsplit("-", 1)[-1][-6:]  # home/away parse mirrors hedge_trial_arms.game_states
        states.append({"game_id": str(gid), "state_ts": (last + timedelta(seconds=1)).isoformat(),
                       "home": code[3:], "away": code[:3], "outcome": int(float(ticks[idx[0]]["outcome"])),
                       "features": {"arm_rows": mat, "regime_rows": [regimes[i] for i in idx], "mid": len(idx) // 2},
                       "feature_avail": {kk: last.isoformat() for kk in ("arm_rows", "regime_rows", "mid")}})
    return sorted(states, key=lambda s: s["state_ts"])

def outer_walk_forward(ticks, arms: Mapping[str, Series], regimes, *, fallback: str) -> tuple:
    """OUTER expanding game-first-date walk-forward; each fold's weights average the
    INNER cpcv fold fits over the outer-train games only. Game-disjoint asserted."""
    names = list(arms)
    f_idx, r_idx = names.index(fallback), names.index("raw_model")
    first, by_game = _first_dates(ticks), defaultdict(list)
    for i, t in enumerate(ticks):
        if t.get("outcome") is not None: by_game[str(t["game"])].append(i)  # noqa: E701
    out, folds = [None] * len(ticks), []
    for date in sorted({first[g] for g in by_game})[1:]:
        train_games = {g for g in by_game if first[g] < date}
        test_games = {g for g in by_game if first[g] == date}
        assert not (train_games & test_games), "outer fold not game-disjoint"
        tr_idx = {g: by_game[g] for g in train_games}
        n_train, fits, inner = sum(len(v) for v in tr_idx.values()), {}, None
        states = _states(ticks, arms, regimes, tr_idx) if n_train >= MIN_TRAIN else []
        if len({s["state_ts"] for s in states}) >= 8:   # cpcv needs >= n_groups distinct stamps
            pred = stack_predictor(names, fallback=fallback)
            recs = cpcv_evaluate(states, pred, n_groups=8, n_test_groups=2, embargo_days=1)
            acc: Dict[tuple, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
            for ff in pred.fold_fits.values():
                for pat, entry in ff.items():
                    for kk, w in entry.items(): acc[pat][kk].append(np.asarray(w, float))  # noqa: E701
            fits = {p: {k: np.mean(ws, axis=0) for k, ws in e.items()} for p, e in acc.items()}
            inner = {"n_paths": len({r["split_id"] for r in recs}), "n_fold_fits": len(pred.fold_fits), "inner_brier": brier([r["p_model"] for r in recs], [r["y"] for r in recs])}
        for g in test_games:
            for i in by_game[g]:
                vals = np.asarray([float(arms[n][i]) if _finite(arms[n][i]) else np.nan for n in names])
                out[i] = _predict_one(vals, regimes[i], fits, f_idx, r_idx)
        folds.append({"date": date, "n_train_ticks": n_train, "fallback_used": not fits, "inner": inner, "n_test_ticks": sum(len(by_game[g]) for g in test_games)})
    return out, folds

def e4_gd_series(ticks, features: pd.DataFrame, column: str = "arm_b_prob") -> Series:
    """GAME-FIRST-DATE e4_blend (leak-free variant, pre-flight sec 3); game-disjoint asserted."""
    from scripts.platformkit import hedge_trial_arms as A
    from scripts.platformkit.ingame import gap_blend_arm as B
    first = _first_dates(ticks)
    signal = features.set_index(["game", "timestamp"])["score_diff"].to_dict()
    keep = [t for t in ticks if pd.notna(signal.get((t["game"], t["timestamp"])))]
    rows = [{**t, "state_signal": float(signal[(t["game"], t["timestamp"])]),
             "game_date": first[str(t["game"])]} for t in keep]
    frame = B._frame(rows); assert len(frame) == len(rows), "gap_blend_arm._frame dropped rows"  # noqa: E702
    frame["_row_id"] = [int(t["_row_id"]) for t in rows]
    for d in sorted(frame["date"].unique())[1:]:
        assert not (set(frame[frame["date"] < d]["game"]) & set(frame[frame["date"] == d]["game"]))
    scored, _ = B._walk_forward(frame, B._DEFAULT_W_MAX, B._DEFAULT_MAX_DEVIATION)
    return A._by_row(scored, len(ticks), column)

def e2_gd_series(ticks) -> Series:
    """GAME-FIRST-DATE e2_regime (leak-free variant, pre-flight sec 3)."""
    from scripts.platformkit.ingame import gap_regime_arm as R
    from scripts.platformkit.regime_calibration import buckets, fit_per_regime
    first = _first_dates(ticks)
    usable = [dict(t) for t in ticks if {"game", "model_prob", "market_prob", "outcome"}.issubset(t) and t.get("in_window", True)]
    out: Series = [None] * len(ticks)
    for test_date in sorted({first[str(t["game"])] for t in usable})[1:]:
        train = [t for t in usable if first[str(t["game"])] < test_date]
        test = [t for t in usable if first[str(t["game"])] == test_date]
        if not train or not test: continue  # noqa: E701
        assert not ({t["game"] for t in train} & {t["game"] for t in test}), "e2 fold not game-disjoint"
        fits = fit_per_regime([float(t["model_prob"]) for t in train], [float(t["outcome"]) for t in train],
                              buckets(R._month_confidence_rows(train)), min_n=200)
        probs, _ = R._apply(fits, buckets(R._month_confidence_rows(test)), [float(t["model_prob"]) for t in test])
        for t, p in zip(test, probs):
            out[int(t["_row_id"])] = float(p) if math.isfinite(float(p)) else None
    return out

def run_stacker_trial(ticks, arms: Mapping[str, Series], *, sport: str, ledger_path: Path,
                      prereg_sha256: str, prereg_path: Path = PREREG, regimes=None,
                      fallback: str = "e4_blend", pair: str = "e4_blend", incumbent=None,
                      scored_idx=None, guard: Optional[Series] = None, repro: Sequence[tuple] = (),
                      dropped_detail=None, out_path=None, series_path=None) -> dict:
    """SEAL -> CHARGE -> compute. row['k_cumulative'] is the ONLY K used (Q2)."""
    seal = hashlib.sha256(Path(prereg_path).read_bytes()).hexdigest()
    if seal != prereg_sha256: raise AssertionError("prereg sha mismatch: %s != %s" % (seal, prereg_sha256))  # noqa: E701
    row = _charge_ledger(Path(ledger_path), SPEC_ID, sport, START, END)
    k, names = int(row["k_cumulative"]), list(arms)  # the ONLY K used anywhere
    y_all = [float(t["outcome"]) if t.get("outcome") is not None else float("nan") for t in ticks]
    for name, series, idx, target in repro:
        got = brier([float(series[i]) for i in idx], [y_all[i] for i in idx])
        assert abs(got - target) < 1e-9, "ARM REPRODUCTION FAILED %s: %.15f vs %.15f (n=%d)" % (name, got, target, len(idx))
    regimes = list(regimes) if regimes is not None else [inning_bucket(t) for t in ticks]
    stack, folds = outer_walk_forward(ticks, arms, regimes, fallback=fallback)
    if scored_idx is None:
        scored_idx = [i for i, t in enumerate(ticks) if _finite(stack[i]) and _finite(arms[pair][i]) and _finite(t.get("market_prob"))]
    idxs = sorted(scored_idx, key=lambda i: (str(ticks[i]["timestamp"]), str(ticks[i]["game"]), i))
    games, y = [str(ticks[i]["game"]) for i in idxs], np.array([y_all[i] for i in idxs])
    M = np.array([[float(arms[n][i]) if _finite(arms[n][i]) else np.nan for n in names] for i in idxs])
    p_stack = np.array([float(stack[i]) for i in idxs])
    p_pair, p_unif = np.array([float(arms[pair][i]) for i in idxs]), np.nanmean(M, axis=1)
    l_stack, l_pair = (p_stack - y) ** 2, (p_pair - y) ** 2
    b_stack, b_pair = float(l_stack.mean()), float(l_pair.mean())
    before = float(incumbent) if incumbent is not None else b_pair
    improvement, d = before - b_stack, l_pair - l_stack   # d > 0 = stacker better than pair
    dm = diebold_mariano(d, games); p_defl = deflated_p(float(dm.p_value), k)  # noqa: E702
    verdict = "AHEAD" if (improvement >= BAR and dm.ci95[0] > 0.0 and p_defl < 0.05) else "BEHIND"
    ess = effective_sample_size(pd.DataFrame({"game": games, "loss_differential": d}))
    g_idx, ok = [i for i in idxs if guard is not None and _finite(guard[i])], np.isfinite(M).all(axis=1)
    pbo_res = cscv_pbo(np.column_stack([M[ok], p_unif[ok], p_stack[ok]]), y[ok].astype(int))
    arm_b = {n: {"brier": brier(M[np.isfinite(M[:, j]), j], y[np.isfinite(M[:, j])]), "n": int(np.isfinite(M[:, j]).sum())} for j, n in enumerate(names)}
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "sport": sport, "prereg": str(prereg_path),
        "prereg_sha256": seal, "ledger_row": dict(row), "k_at_launch": k, "bar_improvement": BAR,
        "incumbent_paired_all_ticks": before, "arms": names, "fallback": fallback, "pair_arm": pair,
        "n_scored_ticks": len(idxs), "n_scored_games": len(set(games)),
        "dropped_detail": dropped_detail or {"n_corpus_ticks": len(ticks), "n_dropped": len(ticks) - len(idxs)},
        "brier": {"stacker": b_stack, "pair_leakfree": b_pair, "uniform": float(brier(p_unif, y)),
                  "guard_only": brier([float(guard[i]) for i in g_idx], [y_all[i] for i in g_idx]) if g_idx else None,
                  "guard_n": len(g_idx), "per_arm": arm_b},
        "improvement_vs_incumbent": improvement, "improvement_vs_pair_leakfree": b_pair - b_stack,
        "dm": {"stat": float(dm.dm_stat), "p_raw": float(dm.p_value), "ci95": [float(dm.ci95[0]), float(dm.ci95[1])],
               "n_clusters": int(dm.n_clusters)}, "deflated_p": float(p_defl), "verdict": verdict,
        "pbo": {"pbo": float(pbo_res.pbo), "n_obs": int(pbo_res.n_obs), "n_splits": int(pbo_res.n_splits),
                "configs": names + ["uniform", "stacker"]},
        "ess_scored_predictor_vs_pair": {kk: float(vv) for kk, vv in ess.items()},
        "min_corpora_eff_at_launch_k": int(min_corpora_eff(1, k)), "single_window": True, "folds": folds,
        "per_tick_series": str(series_path) if series_path else None}
    if series_path:
        Path(series_path).parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"tick_index": idxs, "game": games, "timestamp": [str(ticks[i]["timestamp"]) for i in idxs],
                      "regime": [regimes[i] for i in idxs], "y": y, "stacker": p_stack, "pair_leakfree": p_pair,
                      "uniform": p_unif, "raw_model": M[:, names.index("raw_model")]}).to_csv(series_path, index=False)
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(json.dumps(result, indent=1, sort_keys=True,
                                             default=lambda o: o.item() if hasattr(o, "item") else str(o)), "ascii")
    return result

def main() -> int:
    """The REAL S06 charged trial (the only ledger charge tonight). Main repo only."""
    from scripts.platformkit import hedge_trial_arms as A
    from scripts.platformkit.ingame_replay_scoreboard import discover_store
    seal = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    ticks, features = A.load_corpus(discover_store(REPO / "data" / "cache"), "mlb")  # data prep only before the charge
    raw: Series = [float(t["model_prob"]) for t in ticks]
    e4o, e2o = A.e4_blend_series(ticks, features), A.e2_regime_series(ticks)
    e1 = A.e1_offset_series(ticks, features, 300)
    e4g, e2g, guard = e4_gd_series(ticks, features), e2_gd_series(ticks), e4_gd_series(ticks, features, "arm_a_prob")
    arms: Dict[str, Series] = {"raw_model": raw, "e4_blend": e4g, "e1_offset": e1, "e2_regime": e2g}
    hedge_e4 = A.hedge_series(ticks, {"e4_blend": e4o}, 371)
    scored = [i for i, t in enumerate(ticks) if _finite(hedge_e4[i]) and _finite(t.get("market_prob"))]
    assert (len(scored), len({str(ticks[i]["game"]) for i in scored})) == (47104, 158), "denominator drift"
    hall = {"raw_model": raw, "e4_blend": e4o, "e1_offset": e1, "e2_regime": e2o}
    hcfg = {n: A.hedge_series(ticks, {n: s}, 371) for n, s in hall.items()}
    hcfg["uniform"] = A.hedge_series(ticks, hall, 10 ** 9)
    for t_r in (100, 371, 1000): hcfg["hedge_T%d" % t_r] = A.hedge_series(ticks, hall, t_r)  # noqa: E701
    order = sorted(range(len(ticks)), key=lambda i: (str(ticks[i]["timestamp"]), str(ticks[i]["game"]), i))
    inter = [i for i in order if all(_finite(s[i]) for s in hcfg.values())]
    e2i = [i for i in range(len(ticks)) if _finite(e2g[i]) and _finite(e2o[i]) and _finite(ticks[i].get("market_prob"))]
    repro = [("raw_model", raw, scored, 0.236682901513263), ("e4_gd", e4g, scored, 0.206785778212713),
             ("e1_offset", e1, inter, 0.281762477954033), ("e2_gd", e2g, e2i, 0.254350980569169)]
    first, scored_set = _first_dates(ticks), set(scored)
    burn, dropped = min(first.values()), [i for i in range(len(ticks)) if i not in scored_set]
    mkt = [i for i in dropped if _finite(ticks[i].get("market_prob"))]
    detail = {"n_corpus_ticks": len(ticks), "n_dropped": len(dropped), "no_market_prob": len(dropped) - len(mkt),
              "burn_in_first_date_game": int(sum(first[str(ticks[i]["game"])] == burn for i in mkt)),
              "e4_pairing_absent_other": int(sum(first[str(ticks[i]["game"])] != burn for i in mkt))}
    result = run_stacker_trial(
        ticks, arms, sport="mlb", ledger_path=LEDGER, prereg_sha256=seal, scored_idx=scored,
        guard=guard, repro=repro, incumbent=INCUMBENT, dropped_detail=detail,
        out_path=REPO / "data" / "cache" / "eval_gate" / "s06_stacker_trial_2026-09-03.json",
        series_path=REPO / "data" / "cache" / "eval_gate" / "s06_stacker_series_2026-09-03.csv")
    b = result["brier"]
    print("S06 %s | improvement_vs_incumbent %.6f | dm_ci95 %s | deflated_p %.6f | K %d" % (
        result["verdict"], result["improvement_vs_incumbent"], result["dm"]["ci95"],
        result["deflated_p"], result["k_at_launch"]))
    print("stacker %.15f | pair_leakfree %.15f | uniform %.6f | guard_only %s | pbo %.3f (n_obs %d)" % (
        b["stacker"], b["pair_leakfree"], b["uniform"], b["guard_only"],
        result["pbo"]["pbo"], result["pbo"]["n_obs"]))
    return 0

if __name__ == "__main__": raise SystemExit(main())  # noqa: E701
