# The Data Layer -- a leak-safe, as-of-stamped, keyless multi-sport data platform that audits its own completeness

> Data engineering at scale, built to be reproducible and honest about what it does
> not yet have. The single truth-source for any figure below is
> [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md) (sections F and G); the full
> pipeline/cache reference is [docs/DATA.md](../DATA.md). `data/` is local-only and
> gitignored, so every number here is read from a committed artifact under
> `scripts/platformkit/analytics_showcase/out/` or a committed builder, never from the
> private corpora themselves.

---

## The claim

The platform ingests four sports from **keyless-first** public sources, folds them into
point-in-time-correct feature corpora that are **leak-safe by construction**, and then
**audits its own completeness** and publishes the audit. No number is presented without
its provenance and an honesty label; a feed miss is logged and skipped, never filled with
a guess. This is a calibration/measurement layer -- **no dollar/edge/ROI claim is made
anywhere**, and the artifacts carry that fact in their own metadata.

---

## The layer, by the numbers

Each figure below is copied verbatim from a committed artifact; the artifact path is the
receipt.

- **693,037 MLB Statcast pitches** in one season pull, presented as a descriptive coverage
  showcase -- pitch-type mix, velocity percentiles, and column completeness. The
  framing-ingredient columns (`plate_x/z`, `sz_top/bot`, `zone`) are **99.63%** non-null
  and `type`/`balls`/`strikes` are **100%** non-null. Source:
  [`statcast_showcase.json`](../../scripts/platformkit/analytics_showcase/out/statcast_showcase.json)
  (`data/cache/statcast/statcast_fuller__2025.parquet`).
- **103,048 generated fact-claims across 103 families**, four sports plus WNBA/NPB-KBO/intl.
  A validation sidecar re-derived **101,865** of them and verified **101,864** (1
  unverifiable, **0** mismatches) -- **98.85%** of generated claims covered by a validation
  sample. Sport split: NBA 62,227 / MLB 21,519 / tennis 13,709 / soccer 4,275. Source:
  [`claims_corpus_meta.json`](../../scripts/platformkit/analytics_showcase/out/claims_corpus_meta.json).
  Honesty rail: verified counts are sidecar **sample** counts, not full-corpus audits;
  "generated" outnumbers "verified" by design, and every sidecar records `edge_claimed=false`.
- **291,625-pair player-vs-player matchup matrix** built from **2,214** raw per-game tracking
  files across three seasons (`data/cache/coverage_faced_allseasons.parquet`, built by
  [`build_coverage_allseasons.py`](../../scripts/intel/build_coverage_allseasons.py)). Its
  own metadata bakes in "descriptive not causal, not a betting edge."
- **6 keyless acquisition pipelines**, honestly staged. Some already produce data on disk
  (e.g. `bbref_advanced_extended.parquet` = **1,470** rows); others are wired but not yet
  armed, and the shipping commits say so explicitly (MiLB StatsAPI and Action Network
  public-splits are marked `PENDING-RESTART` in their own commit messages, not claimed live).
  Source: `scripts/platformkit/data_frontier/{bbref_advanced,understat_xg,statsbomb_open_full,savant_bat_tracking,milb_statsapi,an_public_splits}.py`.
- **A data-completeness auditor** that measures its own per-attribute/per-window coverage:
  for NBA it audits **61 attributes across 6 windows** over a **505-player** active
  universe and reports **0 all-null attributes**
  ([`profile_completeness.py`](../../scripts/platformkit/data_frontier/profile_completeness.py)
  -> `data/frontend/ops/profile_completeness.json`). The system reports what it does not
  know yet instead of silently degrading.

![MLB Statcast coverage showcase: 693,037 pitches, pitch-type mix and velocity percentiles](../img/statcast_showcase.png)

*Figure: descriptive coverage of the 693,037-pitch Statcast pull. Coverage only -- it does
not recompute any predictive-validity result.*

