"""scripts.platformkit.improve.candidate_enum -- Stage-1 candidate ENUMERATOR (A4).

The deterministic, family-deduped proposal stream the recalibrator/runner draws from.
It walks candidate_families.all_specs, drops any candidate_id already in the
tried-families memory (data/cache/improve/tried_families.jsonl), validates every spec,
and yields the survivors in a STABLE order so coverage widens monotonically (a tried
family is never re-rolled).

THE MF4 INVARIANT (the choke point this module must never bypass):
  The enumerator may only PROPOSE specs. It may NEVER construct a gate-consumable
  candidate dict. The ONLY way a spec becomes a built candidate is
  recalibrator.build_candidate -- the choke point that enforces the PIPELINE_ENABLED
  kill-switch (MF1) + settle_audit (MF3) + the degenerate-base guard (MF2). The
  build_candidates() helper here routes EVERY enumerated spec through
  build_candidate(...) and returns only what that choke point packages. With the
  sentinel ABSENT, build_candidate returns None for every spec, so enumeration stays
  byte-identical to today's NO_CANDIDATE -- the enumerator proposes, the choke decides.

Public surface:
  enumerate_specs(sport, ..., tried_ids=...) -> List[CandidateSpec]
      deterministic, dedup-filtered, validated SPEC stream (no build, no fit).
  build_candidates(sport, settled, ..., build_fn=...) -> List[dict]
      routes each enumerated spec through recalibrator.build_candidate ONLY; never
      constructs a candidate dict itself; returns the (possibly empty) built list.
  load_tried_ids(path) / append_tried(path, spec) -- the tried-families memory.

INVARIANTS: never edits MEMORY.md, never writes data/registry/ (tried memory lives
under data/cache/improve), never flips a flag, never creates the sentinel, never builds
a candidate except via recalibrator.build_candidate. Calibration NOT edge (no $/pnl/roi/
edge field). vs_close UNPROVEN. Stdlib only; ASCII; <=300 LOC.
"""
from __future__ import annotations

import json
import logging
import pathlib
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set

from scripts.platformkit.improve.candidate_families import (
    CandidateSpec, all_specs, validate_spec,
)

logger = logging.getLogger("candidate_enum")

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]  # .../nba-ai-system
# Tried-families memory: data/cache/improve (a CACHE, NEVER data/registry).
TRIED_PATH: pathlib.Path = (
    _REPO_ROOT / "data" / "cache" / "improve" / "tried_families.jsonl"
)


def load_tried_ids(path: Optional[pathlib.Path] = None) -> Set[str]:
    """Return the set of candidate_ids already tried (resolved), from the JSONL memory.

    A missing / unreadable file yields an empty set (cold start). Never raises: a
    malformed line is skipped, not fatal -- a corrupt memory must not wedge the loop.
    """
    p = path if path is not None else TRIED_PATH
    tried: Set[str] = set()
    try:
        if not p.exists():
            return tried
        with p.open("r", encoding="ascii", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except (ValueError, TypeError):
                    continue
                cid = row.get("candidate_id") if isinstance(row, dict) else None
                if isinstance(cid, str) and cid:
                    tried.add(cid)
    except Exception as exc:  # noqa: BLE001 -- a bad memory must never wedge the loop
        logger.debug("load_tried_ids(%s) unreadable -> empty: %s", p, exc)
    return tried


def append_tried(spec: CandidateSpec, path: Optional[pathlib.Path] = None) -> None:
    """Append a tried spec's id to the memory (append-only JSONL under data/cache).

    Writes a minimal provenance row (candidate_id + family/sport/target/signature) so a
    future enumeration dedups it. Never edits MEMORY.md / data/registry. Never raises.
    """
    p = path if path is not None else TRIED_PATH
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "candidate_id": spec.candidate_id,
            "family": spec.family, "sport": spec.sport,
            "target": spec.target, "signature": spec.signature,
            "note": spec.note,
        }
        with p.open("a", encoding="ascii") as fh:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")
    except Exception as exc:  # noqa: BLE001 -- memory write must never sink the loop
        logger.debug("append_tried(%s) failed: %s", p, exc)


