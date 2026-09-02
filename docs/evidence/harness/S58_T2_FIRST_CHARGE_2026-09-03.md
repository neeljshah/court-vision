# S58 T2 #1 -- the factory's FIRST end-to-end charged T2: soccer_gate rank 1 vs the devigged close (2026-09-03)

## VERDICT: MATCH (SINGLE-WINDOW) -- indistinguishable from the devigged close; the pipeline proof holds

Candidate (chosen by the frozen rule BEFORE any verdict-side row was opened -- prereg
`docs/evidence/harness/S58_T2_FIRST_PREREG_2026-09-03.md`, commit 126dbdb48, blob 6378e7619,
SHA-256 7125552f4c772e15c05057a5beaf460b1dc152496007cd20ea14c521f893cc30): the soccer family
whose incumbent is the devigged close with the highest screened n (soccer_gate, 82 screened in
2026-W36; soccer_xg_proxy 75), rank 1 by the frozen `rank_by t1_brier_improvement` (tiers spec
pin b2b2ea5a0): `diff_shots_for_asof`, transform `ew`, halflife 10, hash
d65df2a95aeb0f49265445cbaf8be51284f37454538f55fc338412e16ec71936.

Factory verdict (`tiers.run_tier("T2")`, dual bar, S59): **MATCH**, dual_verdict `NOT AHEAD`
blocked by global AND family. The prereg's four AHEAD conditions on the pooled 8,666
verdict-side events (E1, I1, D1; 2019-08-02..2026-05-24):

| condition | bar | measured | pass |
|---|---|---|---|
| (1) paired Brier improvement (close - model) | >= 0.004 | **-0.000057** (model 0.239843 vs close 0.239785) | FAIL |
| (2) DM 95 pct CI of d (d > 0 = model better), cluster = div (G = 3) | lower > 0 | **[-0.000831, +0.000717]**, DM stat 0.3186 | FAIL (contains 0) |
| (3) deflated_p(raw p, K at launch) < 0.05 | < 0.05 | raw p 0.780243, **deflated_p 1.0 at K = 18** | FAIL |
| (4) family bar (soccer_gate, fdr_bh at q 0.05; fdr_by printed) | q = 0.05 | bh_adj_p 0.780243, **family n used = 1** | FAIL |

PBO (cscv, s_blocks 16, [model, close]) 0.581. n_eff by the div ICC 2,444.2 of 8,666.
Replication (Q5 / S08): n_corpora = 0 of 3 verdict-side units meet (improvement >= 0.004 AND
per-unit CI lower > 0); `replication_fields("MATCH", 0, 18)` -> verdict_replicated MATCH,
**min_corpora_eff(K=18) = 2**. The six divisions are one gate corpus: SINGLE-WINDOW.

Per unit (cluster = home team inside a unit, because div is constant there):

| unit | n | Brier model | Brier close | improvement | DM CI 95 | raw p | n_eff |
|---|---|---|---|---|---|---|---|
| D1 | 2,142 | 0.226228 | 0.226654 | +0.000425 | [-0.000030, +0.000881] | 0.0660 | 2,142.0 |
| E1 | 3,864 | 0.245152 | 0.244938 | -0.000214 | [-0.000471, +0.000043] | 0.0999 | 2,571.1 |
| I1 | 2,660 | 0.243094 | 0.242875 | -0.000219 | [-0.000589, +0.000152] | 0.2373 | 2,660.0 |

Every unit's CI contains 0; every improvement is inside +-0.0005. The screen's +0.000968 on
E0/SP1/F1 and the verdict side's -0.000057 on E1/I1/D1 are the same picture: the devigged
close already carries what the as-of shot differential knows. An honest MATCH -- the market
is efficient on this family; the success here is that the factory ran end to end.

The bars line, verbatim (direction-blind):

    verdict=NOT AHEAD blocked_by=global,family raw_p=0.780243 | GLOBAL k=18 deflated_p=1 alpha=0.05 pass=False | FAMILY soccer_gate q=0.05 n=1 bh_adj_p=0.780243 pass=False | rule=fdr_bh fdr_bh_adj_p=0.780243 pass=False fdr_by_adj_p=0.780243 pass=False | spec=s14-families-v1@62702554f6e5

## Seal, partition, charge (Q1 / Q2 / SF-1)

- Prereg committed ALONE first (126dbdb48); `run_trial` verifies the SHA-256 (newlines
  normalised to LF, autocrlf-proof) before anything else; the seal is embedded in the trial
  JSON and the per-event CSV header.
- Partition `tiers.partition_corpus(states, seed=20260903)`, basis corpus_unit: SCREEN
  E0/SP1/F1 = 7,656 (sha 5c8d63970b08ce97...6323873, byte-equal to the S58c screen artifact's
  `screen_partition_sha256`), VERDICT E1/I1/D1 = 8,666 (sha 3ea2e582304ea727...c4e72b),
  intersection 0; asserted with the STEP 0 counts (16,322 / 7,656 / 8,666) BEFORE the charge.
  T2 read the VERDICT side only (all 8,666 rows; a leak would have raised ScreenPartitionLeak).
