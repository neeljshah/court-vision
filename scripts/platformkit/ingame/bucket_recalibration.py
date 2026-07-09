"""scripts.platformkit.ingame.bucket_recalibration -- walk-forward state-bucket
recalibration for the MLB in-game model (closes the MODEL_BEHIND gap measured in
state_bucket_benchmark.py: pooled Brier 0.2295 vs market 0.1898, worst in blowout
states e.g. late|leading_big model 0.294 vs market 0.146).

REUSE via import, never copy-paste: discover_grade_files, live_grade._load_pairs,
MlbOutcomeResolver, sb's _parse_state_summary/margin_bucket/phase_bucket/
_cluster_bootstrap_ci, eval_gate.scoring, calibration_ladder._logit. This module
only ADDS per-tick date + numeric margin (not in sb's public loader) + 2 specs.

SPEC (K=2, declared up front): (a) phase_platt -- per-phase Platt on
logit(model_prob), 2 params/phase. (b) phase_platt_margin -- (a) + one joint
logistic on [logit(model_prob), margin*phase_dummies] (5 params) so blowout
states can get pulled toward 0/1 like the market. Winner = lower pooled
eval-set (post-burn-in) recalibrated Brier; both reported honestly.

WALK-FORWARD by game DATE (first tick's capture ts): fit on dates < t, apply to
date t. First 20% of dates = burn-in, raw passthrough, excluded from the verdict.

HONESTY: calibration only, edge_claimed always False. Params written to
data/cache/ingame/mlb_bucket_recalib_params.json ONLY if verdict_vs_raw ==
IMPROVED (no orphan artifact for a null result). NO LIVE WIRING here.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no network at import;
never writes data/registry/; never flips a flag; ingame_grade is READ-ONLY.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_bucket_recalibration.py -q
"""
from __future__ import annotations

import json, logging, math, os
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np
from sklearn.linear_model import LogisticRegression
from scripts.platformkit.eval_gate.scoring import brier, ece, log_loss
from scripts.platformkit.calibration_ladder import _logit
from scripts.platformkit.ingame import live_grade as lg, state_bucket_benchmark as sb
from scripts.platformkit.ingame.ingame_clv_aggregate import discover_grade_files
from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver

logger = logging.getLogger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "mlb_bucket_recalibration.json"
DEFAULT_PARAMS_PATH = _REPO_ROOT / "data" / "cache" / "ingame" / "mlb_bucket_recalib_params.json"
BURN_IN_FRAC = 0.2
MIN_FIT_N = 50          # honest floor for a phase-scoped (or joint) Platt fit
PHASES: Tuple[str, ...] = ("early", "mid", "late", "unknown")
# -- loading: reuse sb's parsing/bucketing primitives, add date + numeric margin --
def load_recal_ticks(grade_dir: Optional[Path] = None,
                     resolver: Optional[MlbOutcomeResolver] = None) -> List[Dict[str, Any]]:
    """sb's resolvable+bucketable ticks plus date/phase/margin. Never raises."""
    res = resolver if resolver is not None else MlbOutcomeResolver()
    files = discover_grade_files(grade_dir, sport="mlb")
    ticks: List[Dict[str, Any]] = []
    for path in files:
        try:
            pairs = lg._load_pairs(path)
        except Exception as exc:  # noqa: BLE001 -- one bad file is not a crash
            logger.debug("load_recal_ticks: %s failed: %s", path, exc)
            continue
        if not pairs:
            continue
        gid = str(pairs[0].get("game_id", path.stem))
        home_win = res.home_win(gid)
        if home_win is None:
            continue
        game_date = str(pairs[0].get("ts", ""))[:10]
        for r in pairs:
            fields = sb._parse_state_summary(r.get("state_summary"))
            if "home_score" not in fields or "away_score" not in fields:
                continue
            phase = sb.phase_bucket(fields.get("inning"))
            margin_b = sb.margin_bucket(fields["home_score"], fields["away_score"])
            ticks.append({
                "game_id": gid, "date": game_date, "phase": phase,
                "margin": fields["home_score"] - fields["away_score"],
                "bucket": "%s|%s" % (phase, margin_b),
                "model_prob": float(r["model_prob"]), "market_prob": float(r["market_prob"]),
                "outcome": float(home_win),
            })
    return ticks
