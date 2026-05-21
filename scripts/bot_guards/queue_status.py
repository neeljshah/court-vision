"""Quick status of all queues — invoked from VS Code task."""
from __future__ import annotations
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / ".planning" / "queue"

SKIP_MARKERS = ("[PRIORITY]", "YYYY-MM-DD", "[category]")


def is_template(line: str) -> bool:
    return any(m in line for m in SKIP_MARKERS)


def show(name: str, marker: str = "## ") -> None:
    p = QUEUE / name
    if not p.exists():
        print(f"  {name}: (not found)")
        return
    items = [
        ln.strip()
        for ln in p.read_text(encoding="utf-8").splitlines()
        if ln.startswith(marker) and not is_template(ln)
    ]
    print(f"\n{name} ({len(items)} real items):")
    for it in items[:10]:
        print(f"  {it}")
    if len(items) > 10:
        print(f"  ... +{len(items) - 10} more")


print("=" * 60)
print("Bot Queue Status")
print("=" * 60)
show("ai-todo.md")
show("for-review.md")
show("human-todo.md")
show("done.md")
