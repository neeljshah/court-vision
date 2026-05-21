"""scan_plans.py — task-discovery CLI that keeps the autonomous bot queue self-stocked.

Scans the repo's planning corpus, finds the highest-priority un-built work,
and optionally appends it to .planning/queue/ai-todo.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Console may be cp1252 on Windows — keep em-dashes / unicode in menu output intact.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _plan_discovery import discover_candidates, AI_TODO, REPO_ROOT  # noqa: E402


# ---------------------------------------------------------------------------
# Task block formatter
# ---------------------------------------------------------------------------

def _est(files: list[str]) -> str:
    n = len(files)
    if n <= 1:
        return 'S'
    if n <= 4:
        return 'M'
    return 'L'


def _touches_betting(files: list[str]) -> str:
    keywords = ('betting_portfolio', 'schema.sql', 'schema_v2')
    return 'yes' if any(any(kw in f for kw in keywords) for f in files) else 'no'


def _format_task_block(c: dict[str, Any]) -> str:
    files_str = ', '.join(c['files_modified']) if c['files_modified'] else 'see source PLAN'
    done_when = c['truths'][0] if c['truths'] else 'see acceptance criteria in source'
    # why = title (truncated to fit)
    why = c['title'][:180] if c['title'] else c['id']
    est = _est(c['files_modified']) if c['source'] == 'gsd' else 'M'
    touch = _touches_betting(c['files_modified'])

    lines = [
        f"## [{c['priority']}] {c['id']} — {c['title'][:80]}",
        f"- **why:** {why}; full spec in {c['rel_path']}",
        f"- **files:** {files_str}",
        f"- **done when:** {done_when}",
        f"- **est:** {est}",
        f"- **touch betting?:** {touch}",
        f"- **source:** {c['rel_path']}",
    ]
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# CLI modes
# ---------------------------------------------------------------------------

def cmd_menu(candidates: list[dict[str, Any]]) -> None:
    print(f"{'ID':<20} {'STATUS':<10} {'FILES':>5}  TITLE")
    print('-' * 90)
    for c in candidates:
        status = '[READY]' if c['ready'] else '[BLOCKED]'
        title_short = c['title'][:50]
        files_count = len(c['files_modified'])
        print(f"{c['id']:<20} {status:<10} {files_count:>5}  {title_short}")


def cmd_json(candidates: list[dict[str, Any]]) -> None:
    # Exclude non-serialisable Path objects
    out = []
    for c in candidates:
        row = {k: v for k, v in c.items() if k != 'path'}
        out.append(row)
    print(json.dumps(out, indent=2))


def cmd_write(candidates: list[dict[str, Any]], n: int, dry_run: bool) -> None:
    # Only READY GSD plans (open issues are already ready=True)
    writable = [c for c in candidates if c['ready']][:n]

    if not writable:
        print("No READY candidates to write.")
        return

    blocks = [_format_task_block(c) for c in writable]
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    separator = f"\n# Auto-replenished {timestamp}\n"
    content = separator + '\n\n'.join(blocks) + '\n'

    if dry_run:
        print("--- DRY RUN: would append to ai-todo.md ---")
        print(content)
        print("--- END DRY RUN ---")
        return

    AI_TODO.parent.mkdir(parents=True, exist_ok=True)
    with AI_TODO.open('a', encoding='utf-8') as fh:
        fh.write(content)

    print(f"Appended {len(writable)} task block(s) to {AI_TODO.relative_to(REPO_ROOT)}")
    for c in writable:
        print(f"  + {c['id']} [{c['priority']}] {c['title'][:60]}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Scan plans and replenish the bot task queue.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--menu', action='store_true', default=False, help='Print ranked candidate list (default)')
    mode.add_argument('--json', action='store_true', default=False, help='Emit candidates as JSON')
    mode.add_argument('--write', metavar='N', type=int, default=None,
                      help='Append top N READY candidates to ai-todo.md')
    parser.add_argument('--dry-run', action='store_true', default=False,
                        help='With --write: print blocks but do not modify ai-todo.md')
    args = parser.parse_args()

    candidates = discover_candidates()

    if args.json:
        cmd_json(candidates)
    elif args.write is not None:
        cmd_write(candidates, args.write, args.dry_run)
    else:
        # Default: --menu
        cmd_menu(candidates)


if __name__ == '__main__':
    main()
