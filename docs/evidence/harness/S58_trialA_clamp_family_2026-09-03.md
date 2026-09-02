# S58 in-game trial A -- MLB market-anchor CLAMP family (9 configs, chosen inside the folds) vs e4_gd (2026-09-03)

## VERDICT: NULL (SINGLE-WINDOW) -- valid; the instrument, not the hypothesis, decided 8 of 13 folds

The four preregistered AHEAD conditions on the 47,104-tick / 158-game scored set (13 outer
game-first-date folds 2026-06-30..2026-07-12; every config finite on exactly the same ticks,
asserted):

| condition | bar | measured | pass |
|---|---|---|---|
| (1) paired Brier improvement (incumbent - candidate) | >= 0.004 | **+0.000866166276095** (candidate 0.2059196119366176 vs incumbent e4_gd 0.20678577821271302) | FAIL |
| (2) game-clustered DM 95 pct CI of d (d > 0 = candidate better), lower bound > 0 | > 0 | **[-0.0003638636071911647, 0.0020961961593819476]**, DM stat 1.3909, 158 clusters | FAIL |
| (3) deflated_p(raw p, K at launch) < 0.05 | < 0.05 | raw p 0.16622545084901985, **deflated_p 1.0 at K = 16** | FAIL |
| (4) family bar (10 p-values: 9 configs + the composite, fdr_bh; fdr_by printed) | q = 0.05 | bh_adj_p 0.237465 (by 0.695527) | FAIL |

NULL per the prereg rule: Brier(candidate) < Brier(incumbent) but no condition holds.
SINGLE-WINDOW: one MLB window; min_corpora_eff(1, K=16) = 2 cannot be met (Q5).

The bars line, verbatim (direction-blind):

    verdict=NOT AHEAD blocked_by=global,family raw_p=0.166225 | GLOBAL k=16 deflated_p=1 alpha=0.05 pass=False | FAMILY - q=0.05 n=10 bh_adj_p=0.237465 pass=False | rule=fdr_bh fdr_bh_adj_p=0.237465 pass=False fdr_by_adj_p=0.695527 pass=False | spec=s14-families-v1@62702554f6e5

## What actually happened inside the folds (read before quoting the NULL)

The inner cpcv selection was OPERATIVE on 5 of 13 folds (2026-07-08..07-12: 12,947 ticks /
57 games = 27.5 pct of the scored set) and FELL BACK to the incumbent config on the first
8 folds (34,157 ticks / 101 games), exactly as the prereg's fallback clause says -- so on
72.5 pct of the ticks the candidate IS the incumbent (identical values, verified) and the
whole differential comes from the last five dates. The fallback was NOT data scarcity: every
fold had >= 5,454 train ticks and >= 20 train games. It was an INSTRUMENT DEFECT in this
module's inner predictor: under CPCV's symmetric 1-calendar-day embargo plus the 48 h
same-team purge, some test states in the early folds are left with an EMPTY or < 1,000-tick
purged train set, the predictor raises on that state (`need at least one array to
concatenate` on 6 folds, `inner train infeasible` on 2), and one raise fails the whole
config's inner run for that fold (every config, since the purge is config-independent).
The folds JSON archives every status and error string per (fold, config).

Where the inner selection ran, it was unanimous: every one of the 5 folds picked
e4_w0.5_d0.10 (the tightest clamp, lowest weight cap), and in every fold all three d=0.10
configs beat all three d=0.15 configs beat all three d=0.25 configs on the inner score
(e.g. 2026-07-12: 0.1994 / 0.2038 / 0.2141) -- the market-pull ordering the leaky E4 table
showed, now reproduced OOF inside purged folds.

Descriptive split (no test; a subset, never the verdict): on the 5 active folds the
candidate scored 0.207563 vs the incumbent 0.210715 (market 0.208903 on the same 12,947
ticks); on the 8 fallback folds candidate = incumbent = 0.205297 (market 0.190264).

## Per-config OUTER series (descriptive; REPORTED, never used to choose -- prereg)

| config | outer Brier | vs incumbent | raw DM p |
|---|---|---|---|
| e4_w1.0_d0.15 (incumbent) | 0.206786 | 0 | 1 (itself) |
| e4_w0.5_d0.10 | 0.201627 | +0.005159 | 0.00263 |
| e4_w1.0_d0.10 | 0.201635 | +0.005151 | 0.0027 |
| e4_w2.0_d0.10 | 0.201587 | +0.005198 | 0.00241 |
| e4_w0.5_d0.15 | 0.206790 | -0.000004 | 0.65 |
| e4_w2.0_d0.15 | 0.206808 | -0.000022 | 0.349 |
| e4_w0.5_d0.25 | 0.218269 | -0.011483 | 0.000165 |
| e4_w1.0_d0.25 | 0.218281 | -0.011495 | 0.00016 |
| e4_w2.0_d0.25 | 0.218256 | -0.011470 | 0.000172 |

