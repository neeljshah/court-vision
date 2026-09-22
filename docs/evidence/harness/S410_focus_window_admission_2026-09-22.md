# S410 focus-window admission: construct build

Local worktree: C:/Users/neelj/nba-harness-h68. Interpreter: Python 3.10.0.
Authority: docs/evidence/tracking/specs/S410_spec.md including AMENDMENTS 1-4.
Contract A, B and Q were read. PREPARE only; local construct inputs only.
Starting HEAD: e65683a7d1a756a268a0fe3f7e70011045c1fd8f.
FIX 1b updates the construct build for AMENDMENT 3. No commit was made.

## Binding before-condition evidence

All six named source/artifact files have empty diffs against HEAD and master.
The checks below quote the landed before-conditions, without modifying them.

- scripts/platformkit/ingame/capture_scheduler.py:123:
  `if start - 120 <= now < start + 3600: priority.append(game); ids[game] = row["game_id"]`
- scripts/platformkit/ingame/capture_scheduler.py:113:
  `if any(b - a < 3600 for a, b in zip(starts, starts[2:])): raise ValueError("schedule exceeds two games per hour")`
  This refuses the whole schedule.
- docs/evidence/forward/schedules/2026-09-22_maker_forward.capacity_note.json:3:
  `"denominator_of_record": "docs/evidence/forward/schedules/2026-09-22_maker_forward_full_selection.json"`
  Lines 4-8 list three not_served tickers; lines 10-14 list three served tickers.
  Line 9 states `any three consecutive starts must span >= 3600 s` and cites
  `capture_scheduler.schedule_rows line 113`.
- scripts/platformkit/ingame/capture_scheduler.py:116:
  `dict(scheduled_games_total=0, scheduled_admitted=0, scheduled_not_admitted=0)`
  Line 118 increments `scheduled_games_total`. Line 119 counts
  `"scheduled_market_unavailable": 1` and `"scheduled_pair_refused": 1`;
  line 121 increments `errors["scheduled_pair_refused"]`.
  Line 135 increments `stats[game[0]]["scheduled_not_admitted"]`.
- scripts/platformkit/ingame/local_capture_runner.py:207:
  `if kind == "focus_books":`
  Line 210 calls `_book(client, writer, state, markets[key], iso(now), clock())`.
  Line 63 writes
  `writer.append(record, "books" if record["record_type"] == "snapshot" else "fetch_error")`.
- scripts/platformkit/ingame/local_capture_runner_row.py:58:
  `out = envelope(market, "snapshot_bulk", request_start, response_end, http_status)`
  Lines 46-50 define the shared row envelope: record_type, venue, sport,
  series, ticker, event_ticker, capture_ts, request_start_ts, response_end_ts,
  http_status and capture_version.
- scripts/platformkit/ingame/local_capture_runner.py:236:
  `writer.atomic(lrow.heartbeat_path("kalshi", sport, writer.root), state["hb"][sport], "heartbeat")`
- scripts/platformkit/ingame/local_capture_runner_row.py:146:
  `def heartbeat_path(venue: str, sport: str, output_root: Path) -> Path:`
  Line 148 returns `output_root / venue / sport / "_heartbeat.json"`.
  There is no append-only scheduler journal in the cited route; its one
  heartbeat per sport is atomically replaced. The open instant must be
  inferred from the receipt stream, not from a heartbeat time series.
- scripts/platformkit/ingame/forward_capture_profile.json:2:
  `"focus_tick_s": 5,`
  Line 3: `"reservation_ttl_s": 5,`
  Line 5: `"maximum_scheduled_games_per_hour": 2,`
- scripts/platformkit/execution/forward_replay_qualification.py:16:
  `WINDOW_S = 3600`
  Line 19: `BOOK_MEDIAN_S, BOOK_P95_S, BOOK_MAX_S = 45, 90, 120`
  Line 47: `def nearest(values: list, percentile: int) -> D:`
  Line 49: `return sorted(values)[(len(values) * percentile + 99) // 100 - 1]`
  Lines 41-44 include positive boundary gaps using start, receipts and end.

## FIX 1b: AMENDMENT 3 (a)-(d)

Interpreter: C:/Users/neelj/AppData/Local/Programs/Python/Python310/python.exe,
Python 3.10.0. Timestamp parsing remains through parse_venue_time; datetime
only formats validated epoch values. Required --as-of is a zoned instant,
recorded verbatim; future receipts are excluded. Window bounds are UTC
window_start and window_end, interpreted as [start, end). window_status is
not_started before start, in_progress from start, completed at or after end.
An unparseable scheduled_start retains its named reason and lacks bounds/status.

