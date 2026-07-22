# I independently built the eval loop that LLM/ML eval platforms sell

> **Framing.** Braintrust, Galileo, and Arize productize a small set of primitives:
> scorers, offline golden-set regression gates, online production monitoring,
> experiment/regression diffing, eval-set hygiene / leakage detection, and drift
> observability. Before I knew those products by name, I built the same loop for a
> forecasting system -- because the discipline is the same whether the thing under
> test is an LLM output or a probability. This page maps my existing machinery to
> those industry primitives, one row per primitive, each citing the real file or
> directory that implements it.
>
> This is an engineering-parity claim, **not** a performance or edge claim. Nothing
> here asserts a dollar, ROI, or betting edge. The one measured quality win in the
> system is in-game win-probability **calibration** (NBA Brier 0.209 -> 0.159, MLB
> 0.241 -> 0.126, `edge_claimed=False`; see [INGAME_PROOF.md](INGAME_PROOF.md)) -- a
> calibration result a live book could also see, never a claim of beating anyone.
> Truth-source for any number: [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).

---

## The mapping

| Eval-platform primitive (what Braintrust / Galileo / Arize sell) | What I built | Where it lives (real artifact) |
|---|---|---|
| **Scorers / metrics** -- pluggable functions that score each output against ground truth (Brier, log-loss, accuracy, calibration error) | Per-sport calibration scoreboards and a reliability-diagram / Murphy Brier decomposition (reliability, resolution, uncertainty + ECE/MCE) computed read-only over settled outcomes | `scripts/platformkit/calibration_diagram.py` (reliability table + Murphy decomposition + ECE/MCE), `scripts/platformkit/ingame_scoreboard.py`, `src/prediction/devig.py` (Shin/4-method de-vig scorer) |
| **Offline eval / golden-dataset regression gate** -- run a fixed labeled set every change, fail the build if quality regresses | Walk-forward backtest harness with an assertion-level per-fold leak guard, plus a CI gate that exits non-zero on overfit, plus a multi-corpus calibration acceptance gate that only ships a calibration if it beats raw on >=2 independent OOS corpora | `src/prediction/walk_forward_backtester.py` (asserts `max_train_date < min_test_date` every fold), `scripts/run_walk_forward.py --gate` (exit 1 on overfit), `scripts/validate_calibration_multicorpus.py` |
| **Online eval / production monitoring** -- score live production traffic against outcomes as they resolve | Append-only shadow-logging of every evaluated candidate (passed *and* blocked), overnight settlement against final box scores, and a job that forward-settles the discovery loop's own not-yet-confirmed verdicts against real outcomes | `src/prediction/shadow_logger.py`, `src/prediction/settlement.py`, `scripts/platformkit/autoloop/shadow_settle_job.py` (`data/cache/intel_claims/shadow/shadow_settle_ledger.jsonl`) |
| **Experiment gating / regression diff** -- compare candidate vs baseline, block on a statistically meaningful regression | The ship gate built to refute, not confirm: expanding walk-forward (all folds must improve), null-shuffle permutation control (z >= 3), ablation-vs-full-model marginal-lift, Benjamini-Hochberg FDR; plus an append-only reject ledger of every candidate that failed | `src/loop/gate.py`, `src/loop/discovery.py` (LLM-free proposer feeding the gate), `scripts/platformkit/reject_ledger.py` (513 recorded REJECT/DEFER verdicts), `scripts/platformkit/edge_hunt_scoreboard.py`, `scripts/platformkit/beat_the_close_scoreboard.py` |
| **Eval-set hygiene / data-leakage detection** -- guarantee the eval set never contaminates training | Truncation-invariance property test (a streaming feature at time T must be byte-identical whether or not future events exist) + strict walk-forward with no K-fold on time-ordered data; this is the harness that caught a real Q4 lookahead leak in my own end-of-Q3 model | `tests/test_ingame_leak_free.py` (truncation-invariance, passes), `src/prediction/walk_forward_backtester.py` (temporal split assertion) |
| **Observability / drift monitoring** -- watch feed liveness, output freshness, and metric drift; alert before silent degradation | Feed-health + output-freshness + calibration-drift sentinels, a heartbeat-coverage watcher, and a one-command liveness harness that composes them into a single RED/GREEN readout (and was fixed so a down section can no longer roll up green) | `scripts/platformkit/odds_provider/feed_health.py`, `scripts/platformkit/ops_sentinel/output_freshness.py`, `scripts/platformkit/ops_sentinel/heartbeat_coverage.py`, `scripts/platformkit/calib_drift_monitor.py`, `scripts/platformkit/proof_harness/system_proof.py` |

---

## Why this is the same loop, not a stretch

An eval platform exists to answer one question repeatedly: *did this change make the
model's outputs measurably better or worse, on held-out data, without leakage, and is
production still behaving?* Every column above is one stage of that answer:

- **score it** (scorers) -> **regression-gate it offline** (golden set) -> **diff
  candidate vs baseline with a significance test** (experiment gating) -> **guard the
  eval set from leakage** (hygiene) -> **watch it in production** (observability), with
  a **standing online eval** closing the loop between "looks promising" and "held up".

The credential is not that I reinvented these products. It is that I built the same
control loop from first principles for a domain where getting it wrong is silent, and
then pointed it at my own work: the multi-corpus gate and the leakage property test are
the instruments that rejected every candidate edge I proposed and caught my own leaks --
the negative-result count (513 rejects) dwarfs the positive one, which is exactly the
shape a working eval loop produces.

---

## Honest limits

- **Parity, not equivalence.** These platforms add multi-tenant UIs, dataset
  versioning, human-labeling workflows, and LLM-as-judge tooling I did not build. The
  claim is that the *core eval loop* -- scorers, offline gate, online monitoring,
  regression diffing, leakage detection, drift observability -- exists here as working
  code, not that this is a drop-in replacement for a commercial platform.
- **No performance or edge claim.** This page maps machinery, not results. The only
  measured quality win is in-game calibration (Brier deltas above, `edge_claimed=False`);
  pregame the system MATCHES the efficient closing line within noise and beats nothing
  (see [MARKET_EFFICIENCY_PROOF.md](MARKET_EFFICIENCY_PROOF.md)). No dollar/ROI/edge
  figure appears anywhere on this page, and none of the retracted measurement artifacts
  (listed only in [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)) are quoted here.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
