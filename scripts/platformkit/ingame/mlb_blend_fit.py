"""scripts.platformkit.ingame.mlb_blend_fit -- fit + gate a per-(time,margin) MLB blend surface.

mlb_live_model._MLB_SURFACE is MARGIN-BLIND: its grid weight w = _W_BY_TIME[t] is the same for
every run-margin bucket, so a big deficit early in the game keeps ~60% weight on the pregame
prior. This module walk-forward FITS a per-(time,margin) cell weight from the real logged MLB
in-game corpus (data/cache/ingame_grade_joined/mlb/*.jsonl) and GATES the fit out-of-sample
before it is allowed to touch production.

REUSES, never reimplements:
  * blend math        -> eval_gate.ingame_blend.{blend, time_bucket, margin_bucket}
  * score-anchor p_live -> ingame.blend_apply._p_live_from_anchor (SAME Gaussian anchor
    mlb_live_model uses via apply_surface; untouched here).
  * bucketing shape    -> mlb_live_model._N_TIME / _N_MARGIN / margin_edges_abs / _W_BY_TIME
    (the flat baseline AND the fallback value for sparse fitted cells).
  * clustered bootstrap -> the same per-game resample pattern as
    inplay_aggregate_grade._cluster_bootstrap_ci (imported directly).

HONEST (binding): p0 IS NOT LOGGED per-tick in this corpus. p0_source is DECLARED in the
artifact: 'first_tick_model_prob_proxy' (the game's earliest logged model_prob tick, which at
inning-1-top already carries only ~12% live weight -- the closest available proxy for the
pregame prior; a real pregame-service join was checked and rejected, see NOTE below). This is
a CALIBRATION exercise, never a $ edge -- edge_claimed is always False. The candidate artifact
NEVER auto-ships: mlb_live_model.py is untouched by this module.

NOTE: data/frontend/predict_service/mlb/latest.json uses a DIFFERENT game_id namespace
(fd:NNNN) and only covers the current slate, not this corpus's date range -- no reliable
join key exists, hence the first-tick proxy.

INVARIANTS: build only under scripts/platformkit/; never edit src/, kernel/, or the ingame
blend/model files this reuses; ASCII; <=300 LOC; pure except for reading the corpus + writing
the candidate artifact.
"""
from __future__ import annotations

import argparse
import glob
import json
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.eval_gate.ingame_blend import blend, margin_bucket, time_bucket
from scripts.platformkit.ingame.blend_apply import _p_live_from_anchor
from scripts.platformkit.ingame.inplay_aggregate_grade import _cluster_bootstrap_ci
from scripts.platformkit.ingame.mlb_live_model import _MLB_SURFACE, _N_MARGIN, _N_TIME, _W_BY_TIME

EDGE_CLAIMED = False
_STATE_RE = re.compile(r"home_score=([\-\d.]+) away_score=([\-\d.]+) inning=(\d+) half=(\w+)")
_MARGIN_EDGES = _MLB_SURFACE["margin_edges_abs"]
_MARGIN_SIGMA = _MLB_SURFACE["margin_sigma"]
_FRAC_CEIL = 0.999
_MIN_CELL_N = 50
_MIN_EVAL_GAMES = 10
_MIN_EVAL_TICKS = 200
_W_GRID = np.linspace(0.0, 1.0, 21)


def _frac_mlb(inning: int, half: str) -> float:
    """9-inning-regulation freshness lever, SAME formula as mlb_live_model's caller."""
    h = 1 if half == "top" else 2
    return max(0.0, min(_FRAC_CEIL, (2 * (inning - 1) + h) / 18.0))


def _load_rows(corpus_dir: Path) -> List[Dict[str, Any]]:
    """Parse each jsonl tick into a row carrying every field the fit/gate needs."""
    rows: List[Dict[str, Any]] = []
    for f in sorted(glob.glob(str(corpus_dir / "*.jsonl"))):
        with open(f, "r") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                m = _STATE_RE.search(d.get("state_summary", "") or "")
                if not m or d.get("outcome") is None or d.get("model_prob") is None:
                    continue
                hs, aw, inn, half = float(m.group(1)), float(m.group(2)), int(m.group(3)), m.group(4)
                rows.append({
                    "game_id": d.get("game_id"), "ts": d.get("ts", ""),
                    "run_diff": hs - aw, "inning": inn,
                    "outcome": float(d["outcome"]), "market_prob": d.get("market_prob"),
                    "model_prob": float(d["model_prob"]),
                    "frac_elapsed": _frac_mlb(inn, half),
                })
    return rows


