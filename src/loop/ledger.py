"""The experiment LEDGER -- append-only JSONL record of every tested item + FDR.

One line per tested signal/atlas with its verdict, the gate sub-criteria, and the
supersession chain. Maintains Benjamini-Hochberg FDR bookkeeping across ALL tested
items (the multiple-comparisons guard) so the orchestrator can ask "does this signal
survive FDR given everything we've ever tested?".

Ledger JSON schema (one object per line) -- THE CONTRACT (see DESIGN.md §3):
  {
    "id": str,                  # f"{kind}:{name}:{date}" unique
    "kind": "signal"|"atlas",
    "name": str,                # signal slug or atlas section key
    "target": str|null,         # stat/total/winprob/sigma  (signals)
    "entity": str|null,         # "player"|"team"           (atlas)
    "verdict": "SHIP"|"VARIANCE_ONLY"|"REJECT"|"DEFER",
    "reason": str,
    "wf_folds": [float, ...],   # per-fold delta_mae
    "wf_all_improve": bool,
    "null_delta": float|null,
    "ablation_delta": float|null,
    "calibration_ok": bool|null,
    "clv": float|null,
    "p_value": float|null,
    "fdr_pass": bool|null,
    "date": "YYYY-MM-DD",
    "supersedes": str|null,     # id of the item this replaces
    "metrics": {..}             # any extra diagnostics
  }
"""
from __future__ import annotations

import datetime as _dt
import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .atlas import AtlasArtifact
from .signal import GateResult, Verdict

ROOT = Path(__file__).resolve().parents[2]
_LEDGER_PATH = ROOT / ".planning" / "loop" / "ledger.jsonl"

_lock = threading.RLock()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _today() -> str:
    return _dt.date.today().isoformat()


def _make_id(kind: str, name: str, date: str) -> str:
    """Build the unique ledger entry id per the schema: ``f"{kind}:{name}:{date}"``."""
    return f"{kind}:{name}:{date}"


def _resolve_path(path: Optional[Path]) -> Path:
    p = path if path is not None else _LEDGER_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _append(entry: Dict[str, Any], path: Path) -> None:
    """Append one JSON entry to the JSONL ledger (thread-safe)."""
    with _lock, path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")


def _rewrite(entries: List[Dict[str, Any]], path: Path) -> None:
    """Overwrite the ledger with an updated list (used by apply_fdr to patch flags)."""
    with _lock, path.open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, default=str) + "\n")


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def record_signal(
    result: GateResult,
    *,
    target: str,
    supersedes: Optional[str] = None,
    path: Optional[Path] = None,
) -> str:
    """Append a signal gate result to the ledger; return the assigned id.

    Deduplication: if a non-DEFER entry for this (kind=signal, name) already
    exists on the same date, the call is a no-op and returns the existing id.
    DEFER entries are always recorded (the hypothesis may be re-queued multiple
    times while waiting for data coverage).

    Args:
        result:     the :class:`GateResult` from ``gate.evaluate``.
        target:     stat/model surface the signal feeds (one of ``TARGETS``).
        supersedes: id of the ledger entry this result replaces (champion swap).
        path:       override ledger file path (for tests).

    Returns:
        The assigned ``"signal:<name>:<date>"`` id.
    """
    p = _resolve_path(path)
    date = _today()
    eid = _make_id("signal", result.signal_name, date)

    # dedup: skip if non-DEFER result already present for this (name, date)
    if result.verdict != Verdict.DEFER:
        existing = load_all(p)
        for e in existing:
            if (e.get("kind") == "signal"
                    and e.get("name") == result.signal_name
                    and e.get("date") == date
                    and e.get("verdict") != Verdict.DEFER.value):
                return e["id"]

    entry: Dict[str, Any] = {
        "id": eid,
        "kind": "signal",
        "name": result.signal_name,
        "target": target,
        "entity": None,
        "verdict": result.verdict.value if isinstance(result.verdict, Verdict) else str(result.verdict),
        "reason": result.reason,
        "wf_folds": list(result.wf_folds),
        "wf_all_improve": result.wf_all_improve,
        "null_delta": result.null_delta,
        "ablation_delta": result.ablation_delta,
        "calibration_ok": result.calibration_ok,
        "clv": result.clv,
        "p_value": result.p_value,
        "fdr_pass": result.fdr_pass,
        "date": date,
        "supersedes": supersedes,
        "metrics": dict(result.metrics),
    }
    _append(entry, p)
    return eid


def record_atlas(
    artifact: AtlasArtifact,
    *,
    verdict: str,
    reason: str = "",
    supersedes: Optional[str] = None,
    path: Optional[Path] = None,
) -> str:
    """Append an atlas-section persistence record to the ledger; return the id.

    Atlas entries reuse the same schema; signal-only fields are null.

    Args:
        artifact:   the :class:`AtlasArtifact` that was built + validated.
        verdict:    string verdict (SHIP | VARIANCE_ONLY | REJECT | DEFER).
        reason:     human-readable justification.
        supersedes: id of the ledger entry this replaces.
        path:       override ledger file path (for tests).

    Returns:
        The assigned ``"atlas:<section_key>:<date>"`` id.
    """
    p = _resolve_path(path)
    date = artifact.as_of or _today()
    eid = _make_id("atlas", artifact.section, date)

    entry: Dict[str, Any] = {
        "id": eid,
        "kind": "atlas",
        "name": artifact.section,
        "target": None,
        "entity": artifact.entity,
        "verdict": verdict,
        "reason": reason,
        "wf_folds": [],
        "wf_all_improve": False,
        "null_delta": None,
        "ablation_delta": None,
        "calibration_ok": None,
        "clv": None,
        "p_value": None,
        "fdr_pass": None,
        "date": date,
        "supersedes": supersedes,
        "metrics": {},
    }
    _append(entry, p)
    return eid


