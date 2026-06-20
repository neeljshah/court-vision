"""scripts.platformkit.improve.fusion.fusion_families -- 4 model-fusion SPEC families.

A fusion spec names a MODEL-LEVEL combination of ALREADY-VALIDATED base signals. This
module PRODUCES spec descriptors ONLY: it never fits, never builds, never reads a corpus
to decide an outcome, never flips a flag. It is the pure proposal head of the fusion
lane. Each spec is a frozen FusionSpec carrying an order-canonical, param-free SIGNATURE
and a refit-stable blake2b id (same idea -> same id; distinct config -> distinct id).

The four families (each a DIFFERENT blend mechanism than the feature-combo lane):

  STACK_OOF    out-of-fold stacked meta-learner over a NAMED set of validated base
               signals (the ONLY leak-free stacking). Signature encodes the lexicographic
               base-signal id set + the meta family (ridge / nnls / logistic).
  REGIME_MOE   mixture-of-experts: a DIFFERENT convex blend per game-state regime NAME
               (margin/late buckets from regime_experts) or per archetype NAME -- never a
               KMeans cluster-id. A degenerate split collapses to the global blend.
  RESID_BOOST  a learner fit on the OOF RESIDUAL (y - OOF base) of the PROVEN base, added
               back. Signature encodes the base id + the residual-learner family.
  REFUSE_CAL   isotonic / Platt RE-fusion applied AFTER a stack (re-calibrate the fused
               stream). A pure monotone map (no free shape parameter beyond the OOF fit).

Honesty choke: every spec text field passes candidate_families.assert_no_dollar (no
$/ROI/edge/% token, no retracted number). _PROVEN is a STATIC allowlist (no probe can
extend it). Calibration, not edge: vs_close = UNPROVEN. ASCII; stdlib only; <=300 LOC.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from scripts.platformkit.improve.candidate_families import NOTE_CALIBRATION, VS_CLOSE
from scripts.platformkit.improve.fusion.regime_experts import REGIME_NAMES

# Honesty token guard. We use a WORD-BOUNDARY 'edge' (mirroring combination_families)
# rather than the substring scan, because the proven base name 'ast_edge' is a legitimate
# person-free signal handle, NOT a market-edge claim. A bare '$'/'roi'/'%'/'pnl' or the
# standalone word 'edge' is still forbidden -- the disclaimer "calibration, not edge" is
# the one allowed standalone use and is stripped before scanning.
_FORBIDDEN_TOKEN = re.compile(r"(?:\$|\broi\b|\bedge\b|\bpnl\b|%)", re.IGNORECASE)
_RETRACTED = re.compile(r"(?<![\d.])(?:\+?18\.38|0\.119|\+?54|78\.11|8\.94|54\.57)(?![\d.])")


def _assert_clean(text: str) -> None:
    """Raise ValueError on a $-edge token or a retracted number (word-boundary 'edge')."""
    s = str(text)
    scan = s.lower().replace(NOTE_CALIBRATION, " ")  # allow the mandated disclaimer
    if _FORBIDDEN_TOKEN.search(scan):
        raise ValueError("forbidden $-edge token in spec text: %r" % (s,))
    if _RETRACTED.search(s):
        raise ValueError("retracted number in spec text: %r" % (s,))

# ----------------------------------------------------------------- family ids
FAMILY_STACK_OOF = "FAMILY_STACK_OOF"
FAMILY_REGIME_MOE = "FAMILY_REGIME_MOE"
FAMILY_RESID_BOOST = "FAMILY_RESID_BOOST"
FAMILY_REFUSE_CAL = "FAMILY_REFUSE_CAL"

FAMILIES: Tuple[str, ...] = (
    FAMILY_STACK_OOF, FAMILY_REGIME_MOE, FAMILY_RESID_BOOST, FAMILY_REFUSE_CAL,
)

# The ONLY base anchors a fusion may build on -- a STATIC, person-free allowlist (R14:
# defining "proven" loosely would launder a weak signal off a fake anchor). No registry
# probe can extend it. These are the validated in-game prior + the one real model edge.
_PROVEN: Tuple[str, ...] = ("ingame_prior", "ast_edge")
# Meta-learner families for STACK_OOF (param-free, leak-free OOF fits).
_META_FAMILIES: Tuple[str, ...] = ("ridge", "nnls", "logistic")
# Residual-learner families for RESID_BOOST.
_RESID_FAMILIES: Tuple[str, ...] = ("ridge", "tree")
# Re-fusion monotone maps for REFUSE_CAL.
_REFUSION_MAPS: Tuple[str, ...] = ("isotonic", "platt")

__all__ = [
    "FAMILIES", "FAMILY_STACK_OOF", "FAMILY_REGIME_MOE", "FAMILY_RESID_BOOST",
    "FAMILY_REFUSE_CAL", "FusionSpec", "validate_spec", "all_fusion_specs",
]


@dataclass(frozen=True)
class FusionSpec:
    """A spec-only model-fusion descriptor. Builds / fits NOTHING.

    `signature` is order-canonical + param-free; `fusion_id` is a refit-stable blake2b
    over (family|sport|target|signature) so the SAME idea hashes to the SAME id and a
    distinct config to a distinct id. `params` carries structured handles for the
    (downstream, sentinel-gated) build path. No $/ROI/edge field exists by construction.
    """

    family: str
    sport: str
    target: str
    signature: str
    params: Dict[str, str] = field(default_factory=dict)
    note: str = NOTE_CALIBRATION
    vs_close: str = VS_CLOSE

    @property
    def fusion_id(self) -> str:
        key = f"{self.family}|{self.sport}|{self.target}|{self.signature}".encode("ascii")
        return "fuse_" + hashlib.blake2b(key, digest_size=10).hexdigest()


def validate_spec(spec: FusionSpec) -> FusionSpec:
    """Validate a fusion spec or raise ValueError; returns it unchanged when clean.

    Rejects an unknown family / empty sport-or-target, any $-edge token or retracted
    number in ANY text field (via the shared assert_no_dollar honesty choke), and any
    base handle outside the STATIC _PROVEN allowlist. A rejected spec is NEVER enumerated.
    """
    if spec.family not in FAMILIES:
        raise ValueError("unknown fusion family: %r" % (spec.family,))
    if not str(spec.sport).strip():
        raise ValueError("empty sport in fusion spec")
    if not str(spec.target).strip():
        raise ValueError("empty target in fusion spec")
    for textfield in (spec.family, spec.sport, spec.target, spec.signature,
                      spec.note, spec.vs_close):
        _assert_clean(textfield)
    for k, v in spec.params.items():
        _assert_clean(k)
        _assert_clean(v)
    # Every base handle must be in the STATIC allowlist (no fake anchor).
    bases = spec.params.get("bases", "")
    for b in (h for h in str(bases).split("+") if h):
        if b not in _PROVEN:
            raise ValueError("base %r not in STATIC _PROVEN allowlist" % (b,))
    return spec


def _base_subsets(bases: Sequence[str]) -> List[Tuple[str, ...]]:
    """Lexicographic non-empty subsets of the proven bases (order-canonical -> one id)."""
    names = sorted(set(h for h in bases if h in _PROVEN))
    out: List[Tuple[str, ...]] = []
    for mask in range(1, 1 << len(names)):
        out.append(tuple(names[i] for i in range(len(names)) if mask & (1 << i)))
    return out


def _stack_oof(sport, target, bases) -> List[FusionSpec]:
    out: List[FusionSpec] = []
    for subset in _base_subsets(bases):
        joined = "+".join(subset)
        for meta in _META_FAMILIES:
            sig = "stack_oof=bases:%s|meta:%s" % (joined, meta)
            out.append(FusionSpec(FAMILY_STACK_OOF, sport, target, sig,
                                  {"bases": joined, "meta": meta}))
    return out


def _regime_moe(sport, target, bases) -> List[FusionSpec]:
    out: List[FusionSpec] = []
    joined = "+".join(sorted(set(h for h in bases if h in _PROVEN)))
    # one MoE spec per name-stable regime label (never a cluster-id); the split itself is
    # one config counted into K -- a degenerate split collapses to the global blend.
    for regime in REGIME_NAMES:
        sig = "regime_moe=bases:%s|regime:%s" % (joined, regime)
        out.append(FusionSpec(FAMILY_REGIME_MOE, sport, target, sig,
                              {"bases": joined, "regime": str(regime)}))
    return out


def _resid_boost(sport, target, bases) -> List[FusionSpec]:
    out: List[FusionSpec] = []
    for b in sorted(set(h for h in bases if h in _PROVEN)):
        for learner in _RESID_FAMILIES:
            sig = "resid_boost=base:%s|learner:%s" % (b, learner)
            out.append(FusionSpec(FAMILY_RESID_BOOST, sport, target, sig,
                                  {"bases": b, "learner": learner}))
    return out


def _refuse_cal(sport, target, bases) -> List[FusionSpec]:
    out: List[FusionSpec] = []
    joined = "+".join(sorted(set(h for h in bases if h in _PROVEN)))
    for mp in _REFUSION_MAPS:
        sig = "refuse_cal=bases:%s|map:%s" % (joined, mp)
        out.append(FusionSpec(FAMILY_REFUSE_CAL, sport, target, sig,
                              {"bases": joined, "map": mp}))
    return out


def all_fusion_specs(sport: str, target: str = "win_prob",
                     bases: Sequence[str] = _PROVEN) -> List[FusionSpec]:
    """Every fusion family's specs over the STATIC proven bases, ordered + all validated.

    Cold-start safe: an empty / all-rejected base list yields [] (NEVER fabricate a base
    handle). Deterministic order: family order, then signature lexicographic. Every spec
    passes validate_spec (the honesty choke) before it is enumerated.
    """
    use = [h for h in bases if h in _PROVEN]
    if not use:
        return []
    specs: List[FusionSpec] = []
    specs += _stack_oof(sport, target, use)
    specs += _regime_moe(sport, target, use)
    specs += _resid_boost(sport, target, use)
    specs += _refuse_cal(sport, target, use)
    specs = [validate_spec(s) for s in specs]
    fam_rank = {f: i for i, f in enumerate(FAMILIES)}
    specs.sort(key=lambda s: (fam_rank[s.family], s.signature))
    return specs
