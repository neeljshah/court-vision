# The In-Game Conditioning Story -- the one measured calibration win

> Pregame, the market is efficient: across 4 sports and 6 independent corpora my
> leak-free forecaster MATCHES the Shin-devigged closing line within noise and BEATS
> nothing (see [MARKET_EFFICIENCY_PROOF.md](MARKET_EFFICIENCY_PROOF.md)). The one place
> the machinery measurably sharpens is IN-GAME: fusing the pregame rating prior with the
> realized mid-game state improves win-probability calibration. A live book sees the
> score too -- so this is a CALIBRATION result, not a claim of beating anyone. Every
> number below is Brier / MAE / row-count, each carrying its source artifact path.
> `edge_claimed = False` throughout; no dollar, ROI, or edge figure appears anywhere.
>
> Honesty truth-source for any number: [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).

---

## 1. The one-paragraph story

The market is efficient on price. I proved it against myself: a real-data edge hunt
across NBA / MLB / soccer / tennis rejected every candidate pregame signal on >=2
independent corpora, including catching my own full-sample lifts that sign-flip out of
sample. Given that, the honest question is not "can I beat the close" but "does the
system's mid-game conditioning actually sharpen the forecast". It does, and the win is
measured, not asserted: conditioning the win-probability forecaster on the realized
in-game state improves calibration (Brier) on a real out-of-sample corpus in two sports.
This is forecaster quality -- a live book also sees the score, so no beat-the-market test
applies and no money is claimed. The credential is that the same harness that measures
the win is the one that is adversarial to its author: it is truncation-invariant by
property test, walk-forward, multi-corpus gated, and it once caught a Q4 lookahead leak
in my own end-of-Q3 model, which is documented below rather than buried.

---

## 2. The numbers (each with its receipt)

| Claim | Number | Honesty label | Source artifact |
|---|---|---|---|
| In-game state conditioning sharpens NBA win-prob calibration | Brier **0.209 -> 0.159** | calibration, real-corpus OOS, `edge_claimed=False` | `scripts/platformkit/proof_nba/ingame_accuracy.py` (rolled up by `scripts/platformkit/ingame_scoreboard.py`) |
| Same, MLB | Brier **0.241 -> 0.126** | calibration, real-corpus OOS, `edge_claimed=False` | `scripts/platformkit/proof_mlb/ingame_accuracy.py` |
| End-of-Q3 player-projection MAE, learned-head value-add over a naive in-game carry-forward baseline | **~26%** reduction (walk-forward) | the honest value-add number -- **lead with this** | leak-clean 14-feature schema; two independent WF harnesses |
| End-of-Q3 player-projection MAE vs the *pregame* baseline (pooled) | **~46%** reduction | mostly *mechanical* -- 3 of 4 quarters of box score are observed | same as above |
| Live in-game settlement join, MLB | **178** ticker files / **67,519** rows | scale receipt; each row carries model_prob + market_prob + outcome + close_source | `scripts/platformkit/ingame/ticker_settlement_join.py` -> `data/cache/ingame_grade_joined/mlb/` |
| Live in-game settlement join, international soccer | **48** ticker files / **8,700** rows | same four fields per row | `data/cache/ingame_grade_joined/soccer_intl/` |

Scoping note (stated, not hidden): the NBA / MLB Brier wins are measured on the real
local corpora. The committed **synthetic** fixture prints **no improvement** on the NBA
row -- a synthetic-anchor artifact, not a regression -- so the reproduce path below shows
both. The real-corpus OOS result is the win; the fixture proves the pipeline runs
end-to-end on a fresh clone.

**Never** pair the end-of-Q3 MAE numbers with any end-of-Q3 Brier number: the MAE heads
use a clean 14-feature schema, but the separate endQ3 win-prob model had a Q4 leak (see
Section 4). They are different models measured on different targets.

---

## 3. How it's validated (the harness is adversarial to its author)

The conditioning win is only meaningful because the gate around it is built to refute,
not confirm. Every in-game feature and model clears the same chain used for the pregame
edge hunt:

1. **Walk-forward, expanding window.** Train only on strictly-earlier states; the
   backtester asserts `max_train_date < min_test_date` every fold or fails. No K-fold on
   time-ordered data. Code: `src/prediction/walk_forward_backtester.py`.
