# CourtVision — Roadmap

> Build sequence from current state (Phase G, Gate 1 pending) through multi-surface scale and exit.
> For context: [VISION.md](VISION.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [MASTER_PLAN.md](MASTER_PLAN.md)

---

## Current State (2026-05-24 · loop 5 / cycle 96e)

- CV pipeline: 17 quality / 29 usable / 75 attempted games (target: 80 CLEAN)
- Models: **85 trained**, walk-forward MAE for 7 prop heads in `data/models/quantile_pergame_metrics.json`
- Win probability: **0.7094 acc / 0.193 Brier** walk-forward (5-way NNLS stack) — see [README §"The 71% Result"](README.md#the-71-result--backtested-not-claimed)
- Prop backtest: **+19.9% to +28.1% ROI** at +0.5 edge across 7 stats, 19,964-game holdout
- Validation infra: shipped 2026-05-17 (temporal CV, model registry, regression gates, e2e tests, CV benchmark, CI)
- Production CLIs live: `predict_player.py`, `predict_slate.py`, `compare_to_lines.py`, `daily_run.py`, `nightly_report.py`, `compute_clv.py`
- Gate 1 (CLV vs Pinnacle close): **NOT YET RUN** — top priority
- Agentic research system: **not yet built**
- Signal subscription / team licensing: **not yet live**

---

## Near-Term (Weeks 1-12)

### Week 1-2: Gate 1 + Bias Fix

**Goal:** First real validation that the edge thesis is real.

- Run Gate 1: ≥50 settled bets vs real Pinnacle closing lines. Beat rate ≥55%, paper ROI ≥3%.
- Fix underprediction bias on all 7 prop models (all currently predict below closing line)
- Populate `kelly_corr` matrix (run `--build-residuals` then `--compute-corr`)
- Complete 80-game RunPod run (currently 29/80 usable, single RTX 3090, ~$5 budget)

**Gate 1 pass/fail determines everything downstream.** If Gate 1 fails, the hypothesis needs debugging before any other surface investment.

### Week 3-6: Substrate

**Goal:** Build the foundation that makes signal-based research possible.

- PostgreSQL truth layer: migrate from SQLite ingest queue to production PostgreSQL
- Feature store: keyed on (player, game, possession, timestamp), versioned by tracker_version
- Knowledge graph foundation: player node → game edge → possession node → event edge
- Signal-based refactor: each signal gets a signal_id, birth date, IR tracker, retirement trigger
- Model registry v2: holdout R², CV delta R², signal attribution, auto-deprecation threshold

### Week 7-10: First Agentic Loop

**Goal:** Claude agents begin discovering signals autonomously.

- Researcher agent: hypothesis generation from knowledge graph + literature
- Engineer agent: signal implementation + feature wiring
- Validator agent: holdout testing + IR calculation + pass/fail gate
- Orchestrator: coordinates the loop, logs to vault, promotes validated signals
- First autonomous signal: one signal discovered, validated, and deployed without manual direction

### Week 11-12: Production Integration

**Goal:** Signals go live, feedback loop closes.

- Shadow mode: new signals run alongside existing stack, track CLV divergence
- Auto-promote: signals crossing IR threshold enter production
- Risk monitor: real-time correlation watch, daily VaR, circuit breakers
- Nightly retrain: residuals from settled bets recalibrate upstream models

---

## Medium-Term (Months 4-12)

### Month 4-6: Compounding

- Specialist agents: shot-clock specialist, fatigue specialist, referee tendency specialist
- Multi-agent debate: researcher and validator argue before promotion
- Memory consolidation: signal genealogy tracking (which signals decayed, which compounds)
- Signal universe: 50-100 validated signals in production
- news pipe: build injury/lineup news ingestion (ESPN + NBA official + beat reporters)

### Month 7-9: First Commercial Surface

**Gate:** 12 months of audited paper returns, Gate 1 pass, ≥50 validated signals.

- Signal subscriptions: first 3-5 sharp subscribers at $5K/month
- team analytics demo: one team's defensive metrics extracted from broadcast video
- API documentation: prepare knowledge layer API for external consumption

### Month 10-12: Multi-Sport + Scale

- NCAA basketball: same pipeline, different court geometry. ~3 months work.
- Signal universe: 200+ validated signals in production
- Fund management: seek first LP conversations (requires audited track record)

---

## Long-Term (Year 2-3)

| Milestone | Gate | Target |
|-----------|------|--------|
| Signal subscriptions | 12-mo audited track record | $3-5M ARR, ~25 subscribers |
| Fund management | 18-mo track record, audited | $500K-2M AUM, LP capital |
| Team licensing | Demo + track record | 1-3 NBA franchises, $300K/yr |
| Broadcast augmentation | Team licensing proof | 1 RSN deal, $500K |
| Multi-sport (NFL) | NCAA proven | NFL expansion |
| Knowledge layer API | Team licensing + subscriptions | Metered API revenue |

---

## Year 3-5: Exit Territory

When ≥3 revenue surfaces are generating meaningful revenue simultaneously, strategic acquirer conversations become natural. The acquired asset is not "a sports model" — it's:

- The agentic research system architecture
- The signal universe database (500-5000 signals with documented IR history)
- Commercial relationships (subscribers, team clients, broadcast deals)
- Audited fund track record
- The knowledge graph with 5+ years of proprietary CV data

**Acquirer categories:** Stats Perform / Genius Sports / Sportradar (data layer), DraftKings / FanDuel (operator), Two Sigma Sports / SIG Nellie (quant fund), Anthropic-adjacent sports vertical.

**Valuation range:** $300M-$2B depending on which surfaces materialize.

---

## What This Roadmap Is Not

- It's not a linear feature checklist. Gate 1 is binary — it changes the path.
- It's not a promise. Revenue projections are ceiling estimates, not guarantees.
- It's not complete. The agentic research loop will discover things not on this list.

The agentic system is designed to invalidate this roadmap gracefully — by finding better paths than the one planned.

---

*Full planning detail: `.planning/ROADMAP.md` (167KB — grep/section-read only)*
*Gate 1 step-by-step: `vault/Plans/Gate 1 Validation.md`*
*Agentic system design: `vault/Plans/Agentic Research System.md`*
