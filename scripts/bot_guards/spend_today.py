"""Show bot usage — today + this week. Telemetry only; flat Max plan, no cap."""
from __future__ import annotations
import sys, datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _state import read_json_safe, spend_path, SPEND_DEFAULT, week_usage  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

today = dt.date.today().isoformat()
s = read_json_safe(spend_path(today), SPEND_DEFAULT)
wk = week_usage()

print(f"=== Bot Usage ({today}) — flat Max plan, no cap ===")
print(f"  Today:  {s.get('runs', 0)} runs | "
      f"{s.get('input_tokens', 0):,} in / {s.get('output_tokens', 0):,} out | "
      f"~${s.get('usd', 0):.2f} est")
print(f"  7-day:  {wk['runs']} runs over {wk['days']} day(s) | "
      f"{wk['input_tokens']:,} in / {wk['output_tokens']:,} out | ~${wk['usd']:.2f} est")
print(f"  Last task:   {s.get('last_task', '-')}")
print(f"  Last update: {s.get('last_update', '-')}")
