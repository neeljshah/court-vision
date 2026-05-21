"""scan_plans.py — task-discovery CLI that keeps the autonomous bot queue self-stocked.

Scans the repo's planning corpus, finds the highest-priority un-built work,
and optionally appends it to .planning/queue/ai-todo.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Repo root: this file lives at scripts/bot_guards/scan_plans.py
REPO_ROOT = Path(__file__).resolve().parents[2]
PHASES_DIR = REPO_ROOT / ".planning" / "phases"
AI_TODO = REPO_ROOT / ".planning" / "queue" / "ai-todo.md"
DONE_MD = REPO_ROOT / ".planning" / "queue" / "done.md"
CLAUDE_STATE = REPO_ROOT / "docs" / "CLAUDE-state.md"

try:
    import yaml  # type: ignore
    _HAVE_YAML = True
except ImportError:
    _HAVE_YAML = False

# Console may be cp1252 on Windows — keep em-dashes / unicode in menu output intact.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass


# ---------------------------------------------------------------------------
# YAML / frontmatter parsing
# ---------------------------------------------------------------------------

def _parse_frontmatter_stdlib(text: str) -> dict[str, Any]:
    """Minimal flat-field parser when pyyaml is unavailable."""
    result: dict[str, Any] = {}
    lines = text.splitlines()
    i = 0
    current_key: str | None = None
    current_list: list[str] | None = None

    for line in lines:
        stripped = line.strip()
        # Key: scalar value
        kv = re.match(r'^(\w[\w\-]*)\s*:\s*(.+)$', line)
        if kv and not line.startswith(' ') and not line.startswith('\t'):
            if current_key and current_list is not None:
                result[current_key] = current_list
            current_key = kv.group(1)
            current_list = None
            val = kv.group(2).strip().strip('"\'')
            # coerce booleans; keep 'plan' as string to preserve zero-padding
            if val.lower() == 'true':
                result[current_key] = True
            elif val.lower() == 'false':
                result[current_key] = False
            elif current_key != 'plan' and re.match(r'^\d+$', val):
                result[current_key] = int(val)
            else:
                result[current_key] = val
            current_key = None
        # Key: list start (value is empty)
        kl = re.match(r'^(\w[\w\-]*)\s*:\s*$', line)
        if kl and not line.startswith(' ') and not line.startswith('\t'):
            if current_key and current_list is not None:
                result[current_key] = current_list
            current_key = kl.group(1)
            current_list = []
        # List item under current key
        elif current_list is not None and re.match(r'^\s+-\s+', line):
            item = re.sub(r'^\s+-\s+', '', line).strip().strip('"\'')
            current_list.append(item)
        elif current_list is not None and stripped and not stripped.startswith('-'):
            # End of list
            result[current_key] = current_list  # type: ignore[index]
            current_key = None
            current_list = None

    if current_key and current_list is not None:
        result[current_key] = current_list

    return result


def _extract_frontmatter(path: Path) -> dict[str, Any]:
    """Return parsed frontmatter dict from a PLAN.md file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    # Find --- delimiters
    lines = text.splitlines()
    if not lines or lines[0].strip() != '---':
        return {}
    end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == '---'), None)
    if end is None:
        # No closing delimiter: pure-YAML GSD plan (e.g. 17-10..17-25-PLAN.md) —
        # the whole file is one YAML document. Parse all of it.
        fm_text = '\n'.join(lines[1:])
    else:
        fm_text = '\n'.join(lines[1:end])

    if _HAVE_YAML:
        try:
            data = yaml.safe_load(fm_text) or {}
            # drill into must_haves.truths if nested
            # Preserve plan as string (yaml parses '01' → 1; restore via raw scan)
            plan_m = re.search(r'^plan\s*:\s*(\S+)', fm_text, re.MULTILINE)
            if plan_m:
                data['plan'] = plan_m.group(1).strip('"\'')
            return data
        except Exception:
            pass
    return _parse_frontmatter_stdlib(fm_text)


