# Claude Code Power Features: Solo Builder 10x Autonomous Build Loop

_Researched 2026-06-16. Scope: Claude Code's full extension stack (CLAUDE.md, skills, subagents, agent teams, hooks, MCP, headless/CI, plan mode, settings.json, plugins) and how a solo builder wires them into an autonomous, low-friction build loop for a calibrated sports predictor._

---

## TL;DR (7 highest-leverage takeaways)

- **CLAUDE.md is the single highest-ROI move.** Keep it under 200 lines. It loads every session. Encode binding invariants (cwd prefix, no full pytest, leak-free rules, no edge claims) here so every agent inherits them without prompting.
- **Hooks are the ONLY true enforcement layer.** Instructions in CLAUDE.md or skills are requests; a `PreToolUse` hook that rejects `git push origin` or `pytest tests/` is a guarantee. Use hooks for anything that must always happen the same way.
- **Subagents prevent context poisoning.** Route file-heavy research, signal catalog sweeps, or vault reads to Explore/Plan subagents (Haiku tier). Your main session stays clean and only receives summaries. Context isolation is more valuable than it looks.
- **Headless `-p` mode is the autonomous build loop primitive.** `claude -p "..." --output-format json --max-turns N` is scriptable, parseable, and CI-safe. Combine with `--session-id` for idempotent multi-stage pipelines. Exit code 0/1 is machine-readable.
- **Skills replace repeated typing.** Any workflow you run more than twice (benchmark, signal audit, brain rebuild, predict_matchup) belongs in `.claude/skills/` as a markdown file with frontmatter. Invoke with `/skill-name`. Use `disable-model-invocation: true` for destructive skills so only you can trigger them.
- **Scheduled cloud tasks (cron triggers) replace manual "start working" invocations.** `claude trigger create --schedule "0 2 * * *" --prompt "..."` runs on Anthropic infra overnight. The benchmark and signal catalog skills are natural cron targets.
- **Model routing by tier cuts cost 40-50%.** Route `Explore`/read-only subagents to Haiku, planning to Sonnet, final review/diff approval to Opus. Set `CLAUDE_CODE_SUBAGENT_MODEL=haiku` globally; override per skill frontmatter with `model: opus` where it matters.

---

## Key capabilities / techniques (concrete names, what they do, when to use)

### 1. CLAUDE.md / Memory Hierarchy

- **Location precedence (additive, all load):** enterprise -> `~/.claude/CLAUDE.md` -> `./CLAUDE.md` -> subdirectory `CLAUDE.md` files.
- **`.claude/rules/`**: path-scoped rules that only load when Claude works in matching files. Use for domain-specific constraints (e.g., `src/kernel/` gets a rule: "never edit without human gate").
- **`CLAUDE.local.md`**: personal overrides, gitignored.
- **`@path` imports**: inline external files into CLAUDE.md without copy-pasting.
- **Rule of thumb:** keep CLAUDE.md under 200 lines; move reference content to skills (load on demand).

### 2. Skills

- **Location:** `~/.claude/skills/` (user-wide) or `.claude/skills/` (project) or inside a plugin.
- **Format:** a directory with `SKILL.md` (frontmatter + body). Frontmatter controls name, description, model, context isolation, allowed tools, argument hints.
- **Auto-invocation:** Claude matches your task to skill descriptions and loads the relevant one. Set `disable-model-invocation: true` to prevent auto-invocation (forces explicit `/name` call) -- critical for side-effectful skills.
- **`context: fork`**: runs the skill in an isolated subagent so it cannot bloat main context.
- **Argument substitution:** `$ARGUMENTS`, `$0`, `$1`, `${CLAUDE_SKILL_DIR}`.
- **Key built-ins:** `/code-review`, `/batch`, `/debug`, `/compact`, `/recap`, `/ultrareview [PR#]`, `/less-permission-prompts`.

### 3. Subagents

- **Types:** `Explore` (read-only, Haiku default), `Plan` (read-only, Sonnet), `GeneralPurpose` (full tools), custom (define in `.claude/subagents/`).
- **Recursive spawning:** up to 5 levels deep (v2.1.172+).
- **`isolation: worktree`**: each subagent gets its own git worktree -- enables parallel edits without conflicts.
- **Context cost:** isolated from main session; only summary returns to parent. This is the primary value.
- **Custom subagent definition:** YAML frontmatter (`name`, `description`, `tools`, `model`, `isolation`) + system prompt body.
- **Skills in subagents:** listed in `skills:` field are fully preloaded at launch (no on-demand loading).

### 4. Agent Teams (experimental, default-OFF)

