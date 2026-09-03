"""S112 -- re-score the nba/mlb pregame SCREEN side against a real close instead of Elo.

Two arms, both on the SCREEN side of the S108 partition (seed 20260903), restricted to the
events that `close_join_nba_mlb` could attach a `p_close` to:

  (a) S108's own elastic net / HGB, with `logit(p_close)` as the TRUE OFFSET instead of
      `logit(p_base)`.  S108's `folds`, `_prep`, `enet_logistic`, `hgb_offset` and `_grid_oof`
      are IMPORTED unchanged, so the leak contract is the one S108 was scored under (Q4).
      Because the close is now the offset, Elo is no longer a copy of it and becomes an honest
      FEATURE -- exactly the rule S108 applies to soccer and tennis, where `p_base` differs
      from the close.

  (b) the top-N single-term screens that looked best against Elo (S85's `nba_player_value_
      features` family), re-run vs `p_close` through the SAME walk-forward screen predictor
      (`foundry.screen_predictor.ScreenBinder` + `RealScreenPredictor`), on identical rows,
      once with Elo as `p_ref` and once with `p_close` as `p_ref`.  Nothing in `foundry/` is
      edited; the incumbent is swapped by rewriting `devig_close_prob` on a COPY of the states.

Reported per arm: Brier of Elo, of `p_close`, of the model, the improvement vs `p_close`, and
the unit-clustered / declared-cluster DM 95 pct CI.  The close is the reference, never
something "beaten": a model that does not clear `IMPROVEMENT_BAR` with a CI excluding zero is
a NULL and that is a success.  No charge, no seal, no ledger read or write; the VERDICT side
is never built.  Calibration language only.

Reproduce:
  python -m scripts.platformkit.eval_gate.s112_rescore_vs_close --sports nba,mlb
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.close_join_nba_mlb import load_close_corpus
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.s108_features import SEED, build
from scripts.platformkit.eval_gate.s108_pregame_full_model import (IMPROVEMENT_BAR, OUTER_FOLDS,
                                                                   ROOT, _grid_oof, _logit,
                                                                   _score)
from scripts.platformkit.eval_gate.walkforward import walk_forward
from scripts.platformkit.foundry.grammar import Hypothesis
from scripts.platformkit.foundry.screen_predictor import ScreenBinder, corpus_states
from scripts.platformkit.foundry.tiers import _cluster_ids, partition_corpus

OUT_DIR = ROOT / "data" / "cache" / "eval_gate"
S85_DB = OUT_DIR / "s85_screen_2026-09-03.sqlite"
TOP_N = 5
STEM = "s112_rescore_2026-09-03"
# S108's design needs >= 5 outer folds. mlb's close-covered screen side is 442 rows, on which
# S108's default k = 6 forms only FOUR. That minimum is NOT lowered (Q3): k is raised to the
# smallest value that satisfies it, and the deviation from S108's k is stated in the artifact.
OUTER_FOLDS_BY_SPORT = {"nba": OUTER_FOLDS, "mlb": 7}


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


def close_map(sport: str) -> pd.Series:
    """event_id -> p_close from the NEW close corpus (the live corpus is never touched)."""
    frame = load_close_corpus(sport)
    frame = frame.loc[frame["p_close"].notna()]
    return pd.Series(frame["p_close"].astype(float).to_numpy(),
                     index=frame["event_id"].astype(str)).sort_index()


# --------------------------------------------------------------------------- #
# Arm (a): S108's full-feature model with logit(p_close) as the offset
# --------------------------------------------------------------------------- #

def full_model_vs_close(sport: str, k: int | None = None) -> Dict[str, Any]:
    """S108's arms re-run with the close as the offset; Elo becomes a plain feature."""
    k = OUTER_FOLDS_BY_SPORT.get(sport, OUTER_FOLDS) if k is None else int(k)
    bundle = build(sport)
    prices = close_map(sport).reindex(bundle["X"].index)
    keep = np.isfinite(prices.to_numpy(dtype=float))
    if int(keep.sum()) < 30:
        raise ValueError("%s: only %d screen events carry a close" % (sport, int(keep.sum())))
    p_elo = bundle["p_inc"][keep]
    X = bundle["X"].loc[keep].copy()
    # The close is the offset now, so the corpus's own Elo base is no longer a copy of it and
    # is a legal feature -- the rule S108 already applies to soccer/tennis.
    X["logit_p_base"] = _logit(p_elo)
    sub = {**bundle, "X": X, "p_inc": prices.to_numpy(dtype=float)[keep],
           "y": bundle["y"][keep], "dates": bundle["dates"][keep],
           "units": bundle["units"][keep], "cluster_ids": bundle["cluster_ids"][keep]}

    grid = _grid_oof(sub, k)
    order = np.array([r["row"] for r in grid["rows"]])
    y, p_close = sub["y"][order], sub["p_inc"][order]
    elo = p_elo[order]
    loss_close, loss_elo = (p_close - y) ** 2, (elo - y) ** 2
    frame = pd.DataFrame({
        "event_id": X.index.to_numpy()[order], "event_date": sub["dates"][order],
        "corpus_unit": sub["units"][order], "cluster_id": sub["cluster_ids"][order],
        "fold": [r["fold"] for r in grid["rows"]], "y": y,
        "p_close": p_close, "p_elo": elo,
        "p_enet": [r["p_enet"] for r in grid["rows"]],
        "p_hgb": [r["p_hgb"] for r in grid["rows"]],
        "loss_close": loss_close, "loss_elo": loss_elo})

    out: Dict[str, Any] = {
        "sport": sport, "arm": "s108_full_model_offset_close", "n_screen": bundle["n_screen"],
        "n_with_close": int(keep.sum()), "n_scored": int(len(order)),
        "n_features": int(X.shape[1]), "screen_sha256": bundle["screen_sha256"],
        "partition_basis": bundle["partition_basis"], "cluster_key": bundle["cluster_key"],
        "improvement_bar": IMPROVEMENT_BAR, "outer_folds_requested": k,
        "s108_outer_folds": OUTER_FOLDS, "folds": grid["picks"],
        "brier_elo": _brier(elo, y), "brier_close": _brier(p_close, y),
        # The close is the reference. A positive number here is the close beating Elo.
        "close_minus_elo": float(np.mean(loss_elo - loss_close)),
        "close_vs_elo_unit_dm": _score(loss_elo - loss_close, frame["corpus_unit"].to_numpy()),
        "close_vs_elo_declared_dm": _score(loss_elo - loss_close, frame["cluster_id"].to_numpy()),
        "arms": {}}
    for arm, column in (("elastic_net", "p_enet"), ("hgb_offset", "p_hgb")):
        loss = (frame[column].to_numpy(dtype=float) - y) ** 2
        frame["loss_" + arm] = loss
        frame["d_" + arm] = loss_close - loss
        stats = {"brier_model": float(loss.mean()),
                 "improvement_vs_close": float(np.mean(loss_close - loss)),
                 "unit_dm": _score(loss_close - loss, frame["corpus_unit"].to_numpy()),
                 "declared_dm": _score(loss_close - loss, frame["cluster_id"].to_numpy())}
        unit = stats["unit_dm"]
        stats["clears_bar"] = bool(stats["improvement_vs_close"] >= IMPROVEMENT_BAR
                                   and unit["ci95"] is not None and unit["ci95"][0] > 0.0)
        out["arms"][arm] = stats
    path = OUT_DIR / ("%s_%s_fullmodel.csv" % (STEM, sport))
    frame.to_csv(path, index=False)
    out["artifact"] = path.as_posix()
    return out


