# S06 stacker charged trial -- result (2026-09-03)

## VERDICT: BEHIND (valid, expected outcome; the module lands either way)

The three preregistered AHEAD conditions, measured on the outer walk-forward
(47,104 paired ticks / 158 games; incumbent e4_blend paired all-ticks Brier
0.2070329295167757):

1. Paired Brier improvement >= 0.004: **FAILED** -- improvement_vs_incumbent =
   -0.0899096845066431 (stacker Brier 0.2969426140234188). Vs the stricter
   leak-free pairing series (e4_gd 0.20678577821271302): -0.0901568358107058.
2. Game-clustered DM 95 pct CI excludes 0: excludes 0, but in the WRONG
   direction -- CI [-0.13192744799390593, -0.04838622362750562], DM stat
   -4.2304 (d > 0 = stacker better; the stacker is significantly worse),
   n_clusters = 158.
3. deflated_p < 0.05 at launch K: deflated_p = 0.000553219827291201 at K = 14
   (raw p 3.95157019493715e-05) -- significant, again for the stacker being
   WORSE, not better.

## Seal and charge (Q1 / Q2)

- Prereg docs/evidence/harness/S06_STACKER_PREREG_2026-09-03.md committed
  FIRST (d81c374f0); SHA-256
  5abddabea08a753050c914ca2cc102d6ee9c406eba7404c45864176d15f8c90f verified by
  run_stacker_trial before the charge and embedded in the trial JSON.
- Charge: the ledger went 13 -> 14 rows exactly once. Row appended:
  {"at": "2026-09-02T05:42:37.630316+00:00", "predictor":
  "scripts.platformkit.eval_gate.stacker:mlb_stack_v1", "sport": "mlb",
  "start": "2026-06-28", "end": "2026-07-12", "k_cumulative": 14}.
  K = 14 (read from the row at launch) is the only K used; at K=14 the raw-p
  bar is 0.05/14 = 0.00357 as preregistered.

## Step-0 arms and the 1e-9 reproduction gate (Q4; all PASSED inside the trial)

Arms per the pre-flight (S06_OOF_PREFLIGHT_2026-09-03.md, GO WITH CORRECTIONS):
raw_model and e1_offset AS-IS; e4_blend and e2_regime as GAME-FIRST-DATE
recomputed variants with per-fold train/test game-disjoint asserts; the
shipped tick-date series DROPPED. Reproduction asserts (|delta| < 1e-9):
raw_model 0.236682901513263 (47,104), e4_gd 0.206785778212713 (47,104),
e1_offset 0.281762477954033 (6,579 intersection), e2_gd 0.254350980569169
(6,579). A pre-charge counts-only sanity check reproduced every denominator
(scored 47,104 / 158; both intersections exactly 6,579) before the charge.

## Reported beside the verdict (prereg-required)

| series | Brier (scored set) | n ticks |
|---|---|---|
| stacker (outer walk-forward) | 0.2969426140234188 | 47,104 |
| e4_blend leak-free (pairing series) | 0.20678577821271302 | 47,104 |
| incumbent (paired all-ticks, prereg before) | 0.2070329295167757 | 47,104 |
| UNIFORM-weight arm (masked mean of arms) | 0.22842246795771406 | 47,104 |
| guard-only | 0.21101808614356019 | 47,104 |
| raw_model | 0.23668290151326293 | 47,104 |
| e1_offset | 0.28061452562013994 | 47,104 |
| e2_regime leak-free | 0.25435098056916927 | 6,579 (masked ~87 pct) |

- PBO via cscv_pbo: 0.0 (n_obs 6,579 all-configs-finite intersection, 1,000
  splits, configs = 4 arms + uniform + stacker). The IS-best config (e4_gd)
  is also OOS-best in every split -- consistent with one dominant arm, no
  selection instability.
- GUARD NAMED (advantage over guard-only is under the bar): the guard is
  gap_blend_arm's arm_a_prob series -- the market-anchored guard component of
  e4 with zero signal weight, recomputed game-first-date -- Brier 0.211018 on
  the full 47,104. The stacker trails even the guard by 0.0859.
- ESS, the SCORED predictor's own (stacker-vs-e4_gd loss differential,
  labelled): ICC 0.5311114612559932 / design effect 158.80733329192313 /
  n_eff 296.61098781510543 on 47,104 ticks / 158 games. (These are NOT e4's
  0.207/62.4/754.5 nor Hedge's 0.291/87.4/539.1.)
- SINGLE-WINDOW: yes -- one MLB window is the only corpus;
  min_corpora_eff(n_corpora=1, K=14) = 2 cannot be met. The verdict is
  labelled SINGLE-WINDOW here and in the register row (Q5).

## Denominator accounting (non-tautology)

Corpus 52,558 ticks / 178 games; scored 47,104 / 158. Dropped 5,454 ticks =
5,454 burn-in ticks of the 20 first-date (2026-06-28) games + 0 missing
market_prob + 0 other pairing absence. No post-hoc exclusion: the scored set
is the e4-promotion paired denominator fixed in the prereg, asserted
(47,104 / 158) before the charge.

## Protocol as run

Outer: 13 expanding game-first-date folds (2026-06-30..2026-07-12), per-fold
game-disjoint assert; 1 fold used the fallback arm (2026-06-30 -- every inner
CPCV path's purged train held under MIN_TRAIN=1000 ticks); 12 folds used
inner-CPCV-averaged weights (cpcv_evaluate, n_groups=8, n_test_groups=2,
embargo_days=1; 28 paths per fold; fold fits keyed by frozenset of train
game_ids, never id(train) -- RT-2). Regime key: inning bucket; absent arms
masked by availability pattern, never 0.5-imputed. Per-file test (synthetic,
tmp ledger only) ran BEFORE the real trial:
`python -m pytest scripts/platformkit/eval_gate/test_stacker.py -q` = 4 passed
in 2.84s (dominant arm not beaten; all-absent arm changes nothing; regime
weights differ across planted regimes; seal-before-charge on a tmp ledger,
failed seal leaves the tmp ledger unchanged).

## Reading (calibration language only)

The nested-CV stacker as specified does not rescue the Hedge gap: inner CPCV
Briers looked healthy (0.177-0.259) while the outer series collapsed to
0.2969, i.e. the per-regime logit-ridge weights fit on within-game-duplicated
game outcomes sharpen overconfidently and transfer badly across dates. The
measured limit stands: no combination beat the single dominant arm; e4_blend
remains the incumbent. BEHIND is recorded as a success of the gate, not a
failure of the program.

Artifacts: data/cache/eval_gate/s06_stacker_trial_2026-09-03.json (ledger row
+ prereg_sha256 embedded; gitignored, local) and per-tick series
data/cache/eval_gate/s06_stacker_series_2026-09-03.csv (47,104 rows: game,
timestamp, regime, y, stacker, pair_leakfree, uniform, raw_model) -- the
verifier recomputes paired Brier, DM and deflated_p from that series and
re-reads k_cumulative from the ledger row in the JSON.

## NOT VERIFIED

- Any second corpus (soccer_intl or another MLB window): the verdict is
  SINGLE-WINDOW by construction.
- The e1 cross-game concurrency share at the UTC boundary (pre-flight caveat;
  other-game outcomes only, no self-leak).
- Whether a different meta method (shrunken/convex weights instead of
  logit-ridge) would close the inner-outer gap -- out of scope; the prereg
  fixed logit_ridge and the bar never moves (Q3).
- The wall-clock split of the ~13-minute run (arm recomputation dominates; not
  instrumented per stage).