- **Multiple independent Claude Code sessions** that can message each other and share a task list.
- **Vs. subagents:** teammates communicate peer-to-peer; subagents only report back to parent.
- **Use case:** parallel research with competing hypotheses, simultaneous module reviews, parallel feature branches.
- **Cost:** higher -- each teammate is a full Claude instance. Reserve for genuinely parallel independent work.
- **Enable via:** settings flag or `/workflows` command.

### 5. Hooks

- **Event types (full list):** `PreToolUse`, `PostToolUse`, `PreCommit`, `PostCommit`, `SessionStart`, `SessionEnd` (= `Stop`), `SubagentStart`, `SubagentStop`, `TaskCreated`, `TaskCompleted`, `CwdChanged`, `FileChanged`, `PermissionDenied`, `PreCompact`, `PostCompact`, `UserPromptSubmit`, `Notification`, `MessageDisplay` (v2.1.152+).
- **Handler types:** `command` (shell), `prompt` (LLM decides), `HTTP` (POST JSON to endpoint), async (add `"async": true`).
- **`PreToolUse` special power:** can return `updatedInput` to modify tool arguments before execution -- use this to rewrite or sanitize commands.
- **Zero context cost** unless the hook returns output that Claude reads.
- **Config location:** `.claude/settings.json` under `"hooks"` key.
- **Matcher syntax:** regex on tool name, e.g., `"matcher": "Edit|Write"` or `"matcher": "Bash"`.

