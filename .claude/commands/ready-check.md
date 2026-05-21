# Ready Check — Verify Everything Before "bot go"

Quick health check for the workday loop. Reports green/red. Runs on the personal account.

---

Run these in parallel:

```bash
python scripts/bot_guards/queue_status.py
python scripts/bot_guards/spend_today.py
git status --short
git branch --show-current
git branch --list "bot/*"
python -m pytest tests/ -q --co 2>&1 | tail -3
conda info --envs | grep basketball_ai
```

---

Print a single summary table:

| Check | Status | Notes |
|-------|--------|-------|
| Queue has P0/P1 work | ✅/❌ | <counts> |
| Usage this week | ℹ️ | <runs / tokens this week — informational, no cap> |
| On master | ✅/❌ | <branch> |
| No orphan `bot/*` branch | ✅/❌ | <branches or "none"> |
| Tests collect | ✅/❌ | <N tests found> |
| Conda env present | ✅/❌ | <env path> |

A dirty working tree is **not** a failure — untracked bot-rig files are expected.

**All green → say `bot go`.**
**Any red → fix that first, do NOT start the loop.**

On all-green, touch the marker so `/start-day` skips its overlapping checks:
```bash
python -c "from pathlib import Path; Path('.bot_state').mkdir(exist_ok=True); Path('.bot_state/ready_check_ok').touch()"
```
