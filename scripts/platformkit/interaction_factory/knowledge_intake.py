"""scripts.platformkit.interaction_factory.knowledge_intake -- adapter from
the per-sport mechanism KNOWLEDGE ledgers (domains/*/knowledge/
validation_ledger.jsonl, backing domains/*/knowledge/mechanisms.md) into typed
interaction-factory Candidates tagged hypothesis_source='knowledge'.

Most CONFIRMED_LOCAL rows in those ledgers do NOT map onto today's factory
grammar -- they are pregame/state-level mechanisms (rest days, home/away,
count state) or need a registry attribute that does not exist yet (each has
its own "wiring" note in mechanisms.md saying so). KNOWN_MAPPINGS below is the
declared, hand-audited list of the ones that DO map right now: a real
registry attribute (existing or newly added) that belongs in an existing
template's pool. Adding a row here is the deliberate act of wiring one in --
never automatic just because a hypothesis exists in the ledger.

Pure enumeration only (mirrors generator.py's contract): reads the ledger
JSONL files and python constants, no fit, no ledger write -- runner.py's
run_batch(..., candidates=knowledge_candidates()) owns the actual test.

CLI: python -m scripts.platformkit.interaction_factory.knowledge_intake
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from scripts.platformkit.interaction_factory import generator as GEN

REPO = Path(__file__).resolve().parents[3]
LEDGERS: Dict[str, Path] = {
    "mlb": REPO / "domains" / "mlb" / "knowledge" / "validation_ledger.jsonl",
    "basketball_nba": REPO / "domains" / "basketball_nba" / "knowledge" / "validation_ledger.jsonl",
}

# hypothesis (ledger key) -> the (template, attr_a, attr_b) pairs it backs.
# `contact_quality_persists_split_half` (MLB mechanisms.md #15): split-half
# r=0.593 (p=3.2e-42, n=430 batters, 2025) that batter mean-launch-speed
# persists -- the mechanism's own wiring note says this is "already the right
# shape for mlb_pa_batter_x_pitcher's left pool" since the registry already
# has `contact_quality` (DESCRIPTIVE). Every other CONFIRMED_LOCAL row in
# both ledgers either names a not-yet-built registry attribute (edge_zone
# rate, first_pitch_outcome, bb_type x force_state, overall_fga_share, ...)
# or a pregame/state-level effect with no attr-pair shape (rest days,
# home/away, garbage time, rotation size) -- honestly left unmapped.
KNOWN_MAPPINGS: Dict[str, List[Dict[str, str]]] = {
    "contact_quality_persists_split_half": [
        {"template_id": "mlb_pa_batter_x_pitcher", "attr_a": "contact_quality", "attr_b": "whiff_rate"},
        {"template_id": "mlb_pa_batter_x_pitcher", "attr_a": "contact_quality", "attr_b": "platoon_split"},
    ],
}


def _load_ledger(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="ascii", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def confirmed_hypotheses(ledger_paths: Dict[str, Path] = LEDGERS) -> set:
    """The set of hypothesis names verdict==CONFIRMED_LOCAL across both
    ledgers (sport-agnostic union -- KNOWN_MAPPINGS names are already unique
    per hypothesis)."""
    out = set()
    for path in ledger_paths.values():
        for row in _load_ledger(path):
            if row.get("verdict") == "CONFIRMED_LOCAL":
                out.add(row.get("hypothesis"))
    return out


def knowledge_candidates(ledger_paths: Dict[str, Path] = LEDGERS) -> List[GEN.Candidate]:
    """CONFIRMED_LOCAL ledger hypotheses with a declared KNOWN_MAPPINGS entry
    -> one Candidate per mapped (template, attr_a, attr_b), hypothesis_source=
    'knowledge'. Deterministic (sorted by candidate_id). A hypothesis missing
    from either the ledger or KNOWN_MAPPINGS contributes nothing -- honest,
    not an error."""
    confirmed = confirmed_hypotheses(ledger_paths)
    out: List[GEN.Candidate] = []
    for hyp, mappings in KNOWN_MAPPINGS.items():
        if hyp not in confirmed:
            continue
        for m in mappings:
            tpl = GEN.TEMPLATES[m["template_id"]]
            a, b = m["attr_a"], m["attr_b"]
            cid = "%s::%s__x__%s::src=knowledge" % (m["template_id"], a, b)
            out.append(GEN.Candidate(
                candidate_id=cid, template_id=m["template_id"], sport=tpl["sport"],
                atomic_unit=tpl["atomic_unit"], outcome=tpl["outcome"], attr_a=a, attr_b=b,
                feature_builder=tpl["feature_builder"], hypothesis_source="knowledge",
            ))
    return sorted(out, key=lambda c: c.candidate_id)


def main() -> int:
    cands = knowledge_candidates()
    if not cands:
        print("knowledge_intake: no CONFIRMED_LOCAL hypothesis maps onto the factory grammar yet")
        return 0
    for c in cands:
        print("%-58s template=%s attr_a=%s attr_b=%s" % (c.candidate_id[:58], c.template_id, c.attr_a, c.attr_b))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["knowledge_candidates", "confirmed_hypotheses", "KNOWN_MAPPINGS", "LEDGERS", "main"]
