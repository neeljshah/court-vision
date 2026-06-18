# Claude Code Build-Loop Upgrades: Hooks, Skills, Routing, Nightly Cron, CLAUDE.md Refactor

_Design doc, 2026-06-16. For: roadmap N4 (lock invariants as hooks) + item 8 (build velocity via Claude, the force multiplier). Build location: scripts/hooks/ (new), .claude/skills/ (new), .claude/rules/ (new), docs/operations/ (new); ALL edits to .claude/settings.json flagged HUMAN-CONFIRM because a live session is on branch fullsend-ingame-pregame-execution._

> SCOPE NOTE: this is build-velocity + enforcement plumbing. It creates NO prediction edge. Its only job is to make every item 1-4 land faster and more honestly, and to make the no-push / no-leak / no-edge-claim discipline mechanical instead of a prose request. "Velocity at the wrong target" is the documented risk -- point this loop only at calibration work.

---

## Goal + done-criteria (measurable)

"Shipped + validated" means all five sub-deliverables below are true, verified by the listed concrete check:

1. HOOKS ENFORCE. With the hook block installed, a Bash call of `git push origin main` is REJECTED (exit 2, blocking), `git push --force` REJECTED, `pytest tests/` REJECTED, a bare `python foo.py` is REWRITTEN to `cd /c/Users/neelj/nba-ai-system && python foo.py`, an Edit to `src/sim/basketball_sim.py` emits a human-gate WARNING (non-blocking), and a Write that produces a 340-LOC file emits a >300-LOC WARNING. Each verified by one manual trigger; transcript shows the hook fired.
2. SKILLS EXIST. Five SKILL.md files under `.claude/skills/` (predict-matchup, benchmark, eval-gate, signal-audit, brain-rebuild), each <300 lines, each with valid frontmatter, side-effectful ones carry `disable-model-invocation: true`. Verified: `/eval-gate` is invocable and `predict-matchup` auto-triggers on "predict the matchup" in a fresh session.
3. ROUTING ACTIVE. `CLAUDE_CODE_SUBAGENT_MODEL=haiku` set; `fallbackModel` lists 2+ models; review/plan skills pin `model: opus`. Verified: an Explore subagent reports it ran on Haiku; a forced 529 falls back without aborting the run.
4. NIGHTLY GATE RUNS. A headless `claude -p` job runs the eval-gate + drift check + appends one row to the track-record ledger CSV, writes a JSON log, exits 0 on no-drift / 1 on >1-sigma drift. Verified: one manual `--max-turns` dry run produces a ledger row and a parseable JSON.
5. CLAUDE.md < 200 lines with path-scoped `.claude/rules/` files (kernel human-gate, vault/data no-commit, no-edge-claims). Verified: `wc -l CLAUDE.md` < 200 and the three rule files load when editing matching paths.

Non-goal / explicit anti-criteria: no ROI/edge claim anywhere in any skill description or hook message; no flag flipped ON; no flow that pushes origin.

---

## Design (architecture, data flow, layout under ALLOWED paths)

The enforcement layer is hooks (the only true guarantee). The ergonomics layer is skills (replace repeated typing, isolate noisy context). Routing + fallback cut cost and dodge 529s. The nightly cron makes the eval gate autonomous. The CLAUDE.md refactor moves long-lived prose into path-scoped rules so the root file stays loadable.

```
scripts/hooks/                      # NEW -- all shell, ASCII only, <60 lines each
+-- block_dangerous_bash.sh         # PreToolUse(Bash): block push origin / --force / pytest tests/
+-- prepend_cwd.sh                   # PreToolUse(Bash): updatedInput rewrite to add cd prefix
+-- warn_protected_edit.sh          # PostToolUse(Edit|Write): warn on src|kernel|api|scripts/team_system|intel
+-- warn_file_length.sh             # PostToolUse(Edit|Write): warn if >300 LOC (spec data modules exempt)
+-- _common.sh                      # shared: read hook JSON from stdin via python -c, emit decision JSON

.claude/skills/                     # NEW
+-- predict-matchup/SKILL.md        # auto-invocable (read-mostly); calibrated pregame+in-game one-command
+-- benchmark/SKILL.md              # disable-model-invocation (heavy, side-effectful)
+-- eval-gate/SKILL.md              # disable-model-invocation; model: opus; context: fork
+-- signal-audit/SKILL.md           # context: fork; Explore-style catalog sweep
+-- brain-rebuild/SKILL.md          # disable-model-invocation (rmtree danger -> serialize)

.claude/rules/                      # NEW -- path-scoped, load only when editing matching files
+-- kernel-human-gate.md            # paths: src/**, kernel/**, api/**, scripts/team_system/**, intel/**
+-- vault-data-no-commit.md         # paths: vault/**, data/**
+-- no-edge-claims.md               # paths: ** (always; honesty guardrail)

docs/operations/
+-- nightly-eval-gate.md            # runbook: the headless -p cron + Windows Task Scheduler XML

.claude/settings.json               # HUMAN-CONFIRM: NEW shared file (does not exist yet). Carries hooks
                                    # block + env routing + fallbackModel. settings.local.json stays as-is.

vault/Ledgers/track_record.csv      # NEW append-only (gitignored path); the X3 calibration ledger
```