The existing quantiles_s and meets_frozen_values retain positive boundary gaps
and the imported 45/90/120 comparisons; window_seconds remains the integer 3600.
in_window.max_s aliases quantiles_s.max. trailing_boundary_s names the distance
from the last in-window receipt to window_end. max_completed_s excludes that
trailing gap and exists only for a completed window with positive remaining
gaps. Empty gap sets never invent zero quantiles.

A crossing ticker reads both dated shard sets. Each game's shards records
every opened applicable path with size_bytes; next_day_shard_absent is counted
per game and sport. Noncrossing tickers ignore next-day rows; out_of_window
retains only the requested date's shard receipts. Every line is JSON-decoded
before ticker filtering; memory holds one decoded row plus selected timestamps,
not constant memory. fetch_error rows may carry a book but are not focus evidence.

Heartbeat counters and label=single_snapshot remain unchanged. Added
counter_scope=source_heartbeat_counters and heartbeat_captured_at preserve
the source file mtime independently of any timestamp in its JSON body.
heartbeat_denominator labels these counters unrelated to this audit's denominator.
two_per_hour_refused is a full-selection capacity diagnostic; it
does not establish that the running scheduler refused six games.
The scheduler's own selection is visible only through the served subset
and heartbeat. This distinction is also labelled in the output artifact.

## AMENDMENT 2: first real run, verbatim from the binding spec

The following is orchestrator-supplied evidence, not a FIX 1b real-shard run.

AMENDMENT 2 (2026-09-22 23:1xZ; binding; VERBATIM FACTS from the orchestrator's first real run of the built candidate, from
the worktree, over the real Kalshi mlb shard (323,207,242 bytes at run time) with the committed 2026-09-22 full selection (six
games) and its capacity note, run at about 23:09Z while the first two games were in progress; exit 0, wall clock about 2 s).
PER GAME: TORBAL (22:35Z start) focus_open_lag_s -118.755464, in-window receipt_count 382 (gap_count 383) with quantiles
median 5.173227 / p95 5.868722 / max 1547.427332 s (median and p95 meet the frozen values, max does not -- the window was still
in progress, so the trailing boundary gap to the window end is inside the max), covered_seconds 1908 of 3600; MILPHI (22:40Z)
lag -117.205747, receipt_count 328, median 5.171961 / p95 5.801679 / max 1852.003233, covered 1638; STLPIT and CLEBOS (unserved
by the capacity subset) in-window receipt_count 0, quantile_absent, covered 0, out-of-window gaps median about 249-256 s;
CINATL (23:15Z) and MIACHC (23:40Z) not yet started, in-window 0; first_seen_lag_s about -81,000 to -85,000 s for every game
(the markets were discovered the previous evening). REASON COUNTS (mlb): capacity_subset_excluded 3, no_focus_receipt_in_window 4,
two_per_hour_refused 6; the heartbeat snapshot (single_snapshot) copied verbatim: scheduled_games_total 3, scheduled_admitted 2,
scheduled_not_admitted 0, error_counters duplicate_trade_id 133911 / missed_deadline 1022 / schedule_refused 18. PROFILE
focus_tick_s 5, sha256 5bb818074c5083049e804bffda59c2b5b701706048983d32bbb313120ea3607c. PROGRAM FACT: for a SERVED game the
focus window opens about two minutes before scheduled_start and holds a 5 s cadence; an UNSERVED game gets no in-window
receipt at all -- the capacity subset, not the scheduler's timing, is what a FAIL on S390 will name; the S390 retrospective run
over this date must be made after every scheduled window has ended (the last, MIACHC, ends 2026-09-23 00:40Z) so that the
trailing boundary gap is real. The memo records these counts verbatim as the first real run; the verifier judges whether the
in-progress-window case must be labelled in the artifact (window_in_progress) and whether two_per_hour_refused counting every
game is the capacity rule as capture_scheduler.py implements it.

## FIX 1b checks and reproduction

Pinned tests: test_focus_window_admission.py:226 (a), :244 (b),
:89 (c), :275 (d); :265 and :269 pin zoned/required --as-of.
Module: :131 status, :153 separate gap/max, :179 heartbeat, :204 midnight.
Tracked reader search found only the S410 spec; existing output fields remain.
The capacity label and heartbeat scope are additive. No frozen value changed.

Required per-file test: 39 passed in 0.95s. --help exits 0.
Contract preflight: nine PASS lines, FAIL count 0 (rerun after memo update).
Both fixtures are unchanged. No real-shard run, network access, live capture
access, data/cache access, or commit was performed by FIX 1b.

