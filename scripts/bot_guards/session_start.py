"""SessionStart hook for bot account — prints queue status + today's spend.

Counts only real headers (`## [P0]` etc.) so body-text mentions of [P0] don't
inflate the queue depth. Token-cheap: <2KB stderr emission.
"""
from __future__ import annotations
import os, sys, re
from pathlib import Path

if os.environ.get("COURTVISION_BOT_MODE") != "1":
    sys.exit(0)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _state import ROOT, read_json_safe, spend_path, SPEND_DEFAULT  # noqa: E402

QUEUE = ROOT / ".planning" / "queue"
HEADER_RE = re.compile(r"^##\s+\[P([012])\]\s")

spend = read_json_safe(spend_path(), SPEND_DEFAULT)


def count_pri(path: Path) -> tuple[int, int, int]:
    if not path.exists(): return 0, 0, 0
    c = [0, 0, 0]
    for line in path.read_text(encoding="utf-8").splitlines():
        m = HEADER_RE.match(line)
        if m: c[int(m.group(1))] += 1
    return c[0], c[1], c[2]


def real_items(path: Path) -> int:
    if not path.exists(): return 0
    skip = ("[PRIORITY]", "YYYY-MM-DD", "[category]")
    return sum(
        1 for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.startswith("## ") and not any(m in ln for m in skip)
    )


p0, p1, p2 = count_pri(QUEUE / "ai-todo.md")
review = real_items(QUEUE / "for-review.md")
human = real_items(QUEUE / "human-todo.md")

print(
    f"[bot-session] queue: P0={p0} P1={p1} P2={p2} | "
    f"review={review} human_todo={human} | "
    f"spent_today=${spend.get('usd', 0):.2f}/$15 "
    f"(in={spend.get('input_tokens', 0):,} out={spend.get('output_tokens', 0):,})",
    file=sys.stderr,
)

if spend.get("usd", 0) >= 15.0:
    print("[bot-session] DAILY CAP REACHED — bot must exit, not start new tasks", file=sys.stderr)
elif spend.get("usd", 0) >= 12.0:
    print(f"[bot-session] WARN: ${spend['usd']:.2f}/$15 — ≤1 heavy task remaining", file=sys.stderr)
