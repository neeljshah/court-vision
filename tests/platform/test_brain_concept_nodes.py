"""Per-file tests for scripts.platformkit.brain_concept_nodes.

Run ONLY this file (the full suite freezes the box):
    python -m pytest tests/platform/test_brain_concept_nodes.py -q

Uses the ``injected_specs`` seam (no disk discovery) with 3 synthetic person-free
families across 2 sports, including cross-concept links that resolve (same-sport and
cross-sport) and links that do NOT resolve (must be dropped — no dangling wikilinks).
"""
from __future__ import annotations

import re

from scripts.platformkit.brain_concept_nodes import build_concept_nodes

# --- Synthetic person-free spec data (concepts, never people/teams/matches) ---
_NBA_SITUATIONAL = [
    {
        "slug": "transition_pace_pressure",
        "title": "Transition Pace Pressure",
        "summary": "Forcing early-clock decisions raises variance of the half-court rate.",
        "stat_signature": "transition possessions per 100 above 18; early-clock FG rate split.",
        "mechanism": "Compressed decision time degrades shot selection before the set forms.",
        "conditions": "Shows up against slow-tempo, set-heavy offensive structures.",
        "magnitude": "Descriptive: roughly a 2-3 point swing in projected pace-adjusted scoring.",
        # transition_defense_strain resolves (same family); paint_collapse resolves
        # (other NBA family); nonexistent_concept does NOT resolve -> dropped.
        "links": ["transition_defense_strain", "paint_collapse", "nonexistent_concept"],
    },
    {
        "slug": "transition_defense_strain",
        "title": "Transition Defense Strain",
        "summary": "Repeated cross-matches in retreat raise open-look frequency.",
        "stat_signature": "points allowed per transition chance; cross-match frequency.",
        "mechanism": "Late matching duty leaves the weak side a step behind the play.",
        "conditions": "Amplified against high-frequency early-clock attacking styles.",
        "magnitude": "Descriptive: a modest lift in allowed efficiency on the break.",
        "links": ["transition_pace_pressure"],  # back-link, resolves
    },
]

_NBA_TACTICS = [
    {
        "slug": "paint_collapse",
        "title": "Paint Collapse Gravity",
        "summary": "Interior gravity bends the help shell and opens the perimeter.",
        "stat_signature": "drives per 100; kick-out rate; corner-three frequency.",
        "mechanism": "Help commitment to the rim vacates the relocation arc.",
        "conditions": "Pronounced against drop-coverage structures.",
        "magnitude": "Descriptive: shifts a few percent of shot share toward the arc.",
        "links": [],
    },
]

# Cross-sport: links to an NBA concept (cross-sport resolve) and a dead slug (dropped).
_SOCCER_TACTICS = [
    {
        "slug": "high_press_trigger",
        "title": "High Press Trigger Timing",
        "summary": "Pressing on the back-pass cue compresses the build-out window.",
        "stat_signature": "PPDA below 9; recoveries in the final third per match.",
        "mechanism": "The trigger removes the safe outlet before the line resets.",
        "conditions": "Effective against patient, short build-out structures.",
        "magnitude": "Descriptive: a few extra high turnovers per match on average.",
        # paint_collapse resolves (cross-sport NBA); ghost_slug does NOT -> dropped.
        "links": ["paint_collapse", "ghost_slug"],
    },
]

_SPECS = [
    ("NBA", "Situational", _NBA_SITUATIONAL),
    ("NBA", "Tactics", _NBA_TACTICS),
    ("Soccer", "Tactics", _SOCCER_TACTICS),
]

_SECTIONS = ("## Summary", "## Stat Signature", "## Mechanism",
             "## Conditions", "## Magnitude", "## Related")
# Two consecutive Title-Case words = the person-name shape the lint forbids.
_PERSON_RE = re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b")


def _build(tmp_path):
    rep = build_concept_nodes(organized_root=tmp_path, write=True, injected_specs=_SPECS)
    return rep


def test_one_md_per_concept_with_sections_and_banner(tmp_path):
    rep = _build(tmp_path)
    assert rep["n_modules"] == 3
    assert rep["n_nodes"] == 4  # 2 + 1 + 1
    assert rep["n_skipped"] == 0
    assert rep["by_sport_family"] == {
        "NBA/Situational": 2, "NBA/Tactics": 1, "Soccer/Tactics": 1,
    }
    # One file per concept, under <SPORT>/<FAMILY>/<slug>.md, all sections + banner.
    for sport, family, concepts in _SPECS:
        for c in concepts:
            node = tmp_path / sport / family / f"{c['slug']}.md"
            assert node.exists(), node
            text = node.read_text(encoding="utf-8")
            assert text.startswith("---\ntags: [organized,")
            assert f"# {c['title']}" in text
            assert "no edge" in text.lower() and "NOT a bet" in text
            for sec in _SECTIONS:
                assert sec in text, f"{node} missing {sec}"


