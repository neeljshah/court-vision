"""scripts.platformkit.improve.candidate_families -- A4 candidate-family REGISTRY.

Family REGISTRY + candidate-id schema + $-and-retracted-number validator.
Produces SPECS ONLY -- never builds a candidate dict, never fits anything.
Only path from spec to gate-consumable candidate: recalibrator.build_candidate (MF4).

Families: recal_variant, ingame_interaction, playstyle_corr, scheme_prior,
  archetype_matchup (LANE C), ingame_segment (W10), prop_recency (W10).
Validator (validate_spec / assert_no_dollar): REJECTS any spec with $/ROI/retracted
  numbers. UNITS only. INVARIANTS: no data/registry/ writes, no flag flip, no fit.
  Calibration NOT edge; vs_close UNPROVEN. Stdlib only; ASCII; <=300 LOC.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

NOTE_CALIBRATION = "calibration, not edge"
VS_CLOSE = "UNPROVEN"

# Families this registry knows how to enumerate. SPEC producers only.
FAMILY_RECAL = "recal_variant"
FAMILY_INGAME = "ingame_interaction"
# LANE C signal-factory families (vault-taxonomy-conditioned; person-free, name-stable).
# These are PROPOSAL families only -- the recalibrator.build_candidate choke still
# decides if/whether to build, and the loop stays inert with the sentinel absent.
FAMILY_PLAYSTYLE_CORR = "playstyle_corr"
FAMILY_SCHEME_PRIOR = "scheme_prior"
FAMILY_ARCHETYPE_MATCHUP = "archetype_matchup"
# W10 additions: finer in-game segment recal + prop recency recal (2 new spec families).
FAMILY_INGAME_SEGMENT = "ingame_segment"   # margin x period x time_bucket Platt (W10)
FAMILY_PROP_RECENCY = "prop_recency"       # recency-weighted prop Platt (W10 finding)
FAMILIES: Tuple[str, ...] = (
    FAMILY_RECAL, FAMILY_INGAME,
    FAMILY_PLAYSTYLE_CORR, FAMILY_SCHEME_PRIOR, FAMILY_ARCHETYPE_MATCHUP,
    FAMILY_INGAME_SEGMENT, FAMILY_PROP_RECENCY,
)

# Recalibration-family variants the recalibrator.build_candidate choke point can fit.
# The recalibrator currently fits a single Platt variant; we enumerate the families it
# is allowed to draw from. Adding a variant here is a spec change, never a fit here.
_RECAL_VARIANTS: Tuple[str, ...] = ("platt",)

# In-game state buckets (the proven conditioning lever). These are DESCRIPTIVE labels
# only -- the recalibrator decides how (or whether) to fit a conditioned variant.
_INGAME_MARGIN_BUCKETS: Tuple[str, ...] = ("close", "mid", "blowout")
_INGAME_PERIOD_BUCKETS: Tuple[str, ...] = ("early", "late")
_INGAME_TIME_BUCKETS: Tuple[str, ...] = ("ample", "scarce")

# --- the $-and-retracted-number validator (honesty choke) ---------------------------
# Retracted MEASUREMENT ARTIFACTS (see .claude/rules/no-edge-claims.md). They may NEVER
# appear in a live spec; only inside an explicit retraction context (not here).
_RETRACTED_NUMBERS: Tuple[str, ...] = (
    "+18.38", "18.38", "0.119", "+54", "78.11", "8.94", "54.57",
)
# Forbidden $-edge tokens anywhere in a spec's text fields.
_FORBIDDEN_TOKENS: Tuple[str, ...] = ("$", "roi", "pnl", "dollar", "edge", "%")
_FORBIDDEN_KEY_TOKENS: Tuple[str, ...] = ("roi", "pnl", "dollar", "edge", "$")


def _contains_retracted(text: str) -> Optional[str]:
    """Return the first retracted number found in `text`, else None.

    Matches the retracted token as a standalone numeric (not as a substring of an
    unrelated longer number), so an innocuous '118.38' or '0.1190001'-free value does
    not false-trip while '+18.38' / '78.11' as written are caught.
    """
    for tok in _RETRACTED_NUMBERS:
        # word-ish boundary: the retracted token not flanked by another digit/dot.
        esc = re.escape(tok)
        if re.search(r"(?<![\d.])" + esc + r"(?![\d.])", text):
            return tok
    return None


def assert_no_dollar(text: Any) -> None:
    """Raise ValueError if `text` carries a $-edge token or a retracted number.

    The single honesty choke every spec text field passes through. UNITS only.

    The MANDATED canonical disclaimer ("calibration, not edge") is the one allowed use
    of the word "edge" -- it is the rail-required phrase, not an edge claim. It is
    stripped before token scanning so the disclaimer cannot trip its own guard; the
    retracted-number scan still runs on the original text.
    """
    s = str(text)
    scan = s.lower().replace(NOTE_CALIBRATION, " ")  # allow the mandated disclaimer
    for tok in _FORBIDDEN_TOKENS:
        if tok in scan:
            raise ValueError("forbidden $-edge token %r in spec text: %r" % (tok, s))
    hit = _contains_retracted(s)
    if hit is not None:
        raise ValueError("retracted number %r in spec text: %r" % (hit, s))


@dataclass(frozen=True)
class CandidateSpec:
    """An INERT candidate proposal -- never a built candidate, never a verdict.

    A spec names WHICH recalibration/in-game-conditioning idea to ask the
    recalibrator.build_candidate choke point to package. It carries provenance and a
    deterministic candidate_id; it carries NO predictions, NO fit, NO $/ROI field.
    """

    family: str
    sport: str
    target: str
    scope: str           # "pregame" | "ingame"
    signature: str       # canonical, param-free; same idea -> same id
    rationale: str = ""
    note: str = NOTE_CALIBRATION
    vs_close: str = VS_CLOSE
    params: Dict[str, Any] = field(default_factory=dict)

    @property
    def candidate_id(self) -> str:
        return candidate_id(self.family, self.sport, self.target, self.signature)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "family": self.family,
            "sport": self.sport,
            "target": self.target,
            "scope": self.scope,
            "signature": self.signature,
            "rationale": self.rationale,
            "note": self.note,
            "vs_close": self.vs_close,
            "params": dict(self.params),
            "status": "PROPOSED",
        }


def candidate_id(family: str, sport: str, target: str, signature: str) -> str:
    """Deterministic blake2b id = blake2b(family|sport|target|signature).

    Stable across process restarts and param re-rolls: the SAME (family, sport, target,
    signature) ALWAYS yields the SAME id, and a distinct signature yields a distinct id
    (collision probability negligible at 16 hex / 64 bits). The dedup key.
    """
    key = "|".join((str(family), str(sport), str(target), str(signature)))
    digest = hashlib.blake2b(key.encode("ascii", "strict"), digest_size=8).hexdigest()
    return "cand_" + digest


def validate_spec(spec: CandidateSpec) -> CandidateSpec:
    """Validate a spec or raise ValueError. Returns the spec unchanged when clean.

    Rejects:
      * an unknown family / empty sport / empty target / bad scope;
      * any text field carrying a $-edge token or a retracted number;
      * a params dict carrying a forbidden $-edge KEY.
    A rejected spec is NEVER enumerated (the enumerator calls this on every spec).
    """
    if spec.family not in FAMILIES:
        raise ValueError("unknown family: %r" % (spec.family,))
    if not str(spec.sport).strip():
        raise ValueError("empty sport in spec")
    if not str(spec.target).strip():
        raise ValueError("empty target in spec")
    if spec.scope not in ("pregame", "ingame"):
        raise ValueError("bad scope: %r" % (spec.scope,))
    for textfield in (spec.family, spec.sport, spec.target, spec.scope,
                      spec.signature, spec.rationale, spec.note, spec.vs_close):
        assert_no_dollar(textfield)
    for k, v in spec.params.items():
        kl = str(k).lower()
        if any(tok in kl for tok in _FORBIDDEN_KEY_TOKENS):
            raise ValueError("forbidden $-edge param key: %r" % (k,))
        assert_no_dollar(k)
        assert_no_dollar(v)
    return spec


# --- family generators (SPEC producers; pure; never fit, never build a candidate) ---
def gen_recal_variant(sport: str, target: str = "win_prob") -> List[CandidateSpec]:
    """Recalibration-family SPECS for `sport` (one per known recal variant).

    Each spec names a recal family (e.g. platt) the recalibrator.build_candidate choke
    point may fit on the clean settled window. This producer NEVER fits anything.
    """
    out: List[CandidateSpec] = []
    for variant in _RECAL_VARIANTS:
        sig = "recal=%s" % variant
        spec = CandidateSpec(
            family=FAMILY_RECAL, sport=str(sport), target=str(target),
            scope="pregame", signature=sig,
            rationale="recal-family %s re-fit on the clean settled window" % variant,
            params={"recal": variant})
        out.append(validate_spec(spec))
    return out


def gen_ingame_interaction(sport: str, target: str = "win_prob") -> List[CandidateSpec]:
    """In-game state-interaction conditioning SPECS (the proven north-star lever).

    Enumerates margin x period x time-bucket conditioning splits as SPECS only. Each
    spec proposes a conditioned recalibration; the recalibrator decides if/how to fit
    it. scope="ingame" so the DM-by-game discipline applies downstream. Never fits.
    """
    out: List[CandidateSpec] = []
    for margin in _INGAME_MARGIN_BUCKETS:
        for period in _INGAME_PERIOD_BUCKETS:
            for time_b in _INGAME_TIME_BUCKETS:
                sig = "ingame=margin:%s|period:%s|time:%s" % (margin, period, time_b)
                spec = CandidateSpec(
                    family=FAMILY_INGAME, sport=str(sport), target=str(target),
                    scope="ingame", signature=sig,
                    rationale=("in-game conditioning split margin=%s period=%s time=%s"
                               % (margin, period, time_b)),
                    params={"margin_bucket": margin, "period_bucket": period,
                            "time_bucket": time_b})
                out.append(validate_spec(spec))
    return out


def gen_ingame_segment(sport: str, target: str = "win_prob") -> List[CandidateSpec]:
    """W10: margin x period x time_bucket segment Platt SPECS. Never fits; scope=ingame."""
    out: List[CandidateSpec] = []
    for mb in ("close", "mid", "blowout"):
        for pb in ("early", "late"):
            for tb in ("ample", "scarce"):
                sig = "ingame_seg=margin:%s|period:%s|time:%s" % (mb, pb, tb)
                out.append(validate_spec(CandidateSpec(
                    family=FAMILY_INGAME_SEGMENT, sport=str(sport), target=str(target),
                    scope="ingame", signature=sig,
                    rationale="ingame segment recal margin=%s period=%s time=%s" % (mb, pb, tb),
                    params={"margin_bucket": mb, "period_bucket": pb, "time_bucket": tb})))
    return out


def gen_prop_recency(sport: str, target: str = "prop_prob",
                     stats: Optional[Sequence[str]] = None) -> List[CandidateSpec]:
    """W10: recency-weighted Platt prop recal SPECS (recency beats volume). scope=pregame."""
    stats_list = list(stats) if stats else ["all"]
    out: List[CandidateSpec] = []
    for stat in stats_list:
        out.append(validate_spec(CandidateSpec(
            family=FAMILY_PROP_RECENCY, sport=str(sport), target=str(target),
            scope="pregame", signature="prop_recency=stat:%s" % stat,
            rationale="recency-weighted prop recal stat=%s (recency beats volume)" % stat,
            params={"stat": stat, "half_life_days": 30})))
    return out


def _signal_factory_specs(sport: str, target: str) -> List[CandidateSpec]:
    """Additively pull the LANE C signal-factory specs (vault-conditioned), if available.

    Lazy import so candidate_families has NO hard dependency on the factory (which depends
    on this module for CandidateSpec). A missing factory / empty vault yields [] -- the
    registry simply gains nothing, never raises, and the loop stays inert. Each returned
    spec is re-validated through this module's honesty choke before it is enumerated.
    """
    try:
        from scripts.platformkit.signals.signal_factory import all_signal_specs
    except Exception:  # noqa: BLE001 -- no factory -> the registry simply gains nothing.
        return []
    out: List[CandidateSpec] = []
    try:
        for spec in all_signal_specs(sport, target):
            try:
                out.append(validate_spec(spec))  # honesty choke on every factory spec
            except ValueError:
                continue  # a tainted spec is dropped, never enumerated.
    except Exception:  # noqa: BLE001 -- a factory failure must never wedge enumeration.
        return out
    return out


def all_specs(sport: str, target: str = "win_prob") -> List[CandidateSpec]:
    """All family specs for `sport` (recal + ingame + W10 segment/recency + factory)."""
    specs: List[CandidateSpec] = []
    specs.extend(gen_recal_variant(sport, target))
    specs.extend(gen_ingame_interaction(sport, target))
    specs.extend(gen_ingame_segment(sport, target))      # W10: segment recal
    specs.extend(gen_prop_recency(sport, "prop_prob"))   # W10: recency prop recal
    specs.extend(_signal_factory_specs(sport, target))
    return specs


__all__ = [
    "CandidateSpec", "candidate_id", "validate_spec", "assert_no_dollar",
    "gen_recal_variant", "gen_ingame_interaction", "all_specs",
    "gen_ingame_segment", "gen_prop_recency",
    "FAMILIES", "FAMILY_RECAL", "FAMILY_INGAME",
    "FAMILY_PLAYSTYLE_CORR", "FAMILY_SCHEME_PRIOR", "FAMILY_ARCHETYPE_MATCHUP",
    "FAMILY_INGAME_SEGMENT", "FAMILY_PROP_RECENCY",
    "NOTE_CALIBRATION", "VS_CLOSE",
]