Hook config example (enforce: block push, auto-format on edit):
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "scripts/hooks/block_push.sh" }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "scripts/hooks/lint_file.sh" }]
      }
    ]
  }
}
```

### 6. MCP (Model Context Protocol)

- **Setup:** `claude mcp add <name> <command>` or define in `settings.json` under `"mcpServers"`.
- **Scope hierarchy:** local > project > user (local wins).
- **Tool naming:** MCP tools appear as `/mcp__<server>__<tool>` in skills/prompts.
- **Tool search:** on by default -- idle MCP tools consume minimal context (schemas deferred until use).
- **Glob deny rules (v2.1.166+):** `"deny": ["mcp__dangerous_server__*"]` -- wildcard blocks all tools from a server.
- **Remote servers:** support streamable HTTP + OAuth 2.1 with PKCE (no local stdio process needed).
- **Env vars:** `MCP_TIMEOUT` (startup, default 5000ms), `MCP_TOOL_TIMEOUT` (execution, default 30000ms).
- **Reconnects automatically** if remote server drops.

### 7. Headless / CI / -p Mode

- **Core flag:** `claude -p "prompt"` -- non-interactive, exits after response.
- **Output formats:** `text` (human), `json` (structured: `result`, `session_id`, `total_cost_usd`, `num_turns`, `is_error`), `stream-json` (newline-delimited events for real-time pipelines).
- **Exit codes:** 0 = success, 1 = any error. Machine-parseable.
- **`--max-turns N`:** hard cap on agentic iterations. Always set this in CI.
- **`--max-budget-usd`:** dollar ceiling per run.
- **`--allowedTools`:** explicit allowlist -- run with `"Read,Grep,Glob"` for read-only review tasks.
- **`--permission-mode bypassPermissions`:** skip all prompts (CI sandboxes only).
- **`--bare`:** skip hooks, LSP, plugin sync, skill discovery -- fastest headless mode.
- **Session continuation:** `--resume <UUID>` or `-c` (most recent) -- enables multi-stage pipelines sharing context.
- **`--session-id <UUID>`:** supply your own ID for idempotent reruns.
- **stdin support:** `cat error.txt | claude -p "diagnose this"`.
- **JSON schema output (structured):** `--json-schema '{"type":"object",...}'` -- Claude writes structured output conforming to schema, accessible at `.structured_output`.

### 8. Plan Mode

- **Activate:** `--permission-mode plan` or `/plan` command; or Ctrl+G in VS Code to edit the plan before approving.
- **Behavior:** Claude proposes, writes a plan to `.claude/plans/` (configurable via `plansDirectory`), does NOT execute.
- **Extended thinking triggers:** "think", "think hard", "think harder", "ultrathink" -- each increases reasoning depth. `Alt+T` enables extended thinking in plan mode.
- **Best practice for solo builds:** always plan before a multi-file change wave. Review plan, then approve execution. This is the #1 quality lever for complex tasks.

### 9. settings.json Schema (key fields)

File locations (precedence: CLI > managed > local project > shared project > user):
- `~/.claude/settings.json` (user)
- `.claude/settings.json` (shared project, commit to git)
- `.claude/settings.local.json` (personal, gitignore this)

Key fields:
```json
{
  "model": "claude-sonnet-4-6",
  "permissions": {
    "allow": ["Read", "Glob", "Grep", "Bash(npm run:*)", "Edit(src/**)"],
    "deny": ["Read(.env*)", "Bash(rm -rf:*)", "Bash(git push:*)", "Edit(.git/**)"],
    "defaultMode": "acceptEdits"
  },
  "hooks": { ... },
  "mcpServers": { ... },
  "skillOverrides": {
    "legacy-skill": "off",
    "manual-only-skill": "user-invocable-only"
  },
  "plansDirectory": ".claude/plans",
  "autoMemoryDirectory": ".claude/memory",
  "fallbackModel": ["claude-sonnet-4-6", "claude-haiku-4-5"],
  "env": { "PYTHONPATH": "." }
}
```

- **`fallbackModel`:** try models in sequence on overload (v2.1.166+) -- eliminates 529 failures.
- **`defaultMode: acceptEdits`:** auto-approve file edits, still prompt for Bash -- good default for trusted local work.
- **`additionalDirectories`:** grant access to paths outside cwd (e.g., `["../shared-lib"]`).

### 10. Plugins and Marketplaces

- **Bundle:** skills + hooks + subagents + MCP server definitions into one installable unit.
- **Namespace:** plugin skills appear as `/plugin-name:skill-name` to avoid collisions.
- **Structure:** `.claude-plugin/plugin.json` manifest + `skills/` + `hooks/` dirs.
- **Use case for solo:** package your benchmark/signal-audit/brain-rebuild loop as a plugin for easy portability across machines or future team members.

---

## How THIS project should use it (specific, actionable)

### A. Lock in binding invariants via hooks (not just CLAUDE.md)

The current CLAUDE.md has critical rules ("never push to origin", "never run `pytest tests/`", "prefix every cmd with `cd /c/Users/neelj/nba-ai-system &&`") that are currently only instructions. A Claude instance that ignores them can break the project.

**Immediate action:** add these hooks to `.claude/settings.json`:
- `PreToolUse` on `Bash` -> `block_push.sh`: exit 1 if command matches `git push origin` or `git push --force`. Return error message.
- `PreToolUse` on `Bash` -> `block_full_pytest.sh`: exit 1 if command matches `pytest tests/` (full suite). Allow per-file pytest.
- `PreToolUse` on `Bash` -> `prepend_cwd.sh`: if Bash command lacks the `cd` prefix and is not an absolute path, prepend `cd C:/Users/neelj/nba-ai-system &&`.
- `PostToolUse` on `Edit|Write` -> `check_file_length.sh`: warn if file exceeds 300 LOC (project invariant).
- `PostToolUse` on `Edit` touching `src/` or `kernel/` -> `human_gate_alert.sh`: emit a loud warning that these paths are human-gated.

### B. Encode the benchmark loop as a skill

The `/benchmark` skill already exists in the harness. Formalize it in `.claude/skills/benchmark/SKILL.md` with:
- `disable-model-invocation: true` (you invoke it, not auto-triggered)
- `model: sonnet` (benchmark runner does not need Opus)
- `context: fork` (isolate from main conversation -- benchmark output is noisy)
- Body: the exact benchmark-download-track-evaluate-compare-log-suggest sequence already in the `benchmark` skill definition.

Do the same for: `run-pipeline`, `train-checkpoint`, `debug-cv`, `dataset-status`.

### C. Use subagents to prevent context poisoning in the signal catalog workflow

The signal catalog sweep reads many files (`domains/<sport>/signal_catalog*.py`, `catalog_common.py`, gate data). This is a perfect `Explore` subagent task.

Pattern:
1. Main session (Sonnet): "survey the signal catalog for candidates that have not been gated in the last 30 days" -> spawn Explore subagent (Haiku).
2. Explore subagent reads files, returns a 10-line summary of candidates.
3. Main session decides which to run through the gate -- does NOT read the raw files itself.

This keeps main context clean for the decision layer.

### D. Wire headless -p into the nightly cron

The benchmark skill + scheduled tasks integration:
```bash
# In a GitHub Actions cron or local Task Scheduler:
claude -p "$(cat .claude/skills/benchmark/SKILL.md)" \
  --output-format json \
  --max-turns 20 \
  --allowedTools "Bash,Read,Glob,Grep,Edit" \
  --session-id "nightly-benchmark-$(date +%Y%m%d)" \
  > logs/benchmark-$(date +%Y%m%d).json
