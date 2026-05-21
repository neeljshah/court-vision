# Evening Handoff — Queue Tomorrow's Bot Work

Run this in the evening to (1) review what the bot did today, (2) queue tomorrow's work cleanly. ~5 min of your time.

---

## PHASE 1 — Review today's bot output

Show me in parallel:
- `vault/Sessions/Morning Reports/$(date +%Y-%m-%d).md` (today's report)
- `.planning/queue/for-review.md` (anything I need to approve)
- `git log --oneline --since=midnight` (commits today)
- `git branch --list "bot/*"` (open bot branches)

For each bot branch awaiting review, run:
```bash
git diff master..<branch> --stat
```

Print a summary table:

| Branch | Files | +/- | Tests | Why flagged | Recommend |
|--------|-------|-----|-------|-------------|-----------|
| ...    |       |     |       |             | merge / kill / read closer |

---

## PHASE 2 — Drain human-todo

Show `.planning/queue/human-todo.md`. For each item, ask me:
- **do now** (5-min item — I'll knock it out)
- **schedule** (today, this week) — add a date
- **defer** (move to bottom of list)
- **kill** (no longer relevant — delete)

---

## PHASE 3 — Queue tomorrow's tasks

Ask me: "What should the bot work on tomorrow?"

For each task I name, write it into `.planning/queue/ai-todo.md` in the right format:
- Pick priority (P0/P1/P2) based on what I say
- Locate the exact files myself (don't make me name paths)
- Estimate token size based on scope
- Set `touch betting?: yes` only if the task hits betting_portfolio.py or model weights

**Cap at 3 P0 tasks total in the queue.** If I try to add a 4th, push back: "Queue has 3 P0s already — is this really more urgent than X?"

---

## PHASE 4 — Sanity checks

- `pytest tests/ -q` — make sure trunk is green before bot wakes
- `git status` — no uncommitted human work (bot will skip if dirty)
- Show me budget: tokens used this week vs Max plan cap

---

## PHASE 5 — Confirm tomorrow's run

```
Bot will run tomorrow at 7am:
  - Task: <top of queue>
  - Est tokens: <S/M/L>
  - Will commit to: branch (review needed) | master (auto-merge eligible)
  - Daily cap: $15
  - Skip conditions active: <list>

Ready? (y/n)
```

If I say no, ask what to change. If yes, exit clean.
