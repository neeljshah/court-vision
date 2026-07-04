"""scripts.platformkit.ingame.ingame_enrichment_gates_mlb -- GATE B: MLB
base-out/count live-state enrichment judge (LANE 3, feature-gate
pre-registration). Sibling to ingame_enrichment_gates.py's GATE A (soccer
xG); reuses its shared judge_enrichment() Brier-delta core so both gates
score identically (per-game clustering, md5-parity cross-corpus halves,
game-clustered bootstrap CI).

GATE B HYPOTHESIS (frozen at PRE_REGISTERED_AT, mlb)
--------------------------------------------------------------
Conditioning the MLB in-play model on the live base_out_state (outs +
baserunners, via ingame_baseout_mlb.parse_baseout's base_out_state in [0,23]
and its RE24 run_expectancy) IMPROVES Brier vs OUTCOME relative to a
score+inning-only baseline, walk-forward, scored ONLY on forward-captured
ticks whose row carries a real (non-None) base_out_state (ingame_baseout_mlb
is already wired additively into ingame_live_state._extract, so MLB ticks
captured after this stamp already carry outs/base/bos/re -- unlike GATE A this
gate's enrichment source is ALREADY LIVE, not pending a future wire; this gate
is judge-first: it can start scoring the moment forward MLB grade rows exist
with a non-None `bos` field). >=2 independent corpora (md5-parity halves of
forward game_ids) must agree in sign, mirroring GATE A exactly.

METHOD: identical to GATE A (see ingame_enrichment_gates.judge_enrichment
docstring) -- per-game MSE of baseline vs enriched model_prob against the
resolved OUTCOME (MlbOutcomeResolver.home_win, ticker-keyed), pooled delta,
game-clustered bootstrap 95% CI, BETTER only when BOTH halves' CI clears
zero, WORSE when either half's CI lower bound > 0, else MATCH.
Below MIN_GAMES/MIN_TICKS -> INSUFFICIENT_FORWARD (honest floor).

HONESTY (binding): Brier/probability space only; no $/roi/pnl; edge_claimed
ALWAYS False; a BETTER_THAN_BASELINE verdict never auto-wires any decision
path -- acting on it stays a human call. base_out_state/run_expectancy are
MEASUREMENT-ONLY fields (ingame_baseout_mlb docstring: "NOT wired into the
gated live model here"); this gate does not change that.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no network; no data/registry
write; no flag flip.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_enrichment_gates_mlb.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.ingame.ingame_enrichment_gates import (
    _atomic_write, _verdict_out, judge_enrichment,
)

# Frozen BEFORE any forward-graded, base_out-enriched MLB tick is scored by
# THIS gate (base_out capture itself is already live via ingame_live_state,
# but no grade row has yet been paired through this judge -- see docstring).
GATE_B_PRE_REGISTERED_AT = "2026-07-05T04:00:00Z"

Row = Dict[str, Any]
RowsFn = Callable[[], List[Row]]


def _default_rows_mlb_baseout() -> List[Row]:
    """Production row source for GATE B: forward-captured MLB grade ticks
    paired with a resolved OUTCOME and a non-None base_out_state-conditioned
    model_prob_enriched. No wired producer exists yet (this gate is
    judge-first, per the module docstring) -- honestly returns [] until a
    future lane pairs live_grade rows through a base-out-conditioned model
    variant. Never raises."""
    return []


def run_gate_b(rows_fn: Optional[RowsFn] = None,
              pre_registered_at: Optional[str] = None,
              verdict_out: Optional[Path] = None) -> Dict[str, Any]:
    """GATE B: MLB base-out conditioning judge. Writes
    data/domains/mlb/enrichment_gate_verdict.json. Never raises."""
    stamp = pre_registered_at or GATE_B_PRE_REGISTERED_AT
    _rows = rows_fn if rows_fn is not None else _default_rows_mlb_baseout
    try:
        rows = _rows()
        judged = judge_enrichment(rows)
    except Exception as exc:  # noqa: BLE001
        judged = {"overall_verdict": "INSUFFICIENT_FORWARD", "half0": None, "half1": None,
                  "n_games": 0, "n_ticks": 0, "error": str(exc)}
    doc = {
        "component": "ingame_enrichment_gates_mlb", "gate": "B_mlb_baseout", "sport": "mlb",
        "pre_registered_at": stamp,
        "hypothesis": ("conditioning the MLB in-play model on live base_out_state "
                      "(outs+baserunners, RE24 run_expectancy) improves Brier vs "
                      "OUTCOME over the score+inning-only baseline, walk-forward, on "
                      "forward-captured enriched ticks only; >=2 independent corpora "
                      "(md5-parity halves) must agree in sign"),
        "verdict": judged["overall_verdict"], "half0": judged.get("half0"),
        "half1": judged.get("half1"), "n_games": judged.get("n_games", 0),
        "n_ticks": judged.get("n_ticks", 0),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "honest_note": ("Brier vs outcome, probability space only; no $ edge claimed; "
                        "base_out_state/run_expectancy are measurement-only fields "
                        "(not wired into the live gated model); acting on a "
                        "BETTER_THAN_BASELINE verdict stays a human decision"),
        "edge_claimed": False,
    }
    out_path = Path(verdict_out) if verdict_out is not None else _verdict_out("mlb")
    _atomic_write(out_path, doc)
    return doc


def main() -> None:
    doc = run_gate_b()
    print("ingame_enrichment_gates_mlb | GATE B (MLB base-out) pre_registered_at=%s "
          "verdict=%s n_games=%d n_ticks=%d" % (doc["pre_registered_at"], doc["verdict"],
                                                doc["n_games"], doc["n_ticks"]))
    print("  verdict file: %s" % _verdict_out("mlb"))
    print("NOTE: Brier/probability space only; no fees modeled; no edge claimed.")


if __name__ == "__main__":
    main()


__all__ = ["GATE_B_PRE_REGISTERED_AT", "run_gate_b"]
