"""scripts.platformkit.ops_sentinel.guard_integrity -- TAMPER-EVIDENCE for the
invariant surface (07-10 incident lesson).

Baselines the sha256 of scripts/hooks/pretooluse_guard.py + every
.claude/rules/*.md + CLAUDE.md into a state file. On any mismatch (changed /
missing / added rules file) it emits a RED status row AND an alarm file
data/frontend/ops/GUARD_INTEGRITY_ALERT.json naming each file with old/new hash.

NEVER auto-reverts: the 07-10 incident proved a parallel session's edit can be
legitimate -- this sentinel detects and surfaces ONLY. The baseline updates
ONLY via an explicit ``--accept-current`` CLI run (a human/orchestrator action),
never from the daemon tick.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ops_sentinel/test_guard_integrity.py -q
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.ops_sentinel.status_doc import (
    GREEN, OPS_DIR, RED, STATE_DIR, load_json, repo_root, write_doc,
)

COMPONENT = "ops_guard_integrity"
STATUS_PATH = OPS_DIR / "guard_integrity.json"
ALARM_PATH = OPS_DIR / "GUARD_INTEGRITY_ALERT.json"
BASELINE_PATH = STATE_DIR / "guard_integrity_baseline.json"
_NOTE = ("tamper-EVIDENCE only: detect + surface, NEVER auto-revert (a parallel "
         "session's edit can be legitimate, 07-10 incident). Baseline updates "
         "ONLY via an explicit --accept-current CLI run.")


def guarded_files(repo: Optional[Path] = None) -> List[Path]:
    """The invariant surface: guard hook + every rules file + CLAUDE.md.
    Globbed live so an ADDED or REMOVED rules file also surfaces."""
    root = Path(repo) if repo is not None else repo_root()
    files = [root / "scripts" / "hooks" / "pretooluse_guard.py",
             root / "CLAUDE.md"]
    files.extend(sorted((root / ".claude" / "rules").glob("*.md")))
    return files


def _sha256(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:  # noqa: BLE001
        return None


def current_hashes(repo: Optional[Path] = None) -> Dict[str, Optional[str]]:
    root = Path(repo) if repo is not None else repo_root()
    out: Dict[str, Optional[str]] = {}
    for p in guarded_files(root):
        out[p.relative_to(root).as_posix()] = _sha256(p)
    return out


def write_baseline(*, repo: Optional[Path] = None,
                   baseline_path: Optional[Path] = None,
                   now: Optional[float] = None) -> Path:
    """Seed/replace the baseline from CURRENT file contents. CLI-only action."""
    bp = Path(baseline_path) if baseline_path is not None else BASELINE_PATH
    doc = {"accepted_at": float(now) if now is not None else time.time(),
           "files": {k: v for k, v in current_hashes(repo).items() if v},
           "honest_note": _NOTE}
    bp.parent.mkdir(parents=True, exist_ok=True)
    tmp = bp.with_suffix(bp.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True),
                   encoding="ascii")
    os.replace(str(tmp), str(bp))
    return bp


def check_all(*, repo: Optional[Path] = None,
              baseline_path: Optional[Path] = None,
              now: Optional[float] = None) -> List[Dict[str, Any]]:
    """One row per guarded file: GREEN match / RED changed|missing|added.
    No baseline yet -> one RED no_baseline row (never silently green)."""
    baseline = load_json(baseline_path if baseline_path is not None
                         else BASELINE_PATH).get("files")
    if not isinstance(baseline, dict) or not baseline:
        return [{"name": "baseline", "status": RED, "reason": "no_baseline",
                 "detail": "run --accept-current to seed"}]
    cur = current_hashes(repo)
    rows: List[Dict[str, Any]] = []
    for rel in sorted(set(baseline) | set(cur)):
        old, new = baseline.get(rel), cur.get(rel)
        row: Dict[str, Any] = {"name": rel, "old_sha256": old, "new_sha256": new}
        if rel not in baseline:
            row.update(status=RED, reason="added")
        elif new is None:
            row.update(status=RED, reason="missing")
        elif old != new:
            row.update(status=RED, reason="changed")
        else:
            row.update(status=GREEN, reason=None)
        rows.append(row)
    return rows


def _write_alarm(rows: List[Dict[str, Any]], alarm_path: Path,
                 now: float) -> None:
    """RED rows present -> write the alarm file; all clean -> clear a stale
    alarm (hashes match the accepted baseline again). Never raises."""
    try:
        bad = [r for r in rows if r.get("status") == RED]
        if bad:
            doc = {"detected_at": now, "component": COMPONENT,
                   "mismatches": bad, "honest_note": _NOTE}
            alarm_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = alarm_path.with_suffix(alarm_path.suffix + ".tmp")
            tmp.write_text(json.dumps(doc, ensure_ascii=True, indent=2,
                                      sort_keys=True), encoding="ascii")
            os.replace(str(tmp), str(alarm_path))
        elif alarm_path.exists():
            alarm_path.unlink()
    except Exception:  # noqa: BLE001
        pass


def tick(*, now: Optional[float] = None, repo: Optional[Path] = None,
         baseline_path: Optional[Path] = None,
         status_path: Optional[Path] = None,
         alarm_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Check -> status doc -> alarm file. Never raises."""
    ts = float(now) if now is not None else time.time()
    try:
        rows = check_all(repo=repo, baseline_path=baseline_path, now=ts)
    except Exception as exc:  # noqa: BLE001
        rows = [{"name": "guard_integrity", "status": RED,
                 "reason": "error:%s" % str(exc)[:80]}]
    write_doc(status_path if status_path is not None else STATUS_PATH,
              COMPONENT, rows, now=ts, honest_note=_NOTE)
    _write_alarm(rows, Path(alarm_path) if alarm_path is not None
                 else ALARM_PATH, ts)
    return rows


def _main() -> int:  # pragma: no cover
    import argparse
    p = argparse.ArgumentParser(description="Guard-integrity sentinel: sha256 "
                                "tamper-evidence for the invariant surface.")
    p.add_argument("--accept-current", action="store_true",
                   help="seed/replace the baseline from CURRENT contents "
                        "(explicit human/orchestrator action)")
    a = p.parse_args()
    if a.accept_current:
        bp = write_baseline()
        print("guard_integrity | baseline accepted -> %s (%d files)"
              % (bp, len(load_json(bp).get("files", {}))), flush=True)
        return 0
    rows = tick()
    n_red = sum(1 for r in rows if r.get("status") == RED)
    print("guard_integrity | files=%d red=%d status=%s"
          % (len(rows), n_red, STATUS_PATH), flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