![Fact-claims corpus: 103,048 generated claims across 103 families, generated-vs-validated split](../img/claims_corpus_meta.png)

*Figure: the claims corpus shown with the generated-vs-validated split explicit, so
"verified" never silently means "generated."*

---

## Leak-safety mechanics

Every derived feature corpus (the `asof_*` stems in each sport's `ingest_manifest.py`) is
point-in-time-correct **by construction**, not by after-the-fact filtering. The shared
primitive is [`asof_common.py`](../../scripts/platformkit/asof_common.py), which implements
snapshot-before-update:

1. Sort events into a stable chronological order (stable mergesort, multi-key).
2. For each event, **snapshot** every entity's prior-only state.
3. Only **after** all snapshots in that event, **update** each entity's state with that
   event's realized observation.

State is keyed by global entity id, so a player seen in two games accumulates one shared
history. A debut entity snapshots to `NaN`, and a built-in assertion enforces "debut row =>
NaN" so no row can ever see its own current event. The intel builders extend this with a
strict expanding-window **`shift(1)`** join and confound flagging -- e.g.
[`build_player_availability.py`](../../scripts/intel/outcome/build_player_availability.py)
downgrades a schedule-confounded signal and stamps "descriptive not causal, not a betting
edge" into the artifact's metadata. Post-game columns (`home_win`, `target_over25`,
`winner`) are training labels only, never pregame features.

Because the as-of state is reconstructed from the raw post-game record, a full rebuild
reproduces the exact pregame feature each entity would have seen at that instant -- which is
what makes the corpus **walk-forward and truncation-invariant**. The property-based test
that proves truncation invariance (a feature at time T is byte-identical with or without
future events) is documented alongside the other leak instruments in
[leak-instruments.md](leak-instruments.md).

---

## Receipts

| Layer | Scale (verbatim from artifact) | Proof artifact | Honesty label |
|---|---|---|---|
| MLB Statcast coverage | 693,037 pitches; framing cols 99.63-100% non-null | `analytics_showcase/out/statcast_showcase.json` | Descriptive coverage only; no edge/ROI/$ claim |
| Fact-claims corpus | 103,048 generated / 103 families; 101,864 of 101,865 sampled verified (98.85% covered) | `analytics_showcase/out/claims_corpus_meta.json` | Generated > verified by design; sidecar sample counts; `edge_claimed=false` |
| Matchup matrix | 291,625 pairs from 2,214 tracking files / 3 seasons | `data/cache/coverage_faced_allseasons.parquet`; `scripts/intel/build_coverage_allseasons.py` | Descriptive, not causal; not a betting edge |
| As-of feature builders | shift(1) expanding-window; debut => NaN assertion | `scripts/platformkit/asof_common.py`; `scripts/intel/outcome/build_player_availability.py` | Leak-safe by construction; schedule-confound downgraded |
| Keyless acquisition pipelines | 6 pipelines; `bbref_advanced_extended.parquet` = 1,470 rows | `scripts/platformkit/data_frontier/*.py` | Honestly staged; some `PENDING-RESTART`, flagged in the commit |
| Completeness auditor | NBA: 61 attributes / 6 windows / 505 players / 0 all-null | `scripts/platformkit/data_frontier/profile_completeness.py` -> `data/frontend/ops/profile_completeness.json` | Reports what it does not know yet; no silent degrade |

---

## Why this matters to an employer

The hire signal here is not raw volume -- it is that the volume is **reproducible, provenance-
stamped, and self-audited**. The hard part of data engineering is not fetching rows; it is
building corpora that cannot leak, that rebuild identically from scratch, and that tell you
where the gaps are before a model quietly trains on a hole. This layer does all three:
leak-safety is a construction invariant with an assertion behind it, keyless-first sourcing
removes a paid-API dependency for the default slate, and the completeness auditor plus the
generated-vs-validated split mean no number reaches a reviewer without its own disclaimer.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
