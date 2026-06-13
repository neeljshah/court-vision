"""scripts.research_harness.gap_observer — GapObserver: rank research gaps by coverage/info-gain.

PURPOSE: Systematic search COMPLETENESS, not profit.  Markets are efficient;
every tested family in this codebase REJECTs.  Expected outcome of any test:
REJECT.  Ranking = scientific thoroughness (coverage breadth × posterior
uncertainty), NOT expected profit.  UNTESTED != opportunity.

Scoring heuristic (transparent, documented):
  score = coverage_gap_weight × prior_uncertainty × data_penalty × settled_discount

  coverage_gap_weight : fraction of sport's candidate space that is UNTESTED; [0,1].
  prior_uncertainty   : 95% Beta-Binomial CI width for the family's ship-rate; (0,1].
                        Wide = diffuse posterior; settling it updates beliefs most.
  data_penalty        : 0.5 if previously DEFERred (data-blocked), 1.0 otherwise.
  settled_discount    : 0.20 if any REJECT recorded (already settled); 1.0 otherwise.
                        REJECT families remain listed (the ledger may have nuance)
                        but rank below genuinely unvisited candidates.

CLI:  python -m scripts.research_harness.gap_observer [--top N] [--ledger PATH]
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]

HONEST_PREAMBLE = (
    "SEARCH-COMPLETENESS RANKING — expected outcome of any test: REJECT "
    "(markets efficient; every tested family in this codebase rejects). "
    "UNTESTED != opportunity.  Ranking = scientific thoroughness only."
)

_DEFAULT_WHAT = (
    "Run the signal through the real gate (src.loop.gate) on >=2 independent "
    "corpora with FDR-corrected p<0.05 and positive forward CLV vs close. "
    "Record verdict in the ledger (SHIP or REJECT)."
)
_DEFER_WHAT = (
    "Obtain sufficient data (the previous test was DEFERred due to data "
    "insufficiency).  Then run the gate on >=2 independent corpora."
)


# ---------------------------------------------------------------------------
# Public data class
# ---------------------------------------------------------------------------

@dataclass
class RankedGap:
    """One ranked research gap.  All score components are explicit."""
    rank: int
    sport: str
    family: str
    score: float
    coverage_gap_weight: float
    prior_uncertainty: float
    data_penalty: float
    settled_discount: float
    verdict_history: List[str]
    rationale: str
    what_would_settle_it: str
    honest_note: str = field(default=HONEST_PREAMBLE)

    @property
    def is_already_rejected(self) -> bool:
        return "REJECT" in self.verdict_history

    @property
    def is_deferred(self) -> bool:
        return "DEFER" in self.verdict_history and "REJECT" not in self.verdict_history


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ci_width(store: object, sport: str, family: str) -> float:
    """95% CI width from BeliefStore; default ~0.405 (prior Beta(1,9))."""
    try:
        lo, hi = store.credible_interval(sport, family)  # type: ignore[attr-defined]
        return max(0.0, float(hi) - float(lo))
    except Exception:
        return 0.405  # prior CI [0.003, 0.408]


def _coverage_gap(sport: str, enumerator_results: Dict[str, object]) -> float:
    cr = enumerator_results.get(sport)
    if cr is None:
        return 1.0
    n = getattr(cr, "n_enumerated", 0)
    return 1.0 if n == 0 else max(0.0, 1.0 - getattr(cr, "n_tested", 0) / n)


def _family_verdicts(family: str, sport: str, findings: List[object]) -> List[str]:
    return [
        getattr(f, "verdict", "")
        for f in findings
        if getattr(f, "sport", None) == sport and getattr(f, "family", None) == family
        and getattr(f, "verdict", "")
    ]


# ---------------------------------------------------------------------------
# Core public API
# ---------------------------------------------------------------------------

def rank_gaps(
    enumerator_results: Optional[Dict[str, object]] = None,
    findings: Optional[List[object]] = None,
    belief_store: Optional[object] = None,
    top_n: Optional[int] = None,
    min_score: float = 0.0,
) -> List[RankedGap]:
    """Rank research gaps by scientific thoroughness (coverage × uncertainty).

    Parameters
    ----------
    enumerator_results : sport → CoverageResult from hypothesis_enumerator.
    findings           : list of ResearchFinding from Ledger.all_findings().
    belief_store       : BeliefStore instance (None → use prior CI widths).
    top_n              : if given, return only the top N results.
    min_score          : entries with score < min_score are excluded (default
                         0.0 = include all).  Set to 1e-9 to filter zero-score
                         entries (fully-tested+rejected) that pollute top-N.

    Returns sorted list of RankedGap, descending score.
    Honest: expected outcome of testing any gap is REJECT.
    """
    enumerator_results = enumerator_results or {}
    findings = findings or []

    # Collect (sport, family) pairs: UNTESTED from enumerator + any from ledger
    candidates: Dict[Tuple[str, str], None] = {}
    for sport, cr in enumerator_results.items():
        tested = getattr(cr, "tested_set", set())
        for cand in getattr(cr, "candidates", []):
            name = getattr(cand, "name", None)
            if name and name not in tested:
                candidates[(sport, name)] = None
    for f in findings:
        sport = getattr(f, "sport", "")
        family = getattr(f, "family", "")
        if sport and family:
            candidates.setdefault((sport, family), None)

    if not candidates:
        return []

    results: List[RankedGap] = []
    for sport, family in candidates:
        verdicts = _family_verdicts(family, sport, findings)
        has_rej = "REJECT" in verdicts
        has_def = "DEFER" in verdicts
        cov = _coverage_gap(sport, enumerator_results)
        ciw = _ci_width(belief_store, sport, family) if belief_store is not None else 0.405
        dp = 0.5 if (has_def and not has_rej) else 1.0
        sd = 0.20 if has_rej else 1.0
        score = cov * ciw * dp * sd

        note = (
            "(already REJECTED — listed for completeness)" if has_rej
            else "(previously DEFERred — data-penalised)" if has_def
            else "(UNTESTED — no prior verdict)"
        )
        rationale = (
            f"coverage_gap={cov:.3f} | ci_width={ciw:.3f} | "
            f"data_penalty={dp:.2f} | settled_discount={sd:.2f} | "
            f"=> score={score:.4f} | {note}"
        )
        results.append(RankedGap(
            rank=0,
            sport=sport,
            family=family,
            score=score,
            coverage_gap_weight=cov,
            prior_uncertainty=ciw,
            data_penalty=dp,
            settled_discount=sd,
            verdict_history=verdicts,
            rationale=rationale,
            what_would_settle_it=_DEFER_WHAT if has_def else _DEFAULT_WHAT,
        ))

    # Filter out zero/below-threshold entries (e.g. fully-tested+rejected sport
    # where coverage_gap==0 and settled_discount==0.20 collapses to score==0.0).
    results = [r for r in results if r.score >= min_score]

    results.sort(key=lambda g: (-g.score, g.sport, g.family))
    for i, g in enumerate(results):
        g.rank = i + 1

    return results[:top_n] if top_n is not None else results


def format_gaps(gaps: Sequence[RankedGap], top_n: Optional[int] = None) -> str:
    """Format ranked gaps as a human-readable report."""
    n = top_n or len(gaps)
    lines = [
        "=" * 72,
        "GapObserver — Research Gap Ranking",
        HONEST_PREAMBLE,
        f"Showing top {n} of {len(gaps)} scored gaps.",
        "=" * 72,
    ]
    for g in list(gaps)[:n]:
        lines += [
            "",
            f"Rank #{g.rank}  [{g.sport}]  {g.family}",
            f"  Score       : {g.score:.4f}",
            f"  Rationale   : {g.rationale}",
            f"  Verdicts    : {g.verdict_history or ['(none — UNTESTED)']}",
            f"  To settle   : {g.what_would_settle_it}",
        ]
    lines += [
        "",
        "=" * 72,
        "Note: UNTESTED != opportunity.  Every tested family in this",
        "codebase rejects.  Markets are efficient.",
        "=" * 72,
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI — loads real local artifacts; graceful if absent
# ---------------------------------------------------------------------------

def _load_real_artifacts(
    ledger_path: Optional[Path] = None,
) -> Tuple[Dict[str, object], List[object], Optional[object]]:
    """Load enumerator, ledger, belief store.  Each degrades gracefully."""
    try:
        from scripts.research_harness.hypothesis_enumerator import compute_all_coverage
        enumerator_results: Dict[str, object] = compute_all_coverage()
    except Exception as exc:  # pragma: no cover
        print(f"[gap_observer] enumerator unavailable: {exc}", file=sys.stderr)
        enumerator_results = {}

    findings: List[object] = []
    try:
        from scripts.research_harness.research_ledger import Ledger
        findings = Ledger(path=ledger_path).all_findings()
    except Exception as exc:  # pragma: no cover
        print(f"[gap_observer] ledger unavailable: {exc}", file=sys.stderr)

    belief_store: Optional[object] = None
    try:
        from scripts.research_harness.belief_store import BeliefStore
        bs = BeliefStore.load()
        if findings:
            bs.update_from_findings([
                {"sport": f.sport, "family": f.family,  # type: ignore[attr-defined]
                 "verdict": f.verdict, "dated": f.dated}  # type: ignore[attr-defined]
                for f in findings
            ])
        belief_store = bs
    except Exception as exc:  # pragma: no cover
        print(f"[gap_observer] belief_store unavailable: {exc}", file=sys.stderr)

    return enumerator_results, findings, belief_store


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(
        prog="gap_observer",
        description=(
            "Rank research gaps by search completeness.  "
            "Expected outcome of any test: REJECT (markets efficient).  "
            "UNTESTED != opportunity."
        ),
    )
    p.add_argument("--top", type=int, default=10, metavar="N",
                   help="Number of top gaps to display (default: 10)")
    p.add_argument("--ledger", metavar="PATH", default=None,
                   help="Path to findings.jsonl (default: data/research/findings.jsonl)")
    args = p.parse_args(argv)
    ledger_path = Path(args.ledger) if args.ledger else None
    er, findings, bs = _load_real_artifacts(ledger_path)
    gaps = rank_gaps(enumerator_results=er, findings=findings, belief_store=bs, top_n=args.top)
    if not gaps:
        print("No research gaps found (enumerator and ledger both empty).")
        return
    print(format_gaps(gaps, top_n=args.top))


if __name__ == "__main__":
    main()
