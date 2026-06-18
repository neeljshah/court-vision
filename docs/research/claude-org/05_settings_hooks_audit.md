# Claude Code Settings + Hooks + Permissions Audit

Date: 2026-06-17. READ-ONLY audit. ASCII only.

Scope: user-level (`C:/Users/neelj/.claude/`) and repo-level
(`C:/Users/neelj/nba-ai-system/.claude/`) settings, hooks, rules, permissions.

---

## 1. Files found (and NOT found)

| File | Status | Notes |
|------|--------|-------|
| `~/.claude/settings.json` | EXISTS | The real config: permissions, hooks, statusline, effort. |
| `~/.claude/settings.local.json` | EXISTS but EMPTY | `{"permissions":{"allow":[]}}` -- a no-op file. |
| `nba-ai-system/.claude/settings.json` | MISSING | No tracked/shared repo settings. Repo relies on user-level + local. |
| `nba-ai-system/.claude/settings.local.json` | EXISTS | Broad allow `Bash(*)` etc. + 3 deny rules. Not the wiring. |
| `nba-ai-system/.claude/rules/*.md` | 4 files | bash-cwd-prefix, data-vault-nocommit, no-edge-claims, human-gated-paths. |
| `scripts/hooks/*.py` | 3 files | pretooluse_guard, posttooluse_warn, sessionstart_context -- ALL marked "NOT wired -- proposed". |
| `~/.claude/hooks/*.js` | 3 files | GSD: gsd-check-update, gsd-context-monitor, gsd-statusline. |
| `scripts/update_vault.py`, `scripts/vault_session_close.py` | EXIST | The vault hooks that actually run. |
| ~80 `.claude/worktrees/*/.claude/settings.local.json` | EXIST | Stale agent/worktree leftovers (clutter, see risks). |

KEY MISCONFIG: the three carefully-written Python guard hooks in
`scripts/hooks/` (pretooluse_guard, posttooluse_warn, sessionstart_context)
are NOT referenced by any settings file. They are dead code. Meanwhile the
actual `SessionStart` hook is wired in user settings and runs the vault scripts.

---

## 2. What actually runs (wired hooks, from `~/.claude/settings.json`)

### SessionStart (2 hooks, sequential)
1. `node ~/.claude/hooks/gsd-check-update.js` -- GSD self-update check.
2. `conda run -n basketball_ai python scripts/update_vault.py` -- regenerates
   `vault/Home.md` + folds scheme atlas into 30 team notes. Skips cleanly in
   brain-only / cold-clone mode. Runs git subprocesses (branch, log, rev-list).

### PostToolUse (1 hook, fires after EVERY tool call)
- `node ~/.claude/hooks/gsd-context-monitor.js` -- reads context-usage metrics
  from a statusline bridge file in tmp; injects an advisory "context low"
  message at <=35% (warning) / <=25% (critical). Has a 3s stdin timeout and
  5-call debounce. Fails silent. Lightweight (no git, no heavy IO).

### Stop (1 hook)
- `conda run -n basketball_ai python scripts/vault_session_close.py` -- on
  session end: refresh Home.md, sync Open Issues from CLAUDE-state.md, update
  CV counts + model-performance metrics, append one deduped row to
  `Sessions/Decision Log.md`. Runs several git subprocesses. Idempotent.

### statusLine
- `node ~/.claude/hooks/gsd-statusline.js` -- GSD status line renderer (also
  the producer of the context-metrics bridge file the monitor reads).

NOTE: `conda run -n basketball_ai ...` spawns a conda resolver on EVERY
session start and EVERY stop. That adds noticeable latency (conda env
activation is slow on Windows) to each session boundary.

---

## 3. Permission posture (current)

### User-level `~/.claude/settings.json`
- `permissions.allow = ["*", "Bash(python -c \"import tensorrt\")"]`
- `permissions.defaultMode = "bypassPermissions"`
- `skipDangerousModePermissionPrompt = true`
- `enableAllProjectMcpServers = true`
- `effortLevel = "max"`

