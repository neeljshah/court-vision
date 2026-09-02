# S58 T2 #1 prereg (sealed 2026-09-03) -- the factory's FIRST end-to-end charged T2: soccer_gate rank 1 vs the devigged close

Sealed BEFORE any verdict-side metric: this file is committed ALONE, its SHA-256 is pinned as
`PREREG_SHA256` in `scripts/platformkit/eval_gate/s58_t2_first_trial.py`, verified by
`run_trial` before the charge, and embedded in the trial JSON, the per-event CSV header and
the memo (Q1). The charge is made by THE FACTORY PATH and nothing else: `tiers.run_tier(h,
"T2", ...)` -> `_run_charged` -> `charge_tier` -> `_charge_ledger(data/cache/eval_gate/
backtest_fwer.jsonl, "foundry:d65df2a95aeb0f49", "soccer", "2019-08-02", "2026-05-24",
family="soccer_gate", hypothesis_hash=<hash>, tier="T2", prereg_sha256=<tiers spec pin
b2b2ea5a0fe2bd4adaf327aa38e546b49ca0eec3>)`, appended BEFORE any metric, K read off the
appended row (Q2). The ledger holds 17 rows at sealing (md5 303a7d82cf525d338e258ef565c71d02;
row 17 is trial B's charge). This charge appends row 18, so launch K = 18 and the global bar
is deflated_p(raw_p, 18) = min(1, 18 * raw_p) < 0.05, i.e. raw DM p < 0.002778. ONE charge;
ONE hypothesis; ONE model.

## Why this candidate (stated before opening any verdict-side row)

The frozen rule picked it, not its screen delta. The task's family order: the soccer family
whose incumbent is the DEVIGGED CLOSE with the highest screened n in the S58 promotion list
(9235e9cb1 / 92154a60a) -- soccer_gate, screened 82 in 2026-W36 (soccer_xg_proxy: 75). Within
the family the frozen rule (FACTORY_TIERS_SPEC v1, pin b2b2ea5a0: rank_by
t1_brier_improvement, top_n 20) ranks first:

    feature diff_shots_for_asof, transform ew, params halflife 10, horizon pregame, market total
    semantic hash d65df2a95aeb0f49265445cbaf8be51284f37454538f55fc338412e16ec71936

Its SCREEN delta was +0.000968 (model 0.242864 vs close 0.241896 on the 800-row screen window;
screen DM p 0.7175; a NON-FINDING, behind the close). Expected outcome: MATCH or BEHIND. This
trial is a pipeline proof: what is being tested is that a promoted hypothesis can be charged
through tiers with results_db, the dual bar, a disjoint verdict partition and an archived
differential -- an honest MATCH / BEHIND is the success.

## Corpus (STEP 0, measured 2026-09-03 before sealing; NO Brier computed on the verdict side)

`data/cache/combo/gate_corpus_soccer.parquet`: 25,834 rows, six corpus_units (E1 6,072 /
E0 4,180 / SP1 4,180 / I1 4,180 / F1 3,856 / D1 3,366). `screen_predictor.corpus_states
("soccer")` -> `close_join.gate_corpus_states`: **16,322 states scored with the devigged close**
(E1 3,864 / E0 2,660 / SP1 2,660 / I1 2,660 / F1 2,336 / D1 2,142), 2019-08-02..2026-05-24,
state_ts SYNTHETIC 12:00 (S34). Feature non-null 99.51 pct of the 16,322.

Partition (SF-1) = `tiers.partition_corpus(states, seed=20260903)`, basis corpus_unit:

    SCREEN  = E0, SP1, F1 = 7,656 event_ids, sha256 5c8d63970b08ce971b4c92a476d978596e68e082d888ffc7491ad712e6323873
    VERDICT = E1, I1, D1  = 8,666 event_ids, sha256 3ea2e582304ea727f0f922f5b43bb8c799fd55299f28ec2b9e908204abc4e72b
    intersection = 0 (partition_corpus raises otherwise; run_trial asserts it again)

The SCREEN sha is byte-equal to `screen_partition_sha256` in the S58c screen artifact
`data/cache/eval_gate/s58_screens/trials_soccer/d65df2a9..._T1_all.json` (the rows this
hypothesis was CHOSEN on), so the verdict side is disjoint from the selection set by hash.
`run_trial` asserts (16,322; 7,656; 8,666; both shas) BEFORE the charge; any drift stops the
trial uncharged. T2 reads the VERDICT side only (all 8,666 rows; `ScreenPartitionLeak`
otherwise).

## Model (K = 1 charge; the S58c screen predictor, unchanged)

`screen_predictor.ScreenBinder("soccer", verdict_states, table, rows=8666, "devig_close")`
builds the feature over the VERDICT side only: ew(halflife 10) of `diff_shots_for_asof`
over PRIOR rows of the same div (`shift(1)`). `RealScreenPredictor`: logistic on
[1, logit(close), z(feature)], ridge 1e-3, >= 30 fit rows else the close (missing != bad).
Evaluation is the factory's: `cpcv_evaluate` (8 groups, 2 test groups, embargo 1 day, purge
same-team 48 h / same-matchup 3 d), predictions pooled per event, `cscv_pbo(s_blocks=16)`,
`diebold_mariano` clustered by the SF-10 key `div`. STATED DEFECT, handled here, not in the
module: `RealScreenPredictor` caches its fit by `len(train) // 50`, which is safe under
`walk_forward` (train only grows) but NOT under CPCV, where consecutive paths can share a
bucket and a fit from a path whose train set contained this path's test rows would be reused.
`run_trial` wraps it so a FRESH predictor is built whenever the train set changes (one fit per
CPCV path). This is filed as a NEW GAP, not fixed in screen_predictor.py.

