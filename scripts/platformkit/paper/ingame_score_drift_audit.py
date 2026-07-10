"""scripts.platformkit.paper.ingame_score_drift_audit -- snapshot-then-diff
score-drift audit for the settled paper_ingame ledger (D5 seed).

BACKGROUND: settlement_correctness_audit.audit_ingame_channel already proves
a settled row's stored home/away score can disagree with a FRESH replay of
the live resolver (score_mismatch). What it cannot tell you is WHY: was the
row wrong the moment it settled, or did the local realized-box parquet
(data/domains/mlb/espn_boxscores.parquet et al) get rebuilt/rescraped LATER
and silently drift out from under an already-correct settled row? Answering
that needs a TIME SERIES, not a single point-in-time replay.

This module is the time series. Each run:
  1. reads the CURRENT ledger + the CURRENT resolver score for every settled
     paper_ingame row (reuses ingame_paper_settle._default_score_fn via
     settlement_correctness_audit -- never reimplements a resolver);
  2. classifies today's ledger-vs-parquet mismatches against the snapshot
     HISTORY recorded by all PRIOR runs (parquet moved after we first saw it
     agree, vs. never agreed even at the earliest observation);
  3. appends today's snapshot rows to an append-only JSONL history file
     (forward-only -- never rewrites a past line);
  4. writes a full-replace quarantine FLAG LIST reflecting the current
     mismatch state.

Both artifacts are SIDECARS. Neither ever touches the settled ledger --
re-settling / retroactive repair is HUMAN-gated, out of scope here.

CAVEAT (honest, not hidden): the "first snapshot" for any row that was
ALREADY settled before this module's first run is only the earliest
AUDIT-TIME observation, not true settle-time truth (that's already lost for
the pre-existing backlog -- the whole reason this job exists going forward).
A row therefore needs >=2 runs before "parquet moved after we first observed
it" vs "already wrong at first observation" can be told apart; with exactly
one prior snapshot both cases collapse to baseline_unclassified.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII only; no network;
never writes data/registry/; never flips a flag; no $/ROI language.

CLI:
  python -m scripts.platformkit.paper.ingame_score_drift_audit

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/paper/test_ingame_score_drift_audit.py -q

FOLLOW-UP (not done here): wiring this into the m38 autoloop daemon so it
runs on a cadence automatically. Left for a separate lane -- this module only
adds the reusable job + CLI entry point.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.io_atomic import write_json_atomic, write_text_atomic
from scripts.platformkit.paper.settlement_correctness_audit import (
    _default_ingame_score_fn,
    _INGAME_CHANNEL,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SNAPSHOT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "ingame_score_snapshot.jsonl"
DEFAULT_FLAGS_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "ingame_score_drift_flags.json"

ScoreFn = Callable[[str], Optional[Any]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_id(r: Dict[str, Any]) -> str:
    return str(r.get("settle_key") or r.get("bet_id") or r.get("edge_key") or "")


def build_snapshot_rows(rows: List[Dict[str, Any]], score_fn: ScoreFn,
                        captured_at: Optional[str] = None) -> List[Dict[str, Any]]:
    """One snapshot dict per settled paper_ingame row: the ledger's stored
    score alongside a FRESH resolver read taken right now."""
    captured_at = captured_at or _now_iso()
    out = []
    for r in rows:
        if r.get("channel") != _INGAME_CHANNEL or r.get("status") != "settled":
            continue
        gid = str(r.get("game_id") or "")
        try:
            fresh = score_fn(gid)
        except Exception:  # noqa: BLE001 -- one bad ticker never stops the sweep
            fresh = None
        out.append({
            "id": _row_id(r), "sport": str(r.get("sport") or "?"), "game_id": gid,
            "ledger_home": r.get("home_score"), "ledger_away": r.get("away_score"),
            "ledger_outcome": r.get("outcome"), "settled_at": r.get("settled_at"),
            "parquet_home": fresh[0] if fresh else None,
            "parquet_away": fresh[1] if fresh else None,
            "captured_at": captured_at,
        })
    return out


def load_snapshot_history(path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """id -> prior snapshot dicts, oldest first. Missing/corrupt lines skip,
    never fatal -- this is a diagnostic sidecar, not the ledger."""
    hist: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    if not path.exists():
        return hist
    for line in path.read_text(encoding="ascii", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        hist[str(d.get("id", ""))].append(d)
    for rid in hist:
        hist[rid].sort(key=lambda d: str(d.get("captured_at") or ""))
    return hist


def _append_jsonl_batch(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Append many rows in ONE atomic write. append_jsonl_atomic does a full
    read-modify-write PER row (see io_atomic docstring); calling it once per
    settled row here (hundreds) would re-read/rewrite the growing file that
    many times. Same tmp+os.replace guarantee, batched to one pass."""
    if not rows:
        return
    existing = path.read_text(encoding="ascii", errors="replace") if path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    new_lines = "".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in rows)
    write_text_atomic(path, existing + new_lines, encoding="ascii")


