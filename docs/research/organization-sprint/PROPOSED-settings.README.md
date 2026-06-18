# PROPOSED-settings.json -- HUMAN CONFIRM BEFORE APPLYING

**Do NOT copy this file as-is to .claude/settings.json without reviewing each section.**
The live session reads .claude/ directly. Wrong settings can break the build loop.
(Reconciled after the Opus review: hook script names, model aliases, and deny-globs
were corrected; the three duplicate thinner hooks were deleted.)

---

## What this file proposes

### model + fallbackModel
- Primary: `sonnet` (cost/quality balance for the autonomous build loop)
- Fallback chain (to dodge 529s): `sonnet -> haiku -> opus` (distinct links; up to 3 allowed)
- Subagents: `CLAUDE_CODE_SUBAGENT_MODEL=haiku` (cheap fleet workers)
- Bare aliases (sonnet/haiku/opus) are used for forward-compatibility instead of pinned dated IDs.

**Human check:** confirm the aliases resolve to the models you want (Opus override stays on
the review/plan skills via their own `model:` frontmatter). See https://docs.claude.com/en/docs/about-claude/models

### env block
- Sets `CLAUDE_CODE_SUBAGENT_MODEL` so spawned subagents default to Haiku without per-agent overrides.

### permissions
- Permissive allow list for the autonomous loop; deny list blocks `rm -rf /*`, force push, hard reset.
- Deny-globs corrected to the standard form: `Bash(rm -rf /*)`, `Bash(git push --force:*)`, `Bash(git reset --hard:*)`.
- `Agent(*)` was dropped (subagents are not invoked through an `Agent` tool permission key).
- NOTE: if both settings.json and settings.local.json exist, **permissions MERGE** and deny wins;
  the existing settings.local.json (April) already carries permissions, so you may keep permissions there
  and put only model/env/fallbackModel/hooks in settings.json.

### hooks (the kept set, after dedup)
Three hook scripts in scripts/hooks/ (written but NOT auto-wired):

| Hook event   | Script                              | Matcher    | Purpose                                        |
|--------------|-------------------------------------|------------|------------------------------------------------|
| PreToolUse   | scripts/hooks/pretooluse_guard.py   | Bash       | Block `git push` origin / `--force` / full `pytest tests/`; warn on missing cwd prefix |
| PostToolUse  | scripts/hooks/posttooluse_warn.py   | Edit\|Write | Warn on >300 LOC and on edits under src/kernel/api/scripts/team_system/intel |
| SessionStart | scripts/hooks/sessionstart_context.py | (all)    | Inject north-star + invariants context on session open |

The three thinner duplicates (pre_bash_guard.py, post_bash_cost_log.py, session_start_context.py)
were DELETED in the review fixup. Cost logging is handled by scripts/platformkit/cost_ledger.py
(called from a headless run), not a PostToolUse hook.

**Recommended apply path:**
1. Copy model/env/fallbackModel/hooks into a NEW .claude/settings.json.
2. Leave permissions in .claude/settings.local.json (they merge; deny wins).
3. Test each hook by piping a fake event JSON before relying on it (see checklist).

---

## Merge checklist before applying

- [ ] Verify the model aliases resolve to intended models (Anthropic docs).
- [ ] PreToolUse: `echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}' | python scripts/hooks/pretooluse_guard.py` -> exit 2 (BLOCK).
- [ ] PreToolUse allows a safe cmd: `echo '{"tool_name":"Bash","tool_input":{"command":"cd /c/Users/neelj/nba-ai-system && ls"}}' | python scripts/hooks/pretooluse_guard.py` -> exit 0.
- [ ] PostToolUse: `echo '{"tool_name":"Write","tool_input":{"file_path":"src/x.py"}}' | python scripts/hooks/posttooluse_warn.py` -> warns (exit 0 + stderr).
- [ ] SessionStart: `echo '{}' | python scripts/hooks/sessionstart_context.py` -> prints context lines.
- [ ] Confirm .claude/settings.json does not already exist (`ls .claude/`).
- [ ] fallbackModel length <= 3.

---

## PROPOSED-mcp.json apply note

`PROPOSED-mcp.json` contains human-readable `_README` / `_notes` top-level keys. Claude Code's
`.mcp.json` schema expects ONLY `mcpServers`. **Strip `_README` and `_notes`** (keep just the
`mcpServers` block) before merging into the live `.mcp.json` (currently `{"mcpServers": {}}`).
Register the stdio servers (sports_predictor, vault-knowledge, filesystem-RO, sqlite, memory)
one at a time and confirm each with `claude mcp list` before adding the next.
