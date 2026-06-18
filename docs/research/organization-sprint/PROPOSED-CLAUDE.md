<!--
PROPOSED slim CLAUDE.md (<=200 lines). Detail moved into .claude/rules/*.md.
This is a PROPOSAL for the human to review. Do NOT overwrite the real CLAUDE.md
with this until approved. ASCII only.

APPLY NOTE: this file lives in docs/research/organization-sprint/, so any relative
link written as ../../ or ../../../ is relative to THIS dir. Before copying to the
repo-root CLAUDE.md, rewrite link prefixes to be repo-root-relative
(e.g. ../../PLATFORM.md -> docs/PLATFORM.md ; ../../../README.md -> README.md).
-->

## CourtVision -- Agent Onboarding

**What:** a domain-agnostic, calibrated multi-sport forecasting + decision engine.
Origin = an NBA broadcast-video CV pipeline; now one converged predictor across
NBA, MLB, Soccer, Tennis. Funnel: DATA -> SIGNALS -> MODELS -> ENGINES ->
PREDICTIONS -> INTELLIGENCE, re-validated at every stage by an agentic loop.

**Architecture:** sport-blind `kernel/` (validated machinery) + `domains/<sport>/`
adapters (`predictor.py`: `cohesive_read` pregame, `live_read` in-game). Adding a
sport = mostly the adapter. Full narrative: [docs/PLATFORM.md](../../PLATFORM.md).

**Built by:** [Neel Shah](https://neelshahportfolio.netlify.app) -- solo architect of
an agentic build pipeline (1,470 commits). [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com)

---

### Read these first (cold-start, in order)

1. **[docs/JOB_EVIDENCE_PACKET.md](../../JOB_EVIDENCE_PACKET.md)** -- the honest,
   adversarially-audited account + the do-not-claim list. **The truth source.**
2. **[README.md](../../../README.md)** -- end-to-end funnel narrative, honest numbers.
3. **[docs/PLATFORM.md](../../PLATFORM.md)** -- kernel/adapter architecture, 4-sport state.
4. **[docs/PUBLIC_EVIDENCE.md](../../PUBLIC_EVIDENCE.md)** -- 60-second funnel scan |
   **[docs/INTELLIGENCE.md](../../INTELLIGENCE.md)** -- intelligence-layer manifest.

**Don't:** full-read `ROADMAP.md` (167KB) or walk `src/prediction/` (~130 modules,
mostly research surface). Load specific files from the *Task -> Files* table only
when actually editing.

---

### Binding rules (now path-scoped in `.claude/rules/` -- they auto-load)

| Rule file | What it enforces |
|---|---|
| `.claude/rules/human-gated-paths.md` | `src/ kernel/ api/ scripts/team_system/ intel/` are HUMAN-GATED -- build in `scripts/platformkit/` or `domains/<sport>/` instead; propose gated changes under `docs/research/`. |
| `.claude/rules/data-vault-nocommit.md` | NEVER `git add data/` or `vault/`; targeted staging only; origin is PUBLIC. |
| `.claude/rules/no-edge-claims.md` | Calibration not edge; honest reject = success; never print retracted +18.38% / 0.119 / +54% / 78.11 / 8.94 / 54.57. |
| `.claude/rules/bash-cwd-prefix.md` | Prefix every bash with `cd /c/Users/neelj/nba-ai-system &&`; per-file tests ONLY (full suite freezes the box). |

Quick invariants (detail in the rule files above):
- Local commits only; NEVER push public `origin`. Never write `data/registry/`.
- Never flip a feature flag ON. No $-edge claims anywhere.
- <= 300 LOC/file (spec DATA modules ~600-750 exempt) | type hints | docstrings on public API only.
- Py3.9 | conda `basketball_ai` | CUDA 11.8 | RTX 4060 8GB local.
- Always use the GPU for training. Video headless only (`--no-show`), never `cv2.imshow`.
- Never run `run.py` / `loop_processor.py`. `_VRAM_FLUSH_INTERVAL` in
  `unified_pipeline.py` must be **3000** (not 100).

---

> **Local-only paths** (gitignored, absent from a fresh clone): `docs/CLAUDE-state.md`,
> `.planning/`, `vault/`, `.claude/commands/`, `ROADMAP.md`, `docs/research/`,
> `docs/strategy/`. On a clean clone, skip Vault Auto-Maintenance, the "bot go"
> command files, and any `.planning/`/`ROADMAP.md` reference.
>
> **Current state / open issues / recent fixes:** `docs/CLAUDE-state.md`
> **RunPod launch runbook:** `docs/operations/runpod-runbook.md`

---

### "go" / "start working" -- AUTONOMOUS PLATFORM BUILD

On `go` / `start` / `start working` (or `bot go` / `bot go platform` /
`/build-platform`): read `.claude/commands/build-platform.md` and execute it. The
never-stop builder -- Opus orchestrates/reviews/gates, a parallel Sonnet fleet
writes code, Explore/Haiku search. Builds the kernel/adapter platform from
`.planning/platform/`, self-continues every wake, ends ONLY on `bot stop`
(`python scripts/bot_guards/stop_bot.py`) or `program_complete`. ABSOLUTE
invariants even unattended: never pushes public `origin`, never writes
`data/registry/`, never flips a flag ON, never claims an edge.

**"bot go workday"** (legacy CV/pipeline loop): read `.claude/commands/start-day.md`
(spec `.claude/commands/workday-loop.md`).

---

### Task -> Files (load only what you edit)

| Task | Load only |
|------|-----------|
| Per-sport predictor | `domains/<sport>/predictor.py` |
| Unified matchup CLI | `scripts/platformkit/predict_matchup.py` |
| Proof / scoreboard | `scripts/platformkit/{beat_the_close,ingame}_scoreboard.py` |
| Tracking/detection bug | `unified_pipeline.py` + relevant tracker |
| ML feature | `feature_engineering.py` |
| Prop model | `player_props.py` + `prop_model_stack.py` |
| Betting logic | `betting_portfolio.py` |
| API endpoint | `api/main.py` |
| Batch issue | `batch_season.py` + `unified_pipeline.py` |
| Shot detection | `unified_pipeline.py` (EventDetector section) |
| Homography | `unified_pipeline.py` (_build_panorama, _compute_homography) |
| Re-ID | `osnet_reid.py` + `color_reid.py` |
| Possession MC sim | `src/sim/basketball_sim.py` + `fast_sim.py` |
| In-game projection | `src/prediction/live_engine.py` |
| Signal discovery loop | `src/loop/discovery.py` + `src/loop/orchestrator.py` |

### Key paths

```
domains/<sport>/predictor.py            # cohesive_read (pregame) + live_read (in-game)
scripts/platformkit/predict_matchup.py  # unified cv-matchup CLI
kernel/                                 # sport-blind: loop/ sim/ validation/ decision/ brain/ api/
src/tracking/{advanced_tracker,color_reid,osnet_reid}.py
src/pipeline/unified_pipeline.py        # orchestrator
src/features/feature_engineering.py     # 60+ features
src/prediction/{win_probability,player_props,betting_portfolio}.py
src/sim/basketball_sim.py               # possession Monte Carlo
src/loop/discovery.py                   # LLM-free signal proposer
api/main.py                             # FastAPI (~99 endpoints)
scripts/batch_season.py                 # batch runner
database/schema.sql                     # PostgreSQL
```

---

### Reproduce the proofs (committed fixtures, <60s, fresh clone)

```
python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL --elapsed 0 --home-score 0 --away-score 0
python -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof
python -m scripts.platformkit.ingame_scoreboard       --corpus tests/fixtures/proof
```

---

### Vault Auto-Maintenance (local-only; skip on a clean clone)

When a change affects these, update the matching vault note (minimal edit, dedup --
sharpen the existing entry, never duplicate; do NOT commit `vault/`):
- Model metrics -> `vault/Models/Model Performance.md`
- New CV fix -> `vault/Tracking/Tracker Improvements.md`
- Issue found/resolved -> `vault/Tracking/Open Issues.md`
- Phase status -> `vault/Strategy/Build Phases.md`
- New feature wired -> `vault/Features/Signal Inventory.md`
- New gotcha / design decision -> `vault/Improvements/Engineering Knowledge.md`

The `Stop` hook runs `scripts/vault_session_close.py`; `SessionStart` runs
`scripts/update_vault.py`.
