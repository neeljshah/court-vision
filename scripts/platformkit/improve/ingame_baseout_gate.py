"""scripts.platformkit.improve.ingame_baseout_gate -- the AUTONOMOUS TRIGGER that
decides, leak-free, whether the deep MLB base-out / RE24 / count / pitch state
ANTICIPATES the in-play close BEYOND what the live engine's model_prob already does.

WHY (the user's "when does in-play start beating" question made testable):
  The in-game GAME channel currently MATCHES the in-play close (mean_clv ~ +0.02,
  BEAT ~= BEHIND). To cross from MATCH to BEAT we need a real conditioning signal that
  the model is NOT already using. The deep base-out state only began flowing into the
  paired tick series after the ESPN<->Kalshi id gap was closed, so the corpus that
  could prove (or kill) that lever is only now accumulating. This gate watches that
  corpus and, the MOMENT it is large enough, runs the honest test and writes a
  SHIP / REJECT / INSUFFICIENT verdict -- no human, no guessing at a date.

THE TEST (self-contained, leak-free):
  For each captured tick we have the engine's point-in-time model_prob, the live
  market_prob, and the deep state. The in-play CLOSE is the last market tick of that
  game-side (derived AFTER scoring, never handed in -- same anchor as ingame_clv_grade).
  Define the signed residual  r_t = close - model_prob_t  (= the per-tick CLV the model
  left on the table). We ask: do the deep-state features predict r_t OUT-OF-SAMPLE,
  beyond a baseline that predicts the train-mean residual?
    * Walk-forward by GAME, chronological -> never trains on a game it scores.
    * TWO independent corpora (chronological halves); a lift must replicate in BOTH
      (a single-split lift is an artifact).
    * PLANTED NULL: features shuffled within fold must COLLAPSE the lift.
  SHIP only if BOTH corpora improve RMSE, DM p < 0.05, AND the null collapses.
  Otherwise REJECT (deep state already priced) -- the EXPECTED, honest outcome.

HONEST RAILS: candidate-only (reads cache, flips NO flag, touches NO predictor);
probability space only (no $/roi/pnl/stake key); INSUFFICIENT when thin (never a
fabricated BEAT); never raises out of the public API; ASCII only; <=300 LOC.
No src.*/kernel.*/api.* imports.

CLI:  python -m scripts.platformkit.improve.ingame_baseout_gate [--sport mlb]
"""
from __future__ import annotations

import glob
import json
import logging
import math
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("ingame_baseout_gate")

_REPO = pathlib.Path(__file__).resolve().parents[3]
_GRADE_DIR = _REPO / "data" / "cache" / "ingame_grade"
VERDICT_PATH = _REPO / "data" / "frontend" / "ops" / "ingame_baseout_gate.json"

# Corpus thresholds: BOTH must clear or the verdict is the honest INSUFFICIENT.
MIN_TICKS_TOTAL = 4000
MIN_GAMES = 16          # need >= 2 chronological corpora of >= 8 games each
RIDGE_LAMBDA = 1.0      # mild L2 -- the feature block is small + collinear
_FEATS = ("outs", "base", "re", "score_diff", "inning", "balls", "strikes",
          "pitch_count", "tto")
_BANNED = ("$", "roi", "pnl", "profit", "stake", "bankroll")


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def parse_state(state_summary: str) -> Optional[Dict[str, float]]:
    """`home_score=7 away_score=1 inning=5 half=bottom outs=1 base=0 bos=3
    re=0.254 count=1-0 pitch_count=61 tto=2` -> deep feature dict, or None if the
    DEEP fields (re + base + outs) are absent (a shallow pre-id-fix tick)."""
    kv: Dict[str, str] = {}
    for tok in str(state_summary).split():
        if "=" in tok:
            k, _, v = tok.partition("=")
            kv[k] = v
    if "re" not in kv or "base" not in kv or "outs" not in kv:
        return None
    try:
        balls, strikes = 0.0, 0.0
        if "-" in kv.get("count", ""):
            b, s = kv["count"].split("-", 1)
            balls, strikes = float(b), float(s)
        hs = float(kv.get("home_score", 0.0))
        aw = float(kv.get("away_score", 0.0))
        out = {
            "outs": float(kv.get("outs", 0.0)),
            "base": float(kv.get("base", 0.0)),
            "re": float(kv.get("re", 0.0)),
            "score_diff": hs - aw,
            "inning": float(kv.get("inning", 0.0)),
            "balls": balls,
            "strikes": strikes,
            "pitch_count": float(kv.get("pitch_count", 0.0)),
            "tto": float(kv.get("tto", 0.0)),
        }
    except (TypeError, ValueError):
        return None
    return out


