# 07 - State Single-Source Design: Stop the Re-Derivation Spin

READ-ONLY audit + design. ASCII-only. Date: 2026-06-17.

Problem statement (user's words): "Claude reiterates too much and isn't moving
forward." This document diagnoses WHY, then designs a single, lightweight,
authoritative STATE + NEXT-ACTIONS source of truth that makes progress compound
instead of being re-derived every session.

---

## PART 1 - DIAGNOSIS: why the spinning happens

The spinning is NOT a model-quality problem. It is a STATE-LEGIBILITY problem.
On every fresh context, Claude has to *reconstruct* "what is done / what is next"
from a contradictory, stale, sprawling surface -- and reconstruction is exactly
the "reiteration" the user feels. Six concrete root causes, all evidenced below.

### Root cause 1 - There is no single authoritative "what's done / what's next"

There are at least FOUR files that each claim to be the current state, and they
disagree on date, phase, and next action:

| File | mtime | "Current" date it asserts | What it says is NEXT |
|------|-------|---------------------------|----------------------|
| `.planning/STATE.md` (GSD canonical) | 2026-05-21 | 2026-05-21 | "Phase 14 - 100-game RunPod Run" |
| `docs/CLAUDE-state.md` (onboarding) | 2026-06-07 | 2026-05-27 | "calibration pass after PTS/REB UNDER" |
| `docs/ROADMAP.md` | 2026-05-25 | 2026-05-25 | "Gate 1 CLV validation NOT YET RUN - top priority" |
| `MASTER_PLAN.md` (repo root) | 2026-06-15 | 2026-06-15 | platform/kernel build |

Meanwhile the ACTUAL frontier (git HEAD + auto-memory) is 2026-06-16/17
`pm_trading` (prediction-market paper trader). NONE of the four state files
mentions it. A cold Claude reading any one of them is immediately 3-4 weeks and
an entire project pivot behind reality, and will "helpfully" propose re-doing
Gate 1 or the RunPod run -- work the user has mentally moved past.

### Root cause 2 - Stale roadmaps that were never closed out

- `.planning/STATE.md` frontmatter: `completed_phases: 21 / total 57, 61%`, last
  updated 2026-05-21, almost a month stale. Its body still lists "Known
  blockers: no bet-selector middleware" even though later notes say the selector
  exists.
- `docs/ROADMAP.md` is explicitly labelled "Historical phase log. Last detailed
  update 2026-04-15" yet is still one of the files CLAUDE.md points cold agents
  toward, and it asserts a 2026-05-25 "current state."
- `.planning/ROADMAP.md` is 168 KB. CLAUDE.md itself says "NEVER full-read." A
  state file you are forbidden from reading is not serving as state.

The roadmaps are append-only archives masquerading as live state. Nothing ever
marks the top-line goal as DONE and rotates to the next one, so each session
re-litigates "are we actually past this?"

### Root cause 3 - Catastrophic file sprawl -> no obvious entry point

- `.planning/` contains **394** `.md` files; `docs/` contains **408**.
- Inside `.planning/` alone: `STATE.md`, `ROADMAP.md`, `MASTER_PLAN.md` (also at
  repo root), `PROJECT.md`, `CANONICAL_VALUES.md`, plus ~90 `*-PLAN.md` phase
  files, plus `cycle91_plan.md` / `cycle108_plan.md`, plus 9 subdirectories
  (brain, courtvision, courtvision-odds, courtvision-ui, execution, ingame,
  ingest, intel, intelligence, loop, platform, phases, queue, quick, replay,
  round1, scheme) each with their own roadmap/audit/state docs.
- `docs/` has 9+ overlapping "here is the project" files: `PROJECT_INDEX.md`,
  `JOB_EVIDENCE_PACKET.md`, `HIRE_PACKAGE.md`, `PRODUCT_ONE_PAGER.md`,
  `OUTREACH_KIT.md`, `PREDICTOR_PLATFORM.md`, `PREDICTOR_QUICKSTART.md`,
  `PROOFS.md`, `MARKET_EFFICIENCY_PROOF.md`, plus the state docs above.
- Stale **git worktrees** under `.claude/worktrees/agent-*` each carry their OWN
  copy of `docs/CLAUDE-state.md`, `docs/ROADMAP.md`, `MASTER_PLAN.md`,
  `ROADMAP.md`, and `scripts/execute_loop/STATE_OF_LOOP.md` -- dozens of frozen,
  divergent snapshots that pollute every `find`/grep and invite reading the
  wrong one.

When there is no single obvious entry point, a cold agent fans out, reads a dozen
docs, and synthesizes a fresh summary -- that synthesis IS the reiteration. The
work of re-deriving state crowds out the work of advancing it.

### Root cause 4 - State is scattered across machine-readable silos too

"What is true now" is spread across `.planning/STATE.md` frontmatter,
`scripts/improve_loop/state.json` (ships array), `scripts/coordination_log.md`,
`scripts/daemon_registry.json`, `.planning/loop/ledger.jsonl`, and the auto-memory
`MEMORY.md` index. `docs/CLAUDE-state.md` even ends with a "What to load first
next session" list of SIX files. If onboarding requires reading six files plus an
index, there is no single source of truth -- there are seven, and they drift.

### Root cause 5 - The bot-queue-visibility gap (loop cannot see the plans)

Per the `bot-queue-visibility` memory note: the workday-loop builds its task
queue from EXACTLY two sources -- GSD `.planning/phases/**/*-PLAN.md` files and
`unchecked` phases in `.planning/ROADMAP.md`. Deep-dive docs
(`LIVE_BETTING_PLAN.md`, `DATA_VISION.md`, the entire `docs/research/` tree, the
`PROPOSED-*` org-sprint artifacts) are INVISIBLE to it. So well-specified work
never enters the queue, the loop re-scans the same stale ROADMAP phases, and the
human keeps re-explaining intent that lives in an unread doc. The loop's
intelligence is fine; its INPUT is a stale, narrow slice of the real state.

### Root cause 6 - No write-back discipline -> progress never compounds

There is no rule that finishing work UPDATES one canonical file. STATE.md is
edited by hand, sporadically, and the GSD `status` commands touch yet a different
file. So a completed task leaves its trace in a commit message, maybe a vault
note, maybe `improve_loop/state.json` -- but not in the one place the next
session reads first. Each session therefore starts from a snapshot that is
already wrong and re-derives the delta. That re-derivation, multiplied over
sessions, is the entire felt experience of "reiterates too much, isn't moving
forward."

### One-line root cause

> State is **plural, stale, sprawling, and never written back**, so every session
> re-derives "where are we / what's next" from scratch -- and that re-derivation
> is the reiteration the user feels.

---

## PART 2 - DESIGN: ONE authoritative STATE + NEXT-ACTIONS

### Design principles

1. **Exactly one file** is the live state. Everything else is archive, evidence,
   or deep-dive -- explicitly demoted, never "current."
2. **Lightweight and bounded.** Hard cap ~150 lines / ~8 KB. If it grows past
   that, detail moves to archive. A state file you must skim is not state.
3. **Append-thin, rotate-often.** Top of file = NOW (goal + next 1-5 actions +
   recent done). A short rolling log. Old entries rotate OUT to an archive file.
4. **Human-skimmable in 30 seconds AND machine-parseable** (YAML frontmatter +
   fixed headings) so the loop can read it without an LLM pass.
5. **Write-back is a hard rule**, enforced by a Stop hook, not by goodwill.
6. **The loop reads it.** It becomes a queue source, closing the
   bot-queue-visibility gap.

### Where it lives

```
.planning/NOW.md        <- THE single source of truth (live state + next actions)
.planning/DONE.md       <- rolling archive; rotated-out entries land here (append-only)
```

Rationale for `.planning/NOW.md` (not reusing an existing name):
- A NEW, unambiguous name avoids inheriting the four-way contradiction. STATE.md,
  CLAUDE-state.md, ROADMAP.md and MASTER_PLAN.md are all poisoned by being
  "current" in conflicting ways; a clean name forces a clean cutover.
- `.planning/` is already the agreed home for live planning and is gitignored
  (local-only, per the repo rules) -- correct, since live state is maintainer
  working memory, not public/recruiter-facing.
- `NOW.md` is self-describing: its name tells every agent "this and only this is
  now." It sorts to the top of the directory and is trivial to reference in
  CLAUDE.md as the FIRST and ONLY required read.

The existing files are explicitly demoted (see "Cutover" below): they become
archive/evidence and lose all "current state" language.

### Format (the template)

```markdown
---
updated: 2026-06-17           # ISO date; the Stop hook stamps this
north_star: best-predictions  # one-token current mission
active_project: pm_trading    # the ONE thing in flight right now
phase: paper-trader-step-3    # human-readable, NOT a fragile global phase number
loop_queue_source: true       # the workday-loop reads NEXT items below
---

# NOW - single source of truth

> The ONLY live-state file. STATE.md / CLAUDE-state.md / ROADMAP.md / MASTER_PLAN.md
> are ARCHIVE. If they disagree with this file, THIS file wins. Cap ~150 lines.

## North star (1-2 lines)
Best calibrated predictions across NBA/MLB/soccer/tennis; paper-first PM trader.
No edge claims (see docs/JOB_EVIDENCE_PACKET.md). LOCAL commits only.

## Active project: <name>
One paragraph: what it is, why it is the current focus.

## NEXT (1-5 actions, ordered, each one sitting/half-day sized)
- [ ] N1: <action> -- file/area: <path> -- done-when: <observable check>
- [ ] N2: <action> -- ...
- [ ] N3: ...
(<=5 items. If more, they live in a deep-dive doc, linked, NOT here.)

## RECENT DONE (last ~7 entries, newest first; older rotate to DONE.md)
- 2026-06-17 pm_trading status.py honest per-layer accuracy/Brier split (6039ef8d)
- 2026-06-16 pm_trading in-game leak-drop-at-grading fix (16980287)
- ...

## ACTIVE BLOCKERS (only things actually blocking NEXT; else empty)
- (none)

## POINTERS (where detail lives - do NOT inline it here)
- Truth/claims:        docs/JOB_EVIDENCE_PACKET.md
- Deep plan (current): docs/research/pm-trading/...   (or .planning/<area>/...)
- Memory index:        ~/.claude/.../memory/MEMORY.md
- Archived old state:  .planning/DONE.md, docs/_archive/
```

Why this shape:
- **Frontmatter** is the machine-readable contract: the loop reads `phase`,
  `active_project`, and the `NEXT` checkboxes without an LLM pass.
- **NEXT is capped at 5** and each item is action + location + done-when. That is
  exactly what a fresh agent needs to *start moving* instead of re-planning.
- **RECENT DONE is capped at ~7**; overflow rotates to `DONE.md`. This is the
  anti-staleness mechanism: the file physically cannot accrete into a 168 KB
  unreadable log.
- **POINTERS** replaces inlining. The doc never duplicates content that lives
  elsewhere; it links. This kills the "9 overlapping project docs" duplication at
  the state layer -- NOW.md points to the one current deep-dive, not all of them.
- **Phase is a human string, not a global number.** The Phase-14-vs-Phase-33-vs-
  "Phase 16 interim" numbering chaos in today's STATE.md is itself a re-derivation
  trap; a descriptive phase ("paper-trader-step-3") never collides.

### Who updates it, and when (the write-back rule)

Three triggers, in priority order:

1. **End of every unit of work (HARD RULE).** Whoever finishes a NEXT item:
   checks its box, moves it to RECENT DONE with date + commit, and adds the new
   NEXT item(s). This is the single most important habit -- it is what makes
   progress compound. Add to `.claude/rules/` as a binding rule:
   `state-singlesource.md` -- "Before ending any work session you MUST update
   `.planning/NOW.md`: tick/rotate the NEXT item you advanced, add the follow-up,
   bump `updated`. No exceptions."

2. **Automated stamp via the existing Stop hook.** CLAUDE.md already runs
   `scripts/vault_session_close.py` on Stop. Extend it (or add a tiny
   `scripts/now_touch.py`) to: (a) set frontmatter `updated:` to today, (b) verify
   NOW.md was modified this session and emit a one-line WARN to the Decision Log
   if it was not. Hook stamps the date; the human/agent still writes the substance
   -- automation guarantees the file can never silently rot.

3. **Session start reconciliation (CHEAP).** SessionStart hook
   (`update_vault.py`) additionally checks: is `git log -1` newer than NOW.md's
   `updated`? If yes, print a one-line nudge: "NOW.md is behind HEAD -- reconcile
   before planning." This catches the exact failure we have today (HEAD at
   2026-06-17, state files at 2026-05-21).

