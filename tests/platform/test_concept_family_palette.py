"""Guard: every concept FAMILY the node emitter produces must be COLOURED.

Run ONLY this file (the full suite freezes the box):
    python -m pytest tests/platform/test_concept_family_palette.py -q

brain_vault._CONCEPT_FAMILIES is the hand-maintained palette (one hue per family).
brain_concept_nodes emits nodes under vault/_Organized/<SPORT>/<FAMILY>/, one family
per spec module. Nothing enforces that the two lists agree, so a new or renamed spec
family would ship UNCOLOURED in the graph. This test discovers the real specs (the
production path, write=False so it touches no disk), extracts every emitted family from
the report's ``by_sport_family`` keys ("<sport>/<family>"), and asserts each is present
(case-insensitively) in the palette. Honest: a robustness guard; no edge claimed.
"""
from __future__ import annotations

from scripts.platformkit.brain_concept_nodes import build_concept_nodes
from scripts.platformkit.brain_vault import _CONCEPT_FAMILIES, _LEGACY_PATHS


def _emitted_families() -> set:
    """Families emitted over the DISCOVERED/injected specs (production path)."""
    rep = build_concept_nodes(write=False)
    fams = set()
    for sport_family in rep["by_sport_family"]:
        # key is "<sport>/<family>"; family is everything after the first slash.
        _sport, _, family = sport_family.partition("/")
        if family:
            fams.add(family)
    return fams


def test_every_emitted_family_is_in_the_palette() -> None:
    palette = {f.lower() for f in _CONCEPT_FAMILIES}
    # Legacy structural categories are coloured by PATH, not by the family palette;
    # they are a legitimate way for a "family" dir to be coloured, so allow them too.
    legacy = {p.lower() for p in _LEGACY_PATHS}
    allowed = palette | legacy

    emitted = _emitted_families()
    assert emitted, "expected the discovered specs to emit at least one family"

    drift = sorted(f for f in emitted if f.lower() not in allowed)
    assert not drift, (
        "concept families emitted by brain_concept_nodes but MISSING from "
        "brain_vault._CONCEPT_FAMILIES (would ship uncoloured): " + ", ".join(drift)
    )


def test_palette_has_no_duplicate_families() -> None:
    lowered = [f.lower() for f in _CONCEPT_FAMILIES]
    dupes = sorted({f for f in lowered if lowered.count(f) > 1})
    assert not dupes, "duplicate family names in _CONCEPT_FAMILIES: " + ", ".join(dupes)
