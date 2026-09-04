# S220 MLB event lead time

Verdict: **FALSIFIED; CLOSED AT LIMIT.** The tick-cadence premise is still
measurable, but the current GUMBO live store has zero files. It yields zero
joined event/game clusters, below the required 30. S217's absent capture store
and S62 row 3's unresolved MLB Stats API/GUMBO source decision are the named
blockers. No live capture, deployment, flag change, register write, or ledger
write occurred.

## Step 0: premise re-measurement

The analyzer read each tick file independently and never opened a file above
the 300 MB rail. The 405 JSONL files total 54,260,441 bytes; 401 files supplied
valid tick timestamps. The re-measured corpus is therefore 401 games and
79,566 ticks, not the row's older 371 games and 79,441 ticks. Its tick p50 is
31.0 seconds, its tick p90 is 82.0 seconds, and its maximum admitted live gap
is 869.0 seconds.

`gumbo_mlb_poller.py` stamps `ts` from MLB's `metaData.timeStamp` event clock
and stamps `captured_at` from this poller's UTC receive clock. No GUMBO row is
on disk to independently observe those two fields in this run.

## Frozen method and result

`FROZEN_MOVE_THRESHOLD = 0.004` probability points, byte-identical to
`scripts/platformkit/foundry/ingame_screen.BAR`. For a joined event, the
analyzer would compare every subsequent tick in the next 120 seconds against
the last line at or before the event timestamp and record the first absolute
move strictly greater than that threshold. A same-game non-event anchor at
least 120 seconds before the event and outside every event window is the
deterministic matched placebo. A window with no such move is retained as a
named right-censored row.

| Event class | joined n | event p50 / p90 / max s | event right-censored | placebo n, p50 / p90 / max s | placebo right-censored | observation floor s |
|---|---:|---|---:|---|---:|---:|
| run scored | 0 | null / null / null | 0 | 0, null / null / null | 0 | 31.0 |
| out recorded | 0 | null / null / null | 0 | 0, null / null / null | 0 | 31.0 |
| pitching change | 0 | null / null / null | 0 | 0, null / null / null | 0 | 31.0 |

The required observation floor is printed on every event-class row. A line
move below 31.0 seconds cannot be resolved by this corpus. No class has a
joined event, so there is no lead-time or placebo result to compare and no
right-censoring denominator beyond zero.

## Archived outputs and inputs

The summary and per-event archive are
`docs/evidence/harness/S220_mlb_event_lead_time_2026-09-04.json` (1,452 bytes)
and `docs/evidence/harness/S220_mlb_event_lead_time_2026-09-04.csv` (88 bytes).
The CSV has its required per-event schema but only its header because no event
joined. The analyzer source SHA-256 is
`FA0E24F457FEB3DBDAEF34E4B2144C16D57C1098CFE2CDAF2324EAB677F6B398`.

| Full path | Bytes | Resolution | Use |
|---|---:|---|---|
| `C:/Users/neelj/nba-track-a15/data/cache/ingame_grade/mlb` | 54,260,441 | n/a | 405 JSONL tick files, read one at a time |
| `C:/Users/neelj/nba-track-a15/data/domains/mlb/gumbo_live` | 0 files | n/a | metadata-only event-store premise check |
| `C:/Users/neelj/nba-track-a15/scripts/platformkit/ingame/s220_mlb_event_lead_time.py` | 8,874 | n/a | read-only analyzer |
| `C:/Users/neelj/nba-track-a15/docs/evidence/tracking/specs/S220_spec.md` | 4,220 | n/a | frozen threshold and acceptance contract |
| `C:/Users/neelj/nba-track-a15/docs/evidence/tracking/VERIFIER_CONTRACT.md` | 11,979 | n/a | sections B and Q1-Q9 |

## Verification

- Test: `python -m pytest scripts/platformkit/ingame/test_s220_mlb_event_lead_time.py -q` -- 2 passed.
- The analyzer is 164 lines, below the 300-line rail. The LOC rail test is run
  before landing.
- B1: no joined event is removed; censored rows remain explicit. B2/B6: this is
  additive, with no renamed field or reader change. B3/B4/B5: there is no gate,
  claim lifecycle, deployment, or live action. B7/B8/B9: no head slice, fit, or
  recycled denominator is used. B10/Q3: the fixed threshold is 0.004 in both
  the spec and archive. Q1/Q2/Q4/Q5: no scored comparison, preregistration,
  charge, ledger read, or model result occurred. Q6: calibration language only.
  Q7/Q9: no sampled or scored event set exists; the empty per-event archive is
  retained for reproduction. Q8: the store premise was re-measured first.

## NOT VERIFIED

- No on-disk GUMBO row was available to verify its timestamp stamping or derive
  the three event classes.
- No event-to-price lead time, placebo comparison, or censoring rate is
  measurable until at least 30 joined game clusters exist.
- S217 documents the absent MLB depth-capture premise; S62 row 3 leaves the
  MLB Stats API/GUMBO source decision unresolved. Neither blocker was changed.
