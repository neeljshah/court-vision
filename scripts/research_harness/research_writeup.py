"""research_writeup.py — Render a ResearchLedger as a human-readable markdown note.

The generated note explicitly states the all-REJECT / market-efficient thesis
and never implies a betting edge.  REJECT findings are highlighted, not hidden.

Usage (functional):
    from scripts.research_harness.research_ledger import Ledger
    from scripts.research_harness.research_writeup import render_writeup

    md = render_writeup(Ledger())
    print(md)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Union

# ---------------------------------------------------------------------------
# Lazy import so this module is usable in test without installing the package
# ---------------------------------------------------------------------------
from pathlib import Path as _Path
import sys as _sys

_HERE = _Path(__file__).resolve().parent
if str(_HERE) not in _sys.path:
    _sys.path.insert(0, str(_HERE))

from research_ledger import Ledger, ResearchFinding, VALID_VERDICTS  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HONEST_HEADER = """\
# Research Findings — Quant Signal Catalog

> **Thesis:** Across all tested sport domains and signal families the hypothesis
> market efficiency holds: no signal family has produced a repeatable,
> FDR-corrected positive-CLV edge on out-of-sample corpora.  REJECT verdicts
> are compiled here as first-class, durable knowledge — they prevent wasted
> effort and constrain future hypotheses.
>
> **NO EDGE IS CLAIMED.** A SHIP verdict would mean the gate passed the signal
> under full honest-gate discipline (≥2 independent corpora, FDR-corrected
> p < 0.05, positive CLV vs real closing lines).  Until then every verdict is
> market-efficient-until-proven-otherwise.
"""

_VERDICT_EMOJI: Dict[str, str] = {
    "REJECT": "REJECT",
    "DEFER":  "DEFER",
    "SHIP":   "SHIP",
}


# ---------------------------------------------------------------------------
# Core render
# ---------------------------------------------------------------------------

def render_writeup(
    source: Union[Ledger, List[ResearchFinding]],
    title: Optional[str] = None,
    generated_by: str = "research_writeup.py",
    belief_store: Optional[object] = None,
    gaps: Optional[List] = None,
) -> str:
    """Render research findings as a markdown document.

    Parameters
    ----------
    source        : a Ledger instance or a plain list of ResearchFinding objects
    title         : optional custom title (replaces default header title line)
    generated_by  : attribution string in the footer
    belief_store  : optional BeliefStore instance; when supplied, each family
                    row also shows its posterior ship-rate mean + 95% CI.
                    When None (default), existing behaviour is unchanged.
                    P(ship) is a historical ship-rate prior, NOT an edge claim.
    gaps          : optional list of RankedGap from gap_observer.rank_gaps.
                    When supplied, a "Highest-Value Next Questions" section is
                    appended.  When None (default), the section is omitted and
                    existing behaviour is unchanged.  UNTESTED != opportunity;
                    ranking reflects search completeness, not expected profit.

    Returns
    -------
    str : full markdown document
    """
    findings: List[ResearchFinding]
    if isinstance(source, Ledger):
        findings = source.all_findings()
    else:
        findings = list(source)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Group by sport → family order
    by_sport: Dict[str, List[ResearchFinding]] = {}
    for f in findings:
        by_sport.setdefault(f.sport, []).append(f)

    lines: List[str] = []

    # Header
    if title:
        lines.append(f"# {title}\n")
    else:
        lines.append(_HONEST_HEADER)

    lines.append(f"*Generated: {now} · {len(findings)} findings · {generated_by}*\n")

    # Summary table
    counts: Dict[str, int] = {v: 0 for v in VALID_VERDICTS}
    for f in findings:
        counts[f.verdict] = counts.get(f.verdict, 0) + 1
    lines.append("## Summary\n")
    lines.append("| Verdict | Count |")
    lines.append("|---------|-------|")
    for v in ["REJECT", "DEFER", "SHIP"]:
        lines.append(f"| {_VERDICT_EMOJI[v]} | {counts[v]} |")
    lines.append("")

    if not findings:
        lines.append("*No findings recorded yet.*\n")

    # Per-sport sections
    for sport in sorted(by_sport):
        sport_findings = by_sport[sport]
        lines.append(f"---\n\n## {sport.upper()}\n")
        lines.append(
            f"*{len(sport_findings)} signal families tested — "
            f"all honest verdicts shown.*\n"
        )

        # Group by family within sport
        by_family: Dict[str, List[ResearchFinding]] = {}
        for f in sport_findings:
            by_family.setdefault(f.family, []).append(f)

        for family in sorted(by_family):
            for f in by_family[family]:
                verdict_label = _VERDICT_EMOJI[f.verdict]
                lines.append(f"### [{verdict_label}] `{f.family}`\n")
                lines.append(f"**Hypothesis:** {f.hypothesis}\n")
                lines.append(f"**Verdict:** {f.verdict}  |  **Dated:** {f.dated}\n")

                # Posterior ship-rate (only when a BeliefStore is provided)
                if belief_store is not None:
                    try:
                        pm = belief_store.posterior_mean(f.sport, f.family)
                        lo, hi = belief_store.credible_interval(f.sport, f.family)
                        lines.append(
                            f"**P(ship) posterior:** {pm:.3f}  "
                            f"95% CI [{lo:.3f}, {hi:.3f}]  "
                            f"*(historical ship-rate prior — no edge claimed)*\n"
                        )
                    except Exception:
                        pass  # never let a belief lookup break the writeup

                # Evidence block
                if f.evidence:
                    lines.append("**Evidence:**")
                    lines.append("```")
                    for k, v in f.evidence.items():
                        lines.append(f"  {k}: {v}")
                    lines.append("```\n")

                # What would change my mind
                lines.append(
                    f"**What would change my mind:** {f.what_would_change_my_mind}\n"
                )

    # Highest-Value Next Questions (search completeness only, never edge claims)
    if gaps:
        lines.append("---\n")
        lines.append("## Highest-Value Next Questions (search-completeness, not edges)\n")
        lines.append(
            "> **Honest framing:** expected outcome of testing any gap is **REJECT** — "
            "markets are efficient and every tested family in this codebase rejects.  "
            "**UNTESTED != opportunity.**  Ranking = scientific thoroughness "
            "(coverage breadth × posterior uncertainty), NOT expected profit.  "
            "No edge is claimed.\n"
        )
        for g in gaps:
            sport = getattr(g, "sport", "?")
            family = getattr(g, "family", "?")
            score = getattr(g, "score", 0.0)
            rationale = getattr(g, "rationale", "")
            what = getattr(g, "what_would_settle_it", "")
            verdicts = getattr(g, "verdict_history", [])
            verdict_str = ", ".join(verdicts) if verdicts else "(none — UNTESTED)"
            lines.append(
                f"### Rank #{getattr(g, 'rank', '?')}  [{sport}]  `{family}`\n"
            )
            lines.append(f"**Score:** {score:.4f}  |  **Verdicts so far:** {verdict_str}\n")
            lines.append(f"**Rationale:** {rationale}\n")
            lines.append(f"**To settle it:** {what}\n")
        lines.append(
            "> *Completing these gaps improves search completeness, not profit.  "
            "Markets are efficient; UNTESTED != opportunity.*\n"
        )

    # Footer
    lines.append("---")
    lines.append(
        "*This note is auto-generated by the research harness.  "
        "No edge is claimed.  REJECTs are successes — they preserve "
        "research capital for real frontiers.*"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI shim (convenience)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(
        description="Render the research ledger to stdout as markdown."
    )
    p.add_argument(
        "--ledger",
        metavar="PATH",
        help="Path to findings.jsonl (default: data/research/findings.jsonl)",
    )
    args = p.parse_args()
    from research_ledger import DEFAULT_LEDGER

    ledger_path = args.ledger or str(DEFAULT_LEDGER)
    ledger = Ledger(path=ledger_path)
    print(render_writeup(ledger))
