"""scripts.platformkit.improve.prioritizer -- A1 expected-information ranker (UH3 + FWER).

DISPLAY-ONLY ordering of enumerated self-improvement candidates by expected
information per unit compute. This module NEVER auto-ships, NEVER flips a flag, and
NEVER creates the PIPELINE_ENABLED sentinel. It only decides which candidate the
EXISTING 5-gate ratchet would be asked to gate NEXT; the honest gate still decides
SHIP / REJECT. Reordering carries no authority to promote a candidate.

What it owns (per A1 Stage-2 + SKEPTIC_REVIEW):
  * rank(candidates, ledger) -> a deterministic ordered list (stable tie-break).
  * a planted-null control lane: a candidate flagged is_planted_null belongs to a
    real family but is KNOWN to be null (shuffled-label / random covariate). It is
    interleaved so the loop always re-tests a known null alongside real candidates.
  * a per-family FREEZE: if the ledger records that a planted null for a family ever
    'shipped', that whole family is FROZEN (a flexibility_alarm) -- its candidates
    sink to the bottom and are flagged, so a human reviews before any more gating.

UH3 (SKEPTIC_REVIEW): naming a most-probable SHIP up front ('leverage') must NOT
buy that family a ranking advantage. The ranker gives NO family a built-in priority
bonus by name, and -- crucially -- a named-favorite family's REAL candidate MUST NOT
be ranked above that family's OWN planted null. The null is the noise floor; a real
candidate that cannot out-score its own family's null on expected information has no
business being gated first. We enforce this by clamping a real candidate's score to
strictly below its family's planted-null score whenever that would otherwise invert.

Expected-information score (higher = gate sooner), all from supplied inputs only:
  * prior_pass_rate(family): Beta-posterior mean ship-rate from the ledger; a family
    that historically REJECTS sinks (Thompson-style, deterministic mean -- no RNG).
  * novelty: a never-tried family scores an exploration bonus, BOUNDED so the loop
    cannot thrash forever on novel-but-hopeless rows.
  * data_readiness: a candidate with >=2 rich corpora outranks a thin single-corpus
    one (which can only ever be REPLICATION_PENDING, never a real win).
  * cheap_screen: an optional pre-screen correlation score as a TIE-BREAK ONLY,
    never as a decider (mirrors discovery._screen_score being a tiebreak).

Candidate inputs are DUCK-TYPED (dataclass or dict) so this module does not depend
on the not-yet-built candidate_enum / candidate_families. Required fields:
  name (str), family (str). Optional: is_planted_null (bool), n_corpora (int),
  screen_score (float), novel (bool override).

INVARIANTS: never edits MEMORY.md / data/registry/, never flips a flag, never creates
the sentinel; calibration NOT edge (no $/pnl/roi/edge field emitted anywhere);
display-only. Pure: never raises on malformed candidates (a bad row sinks to the
bottom rather than crashing the loop). Stdlib only; ASCII; <=300 LOC.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Scoring weights. Tunable but FIXED here so ordering is fully deterministic.
# data_readiness dominates (a thin corpus can only ever be REPLICATION_PENDING),
# then the historical pass-rate, then a bounded novelty bonus. The cheap screen is
# deliberately weightless in the primary score -- it enters ONLY as a tie-break.
# ---------------------------------------------------------------------------
_W_READINESS = 1.0
_W_PASS_RATE = 0.6
_W_NOVELTY = 0.25  # bounded exploration; small enough it cannot dominate evidence.

# Beta(prior_a, prior_b) ship-rate prior per family: a weak optimism prior so a
# never-shipped-but-also-never-tried family is not pinned at 0. With no history the
# posterior mean is prior_a/(prior_a+prior_b); ships push it up, rejects pull it down.
_PRIOR_A = 1.0
_PRIOR_B = 4.0  # skeptical: most candidates REJECT (an honest REJECT is success).

# UH3 clamp: a real candidate may score AT MOST its family's planted-null score (the
# null is the noise floor it must not exceed by name advantage). Clamping to EQUAL --
# not below -- lets the real-before-null tie-break then order the real candidate first
# at that shared score, satisfying BOTH "no name advantage over the null" (UH3) and
# "a null never outranks a real, distinct candidate" simultaneously.


def _get(cand: Any, key: str, default: Any = None) -> Any:
    """Duck-typed field read: works for dicts and dataclass-like objects. Never raises."""
    try:
        if isinstance(cand, Mapping):
            return cand.get(key, default)
        return getattr(cand, key, default)
    except Exception:  # noqa: BLE001 -- purity: a malformed row never crashes ranking.
        return default


def _family_of(cand: Any) -> str:
    fam = _get(cand, "family", None)
    return str(fam) if fam is not None else "__unknown__"


def _is_planted_null(cand: Any) -> bool:
    return bool(_get(cand, "is_planted_null", False))


def prior_pass_rate(family: str, ledger: Optional[Mapping[str, Any]]) -> float:
    """Beta-posterior mean ship-rate for a family from the ledger (deterministic).

    The ledger maps family -> {"ships": int, "rejects": int} (other keys ignored).
    Returns (a+ships)/(a+b+ships+rejects). With no history this is the weak prior
    mean a/(a+b); it is NEVER a name-based bonus -- every family shares one prior.
    """
    ships = rejects = 0
    if ledger:
        row = ledger.get(family)
        if isinstance(row, Mapping):
            try:
                ships = max(0, int(row.get("ships", 0)))
                rejects = max(0, int(row.get("rejects", 0)))
            except (TypeError, ValueError):
                ships = rejects = 0
    a = _PRIOR_A + ships
    b = _PRIOR_B + rejects
    return a / (a + b)


def _novelty(family: str, cand: Any, ledger: Optional[Mapping[str, Any]]) -> float:
    """1.0 for a never-tried family (exploration), else 0.0. BOUNDED by _W_NOVELTY.

    A row may force-tag itself novel via a `novel` field; otherwise novelty is read
    from the ledger (a family with any recorded attempt is no longer novel).
    """
    override = _get(cand, "novel", None)
    if override is not None:
        return 1.0 if bool(override) else 0.0
    if not ledger:
        return 1.0
    row = ledger.get(family)
    if not isinstance(row, Mapping):
        return 1.0
    tried = 0
    try:
        tried = int(row.get("ships", 0)) + int(row.get("rejects", 0))
    except (TypeError, ValueError):
        tried = 0
    return 0.0 if tried > 0 else 1.0


def _data_readiness(cand: Any) -> float:
    """1.0 iff the candidate has >=2 corpora (can replicate); 0.0 otherwise.

    A single thin corpus can only ever reach REPLICATION_PENDING, never a real
    >=2-corpora win, so it is deprioritized -- not by name, by data availability.
    """
    try:
        n = int(_get(cand, "n_corpora", 0))
    except (TypeError, ValueError):
        n = 0
    return 1.0 if n >= 2 else 0.0


def _screen(cand: Any) -> float:
    """Optional cheap pre-screen correlation, used ONLY as a tie-break. Never decides."""
    try:
        s = float(_get(cand, "screen_score", 0.0))
    except (TypeError, ValueError):
        return 0.0
    return s if s == s else 0.0  # NaN-safe


def frozen_families(ledger: Optional[Mapping[str, Any]]) -> set:
    """Families whose planted null is recorded as having 'shipped' -> FROZEN.

    A planted null is KNOWN to be null; if it ever ships, the family's added
    flexibility has manufactured a false win (loop-level FWER failure). The whole
    family freezes (a flexibility_alarm) until a human reviews. Detected from a
    ledger row's "null_shipped" truthy flag (or null_ships > 0).
    """
    out: set = set()
    if not ledger:
        return out
    for fam, row in ledger.items():
        if not isinstance(row, Mapping):
            continue
        try:
            if bool(row.get("null_shipped", False)) or int(row.get("null_ships", 0)) > 0:
                out.add(str(fam))
        except (TypeError, ValueError):
            if row.get("null_shipped"):
                out.add(str(fam))
    return out


def _base_score(cand: Any, ledger: Optional[Mapping[str, Any]]) -> float:
    """Expected-information score (higher = gate sooner). No name-based term."""
    fam = _family_of(cand)
    readiness = _data_readiness(cand)
    pass_rate = prior_pass_rate(fam, ledger)
    novelty = _novelty(fam, cand, ledger)
    return (_W_READINESS * readiness
            + _W_PASS_RATE * pass_rate
            + _W_NOVELTY * novelty)


def _ranked_records(candidates: Sequence[Any],
                    ledger: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Compute per-candidate score records with UH3 clamp + family-freeze applied."""
    frozen = frozen_families(ledger)

    # First pass: raw expected-information score per candidate.
    recs: List[Dict[str, Any]] = []
    for idx, cand in enumerate(candidates):
        fam = _family_of(cand)
        recs.append({
            "cand": cand,
            "idx": idx,                       # original order: stable, deterministic.
            "name": str(_get(cand, "name", f"cand_{idx}")),
            "family": fam,
            "is_null": _is_planted_null(cand),
            "score": _base_score(cand, ledger),
            "screen": _screen(cand),
            "frozen": fam in frozen,
            "flexibility_alarm": fam in frozen,
        })

    # UH3: within each family, NO real candidate may outrank that family's planted
    # null. The null is the noise floor; clamp any real candidate whose score is
    # >= its family's null score to strictly below the null. This removes any
    # built-in advantage a named-favorite family ('leverage') would otherwise carry.
    null_score: Dict[str, float] = {}
    for r in recs:
        if r["is_null"]:
            cur = null_score.get(r["family"])
            null_score[r["family"]] = r["score"] if cur is None else max(cur, r["score"])
    for r in recs:
        if not r["is_null"] and r["family"] in null_score:
            ceil = null_score[r["family"]]
            if r["score"] > ceil:
                r["score"] = ceil
                r["uh3_clamped"] = True

    # Frozen families sink unconditionally (below every live candidate).
    return recs


