# Community / Expert Best Practices for Power-Using Claude Code (2026)

Research date: 2026-06-17. Sources: engineering blogs, GitHub, Hacker News, Anthropic docs.
All techniques below are drawn from community/expert posts, with source URLs inline.

---

## 1. Multi-agent / subagent orchestration

### Match the pattern to the task; do not default to the heaviest option
Five native orchestration patterns: supervisor (subagents one level deep), fan-out
(parallel dispatch), pipeline (sequential calls + skills), debate (two agents + judge),
swarm (MCP workers). Supervisor is the 2026 production default. Debate costs ~2.5x a
single model -- reserve it for high-stakes decisions, not routine quality boosting.
- https://www.digitalapplied.com/blog/multi-agent-orchestration-5-patterns-that-work

### Three-layer architecture: orchestrator does NO granular work
Layer 1 = orchestrator (decompose, spawn, monitor, handle errors). Layer 2 = scoped
subagents that execute and return summaries. Layer 3 = verification that cross-checks
subagent outputs before returning the final result.
- https://getaitopia.io/blog/claude-subagents-explained-multi-agent-orchestration

### Parallel only for 3+ independent tasks with no file overlap; sequential when output feeds input
Parallel: frontend/backend/db with clear file boundaries (risk = merge conflicts).
Sequential: Schema -> API -> Frontend, or Research -> Plan -> Implement. Over-parallelizing
creates coordination overhead; under-parallelizing wastes wall-clock time.
- https://claudefa.st/blog/guide/agents/sub-agent-best-practices

### "Most sub-agent failures are invocation failures, not execution failures"
Bad: "Fix authentication." Good: "Fix OAuth redirect loop where successful login goes to
/login instead of /dashboard. Reference auth middleware in src/lib/auth.ts." Always pass
specific context, file references, and success criteria.
- https://claudefa.st/blog/guide/agents/sub-agent-best-practices

### Subagents as a context-isolation device (the biggest lever)
Delegate verbose/exploratory work to subagents so the noisy output stays in THEIR context
and only a summary returns to the main thread. Run light models for subagents
(CLAUDE_CODE_SUBAGENT_MODEL=Sonnet) while keeping Opus on the orchestrator.
- https://claudefa.st/blog/guide/mechanics/context-management
- https://claudefa.st/blog/guide/agents/sub-agent-best-practices

### "Master-Clone" alternative: skip custom subagents, let the main agent spawn clones
One expert (Shrivu Shankar) argues against many bespoke subagents -- instead put rich
context in CLAUDE.md and let the main agent dynamically spawn Task() clones. Preserves
holistic reasoning while still saving context.
- https://blog.sshh.io/p/how-i-use-every-claude-code-feature

---

## 2. CLAUDE.md / memory so knowledge COMPOUNDS

### Treat CLAUDE.md as a growing scar-tissue log, not a manual
Start with guardrails for SPECIFIC errors already seen, not a comprehensive doc. "A good
CLAUDE.md in month one saves repeating yourself; by month six it has captured every mistake
Claude ever made and prevents them automatically." This is the compounding loop.
- https://blog.sshh.io/p/how-i-use-every-claude-code-feature
- https://www.the-ai-corner.com/p/claude-best-practices-power-user-guide-2026

### Keep CLAUDE.md small; push detail into linked files
Instruction compliance degrades past ~200 lines. Keep CLAUDE.md to core rules + an index;
move rule sets into a .claude/rules/ folder or an "LLM wiki" of topic files. Reference paths
with reasoning ("for complex usage see path/to/docs.md") instead of @-embedding whole docs
(which burns the context budget every turn).
- https://medium.com/@bijit211987/the-complete-guide-to-claude-md...
- https://blog.sshh.io/p/how-i-use-every-claude-code-feature

### The 5 things that actually belong in CLAUDE.md
Commands, architecture map, hard rules, workflow preferences, scope boundaries. Prefer
alternatives over bare prohibitions ("use X" beats "never use --flag").
- https://www.the-ai-corner.com/p/claude-best-practices-power-user-guide-2026

### Auto-memory: let the agent update its own memory from its work
The compounding pattern is an agent that learns from its own mistakes and writes them back
to memory without manual effort, so each session improves the next. Pair with a quarterly
30-min review: re-run every documented command, fix stale architecture claims, delete rules
now enforced by CI.
- https://www.mindstudio.ai/blog/what-is-claude-code-auto-memory
- https://www.the-ai-corner.com/p/claude-best-practices-power-user-guide-2026

