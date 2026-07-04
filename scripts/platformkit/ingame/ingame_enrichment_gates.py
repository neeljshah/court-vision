"""scripts.platformkit.ingame.ingame_enrichment_gates -- LANE 3: PRE-REGISTERED
feature-gate judges for the new enrichment data streams (soccer xG, MLB
base-out, stale-quote covariate), registered BEFORE evidence accrues -- mirrors
ingame_tail_gate_multi.py's discipline exactly (per-sport stamp, forward-only
scoring, PENDING verdict file, edge_claimed=False).

This module owns GATE A (soccer xG conditioning). GATE B (MLB base-out) lives
in ingame_enrichment_gates_mlb.py; GATE C (stale-quote covariate scoreboard
spec) lives in ingame_enrichment_gates_staleq.py -- split to stay under the
300 LOC cap, sharing this module's Brier-delta core.

GATE A HYPOTHESIS (frozen at PRE_REGISTERED_AT, soccer_intl)
--------------------------------------------------------------
Conditioning the soccer in-play model on AS-OF xG state (xg_diff = xg_home -
xg_away, sot_diff) IMPROVES Brier vs OUTCOME relative to a score+minute-only
baseline, walk-forward, scored ONLY on forward-captured ticks whose row
carries a real (non-None) enriched xG field (domains.soccer.ingame_fotmob
integration activates at restart -- no enriched tick exists before that, so
"forward" here also means "actually enriched", not merely "after the stamp").
>=2 independent corpora (an md5-parity split of forward game_ids) must agree
in SIGN before this gate can report WORSE_THAN_BASELINE / BETTER_THAN_BASELINE
-- a single-fold lift/loss is an artifact, not a finding (mirrors
ingame_outcome_verdict's per-game clustering discipline).

WHY "the WORSE->MATCH judge": the honest prior for a shallow xG conditioning
on top of an already-reasonable score+minute in-play prior is null-to-negative
(more parameters, same underlying signal, thin corpus) -- this judge exists to
CATCH that overfit/noise failure mode as WORSE_THAN_BASELINE or MATCH, and only
concede BETTER_THAN_BASELINE if the forward CI genuinely clears zero in BOTH
corpus halves. An honest WORSE/MATCH is a correct, useful result here, not a
failure of this gate.

METHOD (leak-free, mirrors ingame_outcome_verdict._seg_verdict)
------------------------------------------------------------------
* One row = one graded, enriched, forward-captured tick: {game_id, model_prob
  (baseline, score+minute), model_prob_enriched (conditioned on xg_diff/
  sot_diff), y (outcome, 0/1)}. Only rows with a resolvable outcome AND a
  non-None enriched field count -- an honest None (pre-integration, or a
  fetch/match miss) is skipped, never imputed.
* Per game: mean squared error of baseline and of enriched vs the outcome
  (game = clustering unit, matches ingame_outcome_verdict).
* Pooled delta = mean(brier_enriched) - mean(brier_baseline); game-clustered
  bootstrap 95% CI (reuses the same iters/seed convention).
* BETTER_THAN_BASELINE only when CI upper bound < 0 in BOTH md5-parity halves
  (cross-corpus agreement); WORSE_THAN_BASELINE when CI lower bound > 0 in
  either half; else MATCH. Below MIN_GAMES -> INSUFFICIENT_FORWARD.

HONESTY (binding): Brier/probability space only; no $/roi/pnl field;
edge_claimed ALWAYS False; a CONFIRMED/BETTER verdict never auto-wires into
any live decision path (mirrors ingame_sp_shadow's shadow-only contract) --
acting on it stays a human decision. Enrichment fields are MEASUREMENT-ONLY:
a poisoned/broken build degrades to permanent None, never a fabricated value.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no network; no data/registry
write; no flag flip.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_enrichment_gates.py -q
"""
from __future__ import annotations

