"""_plan_discovery.py — path constants and candidate-discovery logic for the scan_plans pipeline."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _plan_parse import (  # noqa: E402
    _extract_frontmatter,
    _extract_objective,
    _extract_truths,
    _plan_id_from_fm_and_path,
    _plan_id_sort_key,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASES_DIR = REPO_ROOT / ".planning" / "phases"
AI_TODO = REPO_ROOT / ".planning" / "queue" / "ai-todo.md"
DONE_MD = REPO_ROOT / ".planning" / "queue" / "done.md"
CLAUDE_STATE = REPO_ROOT / "docs" / "CLAUDE-state.md"


def _check_readiness(depends_on: list[str], built_ids: set[str]) -> bool:
    """READY if all dependencies are built (have SUMMARYs)."""
    if not depends_on:
        return True
    return all(dep in built_ids for dep in depends_on)


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


def _load_text_safe(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ''


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
