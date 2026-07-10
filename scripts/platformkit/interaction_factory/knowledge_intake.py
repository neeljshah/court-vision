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

Also composes CONFIRMED_LOCAL x CONFIRMED_LOCAL mechanism-attr pairs (see
composed_candidates / MECHANISM_ATTR below) -- two validated mechanisms
crossed together, not one mechanism paired with a plain pool attr.

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
    "soccer": REPO / "domains" / "soccer" / "knowledge" / "validation_ledger.jsonl",
    "tennis": REPO / "domains" / "tennis" / "knowledge" / "validation_ledger.jsonl",
}

# hypothesis (ledger key) -> the (template, attr_a, attr_b) pairs it backs.
# `contact_quality_persists_split_half` (MLB mechanisms.md #15): split-half
# r=0.593 (p=3.2e-42, n=430 batters, 2025) that batter mean-launch-speed
# persists -- the mechanism's own wiring note says this is "already the right
# shape for mlb_pa_batter_x_pitcher's left pool" since the registry already
# has `contact_quality` (DESCRIPTIVE).
#
# `edge_zone_widens_with_two_strikes` / `two_strike_chase_rate_rises` /
# `first_pitch_strike_suppresses_bb` (fix-wave-alpha, 2026-07-11): the
# registry now carries real as-of attrs for each (edge_zone_rate,
# chase_rate -- domains/mlb/profiles/attribute_registry.py; first_pitch_
# strike_rate already existed) with matching runner.build_mlb_pa_frame
# columns (asof__edge_zone_rate/chase_rate/first_pitch_strike_rate). Mapped
# into mlb_pa_batter_x_pitcher (feature_builder mlb_pa_asof, a REGISTERED
# builder -- unlike mlb_pa_attr_x_count_state's mlb_pa_count_state_asof,
# which has no builder yet and would only yield NOT_TESTABLE). These test a
# related-but-not-identical interaction (same precedent as contact_quality
# above: the ledger's own within-PA state effect isn't literally re-run,
# the now-validated real attribute is wired into the existing attr-pair
# grammar). `gb_double_play_suppression` (MLB's 4th unmapped row) stays
# UNMAPPABLE: it is a batted-ball-event-level (bb_type x force_state)
# effect, not a persistent batter/pitcher as-of attribute -- no pool shape
# fits it; see docs/research/factory_pipe_2026-07-11.md for the full
# UNMAPPABLE ledger (also covers all NBA/soccer/tennis CONFIRMED_LOCAL rows).
#
# soccer/tennis ledgers: `tennis_match_asof_self_cross` / `soccer_match_
# asof_self_cross` templates DO exist (generator.py TEMPLATES, ADJ-1 in
# gap_ledger_2026-07-11.md) -- this comment previously said otherwise, which
# was stale/wrong. The real reason ZERO soccer/tennis CONFIRMED_LOCAL rows
# map is that both templates' pools are PREGAME as-of diff attrs (serve/
# return/shot rates), while every soccer/tennis knowledge mechanism tests an
# IN-MATCH state effect (score_state x shot_rate, set-piece vs open-play,
# surface, within-match serve decay, set number, retirement/fatigue) that
# needs a different atomic_unit/outcome the current grammar has no template
# for. See docs/research/factory_pipe_2026-07-11.md for the per-row detail.
KNOWN_MAPPINGS: Dict[str, List[Dict[str, str]]] = {
    "contact_quality_persists_split_half": [
        {"template_id": "mlb_pa_batter_x_pitcher", "attr_a": "contact_quality", "attr_b": "whiff_rate"},
        {"template_id": "mlb_pa_batter_x_pitcher", "attr_a": "contact_quality", "attr_b": "platoon_split"},
    ],
    "edge_zone_widens_with_two_strikes": [
        {"template_id": "mlb_pa_batter_x_pitcher", "attr_a": "K_avoidance", "attr_b": "edge_zone_rate"},
        {"template_id": "mlb_pa_batter_x_pitcher", "attr_a": "BB_rate", "attr_b": "edge_zone_rate"},
    ],
    "two_strike_chase_rate_rises": [
        {"template_id": "mlb_pa_batter_x_pitcher", "attr_a": "chase_rate", "attr_b": "whiff_rate"},
        {"template_id": "mlb_pa_batter_x_pitcher", "attr_a": "chase_rate", "attr_b": "platoon_split"},
    ],
    "first_pitch_strike_suppresses_bb": [
        {"template_id": "mlb_pa_batter_x_pitcher", "attr_a": "BB_rate", "attr_b": "first_pitch_strike_rate"},
        {"template_id": "mlb_pa_batter_x_pitcher", "attr_a": "K_avoidance", "attr_b": "first_pitch_strike_rate"},
    ],
    # `spin_rate_deception` (MLB mechanisms.md -- OLS whiff ~ release_spin_rate
    # + release_speed on breaking-pitch swings, p=2.2e-16, n=100280): the
    # "cheap future win" flagged in docs/research/factory_pipe_2026-07-11.md's
    # unmappable list ("same shape as this lane's edge_zone_rate"). Now has a
    # real registry attr (release_spin_rate, domains/mlb/profiles/
    # attribute_registry.py) + a matching as-of column (runner.build_mlb_pa_
    # frame's asof__release_spin_rate) -- mapped the same way edge_zone_rate
    # was: onto mlb_pa_batter_x_pitcher's batter pool.
    "spin_rate_deception": [
        {"template_id": "mlb_pa_batter_x_pitcher", "attr_a": "K_avoidance", "attr_b": "release_spin_rate"},
        {"template_id": "mlb_pa_batter_x_pitcher", "attr_a": "BB_rate", "attr_b": "release_spin_rate"},
    ],
}