# --------------------------------------------------------------------------- #
# Arm (b): the top vs-Elo single-term screens, re-run against p_close
# --------------------------------------------------------------------------- #

def top_screens(sport: str, top_n: int = TOP_N, db: Path = S85_DB) -> List[Dict[str, Any]]:
    """The `top_n` best-improving S85 T1 screens for `sport`, by published improvement."""
    with sqlite3.connect(db) as conn:
        rows = pd.read_sql(
            "select h.family, h.sport, h.feature, h.transform, h.params, h.horizon, h.market,"
            " r.brier_model, r.brier_close from result r join hypothesis h on h.hash = r.hash"
            " where r.tier = 'T1' and h.sport = ?"
            " order by (r.brier_close - r.brier_model) desc limit ?", conn, params=(sport, top_n))
    return rows.to_dict("records")


def _hypothesis(row: Dict[str, Any]) -> Hypothesis:
    params = tuple(tuple(p) for p in json.loads(row["params"] or "[]"))
    return Hypothesis(sport=row["sport"], feature=row["feature"], transform=row["transform"],
                      params=params, conditioning=frozenset(), horizon=row["horizon"],
                      market=row["market"], family=row["family"])


def _screen_once(sport: str, states: Sequence[dict], table: pd.DataFrame,
                 hypothesis: Hypothesis, incumbent: str) -> Dict[str, Any]:
    """One walk-forward single-term screen against whatever `devig_close_prob` carries."""
    binder = ScreenBinder(sport, states, table, len(states), incumbent)
    rows, predict_fn = binder(hypothesis)
    records = walk_forward(list(rows), predict_fn).records
    model, reference, y = (np.array([r[k] for r in records], dtype=float)
                           for k in ("p_model", "p_close", "y"))
    by_id = {str(s["game_id"]): s for s in rows}
    key, clusters = _cluster_ids([by_id[str(r["game_id"])] for r in records], sport)
    d = (reference - y) ** 2 - (model - y) ** 2
    dm = diebold_mariano(d.tolist(), clusters)
    return {"incumbent": incumbent, "n": int(len(records)), "cluster_key": key,
            "brier_reference": _brier(reference, y), "brier_model": _brier(model, y),
            "improvement": float(np.mean(d)),
            "ci95": [float(dm.ci95[0]), float(dm.ci95[1])], "p": float(dm.p_value),
            "clusters": int(dm.n_clusters)}


