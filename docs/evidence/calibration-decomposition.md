# Decomposing my own Brier gap vs the market -- and publishing where the model is weakest

> The most transparent sports forecaster you can audit -- every prediction pre-registered,
> every number gated, including the ones that refuted me. The single truth-source for any
> figure below is [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md). Everything on this
> page is `edge_claimed=false`: calibration diagnostics, not a betting signal. No dollar/ROI
> claim appears anywhere.

---

## The claim

I don't just report that the market beats my in-game model -- I take my own Brier gap apart
into its named components and publish the ranked list of exactly which game states my model
handles worst. Two instruments do this:

1. A **Murphy decomposition** splits the Brier gap into *reliability* (miscalibration --
   fixable by recalibration) and *resolution* (information -- the market simply resolves more
   state into its price). This answers *why* the market is ahead.
2. A **state-conditioned calibration** map buckets every graded in-game prediction by
   probability band x game-state time bucket and ranks the worst buckets. This answers
   *where* the model is weakest, as an improvement backlog.

Both run leak-free on row-level joined grade corpora, both have a `--check` self-check, and
both write their numbers to committed JSON + a PNG.

---

## Instrument 1 -- Murphy decomposition (why the market is ahead)

`Brier = reliability - resolution + uncertainty` (10-bin, standard Murphy 1973). The gap vs
the market decomposes cleanly: if it lives in *reliability*, the model is miscalibrated and
recalibration would close it; if it lives in *resolution*, the market knows things the
model's checkpoint snapshots cannot see, and no recalibration fixes that.

**Source:** `scripts/platformkit/analytics_showcase/out/murphy_decomposition.json`
(`edge_claimed: false`; method: `"10-bin Murphy decomposition (Brier = reliability -
resolution + uncertainty)"`). Plot: `docs/img/reliability_model_vs_market.png`.

**Revision 2, segment-clean corpus** (rebuilt 2026-09-16 from the 178-game segmented MLB corpus; see the [join-integrity finding](/analytics/findings/ingame-join-integrity/)). Revision 1 was withdrawn: its 227-game MLB corpus failed the join-integrity check (126 of 227 stored files mixed ticks from consecutive-day games under one outcome label), so its figures are not republished here.

| sport | n | model Brier | market Brier | model reliability | model resolution | market reliability | market resolution |
|---|---|---|---|---|---|---|---|
| mlb | 27,351 | 0.166759 | 0.151008 | 0.005619 | 0.087187 | 0.003425 | 0.102062 |
| soccer_intl | 4,265 | 0.332522 | 0.195157 | 0.191982 | 0.038714 | 0.088088 | 0.071263 |

The verdict string, copied verbatim from the revision-2 JSON:

> mlb: model Brier 0.1668 is worse than market 0.1510 (gap=+0.0158); driven mainly by
> resolution (information, not fixable by recalibration) (reliability_gap=+0.0022,
> resolution_gap=-0.0149). soccer_intl: model Brier 0.3325 is worse than market 0.1952
> (gap=+0.1374); driven mainly by reliability (calibration, fixable) (reliability_gap=+0.1039,
> resolution_gap=-0.0325).

**Honest read:** in MLB the market is not ahead because the model is badly calibrated -- it is
ahead because it resolves more information into its probability (state changes it can see
that our checkpoint snapshots cannot). In soccer_intl the revision-2 gap is mostly
*reliability*: the model is miscalibrated there, which recalibration could address.

**Reconstruction caveat (stated, not hidden):** the binned formula reconstructs MLB model
Brier as 0.168327 vs the exact 0.166759 -- a small residual from within-bin prediction
dispersion, expected for the binned decomposition. The soccer reconstructions carry a larger
residual for the same reason at that sport's smaller n; the exact Brier is the one to quote.

---

## Instrument 2 -- State-conditioned calibration (where the model is weakest)

