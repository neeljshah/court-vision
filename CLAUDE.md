## CourtVision — Agent Onboarding

**What:** AI-native NBA intelligence platform evolving toward a domain-agnostic, multi-sport forecasting + decision engine. CV tracking + NBA API + 85 trained signals + 80-artifact intelligence layer → Monte Carlo possession sim → calibrated predictions. Claude agents autonomously discover, validate, and ship (or reject) prediction signals.
**Architecture direction:** sport-blind `kernel/` (the validated machinery) + `domains/<sport>/` adapters — see [docs/PLATFORM.md](docs/PLATFORM.md).
**Stack:** YOLOv8n → SIFT homography → Kalman+Hungarian → OSNet re-ID → EasyOCR → EventDetector → FastAPI → Claude agents
**Built by:** [Neel Shah](https://neelshahportfolio.netlify.app) — solo human architect/director of an agentic build pipeline (1,470 commits, Mar–May 2026). [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com)
**The funnel:** DATA → SIGNALS → MODELS → ENGINES → PREDICTIONS → INTELLIGENCE, with an agentic loop that re-validates every stage.

---

### If you're a Claude landing on this repo cold

Read these files in order, nothing else, before doing anything else:

0. **[.planning/NOW.md](.planning/NOW.md)** — the SINGLE SOURCE OF TRUTH for what's done / what's next (read first, 30s; update before you finish). Don't re-derive state from scattered docs.
1. **[docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md)** — the honest, adversarially-audited account: every claim's proof artifact + the do-not-claim list. **This is the truth source for any number.**
2. **[README.md](README.md)** — funnel narrative end-to-end with honest numbers + architecture.
3. **[docs/PUBLIC_EVIDENCE.md](docs/PUBLIC_EVIDENCE.md)** — 60-second funnel scan · **[docs/INTELLIGENCE.md](docs/INTELLIGENCE.md)** — 80-artifact intelligence-layer manifest.

**Numbers/claims live in [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md), not here** (so this file can't drift). Market is efficient; honest calibration wins only. **Never re-print the retracted +18.38% / endQ3-0.119 / +54%-as-edge / 78.11 numbers as current** — full list + framing in @.claude/rules/no-edge-claims.md.

**Don't:** full-read `ROADMAP.md` (167KB) or walk `src/prediction/` (~130 modules — most research surface). Load files from the *Task → Files* table below only when actually editing.

---

> **Current state, open issues, recent fixes:** `docs/CLAUDE-state.md`
> **RunPod launch runbook:** `docs/operations/runpod-runbook.md`
>
> ⚠️ **Local-only paths** (gitignored — absent from a fresh clone): `docs/CLAUDE-state.md`, `.planning/`, `vault/`, `.claude/commands/`, `ROADMAP.md`, `docs/research/`, `docs/strategy/` (internal strategy/ops, kept private). Skip "Vault Auto-Maintenance", the "bot go" command files, and any `.planning/`/`ROADMAP.md` reference when working from a clean clone.

### "go" / "start working" — AUTONOMOUS NEVER-STOP PLATFORM BUILD (default)
When the user's message is `go` / `start` / `start working` (or `bot go` / `bot go platform` /
`/build-platform`), read `.claude/commands/build-platform.md` and execute it. This is the
**never-stop** builder: Opus orchestrates·reviews·gates · **Fable makes every decision the user
would make** (the loop never waits on a human — human-gates/`review:human`/for-review are all
Fable-adjudicated) · a **2–3× parallel Sonnet fleet** writes code · Explore/Haiku search. It builds
the kernel/adapter platform + NBA-completeness from `.planning/platform/` and **keeps building for
days** — self-continues every wake, ending ONLY on `bot stop` or `program_complete`. First run
bootstraps its own scripts (H0). `bot stop` (`python scripts/bot_guards/stop_bot.py`) brakes it
cleanly. ABSOLUTE invariants it never violates even unattended: never writes `data/registry/`,
never flips a flag ON, never claims an edge, never uses `--force`. Push to public `origin master`
is ALLOWED (2026-07-09 user override) -- secrets-scan first, targeted `git add` (never `data/`/`vault/`).

### "bot go workday" — legacy CV/pipeline workday loop
When the user's message is explicitly `bot go workday`, read `.claude/commands/start-day.md`
(loop spec `.claude/commands/workday-loop.md`).

### Task → Files
| Task | Load only |
|------|-----------|
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

### Key Paths
```
src/tracking/advanced_tracker.py      # AdvancedFeetDetector
src/tracking/color_reid.py            # TeamColorTracker
src/tracking/osnet_reid.py            # OSNet re-ID 512-dim
src/pipeline/unified_pipeline.py      # Orchestrator
src/features/feature_engineering.py  # 60+ features
src/prediction/win_probability.py     # XGBoost win prob
src/prediction/player_props.py        # 7 prop models
src/prediction/betting_portfolio.py  # Kelly + CLV
src/sim/basketball_sim.py             # Possession Monte Carlo
src/loop/discovery.py                 # LLM-free signal proposer
api/main.py                           # FastAPI (~99 endpoints, 12 routers)
scripts/batch_season.py               # Batch runner
database/schema.sql                   # PostgreSQL
```

### Rules
Binding invariants live in `.claude/rules/` and load via these imports (do not restate them here):
@.claude/rules/no-edge-claims.md
@.claude/rules/data-vault-nocommit.md
@.claude/rules/human-gated-paths.md
@.claude/rules/bash-cwd-prefix.md

- Py3.10.20 local (conda `basketball_ai`, CUDA 11.8, RTX 4060 8GB; verified 2026-07-03) | **RunPod is Py3.12** | type hints | docstrings on public API only
- Max 300 LOC/file | `# ... existing code ...` for unchanged blocks | Models → `data/models/` | Logs → `vault/Improvements/`
- Never re-read data dirs unless asked | Never run: `run.py`, `loop_processor.py` | Video headless only (`--no-show`), never `cv2.imshow`
- **Tests: PER-FILE ONLY** (`python -m pytest tests/path/test_one.py -q`); a full `pytest tests/` FREEZES the box — never run it
- Permissions: execute autonomously, but human-gated paths (see rule) need confirmation; a PreToolUse hook hard-blocks full-pytest + `--force` (push-to-origin is ALLOWED per the 2026-07-09 override -- secrets-scan first)
- On `/compact` or auto-compaction, PRESERVE: modified-file list, test commands run, which flags stay OFF, and the no-edge + human-gated invariants
- Full plan: `.planning/ROADMAP.md` (167KB — grep/section-read only, NEVER full-read) | Session log: `vault/Sessions/Decision Log.md`
- `_VRAM_FLUSH_INTERVAL` in `unified_pipeline.py` must be **3000** (not 100)

### Vault (Obsidian Brain) — auto-maintenance RETIRED
`vault/` is brain-only + gitignored now; the old per-note targets (Model Performance / Open Issues / Build Phases / Signal Inventory) are ARCHIVED and the Stop/SessionStart hooks SKIP these writes ("brain-only vault detected"). Don't hand-update vault notes — durable learnings go to auto-memory instead.


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](docs/INDEX.md) - [Home](README.md) - [Glossary](docs/GLOSSARY.md)
