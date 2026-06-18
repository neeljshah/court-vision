# CLAUDE.md Audit (READ-ONLY) — 2026-06-17

Scope: root `CLAUDE.md`, nested CLAUDE.md files, `.claude/rules/`, and overlap with
auto-memory (MEMORY.md) and `docs/CLAUDE-state.md`. No files were modified.

---

## 1. Inventory (the real, non-worktree files)

| File | Size | Content |
|------|------|---------|
| `CLAUDE.md` (root) | 108 lines / 7.9 KB | Full onboarding: identity, read-order, honest-numbers TL;DR, go-commands, Task->Files, Key Paths, Rules, Vault Auto-Maintenance |
| `apps/quant-dashboard/CLAUDE.md` | 1 line | `@AGENTS.md` (Next.js breaking-changes note) |
| `apps/portfolio-site/CLAUDE.md` | 1 line | `@AGENTS.md` |
| `court-visions/CLAUDE.md` | 1 line | `@AGENTS.md` |
| `.claude/rules/bash-cwd-prefix.md` | 1.2 KB | cwd prefix + per-file tests + bash gotchas |
| `.claude/rules/data-vault-nocommit.md` | 1.3 KB | never commit data/ vault/ |
| `.claude/rules/no-edge-claims.md` | 1.8 KB | calibration-not-profit + retracted numbers |
| `.claude/rules/human-gated-paths.md` | 1.8 KB | gated trees (has YAML `paths:` frontmatter) |
| `docs/CLAUDE-state.md` | 115 lines / 8.7 KB | loaded on demand; current-state log |

The ~95 `*/.claude/worktrees/agent-*/CLAUDE.md` files are git-worktree copies of the
three real files; they are auto-cleaned and out of scope.

The three nested app CLAUDE.md files are ideal: one-line `@AGENTS.md` imports, no bloat. Leave them.

---

## 2. Does it bloat context every turn?

The root `CLAUDE.md` (7.9 KB, ~2k tokens) is injected on every turn. That is **acceptable
in size** by Claude Code norms (the danger zone is ~5k+ tokens / multi-screen files). The
problem is **signal density, currency, and structure**, not raw length. Roughly 35-40% of
the file is low-per-turn-value content that earns its keep only once per session (the read-
order packet, the two go-command paragraphs, Vault Auto-Maintenance) and could move to
on-demand files. `docs/CLAUDE-state.md` is correctly load-on-demand and is NOT a per-turn cost.

---

## 3. Issues found

### A. `.claude/rules/` is NOT wired in (highest-impact gap)
Four well-written, single-purpose rule files exist but **nothing references or loads them**:
- `CLAUDE.md` never mentions `.claude/rules/`.
- `settings.local.json` / `launch.json` have no hook or import that pulls them in.
- Claude Code does NOT auto-load arbitrary `.claude/rules/*.md`; they must be `@`-imported
  from CLAUDE.md (or injected by a hook) to take effect.

Result: the hardest invariants (no-edge-claims, no-commit data/vault, human-gated paths,
per-file-tests/cwd-prefix) currently live ONLY in MEMORY.md and the redundant prose inside
CLAUDE.md. The rules dir is dead weight until imported. Note `human-gated-paths.md` already
carries a `paths:` frontmatter selector — it was clearly authored to be a path-scoped rule.

### B. Heavy duplication across CLAUDE.md / rules / MEMORY.md
The same invariants are stated 2-3 times in different words:
- "Max 300 LOC/file" — CLAUDE.md Rules + human-gated-paths.md + MEMORY.md.
- Per-file-tests / never full pytest — CLAUDE.md (implicit) + bash-cwd-prefix.md + MEMORY.md.
- Never push / data-vault gitignored / no-edge — CLAUDE.md TL;DR + 3 rule files + MEMORY.md.
- Local-only paths list — appears in CLAUDE.md blockquote AND data-vault-nocommit.md.
This is drift-prone: three copies of "300 LOC" can diverge. Pick ONE home per invariant.

### C. Stale / conflicting facts
- **Py version conflict:** `CLAUDE.md` Rules says **Py3.9**; MEMORY/`reference-runpod` says
  Python 3.12 on RunPod. State doc implies 3.9 local. At minimum label which is local vs RunPod.
- **`docs/CLAUDE-state.md` dated 2026-05-27** while today is 2026-06-17 — ~3 weeks stale; it
  still describes the R15-R21 betting-daemon/scraper wave and a `master`/`e5fded39` head,
  predating the entire platform/kernel + productize-sellable + org-sprint work in MEMORY.md.
  The state doc and MEMORY.md now tell two different stories about "current state."
- **Identity drift:** root CLAUDE.md leads with "AI-native NBA intelligence platform";
  state doc says platform identity is "The Renaissance of Sports"; MEMORY north-star is the
  4-sport calibrated predictor. Three names for one project.
- **"~99 endpoints / 12 routers"** in two places — fine, but it is a number that rots; better
  as "see api/main.py" than a hard count repeated.

### D. Conflicting autonomy guidance
- CLAUDE.md Rules: "No permission prompts — execute autonomously."
- human-gated-paths.md: agents must NOT edit `src/** kernel/** api/** scripts/team_system/** intel/**`
  without explicit human confirmation.
These coexist but read as a contradiction unless the reader already knows the gated-paths
carve-out. The autonomy line needs the gated-paths exception inline.