# -- shared logistic fit/predict + spec (a) per-phase Platt, spec (b) + margin term --
def _fit_logistic(X: np.ndarray, y: np.ndarray, C: float) -> LogisticRegression:
    return LogisticRegression(C=C, solver="lbfgs", max_iter=500).fit(X, y)

def _predict1(lr: LogisticRegression, x_row: List[float]) -> float:
    return float(np.clip(lr.predict_proba(np.array([x_row]))[0, 1], 1e-9, 1 - 1e-9))

def _fit_phase_platt(train: List[Dict[str, Any]]) -> Dict[str, LogisticRegression]:
    models: Dict[str, LogisticRegression] = {}
    for ph in PHASES:
        sub = [t for t in train if t["phase"] == ph]
        y = np.array([t["outcome"] for t in sub])
        if len(sub) < MIN_FIT_N or len(np.unique(y)) < 2:
            continue
        X = _logit(np.array([t["model_prob"] for t in sub])).reshape(-1, 1)
        models[ph] = _fit_logistic(X, y, C=1e9)
    return models

def _apply_phase_platt(tick: Dict[str, Any], models: Dict[str, LogisticRegression]) -> float:
    lr = models.get(tick["phase"])
    if lr is None:
        return float(tick["model_prob"])
    return _predict1(lr, [float(_logit(np.array([tick["model_prob"]]))[0])])

def _features_margin(t: Dict[str, Any]) -> List[float]:
    lg_p = float(_logit(np.array([t["model_prob"]]))[0])
    return [lg_p] + [t["margin"] if t["phase"] == ph else 0.0 for ph in PHASES]

def _fit_phase_platt_margin(train: List[Dict[str, Any]]) -> Optional[LogisticRegression]:
    y = np.array([t["outcome"] for t in train])
    if len(train) < MIN_FIT_N or len(np.unique(y)) < 2:
        return None
    return _fit_logistic(np.array([_features_margin(t) for t in train]), y, C=1.0)  # 5 params, light ridge

def _apply_phase_platt_margin(tick: Dict[str, Any], lr: Optional[LogisticRegression]) -> float:
    if lr is None:
        return float(tick["model_prob"])
    return _predict1(lr, _features_margin(tick))

SPECS: Dict[str, Tuple[Callable, Callable]] = {
    "phase_platt": (_fit_phase_platt, _apply_phase_platt),
    "phase_platt_margin": (_fit_phase_platt_margin, _apply_phase_platt_margin)}
