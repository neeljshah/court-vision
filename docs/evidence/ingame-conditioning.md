# In-game conditioning: a static-to-conditional calibration finding

> Pregame, the market is efficient: my leak-free
> forecaster TRAILS the devigged close on MLB moneyline (+0.0039 Brier, 95% CI [+0.0028, +0.0051]) and soccer O/U 2.5 (+0.0076, [+0.0059, +0.0092]) and is indistinguishable from it on NBA moneyline at an underpowered n=372 (corrected 2026-10-06 from DM_RECOMPUTE_2026-09-24) and beats nothing. The one
> place the machinery measurably sharpens is IN-GAME -- fusing the pregame rating prior with
> the realized mid-game state improves win-probability calibration. A live book sees the
> score too, so this is a CALIBRATION result, not a claim of beating anyone. Every number
> below is Brier / MAE / row-count with its source artifact. The single truth-source for any
> figure is [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md); `edge_claimed = False`
> throughout, and no dollar, ROI, or edge figure appears anywhere on this page.

---

## The claim

The honest question is not "can I beat the close" -- I proved against myself that I cannot,
pregame -- but "does the system's mid-game conditioning actually sharpen the forecast." It
does, and the win is measured, not asserted: conditioning the win-probability forecaster on
the realized in-game state improves calibration (Brier) on real out-of-sample corpora in two
sports. This is forecaster quality, measured against the model's own static pregame prior,
not against the market. Against the contemporaneous Kalshi in-play price on the same ticks the
in-game models are BEHIND (measured 2026-09-14 on the 227-game corpus that later failed the
join-integrity check; the 178-game segmented revision keeps the verdict BEHIND).

**Staleness caveat.** The in-game model updates only at parsed state transitions, so on many
ticks it is staler than the market price, and the BEHIND verdict does not separate staleness
from forecast quality. As of 2026-09-14, model_prob changes on 8.3 pct of MLB ticks against
25.0 pct for the market price (source: `docs/evidence/ingame/GATE_A0_2026-09-14.md`, lines
44-45, measured on the 227-game corpus). How stale our in-play view runs is measured in the
[in-play latency paper](../papers/INPLAY_LATENCY_2026.md).

---

## The numbers, each labeled to its measurement

**Static -> conditional calibration (self-improvement, not a market comparison).**

| Sport | static (prior only) | conditional (prior + state) | Honesty label | Source |
|---|---|---|---|---|
| NBA | higher Brier | lower Brier (improves) | calibration finding, real-corpus OOS, `edge_claimed=False` | `scripts/platformkit/proof_nba/ingame_accuracy.py` |
| MLB | higher Brier | lower Brier (improves) | calibration finding, real-corpus OOS, `edge_claimed=False` | `scripts/platformkit/proof_mlb/ingame_accuracy.py` |

The packet records these as calibration findings against a static prior (JOB_EVIDENCE_PACKET
section 2, ML / validation table); they are not in the canonical figure list, so this page states the direction and
not the size.

Most of that lift is *mechanical* -- the scoreboard itself, which anyone watching the game
(including a live book) gets for free. A three-arm decomposition attributes most of the NBA
lift and nearly all of the MLB lift to conditioning on the realized score alone. The model's
own pregame rating prior adds a small remaining share in NBA and is essentially washed out by
mid-game in MLB. The model-prior share is the only part that is ours, and it is never stated
as larger.

**The honest market comparison (1593-game ALLGAMES_v3 run).** When I put the conditional
forecaster head-to-head against the market's own in-game win probability, the result is a
loss where it is powered and a tie everywhere else -- reported exactly as measured:

| Checkpoint | Model (Brier) | Market (Brier) | Delta (95% CI) | n | Verdict |
|---|---|---|---|---|---|
| end_q1 | 0.2006 | 0.1922 | **-0.0084 [-0.0161, -0.0008]** | 1592 | **MARKET_SHARPER_PROVISIONAL** |
| halftime | 0.1677 | 0.1638 | -0.0040 [-0.0098, 0.0015] | 1593 | UNDERPOWERED |
| end_q3 | 0.1233 | 0.1244 | 0.0011 [-0.0028, 0.0052] | 1593 | UNDERPOWERED |
| q4_under5 | 0.0938 | 0.0957 | 0.0019 [-0.0010, 0.0048] | 1593 | UNDERPOWERED |

