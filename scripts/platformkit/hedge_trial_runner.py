"""ONE charged, pre-registered walk-forward trial of the Hedge combiner over the
real gap arms vs the locked bar. Calibration only (Brier); no edge/ROI language.

Prereg (sealed by SHA-256 at launch, embedded in the artifact):
  docs/research/organization-sprint/HEDGE_TRIAL_PREREG_2026-09-01.md
Harness modules wired, never re-implemented: hedge_combiner.evaluate, dm_test,
gap_effective_n, deflated_metrics, pbo.cscv_pbo, cpcv_engine.cpcv_evaluate,
backtest_runner._charge_ledger. ASCII only; <=300 LOC.
Per-file test: python -m pytest scripts/platformkit/test_hedge_trial_arms.py -q
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit import hedge_trial_arms as A
from scripts.platformkit.eval_gate.backtest_runner import _charge_ledger
from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.deflated_metrics import deflated_p
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.pbo import cscv_pbo
from scripts.platformkit.ingame import arm_registry, hedge_combiner as hc
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size
from scripts.platformkit.ingame_replay_scoreboard import discover_store

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "cache" / "eval_gate" / "backtest_fwer.jsonl"
OUT = REPO / "data" / "cache" / "eval_gate" / "hedge_trial_2026-09-01.json"
PREREG = REPO / "docs" / "research" / "organization-sprint" / "HEDGE_TRIAL_PREREG_2026-09-01.md"
SPEC = "scripts.platformkit.hedge_trial_runner:hedge_over_gap_arms"
LOCK = arm_registry.MEASURED_DELTA_BRIER_LOCK          # -0.0343 = market - model
BAR = arm_registry.MINIMUM_DELTA_BRIER_IMPROVEMENT    # +0.004, never moves
T_ROUNDS = {"mlb": 371, "soccer_intl": 68}            # pre-registered, not read off the corpus
PBO_T = {"mlb": (100, 371, 1000), "soccer_intl": (30, 68, 200)}
UNIFORM_T = 10 ** 9
E4_VARIANTS = {"e4_w0.5_d0.15": (0.5, 0.15), "e4_w2.0_d0.15": (2.0, 0.15),   # PBO-only configs,
               "e4_w1.0_d0.10": (1.0, 0.10), "e4_w1.0_d0.25": (1.0, 0.25)}   # pre-registered
_INNING = re.compile(r"inning=(\d+)")


def _finite(v: Any) -> bool:
    return v is not None and math.isfinite(float(v))


def _paired_index(ticks: Sequence[Mapping[str, Any]], hedge: A.Series) -> List[int]:
    return [i for i, t in enumerate(ticks) if _finite(hedge[i]) and _finite(t.get("market_prob"))]


def _losses(ticks: Sequence[Mapping[str, Any]], hedge: A.Series, idx: Sequence[int]) -> pd.DataFrame:
    rows = [{"game": str(ticks[i]["game"]), "y": float(ticks[i]["outcome"]),
             "hedge": float(hedge[i]), "raw": float(ticks[i]["model_prob"]),
             "market": float(ticks[i]["market_prob"]), "in_window": bool(ticks[i].get("in_window", True)),
             "month": str(ticks[i]["timestamp"])[5:7], "inning": _inning(ticks[i])} for i in idx]
    frame = pd.DataFrame(rows)
    for name in ("hedge", "raw", "market"):
        frame["loss_" + name] = (frame[name] - frame["y"]) ** 2
    return frame


def _inning(tick: Mapping[str, Any]) -> str:
    match = _INNING.search(str(tick.get("state_summary") or ""))
    if not match:
        return "unknown"
    inning = int(match.group(1))
    return "early_1_3" if inning <= 3 else "mid_4_6" if inning <= 6 else "late_7plus"


def _slice(frame: pd.DataFrame) -> Dict[str, Any]:
    return {"n_ticks": int(len(frame)), "n_games": int(frame["game"].nunique()),
            "hedge_brier": float(frame["loss_hedge"].mean()), "raw_brier": float(frame["loss_raw"].mean()),
            "market_brier": float(frame["loss_market"].mean()),
            "improvement_vs_raw": float((frame["loss_raw"] - frame["loss_hedge"]).mean()),
            "delta_hedge_vs_market": float((frame["loss_market"] - frame["loss_hedge"]).mean())}


def primary_stats(frame: pd.DataFrame, k_cum: int) -> Dict[str, Any]:
    diff = (frame["loss_raw"] - frame["loss_hedge"]).to_numpy()
    dm = diebold_mariano(diff, frame["game"].tolist())
    ess = effective_sample_size(pd.DataFrame({"game": frame["game"], "loss_differential": diff}))
    stats = {**_slice(frame), "delta_raw_vs_market": float((frame["loss_market"] - frame["loss_raw"]).mean()),
             "locked_delta_brier": LOCK, "bar_improvement": BAR,
             "delta_hedge_minus_lock": float((frame["loss_market"] - frame["loss_hedge"]).mean() - LOCK),
             "dm_ci95_improvement": [float(dm.ci95[0]), float(dm.ci95[1])], "dm_p_raw": float(dm.p_value),
             "dm_stat": float(dm.dm_stat), "n_clusters": int(dm.n_clusters),
             "deflated_p": float(deflated_p(float(dm.p_value), k_cum)), "k_cumulative": int(k_cum),
             "ess": {k: float(v) for k, v in ess.items()}}
    return stats


def verdict_of(stats: Mapping[str, Any]) -> str:
    ahead = (stats["improvement_vs_raw"] >= BAR and stats["dm_ci95_improvement"][0] > 0.0
             and stats["deflated_p"] < 0.05)
    return "AHEAD" if ahead else "BEHIND"


def regime_slices(frame: pd.DataFrame) -> Dict[str, Any]:
    out = {"all_ticks": _slice(frame), "in_window_ticks": _slice(frame[frame["in_window"]])}
    for column in ("inning", "month"):
        for key, group in frame.groupby(column, sort=True):
            out["%s=%s" % (column, key)] = _slice(group)
    return out


def pbo_block(ticks: Sequence[Mapping[str, Any]], arms: Mapping[str, A.Series], sport: str,
              mixtures: bool = True) -> Dict[str, Any]:
    configs: Dict[str, A.Series] = {name: A.hedge_series(ticks, {name: arms[name]}, T_ROUNDS[sport]) for name in arms}
    if mixtures:
        configs["uniform"] = A.hedge_series(ticks, arms, UNIFORM_T)
        for t in PBO_T[sport]:
            configs["hedge_T%d" % t] = A.hedge_series(ticks, arms, t)
    order = sorted(range(len(ticks)), key=lambda i: (str(ticks[i]["timestamp"]), str(ticks[i]["game"]), i))
    rows = [i for i in order if all(_finite(s[i]) for s in configs.values())]
    matrix = np.array([[float(configs[c][i]) for c in configs] for i in rows])
    result = cscv_pbo(matrix, [int(float(ticks[i]["outcome"])) for i in rows])
    return {"pbo": result.pbo, "n_splits": result.n_splits, "n_obs": result.n_obs, "s_blocks": result.s_blocks,
            "configs": list(configs), "config_brier": {c: A.brier(matrix[:, j], [float(ticks[i]["outcome"]) for i in rows])
                                                        for j, c in enumerate(configs)}}


def cpcv_block(ticks: Sequence[Mapping[str, Any]], arms: Mapping[str, A.Series], sport: str,
               names: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    states = A.game_states(ticks, arms)
    hedged = cpcv_evaluate(states, A.hedge_predictor(tuple(names or arms), T_ROUNDS[sport]))
    raw = cpcv_evaluate(states, A.raw_predictor)
    per_path: Dict[int, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for h, r in zip(hedged, raw):
        assert h["game_id"] == r["game_id"] and h["split_id"] == r["split_id"]
        path = per_path[h["split_id"]]
        path["hedge"].append((h["p_model"] - h["y"]) ** 2)
        path["raw"].append((r["p_model"] - r["y"]) ** 2)
        path["market"].append((h["p_close"] - h["y"]) ** 2)
        path["n_train"].append(h["n_train"])
    diffs = [float(np.mean(p["raw"]) - np.mean(p["hedge"])) for p in per_path.values()]
    return {"n_states": len(states), "n_paths": len(per_path),
            "paired_improvement_vs_raw_per_path": {"min": min(diffs), "median": float(np.median(diffs)),
                                                   "mean": float(np.mean(diffs)), "max": max(diffs)},
            "share_paths_hedge_better": float(np.mean([d > 0 for d in diffs])),
            "mean_hedge_brier": float(np.mean([np.mean(p["hedge"]) for p in per_path.values()])),
            "mean_market_brier": float(np.mean([np.mean(p["market"]) for p in per_path.values()])),
            "min_n_train": int(min(min(p["n_train"]) for p in per_path.values()))}


def e4_configs(ticks: Sequence[Mapping[str, Any]], features: pd.DataFrame,
               arms: Mapping[str, A.Series]) -> Dict[str, A.Series]:
    """Candidate-mode PBO matrix: raw, guard-only, e4 default, 4 pre-registered variants."""
    configs = {"raw_model": arms["raw_model"], "e4_guard_only": A.e4_blend_series(ticks, features, column="arm_a_prob"),
               "e4_blend": arms["e4_blend"]}
    for name, (w_max, max_dev) in E4_VARIANTS.items():
        configs[name] = A.e4_blend_series(ticks, features, w_max, max_dev)
    return configs


def run_sport(store: Path, sport: str, k_cum: int, bootstrap: int, max_estimators: int,
              charge, candidate: Optional[str] = None) -> Dict[str, Any]:
    """candidate=None: Hedge over S5's arm set. candidate='e4_blend': the single
    arm IS the scored series (K=1 Hedge, eta=0), compared paired against raw."""
    ticks, features = A.load_corpus(store, sport)
    dates = sorted(str(t["timestamp"])[:10] for t in ticks)
    corpus = {"store": str(store / sport), "n_ticks": len(ticks), "n_games": len({t["game"] for t in ticks}),
              "n_window_ticks": int(sum(bool(t.get("in_window")) for t in ticks)),
              "date_range": [dates[0], dates[-1]]}
    ledger_row = charge(dates[0], dates[-1]) if charge else None   # charged BEFORE any metric
    k_cum = int(ledger_row["k_cumulative"]) if ledger_row else k_cum
    arms = A.arm_series(ticks, features, sport, max_estimators, ("raw_model", candidate) if candidate else None)
    mix = {candidate: arms[candidate]} if candidate else arms
    coverage = {name: int(sum(_finite(v) for v in series)) for name, series in arms.items()}
    report = hc.evaluate(ticks, mix, T_ROUNDS[sport], bootstrap_iterations=bootstrap)
    hedge = A.hedge_series(ticks, mix, T_ROUNDS[sport])
    idx = _paired_index(ticks, hedge)
    frame = _losses(ticks, hedge, idx)
    extra: Dict[str, Any] = {}
    if candidate:
        configs = e4_configs(ticks, features, arms)
        guard = _losses(ticks, configs["e4_guard_only"], idx)
        extra = {"candidate": candidate, "decomposition": {
            "guard_only": _slice(guard), "signal_contribution_brier": float(
                guard["loss_hedge"].mean() - frame["loss_hedge"].mean())},
            "pbo": pbo_block(ticks, configs, sport, mixtures=False)}
    reported = report["slices"]["all_ticks"]["metrics"]["hedge_brier"]
    assert abs(float(frame["loss_hedge"].mean()) - reported) < 1e-9, "hedge series != evaluate() Brier"
    stats = primary_stats(frame, k_cum)
    return {"corpus": corpus, "ledger_row": ledger_row, "t_rounds": T_ROUNDS[sport], "arm_coverage_ticks": coverage,
            "combiner_report": {k: v for k, v in report.items() if k != "folds"},
            "combiner_render": hc.render(report), "primary": stats, "verdict": verdict_of(stats),
            "arm_registry_verdict_if_applied": arm_registry.verdict(
                stats["delta_hedge_vs_market"], stats["ess"]["n_eff"], 2, 0.0, True),
            "regime_slices": regime_slices(frame), **extra,
            "pbo": extra.get("pbo") or pbo_block(ticks, arms, sport),
            "cpcv": cpcv_block(ticks, arms, sport, tuple(mix))}


def _json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return None if not math.isfinite(float(obj)) else float(obj)
    if isinstance(obj, (np.integer, np.bool_)):
        return obj.item()
    return obj


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Charged Hedge-over-gap-arms trial (calibration only).")
    parser.add_argument("--cache-root", type=Path, default=REPO / "data" / "cache")
    parser.add_argument("--prereg", type=Path, default=PREREG)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--sports", default="mlb,soccer_intl")
    parser.add_argument("--bootstrap-iterations", type=int, default=300)
    parser.add_argument("--max-estimators", type=int, default=300)
    parser.add_argument("--candidate", default=None, help="single-arm mode, e.g. e4_blend (E4 promotion trial)")
    parser.add_argument("--spec", default=SPEC, help="ledger predictor spec for the charge")
    args = parser.parse_args(argv)
    seal = hashlib.sha256(args.prereg.read_bytes()).hexdigest()
    store = discover_store(args.cache_root)
    if store is None:
        raise SystemExit("NOT_TESTABLE: no tick store under %s" % args.cache_root)
    charge = lambda start, end: _charge_ledger(LEDGER, args.spec, "mlb", start, end)  # noqa: E731
    result: Dict[str, Any] = {"generated_at": datetime.now(timezone.utc).isoformat(), "prereg": str(args.prereg),
                              "prereg_sha256": seal, "lock": LOCK, "bar": BAR, "corpora": {},
                              "candidate": args.candidate, "ledger_spec": args.spec}
    k_cum = 0
    for sport in args.sports.split(","):
        block = run_sport(store, sport, k_cum, args.bootstrap_iterations, args.max_estimators,
                          charge if sport == "mlb" else None, args.candidate)
        k_cum = block["primary"]["k_cumulative"]
        result["corpora"][sport] = block
        print("%s | VERDICT %s | improvement %.6f | dm_ci95 %s | deflated_p %.4f | ess %.1f | pbo %.3f" % (
            sport, block["verdict"], block["primary"]["improvement_vs_raw"],
            block["primary"]["dm_ci95_improvement"], block["primary"]["deflated_p"],
            block["primary"]["ess"]["n_eff"], block["pbo"]["pbo"]))
        print(block["combiner_render"])
    result["verdict"] = result["corpora"]["mlb"]["verdict"] if "mlb" in result["corpora"] else "NOT_TESTABLE"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(_json(result), indent=1, sort_keys=True), encoding="ascii")
    print("ARTIFACT %s | PREREG_SHA256 %s" % (args.out, seal))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
