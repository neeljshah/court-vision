# S263 S88 Preburn Companion: FALSIFIED

## Verdict

FALSIFIED. No new companion CSV was created because the premise that all 13,184 pre-burn ticks lack an evidence artifact is false. The existing additive source is `C:/Users/neelj/nba-track-a15/docs/evidence/harness/S254_mlb_phase_recal_fwer_sealed_2026-09-04_paired_loss.csv`.

## Sealed preregistration

The preregistration is `docs/evidence/harness/S263_s88_preburn_prereg_2026-09-04.md`. Its committed LF-byte seal is `6f8bab53640391f6de1ae2b2b0c3d7946510fc919540733a71bbd59d9bfb3321`, verified before the binding with `git show HEAD:docs/evidence/harness/S263_s88_preburn_prereg_2026-09-04.md | head -n 18 | sha256sum`.

## Exact binding before condition

The S88 memo's old worktree prefix resolves to this worktree. I ran its exact binding locally:

```text
python -m scripts.platformkit.ingame.s88_phase_recal
```

Its remeasured output was:

```text
n_burn_in_dates     : 3
n_eval_ticks        : 33920
n_informative_ticks : 11087
partition           : S06 e4-blend incumbent, game-first-date leak-free, 47104 ticks / 158 games
PUBLISHED_ROWS=33920
```

Thus the count condition gives `47104 - 33920 = 13184`. The binding rewrote the published evidence during its specified run; it was restored immediately to its pre-run working-tree SHA-256 `b7cc67e0ff39a8f20b9b12e981ce93c2ace55374b38d9805e092ada99f9ba91d`. No published artifact change is included in this landing.

## Falsifying evidence

The S254 paired-loss artifact has 47,104 rows and 47,104 unique `game_id|ts` pairs. Its first three sorted game-first dates have these counts:

| date | rows |
|---|---:|
| 2026-06-30 | 7118 |
| 2026-07-01 | 5358 |
| 2026-07-02 | 708 |

Those rows sum to 13,184. S88 defines burn-in as the first `n_burn_in_dates` sorted dates, so the pre-burn rows are already present in a committed `docs/evidence/` artifact. The S254 CSV schema is additive for archival recovery: `game_id`, `ts`, `date`, `phase_bucket`, `phase`, `margin`, `model_prob`, `market_prob`, `outcome`, `recal_prob`, `incumbent_loss`, and `candidate_loss`.

## Inputs opened

| full path | bytes | raster resolution |
|---|---:|---|
| C:/Users/neelj/nba-track-a15/docs/evidence/harness/S88_phase_recal_2026-09-04.md | 9336 | n/a (markdown) |
| C:/Users/neelj/nba-track-a15/docs/evidence/harness/s88_phase_recal_2026-09-04.csv | 4311731 | n/a (CSV) |
| C:/Users/neelj/nba-track-a15/docs/evidence/harness/S254_mlb_phase_recal_fwer_sealed_2026-09-04_paired_loss.csv | 8506516 | n/a (CSV) |

## Result

There is no S263 row-count union or including-burn sensitivity table because the required CHANGE is conditional on an absence premise that did not hold. No scored comparison was claimed, no ledger or register was changed, and no per-file test was added or run.