Data flow, hooks: Claude issues a tool call -> harness serializes the call as JSON on the hook's stdin -> the matching PreToolUse/PostToolUse script reads it, decides, prints a decision JSON on stdout -> harness blocks/rewrites/passes. PreToolUse can return `permissionDecision: "deny"` (block, exit 2) or `hookSpecificOutput.updatedInput` (rewrite the command). PostToolUse returns `additionalContext` (a warning string Claude reads) -- keep it to one line to avoid context bloat.

Data flow, nightly: Windows Task Scheduler (local, has the conda env + data) -> `claude -p` headless with the eval-gate skill text -> runs the real leak-free gate on >=2 corpora -> computes recent Brier/ECE vs 30-day rolling baseline -> appends one ledger row -> writes JSON log -> exit code 0/1 -> on exit 1, a PushNotification.

Why local Task Scheduler not Anthropic cloud cron: the gate needs the conda `basketball_ai` env, the local data/ corpora, and the RTX 4060. Cloud triggers run outside this box and cannot see gitignored data/. Cloud cron is the WRONG tool here; local headless is correct.

---

## Implementation sketch (real, copyable)

### 1. Hooks

`scripts/hooks/_common.sh` -- parse the hook JSON once (avoids brittle pure-bash JSON):
```bash
#!/usr/bin/env bash
# Reads the hook event JSON on stdin, exports HOOK_TOOL, HOOK_CMD, HOOK_PATH.
HOOK_JSON="$(cat)"
get() { printf '%s' "$HOOK_JSON" | python -c "import sys,json;d=json.load(sys.stdin);print(d.get('tool_input',{}).get('$1',''))"; }
HOOK_TOOL="$(printf '%s' "$HOOK_JSON" | python -c "import sys,json;print(json.load(sys.stdin).get('tool_name',''))")"
HOOK_CMD="$(get command)"        # Bash
HOOK_PATH="$(get file_path)"     # Edit|Write
```

`scripts/hooks/block_dangerous_bash.sh` -- PreToolUse(Bash), blocking:
```bash
#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
deny() {  # emit a blocking decision; ASCII only
  python -c "import json,sys;print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':sys.argv[1]}}))" "$1"
  exit 0   # exit 0 with deny JSON = clean block (exit 2 also blocks but stderr-only)
}
# origin is PUBLIC -- never push. Local commits only.
printf '%s' "$HOOK_CMD" | grep -Eq 'git[[:space:]]+push[[:space:]]+(origin|.*--force|-f )' && \
  deny "BLOCKED: push to public origin / force-push is forbidden (local commits only). See .claude/rules/vault-data-no-commit.md"
# full pytest freezes the box -- per-file only
printf '%s' "$HOOK_CMD" | grep -Eq 'pytest[[:space:]]+tests/?([[:space:]]|$)' && \
  deny "BLOCKED: full 'pytest tests/' freezes this box. Run a single file: pytest tests/path/test_x.py -q"
# data/registry is human-gated write target
printf '%s' "$HOOK_CMD" | grep -Eq '>[[:space:]]*data/registry|rm .*data/registry' && \
  deny "BLOCKED: data/registry is human-gated; never write it from an agent."
exit 0   # allow
```

