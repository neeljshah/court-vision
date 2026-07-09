"""scripts.platformkit.ingame.nba_checkpoint_benchmark -- NBA in-game MODEL-vs-MARKET
calibration benchmark on the Kalshi playoff-checkpoint corpus
(data/cache/inplay_odds/nba_checkpoints_2025_26_playoffs.parquet, READ-ONLY, 53 games,
2026 playoffs only).

MODEL: reuses the existing sport-generic repricer, not a new model. get_repricer("nba")
(scripts.platformkit.live_repricer) returns domains.basketball_nba.repricer.NBARepricer
(Gaussian score-anchor: final_margin ~ Normal(margin_now + mu_diff*rem_frac,
margin_sigma^2*rem_frac)). READ-ONLY caller -- no src/kernel/api edit.
model_tag = "domains_basketball_nba_repricer_gaussian_score_anchor".

PRIOR (leak-free, K=2, declared up front, no tuning on outcomes): neutral_p0_0.5 uses
NBARepricer defaults (mu_home=mu_away=113, pick'em); first_traded_pretip uses the
game's first traded tick's market_prob as p0 via the closed form
mu_diff=margin_sigma*Phi^-1(p0) (reproduces win_home==p0 exactly at elapsed=0/margin=0,
verified). price_checkpoint() is a PURE function of (p0, home_score, away_score,
period, game_clock_s) -- never reads outcome_home_win or any other row, so it cannot
leak future info. OT (period>=5) pushes elapsed past the repricer's hardcoded 48-min
length, collapsing rem_frac to 0 -> a degenerate current-score-sign price; grouped into
P4+OT so this known limitation is visible, not hidden.

DATA ARTIFACT: some post-settlement ticks are traded=False (reset/stale quotes, values
include 0.005/0.995/0.500 -- NOT one fixed value). Fix: EXCLUDE every traded=False row
from scoring (conservative, also removes the trailing reset), documented not silent.

BUCKETING: phase = P1-2 (period<=2) | P3 | P4+OT (period>=4); margin = close_le4
(|margin|<=4) | mid_5to10 (5-10) | blowout_11plus (11+).

METRICS: per bucket AND pooled, PER PRIOR VARIANT: model vs market Brier/log-loss/
ECE(10-bin) (kernel-backed, eval_gate.scoring) vs outcome_home_win, plus a
GAME-CLUSTERED bootstrap 95% CI on the paired per-game (market_brier-model_brier)
delta -> MODEL_AHEAD/MATCH/MODEL_BEHIND. n_games < MIN_GAMES -> INSUFFICIENT_DATA.

REPRESENTATIVENESS: 53 games, ALL 2026 playoffs -- no regular season; do not
generalize without a regular-season corpus. HONESTY (binding): calibration measurement
only; edge_claimed always False; no $/ROI field anywhere.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; no network at
import; never writes data/registry/; never flips a flag; never edits live_repricer.py /
domains/basketball_nba/repricer.py / eval_gate/scoring.py; parquet is READ-ONLY.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_nba_checkpoint_benchmark.py -q
"""
from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd
from scipy.stats import norm

from scripts.platformkit.eval_gate.scoring import brier, ece, log_loss
logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_PATH = (_REPO_ROOT / "data" / "cache" / "inplay_odds" /
                     "nba_checkpoints_2025_26_playoffs.parquet")
DEFAULT_OUT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "nba_state_bucket_benchmark.json"
MIN_GAMES = 8
EPS_BRIER = 0.001
_BOOTSTRAP_ITERS = 2000
_DEF_MU = 113.0            # NBARepricer default expected full-game points/team
_DEF_MARGIN_SIGMA = 13.5   # NBARepricer default full-game final-margin SD
MODEL_TAG = "domains_basketball_nba_repricer_gaussian_score_anchor"
PRIOR_VARIANTS: Tuple[str, ...] = ("neutral_p0_0.5", "first_traded_pretip")
_REPRICER: Any = None