2. **Truncation invariance (the leak property test).** A streaming feature at time T must
   be byte-identical whether or not future events exist. The test re-featurizes a
   truncated event stream and asserts every past row is unchanged. If a feature could peek
   at the future, this fails. Code: `tests/test_ingame_leak_free.py` (passes).
3. **Multi-corpus acceptance.** A single-window lift is treated as an artifact. A gain has
   to hold on >=2 independent corpora before it counts (the pregame edge hunt shows the
   inverse: candidates that looked positive full-sample sign-flipped across calendar
   halves and were rejected). Code: `scripts/validate_calibration_multicorpus.py`.
4. **Fail-closed.** On a fresh clone the private corpora are absent, so the live re-run
   prints `VALIDATION_PENDING` and falls back to the recorded table rather than
   fabricating a number. The synthetic fixture's no-improvement NBA row is reported as-is.

The point of Section 2's numbers is that they survived this, and that the same instrument
caught the leak in Section 4.

---

## 4. The leak I caught in my own pipeline (the credential)

The most load-bearing evidence here is a negative result about my own work.

An earlier end-of-Q3 win-probability model quietly peeked at the quarter it was supposed
to predict. Two features were computed from 4th-quarter data, so the "end of Q3" forecast
had already seen part of Q4. The famous headline it produced does not survive, and it is
listed in the do-not-claim register, not quoted here.

- The harness caught it: the truncation-invariance and walk-forward checks surfaced the
  lookahead rather than letting a flattering number ship.
- The honest, leak-free walk-forward endQ3 Brier after removing the two Q4-derived
  features is **~0.141**.
- A controlled A/B measured the leak's inflation at **~4% relative** -- I know the size of
  my own mistake because I ran the experiment to measure it.

This is why the MAE heads (Section 2) are kept strictly separate from any endQ3 Brier: the
14-feature MAE schema is confirmed leak-clean and does **not** share the Q4 contamination.
Frame: the win is the conditioning result; the credential is that I built the instrument
that caught my own leak and wrote the negative result down.

---

## 5. Reproduce it

From a clone (the fixture path runs offline; the live path needs the private corpora):

```
# NBA + MLB in-game calibration scoreboard, real corpus if present
python -m scripts.platformkit.ingame_scoreboard

# the per-sport proof harnesses directly
python -m scripts.platformkit.proof_nba.ingame_accuracy
python -m scripts.platformkit.proof_mlb.ingame_accuracy

# the leak property test (truncation invariance) -- runs on any clone
python -m pytest tests/test_ingame_leak_free.py -q

# rebuild the live in-game settlement join (model + market + outcome + close on one row)
python -m scripts.platformkit.ingame.ticker_settlement_join
```

On a fresh clone with no private corpus, the scoreboard prints `VALIDATION_PENDING` and
the recorded numbers; the committed synthetic NBA fixture prints no-improvement. Both are
the honest behaviour, not a failure -- the harness never fabricates a corpus it does not
have.

---

## 6. Honest limits

- **This is calibration, not edge.** A live book sees the same score at the same time.
  The measured Brier improvement is forecaster sharpness on a real OOS corpus, not a
  demonstrated ability to beat a live in-game price. No DM-vs-close test applies to an
  in-game number, and none is claimed.
- **Most of the ~46% endQ3 MAE lift is mechanical.** Three of four quarters of box score
  are already observed by end of Q3. The learned-head value-add over a naive carry-forward
  baseline is the ~26% figure -- that is the one to lead with.
- **The synthetic fixture shows no improvement on NBA.** That is a synthetic-anchor
  artifact of the committed fixture, disclosed here so a reviewer running the fixture path
  is not surprised. The real-corpus OOS result is the win.
- **Settlement joins are scale receipts, not edge.** 67,519 MLB and 8,700 soccer rows each
  carry model_prob + market_prob + outcome + close_source together; that they exist and
  join correctly is the claim, not that they beat the market.
- **No end-of-Q3 Brier is quoted as a competitive number.** The only endQ3 Brier stated
  anywhere here is the ~0.141 leak-free figure, in the context of the leak I caught.

---

*edge_claimed = False everywhere. Every number is Brier / MAE / row-count vs a real
out-of-sample corpus, never a dollar figure. Retracted measurement artifacts appear only
in [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) and
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md), never on this page.*

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
</content>
</invoke>