`scripts/hooks/prepend_cwd.sh` -- PreToolUse(Bash), rewrite (cwd is flaky):
```bash
#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
ROOT="/c/Users/neelj/nba-ai-system"
# Skip if already prefixed, already absolute-cd'd, or a pure builtin (cd/ls only).
case "$HOOK_CMD" in
  *"cd $ROOT"*|cd\ *|"") exit 0 ;;
esac
NEW="cd $ROOT && $HOOK_CMD"
python -c "import json,sys;print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','updatedInput':{'command':sys.argv[1]}}}))" "$NEW"
exit 0
```

`scripts/hooks/warn_protected_edit.sh` -- PostToolUse(Edit|Write), non-blocking warning:
```bash
#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
printf '%s' "$HOOK_PATH" | grep -Eq '(^|/)(src|kernel|api|intel)/|scripts/team_system/' || exit 0
python -c "import json;print(json.dumps({'hookSpecificOutput':{'hookEventName':'PostToolUse','additionalContext':'WARNING: HUMAN-GATED path edited. src/kernel/api/scripts.team_system/intel require a human gate -- build in domains/<sport> or scripts/platformkit instead. See .claude/rules/kernel-human-gate.md'}}))"
exit 0
```

`scripts/hooks/warn_file_length.sh` -- PostToolUse(Edit|Write), non-blocking:
```bash
#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
[ -f "$HOOK_PATH" ] || exit 0
# spec DATA modules are exempt (~600-750 L); only warn on code dirs
printf '%s' "$HOOK_PATH" | grep -Eq '\.py$' || exit 0
LOC=$(grep -cve '^[[:space:]]*$' "$HOOK_PATH" 2>/dev/null || echo 0)
[ "$LOC" -gt 300 ] || exit 0
printf '%s' "$HOOK_PATH" | grep -Eqi 'spec|catalog|_data' && exit 0   # data-module exemption
python -c "import json,sys;print(json.dumps({'hookSpecificOutput':{'hookEventName':'PostToolUse','additionalContext':'WARNING: %s is %s LOC (>300 invariant). Split it.'%(sys.argv[1],sys.argv[2])}}))" "$HOOK_PATH" "$LOC"
exit 0
```

`.claude/settings.json` snippet -- HUMAN-CONFIRM (this shared file does NOT exist yet; creating it affects the live session). Hooks + routing + fallback together:
```json
{
  "env": {
    "CLAUDE_CODE_SUBAGENT_MODEL": "haiku",
    "PYTHONPATH": "."
  },
  "fallbackModel": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5"],
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [
        { "type": "command", "command": "bash scripts/hooks/block_dangerous_bash.sh" },
        { "type": "command", "command": "bash scripts/hooks/prepend_cwd.sh" }
      ]}
    ],
    "PostToolUse": [
      { "matcher": "Edit|Write", "hooks": [
        { "type": "command", "command": "bash scripts/hooks/warn_protected_edit.sh" },
        { "type": "command", "command": "bash scripts/hooks/warn_file_length.sh" }
      ]}
    ]
  }
}
```
HUMAN-CONFIRM details: (a) ORDER matters in PreToolUse(Bash) -- run block_dangerous BEFORE prepend_cwd so a blocked command is never rewritten then re-evaluated. (b) `prepend_cwd` uses `updatedInput`; confirm the installed Claude Code version supports `updatedInput` (else degrade prepend to a non-blocking `additionalContext` reminder). (c) Keep the existing `.claude/settings.local.json` permissions untouched; settings.json is additive. (d) Mirror the two `deny` entries already in settings.local (`git push --force`, `git reset --hard`) -- hooks are belt-and-suspenders over permissions, not a replacement.

### 2. Skills -- which workflows + one full example

| Skill | Auto-invoke? | model | context | Why formalize |
|-------|--------------|-------|---------|---------------|
| predict-matchup | yes (read-mostly) | sonnet | inherit | the hero one-command pregame+in-game prediction; run constantly |
| benchmark | NO (disable-model-invocation) | sonnet | fork | heavy, side-effectful (downloads clip, runs pipeline); noisy output |
| eval-gate | NO (disable-model-invocation) | opus | fork | the leak-free gate is the quality bar; needs Opus reasoning; isolate |
| signal-audit | yes | haiku/sonnet | fork | catalog sweep reads many files -> isolate to keep main context clean |
| brain-rebuild | NO (disable-model-invocation) | sonnet | fork | rmtree danger -- NEVER two concurrent; must be explicit-only |

