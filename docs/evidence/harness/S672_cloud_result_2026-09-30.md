# S672 cloud result -- 2026-09-30 (desk-improve one-off, Opus, Ubuntu cloud clone)

Row: S672 (stale-vs-fresh reading guards), PINNED by the one-off override in
QUANT_GRADE_BUILD_SLATE_2026-09-30.md section 3a; row text in section 2. Branch
`cloud/S672-2026-09-30` from trunk 89218a73 (`git ls-remote --heads origin 'cloud/S672*'` was empty
before building). Spec: docs/evidence/harness/S672_spec_2026-09-30.md (body + AMENDMENT 1).
Register row and DESK_STATE.md NOT edited on this branch. Report-only: no Model 2.0 module, seal,
PREREG_M2.json, probe file or seal-pinned file edited (`git diff origin/trunk --name-status` = 9
added files, 0 modified). Calibration language only. Labels are EXPLORATORY; no seal, no scored claim.

## Reviewers (codex is not available in the cloud box)

Every tier below was a separate, independent Opus sub-agent that did not build the code.

| Tier | Verdict |
|---|---|
| Pre-build critique (astra) | REVISE, 15 items -> all folded as AMENDMENT 1 |
| CONTRACT (A, B1-B10, Q1-Q9 + spec) | ACCEPT WITH CORRECTIONS (C-1..C-5, applied in 3b018983) |
| ADVERSARIAL (66 mutants + probes) | ACCEPT WITH CORRECTIONS (4 required + 14 recommended survivors, NaN handling; applied in 00954c0d) |
| RE-VERIFY of the corrections (the single allowed pass) | ACCEPT WITH CORRECTIONS: mutant "dwe without abs" survived -> C23 added in the final commit; builder re-ran that mutant: 1 failed (killed) |

Corrections applied:
- CONTRACT C-1: the NBA loader now counts rows, first_tick_no_anchor, state_unchanged and a `reconciles` flag (fixture 13 = 2 + 4 + 1 + 1 + 5). C-2: games_short_series. C-3: per-tick clip_open. C-4: the exclusion note names "P5 grid chose 16". C-5: games_empty_file.
- ADVERSARIAL: non-finite x/y/z ticks are dropped and counted (n_nonfinite_dropped); every CI reports n_finite_draws; there is no reading when a point is None. C18-C22 kill the survivors: the |corr| guard, the anchor and mu_open clips, HX 300, same-half OUT, the ask >= 1 drop, the declared constants, the logit sign, sign_flip_share, the signed corr, post_share, the hi < 0 verdict and clean() NaN. The C10 refusal cleans up in a finally block.

## What was built (new files only)

- `scripts/platformkit/ingame/s672_reading_guards.py`: computes the naive slope cov(x,y)/var(x) and the instrumented slope cov(z,y)/cov(z,x).
  - CIs are game-clustered (2000 draws, seed 13), recomputed per draw from per-game sufficient statistics centred on the pooled mean.
  - The paired iv - naive difference and the first stage (corr, cov CI, bootstrap SE, F, sign-flip share) are printed.
  - Guard order is INSUFFICIENT (< 30 games), then WEAK_INSTRUMENT (|corr| < 0.10 or F < 10), then a reading: IV_ABOVE / IV_BELOW / NO_DIFFERENCE_RESOLVED.
  - REFERENCE_0.638 INSIDE / OUTSIDE is printed as a descriptive field only. It is never read as reconciling anything: 0.638 is a Kalshi price-level slope, and ours is a slope of a Polymarket price change.
- `s672_reading_guards_io.py`: builds the P5 direction-check ticks, reproducing the probe's x, y, selection and noclip rules.
  - Instrument z uses the opening-tick anchor. Instrument z0 is price-free (mu = 0).
  - Shared-noise drops are counted, and an open + 60 s sensitivity cut is printed.
- `s672_reading_bands.py` + `s672_reading_guards_io_mlb.py`: split P1 by p_benefit band.
  - p_benefit is the pre-event mid of the side the event favours. Bands are [0,.25) [.25,.5) [.5,.75) [.75,1].
  - The grid is ALL/FRESH15 x SCORE/OUT/POOLED. Each cell prints n events and n games, reconciles, and gives a verdict or INSUFFICIENT under 30 games.
  - The CI is bit-identical to k_common.cluster_boot. The adapter mirrors probe_p1 measure(); no probe is imported.
- `s672_reading_guards_cli.py`: writes the receipt JSON (inputs with path, bytes and sha256; module sha256s; constants) plus the .ticks.jsonl / .events.jsonl series (Q9). It refuses an --out under data/ or vault/ (exit 2).

## Tests (one file per process, cloud clone Python 3.11.15, final branch head)

    python3 -m pytest tests/platformkit/ingame/test_s672_reading_guards.py -q     -> 16 passed
    python3 -m pytest tests/platformkit/ingame/test_s672_reading_guards_io.py -q  -> 5 passed
    python3 -m pytest tests/platformkit/test_loc_rail_scope.py -q                 -> 1 passed

C1-C23 are CONSTRUCT cases. In C1 (true slope 0.638, x-noise variance = signal variance; recomputed independently by both tiers):
- naive 0.3067 [0.2905, 0.3239] contains 0.319 and excludes 0.638;
- iv 0.6449 [0.5906, 0.7097] contains 0.638;
- iv - naive [0.2869, 0.3993], reading IV_ABOVE_NAIVE_RESOLVED.

## PREMISE (from tracked artifacts, trunk 89218a73)

- P5 printed only a naive slope: 0.3617 (corr 0.6426, n 140,457 state-changed ticks, 1,593 games), and 0.3500 on noclip (n 127,856) (probe_p5_stdout.txt:96, :124).
- P1 has no pre-event probability split (1,107 events / 40 games pooled).
- Our 0.6426 is a correlation, not a slope comparable to the 0.638 figure.

## NOT VERIFIED (needs the laptop archive; the clone has no data/ corpus)

- The real re-cut: `--nba-dir data/cache/ingame_grade_joined/nba_checkpoints_r1 --k-pickle <probe k_compact.pkl> --mode REAL`, with --out outside data/.
- Reproduction of P5's 0.3617 / 0.3500 in the p5_selection / p5_noclip cells, and of P1's 1,107 events / 40 games in ALL POOLED.
- The instrument's exclusion restriction. z shares the WP(sigma 13) state term with x, so IV removes noise in the anchor mu only. It does not remove WP mis-specification or a multi-tick market reaction.
- Windows / Python 3.10 re-run of the two test files.

NEW GAP (from the tiers, not rowed here):
- C5 "identical" holds only to about 1e-16 (summation order).
- No construct has some non-finite bootstrap draws (n_finite_draws < 2000).
- The no-reading-on-None-point guard is likely an equivalent mutant.
- anchor_before_open is dead code by construction.
- A band whose post_120 values are all non-finite would raise; the adapter cannot produce one.

PORTABLE: yes (code and construct tests). The real run is WINDOWS (laptop archive).
