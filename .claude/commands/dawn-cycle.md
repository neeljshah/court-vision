# Dawn Cycle — Autonomous Morning Build

Run by `/schedule` at 7am daily. Picks ONE task from the queue, executes it well, commits, reports.
Be terse. Act. No preamble.

---

## PHASE 0 — Usage check (informational, no gate)

```bash
python scripts/bot_guards/spend_today.py
```

No budget gate — flat Max subscription, usage is the goal. The only things that stop
a run are a rate limit (resume past the stated reset) or an empty queue. Continue to Phase 1.

---

## PHASE 1 — Triage (read-only, ~5K tokens)

Read these in parallel:
- `.planning/queue/ai-todo.md` — find first P0 (or P1 if no P0)
- `.planning/queue/for-review.md` — count pending reviews
- `vault/Sessions/Decision Log.md` — last 3 entries
- `git status` and `git log --oneline -5`

**Smart usage rule**: this phase MUST stay under 10K tokens. If a file is >500 lines, read only the relevant section (e.g., `offset:` to last 100 lines of decision log). Do NOT read ROADMAP.md, full vault notes, or large code files here.

**Skip-day conditions** (write a 1-line report, exit):
- 5+ items already in `for-review.md` (don't pile up work the human can't review)
- Working tree dirty with uncommitted human changes
- Active branch is `bot/*` not yet merged

---

## PHASE 2 — Pick ONE task

From `ai-todo.md`, pick top task by priority. Reject if:
- `touch betting?: yes` AND no explicit human approval comment
- Estimate is L AND `for-review.md` has 3+ pending (don't queue more L work)
- Files listed don't exist (stale task — append to `human-todo.md` for clarification)

If no eligible task: run `/pipeline-loop` instead (always-useful default — improve tracker, log metrics).

---

## PHASE 3 — Execute (smart model routing)

**Model routing — Opus plans, Sonnet codes:**
This session is Opus — it plans and reviews only, never writes feature code.
- "Where is X defined?" / codebase search → `Agent(subagent_type="Explore")` (Sonnet, cheap).
- Library docs → `mcp__context7__*` (cached). Never WebSearch for Python lib syntax.
- Writing the code → an `Agent(subagent_type="general-purpose", model="sonnet")` subagent.
- Reading a known file to plan → Read with `offset/limit`, relevant section only.

Then:

1. **PLAN (Opus) — thorough:** (a) spawn an `Explore` subagent to map every file/call-site/test
   that touches the task's files; (b) `Read` the real code sections you'll change — ground
   truth, not a summary; (c) write the spec — exact changes, edge cases, blast radius, CLAUDE.md
   constraints (300 LOC/file, headless video, `_VRAM_FLUSH_INTERVAL = 3000` untouched), test
   command + acceptance criteria; (d) self-review the spec against the task's `done when` before
   delegating.
2. `git checkout -b bot/$(date +%Y-%m-%d)-$SLUG`
3. **EXECUTE (Sonnet):** spawn `Agent(general-purpose, model="sonnet")` with the full spec plus
   "implement exactly; run `python -m pytest tests/ -q -x`; fix failures, retry ≤2×; report
   files changed + `git diff --stat` + pytest result; do not commit." Independent edits → parallel agents.
4. **REVIEW (Opus):** read the agent summary + `git diff --stat`; `git diff` the protected-file check.
5. Tests pass + no protected file → commit + merge to master.
6. Tests pass + protected file (betting_portfolio.py / schema.sql / CLAUDE.md / requirements) →
   commit on branch, add to `for-review.md`.
7. Tests fail after one Sonnet re-try → revert branch, log diagnosis to `human-todo.md`.

**Hard stop:** if the task balloons past 1.5x estimate, commit what works on branch, flag for review, stop.

**Parallelization rule**: if the task naturally splits into N independent pieces (e.g., add 3 features to 3 separate files), spawn N subagents in a single message instead of doing serially. Each runs with full context cache hit on CLAUDE.md.

---

## PHASE 4 — Vault updates

Per CLAUDE.md vault-auto-maintenance rules. Only if relevant:
- Tracker fix → append one line to `vault/Tracking/Tracker Improvements.md`
- Model metric change → update the cell in `vault/Models/Model Performance.md`
- Issue resolved → flip status in `vault/Tracking/Open Issues.md`
- New signal wired → row in `vault/Features/Signal Inventory.md`

One line per update. No essays.

---

## PHASE 5 — Morning report

Write `vault/Sessions/Morning Reports/$(date +%Y-%m-%d).md`:

```markdown
# Dawn Cycle — YYYY-MM-DD

## Task
- **picked:** <slug from ai-todo>
- **outcome:** ✅ merged to master | 🟡 on branch, needs review | ❌ reverted
- **branch/commit:** <ref>
- **files:** <list>
- **tokens:** ~X (est was Y)

## Tests
- pytest: ✅/❌
- regression check: <key metric before → after>

## Vault touched
- <list of notes updated, one bullet each>

## Queue state
- ai-todo: N P0, N P1, N P2
- for-review: N pending
- human-todo: N pending (new today: M)

## Flagged for you
- <bullets — what needs YOUR eyes/hands today>

## Recommended next human move
- <one specific sentence — what unblocks the most>
```

---

## PHASE 6 — Decision log + spend tracking

Append to `vault/Sessions/Decision Log.md`:
```
YYYY-MM-DD dawn-cycle · <task slug> · <outcome> · next: <slug or "queue empty">
```

Update spend file (rough estimate — bot uses Anthropic usage if available, else token count × $15/M):
```bash
echo "$ESTIMATED_USD" > "$SPEND_FILE"
```

---

## Safeguards (NEVER violate)

- **Never** edit `src/prediction/betting_portfolio.py` without review flag
- **Never** modify `data/models/*.pkl` without human approval in task
- **Never** run `run.py` or `loop_processor.py` (per CLAUDE.md)
- **Never** push to remote (human pushes after review)
- **Never** delete files not created in this session
- **Never** rerun a task already marked done or reverted today
- **Never** create new top-level docs (CLAUDE.md says no md files unless asked)
- **Never** open positions, move money, or call trading APIs (no real $ in autonomous mode)
