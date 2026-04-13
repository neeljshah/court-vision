# Auto-Betting + Quant Dashboard Plan

This plan defines how CourtVision runs fast, safely, and continuously in hybrid mode:

- no live CV inference in betting loop,
- live betting decisions from live data + historical CV-enhanced model context,
- one integrated control and visibility layer for operators.

---

## 1) System Topology

### APIs

1. **Prediction API**
   - Serves game/prop predictions, uncertainty, model metadata, gate status.
2. **Betting API**
   - Runs risk checks, sizing, order placement, order state sync, kill switch.
3. **Quant API**
   - Dashboard-facing aggregation API and websocket event stream.
   - Source of truth for frontend reads.

### Frontend

- Quant dashboard for monitoring + control.
- Most reads from Quant API.
- Controlled writes for strategy updates and execution toggles.

---

## 2) Latency Budget (Target)

| Stage | Target (p95) |
|---|---|
| Live data ingest normalization | <= 120 ms |
| Prediction fetch/inference | <= 350 ms |
| Risk + sizing checks | <= 200 ms |
| Order intent to placement | <= 250 ms |
| End-to-end cycle (line update -> action) | <= 900 ms |
| Event to dashboard paint | <= 1000 ms |

Operational goal: keep critical loop under 1 second p95.

---

## 3) Event-Driven Design

Core event types:

- `line.updated`
- `injury.updated`
- `prediction.created`
- `risk.check.completed`
- `bet.placed`
- `bet.state.changed`
- `gate.status.changed`
- `kill_switch.changed`

Use a queue/event bus for async fan-out. Keep execution path deterministic and idempotent.

---

## 4) Frontend Product Surface

### A) Overview
- Top edges, active exposure, CLV trend, gate health.

### B) Live Markets
- Realtime game/prop cards with model edge, confidence, and freshness.

### C) Execution
- Open intents, placed bets, fills, rejects, order latency.

### D) Risk
- Drawdown, correlation clusters, exposure by market/book/player.

### E) Model Health
- Drift/calibration/leakage indicators and recent failures.

### F) Strategy Studio
- Editable parameters: edge floor, max stake %, correlation cap, market allowlist.
- Dry-run mode + change preview before live apply.

---

## 5) Safety and Governance

- Gate-aware execution: red gates block placement.
- Strategy config versioning with audit trail (`who`, `when`, `before`, `after`, `why`).
- Kill switch with immediate fan-out and persistent state.
- Stale feed protection with operator-visible warnings and optional auto-pause.

---

## 6) Rollout Plan

### Sprint 1
- Quant API overview endpoints
- Live event stream skeleton
- Dashboard shell (overview + live cards + gate badges)

### Sprint 2
- Betting API execution lifecycle
- Risk checks + kill switch
- Execution panel and audit timeline

### Sprint 3
- Strategy Studio controls
- Dry-run simulation for config changes
- Latency observability and alerting

### Sprint 4
- Hardening: load tests, failover drills, runbooks, autoscaling

---

## 7) Definition of Done

Feature is done only when all are true:

1. Functional behavior implemented.
2. Latency target met in test environment.
3. Risk/gate behavior verified with test cases.
4. Monitoring + alerts instrumented.
5. Operator doc/runbook updated.

---

## 8) Locked UX + Operations Decisions (Interview Outcomes)

This section captures operator decisions and is now default behavior unless explicitly changed.

### Main Screen Defaults

- Always visible panels:
  - `Live market board` (edges + line movement)
  - `Execution tape` (intents, fills, rejects)
- Default opportunity sorting:
  - `Hybrid score` = EV + confidence + liquidity quality
- Default mode at app start:
  - `Live auto` (only active when gateways are green)

### Required Confirmation Actions

The following actions require confirmation and audit log entry:

1. Turn kill switch OFF (resume auto-betting)
2. Change risk limits/stake caps
3. Change edge thresholds
4. Change allowed books/markets

### Autonomous Gateway Engine (Start/Stop Logic)

Auto-pause betting when any hard-stop condition is true:

- required gate is red,
- stale feed threshold is breached,
- latency exceeds SLO for configured consecutive cycles,
- drawdown guard is breached,
- order rejection/error spike exceeds threshold.

Auto-resume betting only when all resume conditions are true:

- all hard gates are green for cooldown window,
- feed freshness is restored,
- latency is back within SLO,
- no manual lock is active.

### Always-On Top Status Strip

Even with minimal always-visible panels, the UI must always show:

- gateway state (`RUNNING` / `PAUSED`),
- feed freshness indicator,
- decision-loop latency (p95),
- kill-switch state.
