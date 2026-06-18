# Official Anthropic Best Practices for Organizing a Claude Code Setup

Compiled 2026-06-17 from official Anthropic / Claude documentation (docs.claude.com,
code.claude.com, platform.claude.com, anthropic.com). All recommendations below are
sourced; URLs are listed per section and consolidated at the end. ASCII-only.

The single organizing constraint behind nearly every recommendation: Claude's context
window fills up fast, and model performance DEGRADES as it fills. Treat context as the
scarcest resource and design the whole setup to keep it small, relevant, and clean.

---

## 1. CLAUDE.md structure and best practices

Source: https://code.claude.com/docs/en/best-practices ; https://code.claude.com/docs/en/memory

- CLAUDE.md is a special file Claude reads at the START OF EVERY conversation. It is the
  place for persistent context Claude cannot infer from the code alone.
- Run `/init` to generate a starter CLAUDE.md from your current project structure (it
  detects build systems, test frameworks, code patterns), then refine over time.
- There is NO required format. Keep it SHORT and human-readable. Keep CLAUDE.md UNDER
  ~200 lines (official rule of thumb). If it is growing, move reference content to skills
  or split into `.claude/rules/` files.
- The litmus test for every line: "Would removing this cause Claude to make mistakes?"
  If not, cut it. Bloated CLAUDE.md files cause Claude to IGNORE your actual instructions.

  INCLUDE:
  - Bash commands Claude can't guess
  - Code style rules that DIFFER from language defaults
  - Testing instructions / preferred test runner
  - Repo etiquette (branch naming, PR conventions)
  - Architectural decisions specific to your project
  - Dev environment quirks (required env vars)
  - Common gotchas / non-obvious behaviors

  EXCLUDE:
  - Anything Claude can learn by reading the code
  - Standard language conventions Claude already knows
  - Detailed API docs (link out instead)
  - Information that changes frequently
  - Long explanations / tutorials
  - File-by-file descriptions of the codebase
  - Self-evident advice ("write clean code")

- Tune adherence with emphasis: "IMPORTANT" or "YOU MUST". Check CLAUDE.md into git so the
  team can contribute; its value compounds over time.
- Debugging signals: if Claude keeps violating a rule, the file is probably too long and
  the rule is lost in noise -> prune. If Claude re-asks something that IS in CLAUDE.md,
  the phrasing is ambiguous -> rewrite. Treat CLAUDE.md like code: review, prune, and test
  changes by watching whether behavior actually shifts.
- Import other files with `@path/to/import` syntax, e.g. `@README.md`, `@package.json`,
  `@docs/git-instructions.md`, `@~/.claude/my-project-instructions.md`.
- File locations (all additive; nearer/more-specific wins on conflict):
  - `~/.claude/CLAUDE.md` -> all sessions, all projects
  - `./CLAUDE.md` (project root) -> commit to share with team
  - `./CLAUDE.local.md` -> personal project notes; add to .gitignore
  - Parent dirs (monorepos: both `root/CLAUDE.md` and `root/foo/CLAUDE.md` load)
  - Child dirs -> pulled in ON DEMAND when Claude reads a file there
- `.claude/rules/` files: load every session OR only when matching files are opened
  (via `paths` frontmatter). Use to keep CLAUDE.md focused; path-scoped rules save context.

---

## 2. Memory tool / persistent memory (cross-session)

Source: https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool

- The memory tool lets Claude create/read/update/delete files in a `/memories` directory
  that PERSISTS across conversations, so it builds knowledge without keeping everything in
  context. It is the key primitive for "just-in-time" context retrieval: store what you
  learn, pull it back on demand. Client-side: you control storage.
- When enabled, Claude AUTOMATICALLY checks `/memories` before starting a task. The
  injected protocol: view memory first; record progress/status/thoughts as you go; ASSUME
  INTERRUPTION (context may reset any moment, so unrecorded progress is lost).
