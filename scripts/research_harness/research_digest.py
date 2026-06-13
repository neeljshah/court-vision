"""scripts.research_harness.research_digest — Concise honest health digest.

Formats the result dict returned by run_research_loop into a <20-line terminal
summary that shows verdict counts, coverage, belief calibration, and top gaps.

Framing: markets efficient; REJECT = success; no edge is claimed.
No edge-claim language.  Calibration check is descriptive, not prescriptive.

Public API
----------
format_digest(result: dict) -> str
    Accepts the dict returned by run_research_loop.  Graceful when any
    field is missing (offline / no data).
"""
from __future__ import annotations

from typing import Any, Dict, List

# Phrases that must never appear in digest output (caught by tests).
_FORBIDDEN = frozenset({
    "profitable", "profitability", "arbitrage",
    "winning strategy", "guaranteed",
    "positive edge", "betting edge", "proven edge",
})


def format_digest(result: Dict[str, Any]) -> str:
    """Return a concise (<20 line) honest health summary string.

    Parameters
    ----------
    result:
        Dict as returned by run_research_loop.  Missing keys are handled
        gracefully — digest degrades to what is available.

    Returns
    -------
    str  (never empty; always ends with honest framing line)
    """
    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("RESEARCH HARNESS DIGEST")
    lines.append("=" * 60)

    # --- Verdict counts ---
    vc: Dict[str, int] = result.get("verdict_summary") or {}
    n_total: int = result.get("n_total", 0)
    n_reject = vc.get("REJECT", 0)
    n_ship = vc.get("SHIP", 0)
    n_defer = vc.get("DEFER", 0)
    n_var = vc.get("VARIANCE_ONLY", 0)
    lines.append(
        f"Findings : {n_total}  |  "
        f"REJECT {n_reject}  SHIP {n_ship}  "
        f"DEFER {n_defer}  VARIANCE_ONLY {n_var}"
    )

    # --- Coverage ---
    cov_summary: str = result.get("coverage_summary") or ""
    # Extract a coverage % if present (hypothesis_enumerator embeds "XX%")
    import re as _re
    pct_match = _re.search(r"(\d+(?:\.\d+)?)\s*%", cov_summary)
    if pct_match:
        lines.append(f"Coverage : {pct_match.group(1)}% of candidate hypothesis space tested")
    elif cov_summary:
        # Trim to one line so digest stays compact
        first_line = cov_summary.strip().splitlines()[0][:72]
        lines.append(f"Coverage : {first_line}")
    else:
        lines.append("Coverage : (unavailable — run with vault data)")

    # --- Belief calibration ---
    belief_summary: Dict = result.get("belief_summary") or {}
    if belief_summary:
        all_posteriors: List[float] = []
        for sport_beliefs in belief_summary.values():
            if isinstance(sport_beliefs, dict):
                all_posteriors.extend(sport_beliefs.values())
        if all_posteriors:
            mean_p = sum(all_posteriors) / len(all_posteriors)
            observed_ship_rate = (n_ship / n_total) if n_total else 0.0
            delta = mean_p - observed_ship_rate
            calibration = (
                "OVERCONFIDENT (posterior > observed)"
                if delta > 0.05
                else "OK (posterior ≈ observed)"
            )
            lines.append(
                f"Belief   : P(ship) mean={mean_p:.3f}  "
                f"observed_ship_rate={observed_ship_rate:.3f}  {calibration}"
            )
        else:
            lines.append("Belief   : belief_summary present but no posteriors extracted")
    else:
        lines.append("Belief   : (belief_store unavailable or no findings)")

    # --- Top gaps ---
    top_gaps: List = result.get("top_gaps") or []
    if top_gaps:
        lines.append(f"Top gaps : (search-completeness ranking — UNTESTED ≠ opportunity)")
        for i, gap in enumerate(top_gaps[:3], 1):
            label = getattr(gap, "label", None) or getattr(gap, "family", None) or str(gap)
            score = getattr(gap, "score", None)
            score_str = f"  score={score:.3f}" if score is not None else ""
            lines.append(f"  {i}. {label}{score_str}")
    else:
        lines.append("Top gaps : (gap_observer unavailable or no candidates ranked)")

    # --- Honest framing ---
    lines.append("-" * 60)
    lines.append(
        "Markets efficient — REJECT = success — no edge is claimed."
    )
    lines.append("=" * 60)

    digest = "\n".join(lines)

    # Safety assertion: guard against accidentally introducing edge-claim language
    digest_lower = digest.lower()
    for phrase in _FORBIDDEN:
        if phrase in digest_lower:  # pragma: no cover
            raise RuntimeError(
                f"[research_digest] BUG: forbidden phrase {phrase!r} in digest output"
            )

    return digest