def _extract_truths(fm: dict[str, Any]) -> list[str]:
    """Get must_haves.truths list from parsed frontmatter."""
    mh = fm.get('must_haves')
    if isinstance(mh, dict):
        truths = mh.get('truths', [])
        if isinstance(truths, list):
            return [str(t) for t in truths]
    return []


def _extract_objective(path: Path) -> str:
    """Extract text inside first <objective>...</objective> block, or first # heading."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return path.stem

    m = re.search(r'<objective>(.*?)</objective>', text, re.DOTALL)
    if m:
        obj = re.sub(r'\s+', ' ', m.group(1)).strip()
        return obj[:200]

    for line in text.splitlines():
        if line.startswith('# '):
            return line[2:].strip()[:200]

    return path.stem


# ---------------------------------------------------------------------------
# Plan-id helpers
# ---------------------------------------------------------------------------

def _plan_id_from_fm_and_path(fm: dict[str, Any], path: Path) -> str:
    """Derive canonical plan id like '17-02', '025-04', '14-5a-01'."""
    phase = str(fm.get('phase', '') or '').strip()
    plan = str(fm.get('plan', '') or '').strip()

    if phase and plan:
        # phase may be '17-infrastructure'; take leading token before first space
        phase_tok = phase.split()[0] if ' ' in phase else phase
        # strip trailing alpha-descriptor after last hyphen group if it matches dir name
        # e.g. '17-infrastructure' → '17'
        parts = phase_tok.split('-')
        # keep numeric-ish leading parts (support '14-5a')
        leading = []
        for p in parts:
            if re.match(r'^\d', p):
                leading.append(p)
            else:
                break
        phase_num = '-'.join(leading) if leading else parts[0]
        return f"{phase_num}-{plan}"

    # Fallback: derive from filename e.g. '17-02-PLAN.md'
    stem = path.stem  # '17-02-PLAN'
    m = re.match(r'^([\d\-a-z]+)-PLAN$', stem, re.IGNORECASE)
    if m:
        return m.group(1)
    return stem


def _plan_id_sort_key(pid: str) -> tuple:
    """Numeric sort key for plan ids like '025-04', '17-02', '14-5a-01'."""
    parts = pid.split('-')
    key = []
    for p in parts:
        m = re.match(r'^(\d+)(.*)', p)
        if m:
            key.append(int(m.group(1)))
            key.append(m.group(2))
        else:
            key.append(0)
            key.append(p)
    return tuple(key)


# ---------------------------------------------------------------------------
# Readiness check
# ---------------------------------------------------------------------------

def _check_readiness(depends_on: list[str], built_ids: set[str]) -> bool:
    """READY if all dependencies are built (have SUMMARYs)."""
    if not depends_on:
        return True
    return all(dep in built_ids for dep in depends_on)


# ---------------------------------------------------------------------------
# Open Issues from docs/CLAUDE-state.md
# ---------------------------------------------------------------------------

def _load_open_issues() -> list[dict[str, Any]]:
    """Parse ## Open Issues section from docs/CLAUDE-state.md."""
    issues: list[dict[str, Any]] = []
    if not CLAUDE_STATE.exists():
        return issues
    try:
        text = CLAUDE_STATE.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return issues

    in_section = False
    for line in text.splitlines():
        if re.match(r'^## Open Issues', line):
            in_section = True
            continue
        if in_section:
            if re.match(r'^## ', line):
                break  # next section
            # Match: N. **Title** — description  OR  N. Title — description
            m = re.match(r'^\d+\.\s+\*\*(.+?)\*\*\s*[—-]+\s*(.+)$', line)
            if not m:
                m = re.match(r'^\d+\.\s+(.+?)\s*[—-]+\s*(.+)$', line)
            if m:
                title = m.group(1).strip()
                desc = m.group(2).strip()
                issues.append({'title': title, 'desc': desc, 'source': 'docs/CLAUDE-state.md (Open Issues)'})
    return issues


# ---------------------------------------------------------------------------
# Dedup helpers
# ---------------------------------------------------------------------------