def _attach_derived(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach per-game p0 proxy (first tick's model_prob) + bucket/date/p_live fields."""
    by_game: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_game.setdefault(r["game_id"], []).append(r)
    out: List[Dict[str, Any]] = []
    for gid, grows in by_game.items():
        grows.sort(key=lambda r: r["ts"])
        p0 = grows[0]["model_prob"]
        date = (grows[0]["ts"] or "")[:10]
        for r in grows:
            remaining_frac = 1.0 - r["frac_elapsed"]
            sec_rem = 100.0 * remaining_frac
            t = time_bucket(sec_rem, total=100.0, n=_N_TIME)
            m = margin_bucket(r["run_diff"], edges=_MARGIN_EDGES)
            m = min(m, _N_MARGIN - 1)
            p_live = _p_live_from_anchor(r["run_diff"], remaining_frac, {"margin_sigma": _MARGIN_SIGMA})
            out.append({**r, "date": date, "p0": p0, "t": t, "m": m, "p_live": p_live})
    return out


def _split_by_date(rows: List[Dict[str, Any]], fit_frac: float = 0.6
                   ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Walk-forward split: earliest `fit_frac` of DISTINCT game dates -> fit, rest -> eval."""
    dates = sorted({r["date"] for r in rows})
    cut = dates[max(1, int(len(dates) * fit_frac)) - 1] if dates else ""
    fit_rows = [r for r in rows if r["date"] <= cut]
    eval_rows = [r for r in rows if r["date"] > cut]
    return fit_rows, eval_rows


def _fit_grid(fit_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Fit w per (t,m) cell minimizing blend Brier on fit_rows; sparse cells -> flat baseline."""
    cells: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for r in fit_rows:
        cells.setdefault((r["t"], r["m"]), []).append(r)
    grid: Dict[str, Dict[str, Any]] = {}
    for t in range(_N_TIME):
        for m in range(_N_MARGIN):
            rows = cells.get((t, m), [])
            key = "%d,%d" % (t, m)
            flat_w = _W_BY_TIME[t]
            if len(rows) < _MIN_CELL_N:
                grid[key] = {"w": flat_w, "n": len(rows), "source": "flat_fallback"}
                continue
            p0 = np.array([r["p0"] for r in rows])
            pl = np.array([r["p_live"] for r in rows])
            y = np.array([r["outcome"] for r in rows])
            best_w, best_b = flat_w, float(np.mean((flat_w * pl + (1 - flat_w) * p0 - y) ** 2))
            for w in _W_GRID:
                b = float(np.mean((w * pl + (1 - w) * p0 - y) ** 2))
                if b < best_b:
                    best_b, best_w = b, float(w)
            grid[key] = {"w": best_w, "n": len(rows), "source": "fitted"}
    return grid


def _weight_of(grid: Dict[str, Dict[str, Any]], t: int, m: int) -> float:
    return grid["%d,%d" % (t, m)]["w"]


def _loss_delta(eval_rows: List[Dict[str, Any]], fitted_grid: Dict[str, Dict[str, Any]]
                ) -> List[Tuple[str, float]]:
    """Per-tick (game_id, flat_loss - fitted_loss) -- positive = fitted improves."""
    out = []
    for r in eval_rows:
        w_flat = _W_BY_TIME[r["t"]]
        w_fit = _weight_of(fitted_grid, r["t"], r["m"])
        p_flat = blend(r["p0"], r["p_live"], w_flat)
        p_fit = blend(r["p0"], r["p_live"], w_fit)
        y = r["outcome"]
        out.append((r["game_id"], (p_flat - y) ** 2 - (p_fit - y) ** 2))
    return out


def _per_game_mean(deltas: List[Tuple[str, float]]) -> List[float]:
    by_game: Dict[str, List[float]] = {}
    for gid, d in deltas:
        by_game.setdefault(gid, []).append(d)
    return [float(np.mean(v)) for v in by_game.values()]


def _summarize(deltas: List[Tuple[str, float]]) -> Dict[str, Any]:
    n_games = len({gid for gid, _ in deltas})
    per_game = _per_game_mean(deltas)
    mean_delta = float(np.mean(per_game)) if per_game else 0.0
    lo, hi = _cluster_bootstrap_ci(per_game, iters=2000, seed=0) if per_game else (0.0, 0.0)
    return {"n_ticks": len(deltas), "n_games": n_games, "mean_delta": mean_delta,
            "ci95": [lo, hi]}


def gate(eval_rows: List[Dict[str, Any]], fitted_grid: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Leak-free eval-split gate: fitted vs flat, |run_diff|>=4 must improve, overall must not regress."""
    n_games = len({r["game_id"] for r in eval_rows})
    if n_games < _MIN_EVAL_GAMES or len(eval_rows) < _MIN_EVAL_TICKS:
        return {"verdict": "INSUFFICIENT", "reason": "eval split too small (n_games=%d n_ticks=%d)"
                % (n_games, len(eval_rows))}

    def _breakdown(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        deltas = _loss_delta(rows, fitted_grid)
        big = [(g, d) for (g, d), r in zip(deltas, rows) if abs(r["run_diff"]) >= 4]
        return {"overall": _summarize(deltas), "rd_ge4": _summarize(big)}

    with_inn7 = _breakdown(eval_rows)
    excl_inn7 = _breakdown([r for r in eval_rows if r["inning"] < 7])

    def _verdict(b: Dict[str, Any]) -> str:
        rd = b["rd_ge4"]
        ov = b["overall"]
        if rd["n_games"] < 3:
            return "INSUFFICIENT"
        rd_improves = rd["ci95"][0] > 0.0
        overall_ok = ov["ci95"][1] >= 0.0  # not significantly negative
        return "PASS" if (rd_improves and overall_ok) else "FAIL"

    return {"verdict": _verdict(with_inn7), "with_inn_ge7": with_inn7,
            "excl_inn_ge7": excl_inn7, "verdict_excl_inn_ge7": _verdict(excl_inn7)}


def fit_and_gate(corpus_dir: Path) -> Dict[str, Any]:
    """End-to-end: load -> derive -> walk-forward split -> fit on FIT -> gate on EVAL."""
    raw = _load_rows(corpus_dir)
    rows = _attach_derived(raw)
    fit_rows, eval_rows = _split_by_date(rows)
    fitted_grid = _fit_grid(fit_rows)
    gate_result = gate(eval_rows, fitted_grid)
    dates = sorted({r["date"] for r in rows})
    return {
        "as_of": dates[-1] if dates else None,
        "p0_source": "first_tick_model_prob_proxy",
        "fit_dates": [dates[0], sorted({r["date"] for r in fit_rows})[-1]] if fit_rows else [],
        "eval_dates": [sorted({r["date"] for r in eval_rows})[0], dates[-1]] if eval_rows else [],
        "n_time": _N_TIME, "n_margin": _N_MARGIN,
        "grid": fitted_grid,
        "flat_baseline": {str(t): _W_BY_TIME[t] for t in range(_N_TIME)},
        "gate": gate_result,
        "honest_note": ("Candidate never auto-ships; mlb_live_model.py is untouched. Label "
                        "noise caveat: late-inning (inn>=7) down-side labels in this corpus "
                        "look stale -- gate is reported both with and without inn>=7 ticks."),
        "edge_claimed": EDGE_CLAIMED,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus-dir", default="data/cache/ingame_grade_joined/mlb")
    ap.add_argument("--out", default="data/cache/models/mlb_blend_surface_candidate.json")
    args = ap.parse_args()
    result = fit_and_gate(Path(args.corpus_dir))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))
    print("verdict=%s -> %s" % (result["gate"].get("verdict"), out_path))


if __name__ == "__main__":
    main()