- Keep memory coherent: instruct Claude to keep files up-to-date and organized, rename or
  delete stale files, and not create new files unless necessary (combats clutter). You can
  scope it: "Only write information relevant to <topic> in memory."
- Multi-session software pattern (official):
  1. Initializer session sets up artifacts BEFORE substantive work: a progress log, a
     feature checklist, a reference to any startup/init script.
  2. Each later session OPENS by reading those artifacts -> recovers full state in seconds.
  3. Before a session ends, UPDATE the progress log with done/remaining.
  Key principle: work on ONE feature at a time; mark complete only after end-to-end
  verification, not just after code is written.
- Pairs with compaction: compaction summarizes the whole conversation server-side near the
  limit; memory persists critical info ACROSS compaction boundaries so nothing is lost.
  Pairs with context editing (client-side tool-result clearing) similarly.
- Security: restrict all ops to `/memories`; guard against path traversal; cap file sizes;
  expire stale files.

---

## 3. Context management (compaction, /clear, context window)

Source: https://code.claude.com/docs/en/best-practices

- Manage context AGGRESSIVELY. The context window holds the entire conversation: every
  message, every file read, every command output. Performance drops as it fills.
- `/clear` between UNRELATED tasks to reset the window entirely (most important habit).
- After correcting Claude more than TWICE on the same issue, `/clear` and restart with a
  better prompt incorporating what you learned. A clean session + better prompt beats a
  long session with accumulated failed approaches.
- Auto-compaction triggers near the limit and summarizes what matters (code patterns, file
  states, key decisions). For control use `/compact <instructions>`, e.g.
  `/compact Focus on the API changes`.
- Partial compaction: `Esc Esc` or `/rewind`, pick a checkpoint, choose "Summarize from
  here" (condense forward) or "Summarize up to here" (condense earlier, keep recent).
- Customize compaction in CLAUDE.md, e.g. "When compacting, always preserve the full list
  of modified files and any test commands."
- `/btw` for quick side questions: the answer shows in a dismissible overlay and NEVER
  enters conversation history (zero context growth).
- Track usage continuously with a custom status line.
- Named failure pattern "the kitchen sink session" (mixing unrelated tasks) -> fix: /clear.
- Named failure pattern "infinite exploration" (unscoped "investigate X" reads hundreds of
  files) -> fix: scope narrowly OR use subagents.

---

## 4. settings.json (permissions, env, model) and scope hierarchy

Source: https://code.claude.com/docs/en/settings ; https://code.claude.com/docs/en/permissions

- 4-tier scope, priority HIGH to LOW: Managed (enterprise, cannot be overridden) >
  command-line args > Local (`.claude/settings.local.json`, gitignored, personal) >
  Project (`.claude/settings.json`, committed, team-shared) > User
  (`~/.claude/settings.json`, you across all projects).
- Permissions: `allow`, `deny`, `ask`. `deny` ALWAYS wins over `allow`. Permission rules
  MERGE across scopes (unlike most other settings). Rule syntax is tool-scoped, e.g.
  `Bash(npm run test *)`, `Read(./.env)`, `Bash(curl *)`.
  - Allowlist known-safe commands to cut interruptions (`npm run lint`, `git commit`).
  - Deny secret reads (`Read(./.env)`, `Read(./secrets/**)`).
- `env`: applied to every session AND subprocess Claude spawns.
- `model`: read at SESSION START only (use `/model` to switch mid-session). Related:
  `availableModels`, `enforceAvailableModels`, `fallbackModel` (chain capped at 3).
- Auto-reload without restart: `permissions`, `hooks`, `env`, credential helpers.
  Read ONCE at startup (need restart): `model`, `outputStyle`.
- Add the `$schema` line for editor autocomplete + inline validation. Validate config with
  `claude doctor`. User/project/local files are strict (whole file rejected if invalid);
  managed files parse tolerantly.