The same Python one-liner was executed before and after the module/memo edits.
Its construct has start 23:40Z, receipts 23:40:05Z and next-day 00:00:05Z,
as_of 00:10Z, and a heartbeat mtime pinned independently of its JSON.
Before:
```text
a status=ABSENT trailing=ABSENT max=3595 completed=ABSENT
b receipts=1 shards=0
c mtime=ABSENT scope=ABSENT
d real_run=False diagnostic=False
```
After:
```text
a status=in_progress trailing=2395 max=2395 completed=ABSENT
b receipts=2 shards=2
c mtime=2026-09-22T12:00:00Z scope=source_heartbeat_counters
d real_run=True diagnostic=True
```
The pinned completed-window test separately proves max_completed_s=5 while
max_s=3595 and all three frozen comparisons remain unchanged.

Reproduction source (executed using Python -B -c with exec(bytes.fromhex(...))
to preserve quoting under cmd.exe; only temporary construct files are created):
```python
import inspect, json, os, tempfile
from pathlib import Path
from scripts.platformkit.execution import focus_window_admission as m
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp); shard=root/'kalshi'/'mlb'/'2026-09-22.jsonl'; shard.parent.mkdir(parents=True)
 schedule=root/'schedule.json'; schedule.write_text(json.dumps([dict(sport='mlb',game_id='X',ticker='X',scheduled_start='2026-09-22T23:40:00Z')]))
 shard.write_text(json.dumps(dict(ticker='X',record_type='snapshot',response_end_ts='2026-09-22T23:40:05Z'))+'\n')
 shard.with_name('2026-09-23.jsonl').write_text(json.dumps(dict(ticker='X',record_type='snapshot',response_end_ts='2026-09-23T00:00:05Z'))+'\n')
 hb=shard.parent/'_heartbeat.json'; hb.write_text('{"scheduled_games_total":3}'); os.utime(hb,(1790078400,1790078400))
 kwargs={'as_of':'2026-09-23T00:10:00Z'} if 'as_of' in inspect.signature(m.audit).parameters else {}
 r=m.audit(schedule,root,'2026-09-22',**kwargs); g=r['games'][0]; h=r['sports']['mlb']['heartbeat_snapshots'][0]
 print('a status='+g.get('window_status','ABSENT')+' trailing='+g['in_window'].get('trailing_boundary_s','ABSENT')+' max='+g['in_window']['quantiles_s']['max']+' completed='+g['in_window'].get('max_completed_s','ABSENT'))
 print('b receipts='+str(g['in_window']['receipt_count'])+' shards='+str(len(g.get('shards',[]))))
 print('c mtime='+h.get('heartbeat_captured_at','ABSENT')+' scope='+h.get('counter_scope','ABSENT'))
 memo=Path('docs/evidence/harness/S410_focus_window_admission_2026-09-22.md').read_text()
 print('d real_run='+str('-118.755464' in memo and '-117.205747' in memo)+' diagnostic='+str('full-selection capacity diagnostic' in memo))
```

git diff HEAD --stat -- <five owned files>: empty because all five are untracked.
git status --porcelain: exactly the five owned paths, each prefixed ??.
ASCII checked on every owned file. Module/tests/books/schedule LOC: 263/283/5/11.
The real-shard run with FIX 1b and master-side verifier reproduction remain unrun.

## FIX 1c: AMENDMENT 4 (a)-(c)

Python 3.10.0: C:/Users/neelj/AppData/Local/Programs/Python/Python310/python.exe.
All reproduction inputs are temporary constructs; timestamp parsing uses
parse_venue_time. Scheduled starts require a parseable string; refused rows
carry row_status=REFUSED, scheduled_start=repr(raw) text, and the counted
scheduled_start_unparseable reason at game and sport level.
The writer uses a temporary file in the output directory, flush, fsync,
and os.replace; serialization failures name artifact_serialization_failed,
preserve any previous artifact, and remove the temporary file.
An empty heartbeat snapshot list now counts heartbeat_absent once per sport.
heartbeat_age_s is Decimal text beside heartbeat_captured_at; negative ages
are reported unchanged. There is no heartbeat age threshold.

Pinned constructs cover (a) NaN, Infinity, a number, null, garbage and a valid
string, plus serialization/fsync/replace failure with and without a previous
artifact; (b) the exact final NOT VERIFIED list; (c) absent heartbeat and
integer, fractional and negative age. FIX 1b tests retain the [start, end)
boundary, absent not_started quantiles, imported values and 3600 denominator.
The midnight test now explicitly repeats a receipt across both dated shards
and confirms it is counted once.