The author is whoever did the work (agent or human); the hooks enforce freshness
and flag drift. No new daemon, no heavy process -- it rides the hooks that already
fire.

### How it stays current (anti-rot mechanics)

- **Size cap enforced by rotation**, not by discipline: a `now_touch.py` check
  trims RECENT DONE to 7 (older -> `DONE.md`) and warns if the file exceeds 150
  lines. A bounded file cannot become the next 168 KB roadmap.
- **One writer of "current".** Only NOW.md may contain the words "current state"
  / "next up" / "active phase." The cutover strips that language from STATE.md,
  CLAUDE-state.md, ROADMAP.md, MASTER_PLAN.md and adds a banner: "ARCHIVE - live
  state is `.planning/NOW.md`." A repo grep guard (CI / pre-commit) can flag any
  other file that reintroduces "Current State (20" headers.
- **Worktree hygiene.** The dozens of `.claude/worktrees/agent-*/` copies of
  STATE/ROADMAP/MASTER_PLAN are stale snapshots; prune merged worktrees
  (`git worktree prune`) so `find`/grep stop surfacing them. NOW.md lives only in
  the main checkout.

### Closing the bot-queue-visibility gap

`NOW.md` becomes a **first-class queue source** for the workday-loop, ranked
ABOVE the stale ROADMAP scan:
- The loop's `scan_plans.py` (or equivalent) reads NOW.md frontmatter +
  `## NEXT` checkboxes and seeds `ai-todo.md` from the unchecked items FIRST.