Every graded in-game prediction is bucketed by `(model_prob band) x (game-state time
bucket)`, and per-bucket calibration error `|mean_p - mean_y|` is computed for both model and
market. The ranked worst-bucket list is, in the module's own words, "the improvement
backlog."

**Source:** `scripts/platformkit/analytics_showcase/out/state_conditioned_calibration.json` (`edge_claimed: false`). Heatmap:
`docs/img/state_calibration_heatmap.png`. The `mlb_clean` corpus was found byte-identical to
`mlb` (verified via `filecmp`) and is logged in `skipped` to avoid double-counting.

Story string, verbatim from the JSON:

> Buckets every graded ingame prediction by model_prob band x game-state time bucket;
> ranked_worst_buckets is where the model is furthest from outcomes relative to the market,
> i.e. the improvement backlog.

n-weighted ECE (calibration only; revision 2, segment-clean corpus):

| sport | n records | model ECE | market ECE |
|---|---|---|---|
| mlb | 27,351 | 0.0494 | 0.0397 |
| soccer_intl | 4,265 | 0.3784 | 0.2666 |

The model trails the market on the same buckets in both sports -- narrowly in MLB, widely in
soccer. Top of the ranked worst-bucket backlog (model source, verbatim numbers):

| sport | time bucket | prob band | n | mean_p | mean_y | calib error |
|---|---|---|---|---|---|---|
| soccer_intl | 75-90+ | .2-.4 | 7 | 0.2108 | 1.0 | 0.7892 |
| soccer_intl | 30-45 | 0-.2 | 232 | 0.0951 | 0.6746 | 0.5795 |
| soccer_intl | 60-75 | .2-.4 | 88 | 0.2578 | 0.8295 | 0.5718 |
| soccer_intl | 15-30 | .4-.6 | 120 | 0.5 | 1.0 | 0.5 |
| soccer_intl | 30-45 | .4-.6 | 104 | 0.5002 | 1.0 | 0.4998 |

**Honest read:** on the segment-clean corpus the top of the backlog is all soccer_intl --
late minutes, the low-probability bands, and coin-flip (.4-.6) bands whose games all resolved
one way. That is the backlog the ranked list surfaces; it is market-trailing, not any edge.

**Two caveats stated on the page, not buried:**

- The single worst bucket (soccer 75-90+, .2-.4) is **n=7** -- flagged as top of the backlog
  but not statistically load-bearing.
- Several soccer buckets show `mean_y = 1.0` for hundreds of rows because the corpus contains
  **many correlated ticks per game** sharing one eventual outcome. Treat bucket counts as raw
  rows, not effective independent sample size.

---

## Reproduce

Both instruments have a `--check` self-check that fails loudly if the decomposition math or
the bucketing drifts. Run against the committed JSON:

```
# Instrument 1 -- Murphy decomposition (writes out/murphy_decomposition.json + PNG)
python -m scripts.platformkit.analytics_showcase.murphy_decomposition
python -m scripts.platformkit.analytics_showcase.murphy_decomposition --check

# Instrument 2 -- state-conditioned calibration (writes out/state_conditioned_calibration.json + PNG)
python -m scripts.platformkit.analytics_showcase.state_conditioned_calibration
python -m scripts.platformkit.analytics_showcase.state_conditioned_calibration --check
```

On a fresh clone the private `data/cache/ingame_grade_joined/` corpora are absent, so a live
re-run has nothing to read; the committed JSON + PNG are the recorded artifacts, and the
numbers on this page are copied from them verbatim.

---

## Why this matters to an employer

Decomposing the gap into reliability vs resolution says whether the market's lead is *my*
fault (recalibrate) or its *information advantage* (unavoidable given my snapshot freshness);
the ranked backlog then names the exact game states where my model is worst, small-n flags
and correlated-sample caveats included. The hire signal is building the diagnostic that
locates the loss and writing it down instead of reporting the one number that looks good.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
