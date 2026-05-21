"""Stop hook — write spend, snapshot live_status, log one useful line to Decision Log.

Pulls token usage from the Stop hook payload when available (Claude Code passes
session metadata on stdin). Falls back to a runs-counter increment if not.
"""
from __future__ import annotations
import json, os, sys, datetime as dt
from pathlib import Path

if os.environ.get("COURTVISION_BOT_MODE") != "1":
    sys.exit(0)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _state import (  # noqa: E402
    ROOT, STATE, add_spend, estimate_usd, read_json_safe, status_path,
)

try:
    payload = json.load(sys.stdin)
except Exception:
    payload = {}

usage = payload.get("usage") or payload.get("session_usage") or {}
in_tok = int(usage.get("input_tokens", 0) or 0)
out_tok = int(usage.get("output_tokens", 0) or 0)
usd_reported = usage.get("total_cost_usd")
usd = float(usd_reported) if usd_reported is not None else estimate_usd(in_tok, out_tok)

status = read_json_safe(status_path(), {})
cur = status.get("current_task") or {}
slug = cur.get("slug") or status.get("last_task") or "—"
phase = status.get("phase", "?")
commit = (status.get("last_commit") or "")[:12]
tasks_done = status.get("tasks_completed_today", 0)

spend = add_spend(usd=usd, in_tok=in_tok, out_tok=out_tok, task_slug=slug)

log = ROOT / "vault" / "Sessions" / "Decision Log.md"
if log.parent.exists():
    log.parent.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    line = (f"\n{ts} bot · phase={phase} · task={slug} · "
            f"done={tasks_done} · commit={commit or '—'} · "
            f"+${usd:.3f} (today=${spend['usd']:.2f}/$15)\n")
    with log.open("a", encoding="utf-8") as f:
        f.write(line)
