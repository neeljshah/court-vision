# Efficiency practices for the two-loop program -- external research vs. our setup (2026-09-03)

Scope: minimum token cost for running the Claude Code + Codex CLI loops (G-register tracking,
S-register harness). Read-only research memo; no code change is made here. Every external claim
carries its source URL. `INFERENCE` marks our own conclusion, not a documented statement.
Calibration language only -- nothing here is a claim about returns.

Sources (fetched 2026-09-03):
- C1 https://code.claude.com/docs/en/costs  (Manage costs effectively)
- C2 https://code.claude.com/docs/en/prompt-caching  (How Claude Code uses prompt caching)
- C3 https://code.claude.com/docs/en/sub-agents  (Subagents)
- X1 https://learn.chatgpt.com/docs/codex/cli  (Codex CLI)
- X2 https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide  (Codex prompting guide)
- P1 https://claudefa.st/blog/guide/development/multi-agent-orchestration-cost  (one engineer's own
     measurements, explicitly NOT Anthropic benchmarks -- treat as directional)
- P2 https://www.tembo.io/blog/claude-code-multi-agent-orchestration
- P3 https://hidekazu-konishi.com/entry/anthropic_claude_api_prompt_caching_and_token_efficiency.html

## 1. Practices we ALREADY follow

| # | Practice | Source | Where it is implemented here |
|---|---|---|---|
| 1 | Move workflow instructions out of CLAUDE.md into on-demand skills; keep CLAUDE.md under 200 lines | C1 | `CLAUDE.md` is 103 lines; rails live in `.claude/skills/harness-lane/SKILL.md` and `.claude/skills/tracking-lane/SKILL.md` |
| 2 | Path-scoped rules load lazily, costing nothing until a matching file is read | C1, C2 | `.claude/rules/*.md` (4 files, 139 lines total) imported from `CLAUDE.md` |
| 3 | Restrict a subagent's tools to what it needs | C3 | `allowed-tools: Read, Grep, Glob, Bash` in both lane SKILL.md files |
| 4 | Route cheap tasks to cheaper models via subagent frontmatter | C1, C3 | `.claude/agents/cv-explore.md` (`model: haiku`), `cv-plan.md` (sonnet), `cv-code-reviewer.md` / `cv-honesty-gate.md` (opus) |
| 5 | Model and effort are part of the cache key -- pick once at session start, never switch mid-task | C2 | recorded as a rule in `docs/research/organization-sprint/CLAUDE_CODE_BEST_PRACTICES_2026-09-03.md` s5; codex side pins `model_reasoning_effort` per `CODEX_HOME` (`~/.codex-a1/config.toml`) |
| 6 | Offload preprocessing to hooks so filtered output, not raw files, enters context | C1 | SessionStart `loop_status.sh` + `usage_dashboard.sh`; PostToolUse `ledger_hook.py`; PreToolUse `scripts/hooks/pretooluse_guard.py` (all wired in `.claude/settings.local.json`) |
| 7 | Delegate verbose operations so only a summary crosses back | C1, C3 | codex jobs run detached via `~/bin/codex-sport`; their full transcript stays in `Temp/cx_*.log` and never enters an orchestrator context |
| 8 | Write specific prompts with verification targets instead of open-ended ones | C1 | `docs/evidence/tracking/CODEX_SPEC_TEMPLATE.md` -- 40-line cap, mandatory ACCEPTANCE RULE |
| 9 | Cap what crosses the agent boundary (billed twice: once as output, again as input) | P1 | `REPORT <=15 lines` rail in both lane SKILL.md files |
| 10 | Skip delegation when the work is small; delegate when the worker absorbs many tokens | P1 | REQUIRED / LIGHT / SKIP verifier tiers, `docs/research/organization-sprint/PLAN_AI_ENGINEERING_2026-09-03.md` s5 |
| 11 | Bound retries so a wrong path cannot spend without limit | C1 (course-correct early) | binding loop rule 2 in `.planning/NOW.md` -- two attempts, second is a LIMIT measurement, then CLOSED AT LIMIT |
| 12 | Prefer CLI tools over MCP servers; disable unused servers | C1 | one project MCP server only (`courtvision` in `.mcp.json`); git/gh/ssh work goes through Bash |
| 13 | Avoid agent teams (~7x the tokens of a standard session when teammates run in plan mode) | C1 | we use subagents plus external codex processes, never `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` |
| 14 | Measure spend rather than assume it | C1, P1 | `scripts/platformkit/tracking/usage_dashboard.sh` sums each log's own `tokens used` line per loop per day |
| 15 | Skill invocation appends as a user message and does not invalidate the cached prefix | C2 | the `Skill: harness-lane` lane preamble is therefore cache-safe as used |

## 2. Upgrades we do NOT yet do

