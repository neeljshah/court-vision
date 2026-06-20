"""scripts.platformkit.progress.ci_regate -- nightly re-gate of newly-GROWN settled data.

Step (F, part 1) of the W4 CONTINUOUS-IMPROVEMENT cadence. This is the heart of
"improves unattended without crossing a gate": when a sport's settled corpus has
GROWN since its last recorded verdict (more games appended), the SAME signal is
re-judged on the WIDER data through the EXISTING gates, and the re-measured verdict
is recorded to data/frontend/funnel/. If nothing grew -> an honest NO_OP (no churn).

RAILS (binding -- this is the highest-risk wave):
  * MEASUREMENT-ONLY. select_regate_targets reads ledger + corpus mtimes only and
    emits work_queue Tasks whose kind is ALWAYS in ALLOWED_KINDS. record_regate
    appends a re-measured verdict ROW to the funnel; it NEVER flips a flag, NEVER
    creates the PIPELINE_ENABLED sentinel, NEVER writes data/registry/, NEVER edits
    MEMORY.md. A re-gate that now PASSES on wider data records a SHIP-PROPOSAL row,
    it does NOT ship.
  * STALE-NEVER-GREEN: a growth measurement we could not take degrades to NO_OP
    (honest "nothing grew"), never a fabricated PASS.
  * NO $ field anywhere; units/probability only; vs_close UNPROVEN.
stdlib-only; ASCII; <=300 LOC; build only under scripts/platformkit/.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

_REPO = pathlib.Path(__file__).resolve().parents[3]
_IMPROVE_LEDGER = _REPO / "data" / "frontend" / "improve_ledger.jsonl"
_CORPORA_DIR = _REPO / "data" / "cache" / "ingame"
_FUNNEL_DIR = _REPO / "data" / "frontend" / "funnel"

# Re-gate enqueues only these MEASUREMENT kinds (subset of work_queue.ALLOWED_KINDS).
REGATE_KINDS = ("regate_ingame", "recalibrate")

NO_OP = "NO_OP"          # nothing grew -> honest no-op, no churn
SELECTED = "SELECTED"    # >=1 sport grew -> a re-gate target was emitted

_SPORTS = ("nba", "mlb", "soccer", "tennis")


@dataclass
class RegateTask:
    """A measurement-only re-gate target (mirrors work_queue enqueue inputs)."""
    kind: str
    sport: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RegateResult:
    status: str = NO_OP
    targets: List[RegateTask] = field(default_factory=list)
    reason: str = "nothing grew since last verdict"
    note: str = ("calibration, not edge; re-measured on wider settled data; "
                 "no $ / flag / registry; vs_close UNPROVEN")


def _norm_sport(s: Optional[str]) -> Optional[str]:
    if not isinstance(s, str):
        return None
    t = s.strip().lower()
    if t in ("basketball_nba", "nba"):
        return "nba"
    if t in ("soccer_intl", "soccer"):
        return "soccer"
    if t in _SPORTS:
        return t
    return None


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


def _last_verdict_meta(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """sport -> {n_settled, ts} from the LAST recorded verdict (later rows win)."""
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        sp = _norm_sport(r.get("sport"))
        if sp is None:
            continue
        out[sp] = {
            "n_settled": int(r.get("n_settled", 0) or 0),
            "ts": str(r.get("ts", "")),
        }
    return out


def _corpus_game_count(sport: str, corpora_dir: pathlib.Path,
                       counts: Optional[Dict[str, int]]) -> Optional[int]:
    """Current settled-game count for a sport.

    Tests inject `counts` (a {sport: n} fixture) -- the honest, fast path. With no
    injection we fall back to a cheap row count via pandas if available; any failure
    returns None (-> treated as 'no measurable growth', never a fabricated number).
    """
    if counts is not None:
        v = counts.get(sport)
        return int(v) if isinstance(v, (int, float)) else None
    try:
        import pandas as pd  # noqa: PLC0415
        total = 0
        found = False
        for p in corpora_dir.glob("%s*settled*.parquet" % sport):
            try:
                total += int(len(pd.read_parquet(p, columns=[]).index))
                found = True
            except Exception:  # noqa: BLE001
                continue
        return total if found else None
    except Exception:  # noqa: BLE001 -- no pandas / read error -> unmeasurable
        return None


def select_regate_targets(
    now: Optional[float] = None,
    *,
    ledger_path: Optional[pathlib.Path] = None,
    corpora_dir: Optional[pathlib.Path] = None,
    current_counts: Optional[Dict[str, int]] = None,
    sports: Sequence[str] = _SPORTS,
) -> RegateResult:
    """Select sports whose settled corpus GREW since the last verdict. NEVER raises.

    For each sport, compare the current settled-game count against the n_settled
    recorded at the last verdict. A POSITIVE delta emits a `regate_ingame` Task on
    the wider data. No growth (or unmeasurable) -> not selected. Nothing selected ->
    an honest NO_OP RegateResult (no churn).
    """
    lp = ledger_path or _IMPROVE_LEDGER
    cd = corpora_dir or _CORPORA_DIR
    last = _last_verdict_meta(_read_jsonl(lp))

    targets: List[RegateTask] = []
    for sp in sports:
        cur = _corpus_game_count(sp, cd, current_counts)
        if cur is None:
            continue  # unmeasurable -> never fabricate growth
        prev = int(last.get(sp, {}).get("n_settled", 0) or 0)
        delta = cur - prev
        if delta > 0:
            kind = REGATE_KINDS[0]  # 'regate_ingame'
            targets.append(RegateTask(
                kind=kind, sport=sp,
                args={"reason": "settled_corpus_grew", "prev_n": prev,
                      "cur_n": cur, "delta_n": delta, "wider_data": True}))

    if not targets:
        return RegateResult(status=NO_OP, targets=[],
                            reason="nothing grew since last verdict")
    return RegateResult(
        status=SELECTED, targets=targets,
        reason="%d sport(s) grew -> re-gate on wider data" % len(targets))


def record_regate(sport: str, verdict: str, readout: Dict[str, Any],
                  *, funnel_dir: Optional[pathlib.Path] = None,
                  now: Optional[float] = None) -> pathlib.Path:
    """Append a re-measured re-gate verdict ROW to data/frontend/funnel/. NEVER ships.

    A PASS on wider data is recorded as 'SHIP-PROPOSAL' (proposal_only=True), never a
    flag flip. The row carries NO $ field and the standing honest note.
    """
    fd = funnel_dir or _FUNNEL_DIR
    fd.mkdir(parents=True, exist_ok=True)
    ts = float(now) if now is not None else _dt.datetime.utcnow().timestamp()
    v = str(verdict).strip().upper()
    recorded = "SHIP-PROPOSAL" if v in ("SHIP", "PASS", "PROMOTE") else v
    # Defensive: strip any forbidden money/edge key from the readout.
    safe = {k: val for k, val in dict(readout or {}).items()
            if not (set(str(k).lower().replace("-", "_").split("_"))
                    & {"pnl", "roi", "bankroll", "profit", "dollar", "usd", "stake"})}
    doc = {
        "sport": sport,
        "gate_verdict": recorded,
        "verdict": recorded,
        "lane": "ci_regate -- re-measured on wider settled data",
        "proposal_only": True,
        "edge_claimed": False,
        "ts": int(ts),
        "readout": safe,
        "note": ("calibration, not edge; a PASS is recorded as a PROPOSAL, never a "
                 "flag flip; no $ field; vs_close UNPROVEN"),
    }
    # Collision-safe stem: an integer-second filename can OVERWRITE a same-second
    # sibling (two re-gate rows recorded within one wall-clock second). Use the FULL
    # ts with microsecond precision (derived from the injected ts only -- no
    # Date.now / random) so distinct ticks never alias to one file. The stored
    # "ts": int(ts) readout field above is unchanged (behavior-preserving).
    stem = "%s_ci_regate_%d_%06d.json" % (
        str(sport).lower(), int(ts), int(round((ts - int(ts)) * 1_000_000)) % 1_000_000)
    out = fd / stem
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="ascii")
    return out


__all__ = ["select_regate_targets", "record_regate", "RegateTask",
           "RegateResult", "REGATE_KINDS", "NO_OP", "SELECTED"]
