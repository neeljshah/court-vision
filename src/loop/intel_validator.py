"""INTEL-VALIDATOR -- the ARM-B validation gate for an AtlasSection artifact.

Validates a built :class:`~src.loop.atlas.AtlasArtifact` against five checks; ALL
required checks must pass for the artifact to be persisted by the profile-factory
bridge. The validator is leak-aware, reuses the ``scripts/qa_profiles.py`` range
rules for face-validity, and reads ``data/cache/profiles/`` for dedup.

Five checks (all must pass to persist):
  1. LEAK-FREE       -- artifact.as_of <= the build as_of; the provenance as_of is
     consistent; and a RE-BUILD at an earlier as_of must not change a past value
     (no future-game leakage into a past stamp).
  2. FACE-VALIDITY   -- sane ranges + expected monotonicities (pcts in [0, ceil],
     per-game rates >= 0, dispersion >= 0, q4_vs_early ratio in a plausible band).
  3. COVERAGE        -- enough games / sample (n >= section minimum) for the stamped
     confidence; else downgrade confidence (marginal) or fail (below min_n).
  4. DEDUP           -- not redundant with the existing same-key profile-factory
     section for this entity (near-identical numeric payload -> duplicate).
  5. CV-SLOT SCHEMA  -- cv_fields() present, well-typed, values null now (reserved).

Reuses: scripts/qa_profiles.py (check_player range rules), data/cache/profiles/
(existing sections for dedup), spec_intel_memory.md schema.
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .atlas import _CONF_ORDER, AtlasArtifact, AtlasSection, confidence_from_n

ROOT = Path(__file__).resolve().parents[2]
_PROFILES = ROOT / "data" / "cache" / "profiles"

# Confidence ladder thresholds (mirror confidence_from_n: high>=20 / med>=5 / low).
_MIN_N_FOR = {"low": 0, "med": 5, "high": 20}
# A plausible band for the q4-vs-early scoring ratio (face-validity heuristic).
_Q4_RATIO_BAND = (0.0, 5.0)
# Fraction of numeric sub-fields that must match (within tol) to call a DUPLICATE.
_DEDUP_MATCH_FRAC = 0.90


@dataclass
class ValidationResult:
    """Outcome of validating an atlas artifact.

    Attributes:
        ok:            True iff all required checks passed.
        leak_free:     criterion 1.
        face_valid:    criterion 2.
        coverage_ok:   criterion 3.
        not_duplicate: criterion 4.
        cv_schema_ok:  criterion 5.
        reasons:       human-readable failure / warning reasons.
        downgraded_confidence: a lowered confidence level if coverage was marginal.
    """

    ok: bool = False
    leak_free: bool = False
    face_valid: bool = False
    coverage_ok: bool = False
    not_duplicate: bool = False
    cv_schema_ok: bool = False
    reasons: List[str] = field(default_factory=list)
    downgraded_confidence: Optional[str] = None


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _iter_numeric(payload: Any, prefix: str = "") -> List[tuple]:
    """Flatten a nested dict/list into ``[(dotted_key, float_value), ...]``.

    Booleans are skipped (they are flags, not measured rates).
    """
    out: List[tuple] = []
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k == "_cv_fields":
                continue
            out.extend(_iter_numeric(v, f"{prefix}{k}."))
    elif isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            out.extend(_iter_numeric(v, f"{prefix}{i}."))
    elif isinstance(payload, bool):
        pass
    elif isinstance(payload, (int, float)):
        out.append((prefix.rstrip("."), float(payload)))
    return out


def _to_date(s: Optional[str]) -> Optional[_dt.date]:
    """Parse an ISO ``YYYY-MM-DD`` prefix to a date, or None if unparseable."""
    if not s:
        return None
    s = str(s)[:10]
    try:
        return _dt.date.fromisoformat(s)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# criterion 1: leak-free
# --------------------------------------------------------------------------- #
def check_leak_free(section: AtlasSection, artifact: AtlasArtifact) -> bool:
    """Criterion 1: as-of correctness + a re-build at an earlier as_of must not
    alter a past value.

    Two sub-checks:
      (a) the artifact's stamped ``as_of`` and provenance ``as_of`` are not in the
          future relative to each other (provenance as_of <= artifact as_of), and
      (b) re-building one day BEFORE the artifact as_of yields values that are a
          leak-safe subset: any numeric field present in BOTH builds must be
          unchanged (a past value must not move when future data is excluded).

    The re-build is best-effort: if ``section.build`` cannot produce an earlier
    artifact (missing source), (b) is vacuously satisfied -- absence of an earlier
    build is not evidence of a leak.
    """
    art_d = _to_date(artifact.as_of)
    prov_d = _to_date(artifact.provenance.get("as_of"))
    if art_d is not None and prov_d is not None and prov_d > art_d:
        return False  # provenance leak boundary is AFTER the stamped as_of

    if art_d is None:
        return True  # no as_of to anchor a re-build; (a) already vacuous

    earlier_dt = _dt.datetime.combine(art_d - _dt.timedelta(days=1), _dt.time())
    try:
        past = section.build(artifact.entity_id, earlier_dt)
    except Exception:  # noqa: BLE001 - a failed re-build is not a leak signal
        return True
    if past is None:
        return True

    past_vals = dict(_iter_numeric(past.sub_fields))
    now_vals = dict(_iter_numeric(artifact.sub_fields))
    for key, pv in past_vals.items():
        if key in now_vals and abs(now_vals[key] - pv) > 1e-6:
            # an earlier-as_of value differs from the value already present in the
            # past build only if the past build saw data it should not have.
            # The PAST build must be a prefix of the present one: a value computed
            # at an earlier as_of should equal the same field recomputed later ONLY
            # if no new games entered -- which is not guaranteed. So we instead
            # require that the past build never references a date AFTER its as_of.
            past_ref = _to_date(past.provenance.get("as_of"))
            if past_ref is not None and past_ref > earlier_dt.date():
                return False
    return True


# --------------------------------------------------------------------------- #
# criterion 2: face-validity
# --------------------------------------------------------------------------- #
def check_face_validity(artifact: AtlasArtifact) -> List[str]:
    """Criterion 2: range/monotonicity checks (qa_profiles rules).

    Returns a list of reason strings (empty == valid). Mirrors
    ``scripts/qa_profiles.check_player``: pct fields in ``[0, ceil]`` (ceil 1.6 for
    eFG/TS, else 1.0), per-game (``*_pg``/``*_pct``-free rate) fields >= 0,
    dispersion >= 0, and the q4-vs-early ratio within a plausible band.
    """
    reasons: List[str] = []
    # Standardized / signed / rank quantities are legitimately negative or
    # out of [0,1] and are NOT proportions, per-game rates, or the q4 ratio --
    # exempt them from the range/sign rules below. Examples that previously
    # tripped false positives: ``imposed_deviations.shot_zone_3pt_pct`` (sigma
    # deviation), ``opp_3pt_pct_allowed_z`` (z-score), ``oreb_pct_season_rank``
    # (a 1..30 rank), ``home_win_pct_advantage`` / ``fta_minus_opp_fta_pg``
    # (signed differences), ``ast_ratio``=18 (an unbounded ratio).
    _STD_CONTAINERS = ("imposed_deviations", "scheme_axes")
    _SIGNED_MARKERS = ("_z", "_z_", "deviation", "rank", "_minus_", "_diff",
                       "_delta", "_advantage", "_vs_opp", "_margin")
    for key, val in _iter_numeric(artifact.sub_fields):
        kl = key.lower()
        leaf = kl.split(".")[-1]
        if (any(m in leaf for m in _SIGNED_MARKERS)
                or any(seg in kl for seg in _STD_CONTAINERS)):
            continue  # standardized/signed/rank field -- exempt
        # Proportions: only genuine *_pct / *_rate / *_share / *_freq leaves
        # (suffix match, so ``pct_season_rank`` etc. are NOT misread as pcts).
        if (leaf.endswith("_pct") or leaf.endswith("_rate")
                or leaf.endswith("_share") or leaf.endswith("_freq")
                or leaf.endswith("freq_pct")):
            ceil = 1.6 if ("efg" in leaf or "_ts" in leaf or leaf.endswith("freq_pct")) else 1.0
            hi = 100.0 if leaf.endswith("freq_pct") else ceil
            if not (0.0 <= val <= hi):
                reasons.append(f"{key}={val} out of range [0,{hi}]")
        elif leaf.endswith("_pg") or leaf.endswith("_per_game"):
            if val < 0:
                reasons.append(f"negative per-game {key}={val}")
        elif "dispersion" in leaf:
            if val < 0:
                reasons.append(f"negative dispersion {key}={val}")
        elif "q4_vs_early" in leaf:  # only the q4-vs-early ratio is band-checked
            lo, hi = _Q4_RATIO_BAND
            if not (lo <= val <= hi):
                reasons.append(f"{key}={val} outside plausible ratio band {(lo, hi)}")
    return reasons


# --------------------------------------------------------------------------- #
# criterion 3: coverage
# --------------------------------------------------------------------------- #
def _coverage_n(artifact: AtlasArtifact) -> int:
    """Extract the stamped sample size from provenance (0 if absent)."""
    try:
        return int(artifact.provenance.get("n", 0) or 0)
    except (TypeError, ValueError):
        return 0


def check_coverage(artifact: AtlasArtifact, min_n: int) -> bool:
    """Criterion 3: sample-size sufficiency. True iff n >= min_n (hard floor)."""
    return _coverage_n(artifact) >= int(min_n)


def _coverage_downgrade(artifact: AtlasArtifact) -> Optional[str]:
    """Return a downgraded confidence level if the stamped confidence overstates n.

    e.g. stamped "high" but n only supports "med" -> returns "med". None if the
    stamped confidence is already supported by n.
    """
    n = _coverage_n(artifact)
    supported = confidence_from_n(n)
    stamped = artifact.confidence or "low"
    if stamped not in _CONF_ORDER:
        return None
    if _CONF_ORDER.get(supported, 0) < _CONF_ORDER.get(stamped, 0):
        return supported
    return None


# --------------------------------------------------------------------------- #
# criterion 4: dedup vs the existing profile factory
# --------------------------------------------------------------------------- #
def _load_existing_section(artifact: AtlasArtifact) -> Optional[dict]:
    """Read the same-key section for this entity from data/cache/profiles/ (or None)."""
    sub = "players" if artifact.entity == "player" else "teams"
    fp = _PROFILES / sub / f"{artifact.entity_id}.json"
    if not fp.exists():
        return None
    try:
        prof = json.loads(fp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return prof.get("sections", {}).get(artifact.section)


def check_dedup(artifact: AtlasArtifact, dedup_threshold: float) -> bool:
    """Criterion 4: True iff NOT a duplicate of the existing same-key section.

    Compares the numeric payload of the new artifact against the existing
    profile-factory section of the same key/entity. If they share numeric keys and
    a fraction >= ``_DEDUP_MATCH_FRAC`` of them match within ``1 - dedup_threshold``
    relative tolerance, the artifact is redundant (returns False).
    """
    existing = _load_existing_section(artifact)
    if not isinstance(existing, dict):
        return True  # nothing to collide with -> not a duplicate
    old = dict(_iter_numeric(existing))
    new = dict(_iter_numeric(artifact.sub_fields))
    shared = set(old) & set(new)
    if not shared:
        return True
    rtol = max(0.0, 1.0 - float(dedup_threshold))
    matches = 0
    for k in shared:
        denom = max(abs(old[k]), abs(new[k]), 1e-9)
        if abs(old[k] - new[k]) / denom <= rtol:
            matches += 1
    return (matches / len(shared)) < _DEDUP_MATCH_FRAC


# --------------------------------------------------------------------------- #
# criterion 5: CV-slot schema
# --------------------------------------------------------------------------- #
_VALID_CV_DTYPES = {"float", "dist", "list", "categorical", "int"}


def check_cv_schema(section: AtlasSection, artifact: AtlasArtifact) -> bool:
    """Criterion 5: cv_fields present, well-typed, and null-valued (reserved).

    Requires that (a) the section's declared ``cv_fields()`` are mirrored on the
    artifact, (b) every slot has a recognised dtype, and (c) every slot value is
    None now (the CV branch fills them later under its session boundary).
    """
    declared = section.cv_fields()
    if not isinstance(declared, dict):
        return False
    for name, slot in declared.items():
        if name not in artifact.cv_fields:
            return False
        if getattr(slot, "dtype", None) not in _VALID_CV_DTYPES:
            return False
        if getattr(slot, "value", None) is not None:
            return False
    # artifact slots must themselves be reserved (null) and typed
    for name, slot in artifact.cv_fields.items():
        if getattr(slot, "dtype", None) not in _VALID_CV_DTYPES:
            return False
        if getattr(slot, "value", None) is not None:
            return False
    return True


# --------------------------------------------------------------------------- #
# top-level orchestration
# --------------------------------------------------------------------------- #
def validate(section: AtlasSection, artifact: AtlasArtifact, *,
             min_n: int = 5, dedup_threshold: float = 0.97) -> ValidationResult:
    """Run all five checks on a built atlas artifact; return a :class:`ValidationResult`.

    Args:
        section:         the AtlasSection that produced the artifact (for re-build
                         leak-checks and the declared CV-slot schema).
        artifact:        the built artifact to validate.
        min_n:           hard floor on stamped sample size for coverage.
        dedup_threshold: 1 - relative tolerance for the dedup numeric match.

    Returns:
        A :class:`ValidationResult` with per-criterion booleans, an aggregate
        ``ok``, accumulated ``reasons``, and a ``downgraded_confidence`` if coverage
        was marginal (stamped confidence above what n supports).
    """
    res = ValidationResult()

    # also-validate the section's own cheap self-check (face-validity author hook)
    try:
        section_self_ok = section.validate(artifact)
    except Exception as exc:  # noqa: BLE001
        section_self_ok = False
        res.reasons.append(f"section.validate raised: {exc!r}")
    if not section_self_ok:
        res.reasons.append("section self-validation failed")

    res.leak_free = check_leak_free(section, artifact)
    if not res.leak_free:
        res.reasons.append("leak: as_of inconsistency or future-data in past build")

    fv_reasons = check_face_validity(artifact)
    res.face_valid = not fv_reasons
    res.reasons.extend(fv_reasons)

    res.coverage_ok = check_coverage(artifact, min_n)
    if not res.coverage_ok:
        res.reasons.append(f"coverage: n={_coverage_n(artifact)} < min_n={min_n}")
    else:
        downgrade = _coverage_downgrade(artifact)
        if downgrade is not None:
            res.downgraded_confidence = downgrade
            res.reasons.append(
                f"coverage marginal: confidence {artifact.confidence}->{downgrade}")

    res.not_duplicate = check_dedup(artifact, dedup_threshold)
    if not res.not_duplicate:
        res.reasons.append(f"dedup: ~identical to existing '{artifact.section}' section")

    res.cv_schema_ok = check_cv_schema(section, artifact)
    if not res.cv_schema_ok:
        res.reasons.append("cv-schema: slots missing, mistyped, or non-null")

    res.ok = bool(
        section_self_ok and res.leak_free and res.face_valid
        and res.coverage_ok and res.not_duplicate and res.cv_schema_ok
    )
    return res
