"""Live ticker for your PERSONAL terminal — tails the bot's heartbeat file.

Usage from your normal terminal (not bot account):
    python scripts/bot_guards/watch.py

Refreshes every 5 sec. Ctrl+C to stop watching (does NOT stop the bot).
"""
from __future__ import annotations
import json, os, sys, time, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / ".bot_state" / "live_status.json"
SPEND = ROOT / ".bot_state"

def fmt_ago(iso_ts: str | None) -> str:
    if not iso_ts: return "—"
    try:
        t = dt.datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        delta = dt.datetime.now(t.tzinfo) - t
        s = int(delta.total_seconds())
        if s < 60: return f"{s}s ago"
        if s < 3600: return f"{s//60}m ago"
        return f"{s//3600}h{(s%3600)//60}m ago"
    except Exception:
        return iso_ts

def render(status: dict, spend: dict) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append(f"  COURTVISION BOT  ·  {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 72)
    phase = status.get("phase", "?")
    started = status.get("started_at")
    lines.append(f"  Phase:       {phase}")
    lines.append(f"  Started:     {fmt_ago(started)}")
    lines.append(f"  Tasks done:  {status.get('tasks_completed_today', 0)} today")
    lines.append(f"  Last commit: {status.get('last_commit', '—')[:12]}")
    lines.append("")
    cur = status.get("current_task")
    if cur:
        lines.append(f"  Now working: {cur.get('slug', '?')}")
        lines.append(f"    files:     {', '.join(cur.get('files', [])[:3])}")
        lines.append(f"    started:   {fmt_ago(cur.get('started_at'))}")
    else:
        wake = status.get("next_wake_at")
        lines.append(f"  Idle. Next wake: {fmt_ago(wake)}")
    lines.append("")
    q = status.get("queue_depth", {})
    lines.append(f"  Queue:  P0={q.get('p0', 0)}  P1={q.get('p1', 0)}  P2={q.get('p2', 0)}")
    lines.append(f"  Review pile: {status.get('review_pending', 0)}   Human-todo: {status.get('human_todo', 0)}")
    lines.append("")
    usd = spend.get("usd", 0)
    pct = min(100, (usd / 15.0) * 100)
    bar = "#" * int(pct / 4) + "-" * (25 - int(pct / 4))
    lines.append(f"  Spend today: [{bar}] ${usd:.2f}/$15  ({pct:.0f}%)")
    in_tok = spend.get("input_tokens", 0)
    out_tok = spend.get("output_tokens", 0)
    lines.append(f"  Tokens:      in {in_tok:,} · out {out_tok:,}")
    lines.append("")
    if status.get("stop_requested"):
        lines.append("  >>> STOP REQUESTED — bot will exit after current task <<<")
    elif phase in ("cap_reached", "queue_empty", "review_pile_full", "needs_human"):
        lines.append(f"  >>> BOT STOPPED ({phase}) <<<")
    lines.append("=" * 72)
    return "\n".join(lines)

def clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")

def main() -> None:
    while True:
        try:
            status = json.loads(STATUS.read_text()) if STATUS.exists() else {"phase": "not started"}
            today = dt.date.today().isoformat()
            spend_f = SPEND / f"spend_{today}.json"
            spend = json.loads(spend_f.read_text()) if spend_f.exists() else {}
            clear()
            print(render(status, spend))
            print("  (refresh 5s · Ctrl+C to stop watching · bot keeps running)")
            time.sleep(5)
        except KeyboardInterrupt:
            print("\n[watch] stopped. Bot still running.")
            sys.exit(0)
        except Exception as e:
            print(f"[watch error] {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