Reading: the d=0.10 configs are +0.0052 ahead of the incumbent on the outer walk-forward
with raw p ~0.0025, and the d=0.25 configs are -0.0115 behind. Picking d=0.10 on this
table would be an OUTER-score selection -- the exact forking path the prereg forbids -- so
it is not a verdict and is not charged. It is the strongest reason to re-run the family
with a repaired inner runner (below). w_max is irrelevant to four decimals, as in E4.
PBO via cscv_pbo over the 9 outer series: 0.0 (n_obs 47,104, 1,000 splits) -- the IS-best
config is OOS-best in every split; descriptive.

## Seal and charge (Q1 / Q2)

- Prereg docs/evidence/harness/S58_TRIALA_PREREG_2026-09-03.md committed ALONE first
  (9c88ea7e8); SHA-256 f93c07be124201d1b45e3ad1fd6231b8dd03da86a6abb48ef3089041fa3bcbbf
  (git blob 089f37fdffeba838e3e40beb269c672976f22411) pinned as PREREG_SHA256 in the
  module, verified by run_trial before the charge, embedded in the trial JSON, the folds
  JSON and the ledger row.
- Charge: ledger 15 -> 16 rows exactly once (md5 b1b1253821b06bbf501ecb8f19937c9c ->
  acd5199f2a2780bcdbd005eb5bef8491). Row: {"at": "2026-09-02T16:59:09.287068+00:00",
  "predictor": "scripts.platformkit.eval_gate.s58_clamp_family_trial:mlb_clamp_family_v1",
  "sport": "mlb", "start": "2026-06-28", "end": "2026-07-12", "k_cumulative": 16, "family":
  "ingame_mlb_clamp", "k_family": 1, "tier": "T2", "hypothesis_hash": "7fa557fe...",
  "prereg_sha256": "f93c07be..."}. K = 16 read from the row at launch is the only K used;
  global bar raw p < 0.05/16 = 0.003125 as preregistered. ONE charge for all 9 configs.

## Q4 reproduction gate (asserted after the charge, before any verdict metric): PASSED

- Incumbent CONFIGS[0] = (1.0, 0.15) outer series on the 47,104 scored ticks:
  0.20678577821271302 vs target 0.206785778212713 -- |delta| < 1e-9; and `main` asserted
  value-for-value identity with `stacker.e4_gd_series` before the charge.
- Denominators asserted BEFORE the charge: (47,104, 158); 9-way finiteness identity.

## Reported beside the verdict

- ESS of THIS trial's scored differential: ICC 0.276636 / design effect 83.196 / n_eff
  566.18 on 47,104 ticks / 158 games. Market Brier on the scored ticks 0.195387.
- Family `ingame_mlb_clamp` is NOT in the frozen FWER_FAMILIES_SPEC (62702554f); priced
  as 9 configs + the composite (n = 10) and labelled; through tiers it would have been
  NOT_IN_FROZEN_FAMILIES and uncharged.

## Denominator accounting (non-tautology)

Corpus 52,558 ticks / 178 games. Scored 47,104 / 158 = every tick with a finite incumbent
series and market_prob (the 2026-06-28 burn-in first-date games and ticks with no
score_diff are not scored, for every config alike). No post-hoc exclusion; the set was
fixed by the prereg before the charge and equals the S06/S58-1 hedge-paired set.

## Files, tests

- scripts/platformkit/eval_gate/s58_clamp_family_trial.py (new, 256 LOC; reuses
  gap_blend_arm._walk_forward / _fit_weight / _guarded_prob unchanged, cpcv_evaluate,
  _charge_ledger, dual_bar_verdict, cscv_pbo, diebold_mariano, effective_sample_size;
  6-process pool for the inner runs). Per-file test
  tests/platformkit/eval_gate/test_s58_clamp_family_trial.py: 3 passed (seal-before-charge on a
  tmp ledger, K from the row, family n = 10, incumbent-vs-itself p = 1, folds/series
  round-trip; repro gate stops AFTER the charge; inner selection counts train games only).
- Artifacts (gitignored, local): data/cache/eval_gate/s58_trialA_clamp_family_2026-09-03.json,
  s58_trialA_clamp_family_folds_2026-09-03.json (13 folds x 9 configs: status, inner score,
  error string, chosen config), s58_trialA_clamp_family_series_2026-09-03.csv (47,104
  rows: tick_index, game, timestamp, y, candidate, incumbent_e4_gd, market,
  selected_config) -- the verifier recomputes both Briers, the DM CI and
  deflated_p(p, 16) from the CSV alone (Q9).

## NOT VERIFIED

- Any second corpus: SINGLE-WINDOW by construction (window 2 = S55, accruing).
- The verdict on the family with a WORKING inner runner on all 13 folds: not measured here.
  A re-run is a NEW prereg and a NEW charge (never a re-score of this one). The fix is in
  the inner predictor only (skip or fall back on a purged-empty test state instead of
  failing the config); no bar moves.
- The 5-active-fold descriptive split has no interval and is not a verdict.
- The per-config outer table is descriptive; nothing was selected on it.

NEW GAP: s58_clamp_family_trial inner predictor fails a whole config on ONE purged-empty
test state (8/13 folds fell back to the incumbent, 72.5 pct of ticks); repair = per-state
fallback, then re-prereg + re-charge the clamp family (window 2 first if S55 has >= 30 games).
