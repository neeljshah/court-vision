# Installed Toolkit -- What This Claude Code Environment Already Gives You

_2026-06-16. The skills / subagents / tools actually available in this repo's Claude Code session,
mapped to concrete uses for the calibrated sports predictor + React board. (Capabilities the research
briefs describe in the abstract -- here is what is literally on hand right now.)_

## Orchestration primitives (the highest-leverage, already used tonight)

- **Workflow** -- deterministic multi-agent fan-out (the tool that ran the 28-agent research fleet). Use for:
  parallel modeling experiments, adversarial verification of any "we beat the close" claim, parallel
  per-sport pipelines, broad audits. Default to pipeline(); barrier only when a stage needs all prior results.
- **Agent / subagents** (`Explore`, `Plan`, `general-purpose`, `claude`, custom) -- context isolation: route
  file-heavy reads (signal-catalog sweeps, vault reads) to `Explore` so the main session only gets summaries.
- **ScheduleWakeup / Monitor / CronCreate** -- self-paced loops + scheduled cloud runs (nightly eval gate,
  benchmark, drift check) + log monitors. The "run the gate every night and alert on drift" mechanism.
- **TodoWrite / EnterPlanMode+ExitPlanMode** -- plan-before-multi-file-change (the #1 quality lever per the brief).
- **EnterWorktree** -- isolated git worktree for parallel edits without collision (useful while another session is live).

## Research + reasoning

- **/deep-research** -- fan-out web research + adversarial verification + cited synthesis. Use for any new
  external question (a new data source, a modeling technique, a competitor) -- it is the lighter-weight
  single-question version of what the Workflow fleet did tonight.
- **WebSearch / WebFetch** -- direct web access (confirmed working). Cite sources.
- **claude-code-guide** (agent) -- authoritative Q&A on Claude Code / Agent SDK / Claude API. Use BEFORE acting
  on any volatile Claude-specific detail (flags, SDK calls) instead of trusting a brief's snapshot.
- **/claude-api** -- reference for model ids, pricing, params, tool use, caching, token counting, migration.

## Build velocity + quality (point these at roadmap items 1-4)

- **/code-review** (and `ultra` for a deep cloud review) -- review the diff for bugs before any local commit.
  This is the Opus-diff-review step the build-loop blueprint recommends; it already exists.
- **/simplify** -- reuse/efficiency/altitude cleanup pass.
- **/verify** -- run the app and observe behavior to confirm a change actually works (used implicitly via the
  CDP screenshots on the front end; formalize for the board).
- **/security-review**, **/review** (PR) -- security pass + PR review.
- **/fewer-permission-prompts**, **/update-config**, **/keybindings-help** -- tune the harness itself.
- **/init** -- (re)generate CLAUDE.md; relevant to the "refactor CLAUDE.md < 200 lines" roadmap item.
- **GSD suite** (`/gsd:new-project`, `plan-phase`, `execute-phase`, `verify-work`, `map-codebase`,
  `add-tests`, `debug`, ...) + the `gsd-*` agents -- a full plan -> execute -> verify methodology with atomic
  commits and state tracking. A ready-made framework for running the roadmap phases with guarantees; consider
  `/gsd:plan-phase` for the eval-gate (N1) build.

## Front end (the live board -- already built, but the toolkit remains)

- **/stitch-design, /enhance-prompt, /react-components, /shadcn-ui, /design-md, /stitch-loop** -- Stitch design
  generation + React component scaffolding + shadcn guidance. Use for any new board view (e.g. the pregame->live
  hero interaction, the calibration-record panel) or a marketing/landing page for the productization step.
- **/remotion** -- generate walkthrough videos (a product demo of the calibration record / hero interaction).
- **DesignSync** -- sync a local component library to a claude.ai design project.

## The sports pipeline (project-specific skills already installed)

- **/benchmark** -- full NBA tracker benchmark (download clip -> track -> evaluate -> cross-validate vs NBA Stats
  -> log to vault -> suggest next fix). A natural nightly cron target.
- **/run-pipeline, /pipeline-fullgame** -- process a game clip end-to-end (tracking -> enrichment -> features ->
  analytics) and log to the vault. The CV-moat (L1) workhorse.
- **/train-checkpoint** -- start/resume training for any module with checkpointing + metric logging.
- **/debug-cv** -- diagnose CV failures (ball detection, team classification, homography, re-ID).
- **/dataset-status** -- dataset status check.
  These already encode the existing funnel; the build-loop blueprint's advice is to formalize them as
  `.claude/skills/` entries with `disable-model-invocation: true` for the side-effectful ones.

## Automation + comms

- **/schedule, /loop** -- recurring cloud agents / interval loops (the eval gate + drift ledger on a cron).
- **PushNotification / RemoteTrigger** -- alert on a drift event; trigger a remote run.
- **Gmail / Google Calendar / Google Drive MCP** (auth required) -- e.g. email the weekly calibration report,
  or drop the track-record ledger snapshot in Drive. Authenticate only if you actually want these.

## How this maps to the roadmap (quick reference)

| Roadmap item | Use these now |
|---|---|
| N1 eval gate | `/gsd:plan-phase` -> Workflow (parallel build) -> `/code-review` -> per-file pytest; `/claude-api` for any API detail |
| N3 in-game blend | Workflow (build in `domains/`), `/verify`, the eval gate as the judge |
| N4 hooks/skills | the build-loop blueprint + `/update-config`; human-confirm shared `.claude/` edits |
| X1 freshness | `/deep-research` for sources, structured-output extraction agents |
| X3 ledger/drift | `/schedule` + `ScheduleWakeup` + `PushNotification`, nightly headless run |
| L1 CV moat | `/run-pipeline`, `/train-checkpoint`, `/debug-cv`, `/benchmark`; Workflow orchestrator-workers for enrichment fan-out |
| Productize | `/stitch-design`, `/react-components`, `/remotion` for a demo |

**Note:** prefer the installed `/code-review`, `/deep-research`, and `claude-code-guide` over re-deriving
things from scratch -- they are tuned and authoritative. Verify any volatile Claude-specific detail with
`claude-code-guide` or `/claude-api` before relying on a brief's 2026-06-16 snapshot.
