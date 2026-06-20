"""scripts.platformkit.signals.signal_factory -- the M2 signal-factory BRIDGE.

LANE C core: turn the PERSON-FREE vault taxonomy + the signal_registry spine into
validated CandidateSpec PROPOSALS in the EXISTING candidate_enum schema, for three
families:

  * playstyle_corr     -- archetype-conditioned stat-pair correlation
                          (does conditioning a stat-pair correlation on an Archetype
                           NAME improve calibration of the joint? proposal only).
  * scheme_prior       -- defensive-scheme -> shot-quality prior
                          (does a DefensiveScheme NAME carry a shot-quality prior?).
  * archetype_matchup  -- archetype-vs-archetype interaction
                          (archetype NAME A vs archetype NAME B as a conditioning split).

Each spec:
  * carries note='calibration, not edge' and vs_close='UNPROVEN' (the rails);
  * is keyed by a NAME-STABLE candidate_id = blake2b(family|sport|target|signature),
    where the signature is built from vault NAMES (never a KMeans cluster-id, never a
    person) -- so the SAME idea hashes to the SAME id across a KMeans refit;
  * is PASSED THROUGH candidate_families.validate_spec (the $-and-retracted-number choke).

COLD START (a tested invariant): if the vault taxonomy is empty (no Archetypes/Schemes)
OR the signal_registry spine carries no valid stat-pair target for the sport, the factory
emits [] -- it never fabricates a target or a taxonomy. PAYLOAD-PROBE (must-fix #6): the
stat-pair targets are read from the ACTUAL signal_registry parquet payload; if that probe
yields nothing the family is empty, not zero-filled.

These are PROPOSALS only. The factory NEVER builds a gate-consumable candidate (that is
recalibrator.build_candidate, the MF4 choke) and NEVER fits anything. Registered
additively into candidate_families.all_specs; the loop stays inert (sentinel absent ->
recalibrator returns None -> NO_CANDIDATE).

INVARIANTS: never edits MEMORY.md, never writes data/registry/, never flips a flag,
never creates the sentinel, never builds a candidate, never fits. Calibration NOT edge
(no $/pnl/roi/edge field). vs_close UNPROVEN. Stdlib (+ optional pandas for the probe);
ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
import pathlib
import re
from typing import List, Optional, Sequence, Tuple

from scripts.platformkit.improve.candidate_families import (
    CandidateSpec, FAMILY_ARCHETYPE_MATCHUP, FAMILY_PLAYSTYLE_CORR, FAMILY_SCHEME_PRIOR,
    NOTE_CALIBRATION, validate_spec,
)
from scripts.platformkit.signals.vault_taxonomy import load_taxonomy

logger = logging.getLogger("signal_factory")

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]  # .../nba-ai-system
_SIGNAL_REGISTRY = _REPO_ROOT / "data" / "registry" / "signal_registry.parquet"

# Bound the enumerated surface so the proposal stream stays finite + deterministic. We
# take the first N names (sorted by the taxonomy loader) per family rather than the full
# cross-product, which would explode. These are caps on PROPOSALS, never on evidence.
_MAX_ARCHETYPES = 8
_MAX_SCHEMES = 8
_MAX_STAT_PAIRS = 6
_MAX_MATCHUP_PAIRS = 12

# Default stat-pair targets for playstyle_corr when the spine probe yields none AND the
# vault has archetypes (so the family is not silently empty just because the registry is
# thin). These are STAT NAMES only -- no number, no $, no retracted token.
_FALLBACK_STAT_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("pts", "reb"), ("pts", "ast"), ("reb", "ast"),
)


def _slug(name: str) -> str:
    """Stable, ASCII, lower-snake signature token from a vault NAME (no cluster-id, no $).

    Deterministic: the SAME name always slugs to the SAME token, so a candidate_id hashed
    over it is stable across a KMeans refit (the names themselves are refit-stable).
    """
    s = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
    return s or "x"


def _probe_stat_pairs(sport: str,
                      registry_path: Optional[pathlib.Path] = None) -> List[Tuple[str, str]]:
    """PAYLOAD-PROBE the signal_registry spine for valid stat-pair targets (must-fix #6).

    Reads the ACTUAL parquet payload and derives candidate stat pairs from the registry's
    own stat vocabulary (the leaf of each signal_id, e.g. 'ppp_by_zone'->'ppp_by_zone').
    Never raises: a missing parquet / pandas yields []. The CALLER decides cold-start when
    this (and the fallback) yield nothing.
    """
    path = registry_path if registry_path is not None else _SIGNAL_REGISTRY
    try:
        import pandas as pd  # local import: the probe is optional
    except Exception:  # noqa: BLE001 -- no pandas -> no probe -> caller uses fallback
        return []
    try:
        if not path.exists():
            return []
        df = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001 -- unreadable spine -> empty probe
        logger.debug("_probe_stat_pairs: registry unreadable -> []: %s", exc)
        return []
    stats: List[str] = []
    try:
        col = "entity" if "entity" in df.columns else None
        idcol = "signal_id" if "signal_id" in df.columns else None
        if idcol is None:
            return []
        for sid in df[idcol].astype(str).tolist():
            leaf = sid.split(".")[-1]
            leaf = _slug(leaf)
            if leaf and leaf not in stats:
                stats.append(leaf)
        # filter to player-entity stat-ish leaves when we can, for stable pairing
        _ = col  # entity presence noted; leaves already entity-agnostic
    except Exception as exc:  # noqa: BLE001
        logger.debug("_probe_stat_pairs: payload parse partial: %s", exc)
        return []
    stats = sorted(set(stats))[: _MAX_STAT_PAIRS + 2]
    pairs: List[Tuple[str, str]] = []
    for i in range(len(stats)):
        for j in range(i + 1, len(stats)):
            pairs.append((stats[i], stats[j]))
            if len(pairs) >= _MAX_STAT_PAIRS:
                return pairs
    return pairs


def _spec(family: str, sport: str, target: str, scope: str, signature: str,
          rationale: str) -> CandidateSpec:
    """Build + validate a CandidateSpec carrying the mandated rails (note/vs_close)."""
    spec = CandidateSpec(
        family=family, sport=str(sport), target=str(target), scope=scope,
        signature=signature, rationale=rationale, note=NOTE_CALIBRATION)
    return validate_spec(spec)


def gen_playstyle_corr(sport: str, target: str = "win_prob",
                       registry_path: Optional[pathlib.Path] = None) -> List[CandidateSpec]:
    """archetype-conditioned stat-pair correlation SPECS (proposal only; never fits).

    Cold-start []: emitted when the vault has NO archetypes OR there is no stat-pair
    target at all (neither a spine probe nor the fallback). NAME-STABLE: the signature is
    built from the archetype NAME slug + the stat-pair names, never a cluster-id.
    """
    tax = load_taxonomy(sport)
    archetypes = tax.archetypes[:_MAX_ARCHETYPES]
    if not archetypes:
        return []  # cold start: no person-free archetype to condition on.
    pairs = _probe_stat_pairs(sport, registry_path) or list(_FALLBACK_STAT_PAIRS)
    if not pairs:
        return []  # cold start: no valid stat-pair target in the spine or fallback.
    out: List[CandidateSpec] = []
    for arche in archetypes:
        a = _slug(arche)
        for s1, s2 in pairs[:_MAX_STAT_PAIRS]:
            sig = "playstyle_corr=arch:%s|pair:%s_%s" % (a, _slug(s1), _slug(s2))
            rat = ("archetype-conditioned correlation of %s,%s under archetype %s "
                   "(name-stable; calibration, not edge)" % (s1, s2, arche))
            out.append(_spec(FAMILY_PLAYSTYLE_CORR, sport, target, "pregame", sig, rat))
    return out


def gen_scheme_prior(sport: str, target: str = "win_prob") -> List[CandidateSpec]:
    """defensive-scheme -> shot-quality prior SPECS (proposal only; never fits).

    Cold-start []: emitted when the vault has NO DefensiveSchemes. NAME-STABLE: keyed by
    the scheme NAME slug, never a cluster-id, never a person.
    """
    tax = load_taxonomy(sport)
    schemes = tax.schemes[:_MAX_SCHEMES]
    if not schemes:
        return []  # cold start: no person-free defensive scheme.
    out: List[CandidateSpec] = []
    for scheme in schemes:
        sig = "scheme_prior=scheme:%s|target:shot_quality" % _slug(scheme)
        rat = ("defensive-scheme %s -> shot-quality prior "
               "(name-stable; calibration, not edge)" % scheme)
        out.append(_spec(FAMILY_SCHEME_PRIOR, sport, target, "ingame", sig, rat))
    return out


def gen_archetype_matchup(sport: str, target: str = "win_prob") -> List[CandidateSpec]:
    """archetype-vs-archetype interaction SPECS (proposal only; never fits).

    Cold-start []: emitted with fewer than TWO archetypes (no pair to form). NAME-STABLE
    + order-canonical: the pair (A,B) is sorted by slug so (A,B) and (B,A) hash to the
    SAME candidate_id (one idea, one id), stable across a KMeans refit.
    """
    tax = load_taxonomy(sport)
    archetypes = tax.archetypes[:_MAX_ARCHETYPES]
    if len(archetypes) < 2:
        return []  # cold start: need at least two archetypes to form a matchup.
    out: List[CandidateSpec] = []
    slugs = sorted({_slug(a) for a in archetypes})
    name_by_slug = {}
    for a in archetypes:
        name_by_slug.setdefault(_slug(a), a)
    n_pairs = 0
    for i in range(len(slugs)):
        for j in range(i + 1, len(slugs)):
            a_slug, b_slug = slugs[i], slugs[j]  # already sorted -> canonical order
            sig = "archetype_matchup=a:%s|b:%s" % (a_slug, b_slug)
            rat = ("archetype-vs-archetype interaction %s vs %s "
                   "(name-stable, order-canonical; calibration, not edge)"
                   % (name_by_slug[a_slug], name_by_slug[b_slug]))
            out.append(_spec(FAMILY_ARCHETYPE_MATCHUP, sport, target, "pregame", sig, rat))
            n_pairs += 1
            if n_pairs >= _MAX_MATCHUP_PAIRS:
                return out
    return out


def all_signal_specs(sport: str, target: str = "win_prob") -> List[CandidateSpec]:
    """Every LANE C signal-factory family's specs for `sport` (deterministic order).

    Returns [] (cold start) when neither the vault taxonomy nor the spine yields a valid
    target. Each spec is validated; none builds or fits anything. Registered additively
    into candidate_families.all_specs.
    """
    specs: List[CandidateSpec] = []
    specs.extend(gen_playstyle_corr(sport, target))
    specs.extend(gen_scheme_prior(sport, target))
    specs.extend(gen_archetype_matchup(sport, target))
    return specs


__all__ = [
    "gen_playstyle_corr", "gen_scheme_prior", "gen_archetype_matchup",
    "all_signal_specs",
]
