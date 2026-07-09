# Models & Calibration

This folder documents the layer between raw signals and priced markets: how each sport's one
calibrated win-probability anchor is built, how player-prop distributions are priced, how
signals are catalogued, and the leak-avoidance/validation discipline every number inherits.

> Everything here is a calibration/sharpness claim (Brier, RMSE, ECE, coverage), never a dollar
> edge. The single numeric truth-source is [../JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md).

---

## Pages in this folder

| Doc | What it covers |
|---|---|
| [calibration-and-validation.md](calibration-and-validation.md) | The sport-blind kernel machinery: proof metrics, the three recalibration methods (Platt / isotonic / temperature) and when each is used, the two leak-avoidance seams (`IngestManifest`, `FeatureSpec`), the parity-matrix gate, walk-forward + truncation-invariance |
| [signal-factory-and-ratings.md](signal-factory-and-ratings.md) | The signal registry (one row per signal *definition*), the signal factory (proposal generator), and the role-aware "2K-style" player/team rating builders |
| [possession-simulators.md](possession-simulators.md) | The cross-sport sequence Monte-Carlo engines (NBA possessions, MLB pitches, soccer Dixon-Coles scorelines, tennis points) and the anchor-coherence pattern they share |
| [pregame-props.md](pregame-props.md) | The cross-sport player-prop pricing chain: rate x exposure -> dispersion -> calibration, per sport |
| [model-registry.md](model-registry.md) | The NBA-specific model-artifact inventory (which `.pkl`/`.json` backs which stat) |
| [feature-inventory.md](feature-inventory.md) | The NBA feature stack and the walk-forward-rejected feature blocks (honest REJECTs recorded) |
| [calibration.md](calibration.md) | NBA-specific calibration detail (Shin devig worked example, per-tier ECE targets) predating the kernel extraction |
| [MODEL_UNIVERSE.md](MODEL_UNIVERSE.md) | The NBA-specific model-planning catalog (legacy, pre-kernel-extraction) |

---

## The one-anchor principle

Every sport produces exactly one calibrated win-probability. Totals, spreads, 1X2, props, and
the in-game reprice are all derived from that single anchor (via a Monte-Carlo engine bisected to
match it, or an analytic joint distribution tilted to match it), so a change to the anchor
propagates coherently to the entire market surface instead of producing four models that can
disagree. See [possession-simulators.md](possession-simulators.md) for the per-sport mechanics
and [../architecture/system-overview.md](../architecture/system-overview.md) for where this sits
in the funnel.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