Net effect: EVERYTHING is allowed and bypassPermissions is on globally. The
user effectively sees NO permission prompts. The `Bash(python -c "import
tensorrt")` entry is redundant given `"*"`.

### Repo `.claude/settings.local.json`
- allow: `Bash(*) Read(*) Write(*) Edit(*) Glob(*) Grep(*) WebFetch(*)
  WebSearch(*) Agent(*) NotebookEdit(*) mcp__*`
- deny: `Bash(rm -rf /)*`, `Bash(git push --force*)`, `Bash(git reset --hard*)`

The repo deny list is the only meaningful guardrail, but it is WEAK and
largely bypassed:
- `bypassPermissions` + `skipDangerousModePermissionPrompt` at user level may
  override / short-circuit prompting; deny rules still apply but the posture
  is "allow all then deny three patterns".
- The deny patterns are easy to evade: `git push -f` (not `--force`),
  `git push origin` (the actual repo risk -- pushing to PUBLIC origin) is NOT
  denied, `rm -rf <path>` (any path other than `/`) is NOT denied,
  `git reset --hard@{u}` variants slip through anchoring.
- The repo's stated #1 invariant -- NEVER push to public origin -- is NOT
  enforced by any wired hook or deny rule. The `pretooluse_guard.py` that WOULD
  enforce it is unwired.

### Prompts the user likely hits repeatedly
Given `bypassPermissions`, essentially NONE -- the user has traded all safety
prompts for zero friction. The cost is not prompt-spam; it is that the
documented hard invariants (no origin push, no full pytest, no data/vault
commits) are unenforced and rely entirely on agent discipline.

---

## 4. Env vars / config

- No `env` block in any settings file. No `ANTHROPIC_*`, no `CLAUDE_*`,
  no model override, no `MAX_THINKING_TOKENS`, no `BASH_DEFAULT_TIMEOUT_MS`.
- conda env name `basketball_ai` is hard-coded into two wired hook commands.
- `effortLevel: "max"` is set globally (high token spend on every turn).

---

## 5. Redundancy / risk / misconfig summary

RISKS
- R1. Public-origin push is UNGUARDED. The single most-emphasized invariant in
  CLAUDE.md / MEMORY / rules has no wired enforcement. `git push` to origin
  will succeed silently.
- R2. `bypassPermissions` + `skipDangerousModePermissionPrompt` globally =
  no human-in-loop on any destructive command. Combined with autonomous
  never-stop loops this is the highest-risk setting.
- R3. Deny patterns are anchored/narrow and trivially evadable (see sec 3).
- R4. Full-suite `pytest` (freezes the 15GB box per MEMORY) is NOT blocked.

REDUNDANCY / DEAD CONFIG
- D1. Three Python guard hooks in `scripts/hooks/` are written, tested-shaped,
  and UNWIRED. Pure dead code OR an un-applied upgrade (see recs).
- D2. `~/.claude/settings.local.json` is an empty no-op.
- D3. `Bash(python -c "import tensorrt")` allow entry is redundant under `"*"`.
- D4. ~80 `worktrees/*/.claude/settings.local.json` stale files -- clutter that
  also slows Glob/ripgrep over `.claude/` (the audit's own Glob timed out at
  20s walking them).

LATENCY
- L1. Two `conda run -n basketball_ai` invocations per session boundary
  (SessionStart + Stop) add slow conda activation each time.

---

## 6. Top 10 efficiency / permission recommendations

Ranked. SAFE = mechanical, reversible, no behavior risk. RISKY = changes the
safety/guardrail posture; confirm with user first.

1. [RISKY] WIRE `pretooluse_guard.py` as a `PreToolUse` Bash hook. It already
   blocks (a) push to origin, (b) `--force`, (c) full `pytest tests/`, and
   warns on missing cwd prefix -- i.e. it enforces exactly the invariants that
   are currently unguarded (R1, R3, R4). This is the single highest-value
   change. Confirm because it can block commands the user expects to run.

