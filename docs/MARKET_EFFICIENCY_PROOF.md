# Market-Efficiency Proof -- a real-data edge hunt that rejected every candidate

> The headline credential. I ran a real-data edge hunt across 4 sports and 6 independent
> corpora, MATCHED the Shin-devigged closing line within noise on team-strength markets, and
> REJECTED every candidate pregame edge -- including catching my own full-sample signals that
> SIGN-FLIP out-of-sample. "The market is efficient; no edge survived" is the FEATURE here, not
> a failure: it is the expected, correct result for efficient markets, and the self-auditing
> harness that proves it is the credential.
>
> This is DECISION-SUPPORT, not a picks / profit / +EV / ROI product. Every number below is a
> CALIBRATION / SHARPNESS measurement (Brier, RMSE, BSS) vs the devigged market close.
> `edge_claimed = False` everywhere; no $ figure is produced. The single honesty truth-source
> is [docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md); retracted numbers appear only there
> (and in [docs/KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)), never here.

---

## 1. Pregame baselines -- we MATCH the efficient close on team-strength markets

Our leak-free OOS forecaster vs the Shin-devigged closing line, on the SAME real outcomes.
MATCH = within sampling noise of the sharp close (the realistic best case for an efficient
market -- beating it would imply information the close lacks). BEHIND = the market's freshness
edge (injuries / lineups / starting pitcher / park / weather) a public + box-score model
cannot see; the gap is data-bound, not a model defect. Source: the per-market proof harnesses
(see [docs/PROOFS.md](PROOFS.md)) rolled up in `vault/_Edge_Maps/_Beat_The_Close.md`.

| Sport | Market | Metric | N | Our model | Close | Gap | Standing |
|---|---|---|---|---|---|---|---|
| NBA | moneyline | Brier | 372 | 0.1735 | 0.1672 | +0.0063 | MATCH |
| NBA | total O/U | RMSE | 372 | 19.17 | 18.11 | +1.06 | BEHIND (freshness) |
| MLB | moneyline | Brier | 13,992 | 0.2429 | 0.2390 | +0.0039 | MATCH |
| MLB | total O/U | RMSE | 1,679 | 4.72 | 4.44 | +0.28 | BEHIND (freshness) |
| Soccer | O/U-2.5 | Brier | 7,558 | 0.2465 | 0.2390 | +0.0076 | MATCH |
| Tennis (ATP) | match-win | Brier | 7,374 | 0.2177 | 0.2028 | +0.0149 | BEHIND (freshness) |

Team-strength win markets (NBA & MLB moneyline, soccer O/U) MATCH within sampling noise.
Totals / ATP are BEHIND ONLY by the freshness gap. Nothing BEATS the close pregame -- and that
is the expected, honest outcome.

---

## 2. The candidate-REJECT table -- nothing survived, and I caught the overfits

Every candidate schedule / fatigue / form / h2h / totals signal scored through the REAL
leak-free gate (walk-forward, purge + embargo, slope fit inside the training window, clustered
Diebold-Mariano) on >=2 independent corpora. SHIP requires BSS>0 AND DM p<0.05 AND N>=200.
Each row is a REJECT. The load-bearing self-audit evidence is the right-hand column: positive
full-sample lifts REVERSE SIGN on the held-out calendar half (the overfit signature). Reproduce
the canonical table -- and re-run the real NBA harness verbatim -- with
`python -m scripts.platformkit.edge_hunt_scoreboard` (`--live` re-runs on the real corpus).

| Candidate | Corpora | BSS vs close | DM p | N | Verdict | Overfit signature |
|---|---|---|---|---|---|---|
| NBA b2b_diff | 2026 H1/H2 | +0.0006 | 0.657 | 1103 | REJECT | sign flips H1<->H2 |
| NBA three_in_four_diff | 2026 H1/H2 | +0.0003 | 0.795 | 1156 | REJECT | sign flips H1<->H2 |
| NBA rest_diff | 2026 H1/H2 | +0.0007 | 0.508 | 1103 | REJECT | sign flips H1<->H2 |
| NBA home_court (HCA probe) | 2026 H1/H2 | 0.0000 | 0.173 | 1156 | REJECT | HCA fully in devig |
| NBA altitude_home | 2026 H1/H2 | -0.0014 | 0.162 | 1156 | REJECT | consistently worse |
| NBA travel_diff | 2026 H1/H2 | +0.0011 | 0.759 | 1103 | REJECT | sign flips H1<->H2 |
| MLB rest/streak/h2h x3 | NL + AL | <=0 | n/s | 14k ea | REJECT | reject on BOTH leagues |
| Soccer rest/totals/h2h x3 | by div | <=0 | n/s | 7.5k | REJECT | fail null-shuffle / BH-FDR |
| Tennis fatigue/surface/h2h x3 | 2 corpora | <=0 | n/s | 7.4k | REJECT | fail null-shuffle / BH-FDR |
| MLB totals slice (NL ALL) | NL | -0.0141 | 0.0092 | 1594 | REJECT | close BEATS us |
| MLB totals slice (AL ALL) | AL | -0.0185 | 0.0002 | 1610 | REJECT | close BEATS us |
| MLB open->close CLV capture | NL + AL | n/a | CI~0 | 25.5k | REJECT | NL/AL sign disagree |

