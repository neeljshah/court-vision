"""scripts.platformkit.calibration_grid.nba_grid -- NBA state-bucket reliability
map (calibration only, never a $/ROI/edge claim).

PASS 1 (cheap, market-side): every TRADED tick in the in-play checkpoints
corpus is bucketed by buckets.nba_bucket(elapsed_minutes, home_lead, is_ot);
per bucket we aggregate n_ticks, n_games, outcome_rate, market_mean_prob,
market_brier (all tick-weighted -- a bucket with more ticks from one blowout
game does pull its own average, that tradeoff is stated in honest_note).

PASS 2 (EXPENSIVE, flag-gated --model-per-bucket N, default 0 = skipped):
up to N ticks are sampled per bucket (uniform, seeded) and priced through the
SANCTIONED resolver scripts.platformkit.answers.winprob_dispatch.dispatch --
one subprocess per sampled tick, never predict_matchup imported directly.
This pass is meant to run on the pod for full coverage; the reference-repo
default (0) only ever produces the market-side pass.

PREREGISTERED can_price GATE (binding -- never tuned after seeing results):
  n_games   >= MIN_GAMES (30)
  model_n   >= MIN_MODEL_N (10)
  |model_mean_prob - outcome_rate| <= MAX_MODEL_MARKET_GAP (0.06)
Any bucket failing this returns can_price=False with the SPECIFIC reason it
failed -- fail-closed beats a confident guess.

CLI: python -m scripts.platformkit.calibration_grid.nba_grid --model-per-bucket 20
Tests: python -m pytest scripts/platformkit/calibration_grid/test_nba_grid.py -q
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from scripts.platformkit.answers.winprob_dispatch import dispatch
from scripts.platformkit.benchmarks.crps_market.ingame_nba_winprob import parse_away_home
from scripts.platformkit.calibration_grid.buckets import nba_bucket
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.nba_checkpoint_benchmark import _elapsed_minutes

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_PATH = _REPO_ROOT / "data" / "cache" / "inplay_odds" / "nba_checkpoints_full.parquet"
DEFAULT_OUT_PATH = _REPO_ROOT / "data" / "cache" / "calibration_grid" / "nba_reliability_map.json"
_COLS = ["game_id", "period", "game_clock_s", "score_home", "score_away",
         "market_prob", "traded", "market_ticker", "outcome_home_win"]

MIN_GAMES = 30
MIN_MODEL_N = 10
MAX_MODEL_MARKET_GAP = 0.06


def load_ticks(data_path: Optional[Path] = None) -> pd.DataFrame:
    """Read + bucket every traded tick. Missing/unreadable corpus -> empty frame."""
    path = data_path or DEFAULT_DATA_PATH
    try:
        df = pd.read_parquet(path, columns=_COLS)
    except Exception:
        return pd.DataFrame(columns=_COLS + ["elapsed_minutes", "home_lead", "bucket"])
    df = df[df["traded"] == True].copy()  # noqa: E712 -- exclude untraded ticks
    df["elapsed_minutes"] = [
        _elapsed_minutes(int(p), float(c)) for p, c in zip(df["period"], df["game_clock_s"])]
    df["home_lead"] = df["score_home"] - df["score_away"]
    df["bucket"] = [
        nba_bucket(e, l, bool(int(p) > 4))
        for e, l, p in zip(df["elapsed_minutes"], df["home_lead"], df["period"])]
    return df


def _market_pass(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for bkt, g in df.groupby("bucket"):
        y = g["outcome_home_win"].astype(float).tolist()
        p = g["market_prob"].astype(float).tolist()
        out[bkt] = {
            "n_ticks": int(len(g)), "n_games": int(g["game_id"].nunique()),
            "outcome_rate": round(float(np.mean(y)), 4),
            "market_mean_prob": round(float(np.mean(p)), 4),
            "market_brier": round(brier(p, y), 4),
        }
    return out


def _sample_for_model(df: pd.DataFrame, n_per_bucket: int, seed: int) -> pd.DataFrame:
    if n_per_bucket <= 0 or df.empty:
        return df.iloc[0:0]
    rng = np.random.default_rng(seed)
    parts = []
    for _bkt, g in df.groupby("bucket"):
        idx = g.index.to_numpy()
        if len(idx) > n_per_bucket:
            idx = rng.choice(idx, size=n_per_bucket, replace=False)
        parts.append(df.loc[idx])
    return pd.concat(parts) if parts else df.iloc[0:0]


def _model_pass(sample: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """One winprob_dispatch.dispatch subprocess call per sampled tick -- EXPENSIVE."""
    buckets: Dict[str, list] = {}
    for row in sample.itertuples():
        pair = parse_away_home(row.market_ticker)
        if pair is None:
            continue
        away, home = pair
        resp = dispatch("nba", home, away, ingame_state={
            "elapsed": float(row.elapsed_minutes),
            "home_score": int(row.score_home), "away_score": int(row.score_away)})
        if resp.get("status") != "ok" or resp.get("p_home_win") is None:
            continue
        buckets.setdefault(row.bucket, []).append(
            (float(resp["p_home_win"]), float(row.outcome_home_win)))
    out: Dict[str, Dict[str, Any]] = {}
    for bkt, rows in buckets.items():
        p = [r[0] for r in rows]; y = [r[1] for r in rows]
        out[bkt] = {"model_n": len(rows), "model_mean_prob": round(float(np.mean(p)), 4),
                    "model_brier": round(brier(p, y), 4)}
    return out


def _can_price(market_row: Dict[str, Any], model_row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    n_games = market_row["n_games"]
    if n_games < MIN_GAMES:
        return {"can_price": False,
                "reason": "insufficient games (n_games=%d < %d)" % (n_games, MIN_GAMES)}
    model_n = model_row.get("model_n", 0) if model_row else 0
    if model_n < MIN_MODEL_N:
        return {"can_price": False,
                "reason": "insufficient model samples (model_n=%d < %d; rerun with "
                          "--model-per-bucket)" % (model_n, MIN_MODEL_N)}
    gap = abs(model_row["model_mean_prob"] - market_row["outcome_rate"])
    if gap > MAX_MODEL_MARKET_GAP:
        return {"can_price": False,
                "reason": "model miscalibrated vs outcome (|delta|=%.4f > %.2f)"
                          % (gap, MAX_MODEL_MARKET_GAP)}
    return {"can_price": True, "reason": "ok"}


def build_reliability_map(data_path: Optional[Path] = None, model_per_bucket: int = 0,
                          seed: int = 0) -> Dict[str, Any]:
    df = load_ticks(data_path)
    market = _market_pass(df) if not df.empty else {}
    sample = _sample_for_model(df, model_per_bucket, seed)
    model = _model_pass(sample) if not sample.empty else {}

    buckets: Dict[str, Any] = {}
    for key, mrow in market.items():
        row = dict(mrow)
        mdl = model.get(key)
        row.update(mdl if mdl else {"model_n": 0, "model_mean_prob": None, "model_brier": None})
        row.update(_can_price(mrow, mdl))
        buckets[key] = row

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sport": "nba", "edge_claimed": False,
        "n_ticks_total": int(len(df)),
        "n_games_total": int(df["game_id"].nunique()) if not df.empty else 0,
        "model_per_bucket_sampled": model_per_bucket,
        "can_price_thresholds": {"min_games": MIN_GAMES, "min_model_n": MIN_MODEL_N,
                                 "max_model_market_gap": MAX_MODEL_MARKET_GAP},
        "buckets": buckets,
        "honest_note": (
            "Calibration/reliability measurement only, never a $/ROI/edge claim. MARKET "
            "= Polymarket in-play price, same tick as the score state (nba_checkpoints_"
            "full.parquet already fuses them, no separate as-of join). MODEL = "
            "winprob_dispatch.dispatch('nba', ...) over predict_matchup.py, sampled "
            "per-bucket (--model-per-bucket; 0 = market-only pass). Tick-weighted "
            "aggregates, not game-weighted -- a bucket with more ticks from one game "
            "pulls its own average, stated here rather than hidden. can_price is a "
            "preregistered gate (n_games>=%d AND model_n>=%d AND |model-outcome|<=%.2f); "
            "any bucket failing it returns can_price=False with the specific reason, "
            "never a guess." % (MIN_GAMES, MIN_MODEL_N, MAX_MODEL_MARKET_GAP)),
    }


def write_reliability_map(out_path: Optional[Path] = None, data_path: Optional[Path] = None,
                          model_per_bucket: int = 0, seed: int = 0) -> Dict[str, Any]:
    doc = build_reliability_map(data_path, model_per_bucket, seed)
    out = out_path or DEFAULT_OUT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    return doc


def _main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="NBA state-bucket reliability map")
    ap.add_argument("--data-root", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--model-per-bucket", type=int, default=0)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    doc = write_reliability_map(a.out, a.data_root, a.model_per_bucket, a.seed)
    print(json.dumps({"n_buckets": len(doc["buckets"]), "n_ticks_total": doc["n_ticks_total"],
                      "honest_note": doc["honest_note"]}, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
