"""scripts.platformkit.benchmarks.crps_market.ingame_nba_winprob -- NBA in-game
win-probability CALIBRATION benchmark: MODEL vs MARKET at fixed game-state
checkpoints, scored Brier + log-loss vs the real final outcome. Modeled on
ingame_mlb.py's bootstrap-CI + verdict-label + honest_note pattern (reused
directly, not reimplemented).

DATA: data/cache/inplay_odds/nba_checkpoints_full.parquet (READ-ONLY, built by
scripts/platformkit/venue_history/nba_checkpoints_full.py) already fuses live
score-state AND Polymarket in-play moneyline price into ONE row per ~60s tick
-- market_prob, score_home/away, period, game_clock_s all come from the SAME
tick, so there is no separate as-of join to perform here. Leak-freeness means:
a checkpoint's row is the LAST tick at-or-before its anchor elapsed-minute
mark, never a later one -- see checkpoint_row() (leak-trap tested).

TICKER DECODE: market_ticker is "nba-{away}-{home}-{date}" with REAL
(post-flip) tricodes -- verified against the ESPN scoreboard cache for two
sample games (2024-10-22 NY@BOS event 401704627, MIN@LAL event 401704628,
both round-tripped exactly against data/cache/nba_pbp_wallclock_raw/
scoreboard/20241022.json).

MODEL: scripts/platformkit/answers/winprob_dispatch.dispatch("nba", home,
away, ingame_state={"elapsed", "home_score", "away_score"}) -- the sanctioned
resolver, subprocess-wrapped over predict_matchup.py. src/ is never imported
directly here.

CHECKPOINTS: OT-aware elapsed-minute anchors (reuses nba_checkpoint_
benchmark.py's _elapsed_minutes) -- end_q1/halftime/end_q3/q4_under5, an
early/mid/mid-late/late moat-shape scan mirroring ingame_mlb.py's inning scan.

SCORING: paired Brier delta (market_brier - model_brier) per checkpoint bucket
+ pooled, 1 row/game/bucket (game-clustered by construction) -- bootstrap CI +
verdict labels (UNDERPOWERED / MODEL_SHARPER_PROVISIONAL /
MARKET_SHARPER_PROVISIONAL) reused verbatim from ingame_mlb._verdict +
ingame_mlb.py's provisional-suffix convention (single capture window --
never durable without independent-corpus replication).

HONESTY (binding): calibration measurement only; edge_claimed always False;
no $/ROI field anywhere.

CLI: python -m scripts.platformkit.benchmarks.crps_market.ingame_nba_winprob --max-games 50
Tests: python -m pytest tests/platformkit/test_ingame_nba_winprob.py -q
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.answers.winprob_dispatch import dispatch
from scripts.platformkit.benchmarks.crps_market.ingame_mlb import _verdict
from scripts.platformkit.eval_gate.scoring import brier, log_loss
from scripts.platformkit.ingame.nba_checkpoint_benchmark import _elapsed_minutes

_REPO = Path(__file__).resolve().parents[4]
_DATA = _REPO / "data" / "cache" / "inplay_odds" / "nba_checkpoints_full.parquet"
_OUT = Path(__file__).resolve().parent / "last_run_ingame_nba_winprob.json"
_COLS = ["game_id", "game_date", "ts", "period", "game_clock_s", "score_home",
         "score_away", "market_prob", "traded", "market_ticker", "outcome_home_win"]

# (label, anchor elapsed-minutes) -- early/mid/mid-late/late moat-shape scan.
CHECKPOINTS: Tuple[Tuple[str, float], ...] = (
    ("end_q1", 12.0), ("halftime", 24.0), ("end_q3", 36.0), ("q4_under5", 43.0))

_TICKER_RE = re.compile(r"^nba-([a-z]+)-([a-z]+)-\d{4}-\d{2}-\d{2}$")


def parse_away_home(market_ticker: str) -> Optional[Tuple[str, str]]:
    """"nba-{away}-{home}-{date}" (real, post-flip tricodes) -> (AWAY, HOME)
    upper-cased, or None if the ticker doesn't match the expected shape."""
    m = _TICKER_RE.match(str(market_ticker))
    if not m:
        return None
    return m.group(1).upper(), m.group(2).upper()