Full example -- `.claude/skills/eval-gate/SKILL.md`:
```markdown
---
name: eval-gate
description: Runs the leak-free walk-forward evaluation gate for a candidate signal or
  model on >=2 corpora and decides SHIP or honest-REJECT. Use when the user asks to gate a
  signal, validate a model, run a backtest, or check whether something beats the devigged
  close. Reports Brier Skill Score, log-loss, reliability, and a Diebold-Mariano test vs the
  Shin-devigged market close with clustered SEs. Honest REJECT is a SUCCESS, never an edge claim.
model: opus
disable-model-invocation: true
context: fork
allowed-tools: Bash, Read, Glob, Grep
---

# Eval Gate (leak-free walk-forward)

Run a candidate through the REAL gate. Decide SHIP only if it passes on >=2 corpora.

## Invariants (NEVER violate)
- Calibration is the bar, NOT raw accuracy (accuracy pulls preds toward the line) and NOT
  bare ECE (gameable by predicting 0.5 -- always pair with a sharpness/resolution check).
- Baseline = the SHIN-DEVIGGED close (not multiplicative devig on lopsided markets).
- Walk-forward EXPANDING window; purge same-team within 48h; embargo 3-day gap.
  Feature selection + tuning happen INSIDE the window. K-fold on time-ordered data is a BUG.
- Vintage alignment: every feature value as-of prediction time (availability_date < game_date).
- >=2 independent corpora (seasons or sports). Single-fold lifts are artifacts.
- "Beats the close" = Diebold-Mariano p<0.05, N>=200, on per-game Brier/log-loss diffs,
  with SEs CLUSTERED by game_id/season (naive SEs run ~3x too narrow). Not a bare point delta.
- NEVER claim $ ROI/edge. Output is calibration accuracy vs the devigged baseline. A clean
  REJECT ("no edge / market efficient") is a valid, documented SUCCESS.

## Steps
1. Identify corpus paths under data/domains/<sport> for the sport in $ARGUMENTS (default: all).
2. Run the gate per corpus (per-file tests only -- NEVER `pytest tests/`, it freezes the box):
   `cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.run_gate --signal $ARGUMENTS --corpus <c>`
3. For each corpus emit: BSS vs devigged close, log-loss, reliability bins, DM stat + clustered p, N.
4. DECISION: SHIP iff PASS on >=2 corpora with DM p<0.05; else REJECT and say which corpus failed.
5. Append one line to vault/Improvements/Engineering Knowledge.md (dedup; sharpen, never duplicate).

## Output (structured)
SPORT | CORPUS | BSS | logloss | DM_p | N | VERDICT  (one row per corpus, then one DECISION line)

WARNING: bash cwd is flaky here -- prefix EVERY command with `cd /c/Users/neelj/nba-ai-system &&`.
WARNING: this skill is read-mostly; it must NEVER flip a flag ON or push to origin.
```

`predict-matchup/SKILL.md` frontmatter (auto-invocable, the hero flow): `model: sonnet`, no disable flag, body wraps `python -m scripts.platformkit.predict_matchup --home <H> --away <A> [--state <q,score>]` and prints the calibration context line ("last OOS Brier; last recalibration date") on startup. `brain-rebuild/SKILL.md` body leads with the hard guardrail: "NEVER run two concurrent brain rebuilds -- both rmtree vault/_Organized (WinError 32); serialize; run the single --strict rebuild yourself after any fleet."

### 3. Model routing + 529 dodge

In settings.json (above): `env.CLAUDE_CODE_SUBAGENT_MODEL=haiku` routes all Explore/read-only subagents to Haiku (cost ~40-50% cut on file-heavy sweeps). Per-skill override pins the high-reasoning skills: `model: opus` in eval-gate (and any plan/review skill). `fallbackModel: ["claude-opus-4-8","claude-sonnet-4-6","claude-haiku-4-5"]` retries down the list on a 529 overload so overnight runs never abort. Memory gotcha confirmed: API-529 overload -> no fleets; fallbackModel is the in-session mitigation, local Opus is the manual one.

### 4. Headless -p nightly cron (local Task Scheduler)

