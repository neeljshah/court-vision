"""improve.brain_observer -- LLM-free ship/reject history observer (read-only).

observe(history) reads the accumulated ratchet ship/reject history (from the
improve_ledger.jsonl + proof artifacts on disk) and produces a structured,
deterministic 'what changed and what to try next' NOTE as a PROPOSAL artifact.

summarize(history) distills that note into a compact dict for callers that need a
machine-readable summary without writing a file.

WHAT THIS IS NOT:
- It does NOT rebuild the brain vault, import/execute any gated module, or mutate
  any file outside data/frontend/improve/.
- It does NOT call an LLM; all logic is pure deterministic Python.
- Proposals are OBSERVATIONS only; a human or the ratchet loop applies them.

WHAT IT READS (strictly read-only):
- The improve_ledger.jsonl entries passed in as `history` (caller supplies the
  already-loaded list; no direct file I/O inside observe/summarize).
- Optionally the scoreboard grade_summary.json via _try_load_scoreboard() if it
  exists; graceful-None if absent/corrupt.
- Optionally the proof-artifact dirs listed in _PROOF_DIRS if they exist;
  file-read only, never writes.

PROPOSAL ARTIFACT SHAPE (written by observe):
  {
    "schema":          "brain_observation_v1",
    "ts":              "<ISO-8601 UTC>",
    "n_verdicts":      <int>,               -- total entries in history
    "sport_verdicts":  {sport: {SHIP:n, REJECT:n, HOLD:n, ...}},
    "recent_ships":    [<last 3 SHIP entries (metrics summary)>],
    "recent_rejects":  [<last 3 REJECT entries (reason snippet)>],
    "scoreboard":      {<grade_summary fields>|null},
    "proof_artifacts": [<list of proof-dir artifact counts>],
    "patterns":        [<str observations>],   -- deterministic, never LLM
    "next_to_try":     [<str suggestions>],    -- based on observed patterns only
    "note":            "<calibration disclaimer>",
    "apply_to_memory": false
  }

GUARANTEES:
- observe() and summarize() never raise; missing/corrupt inputs degrade to empty.
- Pure: deterministic on the same inputs (no randomness, no LLM, no network).
- Read-only: never writes except when observe() is called with proposals_dir.
- ASCII output only; <=300 LOC; no external deps (stdlib + pathlib only).
"""
from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO = Path(__file__).resolve().parents[1]
_DEFAULT_PROPOSALS_DIR = _REPO / "data" / "frontend" / "improve" / "proposals"
_SCOREBOARD_PATH = _REPO / "data" / "frontend" / "grade_summary.json"

# Read-only proof artifact directories (platform proof harnesses).
_PROOF_DIRS: List[Path] = [
    _REPO / "scripts" / "platformkit" / "proof_nba",
    _REPO / "scripts" / "platformkit" / "proof_mlb",
    _REPO / "scripts" / "platformkit" / "proof_soccer",
    _REPO / "scripts" / "platformkit" / "proof_tennis",
]

_CALIBRATION_NOTE = (
    "calibration != edge: better-calibrated probabilities do NOT imply "
    "beating the market close or a positive expected value"
)
_VERDICT_TYPES = ("SHIP", "REJECT", "HOLD", "INSUFFICIENT_DATA")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _try_load_scoreboard() -> Optional[Dict[str, Any]]:
    """Read grade_summary.json; return None on any failure (read-only)."""
    try:
        if not _SCOREBOARD_PATH.exists():
            return None
        raw = _SCOREBOARD_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        # Pluck only safe scalar fields to keep the proposal small.
        return {k: data.get(k) for k in (
            "as_of", "n_settled", "mean_clv_pct", "pct_beat_close",
            "flat_unit_wins", "flat_unit_losses", "honest_note",
        )}
    except Exception:  # noqa: BLE001
        return None


def _count_proof_artifacts() -> List[Dict[str, Any]]:
    """Count .json + .parquet proof artifacts per proof dir (read-only)."""
    out: List[Dict[str, Any]] = []
    for d in _PROOF_DIRS:
        try:
            if not d.exists():
                continue
            jsons = len(list(d.glob("*.json")))
            parquets = len(list(d.glob("*.parquet")))
            if jsons + parquets > 0:
                out.append({
                    "dir": d.name,
                    "json_artifacts": jsons,
                    "parquet_artifacts": parquets,
                })
        except Exception:  # noqa: BLE001
            continue
    return out