def _get_repricer() -> Any:
    global _REPRICER
    if _REPRICER is None:
        from scripts.platformkit.live_repricer import get_repricer
        _REPRICER = get_repricer("nba")
    return _REPRICER

def phase_bucket(period: int) -> str:
    if period <= 2:
        return "P1-2"
    if period == 3:
        return "P3"
    return "P4+OT"

def margin_bucket(margin: float) -> str:
    m = abs(float(margin))
    if m <= 4.0:
        return "close_le4"
    if m <= 10.0:
        return "mid_5to10"
    return "blowout_11plus"

def _elapsed_minutes(period: int, game_clock_s: float) -> float:
    """Minutes ELAPSED (12-min regulation periods, 5-min OT; OT pushes elapsed past
    48 -> repricer's hardcoded full length collapses rem_frac to 0, see module docstring)."""
    s = max(0.0, float(game_clock_s))
    if period <= 4:
        return round((period - 1) * 12.0 + (12.0 - s / 60.0), 4)
    return round(48.0 + (period - 5) * 5.0 + (5.0 - s / 60.0), 4)

def price_checkpoint(p0: float, home_score: float, away_score: float,
                     period: int, game_clock_s: float,
                     margin_sigma: float = _DEF_MARGIN_SIGMA) -> float:
    """LEAK-FREE: pure fn of (p0, score-as-of-tick, period, clock); never reads
    outcome_home_win or any other row -- cannot leak future info."""
    from scripts.platformkit.live_repricer import GameState

    p0c = min(max(float(p0), 1e-6), 1.0 - 1e-6)
    mu_diff = margin_sigma * float(norm.ppf(p0c))
    state = GameState(
        sport="nba", elapsed_minutes=_elapsed_minutes(int(period), game_clock_s),
        home_score=int(home_score), away_score=int(away_score),
        pregame_params={"mu_home": _DEF_MU + mu_diff, "mu_away": _DEF_MU,
                        "margin_sigma": margin_sigma})
    out = _get_repricer().reprice(state)
    return float(out["win_home"])