# -- walk-forward-by-date harness: fit on dates < t only, apply to date t --
def walk_forward_recal(ticks: List[Dict[str, Any]], spec_name: str,
                       burn_in_frac: float = BURN_IN_FRAC
                       ) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Leak-free: train set for date t never includes a tick whose date >= t."""
    fit_fn, apply_fn = SPECS[spec_name]
    by_date: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in ticks:
        by_date[t["date"]].append(t)
    dates = sorted(by_date)
    n_burn = max(1, math.ceil(burn_in_frac * len(dates))) if dates else 0
    burn_dates = set(dates[:n_burn])
    out: List[Dict[str, Any]] = []
    train: List[Dict[str, Any]] = []
    for d in dates:
        day_ticks = by_date[d]
        if d in burn_dates:
            for t in day_ticks:
                r = dict(t)
                r["recal_prob"], r["in_burn_in"] = float(t["model_prob"]), True
                out.append(r)
        else:
            model = fit_fn(train)
            for t in day_ticks:
                r = dict(t)
                r["recal_prob"], r["in_burn_in"] = apply_fn(t, model), False
                out.append(r)
        train.extend(day_ticks)  # today's ticks become fit history from tomorrow on
    return out, sorted(burn_dates)
# -- scoring: raw vs recal vs market, game-clustered bootstrap on both deltas --
def _per_game_delta(ticks: List[Dict[str, Any]], key_a: str, key_b: str) -> List[float]:
    """Per-game mean of (err_a - err_b); positive => b has the lower (better) error."""
    game_ids = sorted(set(t["game_id"] for t in ticks))
    out = []
    for gid in game_ids:
        gt = [t for t in ticks if t["game_id"] == gid]
        d = [(t[key_a] - t["outcome"]) ** 2 - (t[key_b] - t["outcome"]) ** 2 for t in gt]
        out.append(sum(d) / len(d))
    return out
def _verdict(ci: Tuple[float, float], n_games: int, min_games: int, eps: float,
            better: str, worse: str) -> str:
    if n_games < min_games:
        return "INSUFFICIENT_DATA"
    return better if ci[0] > eps else ("NO_CHANGE" if ci[1] >= -eps else worse)
def score_group(ticks: List[Dict[str, Any]], *,
               min_games: int = sb.MIN_GAMES, eps: float = sb.EPS_BRIER) -> Dict[str, Any]:
    """Model(raw)/recal/market metrics + game-clustered verdicts vs raw AND vs market."""
    game_ids = sorted(set(t["game_id"] for t in ticks))
    n_games = len(game_ids)
    y = [t["outcome"] for t in ticks]
    d_raw = _per_game_delta(ticks, "model_prob", "recal_prob")   # + => recal beats raw
    d_mkt = _per_game_delta(ticks, "market_prob", "recal_prob")  # + => recal beats market
    ci_raw, ci_mkt = sb._cluster_bootstrap_ci(d_raw), sb._cluster_bootstrap_ci(d_mkt)
    def _m(key: str) -> Optional[Dict[str, float]]:
        p = [t[key] for t in ticks]
        return {"brier": brier(p, y), "log_loss": log_loss(p, y), "ece": ece(p, y)} if ticks else None
    return {
        "n_ticks": len(ticks), "n_games": n_games,
        "raw": _m("model_prob"), "recal": _m("recal_prob"), "market": _m("market_prob"),
        "delta_vs_raw_mean": (sum(d_raw) / n_games) if n_games else 0.0,
        "delta_vs_raw_ci95": list(ci_raw),
        "verdict_vs_raw": _verdict(ci_raw, n_games, min_games, eps, "IMPROVED", "WORSE"),
        "delta_vs_market_mean": (sum(d_mkt) / n_games) if n_games else 0.0,
        "delta_vs_market_ci95": list(ci_mkt),
        "verdict_vs_market": _verdict(ci_mkt, n_games, min_games, eps, "MODEL_AHEAD", "MODEL_BEHIND"),
    }
def _serialize_params(spec_name: str, model: Any) -> Dict[str, Any]:
    """Only for the honestly-improved winner (build_recalibration gates the call)."""
    if spec_name == "phase_platt":
        return {"method": spec_name, "phase_models": {
            ph: {"coef": lr.coef_[0].tolist(), "intercept": float(lr.intercept_[0])}
            for ph, lr in model.items()}}
    return {"method": spec_name, "coef": model.coef_[0].tolist(), "intercept": float(model.intercept_[0]),
           "feature_order": ["logit_model_prob"] + ["margin_if_%s" % p for p in PHASES]}
# -- top-level build: run both specs, pick winner by pooled eval Brier --
def build_recalibration(grade_dir: Optional[Path] = None,
                        resolver: Optional[MlbOutcomeResolver] = None,
                        benchmark_generated_at: Optional[str] = None) -> Dict[str, Any]:
    ticks = load_recal_ticks(grade_dir, resolver)
    all_dates = sorted(set(t["date"] for t in ticks))
    spec_pooled: Dict[str, Dict[str, Any]] = {}
    spec_ticks: Dict[str, List[Dict[str, Any]]] = {}
    burn_in_dates: List[str] = []
    for name in SPECS:
        spec_ticks[name], burn_in_dates = walk_forward_recal(ticks, name)
        spec_pooled[name] = score_group([t for t in spec_ticks[name] if not t["in_burn_in"]])
    winner_name = min(SPECS, key=lambda n: (spec_pooled[n]["recal"] or {}).get("brier", float("inf")))
    winner_ticks = spec_ticks[winner_name]
    eval_ticks = [t for t in winner_ticks if not t["in_burn_in"]]
    burn_ticks = [t for t in winner_ticks if t["in_burn_in"]]
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in eval_ticks:
        buckets[t["bucket"]].append(t)
    bucket_rows = [dict(score_group(buckets[n]), bucket=n) for n in sorted(buckets)]
    winner_pooled = spec_pooled[winner_name]
    warrants_params = winner_pooled["verdict_vs_raw"] == "IMPROVED"
    params = None
    if warrants_params:
        fit_fn, _ = SPECS[winner_name]
        params = _serialize_params(winner_name, fit_fn(ticks))  # refit on ALL history for the shadow artifact
    sc = winner_pooled
    doc: Dict[str, Any] = {
        "generated_at": benchmark_generated_at or "unknown", "sport": "mlb",
        "baseline_source": "data/frontend/ops/mlb_state_bucket_benchmark.json",
        "spec_candidates": list(SPECS), "winner": winner_name, "burn_in_frac": BURN_IN_FRAC,
        "n_dates_total": len(all_dates), "n_dates_burn_in": len(burn_in_dates),
        "burn_in_dates": burn_in_dates,
        "burn_in_note": "first 20% of dates are raw passthrough (declared up front), excluded from the improvement verdict",
        "burn_in_raw_vs_market_pooled": score_group(burn_ticks) if burn_ticks else None,
        "method_comparison": {n: spec_pooled[n] for n in SPECS},
        "buckets": bucket_rows, "pooled": winner_pooled,
        "params_written": warrants_params, "params": params,
        "units": "probability (Brier/log-loss/ECE; no dollars)", "edge_claimed": False,
        "honest_note": ("Walk-forward state-bucket recalibration vs the LIVE market price, reusing "
                        "state_bucket_benchmark's resolver/bucketing. Calibration measurement only, "
                        "no dollar/ROI/edge claim; a remaining MODEL_BEHIND verdict vs market is "
                        "reported honestly, not papered over."),
        "calibration_scoreboard": {"per_sport": [{
            "sport": "mlb", "method": "mlb_bucket_recalibration_%s" % winner_name, "n": sc["n_ticks"],
            "baseline_brier": sc["market"]["brier"] if sc["market"] else None,
            "improved_brier": sc["recal"]["brier"] if sc["recal"] else None,
            "baseline_ece": sc["market"]["ece"] if sc["market"] else None,
            "improved_ece": sc["recal"]["ece"] if sc["recal"] else None,
        }]},
    }
    return doc

def write_recalibration(out_path: Optional[Path] = None,
                        params_path: Optional[Path] = None,
                        grade_dir: Optional[Path] = None,
                        resolver: Optional[MlbOutcomeResolver] = None,
                        history_path: Optional[Path] = None,
                        benchmark_path: Optional[Path] = None) -> Dict[str, Any]:
    """Build + atomically write the doc + params (iff warranted). generated_at comes
    from the benchmark JSON (stable across re-runs), never datetime.now()."""
    out = out_path or DEFAULT_OUT_PATH
    bench = benchmark_path or sb.DEFAULT_OUT_PATH
    gen_at = None
    if Path(bench).is_file():
        try:
            gen_at = json.loads(Path(bench).read_text(encoding="utf-8")).get("generated_at")
        except Exception as exc:  # noqa: BLE001 -- missing/bad benchmark is not fatal here
            logger.debug("write_recalibration: benchmark generated_at unavailable: %s", exc)
    doc = build_recalibration(grade_dir, resolver, benchmark_generated_at=gen_at)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(str(tmp), str(out))
    pp = params_path or DEFAULT_PARAMS_PATH
    if doc["params_written"]:
        pp.parent.mkdir(parents=True, exist_ok=True)
        ptmp = pp.with_suffix(pp.suffix + ".tmp")
        ptmp.write_text(json.dumps(doc["params"], indent=2, ensure_ascii=True), encoding="utf-8")
        os.replace(str(ptmp), str(pp))
        doc["params_path"] = str(pp)
    else:
        doc["params_path"] = None
    try:
        from scripts.platformkit import scoreboard_history as sh
        sh.append_rows(source_path=out, history_path=history_path)
    except Exception as exc:  # noqa: BLE001 -- history append is best-effort
        logger.debug("write_recalibration: scoreboard_history append skipped: %s", exc)
    return doc

if __name__ == "__main__":
    result = write_recalibration()
    print(json.dumps({"winner": result["winner"], "pooled": result["pooled"],
                      "params_written": result["params_written"],
                      "honest_note": result["honest_note"]}, indent=2, ensure_ascii=True))
__all__ = [
    "DEFAULT_OUT_PATH", "DEFAULT_PARAMS_PATH", "BURN_IN_FRAC", "MIN_FIT_N", "PHASES", "SPECS",
    "load_recal_ticks", "walk_forward_recal", "score_group",
    "build_recalibration", "write_recalibration",
]
