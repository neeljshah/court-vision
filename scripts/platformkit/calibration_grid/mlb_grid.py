"""scripts.platformkit.calibration_grid.mlb_grid -- MLB state-bucket reliability
map (calibration only, never a $/ROI/edge claim).

DATA: data/cache/statcast/savant_full__<season>.parquet (READ-ONLY, one row per
pitch). Each row's own post_home_score/post_away_score IS the running score
as-of that pitch (statcast convention, reused from ingame_mlb.load_statcast_
index) -- no sort/replay needed to get a per-tick run-diff. Final outcome per
game_pk = max(post_home_score) vs max(post_away_score) (monotonic within a
completed game, same assumption ingame_mlb.py already makes).

BUCKETS: buckets.mlb_bucket(inning, run_diff, extras=inning>9).

MARKET JOIN: OPTIONAL v1, NOT built here -- data/cache/inplay_odds/mlb_price_
series.parquet is a wall-clock ladder (Kalshi ticker keyed) with no shared key
to a wall-clock-free pitch row; a naive date+teams join would silently pick
the wrong in-game moment for a given (inning, run_diff) state (multiple
moments can share a bucket). market_* fields are always null in v1 -- stated
honestly, not guessed. bases-occupied is likewise NOT an axis in this v1 grid.

PASS 2 (EXPENSIVE, flag-gated --model-per-bucket N, default 0): up to N ticks
sampled per bucket, priced through the SANCTIONED resolver
scripts.platformkit.answers.winprob_dispatch.dispatch("mlb", home, away,
{inning, half, home_score, away_score}) -- one subprocess per sampled tick.

PREREGISTERED can_price GATE (same thresholds as nba_grid.py, never tuned
after seeing results): n_games>=30, model_n>=10, |model_mean_prob-outcome_
rate|<=0.06 -- but here that gate can ONLY ever fail on "market join not
built" grounds being moot (market isn't part of the gate) and instead reduces
to a model-vs-outcome check once model_n is available.

CLI: python -m scripts.platformkit.calibration_grid.mlb_grid --model-per-bucket 20
Tests: python -m pytest scripts/platformkit/calibration_grid/test_mlb_grid.py -q
"""
from __future__ import annotations

import argparse
import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from scripts.platformkit.answers.winprob_dispatch import dispatch
from scripts.platformkit.calibration_grid.buckets import mlb_bucket
from scripts.platformkit.eval_gate.scoring import brier

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = _REPO_ROOT / "data" / "cache" / "statcast"
DEFAULT_GLOB = "savant_full__*.parquet"
DEFAULT_OUT_PATH = _REPO_ROOT / "data" / "cache" / "calibration_grid" / "mlb_reliability_map.json"
_COLS = ["game_pk", "home_team", "away_team", "inning", "inning_topbot",
         "post_home_score", "post_away_score"]

MIN_GAMES = 30
MIN_MODEL_N = 10
MAX_MODEL_MARKET_GAP = 0.06

_HALF_MAP = {"top": "top", "bot": "bottom", "bottom": "bottom"}


def _half(inning_topbot: Any) -> Optional[str]:
    return _HALF_MAP.get(str(inning_topbot or "").strip().lower())


def load_ticks(data_dir: Optional[Path] = None, glob_pattern: str = DEFAULT_GLOB) -> pd.DataFrame:
    """Read + bucket every pitch row across every matching season parquet.
    No matching file -> empty frame (never raises)."""
    d = data_dir or DEFAULT_DATA_DIR
    paths = sorted(glob.glob(str(Path(d) / glob_pattern)))
    frames = []
    for p in paths:
        try:
            frames.append(pd.read_parquet(p, columns=_COLS))
        except Exception:
            continue
    if not frames:
        return pd.DataFrame(columns=_COLS + ["run_diff", "extras", "bucket", "home_win"])
    df = pd.concat(frames, ignore_index=True)

    final = df.groupby("game_pk").agg(
        home_final=("post_home_score", "max"), away_final=("post_away_score", "max")).reset_index()
    final["home_win"] = (final["home_final"] > final["away_final"]).astype(int)
    df = df.merge(final[["game_pk", "home_win"]], on="game_pk", how="left")

    df["run_diff"] = df["post_home_score"] - df["post_away_score"]
    df["extras"] = df["inning"].astype(float) > 9
    df["bucket"] = [
        mlb_bucket(i, rd, bool(ex))
        for i, rd, ex in zip(df["inning"], df["run_diff"], df["extras"])]
    return df