def screens_vs_close(sport: str, top_n: int = TOP_N) -> Dict[str, Any]:
    """Re-run the top vs-Elo screens on IDENTICAL rows, once vs Elo and once vs p_close."""
    states, table, incumbent = corpus_states(sport)
    part = partition_corpus(states, seed=SEED)
    prices = close_map(sport)
    screen = [s for s in states
              if str(s["game_id"]) in part.screen_ids and str(s["game_id"]) in prices.index]
    screen.sort(key=lambda s: (s["state_ts"], str(s["game_id"])))
    elo_states = [dict(s) for s in screen]
    close_states = [dict(s, devig_close_prob=float(prices[str(s["game_id"])])) for s in screen]

    results = []
    for row in top_screens(sport, top_n):
        hypothesis = _hypothesis(row)
        results.append({
            "family": row["family"], "feature": row["feature"], "transform": row["transform"],
            "params": row["params"], "s85_brier_model": row["brier_model"],
            "s85_brier_incumbent": row["brier_close"],
            "s85_improvement_vs_elo": float(row["brier_close"] - row["brier_model"]),
            "vs_elo": _screen_once(sport, elo_states, table, hypothesis, incumbent),
            "vs_close": _screen_once(sport, close_states, table, hypothesis, "p_close")})
    return {"sport": sport, "arm": "top%d_single_term_screens" % top_n,
            "n_states": len(states), "n_screen": len(part.screen_ids),
            "n_screen_with_close": len(screen), "screen_sha256": part.screen_sha256,
            "partition_basis": part.basis, "improvement_bar": IMPROVEMENT_BAR,
            "s85_window_rows": 800, "screens": results}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="S112 nba/mlb re-score vs a real close")
    ap.add_argument("--sports", default="nba,mlb")
    ap.add_argument("--top-n", type=int, default=TOP_N)
    ap.add_argument("--outer-folds", type=int, default=None)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)
    report: Dict[str, Any] = {}
    for sport in [s for s in args.sports.split(",") if s]:
        full = full_model_vs_close(sport, k=args.outer_folds)
        print("%-4s n_scored=%d brier_elo=%.6f brier_close=%.6f" % (
            sport, full["n_scored"], full["brier_elo"], full["brier_close"]), flush=True)
        for arm, stats in full["arms"].items():
            print("  %-12s brier=%.6f improvement_vs_close=%+.6f unit_ci=%s clears=%s" % (
                arm, stats["brier_model"], stats["improvement_vs_close"],
                stats["unit_dm"]["ci95"], stats["clears_bar"]), flush=True)
        screens = screens_vs_close(sport, args.top_n)
        for row in screens["screens"]:
            print("  screen %-22s/%-14s vs_elo %+.6f -> vs_close %+.6f  ci=%s" % (
                row["feature"], row["transform"], row["vs_elo"]["improvement"],
                row["vs_close"]["improvement"], row["vs_close"]["ci95"]), flush=True)
        report[sport] = {"full_model": full, "screens": screens}
    path = args.out_dir / ("%s.json" % STEM)
    path.write_text(json.dumps(report, indent=1, sort_keys=True, default=str), encoding="ascii")
    print("summary %s" % path.as_posix())
    return 0


__all__ = ["close_map", "full_model_vs_close", "screens_vs_close", "top_screens"]

if __name__ == "__main__":
    raise SystemExit(main())