```

Or use the cloud cron: `claude trigger create --schedule "0 2 * * *" --prompt "Run /benchmark skill"`.

Set `fallbackModel: ["claude-sonnet-4-6", "claude-haiku-4-5"]` in settings.json to avoid 529 overload failures that stall overnight runs.

### E. Use plan mode before every multi-wave build

Before any wave that touches more than 2 files or crosses a domain boundary:
1. Invoke with `--permission-mode plan` or run `/plan` at session start.
2. Append "think hard" to the prompt to engage extended reasoning.
3. Review `.claude/plans/<session>.md`, edit if needed (Ctrl+G), then approve.

This catches the common failure mode where an agent misinterprets which files to touch and causes a cascade of bad edits.

### F. CLAUDE.md restructuring

Current CLAUDE.md is doing too much (project history, memory notes, invariants). Refactor:
- `CLAUDE.md` (root): under 200 lines -- architecture, build commands, binding invariants (link to rule files for detail).
- `.claude/rules/src-kernel.md` with `paths: ["src/**", "kernel/**"]`: "HUMAN-GATED -- do not edit these files. Emit a warning and stop."
- `.claude/rules/vault-gitignored.md` with `paths: ["vault/**", "data/**"]`: "vault and data are gitignored-local -- never commit files from these paths."
- `.claude/rules/no-edge-claims.md`: the honesty guardrail as a named rule file, not just inline text.

### G. Model routing for cost efficiency

Set in `.claude/settings.json`:
```json
{
  "model": "claude-sonnet-4-6",
  "env": { "CLAUDE_CODE_SUBAGENT_MODEL": "haiku" }
}
```

Override in specific skill frontmatter: `model: opus` for the diff-review skill and the plan-phase skill (these need the most reasoning). Exploration and catalog sweeps stay on Haiku.

### H. MCP: add the Obsidian vault as an MCP server

The vault is the working memory. An MCP server that reads/searches vault markdown files (e.g., `@modelcontextprotocol/server-filesystem` scoped to `vault/`) would let Claude query edge maps, wave notes, and feedback memories without loading them into main context via file reads.

This is the highest-leverage MCP addition for this project: vault intelligence on demand without context cost.

---

## Gotchas / limits

- **CLAUDE.md instructions are not enforcement.** Only hooks guarantee execution. A model under pressure or with a different system prompt may skip prose rules. Never put security-critical rules only in CLAUDE.md.
- **Hooks DO add context if they return output.** A linting hook that emits 200 lines of warnings will consume context. Make hooks output minimal: just the file path and error count, not the full lint report.
- **Skills with `disable-model-invocation: false` (default) load descriptions every session.** If you have many skills, descriptions accumulate. Audit skill count periodically; set `user-invocable-only` for skills you rarely need.
- **Agent teams are experimental and default-OFF.** They cost significantly more (each member is a full Claude instance). For solo builds with cost discipline, subagents are almost always the right choice.
- **Recursive subagents max out at 5 levels deep (v2.1.172+).** Design orchestration to stay within 3 levels to leave headroom for unexpected delegation.
- **`bypassPermissions` mode is for CI sandboxes only.** Never use it on your real checkout unless you fully trust the prompt and have the git-push hook in place.
- **The `--bare` flag skips hooks.** If you use `--bare` for speed, safety hooks do not run. Use it only for truly read-only analysis tasks.
- **Cron-based cloud triggers are Anthropic-managed infrastructure.** They run with your API key but outside your local environment. Verify that file paths and secrets are accessible (env vars in `settings.json` or passed via prompt) before relying on overnight runs.
- **`pytest tests/` freeze is not a hooks issue -- it is a resource issue.** A hook that blocks it is belt-and-suspenders, but the real fix is per-file test discipline. The hook just prevents accidental full-suite runs.
- **No genuine $ edge from any of these features.** Hooks, skills, and subagents speed up BUILD VELOCITY and prediction QUALITY (calibration, OOS walk-forward, Brier). They do not create market alpha. Frame all automation as serving prediction accuracy, not betting profit.

---

## Sources

- [Extend Claude Code (official docs) -- code.claude.com](https://code.claude.com/docs/en/features-overview)
- [Claude Code CLI: Complete Guide -- Hooks, MCP, Skills (blakecrosley.com)](https://blakecrosley.com/guides/claude-code)
- [Claude Code in CI/CD and Headless Automation (hidekazu-konishi.com)](https://hidekazu-konishi.com/entry/claude_code_cicd_and_headless_automation.html)
- [Understanding Claude Code's Full Stack: MCP, Skills, Subagents, Hooks (alexop.dev)](https://alexop.dev/posts/understanding-claude-code-full-stack/)
- [Claude Code Features and Settings Reference 2026 (hidekazu-konishi.com)](https://hidekazu-konishi.com/entry/claude_code_features_settings_reference_2026.html)
- [Claude Code MCP Plugins Guide (clarista.io)](https://www.clarista.io/blog/claude-code-mcp-plugins-guide)
- [Claude Code Headless Mode Autonomous Agents (mindstudio.ai)](https://www.mindstudio.ai/blog/claude-code-headless-mode-autonomous-agents-2)
- [Adaptive Thinking -- Claude API Docs (platform.claude.com)](https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking)
