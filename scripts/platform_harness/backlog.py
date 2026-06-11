"""backlog.py — Parse BUILD_BACKLOG.md into task dicts + compute the ready set.

The ONLY parser of .planning/platform/BUILD_BACKLOG.md.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
BUILD_BACKLOG = ROOT / ".planning" / "platform" / "BUILD_BACKLOG.md"

KNOWN_KEYS = {
    "id", "title", "phase", "epic", "depends_on", "files",
    "change_kind", "do", "done_criteria", "size", "parallel_group",
    "owner_model", "review",
}
_LINT_ROI = re.compile(r"\b\d+(\.\d+)?%\s*(roi|edge)\b", re.I)
_LINT_BEAT = re.compile(r"\bbeats?\s+the\s+(close|market)\b(?!.*\bdoes\s+not\b)", re.I)

# A real task id: uppercase alnum segments joined by hyphens (P0-A-001, N-CLV-002,
# X-P2-GATE). The §1 TASK SCHEMA template block (id == "# globally unique, ...") and
# any other non-task ```yaml fence fail this and are skipped, NOT parsed as tasks.
_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$")


def _epic_from_id(tid: str) -> Optional[str]:
    """P0-A-001 -> P0-A · N-CLV-002 -> N-CLV · X-P2-GATE -> X-P2. None if no match."""
    m = re.match(r"^(.+?)-(\d+|GATE)$", tid)
    return m.group(1) if m else None


def _phase_from_epic(epic: Optional[str]) -> Optional[str]:
    """Deterministic epic-prefix -> MASTER_PLAN phase. Never returns None for a known
    epic family, so a task missing its `phase:` field is still gated to the right phase
    (extraction gates must NOT look ready during Phase 0)."""
    if not epic:
        return None
    e = epic.upper()
    if e.startswith("P0"):
        return "0"
    if e.startswith("T-"):
        return "1"
    if e.startswith("X-P") or e.startswith("LOOP-"):  # extraction waves live in phase 2
        return "2"
    if e == "LOOP":
        return "3"
    if e.startswith("A-"):
        return "4"
    if e.startswith("C-"):
        return "5"
    if e in ("W6", "W7", "W8", "W9"):
        return e[1]
    if e.startswith("N-") or e == "N":
        return "N"
    if e.startswith("M-") or e == "M":
        return "M"
    return None

# ── state (self-contained) ─────────────────────────────────────────────────

sys.path.insert(0, str(ROOT / "scripts" / "bot_guards"))
try:
    from _state import read_json_safe  # type: ignore
except ImportError:
    def read_json_safe(path: Path, default: dict) -> dict:  # type: ignore[misc]
        if not path.exists():
            return dict(default)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return dict(default)


def _load_state() -> dict:
    return read_json_safe(ROOT / ".planning" / "platform" / "build_state.json", {})


def _status(state: dict, tid: str) -> str:
    return state.get("tasks", {}).get(tid, {}).get("status", "todo")


# ── block parser ───────────────────────────────────────────────────────────

def _leading_key(seg: str) -> Tuple[Optional[str], str]:
    c = seg.find(":")
    if c < 0:
        return None, seg
    k, v = seg[:c].strip(), seg[c + 1:].strip()
    return (k, v) if k in KNOWN_KEYS else (None, seg)


def _parse_list(raw: str) -> List[str]:
    flat = re.sub(r"\s+", " ", raw).strip()
    m = re.match(r"\s*\[(.*)\]\s*$", flat, re.DOTALL)
    if not m or not m.group(1).strip():
        return []
    return [x.strip() for x in m.group(1).split(",") if x.strip()]


def _parse_block(raw: str) -> dict:
    fields: Dict[str, List[str]] = {}
    cur: Optional[str] = None
    for line in raw.split("\n"):
        segs = re.split(r"\s{2,}", line)
        k0, v0 = _leading_key(segs[0])
        if k0 is not None:
            cur = k0
            fields.setdefault(cur, [])
            if v0:
                fields[cur].append(v0)
            for seg in segs[1:]:
                k, v = _leading_key(seg)
                if k is not None:
                    cur = k
                    fields.setdefault(cur, [])
                    if v:
                        fields[cur].append(v)
                elif cur and seg.strip():
                    fields[cur].append(seg.strip())
        else:
            stripped = line.strip()
            if stripped and cur:
                for seg in segs:
                    seg = seg.strip()
                    if not seg:
                        continue
                    k, v = _leading_key(seg)
                    if k is not None:
                        cur = k
                        fields.setdefault(cur, [])
                        if v:
                            fields[cur].append(v)
                    elif cur:
                        fields[cur].append(seg)
    return {k: " ".join(v) for k, v in fields.items()}


def _coerce(raw: dict) -> dict:
    def _s(key: str, default: str = "") -> str:
        return raw.get(key, default).strip()

    t: dict = {}
    t["id"] = _s("id")
    t["title"] = _s("title")
    epic = _s("epic") or _epic_from_id(t["id"])
    t["epic"] = epic
    ph = _s("phase")
    t["phase"] = ph if ph else _phase_from_epic(epic)
    t["depends_on"] = _parse_list(raw.get("depends_on", "[]"))
    t["files"] = _parse_list(raw.get("files", "[]"))
    t["change_kind"] = _s("change_kind")
    t["do"] = _s("do")
    t["done_criteria"] = _s("done_criteria")
    t["size"] = _s("size") or "M"
    pg = _s("parallel_group")
    t["parallel_group"] = pg if pg else None
    t["owner_model"] = _s("owner_model") or "sonnet"
    t["review"] = _s("review") or "auto"
    return t


# ── public API ─────────────────────────────────────────────────────────────

def epic_of(task: dict) -> str:
    if task.get("epic"):
        return task["epic"]
    tid = task.get("id", "")
    return _epic_from_id(tid) or tid


def parse(path: Path = BUILD_BACKLOG) -> Tuple[Dict[str, dict], List[str]]:
    content = path.read_text(encoding="utf-8")
    blocks = re.findall(r"^```yaml\n(.*?)\n```", content, re.DOTALL | re.MULTILINE)
    tasks: Dict[str, dict] = {}
    errors: List[str] = []
    warnings: List[str] = []

    for raw_block in blocks:
        task = _coerce(_parse_block(raw_block))
        tid = task["id"]
        if not _ID_RE.match(tid):
            # Not a task: the §1 TASK SCHEMA template / any illustrative ```yaml fence.
            continue
        if tid in tasks:
            errors.append(f"Duplicate id: {tid!r}")
        tasks[tid] = task
        if not task["title"]:
            errors.append(f"{tid}: empty/missing title")
        if not task["done_criteria"]:
            errors.append(f"{tid}: empty/missing done_criteria")
        for fp in task["files"]:
            if re.match(r"^[A-Za-z]:[/\\]", fp) or fp.startswith("/"):
                errors.append(f"{tid}: absolute path in files: {fp!r}")
            if ".." in fp.replace("\\", "/").split("/"):
                errors.append(f"{tid}: '..' in files: {fp!r}")
        text = (task["do"] or "") + " " + (task["done_criteria"] or "")
        if _LINT_ROI.search(text) or _LINT_BEAT.search(text):
            warnings.append(f"{tid}: possible edge assertion")

    # Dep validation — pass 2
    all_ids = set(tasks)
    all_epics = {epic_of(t) for t in tasks.values()}
    for tid, task in tasks.items():
        for dep in task["depends_on"]:
            if ".." in dep or dep in all_ids or dep in all_epics:
                continue
            # Table-format task from a known epic → valid reference
            dep_epic = epic_of({"id": dep, "epic": ""})
            if dep_epic not in all_epics:
                errors.append(f"{tid}: unknown depends_on: {dep!r}")

    parse._warnings = warnings  # type: ignore[attr-defined]
    return tasks, errors


def epic_done(state: dict, epic: str, tasks: dict) -> bool:
    members = [t for t in tasks.values() if epic_of(t) == epic]
    return bool(members) and all(_status(state, t["id"]) == "done" for t in members)


def deps_satisfied(task: dict, state: dict, tasks: dict) -> bool:
    epics = {epic_of(t) for t in tasks.values()}
    for dep in task["depends_on"]:
        if ".." in dep:
            # range dep "X-P1-001..016" == "all of epic X-P1 done". Conservative:
            # while those tasks are still table-format (not decomposed), the epic has
            # zero parsed members so epic_done is False and the dependent stays unready.
            first = dep.split("..")[0].strip().lstrip("[")
            dep_epic = _epic_from_id(first) or first
            if not epic_done(state, dep_epic, tasks):
                return False
            continue
        if dep in tasks:
            if _status(state, dep) != "done":
                return False
        elif dep in epics:
            if not epic_done(state, dep, tasks):
                return False
        else:
            return False
    return True


def active_phase(state: dict, tasks: dict) -> str:
    for p in "0123456789":
        if any(t.get("phase") == p and _status(state, t["id"]) != "done"
               for t in tasks.values()):
            return p
    return "9"


def phase_eligible(task: dict, active: str) -> bool:
    tp = task.get("phase")
    # Track N/M run continuously; Lane-P tasks only when their phase is the active one.
    # An unknown (None) phase is NOT treated as always-eligible (conservative).
    return tp in {"N", "M"} or tp == active


def ready_set(state: dict | None = None, tasks: dict | None = None) -> List[dict]:
    if state is None:
        state = _load_state()
    if tasks is None:
        tasks, _ = parse()
    active = active_phase(state, tasks)
    blocked = {"blocked", "rolled_back", "done", "in_progress", "review", "rejected"}
    ready = [
        t for t in tasks.values()
        if _status(state, t["id"]) in ("todo", "ready")
        and _status(state, t["id"]) not in blocked
        and deps_satisfied(t, state, tasks)
        and phase_eligible(t, active)
    ]

    def _key(t: dict) -> tuple:
        tp = t.get("phase")
        if tp not in (None, "N", "M") and tp == active:
            lane = 0
        elif tp == "N":
            lane = 1
        elif tp == "M":
            lane = 2
        else:
            lane = 3
        return (lane, t.get("id", ""))

    return sorted(ready, key=_key)


def get(task_id: str) -> Optional[dict]:
    tasks, _ = parse()
    return tasks.get(task_id)


# ── CLI ────────────────────────────────────────────────────────────────────

def _main() -> None:
    ap = argparse.ArgumentParser(description="BUILD_BACKLOG.md parser/query CLI")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--ready", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--show", metavar="ID")
    args = ap.parse_args()

    if args.show:
        t = get(args.show)
        if t is None:
            print(f"Task {args.show!r} not found.", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(t, indent=2))
        return

    if args.validate:
        tasks, errors = parse()
        warnings = getattr(parse, "_warnings", [])
        print(f"Tasks parsed: {len(tasks)}")
        print(f"Hard errors: {len(errors)}")
        for e in errors:
            print(f"  ERROR: {e}")
        print(f"Soft warnings: {len(warnings)}")
        for w in warnings:
            print(f"  WARN: {w}")
        sys.exit(1 if errors else 0)

    if args.list:
        tasks, _ = parse()
        state = _load_state()
        for tid, task in sorted(tasks.items()):
            print(f"{tid}  phase={task.get('phase', '?')}  status={_status(state, tid)}")
        return

    # Default: --ready
    tasks, _ = parse()
    state = _load_state()
    ready = ready_set(state, tasks)
    print(f"{len(ready)} ready:")
    for t in ready:
        print(f"  {t['id']}  (phase={t.get('phase', '?')})")


if __name__ == "__main__":
    _main()
