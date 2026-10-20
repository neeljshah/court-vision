# S826 books schedule load on restart -- REJECT (duplicate of S741), 2026-10-19

PAPER ONLY. No code was written. This memo is the reject record for the register row.

## Row as allocated

"A restarted books runner loads every still-open schedule file on disk whose games have not ended, not only
the pointer day; schedules_loaded:<n> in the heartbeat; adoption = one books restart outside every served
focus window."

## Premise check (falsified)

The premise came from my readiness report (NBA_READINESS_2026-10-19.md, the 16:10Z addendum). That report
said a books restart would drop the non-pointer day's rows. The claim was wrong and was corrected at 16:2xZ
(commit 8e8fa0b21).

- S741 (LANDED 22ac12090 on 10-05; scripts/platformkit/ingame/schedule_siblings.py, wired at
  schedule_pointer.py:242-244) runs on every pointer read, including the first read after a restart. It unions
  every dated sibling `<day>_maker_forward.json` in the pointer target's directory whose window can still be
  open (`at < day 00:00Z + 86400 + 3600`). Each sibling is verified against its `<day>_run.json` receipt, and
  only still-open rows are kept.
- Direction D+1 (pointer on 10-19, 10-20 rows must survive): kalshi/nba/_heartbeat.json at 15:4xZ showed
  schedule_sibling_files_loaded 1 = {"2026-10-20_maker_forward.json": "f321510a..."} and
  schedule_sibling_refusals_total 0.
- Direction D (pointer moved to 10-20 at 16:56:32Z, 10-19 rows must survive): kalshi/soccer/_heartbeat.json at
  17:56Z showed schedule_sibling_files_loaded 1 = {"2026-10-19_maker_forward.json": "59a2c881..."},
  carried_rows 6 and scheduled_games_total 2. Row-level evidence from kalshi/soccer/2026-10-19.jsonl:
  KXSERIEAGAME-26OCT19MONCAG-MON focus `snapshot` rows held a steady 24 per minute in every minute from 16:50Z
  to 17:05Z (across the move), spanning 16:28Z..17:30Z = its window [start - 120 s, start + 3600 s).
- The requested heartbeat count already exists: schedule_sibling_files_loaded / schedule_sibling_rows_loaded /
  schedule_sibling_files.

## Other facts recorded

- scripts/platformkit/ingame/local_capture_runner.py is at 300 LOC (the cap). Its sha in
  tests/platformkit/ingame/fixtures/s542_seal.json (ac2ed50f...) no longer matches the file (6ad9fd53...), and
  no test references that fixture, so it is a historical pin rather than an enforced one.
- S741's residual dependency: a sibling whose run.json receipt no longer records its bytes is refused and
  counted (sibling_receipt_mismatch). Any hand edit of a published schedule without its receipt would
  therefore drop that day's rows after a restart. No such edit happened on 10-19.

## Verdict

REJECT: duplicate of S741. No build, no codex tier (there is no diff to tier), no adoption restart. The
dispatcher may close S826, or re-scope it to a real gap if one is found later.
