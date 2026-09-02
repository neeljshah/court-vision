"""scripts.platformkit.eval_gate.s58_clamp_family_trial -- S58 in-game trial A: the MLB
market-anchor CLAMP family (9 (w_max, max_abs_deviation) configs) chosen INSIDE the folds.

Per outer game-first-date fold the config is picked by inner cpcv_evaluate over the train
games only (purged, 1-day embargo; Q4), then the test games take that config's OWN outer
game-first-date walk-forward value (gap_blend_arm._walk_forward, the S36 leak-free variant).
The spliced series is scored ONCE against the incumbent e4_gd = CONFIGS[0]. SEAL -> CHARGE
-> reproduce -> compute (Q1/Q2); one charge for the whole family. Family `ingame_mlb_clamp`
is NOT in the frozen FWER partition (labelled). Calibration language only. ASCII.
Prereg: docs/evidence/harness/S58_TRIALA_PREREG_2026-09-03.md.
Per-file test: python -m pytest tests/platformkit/eval_gate/test_s58_clamp_family_trial.py -q
"""
from __future__ import annotations

import hashlib, json, math
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.combo.fwer_budget import min_corpora_eff
from scripts.platformkit.eval_gate.backtest_runner import _charge_ledger
from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.family_bars import dual_bar_verdict, render_bars
from scripts.platformkit.eval_gate.pbo import cscv_pbo
from scripts.platformkit.eval_gate.stacker import _finite, _first_dates, brier
from scripts.platformkit.ingame import gap_blend_arm as B
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size

REPO = Path(__file__).resolve().parents[3]
LEDGER = REPO / "data" / "cache" / "eval_gate" / "backtest_fwer.jsonl"
PREREG = REPO / "docs" / "evidence" / "harness" / "S58_TRIALA_PREREG_2026-09-03.md"
PREREG_SHA256 = "f93c07be124201d1b45e3ad1fd6231b8dd03da86a6abb48ef3089041fa3bcbbf"  # sealed first, 9c88ea7e8
SPEC_ID = "scripts.platformkit.eval_gate.s58_clamp_family_trial:mlb_clamp_family_v1"
FAMILY, TIER, START, END = "ingame_mlb_clamp", "T2", "2026-06-28", "2026-07-12"
BAR, ALPHA = 0.004, 0.05                       # never move (Q3)
CONFIGS = [(1.0, 0.15), (0.5, 0.10), (1.0, 0.10), (2.0, 0.10), (0.5, 0.15), (2.0, 0.15),
           (0.5, 0.25), (1.0, 0.25), (2.0, 0.25)]  # (w_max, max_abs_deviation); [0] = incumbent
SCORED = (47104, 158)                          # asserted BEFORE the charge
REPRO_INCUMBENT = 0.206785778212713            # e4_gd on the 47,104 scored ticks (S06/S43/S58-1)
MIN_TRAIN, MIN_STAMPS = 1000, 8
RECHARGE_BLOCKED = True                        # S72: instrument repaired after the charge; re-prereg first
COLS = ("model_prob", "market_prob", "signal", "outcome")
Series = List[Optional[float]]


def config_name(c) -> str:
    return "e4_w%.1f_d%.2f" % (float(c[0]), float(c[1]))


def signal_frame(ticks, features: pd.DataFrame) -> pd.DataFrame:
    """gap_blend_arm frame with GAME-FIRST-DATE `date` and `_row_id` (stacker.e4_gd_series)."""
    first = _first_dates(ticks)
    signal = features.set_index(["game", "timestamp"])["score_diff"].to_dict()
    keep = [t for t in ticks if pd.notna(signal.get((t["game"], t["timestamp"])))]
    rows = [{**t, "state_signal": float(signal[(t["game"], t["timestamp"])]), "game_date": first[str(t["game"])]} for t in keep]
    frame = B._frame(rows); assert len(frame) == len(rows), "gap_blend_arm._frame dropped rows"  # noqa: E702
    frame["_row_id"] = [int(t["_row_id"]) for t in rows]
    frame["timestamp"] = [str(t["timestamp"]) for t in rows]
    for d in sorted(frame["date"].unique())[1:]:
        assert not (set(frame[frame["date"] < d]["game"]) & set(frame[frame["date"] == d]["game"])), "fold not game-disjoint"
    return frame


