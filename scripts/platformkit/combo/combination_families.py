"""scripts.platformkit.combo.combination_families -- the SPEC PRODUCER (5 families).

A combination spec names a TRANSFORM over a SMALL, named set of EXISTING in-game
detail signals plus an optional REGIME it is conditioned on. This module PRODUCES
spec descriptors ONLY: it never fits, never builds, never flips a flag, never reads
a corpus to decide an outcome. It is the pure proposal head of the combo generator.

The five families (each an order-canonical, person-free, param-free SIGNATURE):

  COMB_WEAK_ON_PROVEN  weak detail W conditioned on / interacted-with the PROVEN
                       in-game prior P (the margin/time state). HIGHEST prior --
                       in-game prior conditioning is the only proven beat. P may
                       ONLY be a name in the STATIC _PROVEN allowlist (no probe can
                       extend it -- R6).
  COMB_INTERACTION     A*B or A*sign(B): does the product of two weak detail signals
                       carry joint structure neither shows alone?
  COMB_REGIME          a detail signal applied ONLY inside a game-state regime bucket
                       (e.g. run_diff x lead-sign): real inside a regime, washed out
                       pooled?
  COMB_RESID_ON_RESID  gate B on A's residual: does B explain A's leftover structure?
  COMB_DETAIL_x_DETAIL two raw detail layers multiplied (cross-layer interaction).

ORDER-CANONICAL (R4): every two-signal family LEXICOGRAPHICALLY SORTS its pair so
A*B and B*A collapse to ONE signature -> ONE id. A STATIC _PROVEN allowlist is the
ONLY anchor COMB_WEAK_ON_PROVEN may condition on.

NEVER writes data/registry/, never flips a flag, never creates the PIPELINE_ENABLED
sentinel. Calibration, not edge: no $ / ROI / market-edge token anywhere. ASCII;
stdlib only; <=300 LOC.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# ----------------------------------------------------------------- family ids
FAMILY_WEAK_ON_PROVEN = "COMB_WEAK_ON_PROVEN"
FAMILY_INTERACTION = "COMB_INTERACTION"
FAMILY_REGIME = "COMB_REGIME"
FAMILY_RESID_ON_RESID = "COMB_RESID_ON_RESID"
FAMILY_DETAIL_x_DETAIL = "COMB_DETAIL_x_DETAIL"

FAMILIES = (
    FAMILY_WEAK_ON_PROVEN, FAMILY_INTERACTION, FAMILY_REGIME,
    FAMILY_RESID_ON_RESID, FAMILY_DETAIL_x_DETAIL,
)

# The ONLY anchors a weak-on-proven combo may condition on. STATIC + person-free; no
# probe can extend it (R6: defining "proven" loosely would launder a weak signal off a
# fake anchor). The proven in-game prior is the margin/time STATE the gate's base fits.
_PROVEN: Tuple[str, ...] = ("ingame_prior", "ast_edge")

# Regime buckets reuse a small, descriptive, person-free vocabulary (no new numbers).
_REGIMES: Tuple[str, ...] = ("lead_home", "lead_away", "tied", "late_game")

# Interaction operators (param-free, deterministic transforms).
_OPS: Tuple[str, ...] = ("mul", "mul_sign")

# Hard SURFACE caps (proposals, never evidence). They bound the ENUMERABLE surface;
# the bandit + K-cap (combination_enum) then picks K << surface to actually propose.
_MAX_BASE_SIGNALS = 16
_MAX_PAIRS = 24
_MAX_REGIMES_PER_BASE = 4
_MAX_PROVEN_PER_WEAK = 2

# A combo signature must NOT contain a person token or a KMeans cluster-id (mirrors the
# signal_factory slug rule: selectors use NAMES not cluster-ids).
_FORBIDDEN_HANDLE = re.compile(r"(?:kmeans_|cluster_|^c\d+$)")
# Forbidden honesty tokens (a $/edge/roi/% token would launder a market claim).
_FORBIDDEN_TOKEN = re.compile(r"(?:\$|\broi\b|\bedge\b|%)", re.IGNORECASE)


@dataclass(frozen=True)
class CombinationSpec:
    """A spec-only combination descriptor. Builds/fits NOTHING.

    `signature` is order-canonical + param-free; `combo_id` is a refit-stable blake2b
    over (family|sport|target|signature) so A*B and B*A hash to ONE id. `params` carries
    the structured handles for the (downstream, human-gated) build path.
    """

    family: str
    sport: str
    target: str
    signature: str
    params: Dict[str, str] = field(default_factory=dict)

    @property
    def combo_id(self) -> str:
        key = f"{self.family}|{self.sport}|{self.target}|{self.signature}".encode("utf-8")
        return hashlib.blake2b(key, digest_size=12).hexdigest()


def _clean(handle: str) -> Optional[str]:
    """Lower-snake a signal handle; reject person/cluster-id handles (return None)."""
    h = str(handle).strip().lower()
    if not h or _FORBIDDEN_HANDLE.search(h):
        return None
    return h


def validate_spec(spec: CombinationSpec) -> bool:
    """True iff the spec is honest: known family, no $/edge token, person-free handles."""
    if spec.family not in FAMILIES:
        return False
    if _FORBIDDEN_TOKEN.search(spec.signature):
        return False
    for v in spec.params.values():
        if _FORBIDDEN_TOKEN.search(str(v)):
            return False
    # every handle in the signature must be person-free / cluster-id-free
    for tok in re.split(r"[=|:_]+", spec.signature):
        if _FORBIDDEN_HANDLE.search(tok):
            return False
    return True


def _pair(a: str, b: str) -> Tuple[str, str]:
    """Lexicographically sorted pair so A*B == B*A (R4 order-canonical)."""
    return (a, b) if a <= b else (b, a)


def _weak_on_proven(sport, target, weaks) -> List[CombinationSpec]:
    out: List[CombinationSpec] = []
    for w in weaks:
        for p in _PROVEN[:_MAX_PROVEN_PER_WEAK]:
            sig = f"comb_weak_on_proven=weak:{w}|proven:{p}"
            out.append(CombinationSpec(FAMILY_WEAK_ON_PROVEN, sport, target, sig,
                                       {"weak": w, "proven": p}))
    return out


def _interaction(sport, target, pairs) -> List[CombinationSpec]:
    out: List[CombinationSpec] = []
    for (a, b) in pairs:
        for op in _OPS:
            ca, cb = _pair(a, b)
            sig = f"comb_interact=a:{ca}|b:{cb}|op:{op}"
            out.append(CombinationSpec(FAMILY_INTERACTION, sport, target, sig,
                                       {"a": ca, "b": cb, "op": op}))
    return out


def _regime(sport, target, weaks) -> List[CombinationSpec]:
    out: List[CombinationSpec] = []
    for w in weaks:
        for r in _REGIMES[:_MAX_REGIMES_PER_BASE]:
            sig = f"comb_regime=base:{w}|regime:{r}"
            out.append(CombinationSpec(FAMILY_REGIME, sport, target, sig,
                                       {"base": w, "regime": r}))
    return out


def _resid_on_resid(sport, target, pairs) -> List[CombinationSpec]:
    out: List[CombinationSpec] = []
    for (a, b) in pairs:
        # resid-on-resid is ASYMMETRIC (outer A, inner B) -- emit BOTH orderings, but
        # canonicalise the SIGNATURE direction so the pair-de-dup still holds per ordering.
        for outer, inner in ((a, b), (b, a)):
            if outer == inner:
                continue
            sig = f"comb_resid_on_resid=outer:{outer}|inner:{inner}"
            out.append(CombinationSpec(FAMILY_RESID_ON_RESID, sport, target, sig,
                                       {"outer": outer, "inner": inner}))
    return out


def _detail_x_detail(sport, target, pairs) -> List[CombinationSpec]:
    out: List[CombinationSpec] = []
    for (a, b) in pairs:
        ca, cb = _pair(a, b)
        sig = f"comb_detail_x_detail=a:{ca}|b:{cb}"
        out.append(CombinationSpec(FAMILY_DETAIL_x_DETAIL, sport, target, sig,
                                   {"a": ca, "b": cb}))
    return out


def all_combination_specs(sport: str, target: str,
                          detail_signals: Sequence[str]) -> List[CombinationSpec]:
    """Union of all five families over a SMALL set of name-stable detail handles.

    `detail_signals` are the name-stable leaf handles of the in-game detail layer (e.g.
    'run_diff', 'pace_so_far'). Cold-start: an empty / all-rejected handle list returns
    [] (NEVER fabricate a signal handle). The pair set is the lexicographically-canonical
    unordered pairs, capped at _MAX_PAIRS. Every emitted spec passes validate_spec.
    """
    weaks = [c for c in (_clean(s) for s in detail_signals) if c is not None]
    # dedup-preserve-order, cap the base surface
    seen: set = set()
    weaks = [w for w in weaks if not (w in seen or seen.add(w))][:_MAX_BASE_SIGNALS]
    if not weaks:
        return []
    pairs: List[Tuple[str, str]] = []
    pseen: set = set()
    for i in range(len(weaks)):
        for j in range(i + 1, len(weaks)):
            p = _pair(weaks[i], weaks[j])
            if p not in pseen:
                pseen.add(p)
                pairs.append(p)
    pairs = pairs[:_MAX_PAIRS]
    specs: List[CombinationSpec] = []
    specs += _weak_on_proven(sport, target, weaks)
    specs += _interaction(sport, target, pairs)
    specs += _regime(sport, target, weaks)
    specs += _resid_on_resid(sport, target, pairs)
    specs += _detail_x_detail(sport, target, pairs)
    specs = [s for s in specs if validate_spec(s)]
    # deterministic order: family order, then signature lexicographic
    fam_rank = {f: i for i, f in enumerate(FAMILIES)}
    specs.sort(key=lambda s: (fam_rank[s.family], s.signature))
    return specs


__all__ = [
    "FAMILIES", "FAMILY_WEAK_ON_PROVEN", "FAMILY_INTERACTION", "FAMILY_REGIME",
    "FAMILY_RESID_ON_RESID", "FAMILY_DETAIL_x_DETAIL",
    "CombinationSpec", "validate_spec", "all_combination_specs",
]
