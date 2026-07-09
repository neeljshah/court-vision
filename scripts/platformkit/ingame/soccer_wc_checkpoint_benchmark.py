"""scripts.platformkit.ingame.soccer_wc_checkpoint_benchmark -- soccer_intl (World Cup)
MODEL-vs-MARKET in-game calibration benchmark on the Kalshi WC-2026 checkpoint corpus
(data/cache/inplay_odds/soccer_checkpoints_wc2026.parquet, READ-ONLY, 83 games).

LEAK AUDIT: IntlSoccerPredictor builds ONE static team-strength state (ratings.replay(m),
NO ``until`` cutoff) reused for every predict_live() call regardless of date. results.parquet
carries WC-2026 group-stage scores for 2026-06-11..06-16, so a 06-11 prediction uses a state
that already absorbed later/contemporaneous results -- look-ahead leakage for those
16-of-83 games. The earlier 0.15280-vs-0.16291 readout via that predictor is NOT_TESTABLE
(in-sample). FIX (read-only, no predictor edit): ratings.goals_state_asof(until=game_date)
(pre-existing, unused by the live predictor) per game, repriced via the same
live_repricer.get_repricer('soccer') chain. Both readings reported; only asof is scored.

INVARIANTS: <=300 LOC; ASCII only; no network at import; never writes data/registry/; never
edits domains/soccer_intl/*; both parquet inputs READ-ONLY.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_soccer_wc_checkpoint_benchmark.py -q
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

from scripts.platformkit.eval_gate.scoring import brier, ece, log_loss

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_PATH = (_REPO_ROOT / "data" / "cache" / "inplay_odds" /
                     "soccer_checkpoints_wc2026.parquet")
DEFAULT_RESULTS_PATH = _REPO_ROOT / "data" / "domains" / "soccer_intl" / "results.parquet"
DEFAULT_OUT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "soccer_wc_benchmark.json"
MIN_GAMES = 8
EPS_BRIER = 0.001
_BOOTSTRAP_ITERS = 2000
MODEL_TAG_ASOF = "domains_soccer_intl_ratings_goals_state_asof_leakfree_replay"
MODEL_TAG_STATIC = "domains_soccer_intl_predictor_static_replay_in_sample_reference"

# ESPN/checkpoint-corpus team spelling -> martj42 results-corpus spelling (only the 4 that
# differ across the 48 WC teams -- verified by set-difference, see mission trace).
_TEAM_ALIAS = {
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Congo DR": "DR Congo",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
}

def resolve_alias(name: str) -> str:
    return _TEAM_ALIAS.get(name, name)

def phase_bucket(minute: float) -> str:
    m = float(minute)
    if m < 30.0:
        return "early_0to30"
    if m < 70.0:
        return "mid_30to70"
    return "late_70plus"  # covers 2nd-half tail, stoppage, extra time, shootout ticks

def margin_bucket(margin: float) -> str:
    m = float(margin)
    if m > 0:
        return "leading"
    if m < 0:
        return "trailing"
    return "tied"

def _load_results(path: Optional[Path] = None) -> pd.DataFrame:
    p = path or DEFAULT_RESULTS_PATH
    return pd.read_parquet(p)

def _asof_lambdas_by_game(games: pd.DataFrame, matches: pd.DataFrame) -> Dict[str, Tuple[float, float]]:
    """LEAK-FREE: one goals_state_asof(until=game_date) replay PER GAME (cached, never per-tick)."""
    from domains.soccer_intl.ratings import goals_state_asof, _lambdas  # noqa: PLC0415
    out: Dict[str, Tuple[float, float]] = {}
    for row in games.itertuples():
        state = goals_state_asof(matches, row.game_date_d)
        out[row.game_id] = _lambdas(state, row.home_r, row.away_r, True)
    return out

def _static_lambdas_by_game(games: pd.DataFrame, matches: pd.DataFrame) -> Dict[str, Tuple[float, float]]:
    """IN-SAMPLE REFERENCE ONLY (never scored): the production predictor's ONE static
    full-corpus-replay state, reused identically for every game -- reproduces the leak."""
    from domains.soccer_intl.predictor import IntlSoccerPredictor  # noqa: PLC0415
    pred = IntlSoccerPredictor(matches=matches)
    return {row.game_id: pred._matchup_lambdas(row.home_r, row.away_r, True)
           for row in games.itertuples()}

def _price(df: pd.DataFrame, lam_by_game: Dict[str, Tuple[float, float]]) -> List[float]:
    from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: PLC0415

    repricer = get_repricer("soccer")
    out = []
    for gid, minute, hs, as_ in zip(df["game_id"], df["minute"], df["score_home"], df["score_away"]):
        lam_h, lam_a = lam_by_game[gid]
        priced = repricer.reprice(GameState(
            "soccer", float(minute), int(hs), int(as_),
            pregame_params={"lam_home": lam_h, "lam_away": lam_a, "rho": 0.0}))
        out.append(float(priced["1X2_home"]))
    return out

def load_checkpoints(path: Optional[Path] = None, results_path: Optional[Path] = None
                     ) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Read the checkpoint parquet, drop untraded + team-unresolvable ticks, price BOTH
    the leak-free asof model and the in-sample-reference static model. Never raises past a
    missing/corrupt file -- returns an empty frame + n_rows=0."""
    p = path or DEFAULT_DATA_PATH
    try:
        raw = pd.read_parquet(p)
    except Exception as exc:  # noqa: BLE001 -- a bad/missing corpus is not a crash
        logger.warning("load_checkpoints: %s unreadable: %s", p, exc)
        return pd.DataFrame(), {"n_rows_total": 0, "n_rows_traded": 0, "n_games": 0}

    n_total = len(raw)
    df = raw[raw["traded"] == True].copy()  # noqa: E712 -- exclude reset/stale untraded ticks
    if df.empty:
        return df, {"n_rows_total": n_total, "n_rows_traded": 0, "n_games": 0}

    matches = _load_results(results_path)
    known = set(matches["home_team"]) | set(matches["away_team"])
    df["home_r"] = df["home_team"].map(resolve_alias)
    df["away_r"] = df["away_team"].map(resolve_alias)
    resolvable = df["home_r"].isin(known) & df["away_r"].isin(known)
    n_unresolved = int((~resolvable).sum())
    df = df[resolvable].copy()
    if df.empty:
        return df, {"n_rows_total": n_total, "n_rows_traded": 0, "n_rows_team_unresolved": n_unresolved, "n_games": 0}

    df["game_date_d"] = pd.to_datetime(df["game_date"]).dt.date
    games = df[["game_id", "game_date_d", "home_r", "away_r"]].drop_duplicates("game_id")

    lam_asof = _asof_lambdas_by_game(games, matches)
    lam_static = _static_lambdas_by_game(games, matches)
    df["model_prob_asof_leakfree"] = _price(df, lam_asof)
    df["model_prob_static_in_sample"] = _price(df, lam_static)
    df["outcome_home_win"] = (df["outcome"] == "home_win").astype(int)
    df["phase"] = df["minute"].apply(phase_bucket)
    df["margin_bucket"] = df["margin"].apply(margin_bucket)
    df["bucket"] = df["phase"] + "|" + df["margin_bucket"]

    counts = {"n_rows_total": n_total, "n_rows_traded": len(raw[raw["traded"] == True]),  # noqa: E712
             "n_rows_team_unresolved": n_unresolved, "n_rows_scored": len(df),
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
    gap = sum(abs(mm - k) for mm, k in zip(model_p, market_p)) / len(sub)

    per_game_delta: List[float] = []
    for gid, gsub in sub.groupby("game_id"):
        d = [(k - p) ** 2 - (mm - p) ** 2 for mm, k, p in
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

def build_benchmark(data_path: Optional[Path] = None, results_path: Optional[Path] = None,
                    benchmark_name: Optional[str] = None) -> Dict[str, Any]:
    """Full per-bucket + pooled benchmark doc, leak-free asof model AND the in-sample
    static-predictor reference side by side (*benchmark_name* labels the run)."""
    df, counts = load_checkpoints(data_path, results_path)
    asof = _score_variant(df, "model_prob_asof_leakfree")
    static_ref = _score_variant(df, "model_prob_static_in_sample")
    max_date = str(df["game_date"].max()) if not df.empty else "unknown"
    min_date = str(df["game_date"].min()) if not df.empty else "unknown"

    per_sport = [{
        "sport": "soccer_intl", "method": "soccer_wc_checkpoint_pooled_asof_leakfree",
        "n": asof["pooled"]["n_ticks"],
        "baseline_brier": asof["pooled"]["market"]["brier"] if asof["pooled"]["market"] else None,
        "improved_brier": asof["pooled"]["model"]["brier"] if asof["pooled"]["model"] else None,
        "baseline_ece": asof["pooled"]["market"]["ece"] if asof["pooled"]["market"] else None,
        "improved_ece": asof["pooled"]["model"]["ece"] if asof["pooled"]["model"] else None,
    }]

    doc: Dict[str, Any] = {
        "generated_at": "%sT00:00:00Z" % max_date if max_date != "unknown" else
                        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sport": "soccer_intl",
        "benchmark": benchmark_name or "kalshi_inplay_checkpoints_wc2026",
        "model_tag_asof_leakfree": MODEL_TAG_ASOF,
        "model_tag_static_in_sample_reference": MODEL_TAG_STATIC,
        "binning": {"phase": "minute: early_0to30 | mid_30to70 | late_70plus (covers ET/pens ticks)",
                   "margin": "score_home-score_away: trailing <0 | tied ==0 | leading >0"},
        "n_rows_total": counts.get("n_rows_total", 0), "n_rows_traded": counts.get("n_rows_traded", 0),
        "n_rows_team_unresolved": counts.get("n_rows_team_unresolved", 0),
        "n_games": counts.get("n_games", 0), "min_games_for_verdict": MIN_GAMES,
        "date_range": [min_date, max_date],
        "leak_audit": (
            "IntlSoccerPredictor builds ONE static team-strength snapshot (ratings.replay(m), "
            "no 'until' cutoff), reused for every predict_live() call regardless of date -- "
            "games 2026-06-11..06-16 are thus priced with a state that already absorbed "
            "later/contemporaneous WC results (look-ahead leakage). model_prob_static_in_sample "
            "reproduces that reading (reference ONLY, no verdict); model_prob_asof_leakfree "
            "calls goals_state_asof(until=game_date) per game (strictly-prior-only) and is the "
            "ONLY column a verdict is drawn from."),
        "asof_leakfree": asof,
        "static_in_sample_reference": static_ref,
        "units": "probability (Brier/log-loss/ECE; no dollars)",
        "edge_claimed": False,
        "honest_note": (
            "Calibration only vs the LIVE Kalshi in-play price, WC-2026 checkpoint corpus "
            "(83 games). Leak-free lambdas per game; traded=False + team-unresolvable rows "
            "excluded. Single tournament/corpus -- any lift needs replication. No $/edge claim."),
        "calibration_scoreboard": {"per_sport": per_sport},
    }
    return doc

def write_benchmark(out_path: Optional[Path] = None, data_path: Optional[Path] = None,
                    results_path: Optional[Path] = None, history_path: Optional[Path] = None,
                    benchmark_name: Optional[str] = None) -> Dict[str, Any]:
    """Build + atomically write the benchmark JSON, then best-effort scoreboard append.
    history_path defaults to the real data/cache/scoreboard_history.jsonl -- tests MUST
    pass a tmp_path override so synthetic rows never land in production history."""
    out = out_path or DEFAULT_OUT_PATH
    doc = build_benchmark(data_path, results_path, benchmark_name)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(str(tmp), str(out))
    try:
        from scripts.platformkit import scoreboard_history as sh  # noqa: PLC0415
        sh.append_rows(source_path=out, history_path=history_path)
    except Exception as exc:  # noqa: BLE001 -- history append is best-effort
        logger.debug("write_benchmark: scoreboard_history append skipped: %s", exc)
    return doc

if __name__ == "__main__":
    result = write_benchmark()
    print(json.dumps({
        "pooled_asof_leakfree": result["asof_leakfree"]["pooled"],
        "pooled_static_in_sample_reference": result["static_in_sample_reference"]["pooled"],
        "n_games": result["n_games"], "honest_note": result["honest_note"],
    }, indent=2, ensure_ascii=True))

__all__ = [
    "DEFAULT_DATA_PATH", "DEFAULT_RESULTS_PATH", "DEFAULT_OUT_PATH", "MIN_GAMES", "EPS_BRIER",
    "MODEL_TAG_ASOF", "MODEL_TAG_STATIC", "resolve_alias", "phase_bucket", "margin_bucket",
    "load_checkpoints", "build_benchmark", "write_benchmark",
]
