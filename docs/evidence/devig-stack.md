# The Devig Stack -- market math from scratch, used as the yardstick I grade against

> I implemented four de-vig methods from scratch -- including the Shin (1992)
> insider-trading model via a numerically stable bisection solver -- wired them into
> production, and then used the devigged closing line as the BENCHMARK MY OWN MODEL IS
> GRADED AGAINST. This is not a marketing prop ("look, I know Shin"): it is the yardstick
> my model is graded against: it TRAILS the devigged close on MLB moneyline and soccer O/U 2.5, and on NBA moneyline the interval includes zero, so I cannot tell.
> The single truth-source for any figure below is
> [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md); `edge_claimed = False`
> throughout and no dollar, ROI, or edge figure appears anywhere on this page.

---

## The claim

A vigged sportsbook price is not a probability -- it carries the book's margin (the
overround). To grade a forecaster against "what the market really thinks" you first have
to strip that vig honestly. So `src/prediction/devig.py` implements four methods from
scratch and dispatches between them. Formulas as quoted in
[method/DEVIG_METHODS.md](method/DEVIG_METHODS.md), with pi_i = 1 / decimal price summing
to S > 1 (the overround):

- **proportional** (alias `additive`) -- p_i = pi_i / S
- **multiplicative** -- find k with sum_i pi_i^k = 1 (bisection); p_i = pi_i^k
- **power** -- p_i = pi_i^(1/n) / sum_j pi_j^(1/n), n = number of outcomes by default
- **shin** (Shin 1992) -- find z in [0, 1) with sum_i p_i(z) = 1 (bisection), where
  `p_of_z(z, q) = (sqrt(z*z + 4*(1 - z)*q*q / s) - z) / (2*(1 - z))`

**Which method the headline rows use.** Proportional is the primary method on the main
pregame rows (MLB moneyline and soccer O/U 2.5); Shin is the sensitivity check. For NBA
moneyline both are reported, and the headline row the verdict sentence cites is the Shin
one, with the proportional row beside it (docs/papers/PREGAME_VS_CLOSE_2026.md sections 3.2
and 4.1). Multiplicative and power are not used in any headline row.

All four are pure functions over probabilities (with American-odds converters), the
library dispatcher `devig(vigged, method="shin")` and `POST /api/devig` default to `shin`,
and the code is covered by tests. The point is not that the code exists; it is what it grades against.

---

## How the devigged close becomes the yardstick

Once you can devig honestly, the devigged closing line is a strong public estimate of
the true probability -- so it becomes the thing my forecaster is scored against, not
something I claim to beat. No de-vig recovers the true probability exactly; each is a model
of how the margin is spread, which is why a second method is reported as a sensitivity check. Two committed harnesses do exactly this:

- `scripts/platformkit/beat_the_close_scoreboard.py` puts my leak-free out-of-sample
  forecaster head-to-head with the devigged close on the SAME real outcomes, per
  sport and market, reporting Brier / RMSE with sample counts.
- `scripts/platformkit/edge_hunt_scoreboard.py` runs the consolidated candidate-signal
  REJECT scoreboard through the same leak-free gate.

The verdict language is copied out honestly, never softened. On MLB moneyline and soccer
O/U 2.5 the model **TRAILS** the devigged close (95% intervals above zero); on NBA moneyline
the interval includes zero at an underpowered n=372, so I cannot tell. On totals and ATP
match-win it **TRAILS**, and the docs label that gap as the market's FRESHNESS edge
(injuries / lineups / starting pitcher / park / weather) a public-plus-box-score model
cannot see -- data-bound, not a model defect. TRAILS is printed where it hurts, and
"cannot tell" is not a match. Nothing beats the close pregame, and that is recorded as the
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

The recorded pregame baselines in `MARKET_EFFICIENCY_PROOF.md`: NBA moneyline Brier
0.1735 vs close 0.1672 (n=372), MLB moneyline 0.2429 vs 0.2390 (n=13,992), soccer
O/U-2.5 0.2465 vs 0.2390 (n=7,558). Read against the game-clustered DM intervals
(DM_RECOMPUTE_2026-09-24), MLB and soccer TRAIL the close and NBA cannot be told apart from
it (interval includes zero); totals and ATP TRAIL by the freshness gap.
These are calibration / sharpness numbers versus the devigged close, never a $ figure.

---

## Reproduce on a fresh clone

```
# devig math + router behaviour (runs on any clone)
python -m pytest tests/test_devig.py tests/test_devig_router.py -q

# pregame baselines vs the close via the committed fixture (proves the pipeline end-to-end)
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
market math from first principles, reported a second de-vig method as a sensitivity
check, and then pointed it AT MY OWN FORECASTER -- making the devigged close the benchmark
I am graded against rather than a number I advertise beating. The result: it TRAILS the devigged close on MLB moneyline and soccer O/U 2.5, and on NBA moneyline the interval includes zero, so I cannot tell.
Nothing beats the close pregame, and I copied that verdict out without softening it. The instrument that proves it -- honest de-vig plus a leak-free gate -- is the credential.

---

*edge_claimed = False everywhere. Every number is Brier / RMSE / row-count vs a real
out-of-sample corpus, never a dollar figure. Retracted measurement artifacts appear only
in [JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md), never on this page.*

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