- Recommended split: USER = personal prefs (editorMode, language, model, MCP);
  PROJECT = shared permissions/env/hooks/announcements; LOCAL = personal per-repo overrides
  and machine-specific settings (auto-gitignored).
- Reduce permission interruptions three ways: Auto mode (classifier blocks only risky
  actions), permission allowlists, or `/sandbox` (OS-level isolation).

---

## 5. Subagents

Source: https://code.claude.com/docs/en/sub-agents ; https://code.claude.com/docs/en/features-overview

- A subagent runs in its OWN context window with its own system prompt, tool access, and
  permissions; it returns ONLY a summary to the main conversation. Use one when a side task
  would flood your main context with search results, logs, or file contents you won't reuse.
- They PRESERVE context (exploration/implementation stay out of main chat), ENFORCE
  constraints (limit tools), enable REUSE (user-level agents), SPECIALIZE behavior, and
  CONTROL cost (route to cheaper models like Haiku).
- Define in `.claude/agents/<name>.md` (project) or `~/.claude/agents/` (user). Frontmatter:
  `name`, `description` (Claude uses this to decide when to delegate -> write it clearly),
  `tools`, `model`. Body is the system prompt.
- Delegate explicitly: "Use a subagent to review this code for security issues" or
  "use subagents to investigate how auth handles token refresh."
- Use as an ADVERSARIAL/fresh-context reviewer: a subagent sees only the diff + criteria,
  not the reasoning that produced the change, so it grades on its own terms. Bundled
  `/code-review` skill does this. Tell the reviewer to flag only correctness/requirement
  gaps, not style, to avoid over-engineering.
- Subagent scope precedence: managed > CLI flag > project > user > plugin.

---

## 6. Hooks

Source: https://code.claude.com/docs/en/hooks-guide ; https://code.claude.com/docs/en/hooks

- Hooks are user-defined shell commands (or HTTP request, LLM prompt, or subagent) that
  fire DETERMINISTICALLY at lifecycle events. Unlike CLAUDE.md instructions (advisory),
  hooks GUARANTEE the action happens. "Put guardrails in hooks": a "never edit .env" rule
  in CLAUDE.md is a request; a PreToolUse hook that blocks it is enforcement.
- Configure in `.claude/settings.json` (or `~/.claude/settings.json`). Browse with `/hooks`.
  Claude can write hooks for you ("write a hook that runs eslint after every file edit").
- Hook events: `SessionStart`, `UserPromptSubmit`, `PreToolUse` (can block),
  `PostToolUse`, `PostToolUseFailure`, `Notification`, `SubagentStop`, `Stop`,
  `StopFailure`, `PreCompact`, `SessionEnd` (plus `CwdChanged`).
- Common uses: auto-format after edits (PostToolUse + `Edit|Write` matcher), block edits to
  protected files / dangerous commands (PreToolUse), desktop notification when Claude needs
  input (Notification), re-inject critical context after compaction (SessionStart +
  `compact` matcher), reload env on directory change (SessionStart + CwdChanged),
  audit config changes, run a verification check as a Stop gate.
- Context cost is ZERO unless the hook returns output. When multiple hooks match an event,
  all run in parallel; for PreToolUse decisions the MOST RESTRICTIVE wins (deny > defer >
  ask > allow). A Stop hook is overridden after 8 consecutive blocks.

---

## 7. Skills

Source: https://code.claude.com/docs/en/best-practices ; https://code.claude.com/docs/en/features-overview

- A skill is a markdown file with frontmatter at `.claude/skills/<name>/SKILL.md` (project)
  or `~/.claude/output-styles`-style user dirs. The MOST FLEXIBLE extension: knowledge,
  reference material, or invocable workflows.
- Use skills (NOT CLAUDE.md) for domain knowledge / workflows that are only relevant
  SOMETIMES. Claude loads them ON DEMAND, so they don't bloat every conversation. By
  default only the description loads each session (low cost); full content loads on use.