def rank(candidates: Sequence[Any],
         ledger: Optional[Mapping[str, Any]] = None) -> List[Any]:
    """Return the candidates DISPLAY-ORDERED by expected information (deterministic).

    Ordering key (all descending unless noted), each fully deterministic:
      1. NOT frozen before frozen (a flexibility-alarm family sinks to the bottom).
      2. Higher expected-information score first.
      3. Planted nulls AFTER real candidates at an equal score (so a real, distinct
         candidate is never out-ranked by a null purely by family name) -- combined
         with the UH3 clamp this guarantees a family's null never sits above that
         family's real candidate by name advantage.
      4. Higher cheap-screen score (TIE-BREAK ONLY -- never a decider).
      5. Name, then original index: a total, stable, reproducible order.

    DISPLAY-ONLY: this never ships, flips a flag, or writes a ledger. Never raises.
    """
    try:
        recs = _ranked_records(candidates, ledger)
    except Exception:  # noqa: BLE001 -- purity: fall back to input order, never crash.
        return list(candidates)

    def sort_key(r: Dict[str, Any]) -> Tuple:
        return (
            1 if r["frozen"] else 0,            # frozen sinks (ascending: 0 before 1)
            -round(r["score"], 12),             # higher score first
            1 if r["is_null"] else 0,           # real before null at equal score
            -round(r["screen"], 12),            # tie-break: higher screen first
            r["name"],                          # stable
            r["idx"],                           # original order
        )

    return [r["cand"] for r in sorted(recs, key=sort_key)]


def rank_with_reasons(candidates: Sequence[Any],
                      ledger: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    """Like rank() but returns the scored records (display rows) instead of bare candidates.

    Each row carries name/family/score/is_null/frozen/flexibility_alarm (+uh3_clamped
    when applicable) so a display surface can show WHY the order is what it is. Pure;
    never emits a $/pnl/roi/edge field; never raises.
    """
    try:
        recs = _ranked_records(candidates, ledger)
    except Exception:  # noqa: BLE001
        return [{"cand": c, "name": str(_get(c, "name", "?")), "error": True}
                for c in candidates]

    def sort_key(r: Dict[str, Any]) -> Tuple:
        return (
            1 if r["frozen"] else 0,
            -round(r["score"], 12),
            1 if r["is_null"] else 0,
            -round(r["screen"], 12),
            r["name"],
            r["idx"],
        )

    ordered = sorted(recs, key=sort_key)
    # Strip the live candidate object out of the display row (keep it referencable).
    return [dict(r) for r in ordered]


__all__ = [
    "rank",
    "rank_with_reasons",
    "prior_pass_rate",
    "frozen_families",
]