The NBA schedule signals are the cleanest self-audit: the schedule is a deterministic fact
known LONG before any line moves, so the entire scored sample is confirmed-before by
construction. A signal that looked positive on the full season but reverses sign across the two
calendar halves is overfit, not edge -- the gate catches it and REJECTS. The market already
prices deterministic calendar physics (b2b / 3-in-4 / rest / travel / altitude / HCA).

---

## 3. CLV exists -- but it is the market's own sharpening, not ours to harvest

Line-movement closing-line value (CLV) is real as a MARKET phenomenon: the close is sharper
than the open (MLB Diebold-Mariano on log-loss p=0.0010, N=27,975; Brier-skill of close over
open +0.43%). But it is not something a retrospective model captures:

- A leak-free open-time model has ~0 correlation with the realized open->close move:
  corr(model_p - opener, close - open) = +0.0038, CI95 [-0.046, +0.055] = zero.
- CLV-capture from disagreement straddles zero AND disagrees in sign across the two
  independent corpora: NL +0.108 pp, AL -0.017 pp -- the overfit signature again. REJECT.

The freshness lane is a same-day-information / speed edge (betting an opener before a roster
move shifts the line), not a cleverer closing-line feature. Not ours to harvest. This confirms
the standing discipline that CLV is measured forward, never claimed retrospectively.

---

## 4. HONEST BOTTOM LINE

NOTHING survived >=2 corpora + DM p<0.05 + N>=200 as a market-beating pregame edge. Every
schedule / fatigue / form / h2h / totals candidate REJECTED across independent corpora; every
positive full-sample BSS reversed sign on the held-out half. The market is efficient on every
pregame slice measured. This is the honest, correct result for efficient markets -- recorded as
a SUCCESS, not a failure. The harness that proves it -- and that catches my own inflated
full-sample lifts -- is the credential.

The one genuine, measured, calibrated win is IN-GAME conditioning (NBA Brier 0.209 -> 0.159,
MLB 0.241 -> 0.126; fusing the pregame intelligence prior with the realized mid-game state).
That is FORECASTER QUALITY / calibration, badged [model in-corpus, real-corpus], NOT a dollar
edge -- a live book also sees the score, so no DM-vs-close test applies and no $ is claimed.
The real-corpus OOS result is the win; on the committed synthetic fixture the NBA row prints
no-improvement (a synthetic-anchor artifact). See [docs/CALIBRATION_RECORD.md](CALIBRATION_RECORD.md)
and [docs/PREDICTOR_PLATFORM.md](PREDICTOR_PLATFORM.md) section 4.

---

## 4a. HOW each REJECT was reached -- the proof in full

The REJECT table above is not a vibe; every row passed through the SAME leak-free gate, and
the verdict is the conjunction of independent tests. A candidate had to clear ALL of them to
ship -- none did. This is the full chain:

1. **Leak-free walk-forward (expanding window).** Sort states by timestamp; train only on
   strictly-earlier states. Purge same-team games within 48h and embargo the same matchup
   within 3 days of the boundary; assert every feature is vintage-valid (available before the
   prediction time) or FAIL. Code: `scripts/platformkit/eval_gate/walkforward.py`, `src/loop/gate.py`.
2. **Feature selection / slope fit INSIDE the training window.** A candidate that selects on
   full history (`select_inside=False`) is surfaced and the run FAILS -- this is exactly the
   over-fit channel that inflates full-sample lifts.
3. **Ablation vs the FULL model, not in isolation.** The signal column is added to the full
   production matrix; only its MARGINAL holdout delta counts (`ablation_vs_full`). A signal
   the market already prices adds nothing on top of the base features.
4. **Permutation null-shuffle + noise control.** The real delta must beat a shuffled-signal
   null cloud by `z >= 3.0`; the shuffled column is also the noise/p0 control that would
   expose a broken harness (`null_shuffle_control`).
5. **Cluster-robust Diebold-Mariano vs the close.** `d_t = loss_close - loss_model` clustered
   by `game_id` (a naive i.i.d. SE runs ~3x too narrow and manufactures fake significance).
   SHIP requires `BSS>0` AND DM `p<0.05` AND `N>=200`. Code: `scripts/platformkit/eval_gate/dm_test.py`.
