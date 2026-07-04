"""scripts.platformkit.ingame.ingame_enrichment_gates_staleq -- GATE C: the
stale-quote covariate SCOREBOARD comparison (LANE 3, feature-gate
pre-registration). Unlike GATE A/B this is NOT a Brier model-conditioning
gate -- it is a registered MEASUREMENT COMPARISON: does filtering venue-
comparison verdicts (e.g. ingame_outcome_verdict's BETTER/WORSE/MATCH-vs-
venue-price segments) by ingame_book_depth.stale_quote_flag change the
conclusion versus quote_freshness.py's existing price-changed heuristic?

GATE C HYPOTHESIS (frozen at PRE_REGISTERED_AT, cross-sport scoreboard row)
--------------------------------------------------------------------------
ingame_book_depth.py's module docstring (WIRE SPEC item 2) already names the
exact comparison: quote_freshness's heuristic is SYNTACTIC on the derived
probability only (is this tick's market_prob != the previous tick's, for the
same game); stale_quote_flag is a STRICTLY STRONGER signal (also requires a
wide >50bp spread) so it can only ever TIGHTEN or CONFIRM a freshness-gated
verdict, never manufacture a new one. This gate PRE-REGISTERS that exact
comparison as a scoreboard row -- for each (sport, segment) pair already
scored by ingame_outcome_verdict_freshness.py, record whether the raw and
depth-enriched (stale_quote_flag-filtered) fresh-only arms AGREE or DISAGREE
on verdict, and if they disagree, in which direction (depth filter flips a
verdict FROM or TO BETTER/WORSE/MATCH). This is a comparison of two ALREADY-
SCORED arms, not a new model -- there is no "improves Brier" claim here, only
"does this covariate change which segments we'd trust."

WHY registered now, before depth-enriched ticks exist: ingame_book_depth.py's
poller (ingame_book_depth_poller.py) is a standalone sidecar not yet joined
to any grade row (see its WIRE SPEC step 1: is_fresh currently hardcoded True
in inplay_capture_loop). Pre-registering the comparison spec now means the
scoreboard fills in mechanically once that join lands, with zero new judgment
calls introduced after data starts accruing.

STATUS: PENDING until depth-enriched ticks exist (n=0 by construction --
scoreboard_rows() honestly returns [] when no (sport, segment) pair has both
a raw AND a depth-filtered fresh-only verdict to compare). This is a
SCOREBOARD spec, not a SHIP/REJECT gate -- its verdict field is always
"PENDING" until real rows exist; there is no CONFIRMED/REJECTED state for a
measurement comparison.

HONESTY (binding): comparison of two calibration measurements; no $/roi/pnl;
edge_claimed ALWAYS False; this module wires no decision path and flips no
flag -- it only registers what will be compared once data exists.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no network; no data/registry
write; no flag flip.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_enrichment_gates_staleq.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.ingame.ingame_enrichment_gates import _atomic_write, _verdict_out

# Frozen BEFORE any depth-enriched (stale_quote_flag-joined) verdict exists --
# ingame_book_depth's own docstring dates its keyless-venue verification
# 2026-07-04; this stamp is deliberately AFTER that so the comparison spec
# predates any join between depth rows and outcome-verdict segments.
GATE_C_PRE_REGISTERED_AT = "2026-07-05T04:00:00Z"

Row = Dict[str, Any]
RowsFn = Callable[[], List[Row]]


def _default_rows_stale_quote() -> List[Row]:
    """Production row source for GATE C: one dict per (sport, segment) pair
    that has BOTH a raw-arm verdict and a stale_quote_flag-filtered fresh-only
    verdict already computed (from ingame_outcome_verdict_freshness /
    ingame_freshness_cross_corpus once depth-joined). No such join exists yet
    (see module docstring) -- honestly returns [] until it does. Never raises."""
    return []


def scoreboard_rows(raw_by_sport_segment: Dict[str, Dict[str, str]],
                    depth_filtered_by_sport_segment: Dict[str, Dict[str, str]]
                    ) -> List[Dict[str, Any]]:
    """Build one comparison row per (sport, segment) present in BOTH maps
    (each maps sport -> {segment: verdict_str}). Never raises; a malformed
    input just yields fewer/no rows rather than a crash."""
    rows: List[Dict[str, Any]] = []
    try:
        for sport, segs in raw_by_sport_segment.items():
            depth_segs = depth_filtered_by_sport_segment.get(sport) or {}
            for seg, raw_verdict in segs.items():
                if seg not in depth_segs:
                    continue
                depth_verdict = depth_segs[seg]
                rows.append({
                    "sport": sport, "segment": seg,
                    "raw_verdict": raw_verdict, "depth_filtered_verdict": depth_verdict,
                    "agree": raw_verdict == depth_verdict,
                    "flip": None if raw_verdict == depth_verdict
                            else "%s->%s" % (raw_verdict, depth_verdict),
                })
    except Exception:  # noqa: BLE001 -- a malformed input degrades to fewer rows, never a raise
        pass
    return rows


def run_gate_c(rows_fn: Optional[RowsFn] = None,
              pre_registered_at: Optional[str] = None,
              verdict_out: Optional[Path] = None) -> Dict[str, Any]:
    """GATE C: stale-quote covariate scoreboard spec. Writes
    data/domains/soccer_intl/enrichment_gate_verdict_staleq.json (a distinct
    file from GATE A's, since GATE C is cross-sport and not a per-sport
    model-conditioning verdict). Never raises."""
    stamp = pre_registered_at or GATE_C_PRE_REGISTERED_AT
    _rows = rows_fn if rows_fn is not None else _default_rows_stale_quote
    try:
        rows = _rows()
    except Exception:  # noqa: BLE001
        rows = []
    n_disagree = sum(1 for r in rows if not r.get("agree", True))
    doc = {
        "component": "ingame_enrichment_gates_staleq", "gate": "C_stale_quote_covariate",
        "sport": "cross_sport", "pre_registered_at": stamp,
        "hypothesis": ("filtering venue-comparison verdicts by "
                      "ingame_book_depth.stale_quote_flag changes the conclusion vs "
                      "quote_freshness.py's existing price-changed heuristic (a "
                      "measurement comparison of two already-scored arms, not a new "
                      "model gate); PENDING until depth-enriched ticks exist"),
        "verdict": "PENDING", "rows": rows, "n_rows": len(rows), "n_disagree": n_disagree,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "honest_note": ("scoreboard comparison only, not a SHIP/REJECT model gate; "
                        "no $ edge claimed; wires no decision path"),
        "edge_claimed": False,
    }
    out_path = (Path(verdict_out) if verdict_out is not None
                else _verdict_out("soccer_intl", "enrichment_gate_verdict_staleq.json"))
    _atomic_write(out_path, doc)
    return doc


def main() -> None:
    doc = run_gate_c()
    print("ingame_enrichment_gates_staleq | GATE C (stale-quote covariate) "
          "pre_registered_at=%s verdict=%s n_rows=%d n_disagree=%d"
          % (doc["pre_registered_at"], doc["verdict"], doc["n_rows"], doc["n_disagree"]))
    print("  verdict file: %s" % _verdict_out("soccer_intl", "enrichment_gate_verdict_staleq.json"))
    print("NOTE: measurement comparison only; no fees modeled; no edge claimed.")


if __name__ == "__main__":
    main()


__all__ = ["GATE_C_PRE_REGISTERED_AT", "scoreboard_rows", "run_gate_c"]