import hashlib
import json
import os
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Frozen BEFORE any enriched tick exists (fotmob integration activates at
# restart) -- see the LANE 3 brief. Kept as a plain constant string (never
# recomputed from wall time) so re-importing this module never re-stamps it.
GATE_A_PRE_REGISTERED_AT = "2026-07-05T04:00:00Z"

MIN_GAMES = 8
MIN_TICKS = 100
EPS_DEFAULT = 0.005
_BOOTSTRAP_ITERS = 2000

Row = Dict[str, Any]
RowsFn = Callable[[], List[Row]]


def _verdict_out(sport: str, name: str = "enrichment_gate_verdict.json") -> Path:
    return _REPO_ROOT / "data" / "domains" / sport.lower() / name


def _md5_half(game_id: str) -> int:
    """Deterministic 2-way split of *game_id* for a cross-corpus parity check
    (0 or 1). Same convention referenced elsewhere in this lane (md5 parity)."""
    return int(hashlib.md5(str(game_id).encode("utf-8")).hexdigest(), 16) % 2


def _brier_by_game(rows: Sequence[Row]) -> Dict[str, Tuple[float, float, int]]:
    """game_id -> (sse_baseline, sse_enriched, n_ticks). Rows missing any
    required field (model_prob, model_prob_enriched, y) are skipped -- an
    honest gap, never imputed."""
    acc: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for r in rows:
        gid = r.get("game_id")
        mp, ep, y = r.get("model_prob"), r.get("model_prob_enriched"), r.get("y")
        if gid is None or mp is None or ep is None or y is None:
            continue
        try:
            mp_f, ep_f, y_f = float(mp), float(ep), float(y)
        except (TypeError, ValueError):
            continue
        a = acc[str(gid)]
        a[0] += (mp_f - y_f) ** 2
        a[1] += (ep_f - y_f) ** 2
        a[2] += 1
    return {gid: (a[0], a[1], int(a[2])) for gid, a in acc.items()}


def _ci_delta(per_game_delta: List[float], *, seed: int = 42) -> Tuple[float, float]:
    """Game-clustered bootstrap 95% CI for pooled per-game (enriched-baseline)
    Brier delta. Mirrors ingame_outcome_verdict._ci_delta exactly."""
    g = len(per_game_delta)
    if g == 0:
        return (0.0, 0.0)
    if g == 1:
        return (per_game_delta[0], per_game_delta[0])
    rng = random.Random(seed)
    means = sorted(
        sum(per_game_delta[rng.randrange(g)] for _ in range(g)) / g
        for _ in range(_BOOTSTRAP_ITERS)
    )
    lo = means[int(0.025 * (_BOOTSTRAP_ITERS - 1))]
    hi = means[int(0.975 * (_BOOTSTRAP_ITERS - 1))]
    return (lo, hi)


def _half_verdict(game_map: Dict[str, Tuple[float, float, int]], *,
                  eps: float, min_games: int, min_ticks: int) -> Dict[str, Any]:
    """One md5-half's verdict from {game: (sse_baseline, sse_enriched, n)}."""
    n_games = len(game_map)
    ticks = sum(v[2] for v in game_map.values())
    if n_games < min_games or ticks < min_ticks:
        return {"verdict": "INSUFFICIENT_FORWARD", "n_games": n_games,
                "total_ticks": ticks, "brier_baseline": None,
                "brier_enriched": None, "brier_delta": None, "delta_ci95": None}
    bb = [v[0] / v[2] for v in game_map.values()]
    be = [v[1] / v[2] for v in game_map.values()]
    delta_g = [e - b for e, b in zip(be, bb)]
    mean_b, mean_e = sum(bb) / n_games, sum(be) / n_games
    delta = mean_e - mean_b
    lo, hi = _ci_delta(delta_g)
    if delta < -eps and hi < 0.0:
        verdict = "BETTER_THAN_BASELINE"
    elif delta > eps and lo > 0.0:
        verdict = "WORSE_THAN_BASELINE"
    else:
        verdict = "MATCH"
    return {"verdict": verdict, "n_games": n_games, "total_ticks": ticks,
            "brier_baseline": round(mean_b, 6), "brier_enriched": round(mean_e, 6),
            "brier_delta": round(delta, 6), "delta_ci95": [round(lo, 6), round(hi, 6)]}


def judge_enrichment(rows: Sequence[Row], *, eps: float = EPS_DEFAULT,
                     min_games: int = MIN_GAMES, min_ticks: int = MIN_TICKS
                     ) -> Dict[str, Any]:
    """Two-half (md5-parity) cross-corpus judge shared by every enrichment
    gate. Returns {overall_verdict, half0, half1, n_games, n_ticks}. Never
    raises (a bad row set just yields INSUFFICIENT_FORWARD n=0)."""
    try:
        by_game = _brier_by_game(rows)
        half0 = {g: v for g, v in by_game.items() if _md5_half(g) == 0}
        half1 = {g: v for g, v in by_game.items() if _md5_half(g) == 1}
        v0 = _half_verdict(half0, eps=eps, min_games=min_games, min_ticks=min_ticks)
        v1 = _half_verdict(half1, eps=eps, min_games=min_games, min_ticks=min_ticks)
        if v0["verdict"] == "BETTER_THAN_BASELINE" and v1["verdict"] == "BETTER_THAN_BASELINE":
            overall = "BETTER_THAN_BASELINE"
        elif v0["verdict"] == "WORSE_THAN_BASELINE" or v1["verdict"] == "WORSE_THAN_BASELINE":
            overall = "WORSE_THAN_BASELINE"
        elif v0["verdict"] == "INSUFFICIENT_FORWARD" or v1["verdict"] == "INSUFFICIENT_FORWARD":
            overall = "INSUFFICIENT_FORWARD"
        else:
            overall = "MATCH"
        return {"overall_verdict": overall, "half0": v0, "half1": v1,
                "n_games": len(by_game), "n_ticks": sum(v[2] for v in by_game.values())}
    except Exception as exc:  # noqa: BLE001 -- a judging error is an honest INSUFFICIENT
        return {"overall_verdict": "INSUFFICIENT_FORWARD", "half0": None, "half1": None,
                "n_games": 0, "n_ticks": 0, "error": str(exc)}


def _default_rows_soccer_xg() -> List[Row]:
    """Production row source for GATE A: forward-captured, xG-enriched
    soccer_intl grade ticks paired with OUTCOME. LANE 4 wired this to
    enrichment_rows_soccer.build_rows, which as-of-joins captured
    soccer_intl grade ticks with fotmob xG sidecars (see that module's
    docstring for the join + naive-conditioning contract). Import is
    lazy and best-effort -- if the producer module is absent or its
    import fails for any reason, this still honestly returns [] rather
    than raising."""
    try:
        from scripts.platformkit.ingame.enrichment_rows_soccer import build_rows
        return build_rows()
    except Exception as exc:  # noqa: BLE001 -- a producer failure is an honest empty gate
        return []


def run_gate_a(rows_fn: Optional[RowsFn] = None,
              pre_registered_at: Optional[str] = None,
              verdict_out: Optional[Path] = None) -> Dict[str, Any]:
    """GATE A: soccer xG conditioning judge. Writes
    data/domains/soccer_intl/enrichment_gate_verdict.json. Never raises."""
    stamp = pre_registered_at or GATE_A_PRE_REGISTERED_AT
    _rows = rows_fn if rows_fn is not None else _default_rows_soccer_xg
    try:
        rows = _rows()
    except Exception as exc:  # noqa: BLE001
        rows = []
        judged = {"overall_verdict": "INSUFFICIENT_FORWARD", "half0": None, "half1": None,
                  "n_games": 0, "n_ticks": 0, "error": str(exc)}
    else:
        judged = judge_enrichment(rows)
    doc = {
        "component": "ingame_enrichment_gates", "gate": "A_soccer_xg", "sport": "soccer_intl",
        "pre_registered_at": stamp,
        "hypothesis": ("conditioning the soccer in-play model on as-of xG state "
                      "(xg_diff, sot_diff) improves Brier vs OUTCOME over the "
                      "score+minute-only baseline, walk-forward, on forward-captured "
                      "enriched ticks only; >=2 independent corpora (md5-parity halves) "
                      "must agree in sign"),
        "verdict": judged["overall_verdict"], "half0": judged.get("half0"),
        "half1": judged.get("half1"), "n_games": judged.get("n_games", 0),
        "n_ticks": judged.get("n_ticks", 0),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "honest_note": ("Brier vs outcome, probability space only; no $ edge claimed; "
                        "enrichment fields are measurement-only (a poisoned/broken build "
                        "degrades to permanent None); acting on a BETTER_THAN_BASELINE "
                        "verdict stays a human decision -- this gate wires no decision path"),
        "edge_claimed": False,
    }
    out_path = Path(verdict_out) if verdict_out is not None else _verdict_out("soccer_intl")
    _atomic_write(out_path, doc)
    return doc


def _atomic_write(path: Path, doc: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
        os.replace(str(tmp), str(path))
    except Exception:  # noqa: BLE001 -- verdict write failure must not kill the tick
        pass


def main() -> None:
    doc = run_gate_a()
    print("ingame_enrichment_gates | GATE A (soccer xG) pre_registered_at=%s verdict=%s "
          "n_games=%d n_ticks=%d" % (doc["pre_registered_at"], doc["verdict"],
                                     doc["n_games"], doc["n_ticks"]))
    print("  verdict file: %s" % _verdict_out("soccer_intl"))
    print("NOTE: Brier/probability space only; no fees modeled; no edge claimed.")


if __name__ == "__main__":
    main()


__all__ = [
    "GATE_A_PRE_REGISTERED_AT", "MIN_GAMES", "MIN_TICKS", "EPS_DEFAULT",
    "judge_enrichment", "run_gate_a", "_verdict_out", "_atomic_write",
]
