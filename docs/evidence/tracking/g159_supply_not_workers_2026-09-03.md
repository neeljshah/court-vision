# G159 Supply Versus Worker Capacity

Date: 2026-09-03

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, including A2, A7, Q7, Q8, and section B.

## Verdict

**NOT VALIDATED: neither supply nor worker capacity can be named as the binding constraint from this run.** The required at-least-30-minute local-download and pod-completion comparison did not occur: three independent read-only samples span 116 seconds, local staging exposed no growing download file, and no job completed during that window. Per G159's NEVER PARK instruction, no monitor was started and the observation stopped rather than waiting for the missing 30-minute window.

The live observation does falsify a clean occupancy reading. All three samples found the configured `--workers 10` daemon with **0 tracking jobs**, while an `ffprobe -count_frames` process against the KBO staged source persisted from 57 to 173 elapsed seconds. This is the G156 confound, so the occupancy distribution is labelled **CONFOUNDED**, not evidence that supply binds. Increasing workers would not fix that observed synchronous poll-loop condition, but that is not the same as a supply-versus-capacity rate verdict.

Raw sampled values and commands are committed in [`g159_supply/raw_samples.md`](g159_supply/raw_samples.md) and [`g159_supply/samples.csv`](g159_supply/samples.csv).

## Q8 premise re-measurement

The premise that the daemon is configured for ten workers is true at every sample: PID 33064 ran `python -u -m scripts.platformkit.track_daemon --workers 10 --forever --interval 15`. The premise that a one-job reading demonstrates supply limitation is false as stated for this window: no `run_clip.py` or `adapter_run.py` process was present, and the retained `ffprobe -count_frames` process makes the zero-worker occupancy confounded.

## Method and sample schedule

Each probe listed the local bridge staging directory and bridge lane processes; on the pod it ran `ps -eo pid,etimes,args`, listed `data/footage_bridge`, used `du -sb data/footage_bridge data/footage_corpus`, and read the daemon ledger. No pod file or process was changed. Samples were scheduled and completed at pod UTC `14:34:25`, `14:35:32`, and `14:36:21`, giving intervals of 67 and 49 seconds (116 seconds total).

## Measurements

| Metric | Result | Eligible denominator / caveat |
|---|---:|---|
| Local bridge lanes | 7 at each sample | baseball, WNBA, tennis, soccer, football, MLB, NCAA basketball; command lines in raw sample. |
| Local download MB/s, per lane and aggregate | NOT OBSERVABLE | `data/videos/bridge` had the same five stale files at all three samples and exposed no active download file. This is not reported as 0 MB/s. |
| Pod `.part` transfer, not local download | 1.021 MB/s (0.974 MiB/s) for sample 001 to 002; 0 for 002 to 003 | Tennis `.part` grew 68,413,440 bytes over 67 seconds, then was unchanged for 49 seconds. It is excluded from the requested local-download metric because local staging did not expose its source. |
| Tracking occupancy | 0/10 in 3/3 samples | Distribution: `{0: 3}` tracking jobs. All three are confounded by the named `ffprobe`; excluding stall samples leaves n=0, so no clean occupancy distribution exists. |
| Completed jobs in the sample window | 0 | Eligible denominator is completed daemon-ledger jobs from `14:34:25Z` through `14:36:21Z`; no new ledger line appeared. |
| Latest ledger service time | 296 seconds | The sole retained row finished at `2026-09-03T14:23:41Z`, before this window. Its arithmetic-only serial equivalent is 12.162 games/hour, but it is not used as the window completion rate. |

The required comparison is therefore undefined: arrival rate is unavailable and window completion rate is `0 / 0` (no eligible completions), not zero. Treating a short remote `.part` upload interval as local download supply, or treating the pre-window 296-second ledger row as a same-clock capacity rate, would manufacture a conclusion.

## Quota measurement and recommendation only

`du -sb` at samples 002 and 003 reported 1,346,141,203 bytes in the pod stage and 342,144,561 bytes in the retained-source corpus: 1,688,285,764 bytes total. With the unchanged `MAX_POD_BACKLOG = 24` and the stated approximately 2,000,000,000-byte game size, the decimal-50-GB arithmetic allows `floor((50,000,000,000 - 1,688,285,764) / 2,000,000,000) = 24` more average-size games before the volume quota itself binds. Two complete MP4s were already staged, so the backlog cap has 22 complete-file slots remaining; the current `.part` is deliberately excluded from backlog counting. The retained corpus is included in the quota arithmetic. Recommendation only: do not raise `MAX_POD_BACKLOG` or change workers; leave the current values untouched.

## NOT VERIFIED

- A 30-minute sample window with an observable local download file for each active lane.
- Per-lane or aggregate local download throughput.
- Same-clock games-arriving-per-hour versus games-completing-per-hour.
- A clean, stall-excluded pod occupancy distribution; all retained samples coincide with the G156 `ffprobe` condition.
- Which of supply or capacity binds. The observed immediate blocker is daemon poll-loop availability, not a valid rate comparison.
- Whether the tennis upload was sourced from the configured local bridge staging directory; its pod `.part` growth is not substituted for that fact.

## Verifier self-check

- A2: calculations reproduce from `samples.csv`: 68,413,440 bytes / 67 seconds = 1.021096 MB/s; 3/3 tracking-job counts are zero; `du` sums to 1,688,285,764 bytes. No headline supply/capacity rate is claimed.
- A7: all evidence paths named here exist in this commit: this memo, `g159_supply/raw_samples.md`, and `g159_supply/samples.csv`.
- B1: all three samples and both intervals are retained. The 116-second shortfall and zero-completion denominator are explicit, not excluded.
- B2: no runtime schema, field, status, or reader changed; only additive evidence documents were added.
- B3 and B4: no gate, claim lifecycle, or retention behavior changed.
- B5: no pod deployment, copy, process action, restart, worker change, backlog change, or file mutation occurred.
- B6: no module moved or retired.
- B7 and B8: no render, head slice, fitted result, or independent-fit claim is made.
- B9: each sample has a unique UTC timestamp; the rate interval is identified by its two samples, and the completion denominator is explicitly zero.
- B10: `--workers 10`, `MAX_POD_BACKLOG = 24`, and every threshold and verdict remain unchanged.