- Two kinds: REFERENCE skills (knowledge Claude applies, e.g. an API style guide) and
  ACTION skills (invoke with `/<name>`, e.g. `/deploy`, `/fix-issue 1234`).
- Frontmatter `name` + `description` (Claude matches your task to the description; vague or
  overlapping descriptions cause wrong/missed loads). Use `$ARGUMENTS` for parameters.
- Set `disable-model-invocation: true` for workflows with SIDE EFFECTS you want to trigger
  manually only; this also drops context cost to zero until invoked. Override another
  author's skill visibility via `skillOverrides` in settings without editing its file.
- Skill precedence by name: managed > user > project. Plugin skills are namespaced
  (`/my-plugin:review`).

---

## 8. Slash commands / custom commands

Source: https://code.claude.com/docs/en/best-practices ; https://code.claude.com/docs/en/slash-commands

- For repeated workflows (debugging loops, log analysis), store prompt templates as
  Markdown. The CURRENT recommended format is a skill: `.claude/skills/<name>/SKILL.md`,
  invoked as `/name` (the older `.claude/commands/` folder still works). Check them into git
  to share with the team.
- Built-in slash commands manage sessions: `/init`, `/clear`, `/compact`, `/rewind`,
  `/permissions`, `/model`, `/hooks`, `/mcp`, `/rename`, `/btw`, `/goal`, `/sandbox`,
  and bundled skills like `/code-review`, `/batch`, `/debug`.

---

## 9. Output styles

Source: https://code.claude.com/docs/en/output-styles

- Output styles modify the SYSTEM PROMPT directly and apply to every response. They change
  HOW Claude responds (role, tone, format), not what it knows.
- Built-in: Default (efficient SWE), Proactive (act immediately, fewer pauses), Explanatory
  (educational "Insights"), Learning (collaborative; asks you to write small pieces).
- Custom: a markdown file with frontmatter, saved to `~/.claude/output-styles/` (user) or
  `.claude/output-styles/` (project, committable). Set `keep-coding-instructions: true` to
  change communication while keeping the built-in SWE coding behavior.
- Read once at startup (restart to apply). Nested project styles: nearest to working dir
  wins (v2.1.178+).

---

## 10. MCP (Model Context Protocol)

Source: https://code.claude.com/docs/en/mcp ; https://code.claude.com/docs/en/features-overview

- Use MCP servers to connect Claude to external services/data: databases, issue trackers,
  Figma, Slack, monitoring, browser. Add with `claude mcp add`.
- Prefer MCP over raw CLI for SENSITIVE data (better control over what Claude can access).
- Context cost: at session start only TOOL NAMES load; full JSON schemas defer until a tool
  is used. Tool search is on by default, so idle MCP tools cost minimal context. Run `/mcp`
  to see connection status and per-server token costs; disconnect servers you aren't using.
- Scope precedence: local > project > user. Enterprise can enforce `allowManagedMcpServersOnly`,
  and settings support `allowedMcpServers` / `deniedMcpServers`.
- Pair MCP with a Skill: MCP provides the connection/tools; the skill teaches Claude how to
  use them well (schema, query patterns, formatting).

---

## 11. CLI tools (most context-efficient external integration)

Source: https://code.claude.com/docs/en/best-practices

- Tell Claude to use CLI tools (`gh`, `aws`, `gcloud`, `sentry-cli`). CLI is the MOST
  context-efficient way to interact with external services. Install `gh` so Claude can
  open PRs / read issues without hitting unauthenticated rate limits.
- Claude can learn unfamiliar CLIs: "Use 'foo-cli --help' to learn the tool, then solve A,B,C."

---

## 12. Token-efficiency and workflow tips

Source: https://code.claude.com/docs/en/best-practices ; https://code.claude.com/docs/en/features-overview ; https://code.claude.com/docs/en/costs

