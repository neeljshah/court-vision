# Start Day — "bot go"

The user said **bot go** (or `go` / `start`).

The autonomous bot runs as a **Windows scheduled task** (`CourtVisionBot`) that fires a
fresh headless Claude Code cycle every 15 minutes. Each cycle runs `/workday-loop`, ships
a batch of work, and exits. `bot go` simply turns that task **ON**.

## Do exactly this, then stop. Be terse.

1. Run: `python scripts/bot_guards/bot_go.py`
2. Relay its output to the user in 1–2 lines — confirm the bot is ON, runs every 15 min
   hands-off, and stops with `bot stop`.

## Do NOT

- Do NOT run `/workday-loop` in this session. The scheduled task's own headless cycles
  run the loop. This interactive session's only job is to flip the task on.
- Do NOT `ScheduleWakeup` or create crons — the Windows scheduled task is the driver now.

`bot stop` → `python scripts/bot_guards/stop_bot.py` (disables the task; bot fully off).
