"""scripts.platformkit.knowledge.assemble -- cited scouting-context bundle.

assemble() runs retrieve() (optionally following ## Related graph edges one hop),
then renders a markdown bundle where EVERY claim line cites a [[note_id]]. It is
the synthesis/narration surface of the RAG layer.

HARD BOUNDARY (binding, tested in tests/test_boundary.py):
  - The bundle NEVER contains a probability / odds / ROI / edge / American-odds token.
  - SYSTEM forbids probabilities/odds/edges, carries the markets-efficient/calibration
    line, and carries the honest-reject clause.
  - On empty retrieval -> the honest-reject string (first-class, not a fabrication).
  - Adversarial "give me the win probability and a bet" -> no numeric-as-prediction
    token + the NO_EDGE_DISCLAIMER substring.

OFFLINE: this is a deterministic, template-based synthesizer (no LLM call). The
agentic multi-hop Claude tool-use loop is an OPTIONAL upgrade -- it would call
vault_search / related_nodes (this module's retrieve/related_nodes) but is NEVER
given a numeric/predict tool, so the same boundary holds. ASCII only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from . import config
from .retrieve import Hit, RetrievalResult, related_nodes, retrieve

SYSTEM = (
    "You assemble SCOUTING CONTEXT from retrieved person-free vault notes. "
    "Every claim MUST cite a [[note_id]]. You do NOT output probabilities, odds, "
    "point spreads, ROI, betting edges, or any number that could enter a prediction. "
    "If retrieval returns nothing relevant, respond exactly 'No relevant intel found.' "
    "Markets are efficient; calibration is the goal; claim no edge. This layer informs "
    "narration only and never emits a forecast number."
)

NO_EDGE_DISCLAIMER = (
    "No advantage claimed. Markets are efficient; this is calibrated scouting "
    "context only -- a qualitative, citation-grounded read, never a forecast number "
    "or a wager recommendation."
)

HONEST_REJECT = "No relevant intel found."

# A claim line in a successful bundle must end with a [[note_id]] citation.
_CITE_RE = re.compile(r"\[\[[^\]]+\]\]\s*$")

# Numeric-as-prediction tokens that must NEVER appear in a bundle.
_FORBIDDEN_RE = re.compile(
    r"\b\d{1,3}\s?%|\bprob|\bodds|\b[+-]\d+(?:\.\d+)?%|\bROI"
    r"|\bedge\b|\bkelly\b|[+-]\d{3,}\b",
    re.IGNORECASE,
)


@dataclass
class Bundle:
    markdown: str
    citations: List[str] = field(default_factory=list)
    reject: bool = False


def _scrub(text: str) -> str:
    """Remove any numeric-as-prediction token a note body might contain.

    The boundary forbids percentages, odds, ROI, edge, kelly, and American-odds
    integers in the SYNTHESIZED bundle. We rewrite offending tokens to a neutral
    word so a snippet that happens to quote a number cannot leak it as a forecast.
    """
    def _sub(m: re.Match) -> str:
        return "[scrubbed]"
    return _FORBIDDEN_RE.sub(_sub, text)


def _claim_line(hit: Hit) -> str:
    """One cited claim line: a scrubbed concept sentence ending in the citation."""
    snip = _scrub(hit.snippet).strip().rstrip(".")
    # Keep it short and qualitative; never a stat line.
    snip = re.sub(r"\s+", " ", snip)[:200].rstrip()
    title = _scrub(hit.title).strip()
    return f"- {title}: {snip}. {hit.citation}"


def assemble(
    sport: str,
    home_id: str = "",
    away_id: str = "",
    question: Optional[str] = None,
    *,
    top_k: int = config.TOP_K,
    follow_graph: bool = True,
    retriever=retrieve,
) -> Bundle:
    """Assemble a cited scouting-context bundle. Honest-reject is first-class.

    `retriever` is injectable so the boundary test can pass a stub. The seed query
    is the question (or a generic matchup-context probe) -- person-free, so a player
    name is treated as an archetype probe, never a dossier lookup.
    """
    seed = (question or "").strip()
    if not seed:
        seed = "matchup scheme tendencies pace and tactical context"
    res: RetrievalResult = retriever(seed, sport=sport, top_k=top_k)

    if res.reject or not res.hits:
        md = "\n".join([
            f"# Scouting Context -- {sport}", "",
            HONEST_REJECT, "", NO_EDGE_DISCLAIMER,
        ])
        return Bundle(markdown=md, citations=[], reject=True)

    hits: List[Hit] = list(res.hits)
    seen = {h.note_id for h in hits}
    if follow_graph:
        for h in list(res.hits)[:3]:
            for nb in related_nodes(h.note_id, hops=1):
                if nb.note_id not in seen:
                    seen.add(nb.note_id)
                    hits.append(nb)
                    if len(hits) >= top_k + 4:
                        break

    lines: List[str] = [f"# Scouting Context -- {sport}", ""]
    if question:
        lines.append(f"_Theme: {_scrub(question).strip()}_")
        lines.append("")
    lines.append("## Relevant concepts")
    for h in hits:
        lines.append(_claim_line(h))
    lines.append("")
    lines.append(NO_EDGE_DISCLAIMER)

    md = "\n".join(lines)
    md = md.encode("ascii", errors="replace").decode("ascii")
    citations = [h.citation for h in hits]
    return Bundle(markdown=md, citations=citations, reject=False)


def check_bundle(bundle: Bundle) -> List[str]:
    """Return a list of boundary violations (empty == clean). Used by tests + CI."""
    problems: List[str] = []
    if not bundle.markdown.isascii():
        problems.append("non-ascii in bundle")
    if NO_EDGE_DISCLAIMER not in bundle.markdown:
        problems.append("missing no-edge disclaimer")
    if _FORBIDDEN_RE.search(bundle.markdown):
        problems.append("forbidden numeric/predict token present")
    if not bundle.reject:
        for ln in bundle.markdown.splitlines():
            s = ln.strip()
            if not s or s.startswith("#") or s.startswith("_"):
                continue
            if s == NO_EDGE_DISCLAIMER or s == HONEST_REJECT:
                continue
            if s.startswith("## ") or s.startswith("Theme"):
                continue
            if s.startswith("- ") and not _CITE_RE.search(s):
                problems.append(f"uncited claim line: {s[:50]}")
    return problems


if __name__ == "__main__":  # pragma: no cover
    import argparse
    ap = argparse.ArgumentParser(description="Assemble a cited scouting bundle.")
    ap.add_argument("--sport", default="NBA")
    ap.add_argument("--question", default=None)
    args = ap.parse_args()
    b = assemble(args.sport, question=args.question)
    print(b.markdown)
    print("\n[reject]", b.reject, "[violations]", check_bundle(b))
