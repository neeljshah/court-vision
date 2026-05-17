## CourtVision — NBA CV+ML Pipeline

**What:** Possession-by-possession NBA simulator. CV tracking + NBA API + 75 trained models → 10K Monte Carlo → +EV edges vs sportsbooks.
**Moat:** Spatial CV features (defender_distance, spacing, fatigue) from broadcast video.
**Stack:** YOLOv8n → SIFT homography → Kalman+Hungarian → OSNet re-ID → EasyOCR → EventDetector → FastAPI → Next.js

> **Current state, open issues, recent fixes:** `docs/CLAUDE-state.md`
> **RunPod launch runbook:** `docs/operations/runpod-runbook.md`
> **Ingest system commands:** `docs/operations/runpod-runbook.md#ingest`

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

### Key Paths
```
src/tracking/advanced_tracker.py    # AdvancedFeetDetector
src/tracking/color_reid.py          # TeamColorTracker
src/tracking/osnet_reid.py          # OSNet re-ID 512-dim
src/pipeline/unified_pipeline.py    # Orchestrator
src/features/feature_engineering.py # 60+ features
src/prediction/win_probability.py   # XGBoost win prob
src/prediction/player_props.py      # 7 prop models
src/prediction/betting_portfolio.py # Kelly + CLV
api/main.py                         # FastAPI (9 endpoints, 5 routers)
scripts/batch_season.py             # Batch runner
database/schema.sql                 # PostgreSQL
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

Keep updates minimal — change the metric value or add a one-liner. Don't rewrite entire notes.
The `Stop` hook runs `scripts/vault_session_close.py` to append one line to Decision Log + refresh Home.md.
The `SessionStart` hook runs `scripts/update_vault.py` to refresh Home.md.