`docs/operations/nightly-eval-gate.md` runbook command:
```bash
cd /c/Users/neelj/nba-ai-system && \
claude -p "Run the /eval-gate skill for all sports, then compute recent 7-day Brier/ECE vs the 30-day rolling baseline from vault/Ledgers/track_record.csv, append one ledger row (ts,sport,n,brier,ece,baseline_brier,drift_sigma), and EXIT 1 if any sport drifted > 1 sigma worse, else EXIT 0." \
  --output-format json \
  --max-turns 30 \
  --max-budget-usd 5 \
  --allowedTools "Bash,Read,Glob,Grep,Edit" \
  --session-id "nightly-gate-$(date +%Y%m%d)" \
  > logs/nightly-gate-$(date +%Y%m%d).json
# on exit 1, fire a desktop/push notification (drift detected)
```
Windows Task Scheduler trigger (daily 02:00): action = `bash -lc "<the command above>"`. Ledger schema (append-only, X3): `ts,sport,n,brier,ece,baseline_brier,drift_sigma,note`. The CSV in `vault/Ledgers/` is gitignored (vault/ is gitignored) -- it is the local validation artifact; the GENERATOR scripts under scripts/platformkit ARE committed so a skeptic reproduces it. Do NOT use `--bare` (it skips hooks -> the no-push guard would not run).

### 5. CLAUDE.md refactor to <200 lines + .claude/rules/

Current CLAUDE.md is 108 lines but mixes onboarding, the Task->Files table, Key Paths, Rules, and vault-maintenance prose. Target: keep architecture + Task->Files + Key Paths + build commands inline; move the three standing constraints into path-scoped rule files so they load ONLY when relevant (and load reliably even if CLAUDE.md is trimmed).

`.claude/rules/kernel-human-gate.md`:
```markdown
---
paths: ["src/**", "kernel/**", "api/**", "scripts/team_system/**", "intel/**"]
---
HUMAN-GATED. Do not edit these files autonomously. Build new code in domains/<sport>
or scripts/platformkit instead. If a change here is truly required, STOP and flag it
for a human gate. <=300 LOC/file (spec DATA modules ~600-750 L exempt). Per-file tests
only -- NEVER `pytest tests/` (it freezes the box).
```
`.claude/rules/vault-data-no-commit.md`:
```markdown
---
paths: ["vault/**", "data/**"]
---
vault/ and data/ are gitignored-local. Never `git add` from these paths. Never write
data/registry/. origin is PUBLIC -- local commits only, NEVER push. Use targeted
`git add <path>`, never `git add -A`.
```
`.claude/rules/no-edge-claims.md` (paths: ["**"], always-on):
```markdown
---
paths: ["**"]
---
Goal = BEST PREDICTIONS: OOS calibration vs the devigged market close. NEVER claim a $
edge / ROI / profit. Honest "no edge / market efficient" outputs are SUCCESSES. The
retracted numbers stay retracted (+18.38% market-follow artifact; endQ3 0.119 Q4-leak;
+54% L5-proxy). LLMs route/extract/synthesize + emit bounded leak-flagged multipliers
only -- the quantitative pipeline computes every probability.
```

---

## Validation plan (leak-free where applicable)

This blueprint is build-tooling, so most validation is behavioral, not statistical -- EXCEPT the eval-gate skill and nightly ledger, which carry the project's full leak-free bar.

Tooling validation (one concrete trigger each):
- block_dangerous_bash: manually issue `git push origin main`, `git push --force`, `pytest tests/`, `echo x > data/registry/y` -> all four return a deny JSON; transcript shows BLOCKED. A benign `git status` passes.
- prepend_cwd: issue `python -c "print(1)"` -> command executed is `cd /c/Users/neelj/nba-ai-system && python -c "print(1)"`. An already-prefixed command is unchanged (idempotent).
- warn_protected_edit / warn_file_length: edit `src/sim/basketball_sim.py` and write a 340-LOC `.py` -> each emits exactly one warning line; an edit to `domains/nba/foo.py` of 200 LOC emits none; a 700-LOC `*_data.py` emits none (exemption).
- skills: fresh session, prompt "predict the matchup NYK vs SAS" -> predict-matchup auto-triggers; `/eval-gate` invocable; `/brain-rebuild` does NOT auto-trigger.
- routing: spawn an Explore subagent -> it reports Haiku; eval-gate reports Opus. Simulate a 529 (or inspect the run log) -> fallback to the next model, run continues.

