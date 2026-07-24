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

| sport | n | model Brier | market Brier | Brier gap | reliability gap | resolution gap |
|---|---|---|---|---|---|---|
| mlb | 78,986 | 0.237684 | 0.206653 | +0.0310 | +0.0066 | -0.0235 |
| soccer_intl | 9,003 | 0.227887 | 0.142726 | +0.0852 | +0.0394 | -0.0446 |

Reliability gaps are small; resolution gaps carry most of the deficit in both sports. The
verdict string, copied verbatim from the JSON:

> mlb: model Brier 0.2377 is worse than market 0.2067 (gap=+0.0310); driven mainly by
> resolution (information, not fixable by recalibration) (reliability_gap=+0.0066,
> resolution_gap=-0.0235). soccer_intl: model Brier 0.2279 is worse than market 0.1427
> (gap=+0.0852); driven mainly by resolution (information, not fixable by recalibration)
> (reliability_gap=+0.0394, resolution_gap=-0.0446).

**Honest read:** the market isn't beating the model because the model is badly calibrated --
it's beating it because it resolves more information into its probability (state changes it
can see that our checkpoint snapshots can't). This is consistent with the standing in-game
freshness finding already on record: early-game deficits are a *news* gap, not a *model* gap.

**Reconstruction caveat (stated, not hidden):** the binned formula reconstructs MLB model
Brier as 0.237166 vs the exact 0.237684 -- a small residual from within-bin prediction
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

n-weighted ECE (calibration only):

| sport | n records | model ECE | market ECE |
|---|---|---|---|
| mlb | 78,986 | 0.079 | 0.0591 |
| soccer_intl | 9,003 | 0.3609 | 0.2511 |

The model trails the market on the same buckets in both sports -- narrowly in MLB, widely in
soccer. Top of the ranked worst-bucket backlog (model source, verbatim numbers):

| sport | time bucket | prob band | n | mean_p | mean_y | calib error |
|---|---|---|---|---|---|---|
| soccer_intl | 75-90+ | .2-.4 | 10 | 0.2117 | 1.0 | 0.7883 |
| soccer_intl | 60-75 | .2-.4 | 90 | 0.2577 | 0.8333 | 0.5756 |
| soccer_intl | 30-45 | 0-.2 | 264 | 0.0935 | 0.6534 | 0.5599 |
| soccer_intl | 75-90+ | 0-.2 | 379 | 0.0661 | 0.5739 | 0.5078 |
| mlb | late(inn7+) | .8-1 | 5,037 | 0.9211 | 0.6853 | 0.2357 |

**Honest read:** the model is closest to the market early and drifts further as game state
resolves -- late innings, late minutes, and the low-probability soccer bands. That drift is
the backlog the ranked list surfaces; it is market-trailing, not any edge.

**Two caveats stated on the page, not buried:**

- The single worst bucket (soccer 75-90+, .2-.4) is **n=10** -- flagged as top of the backlog
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