def outer_series(frame: pd.DataFrame, n: int, w_max: float, max_dev: float) -> Series:
    """One config's outer game-first-date walk-forward (arm_b_prob), by _row_id."""
    scored, _ = B._walk_forward(frame, w_max, max_dev)
    out: Series = [None] * n
    for rid, v in zip(scored["_row_id"], scored["arm_b_prob"]):
        out[int(rid)] = float(v) if math.isfinite(float(v)) else None
    return out


def game_states(frame: pd.DataFrame, games: Sequence[str]) -> List[dict]:
    """cpcv states, one per train game: every tick row as features; vintage = last tick."""
    states = []
    for gid, g in frame[frame["game"].isin(list(games))].groupby("game", sort=False):
        g = g.sort_values("timestamp")
        last = datetime.fromisoformat(str(g["timestamp"].iloc[-1]).replace("Z", "+00:00"))
        code = str(gid).rsplit("-", 1)[-1][-6:]
        states.append({"game_id": str(gid), "state_ts": (last + timedelta(seconds=1)).isoformat(),
                       "home": code[3:], "away": code[:3], "outcome": int(float(g["outcome"].iloc[0])),
                       "features": {k: g[k].to_numpy(dtype=float) for k in COLS},
                       "feature_avail": {k: last.isoformat() for k in COLS}})
    return sorted(states, key=lambda s: s["state_ts"])


