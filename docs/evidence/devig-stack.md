# The Devig Stack -- market math from scratch, used as the yardstick I grade against

> I implemented four de-vig methods from scratch -- including the Shin (1992)
> insider-trading model via a numerically stable bisection solver -- wired them into
> production, and then used the devigged closing line as the BENCHMARK MY OWN MODEL IS
> GRADED AGAINST. This is not a marketing prop ("look, I know Shin"): it is the honest
> yardstick that let me prove the market is efficient and that my model only MATCHES it.
> The single truth-source for any figure below is
> [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md); `edge_claimed = False`
> throughout and no dollar, ROI, or edge figure appears anywhere on this page.

---

## The claim

A vigged sportsbook price is not a probability -- it carries the book's margin (the
overround). To grade a forecaster against "what the market really thinks" you first have
to strip that vig honestly, and the naive retail method (proportional / additive) is
biased on favourite-longshot lines. So `src/prediction/devig.py` implements four methods
from scratch and dispatches between them:

- **proportional / additive** -- symmetric power-sum normalization, the biased retail default.
- **multiplicative** -- power-renormalization, solved by bisection for the exponent `k`.
- **power** -- the closed-form n-th-root approximation.
- **shin** -- the Shin (1992) insider-trading model, solved by a numerically stable
  bisection on `z` (the inferred informed-money fraction). Shin loads the vig
  asymmetrically -- more onto the longshot -- so on heavy favourites it returns a higher
  favourite probability than proportional does. It is the closest thing to the sharp fair
  price, which is why it is the default.

All four are pure functions over probabilities (with American-odds converters),
production-wired behind `POST /api/devig` where `method` defaults to `shin`, and covered
by tests. The point is not that the code exists; it is what the code is FOR.

---

## How the devigged close becomes the yardstick

Once you can devig honestly, the Shin-devigged closing line is the strongest public
estimate of the true probability -- so it becomes the thing my forecaster is scored
against, not something I claim to beat. Two committed harnesses do exactly this:

- `scripts/platformkit/beat_the_close_scoreboard.py` puts my leak-free out-of-sample
  forecaster head-to-head with the Shin-devigged close on the SAME real outcomes, per
  sport and market, reporting Brier / RMSE with sample counts.
- `scripts/platformkit/edge_hunt_scoreboard.py` runs the consolidated candidate-signal
  REJECT scoreboard through the same leak-free gate.

The verdict language is copied out honestly, never softened. On team-strength markets
(NBA and MLB moneyline, soccer O/U-2.5) the model **MATCHES** the devigged close within
sampling noise -- the realistic best case for an efficient market. On totals and ATP
match-win it **TRAILS**, and the docs label that gap as the market's FRESHNESS edge
(injuries / lineups / starting pitcher / park / weather) a public-plus-box-score model
cannot see -- data-bound, not a model defect. MATCH is the ceiling, not a beat; TRAILS is
printed where it hurts. Nothing beats the close pregame, and that is recorded as the
correct, expected result, not a failure.

---

## Receipts -- verified committed paths

| Claim | Artifact (committed) |
|---|---|
| Four devig methods from scratch; Shin via stable bisection on `z` | `src/prediction/devig.py` |
| Production-wired, defaults to `shin` | `api/devig_router.py` (`POST /api/devig`, `method="shin"` default) |
| Devig unit tests + router tests | `tests/test_devig.py`, `tests/test_devig_router.py` |
| Devigged close as the graded yardstick (MATCH/TRAILS) | `scripts/platformkit/beat_the_close_scoreboard.py` |
| Consolidated candidate-REJECT scoreboard | `scripts/platformkit/edge_hunt_scoreboard.py` |
| Recorded MATCH/TRAILS table + full write-up | `docs/MARKET_EFFICIENCY_PROOF.md` |
| Leak-free gate the scoring rides on | `scripts/platformkit/eval_gate/walkforward.py`, `scripts/platformkit/eval_gate/dm_test.py` |
| Committed end-to-end proof fixture (private corpora absent on clone) | `tests/fixtures/proof/` |
| Honesty truth-source for every number | `docs/JOB_EVIDENCE_PACKET.md` (rows 81, 82, 87) |

The recorded MATCH baselines in `MARKET_EFFICIENCY_PROOF.md`: NBA moneyline Brier
0.1735 vs close 0.1672 (n=372), MLB moneyline 0.2429 vs 0.2390 (n=13,992), soccer
O/U-2.5 0.2465 vs 0.2390 (n=7,558) all MATCH; totals and ATP TRAIL by the freshness gap.
These are calibration / sharpness numbers versus the devigged close, never a $ figure.

---

## Reproduce on a fresh clone

```
# devig math + router behaviour (runs on any clone)
python -m pytest tests/test_devig.py tests/test_devig_router.py -q

# pregame MATCH baselines via the committed fixture (proves the pipeline end-to-end)
python -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof

# consolidated market-efficiency / candidate-REJECT scoreboard (recorded table; <60s)
python -m scripts.platformkit.edge_hunt_scoreboard
```

On a fresh clone the private corpora are absent, so the live re-run prints
`VALIDATION_PENDING` and falls back to the recorded canonical table -- it never fabricates
a number.

---

## Why it matters

Anyone can call a devig library. The hire signal is what the devig is FOR: I built the
market math from first principles, chose the Shin model because it is the sharpest fair
price, and then pointed it AT MY OWN FORECASTER -- making the devigged close the benchmark
I have to match rather than a number I advertise beating. The result: I MATCH the
efficient close and beat nothing pregame, and I copied that verdict out without softening
it. The instrument that proves it -- honest de-vig plus a leak-free gate -- is the credential.

---

*edge_claimed = False everywhere. Every number is Brier / RMSE / row-count vs a real
out-of-sample corpus, never a dollar figure. Retracted measurement artifacts appear only
in [JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md), never on this page.*

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
