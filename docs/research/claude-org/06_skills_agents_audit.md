# Skills + Subagents + Commands Audit (2026-06-17)

READ-ONLY audit of the Claude Code automation surface for the NBA AI / CourtVision platform.
Scope: project `.claude/{skills,agents,commands}`, user `~/.claude/{skills,agents,commands}`.

---

## 1. Inventory counts

| Surface | Project-level | User-level | Total |
|---|---|---|---|
| Skills | 7 | 7 (Stitch/design, symlinks) | 14 |
| Subagents | 7 | 12 (gsd-*) | 19 |
| Slash commands | 17 + `gsd/` (empty dir) | 6 + `gsd/` | 23 |

Built-in/plugin skills also present at runtime (deep-research, code-review, simplify, verify,
run, schedule, loop, update-config, claude-api, gsd:* command-skills, etc.) — not user-authored,
not audited for redundancy here except where they overlap a hand-rolled one.

### 1a. Project SKILLS (C:\Users\neelj\nba-ai-system\.claude\skills)

| Skill | Purpose | Triggers on | Model | Notes |
|---|---|---|---|---|
| brain-rebuild | rmtree+regenerate person-free Obsidian brain | explicit only ("rebuild the brain") | sonnet | `disable-model-invocation`, side-effectful, good guardrails |
| pipeline-rebuild | full data->brain pipeline + vault rebuild | explicit only ("run the pipeline") | sonnet | `disable-model-invocation`; OVERLAPS brain-rebuild (both call brain_pipeline.py) |
| calibration-report | per-sport Brier/ECE scoreboard | "calibration report", "Brier", "ECE" | sonnet | clear |
| cross-sport-benchmark | one rating object scored OOS 4 sports | "benchmark", "OOS readout" | sonnet | clear; some conceptual overlap w/ calibration-report |
| eval-gate | fail-closed golden-set + WF/shin/freshness scoreboard | "eval gate", "is the gate green" | sonnet | clear, keystone |
| predict-matchup | calibrated pre/in-game forecast for one matchup | "predict", "who wins", "win probability" | sonnet | clear, buyer-facing entrypoint |
| signal-audit | run signals through real leak-free gate -> SHIP/REJECT | "signal audit", "does this have an edge" | sonnet | clear, honesty-contract baked in |

Descriptions here are EXEMPLARY — explicit trigger-phrase lists, model set, allowed-tools scoped,
side-effectful ones gated off auto-invoke. This is the gold standard the rest should match.

### 1b. User SKILLS (~/.claude/skills -> ~/.agents/skills)

design-md, enhance-prompt, react-components, remotion, shadcn-ui, stitch-design, stitch-loop.
All Stitch/UI-design tooling, symlinked. Unrelated to the sports platform; harmless, leave as-is.

### 1c. Project SUBAGENTS (.claude/agents)

| Agent | Purpose | Model | Status |
|---|---|---|---|
| cv-code-reviewer | diff reviewer + invariant enforcer | opus | CURRENT, strong |
| cv-explore | read-only file/vault/catalog sweeper | haiku | CURRENT, strong |
| cv-honesty-gate | adversarial REFUTED-by-default edge-claim gate | opus | CURRENT, keystone |
| cv-plan | goal -> sequenced invariant-respecting plan | sonnet | CURRENT, strong |
| cv-quality-auditor | tracking-JSON quality (ball_valid_pct, fps, reID) | haiku | STALE-ish (CV-pipeline era) |
| ingest-monitor | video ingest queue dashboard | haiku | STALE-ish (uses `conda run`) |
| prop-r2-tracker | R2 of 7 prop models vs targets | haiku | STALE (hardcoded 2026-05-16 R2 table, `conda run`) |

The four newer `cv-*` agents (reviewer/explore/honesty-gate/plan) are well-described, models are
sensibly tiered (opus for judgment, sonnet for planning, haiku for search). The three older
haiku agents are CV/prop-era and predate the 4-sport platformkit pivot.

### 1d. User SUBAGENTS (~/.claude/agents) — 12 gsd-* agents

gsd-codebase-mapper, gsd-debugger, gsd-executor, gsd-integration-checker, gsd-nyquist-auditor,
gsd-phase-researcher, gsd-plan-checker, gsd-planner, gsd-project-researcher,
gsd-research-synthesizer, gsd-roadmapper, gsd-verifier. Third-party GSD framework; spawned only by
gsd:* commands. Leave as-is (vendored).

### 1e. Project COMMANDS (.claude/commands)

Loop/orchestrator commands: build-platform, dawn-cycle, deep-build, game-loop, improve-loop,
night-build, pipeline-loop, signal-loop, workday-loop, start-day. Helper/dashboard: cv-add,
cv-pivot, cv-review, cv-status, evening-handoff, ready-check, quant-refresh.

---

## 2. Redundancies to consolidate

1. **brain-rebuild vs pipeline-rebuild (skills).** Both `disable-model-invocation` skills wrap
   `scripts/platformkit/brain_pipeline.py`; pipeline-rebuild = brain-rebuild + `--with-models`.
   Their guardrail text is near-identical (no concurrent rmtree). CONSOLIDATE into one
   `rebuild-brain` skill with a `--with-models` arg-hint; drop the second SKILL.md. (Two
   near-duplicate side-effectful skills is exactly the kind of thing that confuses auto-routing.)