def test_family_index_lists_members(tmp_path):
    _build(tmp_path)
    idx = (tmp_path / "NBA" / "Situational" / "_Index.md")
    assert idx.exists()
    body = idx.read_text(encoding="utf-8")
    assert "NOT a bet" in body
    assert "[[transition_pace_pressure|Transition Pace Pressure]]" in body
    assert "[[transition_defense_strain|Transition Defense Strain]]" in body


def test_resolving_links_render_unresolved_dropped(tmp_path):
    _build(tmp_path)
    node = (tmp_path / "NBA" / "Situational" / "transition_pace_pressure.md")
    text = node.read_text(encoding="utf-8")
    related = text.split("## Related", 1)[1]
    # Same-family link -> sibling path; cross-family link -> ../Tactics/... ; both present.
    assert "[[transition_defense_strain|Transition Defense Strain]]" in related
    assert "[[../Tactics/paint_collapse|Paint Collapse Gravity]]" in related
    # Dead slug must be dropped entirely (no dangling wikilink to it).
    assert "nonexistent_concept" not in text


def test_cross_sport_link_resolves_and_no_dangling_anywhere(tmp_path):
    _build(tmp_path)
    soccer = (tmp_path / "Soccer" / "Tactics" / "high_press_trigger.md")
    stext = soccer.read_text(encoding="utf-8")
    # Cross-sport resolve to the NBA node via a relative path.
    assert "paint_collapse|Paint Collapse Gravity]]" in stext
    assert "ghost_slug" not in stext  # dead slug dropped
    # GLOBAL no-dangling guarantee: every [[target|title]] in every emitted .md must
    # point at a file that exists (drop the leading "../" walks while checking).
    emitted = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.md")}
    wiki = re.compile(r"\[\[([^\]|]+)\|")
    for md in tmp_path.rglob("*.md"):
        base_parts = md.relative_to(tmp_path).parent.parts
        for target in wiki.findall(md.read_text(encoding="utf-8")):
            if "/" in target:  # path-style link -> resolve against the node's dir
                parts = list(base_parts)
                for seg in target.split("/"):
                    if seg == "..":
                        parts = parts[:-1]
                    else:
                        parts.append(seg)
                resolved = "/".join(parts) + ".md"
            else:  # bare-slug link (used only by the family _Index, same dir)
                resolved = "/".join(list(base_parts) + [target]) + ".md"
            assert resolved in emitted, f"DANGLING link {target!r} in {md}"


def test_person_free(tmp_path):
    _build(tmp_path)
    # Allowed two-word Title-Case CONCEPT phrases (not people). Strip these, then assert
    # no remaining two-word Title-Case sequence (the person-name shape) survives.
    allowed = {
        "Transition Pace", "Pace Pressure", "Transition Defense", "Defense Strain",
        "Paint Collapse", "Collapse Gravity", "High Press", "Press Trigger",
        "Trigger Timing", "Stat Signature", "Concept Index",
    }
    for md in tmp_path.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        for phrase in allowed:
            text = text.replace(phrase, "")
        leftovers = [m for m in _PERSON_RE.findall(text)]
        assert not leftovers, f"possible person name in {md}: {leftovers}"


def test_idempotent_rerun(tmp_path):
    rep1 = _build(tmp_path)
    snap1 = {p.relative_to(tmp_path).as_posix(): p.read_text(encoding="utf-8")
             for p in sorted(tmp_path.rglob("*.md"))}
    rep2 = _build(tmp_path)
    snap2 = {p.relative_to(tmp_path).as_posix(): p.read_text(encoding="utf-8")
             for p in sorted(tmp_path.rglob("*.md"))}
    assert rep1 == rep2
    assert snap1 == snap2


def test_no_write_mode_counts_only(tmp_path):
    rep = build_concept_nodes(organized_root=tmp_path, write=False, injected_specs=_SPECS)
    assert rep["n_nodes"] == 4
    assert not list(tmp_path.rglob("*.md"))  # nothing written


def test_production_discovery_never_crashes():
    # No spec modules exist yet -> honest 0 nodes, but discovery must not raise.
    rep = build_concept_nodes(write=False)
    assert rep["n_nodes"] >= 0
    assert isinstance(rep["skipped"], list)
    assert "no edge claimed" in rep["_note"]