# --------------------------------------------------------------------------
# MECHANISM-INTERACTION COMPOSITION (build lane C2): pairwise CONFIRMED x
# CONFIRMED candidates -- unlike KNOWN_MAPPINGS above (one validated mechanism
# attr paired with a plain existing-pool attr), BOTH attr_a and attr_b here
# are each independently a validated (CONFIRMED_LOCAL) mechanism's own
# registry attribute. This is the composition step: two mechanisms that are
# each individually real might interact in a way blind combinatorial search
# would take far longer to stumble onto.
#
# MECHANISM_ATTR: hypothesis -> its own registry attribute (the one that
# repeats across every KNOWN_MAPPINGS row for that hypothesis) + which side
# of mlb_pa_batter_x_pitcher's batter x pitcher cross it belongs on.
# Hand-audited, same discipline as KNOWN_MAPPINGS: a hypothesis absent here
# contributes nothing to composition, never inferred from KNOWN_MAPPINGS.
MECHANISM_ATTR: Dict[str, Dict[str, str]] = {
    "contact_quality_persists_split_half": {"attr": "contact_quality", "entity": "batter"},
    "two_strike_chase_rate_rises": {"attr": "chase_rate", "entity": "batter"},
    "edge_zone_widens_with_two_strikes": {"attr": "edge_zone_rate", "entity": "pitcher"},
    "first_pitch_strike_suppresses_bb": {"attr": "first_pitch_strike_rate", "entity": "pitcher"},
    "spin_rate_deception": {"attr": "release_spin_rate", "entity": "pitcher"},
}
# The only template today whose two pools are exactly {batter, pitcher} attrs
# -- the sole place composition's entity/attr shapes align with the grammar
# (NBA/soccer/tennis have zero mapped mechanisms per docs/research/
# factory_pipe_2026-07-11.md's unmappable list -- nothing to compose there yet).
_COMPOSE_TEMPLATE = "mlb_pa_batter_x_pitcher"


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


def composed_candidates(ledger_paths: Dict[str, Path] = LEDGERS) -> List[GEN.Candidate]:
    """CONFIRMED_LOCAL x CONFIRMED_LOCAL mechanism-attr pairs: cross every
    batter-side mechanism attr against every pitcher-side mechanism attr
    (both named in MECHANISM_ATTR, both hypotheses CONFIRMED_LOCAL) under
    _COMPOSE_TEMPLATE's batter x pitcher cross grammar. Deterministic (sorted
    by candidate_id). A mechanism missing from the ledger or not yet in
    MECHANISM_ATTR contributes nothing -- honest, not an error."""
    confirmed = confirmed_hypotheses(ledger_paths)
    batter_attrs = sorted({m["attr"] for h, m in MECHANISM_ATTR.items()
                            if m["entity"] == "batter" and h in confirmed})
    pitcher_attrs = sorted({m["attr"] for h, m in MECHANISM_ATTR.items()
                             if m["entity"] == "pitcher" and h in confirmed})
    tpl = GEN.TEMPLATES[_COMPOSE_TEMPLATE]
    out: List[GEN.Candidate] = []
    for a in batter_attrs:
        for b in pitcher_attrs:
            cid = "%s::%s__x__%s::src=knowledge" % (_COMPOSE_TEMPLATE, a, b)
            out.append(GEN.Candidate(
                candidate_id=cid, template_id=_COMPOSE_TEMPLATE, sport=tpl["sport"],
                atomic_unit=tpl["atomic_unit"], outcome=tpl["outcome"], attr_a=a, attr_b=b,
                feature_builder=tpl["feature_builder"], hypothesis_source="knowledge",
            ))
    return sorted(out, key=lambda c: c.candidate_id)


def knowledge_candidates(ledger_paths: Dict[str, Path] = LEDGERS) -> List[GEN.Candidate]:
    """CONFIRMED_LOCAL ledger hypotheses with a declared KNOWN_MAPPINGS entry
    -> one Candidate per mapped (template, attr_a, attr_b), PLUS every
    CONFIRMED x CONFIRMED mechanism-composition candidate (composed_
    candidates) -- both arms share hypothesis_source='knowledge', the field
    the autoloop/report tooling already uses to count the knowledge arm.
    Deterministic (sorted by candidate_id, de-duped by candidate_id -- a pair
    could in principle appear from both arms; the composition ids are
    disjoint from the mapping ids today since composition only crosses each
    hypothesis's OWN mechanism attr against another hypothesis's OWN
    mechanism attr, never against a KNOWN_MAPPINGS partner). A hypothesis
    missing from either the ledger or a declared mapping contributes
    nothing -- honest, not an error."""
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
    seen = {c.candidate_id for c in out}
    for c in composed_candidates(ledger_paths):
        if c.candidate_id not in seen:
            out.append(c)
            seen.add(c.candidate_id)
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


__all__ = ["knowledge_candidates", "composed_candidates", "confirmed_hypotheses",
           "KNOWN_MAPPINGS", "MECHANISM_ATTR", "LEDGERS", "main"]
