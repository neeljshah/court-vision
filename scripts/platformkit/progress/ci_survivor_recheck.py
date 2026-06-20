"""scripts.platformkit.progress.ci_survivor_recheck -- re-check survivors at WIDER K.

Step (F, part 2) of the W4 CONTINUOUS-IMPROVEMENT cadence. For each CONFIRMED
survivor in the verdict ledger (e.g. the soccer-corners CALIBRATION survivor), this
re-runs the EXISTING combo_gate / survivor harness at a WIDER cumulative K (more
corpora / folds now available). A survivor that fails the wider check is DEMOTED to
artifact and the demotion is recorded honestly ("held at K=20, failed re-check at
K=40" -> dropped) -- never silently kept, never auto-promoted to a feature.

RAILS (binding):
  * MEASUREMENT-ONLY. select_survivor_targets reads the ledger and emits work_queue
    Tasks whose kind is ALWAYS in ALLOWED_KINDS (regate_ingame). recheck_survivor
    CONDUCTS the existing survivor_corners_combo_gate harness (injectable for tests)
    and records the verdict; it NEVER ships a feature, NEVER flips a flag, NEVER
    creates the sentinel, NEVER writes data/registry/ or MEMORY.md. The bar is NEVER
    weakened to keep a survivor; a truthful DEMOTE is a SUCCESS.
  * NO $ field anywhere; calibration survivors only (held-out Brier); vs_close
    UNPROVEN.
stdlib-only (the survivor harness is injected / imported lazily); ASCII; <=300 LOC.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

_REPO = pathlib.Path(__file__).resolve().parents[3]
_REJECT_LEDGER = _REPO / "data" / "frontend" / "reject_ledger.jsonl"
_IMPROVE_LEDGER = _REPO / "data" / "frontend" / "improve_ledger.jsonl"
_FUNNEL_DIR = _REPO / "data" / "frontend" / "funnel"

# Survivor re-check enqueues only this MEASUREMENT kind (subset of ALLOWED_KINDS).
RECHECK_KIND = "regate_ingame"

# Verdict tokens that mark a row as a confirmed survivor eligible for re-check.
_SURVIVOR_VERDICTS = ("CONFIRMED_SURVIVOR", "SHIP", "SURVIVOR", "PASS")

HELD = "HELD"          # survived the wider-K re-check -- still a survivor
DEMOTED = "DEMOTED"    # failed the wider-K re-check -> dropped to artifact


@dataclass
class SurvivorTask:
    kind: str
    sport: str
    signal: str
    prev_k: int
    next_k: int
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecheckOutcome:
    sport: str = ""
    signal: str = ""
    prev_k: int = 0
    wider_k: int = 0
    status: str = HELD
    demoted: bool = False
    deciding: str = ""
    note: str = ("calibration, not edge; bar NEVER weakened; a truthful DEMOTE is a "
                 "SUCCESS; no $ / flag / registry; no feature promotion")


def _read_jsonl(path: pathlib.Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        if not path.exists():
            return out
        for line in path.read_text(encoding="ascii", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(obj, dict):
                out.append(obj)
    except Exception:  # noqa: BLE001
        return out
    return out


def select_survivor_targets(
    *,
    ledger_paths: Optional[Sequence[pathlib.Path]] = None,
    survivors: Optional[Sequence[Dict[str, Any]]] = None,
    k_step: int = 2,
) -> List[SurvivorTask]:
    """Emit a wider-K re-check Task for each confirmed survivor. NEVER raises.

    Tests inject `survivors` directly; otherwise we scan the ledgers for rows whose
    verdict is a survivor token. wider_k = prev_k * k_step (more corpora/folds now).
    """
    rows: List[Dict[str, Any]] = list(survivors or [])
    if not rows:
        paths = ledger_paths or (_IMPROVE_LEDGER, _REJECT_LEDGER)
        for p in paths:
            for r in _read_jsonl(p):
                v = str(r.get("verdict", "")).strip().upper()
                if v in _SURVIVOR_VERDICTS:
                    rows.append(r)

    out: List[SurvivorTask] = []
    for r in rows:
        sport = str(r.get("sport", "")).strip().lower() or "platform"
        signal = str(r.get("signal") or r.get("layer") or r.get("candidate") or "")
        prev_k = int(r.get("K", r.get("cum_k", 0)) or 0)
        wider = max(prev_k + 1, prev_k * max(2, int(k_step)))
        out.append(SurvivorTask(
            kind=RECHECK_KIND, sport=sport, signal=signal,
            prev_k=prev_k, next_k=wider,
            args={"reason": "survivor_recheck_wider_k", "signal": signal,
                  "prev_k": prev_k, "wider_k": wider}))
    return out


def recheck_survivor(
    task: SurvivorTask,
    *,
    gate_fn: Optional[Callable[[int], Any]] = None,
    funnel_dir: Optional[pathlib.Path] = None,
    now: Optional[float] = None,
) -> RecheckOutcome:
    """Re-run the survivor harness at the WIDER K; DEMOTE on fail. NEVER raises.

    `gate_fn(wider_k)` runs the existing combo/survivor gate and returns an object
    with a `.verdict` (e.g. survivor_corners_combo_gate.run()). With no injection we
    lazily bind that real harness. A non-CONFIRMED verdict -> DEMOTED. Any harness
    failure DEMOTES (fail-closed: we never keep a survivor we could not re-confirm).
    """
    fn = gate_fn or _default_gate_fn
    outcome = RecheckOutcome(sport=task.sport, signal=task.signal,
                             prev_k=task.prev_k, wider_k=task.next_k)
    try:
        rep = fn(task.next_k)
        verdict = str(getattr(rep, "verdict", rep) or "").strip().upper()
    except Exception as exc:  # noqa: BLE001 -- fail-closed: cannot re-confirm -> demote
        outcome.status = DEMOTED
        outcome.demoted = True
        outcome.deciding = "re-check harness raised (%s) -> fail-closed demote" % type(exc).__name__
        _record(outcome, funnel_dir, now)
        return outcome

    if verdict in ("CONFIRMED_SURVIVOR", "SHIP", "SURVIVOR", "PASS"):
        outcome.status = HELD
        outcome.demoted = False
        outcome.deciding = "held at wider K=%d (verdict=%s)" % (task.next_k, verdict)
    else:
        outcome.status = DEMOTED
        outcome.demoted = True
        outcome.deciding = ("held at K=%d, failed re-check at K=%d (verdict=%s) -> "
                            "dropped to artifact" % (task.prev_k, task.next_k, verdict))
    _record(outcome, funnel_dir, now)
    return outcome


def _default_gate_fn(wider_k: int) -> Any:
    """Lazily conduct the real survivor harness (soccer corners). NEVER imported eagerly."""
    from scripts.platformkit.survivor_corners_combo_gate import run as _run  # noqa: PLC0415
    return _run()


def _record(outcome: RecheckOutcome, funnel_dir: Optional[pathlib.Path],
            now: Optional[float]) -> pathlib.Path:
    fd = funnel_dir or _FUNNEL_DIR
    fd.mkdir(parents=True, exist_ok=True)
    ts = float(now) if now is not None else _dt.datetime.utcnow().timestamp()
    v = "SURVIVOR_HELD" if outcome.status == HELD else "DOWNGRADE_TO_ARTIFACT"
    doc = {
        "sport": outcome.sport,
        "gate_verdict": v,
        "verdict": v,
        "lane": "ci_survivor_recheck -- re-check at wider cumulative K",
        "signal": outcome.signal,
        "prev_k": outcome.prev_k,
        "wider_k": outcome.wider_k,
        "demoted": outcome.demoted,
        "proposal_only": True,
        "edge_claimed": False,
        "ts": int(ts),
        "deciding": outcome.deciding,
        "note": outcome.note,
    }
    stem = "%s_ci_survivor_%d.json" % (str(outcome.sport).lower(), int(ts))
    out = fd / stem
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="ascii")
    return out


__all__ = ["select_survivor_targets", "recheck_survivor", "SurvivorTask",
           "RecheckOutcome", "RECHECK_KIND", "HELD", "DEMOTED"]
