# "bot go" — run a work burst

The user said **bot go** (or `go` / `start`). This is a **poke**: run one autonomous
work burst, then stop. There is no scheduled task and no auto-restart — those do not
work in this environment. The model is poke-to-run: the user pokes, the bot ships a
burst, the user pokes again when they want more.

## Do this

Execute `/workday-loop` — read `.claude/commands/workday-loop.md` and follow it:

1. Probe the queue (`.planning/queue/ai-todo.md`).
2. If the queue is low, replenish: `python scripts/bot_guards/scan_plans.py --write 12`,
   and if that adds little, decompose the next `🔲` roadmap phase from
   `.planning/ROADMAP.md` into fresh task blocks (Tier 2 — the queue never runs dry
   while roadmap phases remain).
3. Build a batch — Opus plans, Sonnet subagents code in parallel, review, merge, push.
4. Run batches back-to-back until context gets heavy (~6-10 tasks), then report what
   shipped in a short summary and STOP. Do not ScheduleWakeup, do not create crons.

One poke = one burst. That is the whole job.