def load_all(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load every ledger entry (for FDR, dedup, supersession, reporting).

    Returns an empty list if the ledger file does not yet exist.
    """
    p = _resolve_path(path)
    if not p.exists():
        return []
    entries: List[Dict[str, Any]] = []
    with _lock, p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def already_tested(
    name: str,
    kind: str = "signal",
    path: Optional[Path] = None,
) -> bool:
    """True iff this signal/atlas has a non-DEFER verdict already (dedup the queue).

    DEFER entries are intentionally excluded: a DEFER result means the hypothesis
    could not be evaluated and should remain in the queue for re-testing.

    Args:
        name: signal slug or atlas section key.
        kind: "signal" | "atlas".
        path: override ledger path (for tests).

    Returns:
        True if there is at least one SHIP, VARIANCE_ONLY, or REJECT entry for
        this (kind, name) pair — meaning the hypothesis has been resolved.
    """
    entries = load_all(path)
    for e in entries:
        if (e.get("kind") == kind
                and e.get("name") == name
                and e.get("verdict") not in (Verdict.DEFER.value, "DEFER")):
            return True
    return False


def apply_fdr(
    q: float = 0.10,
    path: Optional[Path] = None,
) -> Dict[str, bool]:
    """Recompute Benjamini-Hochberg FDR across all entries with a p_value.

    Implements the standard BH procedure (1995):
      1. Sort all p-values ascending.
      2. Entry i (1-indexed) passes iff p_i <= (i/m) * q,
         where m is the total number of hypotheses with a p_value.
      3. Apply the standard BH step-up: all hypotheses with rank <= the
         largest passing rank are declared discoveries.

    Updates ``fdr_pass`` in-place on every entry and rewrites the ledger.

    Args:
        q:    desired FDR level (default 0.10 per DESIGN.md).
        path: override ledger path (for tests).

    Returns:
        ``{id: fdr_pass}`` for every entry that has a ``p_value``.
    """
    p = _resolve_path(path)
    entries = load_all(p)
    if not entries:
        return {}

    # collect entries that have a p_value
    testable = [
        (i, e) for i, e in enumerate(entries)
        if e.get("p_value") is not None
    ]
    result: Dict[str, bool] = {}

    if not testable:
        return result

    m = len(testable)
    # sort by ascending p_value; keep original index so we can patch entries[]
    sorted_testable = sorted(testable, key=lambda x: float(x[1]["p_value"]))

    # BH step-up: find the largest rank k where p_(k) <= (k/m)*q
    # then all ranks 1..k are discoveries
    max_passing_rank = 0
    for rank_0idx, (_, e) in enumerate(sorted_testable):
        rank = rank_0idx + 1          # 1-indexed
        threshold = (rank / m) * q
        if float(e["p_value"]) <= threshold:
            max_passing_rank = rank

    # assign fdr_pass
    for rank_0idx, (orig_idx, e) in enumerate(sorted_testable):
        rank = rank_0idx + 1
        passes = rank <= max_passing_rank
        result[e["id"]] = passes
        entries[orig_idx]["fdr_pass"] = passes

    _rewrite(entries, p)
    return result


def supersession_chain(
    name: str,
    kind: str = "signal",
    path: Optional[Path] = None,
) -> List[str]:
    """Return the ordered list of ledger ids forming the supersession chain.

    Follows ``supersedes`` pointers from the most-recent entry back to the
    original, returning ids in chronological order (oldest → newest).

    Args:
        name: signal slug or atlas section key.
        kind: "signal" | "atlas".
        path: override ledger path (for tests).

    Returns:
        List of ids in chronological order.  A single-entry chain returns a
        one-element list.  If the name has never been tested, returns ``[]``.
    """
    entries = load_all(path)
    by_id = {e["id"]: e for e in entries}

    # find all entries for this (kind, name)
    candidates = [e for e in entries
                  if e.get("kind") == kind and e.get("name") == name]
    if not candidates:
        return []

    # find the "tip" — the entry that is not superseded by any other
    superseded_ids = {e["supersedes"] for e in candidates if e.get("supersedes")}
    tips = [e for e in candidates if e["id"] not in superseded_ids]

    # walk back from the tip following supersedes links
    chain: List[str] = []
    current_id = tips[-1]["id"] if tips else candidates[-1]["id"]
    seen: set = set()
    while current_id and current_id not in seen:
        seen.add(current_id)
        entry = by_id.get(current_id)
        if entry is None:
            break
        chain.append(current_id)
        current_id = entry.get("supersedes")  # type: ignore[assignment]

    chain.reverse()   # chronological: oldest first
    return chain
