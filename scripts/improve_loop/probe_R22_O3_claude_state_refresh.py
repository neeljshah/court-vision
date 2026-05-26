"""probe_R22_O3_claude_state_refresh.py

Diffs the prior `docs/CLAUDE-state.md` against the freshly-rewritten one,
counts top-level sections (## headings) before/after, and persists the
result to `data/cache/probe_R22_O3_results.json` for later auditing.

Two modes:
  (a) `--old PATH` provided   → diff against the saved snapshot at PATH.
  (b) no `--old` and `git`     → diff against the file's last committed
      version (HEAD^ if HEAD is the R22_O3 commit, else HEAD).

The probe is INFORMATIONAL — it does not gate the ship. The ship gate is
`tests/test_claude_state_currency.py`.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOC_REL = "docs/CLAUDE-state.md"
DOC_PATH = REPO_ROOT / DOC_REL
OUT_PATH = REPO_ROOT / "data" / "cache" / "probe_R22_O3_results.json"

SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _read_current() -> str:
    return DOC_PATH.read_text(encoding="utf-8", errors="replace")


def _read_git_blob(rev: str) -> str:
    out = subprocess.run(
        ["git", "show", f"{rev}:{DOC_REL}"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        return ""
    return out.stdout


def _count_sections(text: str) -> Tuple[int, List[str]]:
    matches = SECTION_RE.findall(text or "")
    return len(matches), matches


def _line_diff(old: str, new: str) -> Tuple[int, int, int]:
    old_lines = (old or "").splitlines()
    new_lines = (new or "").splitlines()
    return len(old_lines), len(new_lines), len(new_lines) - len(old_lines)


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:  # pragma: no cover - defensive
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--old",
        type=str,
        default=None,
        help="Path to prior CLAUDE-state.md snapshot. If omitted, falls back to git HEAD blob.",
    )
    parser.add_argument(
        "--rev",
        type=str,
        default="HEAD",
        help="Git rev to compare against when --old is not provided (default: HEAD).",
    )
    args = parser.parse_args()

    if not DOC_PATH.exists():
        print(f"FATAL: {DOC_PATH} does not exist", file=sys.stderr)
        return 2

    new_text = _read_current()
    if args.old:
        old_path = Path(args.old)
        old_text = old_path.read_text(encoding="utf-8", errors="replace") if old_path.exists() else ""
        old_source = f"file:{old_path}"
    else:
        old_text = _read_git_blob(args.rev)
        old_source = f"git:{args.rev}:{DOC_REL}"

    old_lines, new_lines, delta_lines = _line_diff(old_text, new_text)
    old_sections, old_section_names = _count_sections(old_text)
    new_sections, new_section_names = _count_sections(new_text)

    head = _git_head()
    head_short = head[:8] if head else ""
    mentions_head = bool(head_short) and head_short in new_text

    result = {
        "probe": "R22_O3_claude_state_refresh",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "doc_path": DOC_REL,
        "doc_lines_before": old_lines,
        "doc_lines_after": new_lines,
        "delta_lines": delta_lines,
        "sections_before": old_sections,
        "sections_after": new_sections,
        "section_names_after": new_section_names,
        "old_source": old_source,
        "head_commit": head,
        "head_short": head_short,
        "currency_ok": mentions_head,
        "under_150_lines": new_lines <= 150,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