- Give Claude a CHECK it can run (tests, build exit code, linter, screenshot diff). Without
  a verifiable signal, YOU are the verification loop. Escalating gates: in-prompt -> `/goal`
  condition (re-checked every turn) -> Stop hook (deterministic) -> fresh-context reviewer
  subagent. Have Claude show EVIDENCE, not assertions of success.
- Explore -> Plan -> Code -> Commit. Use plan mode to read/answer without editing, then have
  Claude write a detailed plan (`Ctrl+G` to edit it), THEN implement. Skip planning for
  one-sentence diffs; plan when uncertain, multi-file, or unfamiliar code.
- Be specific: scope the task (which file, which scenario, test prefs), point to sources
  (git history, example files), reference existing patterns. Vague prompts only for
  open-ended exploration.
- Provide rich context: `@file` references, paste images, give doc URLs (allowlist domains
  via `/permissions`), pipe data (`cat error.log | claude`).
- For larger features, have Claude INTERVIEW you (AskUserQuestion tool) to a SPEC.md, then
  start a FRESH session to implement. Self-contained specs name files/interfaces, state
  out-of-scope, end with an end-to-end verification step.
- Course-correct early: `Esc` to interrupt (context preserved), `Esc Esc` / `/rewind` to
  restore prior state, "undo that" to revert.
- Use checkpoints to try risky approaches and rewind if they fail (persist across sessions;
  NOT a git replacement).
- Name and resume sessions like branches: `/rename oauth-migration`, `claude --continue`,
  `claude --resume`.
- Match feature to goal (the decision rule):
  - "Always do X" rule / convention -> CLAUDE.md
  - Reusable knowledge or `/name` workflow used sometimes -> Skill
  - Side task that floods context, parallel/specialized work -> Subagent
  - Must happen every time, deterministically (lint, block, notify) -> Hook
  - Connect to an external system -> MCP
  - Reuse the same setup across repos / distribute -> Plugin
  - Symbol navigation / live type errors in a typed language -> code-intelligence plugin
- Build your setup OVER TIME, not up front. Each trigger maps to an addition:
  Claude gets a convention wrong twice -> CLAUDE.md edit; you retype the same prompt ->
  Skill; you re-paste a playbook a third time -> Skill; you keep copying from a browser tab
  Claude can't see -> MCP; a side task floods context -> Subagent; you want something every
  time -> Hook; a second repo needs the same setup -> Plugin.
- Scale: non-interactive `claude -p "..."` with `--output-format json|stream-json` and
  `--allowedTools` for CI/pre-commit/fan-out; worktrees / agent teams for parallel sessions;
  Writer/Reviewer pattern with a fresh-context reviewer.

---

## Source URLs (consolidated)

- Best practices for Claude Code: https://code.claude.com/docs/en/best-practices
  (formerly https://www.anthropic.com/engineering/claude-code-best-practices)
- CLAUDE.md / memory (project context): https://code.claude.com/docs/en/memory
- Extend Claude Code (match features to goal, context costs): https://code.claude.com/docs/en/features-overview
- Settings: https://code.claude.com/docs/en/settings
- Permissions: https://code.claude.com/docs/en/permissions
- Subagents: https://code.claude.com/docs/en/sub-agents
- Hooks guide: https://code.claude.com/docs/en/hooks-guide
- Hooks reference: https://code.claude.com/docs/en/hooks
- Skills: https://code.claude.com/docs/en/skills
- Slash commands (SDK): https://code.claude.com/docs/en/agent-sdk/slash-commands
- Output styles: https://code.claude.com/docs/en/output-styles
- MCP: https://code.claude.com/docs/en/mcp
- Memory tool (API, cross-session persistent storage): https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
- Compaction (API): https://platform.claude.com/docs/en/build-with-claude/compaction
- Context editing (API): https://platform.claude.com/docs/en/build-with-claude/context-editing
- Context windows (API): https://platform.claude.com/docs/en/build-with-claude/context-windows
- Reduce token usage / costs: https://code.claude.com/docs/en/costs
- Effective context engineering: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Effective harnesses for long-running agents: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
