"""backlog_lint.py — Lint BUILD_BACKLOG.md for schema, honest-edge, and file-collision issues.

Reuses backlog.py's parse() function; adds three independent lint passes:

  (a) SCHEMA — hard-required fields present (id, title, done_criteria); depends_on ids
      all resolve against the task graph, known epics, or are range deps.
      Note: `do` and `files` are optional by backlog convention — many gate/verify/ops
      tasks legitimately omit them.  The parser (backlog._coerce) derives `phase` from
      the epic prefix when it is not explicit, so phase is always populated.
  (b) HONEST-EDGE — no task do/done_criteria/title asserts a betting edge exists /
      is proven / is profitable.
  (c) FILE-COLLISION — tasks sharing a parallel_group that also share a file path
      (they must serialize; the harness catches this at wave time, but early lint
      is cheaper and clearer).

CLI prints a structured report. Exit codes:
  0 — no schema errors (warnings/collisions are non-fatal but printed)
  1 — one or more schema errors found
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "platform_harness"))

import backlog  # noqa: E402  (path insertion above)

# ---------------------------------------------------------------------------
# Hard-required fields — the harness CANNOT function without these.
# (do, files, change_kind are optional per backlog convention)
# ---------------------------------------------------------------------------

REQUIRED_FIELDS: Tuple[str, ...] = (
    "id",
    "title",
    "done_criteria",
)

# ---------------------------------------------------------------------------
# Honest-edge patterns — phrases that claim a betting edge exists / is proven
# ---------------------------------------------------------------------------

_EDGE_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (  # type: ignore[type-arg]
    ("edge_exists", re.compile(r"\bedge\s+exists\b", re.I)),
    ("proven_edge", re.compile(r"\bproven\s+edge\b", re.I)),
    ("edge_proven", re.compile(r"\bedge\s+(is\s+)?proven\b", re.I)),
    ("profitable", re.compile(r"\bprofitable\b", re.I)),
    ("beats_close", re.compile(r"\bbeats?\s+the\s+(close|market|books?)\b", re.I)),
    ("roi_edge", re.compile(r"\b\d+(\.\d+)?%\s*(roi|edge)\b", re.I)),
    ("positive_ev_proven", re.compile(r"\+EV\s+proven\b", re.I)),
    ("guaranteed_returns", re.compile(r"\bguaranteed\s+(return|profit|edge|win)\b", re.I)),
)

# ---------------------------------------------------------------------------
# Data classes for lint results
# ---------------------------------------------------------------------------


class SchemaError(NamedTuple):
    """A hard schema violation that blocks execution."""
    task_id: str
    message: str

    def __str__(self) -> str:
        return f"SCHEMA_ERROR [{self.task_id}]: {self.message}"


class EdgeWarning(NamedTuple):
    """A task text that asserts a betting edge."""
    task_id: str
    field: str
    pattern: str
    excerpt: str

    def __str__(self) -> str:
        return (
            f"HONEST_EDGE_WARN [{self.task_id}] field={self.field!r} "
            f"pattern={self.pattern!r}: {self.excerpt!r}"
        )


class CollisionWarning(NamedTuple):
    """Two tasks in the same parallel_group share a file (must serialize)."""
    parallel_group: str
    file_path: str
    task_ids: Tuple[str, ...]

    def __str__(self) -> str:
        ids = ", ".join(self.task_ids)
        return (
            f"FILE_COLLISION [{self.parallel_group}] file={self.file_path!r} "
            f"shared_by=[{ids}]"
        )


# ---------------------------------------------------------------------------
# Lint pass (a): schema validation
# ---------------------------------------------------------------------------


def lint_schema(tasks: Dict[str, dict]) -> List[SchemaError]:
    """Validate every task against the required-field contract.

    Hard requirements:
    - id, title, done_criteria must be non-empty strings.
    - depends_on ids must resolve to a known task id, known epic, or be a range dep
      (contains '..').  Unknown references are hard errors.

    Optional (not validated here):
    - do, files, change_kind — many gate/verify/ops tasks legitimately omit them.
    - phase — always populated by backlog._coerce (derived from epic prefix).

    Returns a list of SchemaError. Empty list = clean.
    """
    errors: List[SchemaError] = []
    all_ids = set(tasks.keys())
    all_epics = {backlog.epic_of(t) for t in tasks.values()}

    for tid, task in tasks.items():
        # Required fields: id/title/done_criteria must be present and non-empty
        for field in REQUIRED_FIELDS:
            value = task.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(
                    SchemaError(tid, f"required field {field!r} is missing or empty")
                )

        # files must be a list type when present (parser always coerces, but defend)
        files_val = task.get("files")
        if files_val is not None and not isinstance(files_val, list):
            errors.append(
                SchemaError(tid, "'files' is present but not a list (parser coerce failed)")
            )

        # depends_on ids must exist or be range deps or known epics
        for dep in task.get("depends_on") or []:
            if ".." in dep:
                # Range dep (e.g. "X-P1-001..016") — accepted as-is, checked at wave time
                continue
            dep_clean = dep.lstrip("[").rstrip("]").strip()
            if dep_clean in all_ids or dep_clean in all_epics:
                continue
            # Check if it derives from a known epic family (e.g. task in a table-format epic)
            dep_epic = backlog._epic_from_id(dep_clean)
            if dep_epic and dep_epic in all_epics:
                continue
            errors.append(
                SchemaError(tid, f"depends_on references unknown id/epic: {dep!r}")
            )

    return errors


# ---------------------------------------------------------------------------
# Lint pass (b): honest-edge
# ---------------------------------------------------------------------------

_EDGE_FIELDS = ("title", "do", "done_criteria")


def lint_honest_edge(tasks: Dict[str, dict]) -> List[EdgeWarning]:
    """Check that no task title/do/done_criteria asserts a proven betting edge.

    Returns a list of EdgeWarning (soft warnings). Empty = clean.
    """
    warnings: List[EdgeWarning] = []
    for tid, task in tasks.items():
        for field in _EDGE_FIELDS:
            text = task.get(field) or ""
            for pattern_name, pat in _EDGE_PATTERNS:
                m = pat.search(text)
                if m:
                    start = max(0, m.start() - 20)
                    end = min(len(text), m.end() + 20)
                    excerpt = text[start:end].replace("\n", " ")
                    warnings.append(
                        EdgeWarning(
                            task_id=tid,
                            field=field,
                            pattern=pattern_name,
                            excerpt=excerpt,
                        )
                    )
    return warnings


# ---------------------------------------------------------------------------
# Lint pass (c): file-collision within parallel_group
# ---------------------------------------------------------------------------


def lint_file_collisions(tasks: Dict[str, dict]) -> List[CollisionWarning]:
    """Report tasks in the same parallel_group that share a file path.

    These tasks MUST be serialized.  The harness normally enforces this at wave
    time, but catching it early is cheaper and provides a clearer message.

    Returns a list of CollisionWarning. Empty = no collisions.
    """
    # group_id -> list of (task_id, files)
    groups: Dict[str, List[Tuple[str, List[str]]]] = {}
    for tid, task in tasks.items():
        pg = task.get("parallel_group")
        if not pg:
            continue
        files = task.get("files") or []
        groups.setdefault(pg, []).append((tid, files))

    collisions: List[CollisionWarning] = []
    for group, members in groups.items():
        # Build map: normalized_file_path -> [task_ids that touch it]
        file_to_tasks: Dict[str, List[str]] = {}
        for tid, files in members:
            for fp in files:
                fp_norm = fp.strip().replace("\\", "/")
                file_to_tasks.setdefault(fp_norm, []).append(tid)
        for fp, tids in file_to_tasks.items():
            if len(tids) > 1:
                collisions.append(
                    CollisionWarning(
                        parallel_group=group,
                        file_path=fp,
                        task_ids=tuple(sorted(tids)),
                    )
                )
    return collisions


# ---------------------------------------------------------------------------
# Public API: run all lint passes
# ---------------------------------------------------------------------------


def run_lint(
    path: Optional[Path] = None,
) -> Tuple[List[SchemaError], List[EdgeWarning], List[CollisionWarning]]:
    """Parse the backlog and run all three lint passes.

    Args:
        path: Path to BUILD_BACKLOG.md.  Defaults to the canonical location.

    Returns:
        (schema_errors, edge_warnings, collision_warnings)
        schema_errors is non-empty → caller should exit nonzero.
    """
    effective_path = path or backlog.BUILD_BACKLOG
    tasks, parse_errors = backlog.parse(effective_path)

    # Promote parse-level errors (duplicate ids, absolute paths, etc.) to SchemaErrors
    schema_errors: List[SchemaError] = [
        SchemaError("(parse)", e) for e in parse_errors
    ]
    schema_errors.extend(lint_schema(tasks))
    edge_warnings = lint_honest_edge(tasks)
    collision_warnings = lint_file_collisions(tasks)

    return schema_errors, edge_warnings, collision_warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Lint BUILD_BACKLOG.md — schema, honest-edge, and file-collision checks."
        )
    )
    ap.add_argument(
        "--path",
        metavar="FILE",
        default=None,
        help="Path to BUILD_BACKLOG.md (default: canonical .planning/platform/ location)",
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-item detail; only print summary counts.",
    )
    args = ap.parse_args()

    target = Path(args.path) if args.path else None
    schema_errors, edge_warnings, collision_warnings = run_lint(target)

    total_schema = len(schema_errors)
    total_edge = len(edge_warnings)
    total_collision = len(collision_warnings)

    # --- Schema errors (hard) ---
    print(f"=== SCHEMA ERRORS: {total_schema} ===")
    if not args.quiet:
        for err in schema_errors:
            print(f"  {err}")

    # --- Honest-edge warnings ---
    print(f"=== HONEST-EDGE WARNINGS: {total_edge} ===")
    if not args.quiet:
        for w in edge_warnings:
            print(f"  {w}")

    # --- File-collision warnings ---
    print(f"=== FILE-COLLISION WARNINGS: {total_collision} ===")
    if not args.quiet:
        for c in collision_warnings:
            print(f"  {c}")

    # Summary line
    status = "PASS" if total_schema == 0 else "FAIL"
    print(
        f"\nRESULT: {status} | "
        f"schema_errors={total_schema} "
        f"edge_warnings={total_edge} "
        f"file_collisions={total_collision}"
    )

    sys.exit(1 if total_schema > 0 else 0)


if __name__ == "__main__":
    _main()
