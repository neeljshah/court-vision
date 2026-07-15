"""Machine room builder: daemon roster + build provenance + recent verdicts.

Daemons: data/frontend/ops/autonomy_status.json 'services' list (already a
per-daemon roster: name/live/last_seen). Falls back to a **/_heartbeat.json
glob if that list is absent. Build provenance: git rev-list/log (read-only).
Loop verdicts: last 10 rows of data/frontend/reject_ledger.jsonl.
"""
from __future__ import annotations

import glob
import subprocess
from pathlib import Path
from typing import Any

from ..common import FRONTEND, REPO, read_json, read_jsonl, unavailable

AUTONOMY = FRONTEND / "ops" / "autonomy_status.json"
REJECT_LEDGER = FRONTEND / "reject_ledger.jsonl"
MODEL_ROLES = "Fable decides, Opus judges, Sonnet fleet executes"


def _status_word(live: Any) -> str:
    if live is True:
        return "ok"
    if live is False:
        return "down"
    return "unknown"


def _daemons_from_autonomy(status: dict) -> list[dict]:
    services = status.get("services") or []
    return [
        {
            "name": s.get("name"),
            "purpose": None,
            "status": _status_word(s.get("live")),
            "last_beat_utc": s.get("last_seen"),
        }
        for s in services
    ]


def _daemons_from_heartbeats() -> list[dict]:
    out = []
    for p in glob.glob(str(FRONTEND / "**" / "_heartbeat.json"), recursive=True):
        path = Path(p)
        hb = read_json(path)
        if hb is None:
            continue
        last_beat = hb.get("as_of") or hb.get("generated_at") or hb.get("updated_at")
        out.append({"name": path.parent.name, "purpose": None, "status": "ok", "last_beat_utc": last_beat})
    return out


def _git(*args: str) -> str | None:
    try:
        res = subprocess.run(
            ["git", "-C", str(REPO), *args],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if res.returncode != 0:
            return None
        return res.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _build_provenance() -> dict:
    commits = _git("rev-list", "--count", "HEAD")
    first = _git("log", "--format=%cI", "--reverse", "-1")
    last = _git("log", "-1", "--format=%cI")
    return {
        "commits": int(commits) if commits and commits.isdigit() else None,
        "span": {"first": first, "last": last},
        "model_roles": MODEL_ROLES,
    }


def _recent_verdicts() -> list[dict]:
    rows = read_jsonl(REJECT_LEDGER)
    tail = rows[-10:] if rows else []
    return [
        {
            "ts": r.get("ts"),
            "sport": r.get("sport"),
            "signal": r.get("signal"),
            "verdict": r.get("verdict"),
            "reason": r.get("reason"),
        }
        for r in tail
    ]


def build() -> dict[str, Any]:
    status = read_json(AUTONOMY)
    daemons = _daemons_from_autonomy(status) if status else []
    if not daemons:
        daemons = _daemons_from_heartbeats()

    if not daemons and not REJECT_LEDGER.exists():
        return unavailable("no autonomy_status/autoloop/heartbeat sources and no reject_ledger found")

    return {
        "daemons": daemons,
        "build": _build_provenance(),
        "loop": {"recent_verdicts": _recent_verdicts()},
    }