def _sport_verdicts(history: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """Count verdicts per sport from the history list."""
    out: Dict[str, Dict[str, int]] = {}
    for entry in history:
        sport = str(entry.get("sport") or "unknown").lower()
        v = str(entry.get("verdict") or "UNKNOWN").strip().upper()
        out.setdefault(sport, {})
        out[sport][v] = out[sport].get(v, 0) + 1
    return out


def _recent_ships(history: List[Dict[str, Any]], n: int = 3) -> List[Dict[str, Any]]:
    ships = [e for e in history if str(e.get("verdict", "")).upper() == "SHIP"]
    out = []
    for e in ships[-n:]:
        out.append({
            "ts": e.get("ts"),
            "sport": e.get("sport"),
            "delta_brier": e.get("delta_brier"),
            "recal_brier": e.get("recal_brier"),
            "baseline_brier": e.get("baseline_brier"),
        })
    return out


def _recent_rejects(history: List[Dict[str, Any]], n: int = 3) -> List[Dict[str, Any]]:
    rejects = [e for e in history if str(e.get("verdict", "")).upper() == "REJECT"]
    out = []
    for e in rejects[-n:]:
        reason = str(e.get("reason") or "")[:120]
        out.append({
            "ts": e.get("ts"),
            "sport": e.get("sport"),
            "reason": reason,
            "delta_brier": e.get("delta_brier"),
        })
    return out


def _patterns(history: List[Dict[str, Any]],
              sv: Dict[str, Dict[str, int]]) -> List[str]:
    """Derive deterministic pattern strings from the verdict history."""
    pats: List[str] = []
    if not history:
        pats.append("No ratchet cycles recorded yet; awaiting real settled games.")
        return pats

    total = len(history)
    ships = sum(1 for e in history if str(e.get("verdict", "")).upper() == "SHIP")
    rejects = sum(1 for e in history if str(e.get("verdict", "")).upper() == "REJECT")
    insuff = sum(
        1 for e in history
        if str(e.get("verdict", "")).upper() == "INSUFFICIENT_DATA"
    )
    pats.append(
        "Total ratchet cycles: %d | SHIPs: %d | REJECTs: %d | INSUFFICIENT_DATA: %d"
        % (total, ships, rejects, insuff)
    )

    # Per-sport patterns
    for sport, counts in sorted(sv.items()):
        s = counts.get("SHIP", 0)
        r = counts.get("REJECT", 0)
        h = counts.get("HOLD", 0)
        pats.append(
            "Sport=%s: SHIP=%d REJECT=%d HOLD=%d" % (sport, s, r, h)
        )

    # Brier delta distribution across all entries that have it
    deltas = [
        float(e["delta_brier"])
        for e in history
        if isinstance(e.get("delta_brier"), (int, float))
    ]
    if deltas:
        mean_d = sum(deltas) / len(deltas)
        pats.append(
            "Mean delta_brier across %d scored cycles: %+.5f "
            "(positive = improvement; negative = regression held)" % (len(deltas), mean_d)
        )

    # Consecutive-INSUFFICIENT_DATA detection
    last_non_insuff = None
    for e in reversed(history):
        if str(e.get("verdict", "")).upper() != "INSUFFICIENT_DATA":
            last_non_insuff = e
            break
    if last_non_insuff is None and insuff > 0:
        pats.append(
            "All %d cycles are INSUFFICIENT_DATA -- "
            "real settled games have not accumulated yet." % insuff
        )

    return pats


def _next_to_try(history: List[Dict[str, Any]],
                 sv: Dict[str, Dict[str, int]]) -> List[str]:
    """Generate deterministic 'what to try next' suggestions from patterns."""
    sugg: List[str] = []
    if not history:
        sugg.append(
            "Wait for real settled games to accumulate (>= 60 per sport) "
            "before expecting a non-INSUFFICIENT_DATA verdict."
        )
        return sugg

    insuff_sports = [
        sp for sp, counts in sv.items()
        if counts.get("INSUFFICIENT_DATA", 0) > 0
        and counts.get("SHIP", 0) == 0
        and counts.get("HOLD", 0) == 0
    ]
    if insuff_sports:
        sugg.append(
            "Sports still in cold-start (only INSUFFICIENT_DATA): %s. "
            "No action needed; ledger will accumulate automatically."
            % ", ".join(sorted(insuff_sports))
        )

    reject_sports = [
        sp for sp, counts in sv.items()
        if counts.get("REJECT", 0) > 0 and counts.get("SHIP", 0) == 0
    ]
    if reject_sports:
        sugg.append(
            "Sports with REJECTs and no SHIPs yet: %s. "
            "Review recent reject reasons in the ledger; "
            "check for a leak-guard fire or a genuine calibration regression."
            % ", ".join(sorted(reject_sports))
        )

    ship_sports = [
        sp for sp, counts in sv.items()
        if counts.get("SHIP", 0) > 0
    ]
    if ship_sports:
        sugg.append(
            "Sports with at least one SHIP: %s. "
            "Ensure pkl.n_features_in_ matches meta.json after each retrain "
            "(parity_check gate)."
            % ", ".join(sorted(ship_sports))
        )

    # If many HOLDs: model is well-calibrated; suggest freshness work instead.
    holds = sum(c.get("HOLD", 0) for c in sv.values())
    if holds >= 3:
        sugg.append(
            "%d HOLD verdicts observed -- model is well-calibrated on this corpus. "
            "Freshness (same-day features) is the next lever per north-star docs."
            % holds
        )

    if not sugg:
        sugg.append(
            "No clear pattern yet; continue accumulating real settled games per sport."
        )
    return sugg


def summarize(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Distill the ratchet history into a compact summary dict.

    Pure, deterministic, never raises.  Does not write any file.
    Useful for callers that need a machine-readable view without an artifact.

    Parameters
    ----------
    history:
        List of verdict dicts (e.g. loaded from improve_ledger.jsonl by the
        caller).  May be empty; degrades gracefully.
    """
    try:
        sv = _sport_verdicts(history)
        return {
            "n_verdicts": len(history),
            "sport_verdicts": sv,
            "recent_ships": _recent_ships(history),
            "recent_rejects": _recent_rejects(history),
            "patterns": _patterns(history, sv),
            "next_to_try": _next_to_try(history, sv),
            "note": _CALIBRATION_NOTE,
        }
    except Exception:  # noqa: BLE001 -- never raise
        return {
            "n_verdicts": 0,
            "sport_verdicts": {},
            "recent_ships": [],
            "recent_rejects": [],
            "patterns": ["summarize() internal error -- see reason"],
            "next_to_try": [],
            "note": _CALIBRATION_NOTE,
            "error": traceback.format_exc()[:300],
        }


def observe(
    history: List[Dict[str, Any]],
    proposals_dir: Optional[Path] = None,
) -> Path:
    """Read the ratchet history and write a structured observation PROPOSAL.

    Parameters
    ----------
    history:
        List of verdict dicts (caller loads from improve_ledger.jsonl).
    proposals_dir:
        Override output directory (default: data/frontend/improve/proposals/).

    Returns
    -------
    Path of the written observation file.  Never raises.
    """
    try:
        sv = _sport_verdicts(history)
        proposal = {
            "schema": "brain_observation_v1",
            "ts": _now_iso(),
            "n_verdicts": len(history),
            "sport_verdicts": sv,
            "recent_ships": _recent_ships(history),
            "recent_rejects": _recent_rejects(history),
            "scoreboard": _try_load_scoreboard(),
            "proof_artifacts": _count_proof_artifacts(),
            "patterns": _patterns(history, sv),
            "next_to_try": _next_to_try(history, sv),
            "note": _CALIBRATION_NOTE,
            "apply_to_memory": False,
        }
        out_dir = proposals_dir if proposals_dir is not None else _DEFAULT_PROPOSALS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        ts_safe = "".join(c if c.isalnum() else "_" for c in proposal["ts"])[:32]
        fname = "%s_brain_observation.json" % ts_safe
        out_path = out_dir / fname
        payload = json.dumps(proposal, indent=2, sort_keys=True, default=str)
        tmp = out_path.with_name(out_path.name + ".tmp.%d" % os.getpid())
        tmp.write_text(payload, encoding="ascii")
        os.replace(tmp, out_path)
        return out_path
    except Exception:  # noqa: BLE001 -- never raise
        try:
            error_proposal = {
                "schema": "brain_observation_v1",
                "ts": _now_iso(),
                "n_verdicts": 0,
                "sport_verdicts": {},
                "recent_ships": [],
                "recent_rejects": [],
                "scoreboard": None,
                "proof_artifacts": [],
                "patterns": ["observe() internal error; see note"],
                "next_to_try": [],
                "note": traceback.format_exc()[:300],
                "apply_to_memory": False,
            }
            out_dir = proposals_dir if proposals_dir is not None else _DEFAULT_PROPOSALS_DIR
            out_dir.mkdir(parents=True, exist_ok=True)
            ts_safe = "".join(c if c.isalnum() else "_" for c in _now_iso())[:32]
            out_path = out_dir / ("%s_brain_obs_error.json" % ts_safe)
            out_path.write_text(
                json.dumps(error_proposal, indent=2, default=str), encoding="ascii"
            )
            return out_path
        except Exception:  # noqa: BLE001
            return _DEFAULT_PROPOSALS_DIR / "observe_failed.json"


__all__ = ["observe", "summarize", "_DEFAULT_PROPOSALS_DIR"]