def load_checkpoints(path: Optional[Path] = None) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Read the checkpoint parquet, drop untraded ticks, price both prior variants.
    Never raises past a missing/corrupt file -- returns an empty frame + n_rows=0."""
    p = path or DEFAULT_DATA_PATH
    try:
        raw = pd.read_parquet(p)
    except Exception as exc:  # noqa: BLE001 -- a bad/missing corpus is not a crash
        logger.warning("load_checkpoints: %s unreadable: %s", p, exc)
        return pd.DataFrame(), {"n_rows_total": 0, "n_rows_traded": 0, "n_games": 0}

    n_total = len(raw)
    df = raw[raw["traded"] == True].copy()  # noqa: E712 -- exclude ALL untraded ticks
    if df.empty:
        return df, {"n_rows_total": n_total, "n_rows_traded": 0, "n_games": 0}

    first_p0 = (df.sort_values("ts").groupby("game_id")["market_prob"].first())
    df["p0_first_traded"] = df["game_id"].map(first_p0)
    df["phase"] = df["period"].apply(phase_bucket)
    df["margin_bucket"] = df["margin"].apply(margin_bucket)
    df["bucket"] = df["phase"] + "|" + df["margin_bucket"]

    df["model_prob_neutral_p0_0.5"] = [
        price_checkpoint(0.5, hs, as_, per, cs) for hs, as_, per, cs in
        zip(df["score_home"], df["score_away"], df["period"], df["game_clock_s"])]
    df["model_prob_first_traded_pretip"] = [
        price_checkpoint(p0, hs, as_, per, cs) for p0, hs, as_, per, cs in
        zip(df["p0_first_traded"], df["score_home"], df["score_away"],
            df["period"], df["game_clock_s"])]

    counts = {"n_rows_total": n_total, "n_rows_traded": len(df),
             "n_games": int(df["game_id"].nunique())}
    return df, counts

def _cluster_bootstrap_ci(per_game_delta: Sequence[float], *,
                          iters: int = _BOOTSTRAP_ITERS, seed: int = 42) -> Tuple[float, float]:
    """95% CI for the pooled mean Brier-diff by resampling GAMES with replacement."""
    vals = [float(v) for v in per_game_delta]
    g = len(vals)
    if g == 0:
        return (0.0, 0.0)
    if g == 1:
        return (vals[0], vals[0])
    rng = random.Random(seed)
    means = []
    for _ in range(iters):
        sample = [vals[rng.randrange(g)] for _ in range(g)]
        means.append(sum(sample) / g)
    means.sort()
    return (means[int(0.025 * (iters - 1))], means[int(0.975 * (iters - 1))])

def _score_group(sub: pd.DataFrame, model_col: str, *,
                 min_games: int = MIN_GAMES, eps: float = EPS_BRIER) -> Dict[str, Any]:
    """Model vs market metrics + game-clustered paired-Brier verdict for one tick group."""
    if sub.empty:
        return {"n_ticks": 0, "n_games": 0, "model": None, "market": None,
               "mean_abs_gap": 0.0, "brier_delta_market_minus_model": 0.0,
               "brier_delta_ci95": [0.0, 0.0], "verdict": "INSUFFICIENT_DATA"}
    model_p = sub[model_col].tolist()
    market_p = sub["market_prob"].tolist()
    y = sub["outcome_home_win"].astype(float).tolist()
    gap = sum(abs(m - k) for m, k in zip(model_p, market_p)) / len(sub)

    per_game_delta: List[float] = []
    for gid, gsub in sub.groupby("game_id"):
        d = [(k - p) ** 2 - (m - p) ** 2 for m, k, p in
             zip(gsub[model_col], gsub["market_prob"], gsub["outcome_home_win"].astype(float))]
        per_game_delta.append(sum(d) / len(d))
    n_games = len(per_game_delta)

    ci_lo, ci_hi = _cluster_bootstrap_ci(per_game_delta)
    if n_games < min_games:
        verdict = "INSUFFICIENT_DATA"
    elif ci_lo > eps:
        verdict = "MODEL_AHEAD"
    elif ci_hi < -eps:
        verdict = "MODEL_BEHIND"
    else:
        verdict = "MATCH"

    return {
        "n_ticks": len(sub), "n_games": n_games,
        "model": {"brier": brier(model_p, y), "log_loss": log_loss(model_p, y), "ece": ece(model_p, y)},
        "market": {"brier": brier(market_p, y), "log_loss": log_loss(market_p, y), "ece": ece(market_p, y)},
        "mean_abs_gap": gap,
        "brier_delta_market_minus_model": (sum(per_game_delta) / n_games) if n_games else 0.0,
        "brier_delta_ci95": [ci_lo, ci_hi], "verdict": verdict,
    }

def _score_variant(df: pd.DataFrame, model_col: str) -> Dict[str, Any]:
    bucket_rows = []
    for name in sorted(df["bucket"].unique()) if not df.empty else []:
        row = _score_group(df[df["bucket"] == name], model_col)
        row["bucket"] = name
        bucket_rows.append(row)
    pooled = _score_group(df, model_col)
    return {"buckets": bucket_rows, "pooled": pooled}

def build_benchmark(data_path: Optional[Path] = None) -> Dict[str, Any]:
    """Full per-bucket + pooled benchmark doc for both prior variants."""
    df, counts = load_checkpoints(data_path)
    variants = {
        "neutral_p0_0.5": _score_variant(df, "model_prob_neutral_p0_0.5"),
        "first_traded_pretip": _score_variant(df, "model_prob_first_traded_pretip"),
    }
    max_date = str(df["game_date"].max()) if not df.empty else "unknown"
    min_date = str(df["game_date"].min()) if not df.empty else "unknown"

    per_sport = [{
        "sport": "nba", "method": "nba_checkpoint_pooled_%s" % vname,
        "n": variants[vname]["pooled"]["n_ticks"],
        "baseline_brier": variants[vname]["pooled"]["market"]["brier"] if variants[vname]["pooled"]["market"] else None,
        "improved_brier": variants[vname]["pooled"]["model"]["brier"] if variants[vname]["pooled"]["model"] else None,
        "baseline_ece": variants[vname]["pooled"]["market"]["ece"] if variants[vname]["pooled"]["market"] else None,
        "improved_ece": variants[vname]["pooled"]["model"]["ece"] if variants[vname]["pooled"]["model"] else None,
    } for vname in PRIOR_VARIANTS]

    doc: Dict[str, Any] = {
        "generated_at": "%sT00:00:00Z" % max_date if max_date != "unknown" else
                        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sport": "nba",
        "benchmark": "kalshi_inplay_checkpoints_playoffs_2025_26",
        "model_tag": MODEL_TAG,
        "prior_variants": list(PRIOR_VARIANTS),
        "binning": {"phase": "P1-2 (period<=2) | P3 | P4+OT (period>=4, includes OT)",
                   "margin": "|margin|: close_le4 <=4, mid_5to10 5-10, blowout_11plus 11+"},
        "n_rows_total": counts["n_rows_total"], "n_rows_traded": counts["n_rows_traded"],
        "n_rows_untraded_excluded": counts["n_rows_total"] - counts["n_rows_traded"],
        "n_games": counts["n_games"], "min_games_for_verdict": MIN_GAMES, "date_range": [min_date, max_date],
        "representativeness_note": (
            "53 games, ALL 2026 playoffs (%s to %s) -- no regular-season games; do not "
            "generalize these verdicts without a regular-season corpus." % (min_date, max_date)),
        "variants": variants,
        "units": "probability (Brier/log-loss/ECE; no dollars)",
        "edge_claimed": False,
        "honest_note": (
            "Calibration measurement only vs the LIVE Kalshi in-play price, not a devigged "
            "close. Model reuses NBARepricer (Gaussian score-anchor) read-only via "
            "live_repricer.get_repricer('nba'); no src/kernel edit. traded=False ticks "
            "(reset/stale quotes) are excluded from scoring. OT inherits a known repricer "
            "limitation (regulation-only 48-min length collapses rem_frac to 0), grouped "
            "into P4+OT so it is visible not hidden. first_traded_pretip reproduces the "
            "market price exactly at each game's own first tick by construction (trivial "
            "there, ~1/150 ticks/game). No $/ROI/edge claim."),
        "calibration_scoreboard": {"per_sport": per_sport},
    }
    return doc

def write_benchmark(out_path: Optional[Path] = None, data_path: Optional[Path] = None,
                    history_path: Optional[Path] = None) -> Dict[str, Any]:
    """Build + atomically write the benchmark JSON, then best-effort scoreboard append.
    generated_at is STABLE (from the corpus's own max game_date, not wall-clock now())
    so reruns on the same corpus dedupe in scoreboard_history. history_path defaults to
    the real data/cache/scoreboard_history.jsonl -- tests MUST pass a tmp_path override."""
    out = out_path or DEFAULT_OUT_PATH
    doc = build_benchmark(data_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(str(tmp), str(out))
    try:
        from scripts.platformkit import scoreboard_history as sh
        sh.append_rows(source_path=out, history_path=history_path)
    except Exception as exc:  # noqa: BLE001 -- history append is best-effort
        logger.debug("write_benchmark: scoreboard_history append skipped: %s", exc)
    return doc

if __name__ == "__main__":
    result = write_benchmark()
    print(json.dumps({
        "pooled_neutral": result["variants"]["neutral_p0_0.5"]["pooled"],
        "pooled_first_traded": result["variants"]["first_traded_pretip"]["pooled"],
        "n_games": result["n_games"], "honest_note": result["honest_note"],
    }, indent=2, ensure_ascii=True))

__all__ = [
    "DEFAULT_DATA_PATH", "DEFAULT_OUT_PATH", "MIN_GAMES", "EPS_BRIER", "MODEL_TAG",
    "PRIOR_VARIANTS", "phase_bucket", "margin_bucket", "price_checkpoint",
    "load_checkpoints", "build_benchmark", "write_benchmark",
]