Eval-gate + ledger validation (the real statistical bar, leak-free):
- Walk-forward EXPANDING window, purge same-team <48h, embargo 3-day gap; feature selection INSIDE the window; vintage alignment availability_date < game_date.
- Metric: Brier Skill Score and log-loss vs the SHIN-devigged close; reliability diagram + ECE-with-sharpness as diagnostics only.
- Test: Diebold-Mariano on per-game Brier/log-loss diffs, p<0.05, N>=200, SEs CLUSTERED by game_id/season.
- Corpora: >=2 independent (e.g., NBA 2023-24 train / 2024-25 test, plus a second sport). A PASS-on-A / REJECT-on-B is a valid finding.
- Ledger drift check: recent 7-day Brier/ECE vs 30-day rolling baseline; alert at >1-sigma worse. The ledger IS the X3 validation artifact.

---

## Effort + sequencing (rough days; dependencies; first things first)

Total ~1.5-2 days of build for the velocity layer (N4 is "half a day"); the skills + ledger add the rest.

1. (0.5 day, NO shared-config touch -- SAFE NOW) Write all of `scripts/hooks/*.sh` + `_common.sh` and test each in ISOLATION by piping a fake hook JSON into the script (`echo '{"tool_name":"Bash","tool_input":{"command":"git push origin x"}}' | bash scripts/hooks/block_dangerous_bash.sh`). No settings.json edit yet -> zero collision risk with the live session.
2. (0.5 day, SAFE NOW) Write the five SKILL.md files + the three `.claude/rules/*.md` files + the `docs/operations/nightly-eval-gate.md` runbook. These are new files, no shared-config conflict.
3. (0.25 day) Refactor CLAUDE.md to <200 lines (it is already 108; mostly move the three standing constraints into the rule files and trim vault-maintenance prose). New-file additions are safe; the CLAUDE.md edit is low-risk but coordinate timing if the live session is also editing it.
4. (HUMAN-CONFIRM, do LAST) Create `.claude/settings.json` with the hooks block + env routing + fallbackModel. This is the ONLY step that touches shared config the live session reads. Apply only after confirming with the human that the fullsend-ingame-pregame-execution session is paused or done -- a settings.json change takes effect on the next tool call and could surprise an active session. Verify each hook fires, then keep.
5. (0.25 day, after step 4) Wire the Windows Task Scheduler nightly job from the runbook; do one manual `--max-turns 5` dry run to confirm a ledger row + parseable JSON before scheduling.

Dependencies: nightly cron (5) depends on eval-gate skill (2) and the ledger schema. Routing (4) depends on nothing but is bundled into the settings.json human-confirm. Hooks (1) and skills (2) are independent and can be built in parallel.

---

## Gotchas + how the honest discipline applies

- HOOKS ARE THE ONLY GUARANTEE. CLAUDE.md and skill bodies are requests; a model under pressure can skip prose. Security-critical rules (no push, no full pytest, no data/registry write) MUST live in the PreToolUse hook, not only in prose. This is the core of N4.
- HOOK OUTPUT COSTS CONTEXT. PostToolUse `additionalContext` is read by Claude -- keep every warning to ONE line. Never dump a full lint report; emit path + count only.
- ORDER + idempotency in PreToolUse(Bash): block BEFORE prepend; prepend must no-op on already-prefixed commands or it double-wraps.
- `--bare` SKIPS HOOKS -- never use it for the nightly run; the no-push guard would be off. Use full headless `-p`.
- updatedInput VERSION RISK: if the installed Claude Code does not support PreToolUse `updatedInput`, degrade prepend_cwd to a non-blocking `additionalContext` reminder instead of silently failing.
- LIVE-SESSION COLLISION: steps 1-3 create only NEW files (zero risk). The settings.json creation (step 4) is the one shared-config touch -- HUMAN-CONFIRM, do last, after the fullsend branch session is paused. Do not edit `.claude/settings.local.json`.
- WINDOWS PATHS: all skill/hook file references use forward slashes (harness runs bash; backslashes fail). cp1252 stdout -> ASCII only in every hook message (no unicode arrows).
- VELOCITY AT THE WRONG TARGET is the documented risk (roadmap item 8). This loop only earns its keep pointed at items 1-4 (calibration/in-game/freshness). It creates no edge.
- HONEST DISCIPLINE BAKED IN: the eval-gate skill description and the no-edge-claims rule both forbid $ROI framing; the gate enforces >=2 corpora + DM test + clustered SEs + Shin devig; the hook blocks the exact actions (push, full pytest, registry write) that would break the no-leak / local-only invariants. A clean REJECT row in the ledger is a SUCCESS, not a failure.