- Charge through the factory path only: `run_tier` -> `_run_charged` -> `charge_tier` ->
  `_charge_ledger`; ledger 17 -> 18 rows exactly once (md5 303a7d82cf525d338e258ef565c71d02 ->
  a4ae7c13995672e478d59770591b83ba). Row 18 verbatim: {"at": "2026-09-02T17:27:21.417992+00:00",
  "end": "2026-05-24", "family": "soccer_gate", "hypothesis_hash": "d65df2a9...c71936",
  "k_cumulative": 18, "k_family": 1, "predictor": "foundry:d65df2a95aeb0f49", "prereg_sha256":
  "b2b2ea5a0fe2bd4adaf327aa38e546b49ca0eec3", "sport": "soccer", "start": "2019-08-02",
  "tier": "T2"}. K = 18 read off the appended row; every metric came after it (the bars JSON
  is stamped 11 min after the charge).
- The ledger row's `prereg_sha256` is the TIERS SPEC pin (b2b2ea5a0), by construction of
  `charge_tier`; the per-trial prereg seal (7125552f...) lives in the trial JSON, the CSV
  header and here. Stated as a gap below.
- Family n: `results_db.family_p_values("soccer_gate")` on the S58c DB
  `data/cache/eval_gate/s58_screens/soccer.sqlite` returned 0 prior raw p-values (S74: screens
  archive `screen_p`, never `raw_p`), so the family bar was priced over n = 1 (this trial's own
  p). screened_n = 82 printed. The T2 row is now indexed in that DB (additive; verdict MATCH).

## Reproduction (A2) and the archived differential (Q9)

A second, independent `cpcv_evaluate` run (28 paths, 8 groups x 2 test groups, embargo 1 day,
purge same-team 48 h / same-matchup 3 d) reproduced the charged TierResult's brier_model,
brier_close and DM stat to < 1e-9 (asserted in `run_trial`; the trial exited 0). The per-event
paired-loss series -- 8,666 rows, 8,666 unique event_ids: event_id, ts, div, home, away,
p_model, p_close, y, loss_model, loss_close, d -- is
`data/cache/eval_gate/s58_t2_first_soccer_gate_2026-09-03_perevent.csv`; its mean d
(-0.0000573) and mean loss_model (0.2398427) recompute the headline from the CSV alone. All 28
CPCV paths' fit coefficients (path 0: n_fit 6,438, coef [0.0139, 1.0898, -0.0022] on
[1, logit(close), z(feature)] -- the feature's slope is 0.002 of a standard deviation) are in
`..._2026-09-03.json` (`archive.fits`); the dual-bar record is `..._bars.json`.

Model: the S58c `RealScreenPredictor` unchanged (logistic, ridge 1e-3, MIN_FIT 30, close as
fallback), bound over the VERDICT side by `ScreenBinder` (ew shift(1) within div; feature
non-null 8,662 / 8,666), wrapped so a FRESH predictor is built per CPCV path (see gap 1).
Module `scripts/platformkit/eval_gate/s58_t2_first_trial.py` (182 LOC), test
`tests/platformkit/eval_gate/test_s58_t2_first_trial.py` 3 passed. tiers.py at run time was
the working-tree blob c075b2a41 (HEAD 9f8534157 + the staged S68 `portable` env flag on the T0
branch only; the T2 path is byte-identical). Wall: 12:27 charge -> 12:46 done (two CPCV runs).

## NEW GAPS (filed, not fixed; nothing here changes the verdict)

1. `RealScreenPredictor` caches its fit by `len(train) // 50`; safe under `walk_forward` but
   under `cpcv_evaluate` a later path can share a bucket with an earlier path whose train set
   held this path's test rows. The runner's `run_charged` never hits it today (it passes the
   stateless `_p_base_predict`), so no charged verdict is affected; this trial reset per path.
   Fix belongs in screen_predictor.py (key the cache on the train set, not its length).
2. `charge_tier` writes the tiers-spec pin as the ledger row's `prereg_sha256`; a per-trial
   prereg seal cannot reach the ledger through the factory path (only the trial JSON / memo).
3. SF-10 clusters soccer by `div`; with a corpus_unit partition the verdict side has G = 3
   clusters, so the pooled DM variance rests on three cluster sums (per-unit team clustering
   is reported beside it). A declared secondary key for the 3-unit case would be the fix.
4. `_run_charged` does not archive the differential (only `_run_screen` does); Q9 was met here
   by an external reproduction run. A charged TierResult should carry `archive` too.

## NOT VERIFIED

- No independent verifier has re-run `run_trial` (it would charge K again); the reproduction
  is the module's own second CPCV pass plus the CSV recompute above.
- The screen-side +0.000968 is quoted from the S58c artifact, not recomputed here.
- ICC / n_eff for the 3-cluster pooled case is a lower bound (SF-10 note); not re-derived.

Calibration language only. MATCH is a success: the factory charged once, priced both bars at
the launch K, read a hash-disjoint verdict partition and archived a reproducible differential.
