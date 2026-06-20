# Guide -- The System, End to End

A single, all-in-one AI for **calibrated sports prediction** across four sports --
NBA, MLB, soccer, and tennis -- wrapped in a live, self-healing, self-improving
serving stack and a **paper-only** decision layer. It turns raw data (broadcast
computer vision, keyless odds feeds, multi-book scrapers, four sports' historical
corpora) into **well-calibrated probabilities**: forecasts whose stated confidence
matches reality. The honest product is *forecast quality and decision support*, not
profit or picks. We measure ourselves against the sharp closing line and, on
team-strength markets, the realistic best case is to **match the devigged close
within noise** -- markets are efficient pregame, and we never claim to beat them.
The one independently **measured** win is **in-game conditioning** (fusing the
pregame prior with the realized score sharpens the live win-prob forecast -- a
calibration gain, not a dollar edge). Everything is **units, never dollars**; real
money is **default-DENY**.

> **Honesty rail.** Every number in this guide traces back to the adversarially
> audited [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md) and obeys
> [.claude/rules/no-edge-claims.md](../../.claude/rules/no-edge-claims.md). Calibration,
> not edge. An honest REJECT is a SUCCESS here, not a failure.

---

## Run it in 30 seconds

```powershell
.\go.ps1          # arms the box, boots the 17-service supervised stack, opens the UI
```

Then open two pages:

- **http://localhost:3000/system** -- is the stack healthy and learning?
- **http://localhost:3000/models** -- how is the predictor getting better over time?

Stop everything with `.\go.ps1 -Stop`. No Claude, no dollars, no manual babysitting --
the supervisor restarts anything that dies and the self-improve loop runs in
measurement-only mode until a human deliberately flips it on. Full operator runbook:
[07_RUN_AND_MONITOR.md](07_RUN_AND_MONITOR.md).

---

## Start here (reading order)

```
00 Overview ---> 02 What the AI Does ---> 03 Predictions ---> 10 Honest Limits
   (the pitch)      (end-to-end flow)       (see it live)        (read before you cite)

then go deep on whatever you care about:
   01 Architecture    04 Paper Trading     05 Execution      06 How It Gets Better
   07 Run & Monitor   08 Live Stack        09 Data & Signals
```

1. **[00_OVERVIEW.md](00_OVERVIEW.md)** -- the one-page honest pitch + north star.
2. **[02_WHAT_THE_AI_DOES.md](02_WHAT_THE_AI_DOES.md)** -- the full DATA->PREDICTIONS flow in plain language.
3. **[03_PREDICTIONS.md](03_PREDICTIONS.md)** -- where to actually see the numbers (pages, APIs, CLI).
4. **[10_HONEST_LIMITS.md](10_HONEST_LIMITS.md)** -- what may and may not be claimed (read before quoting anything).
5. Then dive into any deep-dive below.

---

## The 11 documents

| # | Doc | What it covers |
|---|-----|----------------|
| 00 | **[Overview](00_OVERVIEW.md)** | What the system is, the funnel, and the honest calibration-not-edge north star. |
| 01 | **[Architecture](01_ARCHITECTURE.md)** | Structural layout: the sport-blind `kernel/` + per-sport `domains/<sport>/` adapters, data flow, what runs in production. |
| 02 | **[What the AI Does](02_WHAT_THE_AI_DOES.md)** | End-to-end walkthrough of a single game from raw data to calibrated markets, in plain language. |
| 03 | **[How To See Predictions](03_PREDICTIONS.md)** | The web pages, JSON APIs, and one-shot CLI -- and what every on-screen number means. |
| 04 | **[Paper Trading](04_PAPER_TRADING.md)** | The paper-only decision layer: `executed=False`, `edge_claimed=False`, and CLV (not ROI) as the honest yardstick. |
| 05 | **[Execution + Line Shopping](05_EXECUTION_AND_LINES.md)** | The layer between calibrated probabilities and any action: line shopping, kill-switch, default-DENY real-money gate. |
| 06 | **[How the AI Gets Better](06_HOW_IT_GETS_BETTER.md)** | The self-improve ratchet: learn from settled outcomes, propose a recalibration, ship only if strict gates agree -- most cycles ship nothing. |
| 07 | **[Run and Monitor](07_RUN_AND_MONITOR.md)** | Operator runbook: two PowerShell commands to start/stop, plus the `/system` and `/models` dashboards. |
| 08 | **[The Live, Independent Stack](08_LIVE_STACK_INDEPENDENCE.md)** | How `boot.ps1` runs 17 supervised processes in dependency order, gated on readiness probes, auto-restarting on failure -- no Claude at runtime. |
| 09 | **[Data, Signals & Intelligence](09_DATA_AND_SIGNALS.md)** | The input stack: 4-sport ingestion, the signal factory, the person-free concept graph, and the broadcast-CV pipeline. |
| 10 | **[Honest Limits](10_HONEST_LIMITS.md)** | The claim ledger: what is defensible, the retracted measurement artifacts, and why a REJECT is a success. |

---

## The funnel at a glance

```
 DATA          SIGNALS         MODELS          ENGINES         PREDICTIONS      INTELLIGENCE
broadcast CV -> signal      -> prop XGB (7) -> possession  -> calibrated    -> concept graph
NBA/odds APIs  factory         win-prob        Monte Carlo    markets +         (playstyles,
multi-book     (85 trained)    MOV-Elo         sim ->         Shin/Platt        schemes,
scrapers       + 80-artifact   (per sport)     coherent       calibrated        dossiers)
4-sport        intel layer                     markets        probabilities
   \________________ agentic discover / validate / SHIP-or-REJECT loop ________________/
```

Every stage is re-validated by an agentic loop behind a fail-closed ship gate
(expanding walk-forward + null-shuffle permutation + ablation + FDR). The gate
exists to **refute**, not confirm -- which is why the 4-sport / 6-corpus efficiency
hunt correctly REJECTED every candidate pregame edge.

---

## Where to look in the repo

- `docs/guide/` -- this guide (the 11 docs above + this index).
- `docs/JOB_EVIDENCE_PACKET.md` -- truth source for every claim + the do-not-claim list.
- `.claude/rules/no-edge-claims.md` -- the calibration-not-edge honesty rule.
- `go.ps1`, `boot.ps1` -- one-command start/stop for the whole supervised stack.
- `webapp/app/system/page.tsx`, `webapp/app/models/page.tsx` -- the `/system` and `/models` dashboards.
- `kernel/` + `domains/<sport>/` -- sport-blind machinery + per-sport adapters.
- `api/main.py` -- the FastAPI surface that serves the live page.
