# 09 - Token & Context Efficiency Audit

> Date: 2026-06-17. Scope: cut per-turn context bloat and re-derivation in THIS
> Claude Code setup (nba-ai-system + the user's project memory). READ-ONLY audit.
> ASCII-only.

---

## 1. What this setup actually loads each turn (measured)

Every turn, the model re-sends the WHOLE conversation plus the always-on preamble.
The fixed preamble for this repo (measured 2026-06-17):

| Source | Size | Loaded |
|--------|------|--------|
| Project memory `MEMORY.md` | 33.5 KB / over the 24.4 KB limit (truncated each load) | every turn |
| Root `CLAUDE.md` | 7.9 KB / 108 lines | every turn |
| `.claude/rules/` (4 files) | 20 KB | every turn (3 are unconditional; `human-gated-paths.md` is path-scoped) |
| `.claude/agents/` (7 defs) | 32 KB | descriptions always; full body on spawn |
| `.claude/commands/` (24 files) | 152 KB | only when a command is invoked |
| `.claude/skills/` | 32 KB | descriptions surfaced; body on invoke |

Per-turn fixed overhead before any work = roughly **60 KB+** (MEMORY 33.5 + CLAUDE 7.9
+ rules 20). MEMORY.md is OVER its limit, so it is silently truncated -- you are
paying full token cost for a file whose tail is dropped (so the index entries below
the cut never even load). That is the single worst offender: cost with no benefit.

Accumulating-but-not-auto-loaded state (bloats only when touched, but invites
re-reads): `.planning/` = **30 MB / 394 .md**, project memory dir = **1.5 MB /
178 .md**, `.claude/worktrees/agent-*` = **67 dirs**, `docs/research/` = 74 .md / 5 dirs.

Good news already in place: **settings.local.json has NO hooks** -- so there is no
verbose PreToolUse/PostToolUse/UserPromptSubmit hook spamming stdout into context.
(The `Stop`/`SessionStart` hooks referenced in CLAUDE.md run vault scripts; confirm
they print <=1 line. If they ever echo file lists, that lands in context every session.)

---

## 2. Root causes of bloat / re-derivation in this setup

1. **MEMORY.md over the limit.** 33.5 KB vs a 24.4 KB cap. It is truncated on load,
   so you pay tokens for content that gets cut, and the cut entries provide nothing.
   The file's own WARNING says index lines are too long. This is index-not-detail
   discipline being violated.

2. **Index entries carry detail.** Many MEMORY lines run to ~200 chars with numbers,
   verdicts, and prose that belong in the linked topic file. The index should be a
   lookup table (one short line -> one slug), not a brain dump.

3. **CLAUDE.md mixes lookup with narrative.** 108 lines, but the truth-source TL;DR,
   honest-numbers block, vault-maintenance rules, and two never-stop loop specs are
   all inline. Only the Task->Files table and Key Paths are pure lookup. Anthropic's
   guidance: keep CLAUDE.md a lean lookup table (~<200 lines is the ceiling, leaner is
   better), push narrative into docs that are loaded on demand.

4. **Re-reading large docs.** ROADMAP.md is 167 KB; `.planning/` is 30 MB. Any time an
   agent (or the main thread) full-reads these instead of grep/section-reading, the
   whole turn balloons. CLAUDE.md already warns against full-reading ROADMAP -- extend
   the same rule to `.planning/` and `docs/research/`.

5. **Agent fan-outs return verbose bodies.** 67 worktrees show heavy fan-out use.
   If sub-agents return file contents / logs instead of conclusions, the main thread
   re-absorbs everything the sub-agent was supposed to keep out of context.

6. **Re-derivation across turns.** With 178 memory files + 394 planning docs, the
   same facts (e.g. "AST is the only real edge", "markets efficient") get re-searched
   and re-explained instead of being looked up once from a stable canonical line.

7. **Redundant tool calls / sequential when parallel.** Independent searches issued
   one at a time double the round-trips and the intermediate output retained.

---

## 3. How to use sub-agents to keep the MAIN context lean

The mechanic that matters: a sub-agent runs in its OWN context window. All its file
reads, greps, and logs stay there; only its final message returns to you. So the rule
is: **push the verbose work down, keep only the conclusion up.**

- **Delegate every broad search.** "Where does X live / which files match Y / sweep
  the planning corpus for Z" -> `Explore` agent. It reads excerpts, returns paths +
  the answer, not the file dumps. (This very audit delegated the repo measurement to
  an `Explore` agent and got back a bullet list, not 30 MB of planning text.)
- **Delegate multi-file reads.** If answering means reading across several files,
  delegate it and keep the conclusion, not the contents.
- **Tell the sub-agent its output budget explicitly.** End the prompt with: "Return a
  compact bullet list of facts + absolute paths; do NOT paste file contents." Vague
  delegation produces verbose returns that re-bloat the parent.
- **One file -> one agent in fleets** (already an invariant here) and pre-assign
  unique sections to parallel writers (already a known gotcha) -- both also limit how
  much each agent has to load.
- **Use cheaper models for search/scan** (Haiku/Explore) and reserve Opus for the
  synthesis that actually needs the big brain -- fewer input tokens per scan request.
- **Do not double-run.** Once a search is delegated, do not also run it in the main
  thread -- wait for the result. (Issuing both wastes the round-trip you delegated.)

---

## 4. /clear vs /compact -- when to use which (this setup)

- **/clear** = wipe the conversation, keep the preamble (CLAUDE.md, rules, memory).
  Use it **between unrelated tasks** -- when you finish one signal-audit / build step
  and move to a different one, the prior transcript is dead weight. This setup runs
  long never-stop loops, so clearing at each natural task boundary is the highest-
  leverage habit. Cheap and lossless for the next task because the canonical facts
  live in CLAUDE.md / MEMORY / docs, not in the transcript.
- **/compact** = summarize-and-continue. Use it **mid-task** when you still need the
  thread's findings but it has grown long. Compact EARLY (while the session is still
  healthy) for a better summary; a late compact of a bloated session keeps noise.
  Add a compaction-preservation note to CLAUDE.md so the summary always keeps the
  load-bearing bits (e.g. "When compacting, preserve: modified files, the gate
  verdict, and any do-not-claim numbers").
- **Default bias for this repo:** prefer **/clear at task boundaries** over riding one
  ever-growing context. Because the durable state is externalized (memory + docs +
  vault Decision Log), clearing loses almost nothing and resets you to the ~60 KB
  floor instead of carrying 200 KB of stale transcript.

---

## 5. Structuring work so the agent does not re-read / re-derive

- **Canonical-value line, loaded once.** Keep the binding facts (AST is the only edge;
  markets efficient; retracted numbers list; LOC rule) in ONE short authoritative
  place that is always loaded (the rules files already do this well). Then everything
  else references the slug instead of re-deriving. The `no-edge-claims.md` rule is the
  model to copy.
- **Grep/section-read, never full-read** the big docs. Encode it: extend the existing
  "NEVER full-read ROADMAP" line to cover `.planning/**` and `docs/research/**`.
- **Write the conclusion down immediately.** After a sub-agent or a search produces a
  fact you will reuse, append a one-line note to the relevant memory topic file (not
  the index) so the next turn looks it up instead of re-searching. The vault
  Decision-Log/Engineering-Knowledge dedup habit already in CLAUDE.md is exactly this.
- **Trust file-state tracking.** Do NOT re-Read a file you just edited to "verify" --
  the harness errors if an edit failed. Re-reads after edits are pure bloat.
- **Reference by path, not by paste.** When handing context to a sub-agent, give it the
  path and let it read in its own context; do not paste the file into the prompt.

---

## 6. Avoiding redundant tool calls + batching parallel calls

- **Batch independent calls in ONE message.** If two searches / reads have no data
  dependency, issue them together so they run concurrently -- one round-trip, less
  retained intermediate output. (This audit ran 2 WebSearches + 1 Explore agent in a
  single message.) Only serialize when call B needs call A's output.
- **Prefer the dedicated tool over Bash.** Use Grep (ripgrep) and Glob instead of
  `bash grep/find/cat` -- they return tighter, link-integrated output and avoid the
  cwd-prefix dance. Reserve Bash for things only a shell can do.
- **Scope every search.** Use `glob`/`type` filters and `head_limit` so a Grep returns
  10 lines, not 250. Default head_limit is large; set it down for known-narrow lookups.
- **Read only the slice you need.** For big files, Read with `offset`/`limit` instead
  of pulling 2000 lines; section-read ROADMAP/PLAN rather than whole-file.
- **De-duplicate before searching.** Check whether the fact is already in MEMORY / a
  rule / the Decision Log before launching a search for it.

---

## 7. Concrete fixes for THIS setup (do-list)

1. **Trim MEMORY.md back under 24.4 KB.** Cut every index line to a short
   slug + <=120-char gloss; move all numbers/verdicts/prose into the linked topic
   file. Target ~half the current bytes. This stops the silent-truncation waste and is
   the single biggest per-turn win.
2. **Split CLAUDE.md into lean lookup + on-demand narrative.** Keep Task->Files, Key
   Paths, Rules, and the two loop triggers. Move the honest-numbers TL;DR and vault-
   maintenance list into docs already cited (JOB_EVIDENCE_PACKET / a vault doc) and
   reference them. Aim ~60-70 lines.
3. **Add an anti-full-read line** to CLAUDE.md Rules: "grep/section-read `.planning/**`,
   `docs/research/**`, and any >50 KB doc; never full-read."
4. **Add a compaction-preservation note** to CLAUDE.md (see Section 4).
5. **Standardize sub-agent return contract:** every delegation prompt ends with
   "return facts + absolute paths only, no file contents." Bake it into the agent defs
   in `.claude/agents/`.
6. **Garbage-collect `.claude/worktrees/` (67 dirs).** Stale agent worktrees are disk +
   a temptation to re-read; prune the ones whose git state is clean/merged.
7. **Confirm `Stop`/`SessionStart` hooks print <=1 line.** They feed SessionStart
   context; if they ever echo file lists, redirect that to a log file instead of stdout.

---

## 8. Top 10 ranked by impact (also in the return summary)

1. Trim MEMORY.md under its 24.4 KB limit -- stops paying for truncated content.
2. Index-only memory lines -- one slug + short gloss; detail lives in topic file.
3. /clear at every task boundary -- reset to the ~60 KB floor between loop steps.
4. Delegate broad searches to Explore/sub-agents -- verbose reads stay out of main ctx.
5. Make sub-agents return conclusions-only -- "facts + paths, no file contents."
6. Batch independent tool calls in one message -- concurrent, fewer round-trips.
7. Never full-read ROADMAP/.planning/docs-research -- grep/section-read only.
8. Slim CLAUDE.md to a lookup table (~60-70 lines) -- narrative moves to on-demand docs.
9. Stop re-reading just-edited files + use Grep/Glob over bash -- kill redundant calls.
10. /compact EARLY mid-task with a preserve-list -- better summary, less retained noise.

---

## Sources

- [Best practices for Claude Code (Claude Code Docs)](https://code.claude.com/docs/en/best-practices)
- [Claude Code Context Window: Optimize Your Token Usage](https://claudefa.st/blog/guide/mechanics/context-management)
- [Create custom subagents (Claude Code Docs)](https://code.claude.com/docs/en/sub-agents)
- [Claude Code Sub-Agents Explained: Context, Cost, and Parallel Execution](https://www.mindstudio.ai/blog/claude-code-sub-agents-explained)
- [How to Use Sub-Agents in Claude Code to Manage Context](https://www.mindstudio.ai/blog/sub-agents-claude-code-context-management)
- [Context Management - Claude Code Best Practices](https://muhammadusmangm.github.io/claude-code-best-practices/guides/context-management/)
- [23 Tips for Smart Claude Code Token Saving](https://www.analyticsvidhya.com/blog/2026/05/tips-for-claude-code-token-saving/)
- [7 Practical Ways to Reduce Claude Code Token Usage (KDnuggets)](https://www.kdnuggets.com/7-practical-ways-to-reduce-claude-code-token-usage)