def classify_mismatches(rows: List[Dict[str, Any]], score_fn: ScoreFn,
                        history: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Flag every settled paper_ingame row whose ledger score disagrees with
    the CURRENT resolver read, classified against snapshot history. A row
    that matches NOW is never flagged even if history shows past drift --
    forward-only, no retroactive judgement on a row that reads clean today."""
    flags = []
    for r in rows:
        if r.get("channel") != _INGAME_CHANNEL or r.get("status") != "settled":
            continue
        hs, aws = r.get("home_score"), r.get("away_score")
        if hs is None or aws is None:
            continue
        gid = str(r.get("game_id") or "")
        try:
            fresh = score_fn(gid)
        except Exception:  # noqa: BLE001
            fresh = None
        if fresh is None or (int(fresh[0]) == int(hs) and int(fresh[1]) == int(aws)):
            continue
        rid = _row_id(r)
        hist = history.get(rid, [])
        first = hist[0] if hist else None
        if first is None:
            kind, first_seen = "baseline_unclassified", "this_run"
        else:
            first_matches_ledger = (first.get("parquet_home") == hs and first.get("parquet_away") == aws)
            if len(hist) == 1:
                kind = "parquet_rebuilt_after_settle" if first_matches_ledger else "baseline_unclassified"
            else:
                kind = "parquet_rebuilt_after_settle" if first_matches_ledger else "wrong_at_settle_time"
            prior_mismatch = [h.get("captured_at") for h in hist
                              if not (h.get("parquet_home") == hs and h.get("parquet_away") == aws)]
            first_seen = min(prior_mismatch) if prior_mismatch else str(first.get("captured_at") or "this_run")
        flags.append({
            "id": rid, "sport": str(r.get("sport") or "?"), "game_id": gid, "kind": kind,
            "ledger_score": [hs, aws], "parquet_score_now": list(fresh),
            "first_snapshot_score": [first.get("parquet_home"), first.get("parquet_away")] if first else None,
            "snapshot_count": len(hist), "first_seen": first_seen,
        })
    return flags


def run_audit(ledger_path: Optional[Path] = None, snapshot_path: Optional[Path] = None,
             flags_path: Optional[Path] = None, score_fn: Optional[ScoreFn] = None) -> Dict[str, Any]:
    """One audit cycle. Never raises -- see per-step guards above."""
    ledger_path = Path(ledger_path) if ledger_path else _clv.DEFAULT_LEDGER
    snapshot_path = Path(snapshot_path) if snapshot_path else DEFAULT_SNAPSHOT_PATH
    flags_path = Path(flags_path) if flags_path else DEFAULT_FLAGS_PATH
    score_fn = score_fn or _default_ingame_score_fn()

    rows = _clv.load_ledger(ledger_path)
    history = load_snapshot_history(snapshot_path)  # BEFORE this run's rows land
    flags = classify_mismatches(rows, score_fn, history)
    snap_rows = build_snapshot_rows(rows, score_fn)
    _append_jsonl_batch(snapshot_path, snap_rows)

    report = {
        "generated_at": _now_iso(), "component": "ingame_score_drift_audit",
        "n_settled_scanned": len(snap_rows), "n_flags": len(flags),
        "by_kind": dict(Counter(f["kind"] for f in flags)),
        "flags": flags,
        "note": "sidecar only; never writes the settled ledger; re-settle decisions are HUMAN-gated",
    }
    write_json_atomic(flags_path, report)
    return report


def main() -> int:
    report = run_audit()
    summary = {k: v for k, v in report.items() if k != "flags"}
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_snapshot_rows", "load_snapshot_history", "classify_mismatches",
           "run_audit", "DEFAULT_SNAPSHOT_PATH", "DEFAULT_FLAGS_PATH"]
