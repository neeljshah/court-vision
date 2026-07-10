"""scripts.platformkit.ledger_squash -- one-time dedupe of the 4 knowledge
ledgers (docs/research/ledger_dedupe_audit_2026-07-10.md). 42% of rows were
byte-identical re-appends -- the writer had no content guard (now fixed
forward in io_atomic.append_jsonl_atomic; see the same audit). These 4 files
are rebuildable KNOWLEDGE CACHES (re-derivable by re-running the validators),
not settlement/betting history -- adjudicated safe to squash in place, with a
.bak of the pre-squash file preserved alongside each ledger (repo-wide
`*.bak` is already gitignored, so the .bak never lands in a commit).

Run: python -m scripts.platformkit.ledger_squash
"""
from __future__ import annotations

import json
import pathlib

from scripts.platformkit.io_atomic import write_text_atomic

_LEDGERS = [
    "domains/basketball_nba/knowledge/validation_ledger.jsonl",
    "domains/mlb/knowledge/validation_ledger.jsonl",
    "domains/soccer/knowledge/validation_ledger.jsonl",
    "domains/tennis/knowledge/validation_ledger.jsonl",
]
_BAK_SUFFIX = ".pre_squash_2026-07-10.bak"


def _content_sig(row: dict) -> str:
    """Same ignoring-``run_ts`` signature as io_atomic's forward guard --
    two rows are the "same" if only their run_ts differs."""
    return json.dumps({k: v for k, v in row.items() if k != "run_ts"}, sort_keys=True, default=str)


def squash_ledger(path: str) -> tuple[int, int]:
    """Keep the FIRST occurrence (order preserved) of each exact-content row.
    Writes a .bak of the pre-squash file when anything actually changes.
    Returns (rows_before, rows_after).
    """
    p = pathlib.Path(path)
    if not p.is_file():
        return (0, 0)
    text = p.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    before = len(lines)
    seen: set[str] = set()
    kept = []
    for ln in lines:
        row = json.loads(ln)
        sig = _content_sig(row) if isinstance(row, dict) else ln
        if sig in seen:
            continue
        seen.add(sig)
        kept.append(ln)
    after = len(kept)
    if after != before:
        bak = p.parent / (p.name + _BAK_SUFFIX)
        bak.write_text(text, encoding="utf-8")
        write_text_atomic(p, "\n".join(kept) + "\n" if kept else "", encoding="utf-8")
    return (before, after)


def main() -> None:
    for path in _LEDGERS:
        before, after = squash_ledger(path)
        sport = pathlib.Path(path).parts[1]
        print(f"{sport}: {before} -> {after} rows")


if __name__ == "__main__":
    main()
