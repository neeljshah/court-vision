## CourtVision — Agent Onboarding

**What:** AI-native NBA intelligence platform evolving toward a domain-agnostic, multi-sport forecasting + decision engine. CV tracking + NBA API + 85 trained signals + 80-artifact intelligence layer → Monte Carlo possession sim → calibrated predictions. Claude agents autonomously discover, validate, and ship (or reject) prediction signals.
**Architecture direction:** sport-blind `kernel/` (the validated machinery) + `domains/<sport>/` adapters — see [docs/PLATFORM.md](docs/PLATFORM.md).
**Stack:** YOLOv8n → SIFT homography → Kalman+Hungarian → OSNet re-ID → EasyOCR → EventDetector → FastAPI → Claude agents
**Built by:** [Neel Shah](https://neelshahportfolio.netlify.app) — solo human architect/director of an agentic build pipeline (1,470 commits, Mar–May 2026). [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com)
**The funnel:** DATA → SIGNALS → MODELS → ENGINES → PREDICTIONS → INTELLIGENCE, with an agentic loop that re-validates every stage.

---

### If you're a Claude landing on this repo cold

Read these files in order, nothing else, before doing anything else:

1. **[docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md)** — the honest, adversarially-audited account: every claim's proof artifact + the do-not-claim list. **This is the truth source.**
2. **[README.md](README.md)** — funnel narrative end-to-end with honest numbers + architecture.
3. **[docs/PUBLIC_EVIDENCE.md](docs/PUBLIC_EVIDENCE.md)** — 60-second funnel scan · **[docs/INTELLIGENCE.md](docs/INTELLIGENCE.md)** — 80-artifact intelligence-layer manifest.

**TL;DR (HONEST numbers — inflated ones are retracted, see JOB_EVIDENCE_PACKET):**
- **Defensible core:** broadcast video → court coordinates at **~$0.10/game** vs six-/seven-figure Sportradar/Second Spectrum; leak-free prop MAE **PTS ~4.58 / REB ~1.90 / AST ~1.34 / FG3M ~0.88**; win-prob **0.709 acc / 0.193 Brier**; 430 modules, ~38% already sport-agnostic kernel.
- **Betting read (honest):** vs real closing lines the **market is efficient** — break-even-minus-vig overall; **AST ~+4–5% ROI** is the one durable edge (breaks in playoffs). In-play 78%/+54% is an **L5-proxy ceiling**, not realized edge; first real CLV Oct 2026; zero real money placed.
- **The headline is the discipline:** built the harnesses that caught and retracted his own inflated numbers (+18.38% ROI = market-follow artifact; endQ3 0.119 = Q4 leak; +54% = L5 proxy).
- Open gaps: [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).

**Don't:** full-read `ROADMAP.md` (167KB) or walk `src/prediction/` (~130 modules — most are research surface). Read `docs/JOB_EVIDENCE_PACKET.md` first; load specific files from the *Task → Files* table below only when actually editing. **Never re-print the retracted +18.38% / endQ3-0.119 / +54%-as-edge numbers as current.**

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
cleanly. ABSOLUTE invariants it never violates even unattended: never pushes to public `origin`
(private/local only), never writes `data/registry/`, never flips a flag ON, never claims an edge.

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
- Py3.9 | conda: `basketball_ai` | CUDA 11.8 | RTX 4060 8GB local
- Max 300 LOC/file | type hints | docstrings on public API only
- Models → `data/models/` | Logs → `vault/Improvements/`
- `# ... existing code ...` for unchanged blocks
- Never re-read data dirs unless asked
- Never run: `run.py`, `loop_processor.py`
- Video: headless only (`--no-show`), never `cv2.imshow`
- No permission prompts — execute autonomously
- Tests: `python -m pytest tests/ -q`
- Full plan: `.planning/ROADMAP.md` (167KB — grep/section-read only, NEVER full-read) | Session log: `vault/Sessions/Decision Log.md`
- `_VRAM_FLUSH_INTERVAL` in `unified_pipeline.py` must be **3000** (not 100)

### Vault Auto-Maintenance (Obsidian Brain)
When you make changes that affect any of these, update the corresponding vault note:
- Model metrics changed → update `vault/Models/Model Performance.md`
- New CV pipeline fix → append to `vault/Tracking/Tracker Improvements.md`
- Issue resolved or found → update `vault/Tracking/Open Issues.md`
- Phase status changed → update `vault/Strategy/Build Phases.md`
- New feature wired → update `vault/Features/Signal Inventory.md`
- R² or Brier improved → update `vault/Models/Model Performance.md` + relevant model note
- New gotcha / design decision / non-obvious learning → `vault/Improvements/Engineering Knowledge.md` — **dedup**: sharpen the existing entry, never duplicate

Keep updates minimal — change the metric value or add a one-liner. Don't rewrite entire notes.
The `Stop` hook runs `scripts/vault_session_close.py` to append one line to Decision Log + refresh Home.md.
The `SessionStart` hook runs `scripts/update_vault.py` to refresh Home.md.
