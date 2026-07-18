"""scripts.platformkit.benchmarks.crps_market.state_lag_sensitivity -- quantifies
the freshness artifact in data/cache/inplay_odds/nba_checkpoints_full.parquet:
its build (nba_wallclock_join.join_game_states) does
pd.merge_asof(candles, states, on='ts', direction='backward') and, because
both frames share the column name 'ts', pandas keeps the CANDLE's ts and
DROPS the matched ESPN state's own ts (confirmed by reading
nba_wallclock_join.py -- the output cols list never carries a second
timestamp). So a checkpoint row's market_prob can be several seconds (or
longer, across a quiet stretch) fresher than the score state
ingame_nba_winprob.py prices it against -- part of that benchmark's paired-
Brier delta (e.g. the -.0084 market-ahead reading at end_q1) may be this join
artifact rather than real market skill.

STATE-TS RECOVERY (exact, not a bound): the matched state's ts is NOT gone
from the world, only from the assembled parquet -- game_id in that parquet IS
the ESPN event_id (nba_checkpoints_full.build_checkpoints passes eid straight
through), and nba_wallclock_join.fetch_states_for_event(event_id) reads the
SAME cached ESPN summary payload the original build already fetched
(data/cache/nba_pbp_wallclock_raw/summary/{event_id}.json, READ-ONLY replay,
no re-fetch for any game already in the corpus). merge_asof only ever keys on
ts (never on period/score), so re-running it against the identical states
list for the identical candle ts values reproduces the EXACT match the
corpus build made -- see recover_state_lag(). This is a real, exact
recomputation, not a heuristic proxy.

LARGE LAGS ARE REAL: ESPN posts a new state only on a play event, so a quiet
stretch (timeout, end of quarter, no scoring) leaves a candle matched to a
genuinely-stale state for minutes -- not a join bug, exactly the freshness
gap this module measures.

RE-SCORE: for each CHECKPOINTS bucket (imported from ingame_nba_winprob.py,
never re-typed), the SAME model-vs-market paired-Brier delta is recomputed
excluding rows whose state_lag_s exceeds a threshold (5s/10s/30s) -- same
bootstrap-CI + verdict convention (ingame_nba_winprob._verdict_token, itself
run_mlb._bootstrap_ci). One dispatch() subprocess call per scored checkpoint
row, reused across all thresholds (filtered after the fact, not re-scored
per-threshold) -- the heavy step, meant for the pod; the per-file test here
only exercises the pure lag/stat functions on tiny synthetic frames.

CALIBRATION substrate only -- no $/ROI claim, edge_claimed always False.
PROVISIONAL: single capture-window corpus, no independent-corpus replication.

CLI: python -m scripts.platformkit.benchmarks.crps_market.state_lag_sensitivity --max-games 50
Test: python -m pytest tests/platformkit/test_state_lag_sensitivity.py -q
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.answers.winprob_dispatch import dispatch
from scripts.platformkit.benchmarks.crps_market.ingame_nba_winprob import (
    CHECKPOINTS, _COLS, _DATA, checkpoint_row, parse_away_home, _verdict_token,
)
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.nba_checkpoint_benchmark import _elapsed_minutes
from scripts.platformkit.venue_history.nba_wallclock_join import fetch_states_for_event

_OUT = Path(__file__).resolve().parent / "last_run_state_lag_sensitivity.json"
_THRESHOLDS_S: Tuple[int, ...] = (5, 10, 30)


def recover_state_lag(candle_ts: pd.Series, states: List[dict]) -> pd.Series:
    """EXACT candle_ts - matched_state_ts, re-deriving the merge_asof(
    direction='backward') the corpus build performed but keeping the state's
    own ts (the build discards it -- see module docstring). *states* is
    fetch_states_for_event()'s [{ts, ...}] list, any order. Empty *states* or
    a candle before the first state -> NaN (honestly absent, never a
    fabricated 0). Result is aligned to *candle_ts*'s original index."""
    if not states:
        return pd.Series(np.nan, index=candle_ts.index, dtype=float)
    st = pd.DataFrame(states)[["ts"]].rename(columns={"ts": "_state_ts"}).sort_values("_state_ts")
    cd = candle_ts.sort_values()
    merged = pd.merge_asof(cd.to_frame("ts"), st, left_on="ts", right_on="_state_ts",
                            direction="backward")
    lag = pd.Series((merged["ts"] - merged["_state_ts"]).to_numpy(dtype=float), index=cd.index)
    return lag.reindex(candle_ts.index)


def _lag_distribution(lag: np.ndarray) -> dict:
    """Honest summary of an EXACT state-lag-seconds sample. n=0 -> all None,
    never a fabricated stat from an empty array."""
    if lag.size == 0:
        return {"n": 0, "mean_s": None, "median_s": None, "p90_s": None, "max_s": None}
    return {
        "n": int(lag.size), "mean_s": round(float(np.mean(lag)), 1),
        "median_s": round(float(np.median(lag)), 1),
        "p90_s": round(float(np.percentile(lag, 90)), 1),
        "max_s": round(float(np.max(lag)), 1),
    }


