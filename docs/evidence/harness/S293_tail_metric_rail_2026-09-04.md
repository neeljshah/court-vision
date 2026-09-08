# S293 tail metric rail

## Verdict

NOT VALIDATED. This row implements and reproduces calibration metrics only; it does not fit or accept a candidate.

Preregistration: `docs/evidence/harness/S293_tail_metric_rail_prereg_2026-09-07.md`

LF-normalized preregistration seal: `8af6d5591a3b70f983d94dd5ab9b2a34dc659f0d65b18126b7482175e18618e8`

The sandbox denied staged-byte inspection and commit creation. The embedded seal is SHA-256 of the LF-normalized bytes above its seal line; the orchestrator must verify the committed bytes after explicit-path landing.

## Reproduction

The unchanged S272 route regenerated every tick through its CPCV prediction path with a symmetric one-day embargo and purge. The S293 per-tick differential stores evaluator fields `p_model`, `p_close`, `y`, `split_id`, and `n_train` plus additive loss fields. No loss comes from the old mixed-grain archive summaries.

| metric | candidate | recal_null | delta (baseline minus candidate) |
|---|---:|---:|---:|
| all-tick Brier | 0.073353613894633 | 0.073316945556601 | -0.000036668338033 |
| tail Brier | 0.006840435259548 | 0.006785181571842 | -0.000055253687706 |
| tail ECE | 0.001244584782361 | 0.001493409874920 | 0.000248825092560 |
| tail log loss | 0.030833806300610 | 0.028761870222461 | -0.002071936078148 |

Improvement means baseline loss minus candidate loss; positive means lower candidate loss. The frozen Brier bar remains `+0.004`. The reproduced all-tick Brier interval lower bound is -0.000070422974932; compared with -0.0005 this is a diagnostic comparison only, not an acceptance condition.
All-tick log loss was computed for implementation auditing and is stored in the summary, but no all-tick log-loss comparison claim is made.

## Accounting

Endpoint and clipping counts: `{"candidate": {"clipped_rows": 142316, "excluded_rows": 0, "n": 465249, "one_probability_rows": 80162, "zero_probability_rows": 62154}, "recal_null": {"clipped_rows": 0, "excluded_rows": 0, "n": 465249, "one_probability_rows": 0, "zero_probability_rows": 0}}`. Zero-probability rows are clipped at epsilon 1e-15; excluded rows are zero.
OT periods 5-6: 14765 ticks. Zero-clock ticks: 271154. The S291 mask has 133184 ticks across 1111 games, with 132750 trailing-side wins and 434 losses; it includes unsuccessful trailing states.

## Fine-bin diagnostic table

| bin | ticks / games | recal_null log loss | market log loss |
|---|---:|---:|---:|
| [0.01,0.05) | 9226 / 649 | 0.108935350460834 | 0.109064231604745 |
| [0.05,0.10) | 8982 / 691 | 0.261167621122677 | 0.261923312933974 |
| [0.10,0.20) | 15778 / 826 | 0.468033294804994 | 0.469461864991162 |
| [0.80,0.90) | 23912 / 1005 | 0.452100455173979 | 0.452417312322612 |
| [0.90,0.95) | 13123 / 871 | 0.251914078110729 | 0.251267723457134 |
| [0.95,0.99) | 12624 / 827 | 0.127493601362987 | 0.126642126705553 |

Full reliability tables, source identities, RSS before/after, all tick-level paired losses, and S291 trailing-side diagnostics are in `S293_tail_metric_rail_2026-09-04_summary.json` and `S293_tail_metric_rail_2026-09-04_paired_losses.csv.gz`.

## Contract self-check

- B1: all source ticks are regenerated; no unfavorable diagnostic bin is removed.
- B2: evaluator fields are retained and only new loss fields are added.
- B5: the sole measurement ran in pod scratch through pod_run; no deployed tree was modified.
- Q1: this memo names the preregistration and its LF-normalized seal.
- Q3: the frozen +0.004 Brier bar is unchanged.
- Q4: S272 retains the CPCV route, purge, and nonzero one-day embargo.
- Q6: calibration language only.
- Q7: all scored and diagnostic groups publish their tick/game counts.
- Q8: source identities were remeasured before dispatch and after scoring.
- Q9: the per-tick paired-loss differential includes cluster id, timestamp, and reconstructible OOF probabilities.

## NOT VERIFIED

- A committed-byte verification of the preregistration seal, because staging and commit are sandbox-denied.
- Independent verifier reproduction in the landing worktree.
- Any candidate fit or calibration acceptance under the frozen comparison bar.
