# Start Day — "bot go" Trigger

The user said **bot go** (or `go` / `start`). Boot the autonomous workday loop **on this account**.
Be terse. No preamble.

---

## Account model — read once

- Runs on the user's **personal Max account** — the same account this session is using.
  No separate bot account, no `CLAUDE_CONFIG_DIR`, no `Start-Bot.bat`.
- **Opus orchestrates** (plans, reviews, decides). **Sonnet writes the code** via subagents.
  Explore/Haiku handle search. See `/workday-loop` for the routing table.
- **No spend cap.** Flat Max subscription — the goal is to *use* it. The loop runs
  continuously and rides the 5-hour rate limit, resuming after each reset. Spend
  numbers are telemetry only.

---

## PHASE 0 — Sanity gate (skip if ready-check just passed)

If `.bot_state/ready_check_ok` exists AND is <120s old, skip this phase.

Otherwise, ONE bash call:

```bash
python scripts/bot_guards/queue_status.py 2>&1 | grep -E 'ai-todo|for-review'
python scripts/bot_guards/spend_today.py 2>&1 | tail -3
git branch --show-current
git branch --list "bot/*"
```

Proceed only if:
- branch = `master`

If `ai-todo.md` has < 5 real items, top it up first:
`python scripts/bot_guards/scan_plans.py --write 12` (auto-discovers tasks from the
GSD plan corpus). Only abort if that *still* leaves the queue empty.

(No spend gate — flat Max plan, no cap. `spend_today.py` output is informational only.)

Notes:
- A **dirty working tree is fine** — untracked bot-rig files are expected, not a blocker.
- If a `bot/*` branch exists, the previous loop crashed mid-task — `/workday-loop` Step 2 resolves it.
- If queue empty or spend capped: print one line, exit, do **not** start the loop.

---

## PHASE 1 — Boot live status file (atomic)

Use the helper, NOT raw Write:

```bash
python -c "import sys, json, datetime as dt, subprocess; \
sys.path.insert(0,'scripts/bot_guards'); \
from _state import write_json_atomic, status_path; \
sha = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(); \
write_json_atomic(status_path(), { \
  'started_at': dt.datetime.now().isoformat(timespec='seconds'), \
  'phase': 'starting', 'current_task': None, 'tasks_completed_today': 0, \
  'last_commit': sha, 'next_wake_at': None, 'stop_requested': False, \
})"
```

This file is the bot's heartbeat — `python scripts/bot_guards/watch.py` tails it.

---

## PHASE 2 — Kick the workday loop

Report to the user, one line:
`Bot running on this account — Opus plans, Sonnet codes. Tail: python scripts/bot_guards/watch.py · stop: bot stop`

Then execute `/workday-loop` (read `.claude/commands/workday-loop.md` and follow it):
1. Pick next task from queue (P0 first)
2. PLAN in Opus → delegate coding to a Sonnet subagent → REVIEW in Opus
3. Update `live_status.json`
4. Self-pace with `ScheduleWakeup` between tasks
5. Continue until: queue empty | spend cap | `stop_requested=true` | review pile ≥ 5