def _scored_bucket(rows: List[dict]) -> dict:
    """Paired Brier delta (market - model) + verdict over *rows* (each
    carrying model_brier/market_brier) -- reuses ingame_nba_winprob's
    _verdict_token so this is the SAME CI + PROVISIONAL-suffix convention the
    base benchmark reports, just re-run on a filtered row set."""
    if not rows:
        return {"n": 0, "verdict": "UNDERPOWERED"}
    mb = np.array([r["model_brier"] for r in rows])
    kb = np.array([r["market_brier"] for r in rows])
    delta = kb - mb
    token, provisional, ci = _verdict_token(delta)
    return {
        "n": len(rows), "model_brier_mean": round(float(mb.mean()), 4),
        "market_brier_mean": round(float(kb.mean()), 4),
        "paired_delta_mean": round(float(delta.mean()), 4),
        "paired_delta_95ci": ci, "verdict": token, "provisional": provisional,
    }


def run(max_games: int = 50, thresholds: Tuple[int, ...] = _THRESHOLDS_S) -> dict:
    df = pd.read_parquet(_DATA, columns=_COLS)
    df = df[df["traded"]].copy()
    df["elapsed_minutes"] = [
        _elapsed_minutes(int(p), float(c)) for p, c in zip(df["period"], df["game_clock_s"])]

    game_ids = sorted(df["game_id"].unique())[:max_games]
    records: Dict[str, List[dict]] = {}
    n_ticker_fail = n_model_fail = n_states_missing = n_scored = 0

    for gid in game_ids:
        g = df[df["game_id"] == gid].sort_values("ts").reset_index(drop=True)
        if g.empty:
            continue
        states = fetch_states_for_event(str(int(gid)))
        if not states:
            n_states_missing += 1
        g["state_lag_s"] = recover_state_lag(g["ts"], states)
        pair = parse_away_home(g["market_ticker"].iloc[0])
        if pair is None:
            n_ticker_fail += 1
            continue
        away, home = pair
        y = int(g["outcome_home_win"].iloc[0])

        for label, anchor in CHECKPOINTS:
            row = checkpoint_row(g, anchor)
            if row is None:
                continue
            resp = dispatch("nba", home, away, ingame_state={
                "elapsed": float(row["elapsed_minutes"]),
                "home_score": int(row["score_home"]),
                "away_score": int(row["score_away"]),
            })
            if resp.get("status") != "ok" or resp.get("p_home_win") is None:
                n_model_fail += 1
                continue
            model_p = float(resp["p_home_win"])
            market_p = float(row["market_prob"])
            n_scored += 1
            records.setdefault(label, []).append({
                "model_brier": brier([model_p], [y]), "market_brier": brier([market_p], [y]),
                "state_lag_s": row["state_lag_s"],
            })

    checkpoints_out: Dict[str, dict] = {}
    for label in [c[0] for c in CHECKPOINTS]:
        rows = records.get(label, [])
        lag_known = np.array([r["state_lag_s"] for r in rows if pd.notna(r["state_lag_s"])])
        thresholds_out = {
            str(thr): _scored_bucket([r for r in rows
                                       if pd.notna(r["state_lag_s"]) and r["state_lag_s"] <= thr])
            for thr in thresholds
        }
        checkpoints_out[label] = {
            "n_total": len(rows),
            "n_lag_unknown": sum(1 for r in rows if pd.isna(r["state_lag_s"])),
            "state_lag_seconds_distribution": _lag_distribution(lag_known),
            "unfiltered": _scored_bucket(rows),
            "excluding_lag_over_threshold": thresholds_out,
        }

    result: Dict[str, Any] = {
        "sport": "nba", "edge_claimed": False,
        "n_games_considered": len(game_ids), "n_ticker_parse_fail": n_ticker_fail,
        "n_model_dispatch_fail": n_model_fail, "n_games_states_missing": n_states_missing,
        "n_checkpoints_scored": n_scored, "checkpoints": checkpoints_out,
        "honest_note": (
            "state_lag_s is EXACT (re-derived merge_asof against the matched ESPN "
            "state's own ts, cached read-only from data/cache/nba_pbp_wallclock_raw/"
            "summary/), not a heuristic bound. Large lags reflect real quiet stretches "
            "(no ESPN play event posted), not a bug. excluding_lag_over_threshold drops "
            "(never clips) any row whose state_lag_s exceeds the threshold, then re-runs "
            "the SAME paired-Brier-delta + bootstrap-CI + verdict convention "
            "ingame_nba_winprob.py reports -- compare 'unfiltered' to each threshold "
            "bucket to see how much of the paired delta survives once stale-state rows "
            "are excluded. n_lag_unknown rows (states cache miss) are always excluded "
            "from every threshold bucket, never assumed fresh. Calibration measurement "
            "only, edge_claimed always False. PROVISIONAL -- single capture-window "
            "corpus, needs independent-corpus replication before any durable claim."
        ),
    }
    _OUT.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    return result


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=50)
    a = ap.parse_args(argv)
    doc = run(a.max_games)
    print(json.dumps(doc, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
