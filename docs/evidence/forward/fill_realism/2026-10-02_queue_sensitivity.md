# S724 stored-row queue sensitivity receipt

PAPER ONLY. Status: INSUFFICIENT for calibration. This is a diagnostic replay
of the main checkout's execution-quality census entries marked OK. The census
status is inherited; this lane did not independently re-certify tape coverage.
No arm was chosen after inspection.

Reproduce the JSON from the worktree:
```
python -m scripts.platformkit.execution.queue_sensitivity --main-root C:/Users/neelj/nba-ai-system --census C:/Users/neelj/nba-ai-system/docs/evidence/forward/exec_quality/2026-09-22_2026-09-26.json --out docs/evidence/forward/fill_realism/2026-10-02_queue_sensitivity.json
```
The command printed nineteen census games, eight replayed games, and
`status: INSUFFICIENT`. Explicit tape-completeness evidence covers zero of
the eight replayed games, so the new qualification gate remains unmet. It
streamed seven hundred sixty-one thousand five
hundred twenty-five source lines, according to
`python -c "import json; d=json.load(open('docs/evidence/forward/fill_realism/2026-10-02_queue_sensitivity.json')); print(d['inputs']['scan_counts'])"`,
which printed `{'other_record_type': 302, 'source_lines': 761525}`.

Frozen settings printed by `python -c "import json; d=json.load(open('docs/evidence/forward/fill_realism/2026-10-02_queue_sensitivity.json')); print(d['settings'])"`:
six-second submit and cancel delays, thirty-second quote life, quantity two,
four-times displayed conservative queue, sixty-second mark, and game bootstrap
with four hundred draws, seed 724, central ninety percent. Missing depth is counted, and
no-depth permits through prints only. The receipt prints zero unknown-depth
quotes for these particular selected games; that does not resolve the separate
unknown-depth contexts in the later fill-realism run.

The following values were printed by the `python -c` summary command in
`S724_result_2026-10-02.md`. Shares use quoted orders, then filled orders;
markout is fee-inclusive cents per marked contract. Intervals resample games
as clusters and are descriptive because the game floor is unmet.

| Arm | Quotes | Filled | Partial | Fill share [interval] | Partial share [interval] | Mark [interval] | Missing mark fills |
|---|---:|---:|---:|---|---|---|---:|
| no_depth | two thousand four hundred eighty-two | one hundred fifty | nine | 0.0604 [0.0405, 0.0890] | 0.0600 [0.0069, 0.1298] | 0.0816 [0.0227, 0.1514] | one hundred fifty-eight |
| displayed_depth | two thousand four hundred eighty-two | one hundred fifty-nine | nine | 0.0641 [0.0445, 0.0944] | 0.0566 [0.0065, 0.1218] | 0.0719 [0.0212, 0.1236] | one hundred sixty-two |
| conservative_queue | two thousand four hundred eighty-two | one hundred fifty-five | nine | 0.0624 [0.0428, 0.0928] | 0.0581 [0.0067, 0.1258] | 0.0789 [0.0227, 0.1447] | one hundred sixty-two |

Across-arm ranges, from the same summary command: fill share
[0.0604, 0.0641], partial share [0.0566, 0.0600], and sixty-second
markout [0.0719, 0.0816] cents. These are diagnostic ranges, not calibrated
execution estimates. The JSON retains all games, source counts, refusals,
per-game denominators, and all three arms.

## NOT VERIFIED

Venue queue rank, hidden liquidity, acknowledgement times, cancellation
confirmation, independent tape completeness, account-specific fee precision,
or a continuous full-game capture. Most simulated fills lack a timely mark;
the mark summaries are insufficient for calibration.
