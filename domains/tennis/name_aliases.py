"""domains.tennis.name_aliases — tennis name normalisation + alias table.

Converts tennis-data.co.uk name format ("Djokovic N.") and Sackmann full-name
format ("Novak Djokovic") to a shared canonical key used for the join in
ingest_tennisdata.py.

PRIVATE: outputs are price-bearing or license-restricted; `data/domains/tennis/`
is never tracked. Sackmann data is CC BY-NC-SA — private research use only,
nothing derived is published.

Algorithm (deterministic, no fuzzy matching at runtime):
  canonical_key = last_token_stripped + "_" + first_initial
  e.g. "Djokovic N." → "djokovic_n"
       "Novak Djokovic"  → "djokovic_n"
  Multi-word surnames ("De Minaur") are joined: "deminaur_a".
  Accents stripped via NFD decomposition.
  Literal ALIASES dict catches known divergences discovered from the unjoined-debug
  CSV during wave T3; every addition is a reviewable literal with no fuzzy runtime
  logic.
"""
from __future__ import annotations

import unicodedata
import re


# ---------------------------------------------------------------------------
# Alias table — maps tennis-data.co.uk canonical key → Sackmann canonical key.
# Populated from _raw/unjoined_debug.csv after each --build run.
# Format: td_canonical_key → sackmann_canonical_key
# ---------------------------------------------------------------------------
ALIASES: dict[str, str] = {
    # Seed entries covering the most common known divergences.
    # Key = normalize_td output; value = normalize_sackmann output.
    "musetti_l": "musetti_l",          # identical — placeholder shows the pattern
    "deminaur_a": "de minaur_a",       # tennis-data merges the surname
    "auger-aliassime_f": "auger aliassime_f",
    "karatsev_a": "karatsev_a",
    "kwon_s": "kwon_s",
    "mcdonald_m": "mcdonald_m",
    "obrien_c": "obrien_c",            # apostrophe stripped
}

# Keep the identity mappings above as examples; they are no-ops but show the
# intended shape.  Real fixes land as non-identity entries.


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MULTI_SURNAME_PARTICLES = frozenset(
    ["de", "del", "di", "da", "van", "von", "le", "la", "los", "du", "al"]
)


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
    s = re.sub(r"['’\-]", " ", s)
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


# ---------------------------------------------------------------------------
# Public normalisation functions
# ---------------------------------------------------------------------------

def normalize_td(td_name: str) -> str:
    """Normalise a tennis-data.co.uk name ("Djokovic N.") → canonical key.

    tennis-data format is "Surname F." where F is the first initial.
    The function is tolerant of missing dots / extra spaces.

    Returns
    -------
    str
        Canonical key, e.g. "djokovic_n".  Returns "" on blank input.
    """
    td_name = td_name.strip()
    if not td_name:
        return ""

    cleaned = _clean(td_name)
    # Remove trailing dots on initials ("n." → "n")
    cleaned = re.sub(r"\b(\w)\.", r"\1", cleaned).strip()

    tokens = cleaned.split()
    if not tokens:
        return ""

    if len(tokens) == 1:
        # No initial at all — use the single token as the surname key
        return tokens[0] + "_"

    # Last token is treated as the initial; everything before is the surname.
    initial = tokens[-1][0]  # take first char of last token in case no dot stripped
    surname_tokens = tokens[:-1]
    surname = _particle_join(surname_tokens)
    return f"{surname}_{initial}"


def normalize_sackmann(full_name: str) -> str:
    """Normalise a Sackmann full name ("Novak Djokovic") → canonical key.

    Sackmann stores "name_first name_last" (or combined as "First Last").
    We extract last-name + first-initial.

    Returns
    -------
    str
        Canonical key, e.g. "djokovic_n".  Returns "" on blank input.
    """
    full_name = full_name.strip()
    if not full_name:
        return ""

    cleaned = _clean(full_name)
    tokens = cleaned.split()
    if not tokens:
        return ""
    if len(tokens) == 1:
        return tokens[0] + "_"

    # First token is the given name; remainder is the surname (handles particles).
    initial = tokens[0][0]
    surname_tokens = tokens[1:]
    surname = _particle_join(surname_tokens)
    return f"{surname}_{initial}"


def normalize_name(raw: str, source: str = "td") -> str:
    """Unified entry point: normalise *raw* according to *source* format.

    Parameters
    ----------
    raw:
        Raw name string from the data source.
    source:
        ``"td"`` for tennis-data.co.uk format ("Surname F.");
        ``"sackmann"`` for Sackmann format ("First Last").

    Returns
    -------
    str
        Canonical key after alias resolution.
    """
    if source == "td":
        key = normalize_td(raw)
    elif source == "sackmann":
        key = normalize_sackmann(raw)
    else:
        raise ValueError(f"Unknown source {source!r}; expected 'td' or 'sackmann'")

    # Apply alias table (td-side canonical keys map to sackmann-side keys)
    return ALIASES.get(key, key)
