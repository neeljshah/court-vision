# AGENTS.md — Orientation for AI Coding Agents

This is the landing pad for Cursor, Aider, Codex CLI, OpenCode, and other AI dev tools that don't read `CLAUDE.md`. The deeper task-to-file routing tables live in [CLAUDE.md](CLAUDE.md) — load that too if you're making edits.

---

## What this repo is

**CourtVision** — end-to-end NBA intelligence platform, built solo by [Neel Shah](https://neelshahportfolio.netlify.app). The system takes raw broadcast video, converts it to court-coordinate tracking data at ~$0.10/game, feeds that into a prediction + decision stack, and wraps everything in an agentic self-improving loop.

**Architecture direction (June 2026):** a domain-agnostic, multi-sport engine where sport-agnostic machinery (validation, calibration, Monte Carlo sim, Kelly/devig, agent loop) lives in a shared `kernel/`, and each sport is an adapter in `domains/<sport>/`. About 38% of the current codebase is already kernel-quality. See [docs/PLATFORM.md](docs/PLATFORM.md).

**The funnel:** DATA → SIGNALS → MODELS → ENGINES → PREDICTIONS → INTELLIGENCE

Stack: YOLOv8n → SIFT homography → Kalman+Hungarian → OSNet re-ID 512-dim → EasyOCR → EventDetector → FastAPI (~99 endpoints, 12 routers) → 9 production daemons → Monte Carlo possession sim → agentic improvement loop.

---

## Read these first

1. **[docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md)** — honest, adversarially-audited account of every claim. Canonical truth source. Read this before forming any opinion about system capabilities.
2. **[README.md](README.md)** — dense long-form: architecture, methodology, walk-forward tables, reproducibility.
3. **[docs/PLATFORM.md](docs/PLATFORM.md)** — multi-sport kernel/adapter architecture direction.
4. **[docs/INTELLIGENCE.md](docs/INTELLIGENCE.md)** — manifest of the 80 derived artifacts between CV tracking and the prediction models.

**Skip on first pass:** `docs/architecture/*` and walking `src/prediction/` (~130 modules). Only ~12 of those modules are runtime load-bearing — the list is in [README.md](README.md).

---

## Honest numbers (leak-free, retracted headlines documented)

- **CV pipeline:** broadcast video → court coordinates at **~$0.10/game** on a consumer RTX 4060
- **Prop MAE:** PTS ~4.58 / REB ~1.90 / AST ~1.34 / FG3M ~0.88 (walk-forward, ~51K held-out rows)
- **Win-prob:** 0.709 accuracy / 0.193 Brier (walk-forward, leak-free)
- **Betting vs real closes:** market is efficient — break-even-minus-vig overall; AST ~+4–5% is the one durable edge (breaks in playoffs)
- **In-play backtest 78%/+54%** is an L5-proxy ceiling, not realized edge; first real CLV October 2026; zero real money placed

**Retracted numbers — do not repeat as current wins:**
- +18.38% pre-game ROI (market-follow grading artifact)
- endQ3 Brier 0.119 (Q4 data leak; honest ~0.141)
- +54% as a realized edge claim (L5 line proxy)
- CLV +8.94pp (stale synthetic estimate)

These appear in the repo only as artifacts the validation harnesses caught. Full account: [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md).

---

## Repo conventions

- **Python 3.9 · conda env `basketball_ai` · CUDA 11.8 · RTX 4060 8GB**
- Max 300 LOC/file · type hints · docstrings on public API only
- Models → `data/models/` (most are gitignored; whitelist in `.gitignore`)
- Logs / vault → `vault/` (gitignored)
- Headless video only (`--no-show`); never `cv2.imshow`
- Tests: `python -m pytest tests/ -q`
- **Critical invariant:** `_VRAM_FLUSH_INTERVAL` in `src/pipeline/unified_pipeline.py` **must be 3000, not 100**. Setting it to 100 OOMs the GPU.
- Never run: `run.py`, `loop_processor.py` (legacy entry points)

Task → primary file routing: [CLAUDE.md § Task → Files](CLAUDE.md).

---

## Validation discipline (do not bypass)

Every signal change must clear the ship gate before it touches the production stack:

1. **Walk-forward CV** — expanding window, all folds must improve, assertion-level `max_train_date < min_test_date` check per fold
2. **Multi-corpus gate** — calibration or signal must beat raw on ≥2 independent OOS corpora
3. **Truncation-invariance** — features at time T must be byte-identical with or without future events
4. **Null-shuffle permutation** — z ≥ 3 over permuted labels before shipping
5. **Ablation** — contribution is isolated, not confounded

Most candidates are correctly rejected. A correct reject is not a failure — it is the gate working. Never bypass the gate for a "promising" result. See [docs/research/validation-methodology.md](docs/research/validation-methodology.md).

---

## Honest gaps (don't hide these)

- CV scale-up is 7/80 full-feature games; `defender_distance=200.0` sentinel fix (ISSUE-022) is the blocker
- DraftKings / Caesars / MGM scrapers are IP-blocked; Pinnacle / FanDuel / Bovada / PrizePicks cover the rest
- `sim_win_prob` polarity bug documented in `vault/Models/Polarity Bug Audit 2026-05-27.md` — gated, unpatched
- Multi-sport `kernel/` refactor is planned but not started; current code is NBA-only

Full gap inventory: [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).
