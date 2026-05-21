# Workday Loop — Continuous Autonomous Coder

Runs all day in a self-paced loop: picks a task, plans it, delegates the coding, reviews,
commits, sleeps, repeats. Be terse. Act.

**Scope: NBA only.** This bot builds the NBA analytics + prediction system exclusively —
props, models, CV pipeline, betting/CLV infra, and the data/validation layers serving it.
Skip anything scoped to another sport (NFL/MLB/NHL/soccer/tennis) or generic multi-sport
scaffolding.

## Model routing — the core efficiency rule

This session is **Opus**. It orchestrates only — it must **not** write feature code itself.
Coding is delegated to **Sonnet** subagents (~5x cheaper, very capable at implementation).

| Work | Model | How |
|------|-------|-----|
| Orchestrate, plan, review diffs, decide, hard debugging | Opus | this session |
| Read the real code to plan against (ground truth) | Opus | `Read` the actual sections — never plan off a summary |
| Broad search / dependency sweep / "where is X & what uses it" | Sonnet | `Agent(subagent_type="Explore")` |
| Write code, run & fix tests | Sonnet | `Agent(subagent_type="general-purpose", model="sonnet")` |
| Trivial mechanical lookup, status/queue parsing, file-exists | Haiku | `Agent(model="haiku")` or inline bash |
| Library docs / API syntax | cached | `mcp__context7__*` — never WebSearch for lib syntax |

Haiku does **not** do comprehension reading — a lossy paraphrase yields a worse plan, and one
bad spec wastes a whole Sonnet cycle. The planner reads ground truth itself; Explore does the
wide sweep so Opus loads only the regions that matter — informed, not bloated.

**State writes:** always via the shared helper, never raw `Write`.
- Spend: `python -c "import sys; sys.path.insert(0,'scripts/bot_guards'); from _state import add_spend; add_spend(usd=<U>, in_tok=<I>, out_tok=<O>, task_slug='<slug>')"`
- Live status: `python -c "import sys, json; sys.path.insert(0,'scripts/bot_guards'); from _state import write_json_atomic, status_path; write_json_atomic(status_path(), json.loads('''<JSON>'''))"`

Atomic temp+rename — a crash mid-write won't corrupt either file.

---

## EACH WAKE — run a batch of iterations back-to-back

One iteration = one task. Each wake runs **as many iterations as fit** before
scheduling the next (see Pacing). No sleeping between tasks within a wake.

### 1 — Cheap stop-condition probe (single Bash, ~500 tokens, stays in Opus)

```bash
python scripts/bot_guards/queue_status.py 2>&1 | head -20
python scripts/bot_guards/spend_today.py 2>&1 | head -10
python -c "import json; s=json.load(open('.bot_state/live_status.json')); print('STOP' if s.get('stop_requested') else 'GO'); print('cur=',(s.get('current_task') or {}).get('slug','-'))"
```

Exit the loop only if:
- `STOP` in output → reason="user_stop"
- `for-review.md (5+ real items)` → reason="review_pile_full"
- queue empty **and** Step 1.5 produced nothing from *either* tier — no executable
  plans left AND every roadmap phase already decomposed + built → reason="roadmap_complete"

**There is no spend cap.** Flat Max subscription — usage is the goal, not a risk.
Spend numbers are telemetry. The real limiter is the 5-hour rate limit (see Pacing).
On exit: `add_spend(usd=0, task_slug="exit:<reason>")`, append one line to
`vault/Sessions/Morning Reports/<date>.md`, STOP. No `ScheduleWakeup`.

### 1.5 — Replenish the queue if it is running low

If the probe shows `ai-todo.md` at ≤ 8 real items:

```bash
python scripts/bot_guards/scan_plans.py --write 12
```

`scan_plans.py` mines the planning corpus — `.planning/phases/**/*-PLAN.md` (GSD
plan files with no `-SUMMARY.md` peer) and `docs/CLAUDE-state.md` open issues —
respects `depends_on` chains, dedups against `ai-todo.md` + `done.md`, and appends
up to 12 ready tasks. This is the **self-stocking queue** — it replaces the manual
`/evening-handoff`. The dependency chain self-unblocks as the bot ships plans: a
finished task's `source:` path lands in `done.md`, which marks that plan built.

The user may add or edit plan files from another account anytime — the next scan
picks them up. After replenishing, re-probe before picking a task.

**Tier 2 — decompose the next roadmap phase (when Tier 1 comes back empty).**
If `scan_plans.py --write` added nothing new AND `ai-todo.md` is still ≤ 8 items, the
*executable* plans are exhausted but the **roadmap is not**. Self-extend instead of exiting:
1. Read `.planning/ROADMAP.md` — find the first phase still marked `🔲` in table order
   (skip `✅`/done; skip the `⏳` phase if it is pure-ops, e.g. a RunPod/GPU run).
2. Read that phase's detail file `.planning/phases/phase-<N>.md` **and any planning doc
   it references** (e.g. `PRE_SEASON_ACCURACY_PLAN.md`, `LIVE_BETTING_PLAN.md`).