Read plainly: at the one checkpoint with enough games to resolve, **the market is sharper
than my model** (the CI sits entirely below zero). At every later checkpoint the CIs straddle
zero -- I cannot distinguish the two, so I claim nothing. This is the "market is efficient; we
match the close" result, stated where it hurts. The static -> conditional improvement above is
real calibration self-improvement; it is not evidence of beating the live book, and this table
is why.

**Player-projection MAE (kept strictly separate from any Brier).** End-of-Q3 player
projections reduce MAE by **~46%** against the pregame baseline (pooled) -- but ~three of four
quarters of box score are already observed, so most of that is *mechanical*. The learned-head
value-add over a naive in-game carry-forward baseline is **~26%** (walk-forward, two
independent harnesses). **~26% is the number to lead with.** These heads use a confirmed
leak-clean 14-feature schema; they are never bundled with any end-of-Q3 Brier, because the
separate end-of-Q3 win-prob model carried a Q4 feature leak (documented in the retraction
story, not quoted here).

---

## Receipts

| Number | Artifact path |
|---|---|
| NBA static->conditional Brier improvement (calibration) | `scripts/platformkit/proof_nba/ingame_accuracy.py` |
| MLB static->conditional Brier improvement (calibration) | `scripts/platformkit/proof_mlb/ingame_accuracy.py` |
| Cross-sport roll-up | `scripts/platformkit/ingame_scoreboard.py` |
| end_q1 MARKET_SHARPER delta -0.0084, halftime/end_q3/q4 UNDERPOWERED, n~1593 | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_nba_winprob_ALLGAMES_v3.json` |
| Same, pre-registered ledger row | [`RECEIPTS.md`](../../RECEIPTS.md) (batch 6eba592d3a77, nba end_q1 row) |
| ~46% pooled / ~26% learned-head MAE lift | leak-clean 14-feature schema, two walk-forward harnesses; see [JOB_EVIDENCE_PACKET s3](../JOB_EVIDENCE_PACKET.md) |
| Full receipts write-up | [`docs/INGAME_PROOF.md`](../INGAME_PROOF.md) |

Every RECEIPTS.md row is read verbatim from a machine-readable artifact on disk -- no number
is hand-typed -- and the ledger is append-only, keyed to a content hash of its sources.

---

## Reproduce on a fresh clone

```
# NBA + MLB in-game calibration scoreboard (real corpus if present)
python -m scripts.platformkit.ingame_scoreboard

# the per-sport proof harnesses directly
python -m scripts.platformkit.proof_nba.ingame_accuracy
python -m scripts.platformkit.proof_mlb.ingame_accuracy

# the leak property test (truncation invariance) -- runs on any clone
python -m pytest tests/test_ingame_leak_free.py -q
```

On a fresh clone the private corpora are absent, so the live re-run prints
`VALIDATION_PENDING` and falls back to the recorded table -- it never fabricates a corpus it
does not have. The committed synthetic NBA fixture prints **no improvement**; that is a
synthetic-anchor artifact of the fixture, disclosed so a reviewer is not surprised, not a
regression. The real-corpus OOS result is the win; the fixture proves the pipeline runs
end-to-end.

---

## Why this matters

The in-game conditioning result is small, honest, and load-bearing for exactly that reason.
The static -> conditional Brier improvement is a real calibration gain, most of it mechanical,
with the model's own prior contributing a small measured share in NBA. Benchmarked against the
live market, the conditional forecaster is sharper nowhere it is powered: the market wins the
one resolvable checkpoint and ties everywhere else, the loss stated as plainly as any win. The
hire signal is not the metric. It is a forecaster whose author scores it against the market,
publishes the checkpoint where the market wins, and refuses to convert a real calibration
improvement into an edge claim it did not earn.

---

*edge_claimed = False everywhere. Every number is Brier / MAE / row-count vs a real
out-of-sample corpus, never a dollar figure. Retracted measurement artifacts appear only in
[JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md), never on this page.*

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