- Because each NEXT item already carries file/area + done-when, it converts
  directly into a task block with no re-derivation.
- Deep-dive docs still are not auto-scanned (that stays intentional), but the
  human/Opus surfaces the next slice INTO NOW.md, which the loop CAN see. The
  bottleneck (loop input = stale narrow slice) is removed without making the loop
  read 800 docs.

### Cutover plan (one-time, ~30 min, separate from this read-only audit)

1. Create `.planning/NOW.md` from the template, populated from the TRUE current
   frontier: north_star=best-predictions, active_project=pm_trading,
   phase=paper-trader-step-3, NEXT seeded from the pm_trading risk.py/strategies
   work, RECENT DONE seeded from the last ~7 git commits.
2. Create empty `.planning/DONE.md` (append-only archive header).
3. Add banner to STATE.md, CLAUDE-state.md, docs/ROADMAP.md, MASTER_PLAN.md:
   "ARCHIVE / historical -- live state is `.planning/NOW.md`." Strip "current
   state" phrasing.
4. Edit CLAUDE.md "If you're a Claude landing cold" list: make
   `.planning/NOW.md` the FIRST and only REQUIRED read for state; demote the
   rest to "evidence/archive, read on demand."
5. Add `.claude/rules/state-singlesource.md` (the write-back rule).
6. Extend Stop hook (`now_touch.py`) + SessionStart nudge.
7. Wire NOW.md as the top-priority loop queue source.
8. `git worktree prune` to clear stale state-file copies.

### Why this fixes the spin (the through-line)

- One file, capped and current, means a cold agent spends ~30 seconds reading
  state instead of synthesizing it from a dozen contradictory docs. The
  re-derivation -- the reiteration -- has nowhere to happen.
- Write-back enforced by hook means every finished unit advances the SAME file
  the next session reads first, so progress is cumulative, not re-litigated.
- Demoting the four rival "current" files removes the contradiction that today
  makes any single read untrustworthy.
- Feeding NOW.md to the loop closes the visibility gap so specced work actually
  moves.

Net: the system reads state, acts, writes state. Forward motion compounds;
reiteration stops.