def _predictor(w_max: float, max_dev: float):
    """S72: a test state whose PURGED train set is empty or under MIN_TRAIN is scored as
    MISSING for this state only (recorded in `skipped`), never raised -- one such state used
    to fail the whole config for the whole outer fold. The 0.5 handed back satisfies
    cpcv_evaluate's [0,1] contract for a record that is never scored (only `stash` is)."""
    def predictor(train: List[dict], test: dict, _select_inside: bool) -> float:
        key = frozenset(s["game_id"] for s in train)
        if key not in predictor.fits:
            df = pd.DataFrame({k: np.concatenate([s["features"][k] for s in train]) for k in COLS}) if train else None
            predictor.fits[key] = (None if df is None or len(df) < MIN_TRAIN or df["outcome"].nunique() < 2
                                   else B._fit_weight(df, w_max, max_dev))
        fit = predictor.fits[key]
        if fit is None:
            predictor.skipped.append(test["game_id"]); return 0.5  # noqa: E702
        f = test["features"]
        p = B._guarded_prob(f["model_prob"], f["market_prob"], f["signal"], fit, max_dev)
        predictor.stash.append((float(((p - f["outcome"]) ** 2).sum()), int(len(p)), test["game_id"]))
        return float(np.clip(p[len(p) // 2], 0.0, 1.0))
    predictor.fits, predictor.stash, predictor.skipped = {}, [], []
    return predictor


def inner_score(states: List[dict], cfg) -> dict:
    """Tick-weighted OOF loss of one config over the purged inner CPCV paths (pure)."""
    pred = _predictor(*cfg)
    try:
        recs = cpcv_evaluate(states, pred, n_groups=8, n_test_groups=2, embargo_days=1)
    except Exception as exc:  # infeasible fit or path -> caller falls back to the incumbent
        return {"config": config_name(cfg), "status": "FAILED", "error": str(exc)[:200]}
    n_empty = len(pred.skipped)
    if not pred.stash:                       # S72: no non-empty inner test state at all
        return {"config": config_name(cfg), "status": "NO_SCORED_STATE", "n_states_empty": n_empty,
                "n_states_scored": 0, "error": "every inner test state had a purged-empty or short train set"}
    loss, n = sum(s for s, _, _ in pred.stash), sum(k for _, k, _ in pred.stash)
    return {"config": config_name(cfg), "status": "OK", "score": loss / n, "n_ticks": n,
            "n_states_scored": len(pred.stash), "n_states_empty": n_empty,
            "n_paths": len({r["split_id"] for r in recs}),
            "n_fold_fits": sum(1 for v in pred.fits.values() if v is not None)}


def _task(args):
    date, states, cfg = args
    return date, config_name(cfg), inner_score(states, cfg)


def select_configs(frame: pd.DataFrame, dates: Sequence[str], *, workers: int = 1) -> Dict[str, dict]:
    """Per outer date: inner cpcv score of every config over the train games only -> chosen."""
    first_by_game = frame.groupby("game")["date"].min().to_dict()
    tasks, by_date = [], {}
    for d in dates:
        train_games = sorted(g for g, fd in first_by_game.items() if fd < d)
        states = game_states(frame, train_games)
        n_train = int(frame["game"].isin(train_games).sum())
        feasible = n_train >= MIN_TRAIN and len({s["state_ts"] for s in states}) >= MIN_STAMPS
        by_date[d] = {"date": d, "n_train_games": len(train_games), "n_train_ticks": n_train,
                      "n_train_stamps": len({s["state_ts"] for s in states}), "feasible": feasible, "inner": {}}
        if feasible: tasks += [(d, states, c) for c in CONFIGS]  # noqa: E701
    results = list(ProcessPoolExecutor(max_workers=workers).map(_task, tasks)) if workers > 1 else [_task(t) for t in tasks]
    for d, name, res in results: by_date[d]["inner"][name] = res  # noqa: E701
    for d, rec in by_date.items():
        ok = [(rec["inner"][config_name(c)]["score"], i) for i, c in enumerate(CONFIGS)
              if rec["inner"].get(config_name(c), {}).get("status") == "OK"]
        best = min(ok)[1] if ok else 0                    # ties -> earliest in CONFIGS (incumbent first)
        # S72: the fallback clause fires ONLY when no config has a valid inner score.
        if ok: reason = "%d/%d configs scored on non-empty purged inner test states (%d empty)" % (
            len(ok), len(CONFIGS), int(rec["inner"][config_name(CONFIGS[best])].get("n_states_empty", 0)))  # noqa: E701
        elif not rec["feasible"]: reason = "outer fold infeasible: %d train ticks / %d distinct state stamps" % (
            rec["n_train_ticks"], rec["n_train_stamps"])  # noqa: E701
        else: reason = "no config scored: every inner test state had a purged-empty or short train set"  # noqa: E701
        rec.update({"selected": config_name(CONFIGS[best]), "selected_idx": best, "fallback": not ok,
                    "inner_selection": "operative" if ok else "fallback", "inner_selection_reason": reason,
                    "n_configs_scored": len(ok)})
    return by_date


def splice(frame: pd.DataFrame, per_config: Dict[str, Series], selection: Dict[str, dict], n: int) -> Series:
    out: Series = [None] * n
    for d, rec in selection.items():
        s = per_config[rec["selected"]]
        for rid in frame.loc[frame["date"] == d, "_row_id"]: out[int(rid)] = s[int(rid)]  # noqa: E701
    return out


def score(ticks, cand: Series, inc: Series, idxs: Sequence[int], k: int, *, per_config: Dict[str, Series]) -> dict:
    """Paired per-tick comparison on `idxs`; d > 0 means the candidate is better. Pure."""
    idxs = sorted(idxs, key=lambda i: (str(ticks[i]["timestamp"]), str(ticks[i]["game"]), i))
    games = [str(ticks[i]["game"]) for i in idxs]
    y = np.array([float(ticks[i]["outcome"]) for i in idxs])
    p_c, p_i = (np.array([float(s[i]) for i in idxs]) for s in (cand, inc))
    l_c, l_i = (p_c - y) ** 2, (p_i - y) ** 2
    b_c, b_i, d = float(l_c.mean()), float(l_i.mean()), l_i - l_c
    dm = diebold_mariano(d.tolist(), games); raw_p = float(dm.p_value)  # noqa: E702
    mat, cfg_rows, fam_p = [], {}, []
    for name, s in per_config.items():
        col = np.array([float(s[i]) for i in idxs]); mat.append(col)  # noqa: E702
        dd = l_i - (col - y) ** 2
        if float(np.abs(dd).max()) == 0.0: p_cfg, ci, stat = 1.0, [0.0, 0.0], 0.0  # the incumbent vs itself
        else:
            r = diebold_mariano(dd.tolist(), games); p_cfg, ci, stat = float(r.p_value), [float(r.ci95[0]), float(r.ci95[1])], float(r.dm_stat)  # noqa: E702
        cfg_rows[name] = {"brier": float(((col - y) ** 2).mean()), "improvement_vs_incumbent": b_i - float(((col - y) ** 2).mean()),
                          "dm_p_raw": p_cfg, "dm_ci95": ci, "dm_stat": stat}
        fam_p.append(p_cfg)
    bars = dual_bar_verdict(raw_p, k, fam_p + [raw_p], alpha=ALPHA, family=None)
    bars["bars_line"], bars["family"] = render_bars(bars), FAMILY + " (NOT frozen; 9 configs + the candidate composite)"
    improvement = b_i - b_c
    conds = {"improvement_ge_bar": improvement >= BAR, "dm_ci_excludes_0_favouring_candidate": dm.ci95[0] > 0.0,
             "deflated_p_lt_alpha": bool(bars["global_pass"]), "family_bar_pass": bool(bars["family_pass"])}
    verdict = "AHEAD" if all(conds.values()) else ("BEHIND" if b_c > b_i else "NULL")
    ess = effective_sample_size(pd.DataFrame({"game": games, "loss_differential": d}))
    pbo = cscv_pbo(np.column_stack(mat), y.astype(int))
    market = np.array([float(ticks[i]["market_prob"]) for i in idxs])
    return {"n_ticks": len(idxs), "n_games": len(set(games)), "k_at_launch": int(k),
            "brier": {"candidate_inner_selected": b_c, "incumbent_e4_gd": b_i, "market": float(((market - y) ** 2).mean())},
            "improvement": improvement, "bar_improvement": BAR, "conditions": conds, "verdict": verdict,
            "dm": {"stat": float(dm.dm_stat), "p_raw": raw_p, "ci95": [float(dm.ci95[0]), float(dm.ci95[1])], "n_clusters": int(dm.n_clusters)},
            "deflated_p": float(bars["deflated_p"]), "bars": bars, "per_config_outer": cfg_rows,
            "pbo": {"pbo": float(pbo.pbo), "n_obs": int(pbo.n_obs), "n_splits": int(pbo.n_splits), "configs": list(per_config)},
            "ess_scored_differential": {kk: float(vv) for kk, vv in ess.items()},
            "min_corpora_eff_at_launch_k": int(min_corpora_eff(1, k)), "single_window": True}


def run_trial(ticks, frame: pd.DataFrame, idxs: Sequence[int], *, ledger_path: Path, prereg_path: Path = PREREG,
              prereg_sha256: str = PREREG_SHA256, repro_incumbent: Optional[float] = REPRO_INCUMBENT,
              workers: int = 1, out_path=None, series_path=None, folds_path=None) -> dict:
    """SEAL -> CHARGE (one row, S13 fields) -> reproduce the incumbent -> select inside -> score."""
    seal = hashlib.sha256(Path(prereg_path).read_bytes()).hexdigest()
    if seal != prereg_sha256: raise AssertionError("prereg sha mismatch: %s != %s" % (seal, prereg_sha256))  # noqa: E701
    row = _charge_ledger(Path(ledger_path), SPEC_ID, "mlb", START, END, family=FAMILY, tier=TIER,
                         hypothesis_hash=hashlib.sha256((SPEC_ID + json.dumps(CONFIGS)).encode()).hexdigest(), prereg_sha256=seal)
    k = int(row["k_cumulative"])                                       # the ONLY K used
    n = len(ticks)
    per_config = {config_name(c): outer_series(frame, n, *c) for c in CONFIGS}
    inc = per_config[config_name(CONFIGS[0])]
    y = [float(ticks[i]["outcome"]) for i in idxs]
    got = brier([float(inc[i]) for i in idxs], y)
    if repro_incumbent is not None:
        assert abs(got - repro_incumbent) < 1e-9, "ARM REPRODUCTION FAILED incumbent: %.15f vs %.15f" % (got, repro_incumbent)
    for name, s in per_config.items():
        assert all(_finite(s[i]) for i in idxs), "config %s not finite on the scored set" % name
    dates = sorted(frame["date"].unique())[1:]
    selection = select_configs(frame, dates, workers=workers)
    cand = splice(frame, per_config, selection, n)
    assert all(_finite(cand[i]) for i in idxs), "spliced candidate not finite on the scored set"
    res = score(ticks, cand, inc, idxs, k, per_config=per_config)
    res.update({"generated_at": datetime.now(timezone.utc).isoformat(), "prereg": str(prereg_path), "prereg_sha256": seal,
                "ledger_row": dict(row), "spec_id": SPEC_ID, "family": FAMILY, "tier": TIER, "configs": [config_name(c) for c in CONFIGS],
                "incumbent_reproduction": {"target": repro_incumbent, "got": got, "n": len(idxs)},
                "selection": {d: {kk: v for kk, v in r.items() if kk != "inner"} for d, r in selection.items()},
                "per_tick_series": str(series_path) if series_path else None, "folds": str(folds_path) if folds_path else None})
    if folds_path: Path(folds_path).write_text(json.dumps({"prereg_sha256": seal, "folds": selection}, indent=1, sort_keys=True, default=str), "ascii")  # noqa: E701
    if series_path:
        i2 = sorted(idxs, key=lambda i: (str(ticks[i]["timestamp"]), str(ticks[i]["game"]), i))
        sel_by_date = {d: r["selected"] for d, r in selection.items()}; date_by_rid = dict(zip(frame["_row_id"].astype(int), frame["date"]))  # noqa: E702
        pd.DataFrame({"tick_index": i2, "game": [str(ticks[i]["game"]) for i in i2], "timestamp": [str(ticks[i]["timestamp"]) for i in i2],
                      "y": [float(ticks[i]["outcome"]) for i in i2], "candidate": [float(cand[i]) for i in i2],
                      "incumbent_e4_gd": [float(inc[i]) for i in i2], "market": [float(ticks[i]["market_prob"]) for i in i2],
                      "selected_config": [sel_by_date[date_by_rid[i]] for i in i2]}).to_csv(series_path, index=False)
    if out_path: Path(out_path).write_text(json.dumps(res, indent=1, sort_keys=True, default=lambda o: o.item() if hasattr(o, "item") else str(o)), "ascii")  # noqa: E701
    return res


def main() -> int:
    """The REAL charged trial A (main repo, canonical ledger). Pre-charge work is counts-only.

    BLOCKED since S72: the inner runner was repaired after the 2026-09-03 charge, so PREREG_SHA256
    seals a prereg that describes the PRE-repair instrument. Re-running would charge a different
    candidate under a stale seal (Q1). The re-prereg + re-charge is window 2 (>= 30 games) --
    docs/evidence/harness/S72_clamp_instrument_2026-09-03.md.
    """
    assert not RECHARGE_BLOCKED, ("S72: re-prereg + re-charge required before this trial runs again "
                                  "(see docs/evidence/harness/S72_clamp_instrument_2026-09-03.md)")
    from scripts.platformkit import hedge_trial_arms as A
    from scripts.platformkit.eval_gate.stacker import e4_gd_series
    from scripts.platformkit.ingame_replay_scoreboard import discover_store
    ticks, features = A.load_corpus(discover_store(REPO / "data" / "cache"), "mlb")
    frame = signal_frame(ticks, features)
    e4g = e4_gd_series(ticks, features)
    idxs = [i for i, t in enumerate(ticks) if _finite(e4g[i]) and _finite(t.get("market_prob"))]
    assert (len(idxs), len({str(ticks[i]["game"]) for i in idxs})) == SCORED, "denominator drift"
    inc0 = outer_series(frame, len(ticks), *CONFIGS[0])
    assert all(inc0[i] == e4g[i] for i in idxs), "CONFIGS[0] is not the stacker e4_gd builder"
    out = REPO / "data" / "cache" / "eval_gate"
    res = run_trial(ticks, frame, idxs, ledger_path=LEDGER, workers=6,
                    out_path=out / "s58_trialA_clamp_family_2026-09-03.json", series_path=out / "s58_trialA_clamp_family_series_2026-09-03.csv",
                    folds_path=out / "s58_trialA_clamp_family_folds_2026-09-03.json")
    b = res["brier"]
    print("S58 trialA %s | candidate %.15f vs incumbent %.15f | improvement %.6f | dm_ci95 %s | deflated_p %.6g | K %d" % (
        res["verdict"], b["candidate_inner_selected"], b["incumbent_e4_gd"], res["improvement"], res["dm"]["ci95"], res["deflated_p"], res["k_at_launch"]))
    print(res["bars"]["bars_line"]); print("pbo %.3f n_obs %d | ess %s" % (res["pbo"]["pbo"], res["pbo"]["n_obs"], res["ess_scored_differential"]))
    for d, r in res["selection"].items(): print("  %s -> %s%s" % (d, r["selected"], " (fallback)" if r["fallback"] else ""))
    for name, r in res["per_config_outer"].items(): print("  %-16s brier %.6f impr %+.6f p %.3g" % (name, r["brier"], r["improvement_vs_incumbent"], r["dm_p_raw"]))
    return 0


if __name__ == "__main__": raise SystemExit(main())  # noqa: E701
