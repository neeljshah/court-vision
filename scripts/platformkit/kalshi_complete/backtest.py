"""scripts.platformkit.kalshi_complete.backtest -- historical self-backtest of
own_lines quotes vs the devigged close, NBA + MLB pregame moneyline.

REUSES the existing leak-free walk-forward predictors + loaders instead of
reinventing them:
  NBA: scripts.platformkit.proof_nba.asof_box_accuracy.{_NBA, load_box} for the
       ESPN box corpus; scripts.platformkit.proof_nba.ml_accuracy.
       {_walk_forward_elo, american_to_prob} for the SAME leak-free MOV-Elo
       p_home_win that ml_accuracy.run() already benchmarks vs the close
       (walk-forward = leak-free: each game's snapshot is taken BEFORE that
       game's own result updates the rating).
  MLB: scripts.platformkit.proof_mlb.beat_the_close_ml.{_GAMES, _ODDS,
       _walk_forward_elo, american_to_prob} -- same leak-free walk-forward Elo
       that module already benchmarks.
  DEVIG: scripts.platformkit.eval_gate.shin.shin_devig -- the vetted
       two-outcome Shin solver. This module's "close" column is Shin-devigged
       (favorite-longshot-bias-aware), not the plain normalize
       ml_accuracy/beat_the_close_ml use for their own headline number, so a
       small difference from those modules' reported market_brier is expected
       and not a bug.

GRADES (calibration/basis language only; edge_claimed:false on every artifact):
  (a) paired Brier delta ours-minus-close + bootstrap 95% CI. Expect ours to
      TRAIL or MATCH (efficient-market expectation, see
      .claude/rules/no-edge-claims.md) -- said plainly either way.
  (b) quote-containment: fraction of held-out games where the Shin-devigged
      close probability falls inside our [bid, ask] band (own_lines.quote_from_p,
      SAME DEFAULT_N_EFF/Z own_lines.py declares -- imported, never re-declared
      here). A calibration-of-band measure, not a hit-rate/edge claim.
  (c) basis distribution: our p_fair minus the devigged close (mean/p5/p95) --
      BASIS language, never "edge".

Evaluated on the held-out SECOND HALF of each corpus (model/rating warms up on
the first half), mirroring ml_accuracy.py / beat_the_close_ml.py.

Output: data/cache/kalshi_complete/own_lines_backtest_<sport>.json
CLI: python -m scripts.platformkit.kalshi_complete.backtest --sport nba|mlb
Test: python -m pytest scripts/platformkit/kalshi_complete/test_backtest.py -q
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from scripts.platformkit.eval_gate.shin import shin_devig
from scripts.platformkit.kalshi_complete.own_lines import DEFAULT_N_EFF, quote_from_p

_REPO = Path(__file__).resolve().parents[3]
_OUT_DIR = _REPO / "data" / "cache" / "kalshi_complete"
_MIN_N = 60

_NOTE = ("Pregame expectation: model MATCHES or TRAILS the devigged close -- "
         "the honest, efficient-market outcome (see .claude/rules/no-edge-claims.md). "
         "basis_* is a price DIFFERENCE, never an edge. quote_containment_rate is a "
         "calibration-of-band measure, not a hit rate. edge_claimed is always False.")


def _shin_close_prob_two(pi_h: float, pi_a: float) -> Optional[float]:
    """None for bad close rows (booksum <= 1 = stale/one-sided line in the
    historical odds corpus -- shin asserts on it; found live on MLB
    2026-07-18). Callers drop None rows and count them honestly."""
    if (pi_h + pi_a) <= 1.0:
        return None
    p, _z = shin_devig([pi_h, pi_a])
    return float(p[0])


def load_nba(corpus: Optional[Path] = None):
    """(p_model, p_close, y) frame, chronological, leak-free -- reuses proof_nba loaders/Elo."""
    import pandas as pd  # noqa: PLC0415
    from scripts.platformkit.proof_nba.asof_box_accuracy import _NBA, load_box
    from scripts.platformkit.proof_nba.ml_accuracy import _walk_forward_elo, american_to_prob

    root = corpus or _NBA
    box = load_box(root)
    box["p_model"] = _walk_forward_elo(box)
    raw = pd.read_parquet(root / "odds.parquet").rename(
        columns={"home_team": "home_abbr", "away_team": "away_abbr"})
    raw["date"] = pd.to_datetime(raw["date"])
    raw = raw.dropna(subset=["home_ml", "away_ml"]).copy()
    raw["p_close"] = [
        _shin_close_prob_two(american_to_prob(h), american_to_prob(a))
        for h, a in zip(raw["home_ml"], raw["away_ml"])
    ]
    raw = raw.dropna(subset=["p_close"])  # bad-close rows (booksum<=1) dropped, counted by n
    m = box.merge(raw[["date", "home_abbr", "away_abbr", "p_close"]],
                  on=["date", "home_abbr", "away_abbr"], how="inner").reset_index(drop=True)
    m["y"] = (m["home_pts"] > m["away_pts"]).astype(float)
    return m[["p_model", "p_close", "y"]]


def load_mlb(corpus: Optional[Path] = None):
    """(p_model, p_close, y) frame, chronological, leak-free -- reuses proof_mlb loaders/Elo."""
    import pandas as pd  # noqa: PLC0415
    from scripts.platformkit.proof_mlb.beat_the_close_ml import (
        _GAMES, _ODDS, _walk_forward_elo, american_to_prob)

    games_path = (corpus / "games.parquet") if corpus is not None else _GAMES
    odds_path = (corpus / "odds.parquet") if corpus is not None else _ODDS
    games = pd.read_parquet(games_path)
    odds = pd.read_parquet(odds_path)[
        ["event_id", "ml_close_home_am", "ml_close_away_am"]].dropna().copy()
    games = games.sort_values(["date", "game_seq", "event_id"]).reset_index(drop=True)
    games["p_model"] = _walk_forward_elo(games)
    odds["p_close"] = [
        _shin_close_prob_two(american_to_prob(h), american_to_prob(a))
        for h, a in zip(odds["ml_close_home_am"], odds["ml_close_away_am"])
    ]
    odds = odds.dropna(subset=["p_close"])  # bad-close rows (booksum<=1) dropped
    m = games.merge(odds[["event_id", "p_close"]], on="event_id", how="inner")
    m = m.sort_values(["date", "game_seq", "event_id"]).reset_index(drop=True)
    m["y"] = (m["home_runs"] > m["away_runs"]).astype(float)
    return m[["p_model", "p_close", "y"]]


def _bootstrap_ci(delta: np.ndarray, b: int = 3000, seed: int = 0) -> list:
    rng = np.random.default_rng(seed)
    n = len(delta)
    means = [rng.choice(delta, size=n, replace=True).mean() for _ in range(b)]
    return [round(float(np.percentile(means, 2.5)), 5), round(float(np.percentile(means, 97.5)), 5)]


def grade_frame(df, n_eff: float = DEFAULT_N_EFF, min_n: int = _MIN_N) -> Dict[str, Any]:
    """Grade a (p_model, p_close, y) frame on its held-out second half. Pure -- no I/O,
    so tests can pass a synthetic frame directly."""
    n = len(df)
    if n < min_n:
        return {"status": "data_limited", "n": n, "note": _NOTE, "edge_claimed": False}

    mid = n // 2
    y = df["y"].to_numpy(float)[mid:]
    pm = np.clip(df["p_model"].to_numpy(float)[mid:], 1e-6, 1 - 1e-6)
    pc = np.clip(df["p_close"].to_numpy(float)[mid:], 1e-6, 1 - 1e-6)

    brier_model = float(np.mean((pm - y) ** 2))
    brier_close = float(np.mean((pc - y) ** 2))
    delta = (pm - y) ** 2 - (pc - y) ** 2  # paired per-game Brier delta, model - close
    gap = round(brier_model - brier_close, 5)
    ci = _bootstrap_ci(delta)
    verdict = "MATCHES_CLOSE_WITHIN_NOISE" if gap <= 0.003 else "TRAILS_CLOSE"

    bands = [quote_from_p(float(p), n_eff) for p in pm]
    bids = np.array([q["bid"] for q in bands])
    asks = np.array([q["ask"] for q in bands])
    containment = float(np.mean((pc >= bids) & (pc <= asks)))

    basis = pm - pc
    return {
        "status": "ok", "n": n, "n_holdout": n - mid,
        "brier_model": round(brier_model, 5), "brier_close": round(brier_close, 5),
        "brier_gap_model_minus_close": gap, "brier_gap_ci95": ci, "verdict": verdict,
        "quote_containment_rate": round(containment, 4), "n_eff": n_eff,
        "basis_mean": round(float(basis.mean()), 4),
        "basis_p5": round(float(np.percentile(basis, 5)), 4),
        "basis_p95": round(float(np.percentile(basis, 95)), 4),
        "edge_claimed": False, "note": _NOTE,
    }


_LOADERS = {"nba": load_nba, "mlb": load_mlb}


def run_backtest(sport: str, corpus: Optional[Path] = None, n_eff: float = DEFAULT_N_EFF) -> Dict[str, Any]:
    sport = sport.lower()
    if sport not in _LOADERS:
        return {"status": "not_supported", "sport": sport, "note": _NOTE, "edge_claimed": False}
    try:
        df = _LOADERS[sport](corpus)
    except FileNotFoundError as exc:
        return {"status": "no_data", "sport": sport, "error": str(exc), "note": _NOTE,
                "edge_claimed": False}
    rep = grade_frame(df, n_eff)
    rep["sport"] = sport
    return rep


def write_backtest(sport: str, corpus: Optional[Path] = None,
                   out_dir: Path = _OUT_DIR) -> Dict[str, Any]:
    rep = run_backtest(sport, corpus)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_fp = out_dir / f"own_lines_backtest_{sport.lower()}.json"
    out_fp.write_text(json.dumps(rep, indent=2))
    rep["_written_to"] = str(out_fp)
    return rep


def _main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sport", required=True, choices=["nba", "mlb"])
    a = ap.parse_args(argv)
    rep = write_backtest(a.sport)
    print(json.dumps(rep, indent=2))
    return 0 if rep.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(_main())