def _market_pass(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for bkt, g in df.groupby("bucket"):
        out[bkt] = {
            "n_ticks": int(len(g)), "n_games": int(g["game_pk"].nunique()),
            "outcome_rate": round(float(g["home_win"].astype(float).mean()), 4),
            "market_mean_prob": None, "market_brier": None,
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
        half = _half(row.inning_topbot)
        state = {"inning": int(row.inning), "home_score": int(row.post_home_score),
                 "away_score": int(row.post_away_score)}
        if half:
            state["half"] = half
        resp = dispatch("mlb", str(row.home_team), str(row.away_team), ingame_state=state)
        if resp.get("status") != "ok" or resp.get("p_home_win") is None:
            continue
        buckets.setdefault(row.bucket, []).append(
            (float(resp["p_home_win"]), float(row.home_win)))
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


def build_reliability_map(data_dir: Optional[Path] = None, model_per_bucket: int = 0,
                          seed: int = 0, glob_pattern: str = DEFAULT_GLOB) -> Dict[str, Any]:
    df = load_ticks(data_dir, glob_pattern)
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
        "sport": "mlb", "edge_claimed": False,
        "n_ticks_total": int(len(df)),
        "n_games_total": int(df["game_pk"].nunique()) if not df.empty else 0,
        "model_per_bucket_sampled": model_per_bucket,
        "can_price_thresholds": {"min_games": MIN_GAMES, "min_model_n": MIN_MODEL_N,
                                 "max_model_market_gap": MAX_MODEL_MARKET_GAP},
        "buckets": buckets,
        "honest_note": (
            "Calibration/reliability measurement only, never a $/ROI/edge claim. "
            "Ticks are per-pitch statcast rows; run_diff/inning are as-of that pitch "
            "(post_home_score/post_away_score, statcast's own running-score convention). "
            "MARKET JOIN NOT BUILT v1 -- market_mean_prob/market_brier are always null; "
            "mlb_price_series.parquet is a wall-clock ladder with no shared key to a "
            "wall-clock-free pitch row, so no join is attempted here (never guessed). "
            "BASES-OCCUPIED is NOT an axis in this v1 grid. MODEL = winprob_dispatch."
            "dispatch('mlb', ...) over predict_matchup.py, sampled per-bucket "
            "(--model-per-bucket; 0 = outcome-only pass). can_price is a preregistered "
            "gate (n_games>=%d AND model_n>=%d AND |model-outcome|<=%.2f); any bucket "
            "failing it returns can_price=False with the specific reason, never a guess."
            % (MIN_GAMES, MIN_MODEL_N, MAX_MODEL_MARKET_GAP)),
    }


def write_reliability_map(out_path: Optional[Path] = None, data_dir: Optional[Path] = None,
                          model_per_bucket: int = 0, seed: int = 0) -> Dict[str, Any]:
    doc = build_reliability_map(data_dir, model_per_bucket, seed)
    out = out_path or DEFAULT_OUT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    return doc


def _main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="MLB state-bucket reliability map")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--model-per-bucket", type=int, default=0)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    doc = write_reliability_map(a.out, a.data_dir, a.model_per_bucket, a.seed)
    print(json.dumps({"n_buckets": len(doc["buckets"]), "n_ticks_total": doc["n_ticks_total"],
                      "honest_note": doc["honest_note"]}, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
