# CourtVision Platform Vision — Domain-Agnostic, Self-Improving Forecasting Engine

> **Status:** NBA reference adapter in production. Multi-sport architecture direction announced June 2026. No second-sport code shipped yet; this document describes the intended trajectory.

---

## The Thesis

The NBA system took three months and 1,470 commits to reach production quality. A naïve port to tennis, NFL, or soccer would cost another three months each — because the machinery would be rebuilt from scratch every time.

The insight is that the hard, compounding work is sport-agnostic:

- Walk-forward validation with assertion-level leak guards
- Conformal calibration acceptance gates (must beat raw on ≥2 independent corpora)
- A self-improving signal-discovery loop with an honest reject/ship gate
- Monte Carlo simulation of possessions/sequences, parameterized by sport-specific transition matrices
- Devig, Kelly sizing, CLV tracking, shadow logging, P&L settlement
- The brain: an autonomous agent loop that proposes, validates, and retires signals

None of that belongs to basketball. It belongs to the infrastructure layer. The sport-specific pieces — data connectors, event taxonomy, stat definitions, market structures — are thin adapters that consume the infrastructure.

**Adding a second sport should require writing only the adapter.** The validated machinery compounds across sports without being rebuilt.

---

## Architecture: `kernel/` + `domains/<sport>/`

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          kernel/                                          │
│                   (sport-agnostic, reusable)                              │
│                                                                           │
│  loop/         Self-improving discovery loop                              │
│                  Proposer → cheap screen → walk-forward gate → ship/reject│
│  sim/          Monte Carlo framework                                      │
│                  Parameterized by transition matrices; sport provides     │
│                  possession/event distributions, kernel runs the paths    │
│  validation/   Walk-forward CV, truncation-invariance tests,             │
│                  conformal calibration, multi-corpus acceptance           │
│  decision/     Devig (Shin + 3 others), Kelly sizing, shadow logger,     │
│                  CLV tracker, P&L ledger, drawdown circuit breaker        │
│  brain/        Agent orchestration: Opus plans, Sonnet executes,         │
│                  Haiku searches; hard ship gates at every layer           │
│  api/          Shared endpoint scaffolding, auth, health, SSE            │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │ consumes
          ┌────────────────┴─────────────────────┐
          ▼                                       ▼
┌─────────────────────┐               ┌──────────────────────┐
│ domains/nba/        │               │ domains/<sport-2>/   │
│  (reference adapter)│               │  (future adapter)    │
│                     │               │                      │
│  data/    NBA Stats │               │  data/    sport feed │
│           API + CDN │               │  events/  taxonomy   │
│           PBP feed  │               │  stats/   definitions│
│  cv/      broadcast │               │  markets/ structure  │
│           tracking  │               │                      │
│  events/  shot/pass │               │  ~ weeks to wire     │
│           screen/   │               │  kernel does the rest│
│           drive     │               └──────────────────────┘
│  stats/   per-player│
│           prop defs │
│  markets/ sportsbook│
│           structure │
└─────────────────────┘
```

### Kernel vs. Adapter Responsibility Split

| Concern | kernel/ | domains/<sport>/ |
|---|---|---|
| Walk-forward CV with leak guards | owns | — |
| Conformal calibration, multi-corpus gate | owns | — |
| Monte Carlo path simulation | parameterized framework | transition matrices, possession distributions |
| Signal-discovery loop | owns | feature generators |
| Devig / Kelly / CLV / shadow log | owns | — |
| Agent orchestration (planner/executor) | owns | — |
| Data ingestion | interface | connector implementation |
| Event taxonomy | interface | event definitions |
| Stat definitions (props) | interface | per-stat schema |
| Market structure (O/U lines, formats) | interface | book-specific adapter |
| CV pipeline | — | sport-specific (NBA: broadcast video) |

---

## Current State: ~38% Already Kernel

An audit of the NBA codebase (430 modules, 163K lines) classifies roughly:

| Category | Approx. share | Notes |
|---|---|---|
| Already sport-agnostic (kernel candidates) | ~38% | Validation, decision math, agent loop, calibration, Kelly/devig, shadow log |
| NBA-specific adapter code | ~53% | CV tracking, NBA API connectors, basketball event taxonomy, stat heads |
| Dead / research surface | ~9% | One-off experiment scripts not in the deployment graph |

The kernel is not currently packaged as a separate layer — it lives in `src/` alongside NBA-specific code. The multi-sport refactor isolates it into `kernel/` so a new adapter can import it cleanly.

---

## Why the Machinery Compounds Across Sports

The same validation discipline that caught a leaky +18.38% ROI claim in NBA (documented in [docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)) applies identically to any sport. The walk-forward harness, the truncation-invariance tests, the conformal calibration gate, the shadow logger — these are sport-blind.

The hard-won lessons compound too:

- **CLV > ROI** as the proof of edge: holds for any liquid market
- **Single-fold lifts are artifacts**: the gate requires ≥2 independent corpora
- **Accuracy ≠ edge**: minimizing MAE pulls toward the line in any sport
- **Freshness beats retraining**: same-day information is the lever in every sport's prediction market

Each lesson is already encoded in the kernel as a hard gate or a documented invariant. A tennis adapter inherits all of them on day one.

---

## Roadmap

### Phase 0 — Extract and stabilize the kernel (NBA stays reference)
Isolate the sport-agnostic layer (`kernel/`) without changing any NBA behavior. All existing tests pass. The NBA system runs unchanged; the only difference is it now imports from `kernel/` explicitly.

### Phase 1 — Second-sport proof (tennis as first adapter)
Tennis is the lowest-friction proof: match-level markets (moneyline, games O/U), clean data from ATP/WTA feeds, no CV requirement. The goal is to validate that adding a sport costs adapter weeks, not infrastructure months.

### Phase 2 — Broaden
Additional sports (NFL, soccer, others) each add an adapter without touching the kernel. The kernel continues to compound — improvements to walk-forward gating, calibration, or the agent loop benefit every sport simultaneously.

---

## What This Is Not

This document describes the **architectural direction**, not a deployed product. The multi-sport refactor has not started as of June 2026. No second-sport data has been collected. No edge claims are made for any sport — the NBA system's own validation shows that markets are efficient and beating the close requires freshness and joint-market pricing advantages that are difficult to capture, not model improvements. See [docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) for the honest validation record.

The value of the platform architecture is engineering compounding — shared infrastructure, shared discipline, shared agent loop — not a promised betting edge in any market.

---

*CourtVision is built by [Neel Shah](https://neelshahportfolio.netlify.app). Contact: [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com)*
