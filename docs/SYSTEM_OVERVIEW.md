# System Overview — CourtVision

> This document has been superseded by the top-level [ARCHITECTURE.md](../ARCHITECTURE.md).
> Archived original: `docs/_archive/SYSTEM_OVERVIEW_archived_2026-05-18.md`

See [ARCHITECTURE.md](../ARCHITECTURE.md) for the current system architecture.

---

## One-screen orientation

CourtVision is a domain-agnostic, **calibrated** multi-sport forecasting engine.
A sport-blind `kernel/` (the validated machinery: walk-forward gating,
calibration, the Monte-Carlo framework, the discovery loop, devig/shadow logging)
is consumed by thin `domains/<sport>/` adapters. Four sports — NBA, MLB, soccer,
tennis — share one kernel and one prediction surface; a fifth (`soccer_intl`) is a
census-only international predictor.

- **One win-prob anchors every market.** Each adapter emits a single calibrated
  win probability per matchup; totals / spreads / props / SGP and the in-game
  repricer are all derived from it, so they cannot disagree.
- **A new sport implements only three frozen seams** — `SportContext` (runtime,
  validated by `kernel/testing/conformance.py`), `feature_spec.py`
  (train==inference base matrix), and `ingest_manifest.py` (per-corpus leak-class
  + freshness SLA). One fail-closed grid (`scripts/platformkit/parity_matrix.py`)
  keeps all sports green across `{census, manifest, feature_spec}`.
- **Always-on serving:** a DAG-ordered supervisor boots the producer + Auto-API
  (`:8099`) + boards/UI + paper/line/in-game/self-improve daemons, behind a
  fail-closed governance preflight (real money is default-DENY).

**Honest read:** pregame MATCHES the devigged close on team-strength markets and
trails on totals/ATP only by freshness data a box model cannot see; in-game
conditioning is a *calibration* win (lower Brier), not a dollar edge. No $ edge /
ROI is claimed for any sport.

### Where to go next

| You want | Read |
|---|---|
| End-to-end technical map (CV origin -> ML -> serving) | [ARCHITECTURE.md](../ARCHITECTURE.md) |
| Kernel/adapter contract + 9-step new-sport playbook + parity mechanism | [PLATFORM.md](PLATFORM.md) |
| Tooling CLIs, supervisor process table, robustness test matrix | [PLATFORM_TOOLING.md](PLATFORM_TOOLING.md) |
| The six core decision systems + interconnects | [architecture/system-overview.md](architecture/system-overview.md) |
| Honest, adversarially-audited numbers + do-not-claim list | [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) |
| Known limitations | [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) |
| Full doc map | [INDEX.md](INDEX.md) |


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
