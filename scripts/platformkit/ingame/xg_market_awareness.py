"""scripts.platformkit.ingame.xg_market_awareness -- LANE 3 item 3: THE
KILLER QUESTION. Does xg_diff improve Brier vs OUTCOME beyond what the
CONTEMPORANEOUS venue price (market_prob) already knows?

WHY THIS MATTERS: Wave-14 and this lane's cross-fit (xg_crossfit_
conditioning.py) both show xg_diff beats a score+minute-ONLY baseline. But
the venue price is not score+minute-only -- Kalshi's live quote already
prices in everything the market can see (momentum, near-misses, quality of
chances) that our score+minute model cannot. If xg_diff ALSO helps beyond
the venue price, that is meaningfully stronger evidence (the model is
catching something the market has not fully priced). If it does NOT, the
honest conclusion is narrower: our score+minute model was WORSE than the
market and xg conditioning merely helps it MATCH the market's information
set -- a real (if modest) win, but NOT a market-beating implication.

METHOD (walk-forward, leak-free, pre-declared):
* Row source: enrichment_rows_soccer.rows_fn_backfill() (same 29-game,
  5181-tick corpus as the other two LANE 3 analyses) RE-JOINED with the raw
  grade tick's market_prob by (game_id, ts) -- rows_fn_backfill's own row
  shape does not carry market_prob, so this module re-reads the raw grade
  jsonl (data/cache/ingame_grade/soccer_intl/<ticker>.jsonl, the SAME
  fresh-quote venue-price series every other analysis in this lane uses) and
  joins it back in by exact (game_id, ts) key -- no re-fetch, no new venue
  data, same file already on disk.
* WALK-FORWARD split: games sorted by their first tick's ts; walk-forward
  fold boundary = the median game (by ts) -- train on the earlier half,
  evaluate on the later half (mirrors this lane's forward-only discipline;
  never a random split for this specific analysis, since "does xg add
  beyond venue price" is a claim about GENERALIZATION forward in time, not
  cross-sectional agreement).
* Model A (market-only): logit(p) = logit(market_prob) -- the venue's own
  price, unconditioned (a fit-free identity baseline: the market's number
  IS the reference).
* Model B (market + xg): logit(p) = logit(market_prob) + gamma * xg_diff,
  gamma fit BY LEAST-SQUARES-BRIER on the train fold, frozen, scored on the
  eval fold (same golden-section fit core as xg_crossfit_conditioning.fit_beta,
  reused directly for identical fit discipline).
* Report: brier_market_only, brier_market_plus_xg (both on the eval fold),
  delta + game-clustered bootstrap CI (same _ci_delta core, seed=42).
* VERDICT: XG_ADDS_BEYOND_MARKET only if delta < 0 AND CI upper bound < 0
  (xg genuinely helps beyond what the venue already prices); otherwise
  NO_ADD_BEYOND_MARKET (xg is redundant with what the market already knows --
  the honest, market-efficient-consistent prior). MATCH_INSUFFICIENT_DATA
  below the min-games floor.

HONESTY: this NEVER claims the venue-only price beats our model or vice
versa -- it isolates ONE question (does xg add on top of venue price).
Brier/probability space only; no $/roi/pnl; edge_claimed always False; never
auto-wires into any decision path.

INVARIANTS: platformkit-only; <=300 LOC; ASCII only; no network (reads local
jsonl only); no data/registry write; no flag flip; never raises;
deterministic (fixed seed reused from ingame_enrichment_gates).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_xg_market_awareness.py -q
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.ingame.ingame_enrichment_gates import _ci_delta
from scripts.platformkit.ingame.xg_crossfit_conditioning import (
    BETA_LO, BETA_HI, conditioned_prob, fit_beta,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade" / "soccer_intl"
OUT_PATH = _REPO_ROOT / "data" / "domains" / "soccer_intl" / "xg_market_awareness.json"

MIN_GAMES = 8


def _read_market_probs(grade_dir: Path) -> Dict[Tuple[str, str], float]:
    """(game_id, ts) -> market_prob, read from the raw grade jsonl (same
    fresh-quote venue-price field every ingame grade tick already carries).
    Never raises."""
    out: Dict[Tuple[str, str], float] = {}
    try:
        if not grade_dir.is_dir():
            return out
        for gf in sorted(grade_dir.glob("*.jsonl")):
            if gf.name.startswith("_"):
                continue
            ticker = gf.stem
            try:
                with gf.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        ts, mk = rec.get("ts"), rec.get("market_prob")
                        if ts is None or mk is None:
                            continue
                        try:
                            out[(ticker, str(ts))] = float(mk)
                        except (TypeError, ValueError):
                            continue
            except Exception:  # noqa: BLE001 -- one bad file must not kill the join
                continue
    except Exception:  # noqa: BLE001
        return out
    return out


def build_rows(*, xg_rows_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None,
               grade_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Re-join enrichment_rows_soccer.rows_fn_backfill's rows with market_prob
    by exact (game_id, ts) key. A row whose (game_id, ts) has no market_prob
    match is skipped -- never imputed. Never raises."""
    if xg_rows_fn is None:
        from scripts.platformkit.ingame.enrichment_rows_soccer import rows_fn_backfill as xg_rows_fn
    gdir = Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR
    try:
        xg_rows = xg_rows_fn()
    except Exception:  # noqa: BLE001
        return []
    market = _read_market_probs(gdir)
    out: List[Dict[str, Any]] = []
    for r in xg_rows:
        gid, ts = r.get("game_id"), str(r.get("ts", ""))
        mk = market.get((gid, ts))
        xh, xa, y, mp = r.get("xg_home"), r.get("xg_away"), r.get("y"), r.get("model_prob")
        if mk is None or xh is None or xa is None or y is None or gid is None:
            continue
        out.append({
            "game_id": str(gid), "ts": ts, "y": float(y), "model_prob": mp,
            "market_prob": float(mk), "xg_diff": float(xh) - float(xa),
        })
    return out