Three before/after reproductions, executed with the same Python one-liner
(`python -B -c exec(bytes.fromhex('<hex of source below>'))`):
(a) refused starts and serialization, (b) memo list, (c) heartbeat absence/age.
Before:
```text
a nan exit=3 complete=False count=1 raw=nan
a inf exit=3 complete=False count=1 raw=inf
a serialization exit=3 previous=False
b NOT_VERIFIED_entries=0
c heartbeat_absent=0 captured=2026-09-22T12:00:00.125Z age=ABSENT
```

After:
```text
a nan exit=0 complete=True count=1 raw='nan'
a inf exit=0 complete=True count=1 raw='inf'
a serialization exit=3 previous=True
b NOT_VERIFIED_entries=3
c heartbeat_absent=1 captured=2026-09-22T12:00:00.125Z age=3599.875
```

FIX 1c local single-file test: 52 passed in 0.86s.
Required --help exited 0. Contract preflight against master and S410_spec.md:
nine PASS lines, zero FAIL lines. ASCII and <=300 lines checked on all five
owned files. Module/tests/books/schedule LOC: 292/300/5/11.
Module anchors: :44 string-only start; :120 refused row; :171 heartbeat age;
:253 atomic write. Pinned tests: :206 invalid starts and heartbeat absence;
:224 atomic failures; :83 heartbeat ages; :290 final memo list.
Tracked reader search found only the S410 spec. Both fixtures are unchanged.
git diff HEAD --stat -- <five owned files> is empty because all five remain
untracked; git status --porcelain lists exactly those five paths with ??.
No commit, network access, data/cache access or live-capture access was made.

Reproduction source:
```python
import contextlib, io, json, os, tempfile
from pathlib import Path
from unittest.mock import patch
from scripts.platformkit.execution import focus_window_admission as m
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp); shard=root/'kalshi'/'mlb'/'2026-09-22.jsonl'; shard.parent.mkdir(parents=True); shard.write_text('')
 schedule=root/'schedule.json'; out=root/'out.json'; at='2026-09-22T13:00:00Z'
 args=['--schedule',str(schedule),'--books-root',str(root),'--date','2026-09-22','--as-of',at,'--out',str(out)]
 for value in (float('nan'),float('inf')):
  schedule.write_text(json.dumps([dict(sport='mlb',game_id='X',ticker='X',scheduled_start=value)]))
  log=io.StringIO()
  with contextlib.redirect_stdout(log): code=m.main(args)
  try: json.loads(out.read_text()); complete=True
  except ValueError: complete=False
  g=m.audit(schedule,root,'2026-09-22',as_of=at)['games'][0]
  print('a '+repr(value)+' exit='+str(code)+' complete='+str(complete)+' count='+str(g['reason_counts']['scheduled_start_unparseable'])+' raw='+repr(g['scheduled_start']))
 out.write_text('{"previous":true}')
 with patch.object(m,'audit',return_value={'bad':float('nan')}), contextlib.redirect_stdout(io.StringIO()): code=m.main(args)
 print('a serialization exit='+str(code)+' previous='+str(out.read_text()=='{"previous":true}'))
 memo=Path('docs/evidence/harness/S410_focus_window_admission_2026-09-22.md').read_text()
 tail=memo.rsplit('NOT VERIFIED',1)[-1]
 print('b NOT_VERIFIED_entries='+str(sum(line.startswith('- ') for line in tail.splitlines())))
 schedule.write_text(json.dumps([dict(sport='mlb',game_id='X',ticker='X',scheduled_start='2026-09-22T12:00:00Z')]))
 r=m.audit(schedule,root,'2026-09-22',as_of=at)
 absent=r['sports']['mlb']['reason_counts'].get('heartbeat_absent',0)
 hb=shard.parent/'_heartbeat.json'; hb.write_text('{}'); ns=int(m.parse_venue_time('2026-09-22T12:00:00Z'))*10**9+125000000; os.utime(hb,ns=(ns,ns))
 h=m.audit(schedule,root,'2026-09-22',as_of=at)['sports']['mlb']['heartbeat_snapshots'][0]
 print('c heartbeat_absent='+str(absent)+' captured='+h['heartbeat_captured_at']+' age='+h.get('heartbeat_age_s','ABSENT'))
```

NOT VERIFIED
- Master-side test execution.
- The revised real-shard run.
- AMENDMENT 2 measurements: transcribed, not reproduced.