| # | Change (file + one line) | Token-saving mechanism |
|---|---|---|
| U1 | `.claude/settings.local.json`: add `"subagentPromptCacheTtl": "1h"` and `"promptCacheTtl": "1h"` | Subagents fall outside the main-conversation TTL bucket and get **five minutes** by default even on a subscription (C2). A REQUIRED verifier pass is 15-25 min (`PLAN_AI_ENGINEERING` s5), so its prefix expires mid-pass and each turn after a pause re-reads the whole context at write rates instead of the ~10% cached-read rate (C2). Item 9 of `CLAUDE_CODE_BEST_PRACTICES_2026-09-03.md` already lists this as TODO. |
| U2 | New `.claude/agents/harness-verifier.md` / `tracking-verifier.md` / `gap-finder.md` with `model:`, `tools:`, `skills:` frontmatter | Today the routing ("spec+verify opus/high, gap-finder sonnet", `PLAN_AI_ENGINEERING` s1) exists only in prose, so every lane inherits the `opus[1m]` default in `~/.claude/settings.json` and re-receives its rails inside the spawn prompt. C1: "Keep spawn prompts focused ... everything in the spawn prompt adds to their context from the start"; C1 also says reserve Opus and use cheaper models for simple subagent tasks. Frontmatter makes the routing declarative and drops the repeated preamble. |
| U3 | `scripts/hooks/pretooluse_guard.py`: rewrite `python -m pytest <file> -q` to append a failures-only filter | C1 gives this exact PreToolUse pattern ("Instead of Claude reading a 10,000-line log file to find errors, a hook can grep for `ERROR` and return only matching lines"). Verifier reproduction steps currently pipe full per-file pytest output into an Opus context. |
| U4 | Per-worktree `~/.codex-aN/config.toml`: `model_reasoning_effort = "medium"` for mechanical gaps, keep `"high"` only for design-heavy ones | `~/.codex-a1/config.toml` is `terra/high` for every job; the machine default `~/.codex/config.toml` is `terra/medium`. X1/X2: reasoning effort is selectable per profile and medium is the recommended balanced default, with lower effort spending fewer thinking tokens. Measured here: 19 finished codex jobs, mean 188,550 tokens, min 75,879, max 461,559 -- and the heaviest was a REJECT (`docs/evidence/tracking/TRACKING_LOOP_OPTIMIZATION_2026-09-02.md` s1.1). |
| U5 | `.claude/settings.local.json` `env`: `"DISABLE_AUTOUPDATER": "1"` | C2: "Resuming a session after an upgrade reprocesses the entire conversation history with no cache hits ... the first turn back into a long session can be the most expensive request you send." This loop runs across multiple days and wakes, so an unscheduled upgrade otherwise lands mid-loop. |
| U6 | `PLAN_AI_ENGINEERING` s6 runbooks: use `/rewind` (not `/compact`) when abandoning a path, and `/compact` only at task seams | C2: rewind "truncates back to a prefix that is already cached, rather than building a new one as compaction does"; compaction by design invalidates the conversation layer. |
| U7 | Dispatch the LIGHT verifier batch as one Workflow fan-out of same-skill agents rather than N independent `Agent` calls | C2: "In a workflow fan-out of same-prefix agents, Claude Code briefly holds all but the first so their first requests can read the prefix the first agent cached." P1 frames the same effect: N parallel workers otherwise pay N cache writes (1.25-2x) instead of one write plus N-1 reads (0.1x). |
| U8 | `scripts/platformkit/tracking/usage_dashboard.sh`: add the Claude-side cache figure alongside the codex token counts | The dashboard measures codex only. C1/C2 expose a `Prompt cache (main)` line in `/usage` and a `prompt_cache` object readable from a statusline script; a high creation-to-read ratio is the signal that something is churning the prefix. INFERENCE: without this we cannot tell whether U1 worked. |
| U9 | `.claude/skills/lane-spawn-rails/SKILL.md`: state that Claude lanes run with the main repo as cwd and only codex enters `nba-track-aN` | C2: the cache is scoped to machine plus directory, and "That includes worktrees of the same repository, since each worktree has its own working directory." INFERENCE: this is our current practice by convention only, so it is one careless `cd` away from a cold prefix per lane. |
| U10 | Second-attempt (LIMIT-measurement) passes: use a fork rather than a fresh subagent | C2: "A fork ... inherits the parent's system prompt, tools, and conversation history exactly, so its first request reads the parent's cache," whereas a subagent's first request cannot read the parent's. INFERENCE: the LIMIT pass re-reads the same spec the first pass just read, which is the case a fork is for. |
| U11 | Run `/insights` once at a week seam | C1: it analyses up to 200 recent sessions and reports friction points such as misunderstood requests and buggy code. INFERENCE: our REJECT-cause taxonomy (SPEC / DESIGN / DATA / PROCESS in `TRACKING_LOOP_OPTIMIZATION` s1.1) is the same question asked by hand. |

## 3. Top five, ranked

1. **U1** -- set `subagentPromptCacheTtl: "1h"` (and `promptCacheTtl: "1h"`): the verifier lanes are the
   largest Claude-side cost and they currently run on a five-minute cache TTL that expires inside every
   15-25 minute pass (C2).
2. **U2** -- declare the lane roster as `.claude/agents/*.md` with `model:`/`tools:`/`skills:` frontmatter,
   so the planned sonnet/haiku routing actually takes effect instead of every lane inheriting `opus[1m]`,
   and the rails stop being retyped into each spawn prompt (C1, C3).
3. **U3** -- add the documented PreToolUse output filter for per-file pytest runs, so verifier reproduction
   returns failures rather than full test output into an Opus context (C1).
4. **U4** -- split codex reasoning effort by job class instead of `terra/high` for everything, given the
   measured 76k-462k token spread per job and that the heaviest job in that table was a REJECT (X1/X2 plus
   `TRACKING_LOOP_OPTIMIZATION` s1.1).
5. **U5 + U6** -- two one-line session-hygiene fixes for a multi-day loop: pin the updater so no wake pays a
   full uncached re-read, and prefer `/rewind` over `/compact` when a path is abandoned (C2).

## NOT VERIFIED
- No before/after token measurement was taken for any upgrade above. Every saving named is a mechanism
  documented in the cited pages, not a benchmark run here. P1's figures are one engineer's self-reported
  numbers and the author says so explicitly.
- U7 and U10 assume Workflow and fork are available in the installed Claude Code build; not checked.
- Whether `effortLevel` in `~/.claude/settings.json` already differs per lane type was not inspected.
- The Codex CLI page (X1) documents `/model` and reasoning-effort selection but states no token-cost
  guidance of its own; the medium-default claim rests on X2.
