"""Desync guard: live_read._INGAME_FAMILIES must stay a subset of the
authoritative concept-family list (brain_vault._CONCEPT_FAMILIES).

_INGAME_FAMILIES is a hardcoded, lowercased copy of a slice of the
authoritative families. If a family is renamed/removed upstream, the
in-game read would silently surface nothing. This test fails loudly on
that desync so the duplication is kept honest.
"""
from scripts.platformkit.live_read import _INGAME_FAMILIES
from scripts.platformkit.brain_vault import _CONCEPT_FAMILIES


def test_ingame_families_are_authoritative():
    authoritative = {f.lower() for f in _CONCEPT_FAMILIES}
    orphans = sorted(_INGAME_FAMILIES - authoritative)
    assert not orphans, (
        f"live_read._INGAME_FAMILIES has names absent from the authoritative "
        f"brain_vault._CONCEPT_FAMILIES (desync): {orphans}"
    )


def test_ingame_families_nonempty():
    assert _INGAME_FAMILIES, "_INGAME_FAMILIES must not be empty"