2. [RISKY] Replace the global `bypassPermissions` with `acceptEdits` (or
   `default`) and keep a real deny list. Preserves low friction for edits/reads
   while restoring a prompt on genuinely destructive shell ops. If the user
   wants the never-stop loop to stay fully autonomous, keep bypass but ONLY
   alongside rec 1 (the PreToolUse guard becomes the safety net).

3. [RISKY] Harden the deny list to actually match the repo's risks:
   `Bash(git push*origin*)`, `Bash(git push -f*)`, `Bash(*--force*)`,
   `Bash(rm -rf*)`, `Bash(python -m pytest tests*)`, `Bash(pytest tests*)`,
   `Bash(git add -A*)`, `Bash(git add .*)`, `Bash(git commit -a*)`. Confirm
   wording so legitimate flows are not over-blocked.

4. [SAFE] WIRE `sessionstart_context.py` into `SessionStart` (stdout is added
   to context). It injects the north-star + binding invariants every session
   -- cheaper and more reliable than relying on MEMORY/CLAUDE.md being read.

5. [SAFE] WIRE `posttooluse_warn.py` as a PostToolUse Edit|Write hook. It is
   non-blocking (warn-only) and flags >300-LOC files and human-gated-path
   edits -- directly serving the LOC and human-gated invariants at near-zero
   cost.

6. [SAFE] Delete (or git-clean) the ~80 stale `.claude/worktrees/*` settings
   files. They are leftover agent worktrees; removing them speeds up every
   Glob/Grep over `.claude/` (the audit's Glob timed out because of them).

7. [SAFE] Remove the no-op `~/.claude/settings.local.json` empty allow block
   and the redundant `Bash(python -c "import tensorrt")` allow entry (covered
   by `"*"`). Pure cleanup.

8. [SAFE] Add a `nba-ai-system/.claude/settings.json` (tracked-but-gitignored
   per repo rules, OR kept local) that holds the repo-specific hook wiring +
   deny list, instead of depending on the user-global file. Makes the repo's
   guardrails self-contained and portable to RunPod / fresh clones.

9. [SAFE] Replace `conda run -n basketball_ai python ...` in the two vault
   hooks with a direct path to the env's python
   (`C:/Users/neelj/miniconda3/envs/basketball_ai/python.exe ...` or
   equivalent), eliminating the conda-resolver latency on every session
   boundary. Verify the exact env path before applying.

10. [SAFE/RISKY-mixed] Add a curated read-only Bash allowlist so that IF the
    user ever drops `bypassPermissions` (rec 2) the common loop never prompts:
    `Bash(git status*)`, `Bash(git log*)`, `Bash(git diff*)`,
    `Bash(git rev-parse*)`, `Bash(ls*)`, `Bash(cat*)`, `Bash(python -m pytest
    tests/*::*)` and the per-file pattern `Bash(*python -m pytest tests/*.py*)`.
    SAFE to add (additive); only matters once bypass is off, so pair with rec 2.

### Bonus config tweaks
- Consider scoping `effortLevel: "max"` down for routine sessions (token cost);
  keep `max` only for the build loop. [SAFE-ish, behavior tradeoff -> confirm.]
- The `gsd-context-monitor` PostToolUse hook is good context hygiene; keep it.

---

## 7. Auto-apply vs confirm matrix

| Rec | Action | Verdict |
|-----|--------|---------|
| 4 | Wire sessionstart_context.py | SAFE auto-apply |
| 5 | Wire posttooluse_warn.py (warn-only) | SAFE auto-apply |
| 6 | Clean stale worktree settings files | SAFE auto-apply |
| 7 | Remove no-op local + redundant allow | SAFE auto-apply |
| 8 | Add repo-local settings.json with wiring | SAFE auto-apply |
| 9 | De-conda the vault hook commands | SAFE (verify env path) |
| 10 | Add read-only Bash allowlist | SAFE (additive) |
| 1 | Wire pretooluse_guard.py (blocking) | CONFIRM -- can block expected cmds |
| 2 | Drop global bypassPermissions | CONFIRM -- changes safety posture |
| 3 | Harden deny list | CONFIRM -- wording / over-block risk |

NOTE: this audit made NO changes. All of the above are recommendations only.
