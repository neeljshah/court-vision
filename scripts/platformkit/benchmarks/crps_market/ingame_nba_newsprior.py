"""scripts.platformkit.benchmarks.crps_market.ingame_nba_newsprior -- tests
whether a TIP-TIME-INFORMATION-adjusted prior closes the end_q1 gap found by
ingame_nba_winprob.py (v3: paired Brier delta -.0084, CI excludes 0 -- market
sharper than model at end_q1; indistinguishable at halftime/end_q3/q4_under5).

HYPOTHESIS: the early-checkpoint deficit is an INFORMATION gap, not a
modeling gap -- the market prices tip-time news (who's out, starter changes,
rest) our prior ignores.

PREMISE CHECK (do not re-run, already inventoried): no historical PER-DATE
injury-report store exists for this corpus's span (2024-10-22..2026-06-13).
data/cache/nba_injuries_<date>.parquet + data/cache/injury_features.parquet
only cover 2026-04-12..2026-07-16 (current-season daily scrapes, ~2.5 of the
corpus's 20 months) -- CURRENT-snapshot, not a tip-time-as-of archive. This
module instead uses data/domains/basketball_nba/player_boxscores.parquet
(starter flag + `min`, 2023-10-24..2026-04-12) as an ACTUAL-PLAYED proxy --
see ingame_nba_newsprior_features.py for the feature math + full knowability
caveat (mislabels late scratches / roster churn; upper-bound-noisy, not
causal). COVERAGE GAP: 78/1593 (4.9%) of the v3 corpus's games fall after
player_boxscores' tail and score with an honest all-zero feature row.

WALK-FORWARD: v3's game sample (sorted by game_id, [:max_games], same
convention) is re-sorted by game_date; the first --train-frac (default 0.7)
games chronologically are the FIT split, the remainder is the SCORE split --
no score-split game's outcome, state, or model_p ever enters the fit.

ADJUSTMENT: winprob_dispatch.dispatch() returns ONE p_home_win number per
checkpoint (no separate prior/conditioning split is exposed -- see
ingame_nba_winprob.py), so the fit is a single LOGIT SHIFT applied to that
number: statsmodels GLM(Binomial) of home_win on FEATURE_COLUMNS with
logit(model_p) held as a fixed OFFSET (coefficient forced to 1, never
re-fit) -- adjusted_p = sigmoid(logit(model_p) + X @ beta_hat), beta_hat
fit on the train split only, applied to the score split's checkpoints.
Falls back to a zero shift (no adjustment) if the fit is underpowered or
fails to converge -- expected at small --max-games, recorded via n_train.

SCORING: same 4 checkpoints, same Polymarket ticks, same bootstrap CI
(b=3000, seed=0, reused from run_mlb._bootstrap_ci) as v3 -- two comparisons
per checkpoint: (unadjusted_brier - adjusted_brier) and (market_brier -
adjusted_brier), both positive-is-better. Verdict per checkpoint by CI
position: CLOSES_GAP (CI lo > 0) / WORSENS (CI hi < 0) / NO_CHANGE /
UNDERPOWERED (n<30). beats_market_provisional is True only when the
adjusted-vs-market verdict is CLOSES_GAP, and is still PROVISIONAL even
then -- single-capture-window corpus, never durable without independent-
corpus replication. edge_claimed always False; no $/ROI field anywhere.

Artifact: data/cache/benchmarks/ingame_nba_newsprior_verdict.json
CLI: python -m scripts.platformkit.benchmarks.crps_market.ingame_nba_newsprior --max-games 50
Tests: python -m pytest tests/platformkit/test_ingame_nba_newsprior.py -q
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import statsmodels.api as sm

from scripts.platformkit.answers.winprob_dispatch import dispatch
from scripts.platformkit.benchmarks.crps_market.ingame_nba_newsprior_features import (
    FEATURE_COLUMNS, build_features, team_frames, team_game_dates,
)
from scripts.platformkit.benchmarks.crps_market.ingame_nba_winprob import (
    CHECKPOINTS, checkpoint_row, parse_away_home,
)
from scripts.platformkit.benchmarks.crps_market.run_mlb import _bootstrap_ci
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.nba_checkpoint_benchmark import _elapsed_minutes

_REPO = Path(__file__).resolve().parents[4]
_DATA = _REPO / "data" / "cache" / "inplay_odds" / "nba_checkpoints_full.parquet"
_PBOX = _REPO / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_OUT = _REPO / "data" / "cache" / "benchmarks" / "ingame_nba_newsprior_verdict.json"
_COLS = ["game_id", "game_date", "ts", "period", "game_clock_s", "score_home",
         "score_away", "market_prob", "traded", "market_ticker", "outcome_home_win"]
_EPS = 1e-6
_MIN_TRAIN = len(FEATURE_COLUMNS) + 5


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, _EPS, 1 - _EPS)
    return np.log(p / (1 - p))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _gap_verdict(delta: np.ndarray) -> Tuple[str, List[float]]:
    """delta convention: positive = the adjustment beat the comparator (lower
    Brier). Same CI-position rule as run_mlb._verdict (n<30 -> UNDERPOWERED),
    relabeled CLOSES_GAP/NO_CHANGE/WORSENS."""
    ci = _bootstrap_ci(delta)
    if len(delta) < 30:
        return "UNDERPOWERED", ci
    if ci[0] > 0:
        return "CLOSES_GAP", ci
    if ci[1] < 0:
        return "WORSENS", ci
    return "NO_CHANGE", ci


def fit_logit_shift(train_rows: List[dict]) -> np.ndarray:
    """GLM(Binomial) offset-fit -- see module docstring. Returns
    [intercept, *feature_betas]; an all-zero vector (no adjustment) if the
    train split is too small or the fit fails to converge."""
    n = len(FEATURE_COLUMNS)
    if len(train_rows) < _MIN_TRAIN:
        return np.zeros(n + 1)
    y = np.array([r["y"] for r in train_rows], dtype=float)
    offset = _logit(np.array([r["model_p"] for r in train_rows], dtype=float))
    X = sm.add_constant(
        np.array([[r[c] for c in FEATURE_COLUMNS] for r in train_rows], dtype=float),
        has_constant="add")
    try:
        fit = sm.GLM(y, X, family=sm.families.Binomial(), offset=offset).fit()
        return np.asarray(fit.params, dtype=float)
    except Exception:  # noqa: BLE001 -- underpowered/singular fits fall back honestly
        return np.zeros(n + 1)


def apply_shift(model_p: float, feat_row: Dict[str, float], beta: np.ndarray) -> float:
    x = np.array([1.0] + [feat_row[c] for c in FEATURE_COLUMNS])
    return float(_sigmoid(_logit(np.array([model_p]))[0] + float(x @ beta)))


def walk_forward_split(game_ids: List, gdate_lookup, train_frac: float
                       ) -> Tuple[List, set]:
    """Sort game_ids by date; the first train_frac fraction is the fit split
    (returned as `order` + the `train_ids` set) -- pulled out as a pure
    function so the leak-free ordering is unit-testable without touching the
    real corpus parquet."""
    order = sorted(game_ids, key=lambda g: gdate_lookup[g])
    n_train = int(len(order) * train_frac)
    return order, set(order[:n_train])


def score_checkpoint(rows: List[dict]) -> dict:
    """rows: per-game dicts tagged split=train/test with model_p, market_p,
    y, and FEATURE_COLUMNS -- fits the logit shift on the train rows only and
    scores paired Brier on the test rows only. Pulled out as a pure function
    so the artifact schema + verdict mapping are unit-testable on synthetic
    rows without the real corpus/dispatch subprocess."""
    train_rows = [r for r in rows if r["split"] == "train"]
    test_rows = [r for r in rows if r["split"] == "test"]
    if not test_rows:
        return {"n_train": len(train_rows), "n_test": 0,
                "verdict_vs_unadjusted": "UNDERPOWERED", "verdict_vs_market": "UNDERPOWERED"}

    beta = fit_logit_shift(train_rows)
    model_p = np.array([r["model_p"] for r in test_rows])
    market_p = np.array([r["market_p"] for r in test_rows])
    y = [r["y"] for r in test_rows]
    adj_p = np.array([apply_shift(r["model_p"], r, beta) for r in test_rows])

    b_unadj = np.array([brier([p], [yy]) for p, yy in zip(model_p, y)])
    b_adj = np.array([brier([p], [yy]) for p, yy in zip(adj_p, y)])
    b_mkt = np.array([brier([p], [yy]) for p, yy in zip(market_p, y)])
    delta_vs_unadj = b_unadj - b_adj   # positive = adjustment helped
    delta_vs_mkt = b_mkt - b_adj       # positive = adjusted beats market

    v1, ci1 = _gap_verdict(delta_vs_unadj)
    v2, ci2 = _gap_verdict(delta_vs_mkt)
    return {
        "n_train": len(train_rows), "n_test": len(test_rows),
        "unadjusted_brier_mean": round(float(b_unadj.mean()), 4),
        "adjusted_brier_mean": round(float(b_adj.mean()), 4),
        "market_brier_mean": round(float(b_mkt.mean()), 4),
        "delta_vs_unadjusted_mean": round(float(delta_vs_unadj.mean()), 4),
        "delta_vs_unadjusted_95ci": ci1, "verdict_vs_unadjusted": v1,
        "delta_vs_market_mean": round(float(delta_vs_mkt.mean()), 4),
        "delta_vs_market_95ci": ci2, "verdict_vs_market": v2,
        "beats_market_provisional": v2 == "CLOSES_GAP",
    }


def run(max_games: int = 50, train_frac: float = 0.7) -> dict:
    df = pd.read_parquet(_DATA, columns=_COLS)
    df = df[df["traded"]].copy()
    df["elapsed_minutes"] = [
        _elapsed_minutes(int(p), float(c)) for p, c in zip(df["period"], df["game_clock_s"])]

    pbox = pd.read_parquet(_PBOX, columns=["team", "date", "player_id", "min", "starter"])
    pbox_by_team = team_frames(pbox)
    dates_by_team = team_game_dates(pbox)

    game_ids = sorted(df["game_id"].unique())[:max_games]
    gdate_lookup = df.drop_duplicates("game_id").set_index("game_id")["game_date"]
    order, train_ids = walk_forward_split(game_ids, gdate_lookup, train_frac)

    per_checkpoint: Dict[str, List[dict]] = {c[0]: [] for c in CHECKPOINTS}
    n_ticker_fail = n_model_fail = 0

    for gid in order:
        g = df[df["game_id"] == gid]
        pair = parse_away_home(g["market_ticker"].iloc[0])
        if pair is None:
            n_ticker_fail += 1
            continue
        away, home = pair
        y = int(g["outcome_home_win"].iloc[0])
        feat_row = build_features(pbox_by_team, dates_by_team, home, away, g["game_date"].iloc[0])
        split = "train" if gid in train_ids else "test"

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
            per_checkpoint[label].append({
                "split": split, "model_p": float(resp["p_home_win"]),
                "market_p": float(row["market_prob"]), "y": y, **feat_row,
            })

    checkpoints_out: Dict[str, dict] = {
        label: score_checkpoint(per_checkpoint[label]) for label in [c[0] for c in CHECKPOINTS]}

    result: Dict[str, Any] = {
        "sport": "nba", "edge_claimed": False,
        "hypothesis": "tip-time-information-adjusted prior closes the v3 end_q1 gap",
        "n_games_considered": len(order), "n_train_games": len(train_ids),
        "n_test_games": len(order) - len(train_ids), "train_frac": train_frac,
        "n_ticker_parse_fail": n_ticker_fail, "n_model_dispatch_fail": n_model_fail,
        "checkpoints": checkpoints_out,
        "honest_note": (
            "PROVISIONAL, single-capture-window corpus -- never durable without "
            "independent-corpus replication. Tip-time features are an ACTUAL-PLAYED "
            "proxy (player_boxscores starter/min), not a historical tip-time "
            "injury-report archive -- no such archive exists for this corpus's span "
            "(see module docstring premise check). 78/1593 v3 games fall after "
            "player_boxscores' 2026-04-12 coverage tail and score with an honest "
            "all-zero feature row. beats_market_provisional is only ever True when "
            "the adjusted-minus-market Brier CI excludes 0 in our favor, and remains "
            "PROVISIONAL even then. No dollar/ROI claim anywhere."
        ),
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    return result


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=50)
    ap.add_argument("--train-frac", type=float, default=0.7)
    a = ap.parse_args(argv)
    doc = run(a.max_games, a.train_frac)
    print(json.dumps(doc, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