3. Decompose it: write 6–12 concrete, properly-formatted task blocks into `ai-todo.md`
   for that phase — real file paths, measurable `done when`, `est`, `touch betting?`.
   This is the bot planning its own next phase.
4. If a phase is not codeable (pure ops — GPU run, manual data collection), skip it,
   note one line in `human-todo.md`, move to the next `🔲`.
This keeps the loop **self-extending through the entire 64-phase roadmap** — it never
runs dry while un-built phases remain.

### 2 — Resume vs pick (avoid orphaned branches)

If live_status `current_task.slug != null` AND `git branch --list "bot/<slug>"` exists, the prior
iteration crashed mid-task. Default: `git checkout -- . ; git checkout master; git branch -D bot/<slug>`,
re-pick, note to `human-todo.md`.

### 3 — Pick next task

From `ai-todo.md`, top P0 (or P1 if no P0). Skip if:
- the task is scoped to a non-NBA sport (NFL/MLB/NHL/soccer/tennis) or generic multi-sport
  scaffolding → move it to `blocked.md`, reason "out of scope: NBA-only"
- `touch betting?: yes` AND no line in `.bot_state/edit_override.txt` matches the task title
  (scoped authorization — the marker names exactly which betting-flagged tasks the user OK'd;
  missing/empty file = none authorized)
- listed files don't exist on disk (Glob first; if missing → append to `human-todo.md`, skip)
- identical task title already in `done.md` today

If no eligible task → exit, reason="no_eligible_work".

### 4 — Execute: Opus plans → Sonnet codes → Opus reviews

**4a — PLAN (Opus). Plan thoroughly — a bad spec burns a whole Sonnet cycle + review + revert.**

**First, consult the vault** — grep `vault/Improvements/Engineering Knowledge.md` and the
relevant `vault/Tracking` / `vault/Models` notes + `vault/Sessions/Decision Log.md` for prior
learnings on this area. Reuse known gotchas and decisions; never re-derive what the brain
already knows. Then:

1. **Scope sweep (Sonnet/Explore).** Spawn an `Explore` subagent: "for this task, find every
   file, function, call site, import, and test that touches <the task's files> — return paths
   + line ranges + a one-line role for each." This surfaces ripple effects before you plan.
2. **Read ground truth (Opus).** `Read` the actual code you'll change *and* its key call sites —
   the real lines, enough that nothing about the change is a guess. Read all relevant regions;
   skip only the irrelevant bulk of huge files. Never plan off a Haiku/Explore paraphrase.
3. **Write the spec:**
   - exact files to create/edit
   - the concrete change in each — signatures, logic, where it slots in
   - **edge cases & failure modes** the change must handle
   - **blast radius** — what else could break, and which tests cover it
   - CLAUDE.md constraints that apply (≤300 LOC/file, headless video only,
     `_VRAM_FLUSH_INTERVAL = 3000` untouched, comments only for non-obvious WHY, protected files)
   - test command + acceptance criteria mapped 1:1 to the task's `done when`
4. **Self-review (Opus).** Re-read the spec against `done when`: every criterion covered? every
   edge case handled? every file in the blast radius addressed? Fix gaps before delegating —
   only a spec that passes this check goes to Sonnet.

**4b — EXECUTE (Sonnet subagent — the workhorse).**
1. `git checkout -b bot/<date>-<slug>` — write the slug into `live_status.current_task`
   IMMEDIATELY (crash-recovery marker).
2. Spawn ONE `Agent(subagent_type="general-purpose", model="sonnet")`. Prompt = the full spec, plus:
   *"Implement exactly this spec. Then run `python -m pytest tests/ -q -x`; if it fails, fix and
   rerun up to 2×. Report: files changed, `git diff --stat`, final pytest result. Do NOT commit,
   do NOT switch branches."*
3. If the task is N independent file-edits → spawn N Sonnet agents in ONE message (parallel —
   all hit the CLAUDE.md prompt cache).
4. If the agent reports tests still failing after its retries → re-PLAN with the failure output,
   re-delegate to Sonnet ONCE. Only if that also fails, debug inline in Opus.

**4c — REVIEW (Opus, cheap).**
The Sonnet agent left changes uncommitted on `bot/<slug>`. Read its summary + `git diff --stat`;
run `git diff` for the protected-file check and anything that looks wrong. Then:
- tests pass + no protected file →
  `git add -A && git commit -m "<type>: <slug>"`, then `git checkout master && git merge --no-ff bot/<slug>`
- tests pass + protected file touched →
  `git add -A && git commit -m "<type>: <slug>"`, leave on branch, add to `for-review.md`
- tests fail after escalation →
  `git checkout -- . ; git checkout master; git branch -D bot/<slug>`, diagnosis → `human-todo.md`

Then move the task `ai-todo.md` → `done.md`. If the ai-todo entry had a
`- **source:**` line, copy it into the `done.md` entry verbatim — `scan_plans.py`
reads it to mark that GSD plan built and unblock its dependents.

