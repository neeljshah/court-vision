"""scripts.platformkit.econ.edge_greenlight -- pre-registered proof-of-edge
evaluator (8.1).

Evaluates the 7 pre-registered criteria from .planning/PLAN_SELF_IMPROVING_AI.md
PHASE 8.1 per channel, nightly-runnable, and reports RED / AMBER(missing which)
/ GREEN with the actual numbers behind every criterion. This module NEVER
auto-executes anything -- it is a READ-ONLY report. A GREEN verdict here pages
a human; it does not place a bet, does not flip a flag, does not write a
signoff file.

THE SEVEN CRITERIA (a channel turns GREEN iff ALL seven pass) -- full detail in
each criterion function's docstring in greenlight_criteria.py (factored out to
keep both files under the 300 LOC cap):
  (a) n >= 300 settled paper bets in the channel (>= 150 per date-parity half).
  (b) net units > 0 in BOTH independent halves.
  (c) mean CLV vs TRUE contemporaneous closes > the 6.1 cost hurdle in both
      halves, 95% CI excluding 0 (CLOSE_SUSPECT/off-market rows disqualify --
      handled upstream by clv_scoreboard's is_clv_suspect filter, reused here).
  (d) after-cost units (6.3) > 0 in both halves.
  (e) the specific segments being bet are TRUSTED (m26) AND the channel is
      TRUSTED (4.1) -- both gates, same week.
  (f) eval-gate green (no leak flag) + cv-honesty-gate adjudicates the claim
      NOT-REFUTED.
  (g) beat_the_line excess win rate CI (6.4) excludes 0 in the pooled sample.

HONEST GAPS (report, never fabricate): as of this build, (e)'s CHANNEL-trust
half (a "4.1 channel trust gate") does not exist anywhere in this repo, and
(f)'s "cv-honesty-gate that adjudicates a proof-of-edge claim NOT-REFUTED"
does not exist either -- governance/honesty_linter.py is a DIFFERENT thing (an
output-string banned-claim scanner, not a claim adjudicator). Both are reported
as criterion status NOT_BUILT, which counts as a FAILING sub-criterion -- never
silently passed. A channel that would otherwise be GREEN is therefore held at
AMBER with these two named explicitly until they are built.

Run:  python -m scripts.platformkit.econ.edge_greenlight
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from scripts.platformkit.clv_ledger import load_ledger  # canonical reader
from scripts.platformkit.clv.clv_scoreboard import _channel_of, _dedup_settled, _CHANNEL_LABEL
from scripts.platformkit.econ import greenlight_criteria as G

_OUT_JSON = os.path.join(_REPO, "data", "frontend", "ops", "edge_greenlight.json")


def evaluate_channel(channel: str, rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    criteria = {
        "a": G.criterion_a(rows),
        "b": G.criterion_b(rows),
        "c": G.criterion_c(rows),
        "d": G.criterion_d(rows),
        "e": G.criterion_e(channel),
        "f": G.criterion_f(),
        "g": G.criterion_g(rows),
    }
    failing = [k for k, c in criteria.items() if not c["passed"]]
    not_built = [k for k, c in criteria.items()
                 if "NOT_BUILT" in str(c.get("segment_trust_status", ""))
                 or "NOT_BUILT" in str(c.get("channel_trust_status", ""))
                 or "NOT_BUILT" in str(c.get("cv_honesty_gate_status", ""))]
    n_total = criteria["a"].get("n_total", 0)
    if not failing:
        status = "GREEN"
    elif n_total == 0:
        # nothing settled yet in this channel -- no evidence of any kind
        status = "RED"
    elif criteria["b"]["passed"] is False and criteria["d"]["passed"] is False:
        # actively losing BOTH gross and after-cost, both halves -- a channel
        # this system's own record says is currently anti-edge, not just
        # "not yet proven". Distinct from merely missing volume/significance.
        status = "RED"
    else:
        # has real settled volume and is not actively net-negative on both the
        # raw and after-cost record -- genuine "in progress toward GREEN",
        # blocked by specific named criteria (small-n, missing significance,
        # or the two NOT_BUILT infra gates). This is the honest AMBER case.
        status = "AMBER"
    return {
        "channel": channel,
        "label": _CHANNEL_LABEL.get(channel, channel),
        "status": status,
        "failing_criteria": failing,
        "not_built_criteria": not_built,
        "criteria": criteria,
    }


def edge_greenlight(ledger: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Build the full per-channel greenlight report dict. No auto-execution,
    ever -- read-only. The only non-pure step is one cached in-process offline
    eval-gate run inside criterion_f (no network, no real corpus scan).
    """
    if ledger is None:
        ledger = load_ledger()
    settled = _dedup_settled(ledger)
    by_ch: Dict[str, List[Dict[str, Any]]] = {}
    for r in settled:
        by_ch.setdefault(_channel_of(r), []).append(r)

    channels: Dict[str, Any] = {}
    for ch, rows in by_ch.items():
        try:
            channels[ch] = evaluate_channel(ch, rows)
        except Exception as exc:  # noqa: BLE001 -- one bad channel must not kill the report
            channels[ch] = {"channel": ch, "label": _CHANNEL_LABEL.get(ch, ch),
                             "status": "RED", "error": "%s: %s" % (type(exc).__name__, exc),
                             "failing_criteria": ["a", "b", "c", "d", "e", "f", "g"],
                             "not_built_criteria": [], "criteria": {}}
    return {"channels": channels, "note": "READ-ONLY report; never auto-executes."}


def render(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("=" * 78)
    lines.append("EDGE GREENLIGHT -- pre-registered proof-of-edge criteria (8.1)")
    lines.append("READ-ONLY: a GREEN status pages a human, it places no order.")
    lines.append("=" * 78)
    for ch in sorted(report["channels"], key=lambda c: report["channels"][c]["status"]):
        c = report["channels"][ch]
        lines.append("")
        lines.append("%-20s status=%s" % (c["label"], c["status"]))
        if c.get("error"):
            lines.append("    ERROR: %s" % c["error"])
            continue
        for k in "abcdefg":
            crit = c["criteria"].get(k)
            if not crit:
                continue
            mark = "PASS" if crit["passed"] else "FAIL"
            lines.append("    (%s) %-4s %s" % (k, mark, crit.get("detail", "")))
        if c["not_built_criteria"]:
            lines.append("    NOT_BUILT infra blocking: %s"
                         % ", ".join(sorted(c["not_built_criteria"])))
    lines.append("")
    lines.append("=" * 78)
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    report = edge_greenlight()
    print(render(report))
    try:
        os.makedirs(os.path.dirname(_OUT_JSON), exist_ok=True)
        with open(_OUT_JSON, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1)
        print("\nwrote %s" % _OUT_JSON)
    except OSError as exc:
        print("(edge_greenlight JSON not written: %s)" % type(exc).__name__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