def _load_text_safe(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ''


# ---------------------------------------------------------------------------
# Main discovery
# ---------------------------------------------------------------------------

def discover_candidates() -> list[dict[str, Any]]:
    """Return ordered list of candidate task dicts."""
    # ---- Collect all PLAN.md files ----
    plan_paths: list[Path] = sorted(PHASES_DIR.rglob("*-PLAN.md")) if PHASES_DIR.exists() else []

    # ---- Dedup / completion corpus: ai-todo.md + done.md ----
    todo_text = _load_text_safe(AI_TODO)
    done_text = _load_text_safe(DONE_MD)
    dedup_corpus = todo_text + '\n' + done_text

    # ---- Discover built ids: peer SUMMARY exists, OR already completed in done.md ----
    # The done.md check lets the dependency chain self-unblock as the bot ships plans
    # (the bot logs each finished task's source path to done.md but writes no SUMMARY).
    built_ids: set[str] = set()
    all_plans: list[dict[str, Any]] = []

    for pp in plan_paths:
        summary_path = Path(str(pp).replace('-PLAN.md', '-SUMMARY.md'))
        rel = str(pp.relative_to(REPO_ROOT)).replace('\\', '/')
        is_built = summary_path.exists() or rel in done_text
        fm = _extract_frontmatter(pp)
        pid = _plan_id_from_fm_and_path(fm, pp)

        if is_built:
            built_ids.add(pid)

        fm_deps = fm.get('depends_on') or []
        if isinstance(fm_deps, str):
            fm_deps = [fm_deps] if fm_deps else []
        deps: list[str] = [str(d) for d in fm_deps]

        files_mod = fm.get('files_modified') or []
        if isinstance(files_mod, str):
            files_mod = [files_mod] if files_mod else []

        reqs = fm.get('requirements') or []
        truths = _extract_truths(fm)

        all_plans.append({
            'id': pid,
            'path': pp,
            'rel_path': str(pp.relative_to(REPO_ROOT)).replace('\\', '/'),
            'is_built': is_built,
            'fm': fm,
            'depends_on': deps,
            'files_modified': [str(f) for f in files_mod],
            'requirements': [str(r) for r in reqs],
            'autonomous': bool(fm.get('autonomous', True)),
            'truths': truths,
        })

    # ---- Build candidate list from unbuilt plans ----
    candidates: list[dict[str, Any]] = []
    for p in all_plans:
        if p['is_built']:
            continue
        # Dedup: skip if rel_path already appears in todo or done
        if p['rel_path'] in dedup_corpus:
            continue

        ready = _check_readiness(p['depends_on'], built_ids)
        objective = _extract_objective(p['path'])
        # Pure-YAML plans have no <objective> tag — fall back to first must-have truth
        if objective == p['path'].stem and p['truths']:
            objective = p['truths'][0]

        candidates.append({
            'id': p['id'],
            'source': 'gsd',
            'rel_path': p['rel_path'],
            'title': objective,
            'files_modified': p['files_modified'],
            'truths': p['truths'],
            'depends_on': p['depends_on'],
            'autonomous': p['autonomous'],
            'ready': ready,
            'priority': 'P1',
        })

    # Sort: READY first, then by plan id numerically
    candidates.sort(key=lambda c: (0 if c['ready'] else 1, _plan_id_sort_key(c['id'])))

    # ---- Open issues ----
    issues = _load_open_issues()
    for iss in issues:
        title = iss['title']
        if title in dedup_corpus or iss['source'] in dedup_corpus:
            continue
        candidates.append({
            'id': f"issue-{re.sub(r'[^a-z0-9]+', '-', title.lower())[:20]}",
            'source': 'open-issues',
            'rel_path': iss['source'],
            'title': f"{title} — {iss['desc']}",
            'files_modified': [],
            'truths': [],
            'depends_on': [],
            'autonomous': True,
            'ready': True,
            'priority': 'P0',
        })

    return candidates


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
