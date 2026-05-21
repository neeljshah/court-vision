"""_plan_parse.py — frontmatter/YAML parsing and plan-id helpers for the scan_plans pipeline."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
    _HAVE_YAML = True
except ImportError:
    _HAVE_YAML = False


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
