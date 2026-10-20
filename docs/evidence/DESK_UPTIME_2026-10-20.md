# Paper desk host uptime, 2026-09-24 to 2026-10-18

PAPER ONLY. Operations accounting from committed receipts. No scored comparison, no calibration
metric and no edge claim is made or implied here.

## What this measures

How often the paper desk's host (one laptop) was up long enough to leave a scored night receipt.
Everything below is recomputed by `python -m scripts.platformkit.eval_gate.desk_uptime_report`
from git-tracked files under `docs/evidence/forward/` (the generator filters its inputs with
`git ls-files`, so a clean clone reproduces it; the 10-19 night and several 10-14..10-19 schedule
files were untracked when this was written and are excluded); `--check` confirms this table matches the JSON sidecar
`DESK_UPTIME_2026-10-20.json`.

Definitions:

- scheduled day: a `schedules/<date>_maker_forward.json` file exists.
- served day: that schedule lists at least one game (distinct game_id). This is the schedule of
  record, not a live-capture count; the coverage and census files do not carry a single per-day served
  figure, so they are not used.
- scored night: a `nights/<date>.json` receipt exists (COMPLETE or PARTIAL).
- partial reasons: the `reasons` list on a scored night. Night-attempt files carry only an attempt
  counter, so a day with no receipt has no machine-readable refusal reason; the cause is only the
  owner's own note (see the sleep windows).
- dark spell: the longest gaps between timestamped schedule, night, fill and result records
  (schedule started/completed, night started/selected, live-shadow fill, paper-result
  record/settlement/close). Timestamps are sparse, so a spell is an upper bound on record silence,
  not proof the host was powered off. Scored nights dated inside a spell (2026-09-26 in spell 1;
  2026-10-09 and 2026-10-10 in spell 2) were run and stamped after the spell ended, so the gap is
  not a host-off span.

<!-- DESK_UPTIME:BEGIN -->
| date | scheduled | games served | night receipt | partial reasons | attempt file |
|---|---|---|---|---|---|
| 2026-09-24 | yes | 4 | PARTIAL | ceiling_exceeded | no |
| 2026-09-25 | yes | 3 | PARTIAL | free_ram_below_floor | no |
| 2026-09-26 | yes | 6 | PARTIAL | free_ram_below_floor | no |
| 2026-09-27 | no | 0 | none | - | no |
| 2026-09-28 | no | 0 | none | - | no |
| 2026-09-29 | yes | 3 | PARTIAL | child_nonzero_exit | no |
| 2026-09-30 | yes | 3 | PARTIAL | step_deadline_exceeded | no |
| 2026-10-01 | yes | 2 | PARTIAL | free_ram_below_floor, step_deadline_exceeded | no |
| 2026-10-02 | yes | 2 | COMPLETE | - | no |
| 2026-10-03 | yes | 3 | PARTIAL | child_nonzero_exit, free_ram_below_floor | no |
| 2026-10-04 | yes | 5 | COMPLETE | - | no |
| 2026-10-05 | yes | 1 | COMPLETE | - | yes |
| 2026-10-06 | yes | 3 | PARTIAL | step_deadline_exceeded | yes |
| 2026-10-07 | yes | 7 | PARTIAL | step_deadline_exceeded | yes |
| 2026-10-08 | yes | 19 | PARTIAL | ceiling_exceeded, step_deadline_exceeded | yes |
| 2026-10-09 | yes | 19 | PARTIAL | step_deadline_exceeded | yes |
| 2026-10-10 | yes | 26 | PARTIAL | child_nonzero_exit | yes |
| 2026-10-11 | no | 0 | none | - | no |
| 2026-10-12 | yes | 7 | COMPLETE | - | no |
| 2026-10-13 | yes | 9 | PARTIAL | step_deadline_exceeded | no |
| 2026-10-14 | no | 0 | PARTIAL | step_deadline_exceeded | no |
| 2026-10-15 | no | 0 | none | - | no |
| 2026-10-16 | no | 0 | COMPLETE | - | no |
| 2026-10-17 | no | 0 | none | - | no |
| 2026-10-18 | no | 0 | none | - | no |

Summary (2026-09-24 to 2026-10-18, 25 days):

- days scheduled: 17
- days served (>= 1 game): 17
- scored nights: 19 (COMPLETE 5, PARTIAL 14)
- scored-night share: 76.0% (19 of 25 days)
- days with no night receipt: 6
- dark spell 1: 2026-09-25T13:56Z to 2026-09-28T15:07Z = 73.2 h
- dark spell 2: 2026-10-09T14:11Z to 2026-10-12T13:36Z = 71.4 h
- partial reasons on scored nights: ceiling_exceeded 2, child_nonzero_exit 3, free_ram_below_floor 4, step_deadline_exceeded 8

Owner-reported sleep windows (self-reported, from .planning/NOW.md; not receipt-derived):

- 2026-10-08T01:57:00Z to 2026-10-08T14:24:00Z = 12.4 h
- 2026-10-10T01:56:00Z to 2026-10-12T13:26:00Z = 59.5 h
- 2026-10-13T00:56:00Z to 2026-10-13T20:01:00Z = 19.1 h
- 2026-10-14T03:26:00Z to 2026-10-14T15:30:00Z = 12.1 h
- 2026-10-17T00:26:00Z to 2026-10-19T14:40:00Z = 62.2 h
<!-- DESK_UPTIME:END -->

Reconciliation. Over 2026-10-06..10-16 this table shows 9 night receipts (7 PARTIAL).
JOB_EVIDENCE_PACKET section 5, as of 2026-10-19, counts 8, because the 10-16 receipt was committed
on 2026-10-20. The two figures cover different as-of dates, not different results.

## Honest reading

The desk's record is prospective (schedules and nights are written before outcomes) but
intermittent. A missed night is a missed night: it is absent from the record, never filtered out
after the fact, and the night receipts carry no drop or re-select field. What intermittency
does do is shrink the sample: fewer scored nights means wider uncertainty on every calibration
readout, and the games on unscored days (including late-NBA and tennis windows that fell inside
sleeps) were never observed at all. It does not bias a night that was scored. 15 of the 20 scored
nights are PARTIAL; the reasons are listed above and a PARTIAL night is still a night that ran.
Sleep windows come from the owner's and desk sessions' own notes, are self-reported, and are not
in a tracked file.

## Fix in flight

Host availability is being addressed by the owner: keep the box awake while the desk runs, and move
the recorder to a spare laptop and/or cloud routines as the owner decides. Until that lands, any
public figure built on this record should cite the scored-night share above.
