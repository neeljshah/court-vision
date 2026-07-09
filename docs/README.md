# Documentation

This is the `docs/` folder landing page -- the entry point GitHub shows when you browse into
this directory. For the exhaustive, hand-curated map of every tracked document (organized by
reader role and by funnel stage), see **[docs/INDEX.md](INDEX.md)**. This page is a shorter
front door into the same material, organized by subsystem instead.

**Start at the root [README.md](../README.md)** if you haven't already -- it has the funnel
narrative, the honest headline numbers, and the quickstart. Come here when you want to go one
level deeper into a specific layer of the system.

> **Non-negotiable framing.** This is a calibrated predictor, not a betting-edge product. The
> honest, defensible win is "match the devigged close within noise" on efficient pregame markets,
> plus a measured, calibrated in-game conditioning improvement. No dollar edge, ROI, or "beat the
> close" claim appears anywhere in these docs outside of explicit retraction context. The single
> truth source for any number is [docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).

---

## By subsystem

| Subsystem | What it covers | Docs |
|---|---|---|
| **Architecture** | System overview, layer-by-layer data flow, directory map, design invariants | [docs/architecture/](architecture/) -- start at [system-overview.md](architecture/system-overview.md) |
| **Kernel** | The sport-blind `kernel/` -- validated machinery every domain adapter shares | [docs/kernel/](kernel/) -- start at [README.md](kernel/README.md) |
| **Platformkit** | The `scripts/platformkit/` toolkit -- CLIs, gates, ledgers, proof harnesses | [docs/platformkit/](platformkit/) -- start at [README.md](platformkit/README.md) |
| **Domains** | Per-sport adapters (`domains/<sport>/`) -- NBA, MLB, soccer, tennis, WNBA, ... | [docs/domains/](domains/) -- start at [README.md](domains/README.md) |
| **Models** | Model registry, calibration methodology, feature inventory, signal factory | [docs/models/](models/) -- start at [README.md](models/README.md) |
| **In-play** | The live/in-game conditioning layer -- the one measured, calibrated edge | [LIVE_ENGINE_V2.md](LIVE_ENGINE_V2.md) |
| **Execution** | Line-shopping, devig, sizing, paper-trading, CLV grading | [EXECUTION_GUIDE.md](EXECUTION_GUIDE.md) - [BETTING.md](BETTING.md) - [architecture/execution-engine.md](architecture/execution-engine.md) |
| **Ops** | Daemons, supervisor, deployment, runbooks | [PRODUCTION_RUNBOOK.md](PRODUCTION_RUNBOOK.md) |
| **Data** | Ingestion pipelines, corpora, freshness SLAs, the data census | [DATA.md](DATA.md) - [DATA_DEPTH.md](DATA_DEPTH.md) |

---

## The funnel, in one line

```
DATA -> SIGNALS -> MODELS -> ENGINES (simulation) -> PREDICTIONS (markets) -> EXECUTION -> GRADING
```

Every stage feeds the next. One calibrated win-probability per sport anchors every market it
prices, so a change anywhere propagates coherently instead of producing four models that can
disagree. The full layer-by-layer walkthrough with code paths at every arrow is
[docs/architecture/system-overview.md](architecture/system-overview.md).

---

## Orientation documents (read these first)

| Doc | Why |
|---|---|
| [../README.md](../README.md) | The front door -- what this is, headline capabilities, quickstart |
| [INDEX.md](INDEX.md) | The exhaustive, role-based map of every tracked document |
| [../ARCHITECTURE.md](../ARCHITECTURE.md) | Root-level end-to-end technical map (CV pipeline lineage + funnel) |
| [PLATFORM.md](PLATFORM.md) | The `kernel/` + `domains/<sport>/` contract -- the current architecture direction, in depth |
| [GLOSSARY.md](GLOSSARY.md) | Every term defined once (CLV, leak-free, walk-forward, Shin devig, Brier, Kelly, devig, parity) |
| [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) | The single honesty truth-source -- every claim's proof artifact + the do-not-claim list |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | Open gaps, honestly stated |

## New here? Three ways in

1. **I want the big picture.** [../README.md](../README.md) -> [docs/architecture/system-overview.md](architecture/system-overview.md).
2. **I want to add a sport.** [PLATFORM.md](PLATFORM.md) (the 9-step playbook) -> [docs/kernel/README.md](kernel/README.md) (what you get for free) -> an existing adapter under `domains/tennis/` or `domains/mlb/` as a template.
3. **I want to run something.** [../README.md](../README.md) for the predictor CLI, or [docs/PREDICTOR_QUICKSTART.md](PREDICTOR_QUICKSTART.md) for the fuller quickstart.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
