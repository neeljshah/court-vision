"""domains.tennis.name_aliases_keys — low-level string helpers for name normalisation.

Internal module; do NOT import directly from outside ``domains.tennis``.
All public symbols are re-exported from ``domains.tennis.name_aliases``.

F5-clean: imports only stdlib + kernel.* (none needed here).
"""
from __future__ import annotations

import unicodedata
import re


# ---------------------------------------------------------------------------
# Constant: surname particles treated as prefix-joiners
# ---------------------------------------------------------------------------

_MULTI_SURNAME_PARTICLES = frozenset(
    ["de", "del", "di", "da", "van", "von", "le", "la", "los", "du", "al"]
)


# ---------------------------------------------------------------------------
# Low-level string helpers
# ---------------------------------------------------------------------------

def _strip_accents(s: str) -> str:
    """NFD-decompose and drop combining-character marks."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _clean(s: str) -> str:
    """Lowercase, strip accents, collapse internal whitespace."""
    s = _strip_accents(s).lower().strip()
    # Normalise hyphens and apostrophes to space so multi-word surnames remain
    # parseable; we re-join particles afterwards.
    s = re.sub(r"[''\-]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _particle_join(tokens: list[str]) -> str:
    """Join consecutive leading particles with the following token.

    "de minaur" → "deminaur"  (as tennis-data typically writes it)
    This is intentionally applied only to leading runs so "van der waals b"
    becomes "vanderwaals_b".
    """
    if not tokens:
        return ""
    result: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i] in _MULTI_SURNAME_PARTICLES and i + 1 < len(tokens):
            merged = tokens[i] + tokens[i + 1]
            result.append(merged)
            i += 2
        else:
            result.append(tokens[i])
            i += 1
    return "".join(result)