def enumerate_specs(
    sport: str,
    target: str = "win_prob",
    *,
    tried_ids: Optional[Iterable[str]] = None,
    tried_path: Optional[pathlib.Path] = None,
) -> List[CandidateSpec]:
    """Deterministic, dedup-filtered, validated SPEC stream for `sport`.

    Walks candidate_families.all_specs in a STABLE order, validates every spec (a spec
    carrying a $-edge token or retracted number raises in validate_spec and is dropped),
    and excludes any candidate_id already tried so coverage widens monotonically.

    Produces SPECS ONLY -- it builds nothing, fits nothing, and constructs no
    gate-consumable candidate dict (that is recalibrator.build_candidate's job; MF4).
    """
    if tried_ids is not None:
        tried: Set[str] = {str(c) for c in tried_ids}
    else:
        tried = load_tried_ids(tried_path)

    out: List[CandidateSpec] = []
    seen_this_run: Set[str] = set()
    for spec in all_specs(sport, target):
        try:
            validate_spec(spec)  # honesty choke: drop a $/retracted spec, never enumerate
        except ValueError as exc:
            logger.debug("enumerate_specs: dropped invalid spec: %s", exc)
            continue
        cid = spec.candidate_id
        if cid in tried or cid in seen_this_run:
            continue  # already tried (or a within-run dup) -> never re-roll
        seen_this_run.add(cid)
        out.append(spec)
    return out


def build_candidates(
    sport: str,
    settled: Sequence[Dict[str, Any]],
    target: str = "win_prob",
    *,
    tried_ids: Optional[Iterable[str]] = None,
    tried_path: Optional[pathlib.Path] = None,
    build_fn: Optional[Callable[..., Optional[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """Route EVERY enumerated spec through recalibrator.build_candidate (the choke).

    THE MF4 GUARANTEE: this is the ONLY build path the enumerator exposes, and it
    constructs NO candidate dict itself -- it calls ``build_fn`` (default
    recalibrator.build_candidate) for each spec and collects ONLY what that choke point
    returns. The choke enforces PIPELINE_ENABLED (MF1) + settle_audit (MF3) +
    degenerate-base (MF2). With the sentinel absent, build_fn returns None for every
    spec, so this returns [] (byte-identical to NO_CANDIDATE). Never raises.

    The spec's identity (family/sport/target/signature/candidate_id) is passed to the
    choke as keyword provenance; the choke is free to ignore it. The enumerator never
    fabricates base_preds/cand_preds/y -- only the choke may.
    """
    if build_fn is None:
        # Bind the real MF4 choke point lazily so a missing module fails safe (no build).
        try:
            from scripts.platformkit.improve.recalibrator import build_candidate as _bc
        except Exception as exc:  # noqa: BLE001 -- no choke -> nothing builds
            logger.debug("build_candidates: recalibrator unavailable -> []: %s", exc)
            return []
        build_fn = _bc

    specs = enumerate_specs(sport, target, tried_ids=tried_ids, tried_path=tried_path)
    built: List[Dict[str, Any]] = []
    for spec in specs:
        try:
            cand = build_fn(
                spec.sport, settled,
                priority=None,
                candidate_id=spec.candidate_id,
                family=spec.family,
                target=spec.target,
                signature=spec.signature,
                spec=spec.to_dict(),
            )
        except Exception as exc:  # noqa: BLE001 -- a choke failure is NO_CANDIDATE
            logger.debug("build_candidates: choke raised for %s -> skip: %s",
                         spec.candidate_id, exc)
            continue
        if cand is not None:
            built.append(cand)
    return built


__all__ = [
    "enumerate_specs", "build_candidates",
    "load_tried_ids", "append_tried", "TRIED_PATH",
]
