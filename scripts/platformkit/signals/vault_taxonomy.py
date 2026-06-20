"""scripts.platformkit.signals.vault_taxonomy -- a PERSON-FREE taxonomy loader.

LANE C (M2 signal-factory bridge). This module reads the person-free Obsidian concept
graph under vault/_Organized/<SPORT>/ and returns ONLY the NAMES of Archetypes and
DefensiveSchemes (plus, for archetype-vs-archetype, the same archetype name list). It
NEVER returns a person, NEVER returns a KMeans cluster-id, and NEVER carries a verdict or
a $-edge field. A name is the STABLE handle the signal factory hashes a candidate_id
over; a KMeans cluster-id is forbidden because it re-numbers on every refit, so a spec
keyed by a cluster-id would silently change identity across refits.

Why NAMES only (the RAILS):
  * The graph/intelligence is PERSON-FREE: we load Archetypes/Schemes by NAME, never the
    players who populate them. assert_person_free() is the tripwire a test asserts on.
  * Cluster-ids (kmeans_3, cluster_07, c12, ...) break on refit -- a spec must be
    NAME-STABLE, so cluster-id-looking tokens are filtered out at load.
  * Names are descriptive concept labels (e.g. "3-and-D Wing", "No-Middle Funnel
    Philosophy"), not signals and not bets -- calibration, not edge.

Public surface:
  TaxonomyNames(archetypes, schemes)         -- frozen, name-only result.
  load_taxonomy(sport, vault_root=None)      -- read names from the vault graph.
  assert_person_free(names)                  -- raise if ANY person token leaks.
  archetype_names(sport) / scheme_names(sport) -- convenience name lists.

A MISSING vault / sport folder yields EMPTY name lists (cold start) -- never raises, so
the factory degrades to [] rather than fabricating a taxonomy.

INVARIANTS: never edits MEMORY.md, never writes data/registry/, never flips a flag,
never creates the sentinel; read-only over vault/. Calibration NOT edge (no $/pnl/roi/
edge field). Stdlib only; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
import pathlib
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger("vault_taxonomy")

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]  # .../nba-ai-system
_VAULT_ORGANIZED = _REPO_ROOT / "vault" / "_Organized"

# Sport folder names as they appear under vault/_Organized/.
_SPORT_DIR = {
    "nba": "NBA", "basketball_nba": "NBA",
    "mlb": "MLB", "baseball_mlb": "MLB",
    "soccer": "Soccer", "soccer_intl": "Soccer",
    "tennis": "Tennis",
}

_ARCHETYPE_SUBDIR = "Archetypes"
# Schemes live under DefensiveSchemes (canonical) and sometimes a sibling Schemes dir.
_SCHEME_SUBDIRS = ("DefensiveSchemes", "Schemes")

# Files that are INDEX / computed scaffolding, not concept names. Skipped by name.
_SKIP_PREFIXES = ("_",)
_SKIP_STEMS = {"index", "computed", "playstyles", "archetypes", "defensiveschemes",
               "schemes", "whatwins", "read", "digest"}

# --- person / cluster-id tripwire -----------------------------------------------------
# A KMeans cluster-id re-numbers every refit -- a NAME-STABLE spec must never key off one.
# Match tokens like cluster_07, kmeans3, c12, k_5, grp4 used AS A WHOLE name token.
_CLUSTER_ID_RE = re.compile(
    r"(?:^|[ _\-])(?:cluster|kmeans|kmean|km|grp|group|clust|c|k)[ _\-]?\d+(?:$|[ _\-])",
    re.IGNORECASE,
)
# Person markers: a vault concept node is descriptive; these tokens signal a person leak.
_PERSON_KEY_TOKENS: Tuple[str, ...] = (
    "player_name", "playername", "first_name", "firstname", "last_name", "lastname",
    "full_name", "fullname", "person", "athlete_name", "nba_id", "bbref_id",
    "player_id",
)


def _looks_like_cluster_id(name: str) -> bool:
    """True if `name` is (or contains) a KMeans-style cluster-id token (refit-unstable)."""
    return bool(_CLUSTER_ID_RE.search(str(name)))


def _has_person_token(name: str) -> Optional[str]:
    """Return the first person-marker token found in `name` (lowercased), else None."""
    low = str(name).lower()
    for tok in _PERSON_KEY_TOKENS:
        if tok in low:
            return tok
    return None


@dataclass(frozen=True)
class TaxonomyNames:
    """Person-free, NAME-ONLY taxonomy result. Carries no verdict, no $, no cluster-id."""

    sport: str
    archetypes: Tuple[str, ...]
    schemes: Tuple[str, ...]

    def is_empty(self) -> bool:
        return not self.archetypes and not self.schemes


def assert_person_free(names: Iterable[str]) -> None:
    """Raise ValueError if ANY name carries a person token or a KMeans cluster-id.

    The single tripwire a test asserts on: the taxonomy is PERSON-FREE and refit-stable.
    A person token or a cluster-id-looking token is a rail violation and must abort the
    load, not silently slip into a candidate_id.
    """
    for nm in names:
        tok = _has_person_token(nm)
        if tok is not None:
            raise ValueError("person token %r leaked in taxonomy name: %r" % (tok, nm))
        if _looks_like_cluster_id(nm):
            raise ValueError("KMeans cluster-id (refit-unstable) name not allowed: %r"
                             % (nm,))


def _stem_to_name(stem: str) -> str:
    """Turn a vault file stem into a display name: underscores->spaces, title-ish.

    Pure, deterministic, no network. Keeps the stem stable enough that the same concept
    file always maps to the same name (so a candidate_id hashed over it is stable).
    """
    parts = [p for p in str(stem).replace("-", "_").split("_") if p]
    return " ".join(parts).strip()


def _read_concept_names(folder: pathlib.Path) -> List[str]:
    """List concept NAMES from a vault folder (markdown files), skipping index scaffolding.

    Never raises: a missing folder / unreadable entry yields the names gathered so far.
    Filters out cluster-id-looking stems so a refit-unstable label never becomes a name.
    """
    names: List[str] = []
    try:
        if not folder.is_dir():
            return names
        for p in sorted(folder.glob("*.md")):
            stem = p.stem
            low = stem.lower()
            if any(low.startswith(pre) for pre in _SKIP_PREFIXES):
                continue
            if low in _SKIP_STEMS:
                continue
            if _looks_like_cluster_id(stem):
                logger.debug("skip cluster-id-looking stem: %r", stem)
                continue
            name = _stem_to_name(stem)
            if name:
                names.append(name)
    except Exception as exc:  # noqa: BLE001 -- read-only loader must never wedge the loop
        logger.debug("_read_concept_names(%s) partial: %s", folder, exc)
    return names


def _dedup_sorted(names: Sequence[str]) -> Tuple[str, ...]:
    """Case-insensitive dedup, deterministic (sorted) order."""
    seen = set()
    out: List[str] = []
    for nm in names:
        key = nm.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(nm)
    return tuple(sorted(out, key=lambda s: s.lower()))


def load_taxonomy(sport: str,
                  vault_root: Optional[pathlib.Path] = None) -> TaxonomyNames:
    """Load PERSON-FREE Archetype + DefensiveScheme NAMES for `sport` from the vault.

    Returns a TaxonomyNames with name-only tuples. A missing vault / sport folder yields
    empty tuples (cold start) -- never raises. Every returned name passes assert_person_free
    (a person token or cluster-id aborts the load with ValueError, surfacing the rail
    violation rather than shipping a tainted taxonomy).
    """
    root = vault_root if vault_root is not None else _VAULT_ORGANIZED
    sub = _SPORT_DIR.get(str(sport).lower())
    if sub is None:
        return TaxonomyNames(sport=str(sport), archetypes=(), schemes=())
    sport_dir = pathlib.Path(root) / sub

    arche = _read_concept_names(sport_dir / _ARCHETYPE_SUBDIR)
    schemes: List[str] = []
    for sd in _SCHEME_SUBDIRS:
        schemes.extend(_read_concept_names(sport_dir / sd))

    archetypes_t = _dedup_sorted(arche)
    schemes_t = _dedup_sorted(schemes)
    # Tripwire: refuse to return a tainted taxonomy (person token / cluster-id).
    assert_person_free(archetypes_t)
    assert_person_free(schemes_t)
    return TaxonomyNames(sport=str(sport), archetypes=archetypes_t, schemes=schemes_t)


def archetype_names(sport: str,
                    vault_root: Optional[pathlib.Path] = None) -> Tuple[str, ...]:
    """Convenience: just the person-free Archetype names for `sport`."""
    return load_taxonomy(sport, vault_root=vault_root).archetypes


def scheme_names(sport: str,
                 vault_root: Optional[pathlib.Path] = None) -> Tuple[str, ...]:
    """Convenience: just the person-free DefensiveScheme names for `sport`."""
    return load_taxonomy(sport, vault_root=vault_root).schemes


__all__ = [
    "TaxonomyNames", "load_taxonomy", "assert_person_free",
    "archetype_names", "scheme_names",
]
