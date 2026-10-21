# When the market out-forecasts us -- measured, bucketed, and published

> A calibrated forecaster earns trust by publishing where it *loses*, not just where it wins.
> This page does exactly that: it measures when the market out-forecasts our model, bucketed
> by how far apart the two disagree, and tracks that gap over calendar time. Every number
> below is quoted verbatim from committed JSON. The single truth-source for any figure is
> [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md). No dollar/ROI/edge is claimed
> anywhere -- both analytics carry `edge_claimed: false`.

---

## The claim

We do not hide the cases where the market beats us. We instrument them. Two published
analytics answer two honest questions:

1. **When our model disagrees with the market, who is usually right?**
2. **Is that relationship stable over calendar time, or drifting?**

The answer to both, stated plainly, is a market-efficiency confirmation: at the largest
disagreements the market is usually right, and across every available month the market's
Brier and ECE beat the model's. That is the correct result for an efficient market, and the
credibility signal is that we measure and publish it rather than quoting only the buckets
where we happen to look good.

---

## 1. Who is right when we disagree? (market_disagreement_profile)

**Revision 2, segment-clean corpus** (rebuilt 2026-09-16 from the 178-game segmented MLB corpus; see the [join-integrity finding](/analytics/findings/ingame-join-integrity/)). Revision 1 was withdrawn: its 227-game MLB corpus failed the join-integrity check (126 of 227 stored files mixed ticks from consecutive-day games under one outcome label), so its figures are not republished here.

Every graded in-game row is bucketed by `|model_prob - market_prob|` into four bands
(`<.02`, `.02-.05`, `.05-.10`, `>=.10`). Per bucket we report the row count, the model's
Brier, the market's Brier, and `model_closer_rate` -- the fraction of rows where the model's
absolute error beat the market's (ties excluded).

In MLB the pattern is monotonic: the further our model strays from the market, the more often
the market turns out right, and the wider the market's Brier advantage. In soccer_intl the widest
bucket is again the worst for the model, but the narrower buckets do not fall in order.

**MLB** (`data/cache/ingame_grade_joined/mlb_segmented/`):

| Disagreement bucket | n | model Brier | market Brier | model_closer_rate |
|---|---|---|---|---|
| `<.02`    | 4,649 | 0.129506 | 0.129087 | 0.4166 |
| `.02-.05` | 5,690 | 0.162348 | 0.161486 | 0.4130 |
| `.05-.10` | 8,482 | 0.179072 | 0.177298 | 0.3479 |
| `>=.10`   | 8,530 | 0.177763 | 0.129824 | 0.1994 |

**soccer_intl** (`data/cache/ingame_grade_joined/soccer_intl_segmented/`):

| Disagreement bucket | n | model Brier | market Brier | model_closer_rate |
|---|---|---|---|---|
| `<.02`    | 554 | 0.142768 | 0.137637 | 0.2292 |
| `.02-.05` | 679 | 0.113592 | 0.104293 | 0.3756 |
| `.05-.10` | 741 | 0.132395 | 0.103844 | 0.4103 |
| `>=.10`   | 2,291 | 0.508022 | 0.265530 | 0.1048 |

Revision 2 headline, as the join-integrity finding publishes it: at disagreement >=.10 the
model is closer 0.1994 of the time (Brier 0.177763 vs 0.129824, n=8,530 MLB ticks); in
soccer_intl it is closer 0.1048 of the time, and the market's Brier is lower in both. When we
agree with the market (`<.02`) the two are indistinguishable (MLB 0.129506 vs 0.129087). The signal is
unambiguous: our disagreements with the market are, on average, our mistakes.

![Model vs market Brier by disagreement bucket, MLB and soccer_intl; model_closer_rate falls as disagreement grows](../img/market_disagreement_profile.png)

*Figure: per-bucket model Brier vs market Brier and `model_closer_rate` for MLB and
soccer_intl. Data:
[`scripts/platformkit/analytics_showcase/out/market_disagreement_profile.json`](../../scripts/platformkit/analytics_showcase/out/market_disagreement_profile.json)
(`edge_claimed: false`).*

---

## 2. Is the gap stable over time? (calibration_over_time)

The same segment-clean corpora (revision 2), split by calendar month, scored for both Brier and ECE (10-bin
expected calibration error). Only two months of data exist in either corpus (2026-06,
2026-07), so this is a **two-point trend, not a seasonal-drift study** -- disclosed as such
rather than dressed up. A drift-significance test is deferred until >=4 months of corpus
exist.

**MLB:**

| Month | n | model Brier | market Brier | model ECE | market ECE |
|---|---|---|---|---|---|
| 2026-06 | 5,030 | 0.1968 | 0.1873 | 0.1265 | 0.1210 |
| 2026-07 | 22,321 | 0.1600 | 0.1428 | 0.0750 | 0.0439 |

**soccer_intl:**

| Month | n | model Brier | market Brier | model ECE | market ECE |
|---|---|---|---|---|---|
| 2026-06 | 1,213 | 0.3273 | 0.1955 | 0.3644 | 0.2596 |
| 2026-07 | 3,052 | 0.3346 | 0.1950 | 0.4243 | 0.2952 |

The honest read: the market beats the model on Brier and ECE in **every** sport-month cell.
The MLB model improves month over month (0.1968 -> 0.1600) but the market improves faster
(0.1873 -> 0.1428), so the gap widens. soccer_intl is roughly flat for both (model 0.3273 ->
0.3346, market 0.1955 -> 0.1950), with the model far behind in both months. There is no drift-reversal and no edge to claim -- this
is market efficiency with a visible, if data-thin, time dimension.

![Monthly model vs market Brier and ECE for MLB and soccer_intl across 2026-06 and 2026-07](../img/calibration_over_time.png)

*Figure: monthly model-vs-market Brier and ECE. Data:
[`scripts/platformkit/analytics_showcase/out/calibration_over_time.json`](../../scripts/platformkit/analytics_showcase/out/calibration_over_time.json).*

---

## Reproduce

Both scripts read the private joined-grade corpora
(`data/cache/ingame_grade_joined/{mlb_segmented,soccer_intl_segmented}/`, gitignored) and rewrite their
committed JSON plus the charts under `docs/img/`:

```
# Disagreement profile (also: --check for a self-verifying assertion pass)
python -m scripts.platformkit.analytics_showcase.market_disagreement_profile

# Monthly calibration drift
python -m scripts.platformkit.analytics_showcase.calibration_over_time
```

On a fresh clone the private corpora are absent; the committed JSON and PNG in the repo are
the recorded run. `mlb_clean` is a byte-identical dedup of `mlb` and is skipped by both
scripts.

---

## Why this matters to an employer

The field standard for a forecaster is calibration, and the honest test of calibration is whether you
publish your losses. These two analytics are built to surface exactly the cases where the market
out-forecasts us -- the largest-disagreement bucket and the worst month -- and they say so in
plain numbers. That is the same discipline behind the rest of this repo:
measure against a real market baseline, keep the negative result, and never convert
prediction quality into an edge claim.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