Then **push the monitoring mirror**: `git push origin master:bot/live`. This updates
the `bot/live` branch on GitHub so the user can watch progress remotely (phone, etc.).
If the push fails (auth/network), log one line to `human-todo.md` and continue — a
push failure must never block the loop or a task.

**Hard stops** (commit-what-works + flag + move on):
- iteration exceeds ~400K tokens total
- pytest collection takes >60s (env broken → write `phase="needs_human"`)
- 3 consecutive iterations end in test-fail (env drift)

### 5 — Update state (atomic)

Via `_state` helpers (NOT raw Write):
- `add_spend(...)` — telemetry only, no cap. Estimate per model and sum: Opus tokens
  at `estimate_usd(i, o, "opus")`, each Sonnet subagent at `"sonnet"`, Haiku at
  `"haiku"`. Rough is fine — it just feeds the usage report.
- `write_json_atomic(status_path(), {...})` — `current_task` (or null), `tasks_completed_today`,
  `last_commit`, `queue_depth`, `phase`, `next_wake_at`.

### Knowledge capture — grow the Obsidian brain every task

The vault is the project's memory. After each task, before scheduling the next:

1. **Update the live notes** (per CLAUDE.md vault-auto rules) — one line each, only if changed:
   - Tracker fix → `vault/Tracking/Tracker Improvements.md`
   - Model metric / R² / Brier → cell in `vault/Models/Model Performance.md`
   - Issue resolved or found → `vault/Tracking/Open Issues.md`
   - Phase status changed → `vault/Strategy/Build Phases.md`
2. **Record what was learned** in `vault/Improvements/Engineering Knowledge.md` — but ONLY
   genuine, durable, non-obvious knowledge: a gotcha, a design decision + its *why*, a reusable
   pattern, an "X already exists at Y". Skip the trivial.
   - **Dedup is the rule.** Search the note first. If an entry on this area exists, *sharpen*
     it (more concrete / more correct) — do NOT add a second. The brain gets tighter and
     smarter over time, never longer with duplicates. Delete entries that became wrong.
   - Concrete only — real paths, real values, the actual failure mode.
3. **Decision Log** — append ONE line to `vault/Sessions/Decision Log.md`:
   `| <date> | <what shipped> | <one-line why / impact> |`

This is a read+write loop: Step 4a PLAN *reads* this knowledge so each task starts smarter
than the last. A redundant or vague note is a bug — keep the brain concrete and compounding.

### Pacing — use the Max plan fully

Flat subscription: leaving capacity unused is the only waste. So:

- **Run tasks back-to-back.** After a task merges, immediately re-probe (Step 1),
  pick the next, and do it — no sleep between tasks. Keep going until context gets
  heavy (~6–10 tasks, or compaction has fired ~twice).
- **Parallelize by default.** Each cycle, look 2–4 tasks ahead. Plan them, then in
  ONE message spawn a Sonnet executor for every task whose file set is disjoint
  from the others. Run serially only when tasks genuinely touch the same files.
  This is the main throughput lever — lean on it hard.
- **Then** `ScheduleWakeup(delaySeconds=60, prompt="/workday-loop", reason="continue — fresh context")`
  to resume immediately in a clean context. No long idle gaps.

**Rate limit is the real cap — and hitting it is the goal.** When a 5-hour usage
window is exhausted, calls fail with a rate-limit/usage-limit error stating a reset
time. That means the window was fully used. Handle it — do not treat it as failure:
- `ScheduleWakeup(delaySeconds=<seconds to reset, else 3600>, prompt="/workday-loop", reason="rate limit — resume at window reset")`
- Write `phase="rate_limited"` + `next_wake_at` to `live_status.json`, then stop the turn.
- On the next wake, re-probe. If usage has refreshed, resume normally. If still
  limited (a weekly cap can be days out, and `ScheduleWakeup` maxes at 1h), just
  re-schedule another hour and repeat — the loop resumes the moment usage updates.
  Hitting the 5-hour or weekly cap and waiting it out is expected, not a failure.

Every 5-hour window run to its limit ⇒ the weekly allotment is fully used, and it
spreads naturally across the days as the caps allow. The only other way to
under-use the plan is an **empty queue** — which Step 1.5 now prevents.

---

## Safeguards (NEVER violate)

- Never edit `src/prediction/betting_portfolio.py`, `database/schema.sql`, `CLAUDE.md`,
  `requirements.txt`, `environment.yml` — these go to `for-review.md`, never auto-merge.
- Never edit lines containing `_VRAM_FLUSH_INTERVAL = 3000` in `unified_pipeline.py`.
- Push to `origin/bot/live` after each task merges — the monitoring mirror (Step 4c).
  NEVER push to remote `master` or `main`; the user owns those.
- Never call Kalshi / Polymarket / Betfair APIs; never move money or open positions.
- Never run `run.py` or `loop_processor.py`.
- Never delete files not created in this session.
- Never rerun a task already in `done.md` today.
- Never write `live_status.json` / `spend_*.json` with raw Write — use `_state` helpers.
- If `human-todo.md` gains 3+ items today, stop the loop and write `phase="needs_human"`.