6. **>=2 independent corpora + Benjamini-Hochberg FDR.** A single-corpus / single-fold lift
   is an artifact; the lift must replicate (`multifold_guard.replicated`) and survive
   multiple-comparisons correction (`benjamini_hochberg`).

| Self-audit signature | What it means | Where it shows |
|---|---|---|
| **Sign-flip H1<->H2** | A positive full-season NBA schedule lift reverses sign on the held-out calendar half -> over-fit, not edge. Schedule facts are deterministic and known LONG before any line move, so the whole sample is confirmed-before by construction -- a clean test bed. | NBA b2b / 3-in-4 / rest / travel rows |
| **Sign disagreement NL vs AL** | A CLV-capture signal that is +0.108pp on NL but -0.017pp on AL is not replicable across independent corpora -> REJECT. | MLB open->close CLV row |
| **Close BEATS us (DM significant)** | On the MLB totals slice the close is significantly sharper (BSS negative, DM p<0.01) -> the freshness the market sees (park/weather/SP) we cannot. | MLB totals (NL/AL) rows |
| **Fails null-shuffle / BH-FDR** | A soccer/tennis form/h2h candidate cannot beat its own permuted null or survive FDR -> coincidental, not predictive. | soccer + tennis form/h2h rows |

The headline is therefore a CONJUNCTION result: nothing cleared (BSS>0 AND DM p<0.05 AND
N>=200 AND replication AND FDR) on any pregame slice across 6 corpora. An efficient market
proven efficient -- by the instrument that also catches the author's own inflated full-sample
lifts -- is the credential. See [docs/quant-methodology.md](quant-methodology.md) for the full
toolkit table and [docs/PROOFS.md](PROOFS.md) for the per-module index.

---

## 4b. 2026-07 live-run verification + what would falsify this

The section-1 table was re-run live on 2026-07-07 with
`python -m scripts.platformkit.beat_the_close_scoreboard` against the real corpora (NBA 2025-26
odds, MLB 2010-2021, soccer 2019-2026, ATP). Every row reproduced the recorded numbers to 4
decimal places (NBA ML Brier 0.1735/0.1672 n=372, MLB ML 0.2429/0.2390 n=13,992, Soccer O/U-2.5
0.2465/0.2390 n=7,558, ATP 0.2177/0.2028 n=7,374; NBA/MLB totals RMSE unchanged). No drift since
last verification — the table below stays current, not stale.

**What would falsify the efficiency conclusion.** This is a preregistered, honest test, not a
rhetorical shield: if a freshness feed (injury/lineup wire, starting-pitcher confirmation, live
odds-panel scrape) moved our model's Brier or RMSE below the close's on a BEHIND row — measured
leak-free, OOS, on the same real outcomes, with the feed timestamped strictly before the close —
that would be evidence the market has NOT already priced that information, and the "freshness
gap, not a model defect" framing would be wrong for that row. The natural candidates are the
BEHIND rows in section 1 (NBA totals, MLB totals, ATP match-win), because those are the rows
where we already know the direction of the gap; a MATCH row turning into a beat would be the
stronger and more surprising result. No such feed has been built or tested yet — this is the
falsification condition to watch, preregistered here so a future positive result cannot be
read as inevitable in hindsight.

---

## 5. Reproduce (offline)

```
# consolidated REJECT scoreboard (recorded canonical table; <60s)
python -m scripts.platformkit.edge_hunt_scoreboard

# re-run the REAL NBA schedule harness verbatim on the present corpus
python -m scripts.platformkit.edge_hunt_scoreboard --live
python -m scripts.platformkit.edge_hunt_schedule

# the line-movement / CLV REJECT harness (real MLB + soccer corpora)
python -m scripts.platformkit.hunt_line_movement

# the pregame MATCH baselines (fixture path proves the pipeline end-to-end)
python -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof
```

The recorded tables are the live harness output measured on the real local corpora
(NBA 2025-26 odds, MLB 2010-2021, soccer 2019-2026, ATP/WTA). On a fresh clone the private
corpora are absent, so the live re-run prints VALIDATION_PENDING and falls back to the recorded
canonical table -- the standard fixture / real-corpus convention used across this package; it
never fabricates a number.

---

*edge_claimed = False. All numbers here are calibration / sharpness / BSS vs the devigged
close, never a $ edge. Honesty truth-source: [docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).
The retracted measurement artifacts listed there appear nowhere on this page.*

---

**Sibling docs:** [quant-methodology](quant-methodology.md) (validation toolkit + gate logic) -
[backtest-methodology](backtest-methodology.md) - [PROOFS](PROOFS.md) (claim -> proof index) -
[CALIBRATION_RECORD](CALIBRATION_RECORD.md) - [CEILING](CEILING.md) -
[KNOWN_LIMITATIONS](KNOWN_LIMITATIONS.md) - [full doc map](INDEX.md).


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
