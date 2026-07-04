"""scripts.platformkit.ingame.ingame_tail_gate_multi -- LANE C: PRE-REGISTERED
cross-sport in-play venue-bias gate (tennis + soccer_intl / World Cup + wnba +
npb + kbo + nba), the multi-sport counterpart to ingame_tail_gate.py (MLB-only).

THE HYPOTHESES (registered at each sport's own PRE_REGISTERED_AT stamp -- see
PRE_REGISTERED_AT_BY_SPORT)
---------------------------------------------------------------------------
Mirroring the SAME bands the MLB gate pre-registered (ingame_tail_gate.py
HYPOTHESES, discovery corpus 95 games 2026-06-19..07-02) as the DEFAULT
cross-sport hypotheses is a principled choice: the underlying question --
"are longshot in-play prices underpriced and mid-favorite prices overpriced,
venue-wide, independent of sport?" -- has no reason a priori to be sport-
specific, and re-using the identical bands means confirmation on one sport is
a genuine independent replication of the MLB finding rather than a new
multiple-testing draw:

  H1  [0.10,0.20)  venue UNDERPRICES (realized rate ABOVE price) -- "longshots too cheap"
  H2  [0.65,0.80)  venue OVERPRICES  (realized rate BELOW price) -- "mid-favorites too dear"

Scored on FORWARD-captured games ONLY (first tick strictly after that sport's
own pre-registration stamp) -- never on the discovery/pre-registration sample,
exactly like the MLB gate. Each sport's verdict file starts PENDING_FORWARD
n=0 the moment this module first runs for that sport, and accumulates
evidence as its capture corpus grows (this lane does not touch any daemon hot
path -- the runner registered in ingame_tail_multi_runner.py is what actually
re-runs this per tick once wired).

PER-SPORT STAMPS (2026-07-04 LANE 5 addition; nba added same day, LANE 1)
----------------------------------------------
tennis / soccer_intl / soccer were registered 2026-07-04T00:00:00Z (unchanged
-- see PRE_REGISTERED_AT_BY_SPORT and the byte-identical regression test).
wnba / npb / kbo are registered 2026-07-04T12:00:00Z -- a FRESH, LATER stamp,
deliberately set before any of their in-play capture exists yet, so their
first captured tick is trivially forward-only from day one. nba is
registered 2026-10-01T00:00:00Z -- an NBA-season-open-safe future date, set
deliberately before any NBA in-play tick can exist (2026-27 season has not
tipped off; games.parquet's own data stops 2026-04-12), so it is trivially
forward-only by construction, same discipline as the other pre-registered
sports. A sport not listed in PRE_REGISTERED_AT_BY_SPORT falls back to
_DEFAULT_PRE_REGISTERED_AT (the original single stamp), preserving old
behavior for any future caller that adds a sport without an explicit entry.

HONESTY: venue-vs-outcome calibration only; fees/fills/adverse-selection are
NOT modeled; no $ edge is claimed; acting on a CONFIRMED verdict stays a HUMAN
decision. edge_claimed is ALWAYS False.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no network; no data/registry
write; no flag flip.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_tail_gate_multi.py -q
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.ingame.ingame_tail_scan_multi import SPORTS, scan_sport

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Original single global stamp, kept as the fallback for any sport not present
# in PRE_REGISTERED_AT_BY_SPORT (preserves the pre-refactor default exactly).
_DEFAULT_PRE_REGISTERED_AT = "2026-07-04T00:00:00Z"
PRE_REGISTERED_AT = _DEFAULT_PRE_REGISTERED_AT  # back-compat alias, unchanged value

# Per-sport pre-registration stamps. tennis/soccer_intl/soccer keep the
# ORIGINAL 2026-07-04T00:00:00Z stamp untouched (byte-identical verdict output
# is asserted by test_existing_sports_stamp_and_output_unchanged). wnba/npb/kbo
# get a fresh, later stamp -- registered BEFORE any of their capture exists --
# so evidence counts from each sport's first captured tick. nba gets an
# NBA-season-open-safe FUTURE stamp (2026-10-01, before the 2026-27 season
# tips off) -- trivially forward-only, since no NBA in-play tick can exist
# before then.
PRE_REGISTERED_AT_BY_SPORT: Dict[str, str] = {
    "tennis": _DEFAULT_PRE_REGISTERED_AT,
    "soccer_intl": _DEFAULT_PRE_REGISTERED_AT,
    "soccer": _DEFAULT_PRE_REGISTERED_AT,
    "wnba": "2026-07-04T12:00:00Z",
    "npb": "2026-07-04T12:00:00Z",
    "kbo": "2026-07-04T12:00:00Z",
    "nba": "2026-10-01T00:00:00Z",
}


def pre_registered_at_for(sport: str) -> str:
    """This sport's pre-registration stamp, falling back to the original
    single global stamp for any sport not explicitly listed above."""
    return PRE_REGISTERED_AT_BY_SPORT.get(sport, _DEFAULT_PRE_REGISTERED_AT)


HYPOTHESES: List[Dict[str, str]] = [
    {"id": "H1_longshot_underpriced", "band": "[0.10,0.20)",
     "direction": "VENUE_UNDERPRICES"},
    {"id": "H2_midfav_overpriced", "band": "[0.65,0.80)",
     "direction": "VENUE_OVERPRICES"},
]
_BASIS = ("cross-sport pre-registration mirroring the MLB discovery gate's bands "
          "(ingame_tail_gate.py: 95-game discovery corpus 2026-06-19..07-02, same-sign "
          "venue_gap + model delta_brier<0 in both md5 halves); bands are NOT re-derived "
          "per sport -- pre-registering the SAME bands cross-sport is principled and keeps "
          "this a genuine forward replication, not a new multiple-testing draw")


def _verdict_out(sport: str) -> Path:
    return _REPO_ROOT / "data" / "domains" / sport.lower() / "ingame_tail_verdict.json"


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


def run_gate_for_sport(sport: str, scan_fn: Optional[Callable[..., Dict[str, Any]]] = None,
                       pre_registered_at: Optional[str] = None,
                       verdict_out: Optional[Path] = None) -> Dict[str, Any]:
    """Run discovery + forward scans for ONE sport, judge each pre-registered
    hypothesis on the forward corpus only, write the verdict JSON, return the
    runner headline dict. Never raises -- a scan failure degrades to
    PENDING_FORWARD n=0 rather than killing the tick. *pre_registered_at*
    defaults to this sport's own stamp (PRE_REGISTERED_AT_BY_SPORT) when not
    given explicitly -- explicit callers (e.g. existing tests) keep working
    unchanged."""
    if pre_registered_at is None:
        pre_registered_at = pre_registered_at_for(sport)
    _scan = scan_fn if scan_fn is not None else (
        lambda **kw: scan_sport(sport, **kw))
    try:
        discovery = _scan()
    except Exception as exc:  # noqa: BLE001
        discovery = {"bands": {}, "n_games_resolved": 0, "n_games_graded": 0,
                     "sport_verdict": "ERROR", "error": str(exc)}
    try:
        forward = _scan(since=pre_registered_at)
    except Exception as exc:  # noqa: BLE001
        forward = {"bands": {}, "n_games_resolved": 0, "n_games_graded": 0,
                   "sport_verdict": "ERROR", "error": str(exc)}

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
    n_fwd_resolved = forward.get("n_games_resolved", 0)
    n_fwd_graded = forward.get("n_games_graded", 0)
    if n_fwd_graded == 0 and discovery.get("n_games_graded", 0) < 20:
        headline_verdict = "PENDING_FORWARD"  # honest floor: no evidence to judge yet
    elif any(v == "CONFIRMED_FORWARD" for v in verdicts):
        headline_verdict = "SHIP_REVIEW"
    elif verdicts and all(v == "REJECTED_FORWARD" for v in verdicts):
        headline_verdict = "REJECT"
    else:
        headline_verdict = "PENDING_FORWARD"
    reason = ("sport=%s forward_games=%d (graded=%d) since %s; %s" %
              (sport, n_fwd_resolved, n_fwd_graded, pre_registered_at,
               "; ".join("%s=%s" % (r["id"], r["forward_verdict"]) for r in results)))
    doc = {
        "component": "ingame_tail_gate_multi", "sport": sport,
        "pre_registered_at": pre_registered_at, "basis": _BASIS,
        "hypotheses": results, "verdict": headline_verdict, "verdict_reason": reason,
        "n_forward_games": n_fwd_resolved, "n_forward_games_graded": n_fwd_graded,
        "n_discovery_games": discovery.get("n_games_resolved", 0),
        "n_discovery_games_graded": discovery.get("n_games_graded", 0),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "honest_note": ("venue-vs-outcome calibration only; fees/fills not modeled; "
                        "no $ edge claimed; acting on CONFIRMED stays a human decision"),
        "edge_claimed": False,
    }
    out_path = Path(verdict_out) if verdict_out is not None else _verdict_out(sport)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
        os.replace(str(tmp), str(out_path))
    except Exception:  # noqa: BLE001 -- verdict write failure must not kill the tick
        pass
    return {
        "name": "ingame_tail_bands_%s" % sport, "sport": sport,
        "verdict": headline_verdict, "verdict_reason": reason, "n": n_fwd_resolved,
    }


def run_gate_all(sports: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """run_gate_for_sport for every sport in *sports* (default SPORTS). One
    sport's failure never blocks another's (each call is already internally
    guarded; this just fans out)."""
    out: List[Dict[str, Any]] = []
    for sport in (sports or SPORTS):
        out.append(run_gate_for_sport(sport))
    return out


def main() -> None:
    headlines = run_gate_all()
    print("ingame_tail_gate_multi | per-sport pre_registered_at (see PRE_REGISTERED_AT_BY_SPORT)")
    for h in headlines:
        print("  %-12s pre_registered_at=%s verdict=%s" % (
            h["sport"], pre_registered_at_for(h["sport"]), h["verdict"]))
        print("    " + h["verdict_reason"])
        print("    verdict file: %s" % _verdict_out(h["sport"]))
    print("NOTE: calibration measurement; no fees modeled; no edge claimed.")


if __name__ == "__main__":
    main()