## Incumbent

`devig_close_prob` -- the devigged close from `close_join` (S02), LABELLED `devig_close`.

## Verdict rule (frozen; no bar moves, Q3)

The verdict of record is the factory's `TierResult.verdict` from `tiers._run_charged` (MATCH /
BEHIND / AHEAD, AHEAD needs BOTH bars per S59), printed verbatim -- AND an AHEAD additionally
requires the four conditions below on the pooled 8,666 (the stricter of the two is the
verdict of record). Let d = loss(close) - loss(model) per event (d > 0 = model better):
  (1) paired Brier improvement = Brier(close) - Brier(model) >= 0.004;
  (2) Diebold-Mariano 95 pct CI of d, cluster = div (the SF-10 key; G = 3 on the verdict
      side, stated), lower bound > 0;
  (3) deflated_p(raw DM p, K read at launch) < 0.05;
  (4) the family bar via `charged_bars` with `results_db = data/cache/eval_gate/s58_screens/
      soccer.sqlite`: prior recorded raw_p for soccer_gate = 0 (S74: screens archive
      `screen_p` only, never `raw_p`), so the family n actually used is 1 (this trial's own
      p) -- stated, not fixed.
Replication (Q5 / S08): n_corpora = the number of verdict-side units (E1, I1, D1) on which
BOTH per-unit improvement >= 0.004 AND per-unit DM CI lower bound > 0 (per-unit cluster =
home team, because div is constant inside a unit); `replication_fields(verdict, n_corpora,
K=18)` gives `verdict_replicated` and `min_corpora_eff`. The six divisions are one gate
corpus, so the trial is labelled SINGLE-WINDOW in the memo and the register row unless
n_corpora >= min_corpora_eff. Else BEHIND iff Brier(model) > Brier(close) pooled; else MATCH.
screened_n = 82 (soccer_gate, 2026-W36, the promotion list's `screened` column).

## Reported beside the verdict (always)

Per-unit table (n, Brier model / close, improvement, DM CI, raw p, n_eff); pooled PBO; n_eff
by the div ICC; both bars' `bars_line` verbatim; the ledger row verbatim with md5 before /
after; the per-event CSV (Q9: event_id, ts, div, home, away, p_model, p_close, y, loss_model,
loss_close, d) plus every CPCV path's fit coefficients in the trial JSON; a REPRODUCTION:
the pooled series is recomputed from a second, independent `cpcv_evaluate` run and asserted
equal to the charged TierResult's brier_model / brier_close / dm to 1e-9.

## Leak risks named

- Selection: the screen chose this hypothesis on E0/SP1/F1; the verdict side is E1/I1/D1,
  disjoint by event_id and by division (transforms never cross divisions).
- Feature vintage: `diff_shots_for_asof` is as-of by construction (corpus_cache built it so);
  the ew uses shift(1) within div. `assert_vintage` runs on every CPCV test row.
- Predictor state across CPCV paths: the per-path reset above.
- Same-day cross-section: none (ew, not rank / z_vs_league).

Artifacts: data/cache/eval_gate/s58_t2_first_soccer_gate_2026-09-03.json (+ _perevent.csv,
+ _bars.json written by charged_bars), memo docs/evidence/harness/S58_T2_first_2026-09-03.md.
Must not move: BAR 0.004, ALPHA 0.05, q 0.05, top_n 20, partition_seed 20260903, refit 50,
MIN_FIT_ROWS 30, ridge 1e-3, cpcv (8, 2, embargo 1), s_blocks 16, deflated_p,
min_corpora_eff, replication_verdict, diebold_mariano, every threshold under
scripts/platformkit/eval_gate/, the ledger except the one appended row, data/registry/**
(never written), the S58c screens DB except the one additive T2 index row. Calibration
language only.