### Memory-staleness verification is built in
Claude Code instructs the agent to verify memory records against current file/resource state
and DELETE memories that conflict with observed reality -- so stale single-source-of-truth
entries self-purge rather than silently misleading.
- https://github.com/Piebald-AI/claude-code-system-prompts

---

## 3. Single-source-of-truth state files + verification-driven loops

### The 4-file persistent-state pattern (defeats context drift)
PROJECT.md (vision/features), REQUIREMENTS.md (schema/auth/API/edge cases),
ROADMAP.md (phases + success criteria), STATE.md (current position, done, pending).
"Claude reads these before writing ANY code. Can't forget the schema -- it's documented."
Parallel executors all read the SAME truth files, so they cannot make conflicting edits.
- https://news.ycombinator.com/item?id=47402125

### Verification-driven loop: do work -> run check -> read result -> iterate until pass
Give Claude something that emits a pass/fail signal it can read in-conversation: test suite,
build exit code, linter, fixture diff, or screenshot-vs-design. A verifier agent tests
against the documented success criteria after each phase; a debugger agent spawns on failure.
- https://code.claude.com/docs/en/best-practices
- https://news.ycombinator.com/item?id=47402125

### Spec-driven sequence
Specify requirements in markdown -> generate a plan from them -> implement against the plan
-> validate results against the original spec. The spec is the source of truth for both
human and agent.
- https://www.augmentcode.com/guides/claude-code-spec-driven-development

---

## 4. Hooks for automation (deterministic, vs probabilistic skills/agents)

### The architecture rule
CLAUDE.md and hooks are DETERMINISTIC (run every time). Skills and agents are PROBABILISTIC
(agent judgment). Use hooks for guarantees, skills for reusable method, slash commands for
human-timed shortcuts.
- https://blog.laozhang.ai/en/posts/claude-code-hooks-slash-commands-skills

### Block-at-submit, not block-at-write
Wrap git commit with a PreToolUse hook that runs tests/lint and blocks the commit on failure.
Let the agent finish its plan first, then validate the FINAL result -- write-time blocking
fights the agent mid-thought. Use non-blocking "hint" hooks for soft suggestions.
- https://blog.sshh.io/p/how-i-use-every-claude-code-feature

---

## 5. Custom skills / slash commands

### Skills now auto-invoke (commands merged into skills)
Canonical location: .claude/skills/ (project), ~/.claude/skills/ (global). Mode 1 =
user-invocable (/skill-name). Mode 2 = auto-invocable -- Claude reads the SKILL.md
description and decides to fire it from context. Write descriptions with explicit trigger
phrases.
- https://code.claude.com/docs/en/skills

### Keep the command surface tiny
A handful of high-leverage commands (/catchup to read changed files, /pr to stage). "If
engineers must learn magic commands, the tooling design has failed." Document internal CLIs
inside SKILL.md as the formal scripting layer.
- https://blog.sshh.io/p/how-i-use-every-claude-code-feature

### Curated catalog
awesome-claude-code: vetted skills, hooks, slash-commands, orchestrators, plugins.
- https://github.com/hesreallyhim/awesome-claude-code

---

## 6. Token / context efficiency

### Watch /context and act at thresholds
/context shows the breakdown (system prompt, tools, memory, skills, history). Fresh monorepo
baseline ~20k tokens (10% of 200k). At ~80% usage on complex multi-file work, restart rather
than push into degraded territory.
- https://blog.sshh.io/p/how-i-use-every-claude-code-feature
- https://thepromptshelf.dev/blog/claude-code-context-management/

### Compact early -- override the autocompact threshold
Set CLAUDE_AUTOCOMPACT_PCT_OVERRIDE (1-100). Default fires near 95%; dropping to ~70%
compacts around 140k tokens, before quality drops, with better summaries (less to summarize).
- https://thepromptshelf.dev/blog/claude-code-context-management/

### Prefer /clear + /catchup over auto-compaction for clean reboots
For simple reboots, /clear then /catchup beats letting auto-compaction guess. Right-size the
model: Sonnet for most coding, Opus only for architecture; /model to switch mid-session.
- https://blog.sshh.io/p/how-i-use-every-claude-code-feature
- https://code.claude.com/docs/en/costs

---

## 7. THE 3 BEST FIXES for "Claude reiterates and doesn't move forward"