def _first_ts_by_game(rows: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for r in rows:
        g, ts = r["game_id"], r["ts"]
        if g not in out or ts < out[g]:
            out[g] = ts
    return out


def walk_forward_split(rows: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Sort games by first-tick ts; earlier half -> train, later half ->
    eval. Deterministic (no RNG, no shuffling). Ties broken by game_id for
    stability."""
    first_ts = _first_ts_by_game(rows)
    games_sorted = sorted(first_ts.keys(), key=lambda g: (first_ts[g], g))
    mid = len(games_sorted) // 2
    train_games = set(games_sorted[:mid])
    eval_games = set(games_sorted[mid:])
    train = [r for r in rows if r["game_id"] in train_games]
    ev = [r for r in rows if r["game_id"] in eval_games]
    return train, ev


def _mean_brier_market_plus_xg(rows: Sequence[Dict[str, Any]], gamma: float) -> float:
    if not rows:
        return float("nan")
    total = 0.0
    for r in rows:
        p = conditioned_prob(r["market_prob"], r["xg_diff"], gamma)
        total += (p - r["y"]) ** 2
    return total / len(rows)


def fit_gamma(train_rows: Sequence[Dict[str, Any]]) -> float:
    """Reuses xg_crossfit_conditioning's golden-section search core, scored
    against market_prob (not model_prob) as the base rate."""
    if not train_rows:
        return 0.0
    import math
    a, b = BETA_LO, BETA_HI
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    c = b - ratio * (b - a)
    d = a + ratio * (b - a)
    fc = _mean_brier_market_plus_xg(train_rows, c)
    fd = _mean_brier_market_plus_xg(train_rows, d)
    for _ in range(60):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - ratio * (b - a)
            fc = _mean_brier_market_plus_xg(train_rows, c)
        else:
            a, c, fc = c, d, fd
            d = a + ratio * (b - a)
            fd = _mean_brier_market_plus_xg(train_rows, d)
    return (a + b) / 2.0


def _per_game_brier(eval_rows: Sequence[Dict[str, Any]], gamma: float
                    ) -> Dict[str, Tuple[float, float, int]]:
    acc: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for r in eval_rows:
        p_market = r["market_prob"]
        p_both = conditioned_prob(r["market_prob"], r["xg_diff"], gamma)
        a = acc[r["game_id"]]
        a[0] += (p_market - r["y"]) ** 2
        a[1] += (p_both - r["y"]) ** 2
        a[2] += 1
    return {g: (v[0], v[1], int(v[2])) for g, v in acc.items()}


def run_market_awareness(*, rows_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                         min_games: int = MIN_GAMES) -> Dict[str, Any]:
    """Walk-forward market-awareness check. Never raises."""
    fn = rows_fn if rows_fn is not None else build_rows
    try:
        rows = fn()
    except Exception as exc:  # noqa: BLE001
        rows = []
        err: Optional[str] = str(exc)
    else:
        err = None

    train, ev = walk_forward_split(rows)
    n_games_train = len({r["game_id"] for r in train})
    n_games_eval = len({r["game_id"] for r in ev})

    if n_games_train < min_games or n_games_eval < min_games:
        doc_body: Dict[str, Any] = {
            "verdict": "MATCH_INSUFFICIENT_DATA", "gamma_fit": None,
            "n_games_train": n_games_train, "n_games_eval": n_games_eval,
            "total_ticks_eval": len(ev), "brier_market_only": None,
            "brier_market_plus_xg": None, "brier_delta": None, "delta_ci95": None,
        }
    else:
        gamma = fit_gamma(train)
        by_game = _per_game_brier(ev, gamma)
        n_games = len(by_game)
        bb = [v[0] / v[2] for v in by_game.values()]
        bf = [v[1] / v[2] for v in by_game.values()]
        delta_g = [f - b for f, b in zip(bf, bb)]
        mean_b, mean_f = sum(bb) / n_games, sum(bf) / n_games
        delta = mean_f - mean_b
        lo, hi = _ci_delta(delta_g)
        if delta < 0 and hi < 0.0:
            verdict = "XG_ADDS_BEYOND_MARKET"
        elif delta > 0 and lo > 0.0:
            verdict = "XG_HURTS_BEYOND_MARKET"
        else:
            verdict = "NO_ADD_BEYOND_MARKET"
        doc_body = {
            "verdict": verdict, "gamma_fit": round(gamma, 6),
            "n_games_train": n_games_train, "n_games_eval": n_games_eval,
            "total_ticks_eval": sum(v[2] for v in by_game.values()),
            "brier_market_only": round(mean_b, 6),
            "brier_market_plus_xg": round(mean_f, 6),
            "brier_delta": round(delta, 6),
            "delta_ci95": [round(lo, 6), round(hi, 6)],
        }

    doc = {
        "component": "xg_market_awareness", "sport": "soccer_intl",
        "provenance": "backfill_validation",
        "family": ("Model A: logit(p)=logit(market_prob) (venue price, unconditioned). "
                  "Model B: logit(p)=logit(market_prob) + gamma*xg_diff (gamma walk-forward "
                  "fit on the earlier-games train fold, frozen, scored on the later-games "
                  "eval fold)"),
        "hypothesis": ("does xg_diff improve Brier vs OUTCOME beyond what the contemporaneous "
                      "venue price already knows -- the killer question distinguishing "
                      "'our model catches up to the market' from 'we beat the market'"),
        **doc_body,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "honest_note": ("If verdict is NO_ADD_BEYOND_MARKET: the earlier WORSE->MATCH/BETTER "
                        "findings in this lane are consistent with the venue ALREADY pricing "
                        "shot quality that our score+minute baseline missed -- our model "
                        "catching up to the venue, not beating it; no market-beating "
                        "implication either way. Brier/probability space only; no $/roi/pnl "
                        "field; edge_claimed is always False; never auto-wires into any live "
                        "decision path."),
        "edge_claimed": False,
    }
    if err is not None:
        doc["error"] = err
    return doc


def _atomic_write(path: Path, doc: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
        os.replace(str(tmp), str(path))
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    doc = run_market_awareness()
    _atomic_write(OUT_PATH, doc)
    print("xg_market_awareness | verdict=%s gamma=%s n_train=%s n_eval=%s delta=%s" % (
        doc.get("verdict"), doc.get("gamma_fit"), doc.get("n_games_train"),
        doc.get("n_games_eval"), doc.get("brier_delta")))
    print("  out: %s" % OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OUT_PATH", "MIN_GAMES", "build_rows", "walk_forward_split",
    "fit_gamma", "run_market_awareness",
]