### E. Verified-good (no action)
- All 16 Key-Path / Task->Files targets resolve on disk (unified_pipeline, win_probability,
  player_props, betting_portfolio, basketball_sim, fast_sim, live_engine, discovery,
  orchestrator, feature_engineering, api/main, batch_season, schema.sql, prop_model_stack,
  osnet_reid, color_reid). The Task->Files table is the strongest, most CLAUDE-Code-idiomatic
  part of the file — keep it.
- `kernel/`, `domains/`, `scripts/platformkit/`, `.planning/platform/`, `.claude/commands/`
  all exist; the build-platform.md and start-day.md command files exist. The go-command
  prose is accurate, just verbose.

### F. Minor
- Unicode arrows/em-dashes throughout CLAUDE.md and rules, despite the ASCII-only cp1252
  console gotcha. Harmless in markdown but inconsistent with the stated discipline.
- The "If you're a Claude landing cold" packet + TL;DR honest-numbers block (~lines 11-25)
  is once-per-session orientation paying a per-turn tax.

---

## 4. Best-practice gap vs Claude Code norms

| Best practice | Current state |
|---------------|---------------|
| Concise, high-signal, scannable | Partly — Task->Files/Key Paths great; onboarding+vault sections bloat |
| Hard invariants stated once, unambiguously | Violated — invariants triplicated, rules dir unwired |
| Task -> files mapping | Present and good |
| On-demand detail via imports/links | State doc is on-demand (good); rules dir should be `@`-imported, is not |
| No stale/rotting facts | Violated — state doc 3 weeks stale, Py3.9 conflict, identity drift |
| Path-scoped rules for gated trees | Authored (frontmatter) but inert |

---

## 5. Proposed slimmer, cohesive structure

Target root `CLAUDE.md`: ~45-60 lines / ~3.5-4.5 KB per-turn. Move once-per-session and
detailed content out; make the rules dir live.

### Recommended root CLAUDE.md outline

```
# CourtVision — Agent Guide

<1-2 line identity: 4-sport calibrated forecasting platform; kernel/ + domains/<sport>/>
<1 line: cold-start? read docs/JOB_EVIDENCE_PACKET.md (truth source) then README.md>

## Hard invariants  (THE one home — short pointers, detail in @rules)
@.claude/rules/no-edge-claims.md
@.claude/rules/data-vault-nocommit.md
@.claude/rules/human-gated-paths.md
@.claude/rules/bash-cwd-prefix.md
(+ a 4-6 bullet quick-list mirroring the rule titles, so the gist is inline)

## Task -> Files            (KEEP AS-IS — highest value)
## Key Paths               (KEEP — trim to ~10 lines, drop rotting endpoint count)

## Build conventions       (the de-duplicated survivors of today's "Rules")
- env: conda basketball_ai; Py3.9 LOCAL / 3.12 RunPod; CUDA; GPU-default
- <=300 LOC/file (spec/DATA exempt)  [single source; rules echo it for gated work]
- autonomous EXCEPT human-gated paths (see rule); never run run.py/loop_processor.py;
  video headless only
- current state + open issues -> docs/CLAUDE-state.md (load on demand)

## Commands                (1-2 lines, pointer only)
- "go"/"start" -> .claude/commands/build-platform.md (never-stop platform build)
- "bot go workday" -> .claude/commands/start-day.md
```

### Cut from per-turn CLAUDE.md (move, don't delete)
- **Cold-start read packet + honest-numbers TL;DR (lines 11-25):** move to a
  `docs/ONBOARDING.md` (or keep the truth-source one-liner + a link). It is session-once,
  not turn-by-turn. The retracted-numbers list already lives authoritatively in
  no-edge-claims.md — do not duplicate it here.
- **Vault Auto-Maintenance block (lines 96-108):** move whole section to
  `.claude/rules/vault-maintenance.md` (new) or `docs/operations/`. It is a conditional
  "when you change X, update vault note Y" workflow, irrelevant on most turns and absent on
  a clean clone anyway.
- **Long go-command paragraphs (lines 34-48):** compress to the two pointer lines above;
  the detail already lives in the command files they point to.
- **Local-only paths blockquote:** keep ONE copy in data-vault-nocommit.md; replace the
  CLAUDE.md copy with a one-line pointer.

### Keep inline (per-turn worth it)
- Identity (1-2 lines), Task->Files table, trimmed Key Paths, the de-duplicated build
  conventions, the `@`-imports to the four rules, command pointers.

### Wire the rules (the key fix)
Add the four `@.claude/rules/*.md` import lines under "Hard invariants" so they actually
load. Consider whether human-gated-paths (with its `paths:` frontmatter) should be a
path-scoped activation rather than always-on, to keep per-turn cost down.

### Fix currency (one-time)
- Refresh or clearly date-stamp `docs/CLAUDE-state.md` to the post-org-sprint reality
  (or add a top banner: "superseded by MEMORY.md START-HERE entries as of 2026-06-16").
- Resolve the Py3.9-vs-3.12 line (label local vs RunPod).
- Pick ONE project name (suggest: lead with the 4-sport calibrated-predictor framing that
  matches the north star; mention "CourtVision / Renaissance of Sports" once as aliases).

---

## 6. Net effect
- Per-turn token cost drops ~40% (7.9 KB -> ~4 KB) while RAISING enforcement, because the
  four invariant rules go from inert to actually imported.
- Each invariant gets exactly one authoritative home; CLAUDE.md holds pointers + the
  Task->Files / Key Paths tables that are its highest-value, turn-relevant content.
- Stale state and name/version conflicts removed or dated.
- Nested app CLAUDE.md files unchanged (already optimal).
```