Distilled from the infinite-loop / no-progress research. Detection first: if outputs are
near-identical for 5+ minutes, error messages repeat, or minor variable renames are the only
"change," you are in a loop. Confirm it is planning-level (not capability) by issuing one
atomic 30-second command -- if that succeeds, the plan is the problem.
- https://ralphable.com/blog/claude-code-infinite-loop-bug-how-to-spot-stop-fix

### FIX 1 -- Hard context reset via a state file (Document & Clear)
The agent re-iterates because its context is corrupted with failed attempts. Have it write
current goal + sticking point + what was tried to a .md, then /clear (or start a fresh chat)
and restart with that .md as the only reference. The 4-file truth pattern makes this routine
instead of lossy.
- https://blog.sshh.io/p/how-i-use-every-claude-code-feature
- https://news.ycombinator.com/item?id=47402125

### FIX 2 -- Forced decomposition meta-command
Stop execution and issue: "List every step you attempted, explain each failure in one
sentence, then propose THREE fundamentally different approaches before doing anything." This
forces the meta-cognition the loop lacks and breaks the same-flawed-approach cycle.
- https://ralphable.com/blog/claude-code-infinite-loop-bug-how-to-spot-stop-fix

### FIX 3 -- Atomic tasks with explicit pass criteria (the structural prevention)
Convert monolithic instructions into atomic skills, each with: one singular objective, an
explicit verifiable pass criterion, and a defined failure/next-step. This turns a "loopy
planner" into a "deterministic executor" -- every micro-step is testable, so there is no
ambiguous retry to spin on. Pair with the verification-driven loop so each step exits on a
real pass/fail signal.
- https://ralphable.com/blog/claude-code-infinite-loop-bug-how-to-spot-stop-fix
- https://code.claude.com/docs/en/best-practices

---

## Top 12 techniques -- one-line "how to apply"

1. Supervisor/orchestrator pattern -- orchestrator decomposes + monitors; it does zero granular work itself.
2. Subagents for context isolation -- delegate verbose/exploratory work so only summaries return to main thread.
3. Parallel only for 3+ independent, non-overlapping tasks -- otherwise go sequential.
4. Invoke subagents with full context -- always include the bug, the file path, and the success criterion.
5. Keep CLAUDE.md small (<200 lines) + linked rule files -- core rules and an index only; detail lives in .claude/rules/.
6. Grow CLAUDE.md as a scar-tissue log -- after each mistake, add a guardrail so it never recurs (the compounding loop).
7. Auto-memory + quarterly review -- let the agent write lessons back; quarterly re-run commands and delete stale rules.
8. 4-file truth pattern (PROJECT/REQUIREMENTS/ROADMAP/STATE) -- agent reads these before any code; kills context drift.
9. Verification-driven loop -- give a pass/fail signal (tests/build/lint/diff) and iterate until it passes.
10. Hooks for guarantees, block-at-submit -- gate git commit on tests; validate the final result, not mid-write.
11. Auto-invoking skills with trigger-phrase descriptions -- put method in .claude/skills/SKILL.md; keep the command surface tiny.
12. Compact early (autocompact override ~70%) + watch /context -- restart at ~80%; Sonnet for coding, Opus for architecture.

---

## Source list

- https://www.digitalapplied.com/blog/multi-agent-orchestration-5-patterns-that-work
- https://getaitopia.io/blog/claude-subagents-explained-multi-agent-orchestration
- https://www.cloudzero.com/blog/claude-code-agents/
- https://claudefa.st/blog/guide/agents/sub-agent-best-practices
- https://claudefa.st/blog/guide/mechanics/context-management
- https://blog.sshh.io/p/how-i-use-every-claude-code-feature
- https://news.ycombinator.com/item?id=47402125
- https://ralphable.com/blog/claude-code-infinite-loop-bug-how-to-spot-stop-fix
- https://code.claude.com/docs/en/best-practices
- https://code.claude.com/docs/en/skills
- https://code.claude.com/docs/en/costs
- https://code.claude.com/docs/en/memory
- https://www.augmentcode.com/guides/claude-code-spec-driven-development
- https://blog.laozhang.ai/en/posts/claude-code-hooks-slash-commands-skills
- https://github.com/hesreallyhim/awesome-claude-code
- https://github.com/Piebald-AI/claude-code-system-prompts
- https://medium.com/@bijit211987/the-complete-guide-to-claude-md-memory-rules-loading-and-cross-tool-compression-97cc12ed037b
- https://www.the-ai-corner.com/p/claude-best-practices-power-user-guide-2026
- https://www.mindstudio.ai/blog/what-is-claude-code-auto-memory
- https://thepromptshelf.dev/blog/claude-code-context-management/