2. **The "run a giant loop forever" commands are heavily overlapping.** night-build, deep-build,
   build-platform, signal-loop, improve-loop, workday-loop, dawn-cycle, game-loop, pipeline-loop
   all describe "Opus orchestrates, Sonnet/Fable execute, never stop, ship-what-survives-the-gate."
   They differ mainly in scope (NBA-only vs 4-sport, signals vs CV vs brain). This is 9 commands
   for ~3 real workflows. CONSOLIDATE to: (a) one **build loop** (4-sport, supersedes
   night-build/deep-build/build-platform), (b) one **signal/improve loop** (supersedes
   signal-loop/improve-loop/workday-loop NBA-modeling parts), (c) one **CV/ingest pipeline loop**
   (supersedes game-loop/pipeline-loop). Keep dawn-cycle/start-day as the poke entrypoints.

3. **cv-quality-auditor + ingest-monitor + prop-r2-tracker (agents) are stale.** All three are
   CV/prop-pipeline-era (last touched 2026-05-16, before the platformkit + 4-sport pivot), use
   `conda run -n basketball_ai` (the rest of the system runs the env python directly), and
   prop-r2-tracker hard-codes a 2026-05-16 R2 table and "MASTER_PLAN.md targets" that the project
   has since superseded (memory says PTS/REB at the data ceiling). RECOMMEND: fold
   prop-r2-tracker's intent into a fresh metrics skill (see gap #3), refresh or retire
   cv-quality-auditor + ingest-monitor only if the CV ingest lane is still active.

4. **calibration-report vs cross-sport-benchmark (skills).** Mild overlap — both produce
   cross-sport calibration readouts. They are distinct enough (per-sport recalibration scoreboard
   vs single-rating-object OOS sweep) to keep BOTH, but their descriptions should cross-reference
   each other so the model picks the right one (benchmark = "is the predictor good", calibration =
   "did recalibration help").

5. **Empty `gsd/` command dirs** exist at both project and user level (0 .md files found under
   project `.claude/commands/gsd/`; gsd commands resolve as skills). Harmless but dead; can remove.

---

## 3. Stale items

- prop-r2-tracker.md — hardcoded R2 numbers + targets, `conda run`, prop-only worldview. STALE.
- ingest-monitor.md, cv-quality-auditor.md — CV-pipeline era, `conda run`. Stale-ISH; valid only
  if the video ingest lane is still live (queue DB + data/tracking/ do still exist on disk).
- game-loop.md (2026-03-27), pipeline-loop.md (2026-03-23) — oldest commands, CV-clip-centric,
  predate the 4-sport + sellable-package direction.
- `conda run -n basketball_ai` appears in 5 files while the canonical interpreter (per deep-build/
  night-build headers) is `C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe`. Inconsistent.

---

## 4. Description / auto-trigger quality

- The 7 project skills + 4 new cv-* agents have EXCELLENT descriptions: explicit "Use when..." +
  literal "Triggers on ..." phrase lists. These will auto-route correctly.
- The 3 stale haiku agents have thin one-line descriptions without trigger phrases — they will
  rarely auto-fire, which is fine since they should be retired/refreshed anyway.
- Loop commands are not auto-triggered (they are slash commands), so trigger-phrase quality is
  moot — but their near-identical purpose statements make it hard for a human to remember which to
  invoke. The consolidation in #2 fixes the human-routing problem.

---

## 5. Gaps — top 5 new skills/agents worth adding

1. **`memory-curate` skill (sonnet, side-effect-light).** MEMORY.md is already OVER its size limit
   (31.6KB vs 24.4KB) and the system warns index entries are too long. A skill that audits
   `~/.claude/.../memory/MEMORY.md` + topic files for: over-limit size, >200-char index lines,
   dead links, duplicate/stale entries, and proposes consolidations. Directly addresses a live,
   self-reported failure. Triggers: "curate memory", "trim MEMORY.md", "fix the memory index".

2. **`state-roadmap` skill (sonnet, read-only).** A single dashboard over `.planning/` — STATE.md,
   ROADMAP.md, PLAN.md files, build_state.json, loop ledger — that reports current milestone,
   what's blocked, what's queued, and what's drifted. cv-status only covers the platform build;
   there is no unified "where does the whole project stand" command. Triggers: "project status",
   "where are we", "roadmap state".

3. **`model-metrics` skill (sonnet).** The honest, non-stale replacement for prop-r2-tracker:
   reads the CURRENT model registry / `_meta.json` files across all 4 sports, reports R2/MAE/Brier
   vs the live baseline (not a hardcoded table), and runs the pkl `n_features_in_` integrity check
   (a memory-flagged expensive bug class). Triggers: "model metrics", "model registry status",
   "R2 readout".

4. **`leak-check` agent (opus, read-only).** Splits the train/inference-parity + leak-free
   verification out of cv-code-reviewer into a focused adversarial agent that, given changed
   feature code, confirms the feature is wired in BOTH the training and inference builders
   (memory: "most expensive bug class") and that no season-final / future / Q4-into-Q3 leak exists.
   Complements cv-honesty-gate (which judges CLAIMS) by judging CODE for leaks pre-commit.

5. **`memory-write` / session-handoff skill (sonnet).** Companion to #1: at end of a work burst,
   distill what happened into a single <200-char MEMORY.md index line + a topic file, following the
   project's kebab-case slug + index-only convention automatically. evening-handoff covers bot-work
   queueing but nothing enforces the memory-format discipline that MEMORY.md keeps violating.

(Honorable mention: a `commands-lint` / self-audit skill that re-runs this very audit on a
schedule, since the loop-command sprawl will recur.)

---

## 6. One-paragraph recommendation

The 7 platformkit skills and the 4 new cv-* agents are the model to follow — keep them. Merge the
two brain-rebuild skills into one, collapse the 9 overlapping "loop forever" commands down to ~3
canonical loops plus the poke entrypoints, and retire/refresh the 3 stale `conda run` haiku agents.
Then add the five gaps above, of which **memory-curate is the single highest-value add** because
MEMORY.md is already failing its own size contract today.