def checkpoint_row(df_game: pd.DataFrame, anchor_minutes: float) -> Optional[pd.Series]:
    """LEAK TRAP: the LAST row of df_game (must carry 'elapsed_minutes') with
    elapsed_minutes <= anchor_minutes -- a row past the anchor is never
    selected, however extreme its market_prob. None if the anchor is never
    reached (df_game empty or all rows are past it)."""
    sub = df_game[df_game["elapsed_minutes"] <= anchor_minutes]
    if sub.empty:
        return None
    return sub.loc[sub["elapsed_minutes"].idxmax()]


def _verdict_token(delta: np.ndarray) -> Tuple[str, bool, List[float]]:
    """Reuses ingame_mlb._verdict (bootstrap CI, fixed seed=0) + its
    provisional-suffix convention: any non-UNDERPOWERED verdict is
    PROVISIONAL until an independent corpus replicates it."""
    verdict, ci = _verdict(delta)
    provisional = verdict != "UNDERPOWERED"
    token = verdict + "_PROVISIONAL" if provisional else verdict
    return token, provisional, ci


def run(max_games: int = 50) -> dict:
    df = pd.read_parquet(_DATA, columns=_COLS)
    df = df[df["traded"]].copy()  # defensive; always True in this corpus
    df["elapsed_minutes"] = [
        _elapsed_minutes(int(p), float(c)) for p, c in zip(df["period"], df["game_clock_s"])]

    game_ids = sorted(df["game_id"].unique())[:max_games]
    buckets: Dict[str, List[dict]] = {}
    n_ticker_fail = n_model_fail = n_scored = 0

    for gid in game_ids:
        g = df[df["game_id"] == gid]
        if g.empty:
            continue
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
            buckets.setdefault(label, []).append({
                "model_brier": brier([model_p], [y]), "market_brier": brier([market_p], [y]),
                "model_logloss": log_loss([model_p], [y]), "market_logloss": log_loss([market_p], [y]),
            })

    checkpoints_out: Dict[str, dict] = {}
    for label in [c[0] for c in CHECKPOINTS]:
        rows = buckets.get(label, [])
        if not rows:
            checkpoints_out[label] = {"n": 0, "verdict": "UNDERPOWERED"}
            continue
        mb = np.array([r["model_brier"] for r in rows]); kb = np.array([r["market_brier"] for r in rows])
        ml = np.array([r["model_logloss"] for r in rows]); kl = np.array([r["market_logloss"] for r in rows])
        delta = kb - mb
        token, provisional, ci = _verdict_token(delta)
        checkpoints_out[label] = {
            "n": len(rows),
            "model_brier_mean": round(float(mb.mean()), 4),
            "market_brier_mean": round(float(kb.mean()), 4),
            "model_logloss_mean": round(float(ml.mean()), 4),
            "market_logloss_mean": round(float(kl.mean()), 4),
            "paired_delta_mean": round(float(delta.mean()), 4),
            "paired_delta_95ci": ci,
            "verdict": token, "provisional": provisional,
        }

    result: Dict[str, Any] = {
        "sport": "nba", "edge_claimed": False,
        "n_games_considered": len(game_ids), "n_ticker_parse_fail": n_ticker_fail,
        "n_model_dispatch_fail": n_model_fail, "n_checkpoints_scored": n_scored,
        "checkpoints": checkpoints_out,
        "honest_note": (
            "Win-probability Brier/log-loss calibration only, never a $/ROI claim. "
            "MODEL = winprob_dispatch.dispatch('nba', ...) over predict_matchup.py "
            "(sanctioned resolver, no src/ import). MARKET = Polymarket in-play "
            "moneyline, same tick as the score state it's paired with (no separate "
            "as-of join needed -- nba_checkpoints_full.parquet already fuses them). "
            "Checkpoints are the last observed tick at-or-before each elapsed-minute "
            "anchor (%s), never a later one -- leak-free by construction. Verdicts are "
            "PROVISIONAL -- single capture-window corpus, needs independent-corpus "
            "replication before any durable claim."
        ) % "/".join("%s=%gmin" % (lbl, m) for lbl, m in CHECKPOINTS),
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
