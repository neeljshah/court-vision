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

Multi-candidate key matching (candidate_keys):
  For Sackmann "First [Middle...] Last" names, generates ALL plausible keys:
    - surname = last token only (handles middle-name cases)
    - surname = last two tokens joined (handles compound surnames)
  For tennis-data "Surname F." names, generates keys from the hyphen-split variants.
  This resolves middle-name mismatches without breaking compound surnames.
"""
from __future__ import annotations

import re

from domains.tennis.name_aliases_keys import (
    _MULTI_SURNAME_PARTICLES,
    _strip_accents,
    _clean,
    _particle_join,
)


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


def candidate_keys(raw_name: str, source: str) -> set:
    """Return ALL plausible ``<surname>_<firstinitial>`` keys for *raw_name*.

    This is the multi-candidate extension of normalize_sackmann / normalize_td.
    It resolves the middle-name / compound-surname ambiguity without fuzzy matching:

    Sackmann source (``"First [Middle...] Last"``):
      - Key using surname = last token only → handles "Tomas Martin Etcheverry"
        → ``etcheverry_t`` (correct; middle name "Martin" is skipped).
      - Key using surname = last two tokens joined → handles "Felix Auger Aliassime"
        → ``augeraliassime_f`` (correct compound surname).
      - Also applies particle-join so "Alex De Minaur" → ``deminaur_a``.

    tennis-data source (``"Surname F."`` or ``"Surname-Part F."``):
      - Standard key from normalize_td.
      - Hyphen-split variants so "Auger-Aliassime F." produces both
        ``augeraliassime_f`` and ``aliassime_f`` (the former joins; the latter
        is the last-token fallback).

    All keys have ALIASES applied.

    Returns
    -------
    set[str]
        Non-empty set of candidate canonical keys.
    """
    raw_name = raw_name.strip()
    if not raw_name:
        return {""}

    keys: set = set()

    if source == "sackmann":
        cleaned = _clean(raw_name)
        tokens = cleaned.split()
        if not tokens:
            return {""}
        if len(tokens) == 1:
            return {tokens[0] + "_"}

        initial = tokens[0][0]
        surname_tokens = tokens[1:]

        # Candidate 1: full suffix joined — original normalize_sackmann behaviour.
        # Covers "Felix Auger Aliassime" → "augeraliassime_f",
        #        "Alex De Minaur"        → "deminaur_a".
        surname_full = _particle_join(surname_tokens)
        keys.add(f"{surname_full}_{initial}")

        # Candidate 2: last token only — handles embedded middle names.
        # "Tomas Martin Etcheverry" → "etcheverry_t"
        # "Jan Lennard Struff"      → "struff_j"
        surname_last = _particle_join([surname_tokens[-1]])
        keys.add(f"{surname_last}_{initial}")

        # Candidate 3: last two tokens joined — captures two-token compound surnames
        # even when there is a preceding middle name.
        # "Felix Auger Aliassime" (3-token suffix) → "augeraliassime_f"
        if len(surname_tokens) >= 2:
            surname_last2 = _particle_join(surname_tokens[-2:])
            keys.add(f"{surname_last2}_{initial}")

        # Candidate 4: first surname token only — handles td "Bautista R." where
        # Sackmann stores "Roberto Bautista Agut" (td uses first part of compound).
        # "Roberto Bautista Agut" → "bautista_r"
        # "Victor Estrella Burgos" → "estrella_v" (td writes "Estrella Burgos V.")
        # Skip if first token is a particle (would generate "de_a" etc.)
        if surname_tokens[0] not in _MULTI_SURNAME_PARTICLES:
            keys.add(f"{surname_tokens[0]}_{initial}")

    elif source == "td":
        cleaned = _clean(raw_name)
        # Remove trailing dots on initials
        cleaned = re.sub(r"\b(\w)\.", r"\1", cleaned).strip()
        tokens = cleaned.split()
        if not tokens:
            return {""}
        if len(tokens) == 1:
            return {tokens[0] + "_"}

        initial = tokens[-1][0]
        surname_tokens = tokens[:-1]

        # Candidate 1: standard particle-joined surname
        surname_std = _particle_join(surname_tokens)
        keys.add(f"{surname_std}_{initial}")

        # Candidate 2: collapsed (no particle logic) — "Auger Aliassime" → "augeraliassime"
        surname_flat = "".join(surname_tokens)
        keys.add(f"{surname_flat}_{initial}")

        # Candidate 3: last surname token only — for cases where td uses full compound
        # surname but Sackmann uses only the last part.
        if len(surname_tokens) > 1:
            keys.add(f"{surname_tokens[-1]}_{initial}")

        # Candidate 4: first surname token only — for compound surnames where Sackmann
        # uses a different part (e.g. td "Estrella Burgos V." → "estrella_v").
        if len(surname_tokens) > 1 and surname_tokens[0] not in _MULTI_SURNAME_PARTICLES:
            keys.add(f"{surname_tokens[0]}_{initial}")

    else:
        raise ValueError(f"Unknown source {source!r}; expected 'td' or 'sackmann'")

    # For td source: include BOTH the raw key and its ALIASES-resolved form.
    # This ensures that "deminaur_a" (td "Deminaur A.") and "de minaur_a" (alias)
    # both participate in candidate matching, catching both old-style and new-style keys.
    # For sackmann source: ALIASES maps td→sackmann keys; don't apply or it corrupts
    # sackmann keys (e.g. "deminaur_a" → "de minaur_a" when sackmann is already correct).
    resolved: set = set()
    for k in keys:
        resolved.add(k)  # always include raw key
        if source == "td":
            resolved.add(ALIASES.get(k, k))  # also include alias-resolved form
    return resolved


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