def _f(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_deep_ticks(sport: str = "mlb", grade_dir: Any = None) -> List[Dict[str, Any]]:
    """Every paired tick carrying deep state, with its game-side in-play close attached.

    Returns rows: {game, ts, model_prob, close, resid, feats(list)}. Leak-free: the
    close is the LAST market_prob of the same game-side, derived here after grouping.
    Games are time-ordered by first tick. Never raises.
    """
    base = pathlib.Path(grade_dir) if grade_dir is not None else _GRADE_DIR
    sdir = base / str(sport)
    by_key: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for fp in sorted(glob.glob(str(sdir / "*.jsonl"))):
        try:
            with open(fp, encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        rec = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(rec, dict):
                        continue
                    mp = _f(rec.get("market_prob"))
                    pm = _f(rec.get("model_prob"))
                    ts = rec.get("ts")
                    if mp is None or pm is None or ts is None:
                        continue
                    if not (0.0 <= mp <= 1.0 and 0.0 <= pm <= 1.0):
                        continue
                    feats = parse_state(rec.get("state_summary", ""))
                    if feats is None:
                        continue
                    gid = str(rec.get("game_id", pathlib.Path(fp).stem))
                    side = str(rec.get("side", "?"))
                    by_key.setdefault((gid, side), []).append(
                        {"ts": str(ts), "model_prob": pm, "market_prob": mp,
                         "feats": [feats[k] for k in _FEATS], "game": gid})
        except Exception as exc:  # noqa: BLE001
            logger.debug("load_deep_ticks(%s): %s", fp, exc)
            continue

    rows: List[Dict[str, Any]] = []
    for (gid, _side), series in by_key.items():
        series.sort(key=lambda t: t["ts"])
        close = series[-1]["market_prob"]      # in-play close (leak-free anchor)
        for t in series[:-1]:                  # drop the close tick (resid==0 by defn)
            rows.append({"game": gid, "ts": t["ts"], "model_prob": t["model_prob"],
                         "close": close, "resid": close - t["model_prob"],
                         "feats": t["feats"]})
    rows.sort(key=lambda r: r["ts"])
    return rows


# --------------------------------------------------------------------------- #
# Honest WF / DM machinery (numpy only)
# --------------------------------------------------------------------------- #
def _ridge_fit(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    n, d = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    A = Xb.T @ Xb + RIDGE_LAMBDA * np.eye(d + 1)
    A[0, 0] -= RIDGE_LAMBDA                       # do not penalize the intercept
    return np.linalg.solve(A, Xb.T @ y)


def _predict(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    return np.hstack([np.ones((X.shape[0], 1)), X]) @ w


def _dm_p(e_base: np.ndarray, e_cand: np.ndarray) -> float:
    """Two-sided Diebold-Mariano on squared-error loss differentials (z -> p)."""
    d = e_base ** 2 - e_cand ** 2
    n = d.size
    if n < 8 or d.std(ddof=1) == 0:
        return 1.0
    z = d.mean() / (d.std(ddof=1) / np.sqrt(n))
    # normal-tail approx (no scipy dependency)
    return float(math.erfc(abs(z) / math.sqrt(2.0)))


def _score_corpus(rows: List[Dict[str, Any]], shuffle: bool = False,
                  seed: int = 0) -> Optional[Dict[str, float]]:
    """Held-out RMSE: baseline(train-mean resid) vs ridge(feats), grouped by game.
    First chronological half of games trains; second half is scored. shuffle=True
    permutes the feature rows (planted null) -- a real lift must then collapse."""
    games = sorted({r["game"] for r in rows})
    if len(games) < 4:
        return None
    cut = len(games) // 2
    tr_g, te_g = set(games[:cut]), set(games[cut:])
    tr = [r for r in rows if r["game"] in tr_g]
    te = [r for r in rows if r["game"] in te_g]
    if len(tr) < 50 or len(te) < 50:
        return None
    Xtr = np.array([r["feats"] for r in tr], float)
    ytr = np.array([r["resid"] for r in tr], float)
    Xte = np.array([r["feats"] for r in te], float)
    yte = np.array([r["resid"] for r in te], float)
    if shuffle:
        rng = np.random.default_rng(seed)
        Xtr = Xtr[rng.permutation(Xtr.shape[0])]
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd[sd == 0] = 1.0
    w = _ridge_fit((Xtr - mu) / sd, ytr)
    pred = _predict(w, (Xte - mu) / sd)
    e_base = yte - ytr.mean()
    e_cand = yte - pred
    rmse_base = float(np.sqrt(np.mean(e_base ** 2)))
    rmse_cand = float(np.sqrt(np.mean(e_cand ** 2)))
    return {"n_test": len(te), "n_train": len(tr), "rmse_base": rmse_base,
            "rmse_cand": rmse_cand, "rmse_delta": rmse_cand - rmse_base,
            "dm_p": _dm_p(e_base, e_cand)}


def _assert_clean(d: Dict[str, Any]) -> None:
    for k in d:
        if any(b in str(k).lower() for b in _BANNED):
            raise ValueError("banned key %r violates no-dollar-field contract" % k)


# --------------------------------------------------------------------------- #
# Gate
# --------------------------------------------------------------------------- #
def gate(sport: str = "mlb", grade_dir: Any = None,
         min_ticks: int = MIN_TICKS_TOTAL, min_games: int = MIN_GAMES,
         write: bool = True) -> Dict[str, Any]:
    """Run the trigger. INSUFFICIENT until the corpus crosses (min_ticks AND
    min_games); then SHIP iff BOTH chronological corpora improve OOS RMSE with
    DM p<0.05 and the planted null collapses, else REJECT. Candidate-only."""
    rows = load_deep_ticks(sport, grade_dir=grade_dir)
    n_games = len({r["game"] for r in rows})
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    base = {"ts": ts, "sport": str(sport), "n_ticks": len(rows), "n_games": n_games,
            "min_ticks": min_ticks, "min_games": min_games, "edge_claimed": False,
            "note": ("does deep base-out/RE24/count/pitch state anticipate the in-play "
                     "close beyond model_prob? probability space; REJECT is the honest "
                     "default; SHIP = candidate lever for review, never a $ edge.")}

    if len(rows) < min_ticks or n_games < min_games:
        base["verdict"] = "INSUFFICIENT"
        base["msg"] = ("corpus still filling: %d/%d ticks, %d/%d games -- honest "
                       "can't-tell, not a beat (keep capturing)"
                       % (len(rows), min_ticks, n_games, min_games))
        return _finish(base, write)

    # Two corpora = the chronological halves of the games.
    games = sorted({r["game"] for r in rows})
    mid = len(games) // 2
    g_a, g_b = set(games[:mid]), set(games[mid:])
    rows_a = [r for r in rows if r["game"] in g_a]
    rows_b = [r for r in rows if r["game"] in g_b]
    c_a = _score_corpus(rows_a)
    c_b = _score_corpus(rows_b)
    null = _score_corpus(rows, shuffle=True, seed=7)
    if c_a is None or c_b is None or null is None:
        base["verdict"] = "INSUFFICIENT"
        base["msg"] = "corpus too thin to split into two scorable walk-forward halves"
        return _finish(base, write)

    improves = (c_a["rmse_delta"] < 0 and c_a["dm_p"] < 0.05
                and c_b["rmse_delta"] < 0 and c_b["dm_p"] < 0.05)
    null_collapses = not (null["rmse_delta"] < 0 and null["dm_p"] < 0.05)
    ship = bool(improves and null_collapses)
    base["corpus_a"] = c_a
    base["corpus_b"] = c_b
    base["planted_null"] = null
    base["null_collapses"] = bool(null_collapses)
    base["verdict"] = "SHIP_REVIEW" if ship else "REJECT"
    if ship:
        base["msg"] = ("deep base-out state improves OOS residual RMSE in BOTH corpora "
                       "(a=%.5f b=%.5f) with null collapse -- CANDIDATE lever for human "
                       "review; NOT an auto-armed edge"
                       % (c_a["rmse_delta"], c_b["rmse_delta"]))
    else:
        base["msg"] = ("deep base-out state does NOT beat the model OOS (a_delta=%.5f "
                       "p=%.3f | b_delta=%.5f p=%.3f | null_collapses=%s) -- already "
                       "priced into the live number; honest REJECT"
                       % (c_a["rmse_delta"], c_a["dm_p"], c_b["rmse_delta"],
                          c_b["dm_p"], null_collapses))
    return _finish(base, write)


def _finish(d: Dict[str, Any], write: bool) -> Dict[str, Any]:
    _assert_clean(d)
    if write:
        try:
            VERDICT_PATH.parent.mkdir(parents=True, exist_ok=True)
            VERDICT_PATH.write_text(json.dumps(d, indent=1), encoding="ascii")
        except Exception as exc:  # pragma: no cover
            logger.debug("write verdict: %s", exc)
    return d


def _main() -> int:  # pragma: no cover
    import argparse as _ap
    p = _ap.ArgumentParser(description="In-game base-out anticipation trigger gate "
                                       "(leak-free; REJECT/SHIP_REVIEW/INSUFFICIENT).")
    p.add_argument("--sport", default="mlb")
    a = p.parse_args()
    r = gate(a.sport)
    print("=" * 74)
    print("INGAME BASE-OUT GATE -- does deep state anticipate the in-play close?")
    print("=" * 74)
    print("sport      : %s" % r["sport"])
    print("corpus     : %d ticks / %d games (need %d / %d)"
          % (r["n_ticks"], r["n_games"], r["min_ticks"], r["min_games"]))
    print("verdict    : %s" % r["verdict"])
    print("msg        : %s" % r["msg"])
    print("(probability space; REJECT = already priced = honest success; no $ edge.)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["parse_state", "load_deep_ticks", "gate", "VERDICT_PATH",
           "MIN_TICKS_TOTAL", "MIN_GAMES"]
