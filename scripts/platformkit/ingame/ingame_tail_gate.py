"""scripts.platformkit.ingame.ingame_tail_gate -- PRE-REGISTERED in-play venue-bias gate.

THE HYPOTHESES (registered 2026-07-03, from the discovery scan in ingame_tail_scan):
On the captured MLB in-play venue prices (95 graded games, 2026-06-19..07-02), two price
bands showed the SAME-SIGN venue-vs-realized gap AND model-better-Brier in BOTH md5
even/odd game halves:

  H1  [0.10,0.20)  venue UNDERPRICES (realized rate ABOVE price)   -- "longshots too cheap"
  H2  [0.65,0.80)  venue OVERPRICES  (realized rate BELOW price)   -- "mid-favorites too dear"

Because these bands were CHOSEN from that sample, the discovery sample cannot confirm
them (that would be multiple-testing).  This gate therefore scores them on FORWARD
evidence only: games whose first captured tick is AFTER REGISTERED_AT.  The m32 nightly
autogate re-runs this as the corpus grows, so confirmation (or refutation) accumulates
autonomously.

Verdicts per hypothesis (forward corpus only, game-clustered CI):
  CONFIRMED_FORWARD    band CI excludes 0 in the registered direction
  REJECTED_FORWARD     band CI excludes 0 in the OPPOSITE direction
  PENDING_FORWARD      enough games, CI still includes 0 -- keep accumulating
  INSUFFICIENT_FORWARD below the band's min-games floor

Headline verdict for m32: SHIP_REVIEW iff any hypothesis is CONFIRMED_FORWARD, else
PENDING_FORWARD (or REJECT if all are REJECTED_FORWARD).  HONESTY: venue price vs
outcome calibration only; fees/fills/adverse-selection are NOT modeled here; no $ edge
is claimed; acting on a CONFIRMED verdict stays a HUMAN decision via the greenlight
ladder.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no network; no data/registry write;
no flag flip.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_tail_gate.py -q
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VERDICT_OUT = _REPO_ROOT / "data" / "domains" / "mlb" / "ingame_tail_verdict.json"

REGISTERED_AT = "2026-07-03T00:00:00Z"
HYPOTHESES: List[Dict[str, str]] = [
    {"id": "H1_longshot_underpriced", "band": "[0.10,0.20)",
     "direction": "VENUE_UNDERPRICES"},
    {"id": "H2_midfav_overpriced", "band": "[0.65,0.80)",
     "direction": "VENUE_OVERPRICES"},
]
_BASIS = ("discovery corpus 95 games 2026-06-19..07-02: same-sign venue_gap and "
          "model delta_brier<0 in both md5 even/odd halves; bands chosen from that "
          "sample so ONLY post-registration games count as evidence")


def _judge(band_stats: Optional[Dict[str, Any]], direction: str) -> str:
    if not band_stats:
        return "INSUFFICIENT_FORWARD"
    v = band_stats.get("venue_verdict")
    if v == "INSUFFICIENT_DATA" or v is None:
        return "INSUFFICIENT_FORWARD"
    if v == direction:
        return "CONFIRMED_FORWARD"
    if v in ("VENUE_UNDERPRICES", "VENUE_OVERPRICES"):
        return "REJECTED_FORWARD"
    return "PENDING_FORWARD"


def run_gate(scan_fn: Optional[Callable[..., Dict[str, Any]]] = None,
             registered_at: str = REGISTERED_AT,
             verdict_out: Optional[Path] = None) -> Dict[str, Any]:
    """Run discovery + forward scans, judge each pre-registered hypothesis on the
    forward corpus only, write the verdict JSON, return the m32 headline dict."""
    if scan_fn is None:
        from scripts.platformkit.ingame.ingame_tail_scan import scan as scan_fn  # type: ignore
    discovery = scan_fn()
    forward = scan_fn(since=registered_at)
    results: List[Dict[str, Any]] = []
    for h in HYPOTHESES:
        fwd_band = forward.get("bands", {}).get(h["band"])
        disc_band = discovery.get("bands", {}).get(h["band"])
        results.append({
            "id": h["id"], "band": h["band"], "direction": h["direction"],
            "forward_verdict": _judge(fwd_band, h["direction"]),
            "forward_band": fwd_band, "discovery_band_reference_only": disc_band,
        })
    verdicts = [r["forward_verdict"] for r in results]
    if any(v == "CONFIRMED_FORWARD" for v in verdicts):
        headline_verdict = "SHIP_REVIEW"
    elif verdicts and all(v == "REJECTED_FORWARD" for v in verdicts):
        headline_verdict = "REJECT"
    else:
        headline_verdict = "PENDING_FORWARD"
    n_fwd = forward.get("n_games_resolved", 0)
    reason = ("forward games=%d since %s; %s" %
              (n_fwd, registered_at,
               "; ".join("%s=%s" % (r["id"], r["forward_verdict"]) for r in results)))
    doc = {
        "component": "ingame_tail_gate", "registered_at": registered_at,
        "basis": _BASIS, "hypotheses": results,
        "verdict": headline_verdict, "verdict_reason": reason,
        "n_forward_games": n_fwd,
        "n_discovery_games": discovery.get("n_games_resolved", 0),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "honest_note": ("venue-vs-outcome calibration only; fees/fills not modeled; "
                        "no $ edge claimed; acting on CONFIRMED stays a human decision"),
        "edge_claimed": False,
    }
    out_path = Path(verdict_out) if verdict_out is not None else DEFAULT_VERDICT_OUT
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
        os.replace(str(tmp), str(out_path))
    except Exception:  # noqa: BLE001 -- verdict write failure must not kill the m32 tick
        pass
    return {
        "name": "ingame_tail_bands", "verdict": headline_verdict,
        "verdict_reason": reason, "n": n_fwd,
    }


def main() -> None:
    headline = run_gate()
    print("ingame_tail_gate | verdict=%s" % headline["verdict"])
    print("  " + headline["verdict_reason"])
    print("  verdict file: %s" % DEFAULT_VERDICT_OUT)
    print("  NOTE: calibration measurement; no fees modeled; no edge claimed.")


if __name__ == "__main__":
    main()
