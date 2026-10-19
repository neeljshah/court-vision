# S805 measurement memo -- qualification step resident set (2026-10-09, PAPER ONLY, measurement only)

Row S805 (docs/evidence/HARNESS_GAPS_2026-09-03.md). No code changed for this row: this memo names the resident structure,
measures it, and states why the bound is not built in this lane (ownership). Operations language only.

## 1. Premise (fresh reads, 2026-10-09)
- nights/2026-10-08.json step qualification: KILLED, reason ceiling_exceeded, exit 15, peak_working_set_bytes 1,598,431,232
  vs ceiling_bytes 1,572,864,000 (the night wrapper's ceiling; paper_night_deadline.py:261-264), wall 829.172 s, empty claim
  removed, scratch_swept_bytes 8,155,191,223. CONFIRMED.
- CORRECTION to the row text "no qualification receipt since 10-05": docs/evidence/forward/qualification/2026-10-06.json exists
  (9,971 bytes, written 10-07 12:30 local, as_of 2026-10-07T06:00:00Z, games_total 3); 10-07 and 10-08 have none.

## 2. Method
Scratch capture view C:/Users/neelj/AppData/Local/Temp/claude/s806/qview08/ (kalshi|state/<sport>/<date>.jsonl hard links to the
S806 r08 files). Byte lengths: the KILLED step left no receipt, so the recorded lengths are a PROXY: the fill_realism receipt's
inputs[].bytes of the same night (that step started 14 min after qualification, so the proxy can only be longer).
qmeasure.py runs forward_qualification_daily.main(argv) in-process with the night's own argv except --capture-root (scratch
view), --out (scratch) and a sport-filtered copy of --schedule / --served-schedule; RSS sampled every 20 ms, a mark at every
StreamedEvidence phase (spooled / linked / taped / replayed), at bridge._links entry (number of state rows listed), at
replay.run entry / exit, and every 100,000 rows of Store.native(role). Self-kill above 1,200 MiB (lane cap); one process at a time,
free RAM >= 2,500 MB, pump.stop absent. Subsampled BY SPORT because the full night exceeds the cap.

## 3. Results (master code 0666dbc99 = branch code for these modules)
| sport subset | scheduled | state rows listed | peak at _links entry | peak overall | outcome |
|---|---|---|---|---|---|
| mlb | 2 | 2,929 | 167 MiB | 168 MiB (wall 79 s) | rc 0, artifact written, 0 qualified of 2 |
| nba | 8 | 12,683 | 203 MiB | 204 MiB | rc 3 reused_run_nonce at replay start (the mlb run had recorded the nonce in the WORKTREE's vault/S362 ledger; removed afterwards) -- load phases fully measured |
| tennis | 15 | n/a (killed before _links) | n/a | > 1,200 MiB at t = 229 s | self-kill: state rows 0 -> 100,000 -> 200,000 took RSS 33 -> 537 -> 1,040 MiB |
Tennis trace (q08_tennis2.jsonl): spool finished at 33 MiB (the disk spool works); books pass 24,898 rows at 33 MiB (streams);
then `states = [row for _, row in store.native("state")]` (forward_capture_stream.py:_load) grows about 5.0 KiB per state row
(+504 MiB per 100,000 rows). The tennis D shard alone holds 944,944 state lines (state/tennis/2026-10-08.jsonl, 759,110,342 bytes),
so the list would need roughly 4.5 GiB for that shard before the D+1 rows: the step cannot fit any ceiling on a tennis night
while that list exists. On mlb / nba nights the same list is 3k-13k rows (under 200 MiB), which is why 10-05 / 10-06 ran.

## 4. The resident structure, named
forward_capture_stream._load: `states = [row for _, row in store.native("state")]` -- every as-of-visible state row of every
scheduled sport, unpickled at once, held through bridge._links (which also groups them all by (sport, game_key)) and the output
loop, then `del states`. Served row count matters only through which sports are scheduled: one tennis match family is enough.

## 5. Proposed bound (NOT built: ownership)
Two streaming passes over Store.native("state") instead of the list: pass 1 feeds _links SLIM rows (only the keys _common, _text
and _metadata read: sport, game_key, ids, receipt fields, scheduled_start_utc and the metadata fields, http_status, _refusal),
recording any _refusal it sets by pos; pass 2 re-reads each full row and emits it exactly as now (with the recorded _refusal
re-attached). Expected resident set: slim rows, a few hundred bytes each instead of ~5 KiB. Bytes-unchanged check: the 10-05
receipt (and 10-06) at their recorded hashed_bytes. Window, gates and bars untouched.
Why not built here: forward_capture_stream.py is imported by forward_qualification_daily.py AND by
scripts/platformkit/execution/book_provenance_replay.py and scripts/platformkit/ops/probes/s479_ram_probe.py (tests:
test_forward_capture_stream.py, test_forward_capture_stream_integration.py, test_forward_replay_io_shard_sport.py,
test_s733_tape_lower_bound.py), so it is NOT exclusive to the qualification step and is outside this lane's OWNS; the grouping
in forward_capture_bridge._links (300 LOC, shared) would also be read-only input to the change. Needs a dispatcher ownership
grant for forward_capture_stream.py (+ its tests) before a build.

## 6. NOT VERIFIED
- The full 3-sport night peak and the replay phase on tennis (killed at the lane cap by design).
- The exact recorded byte lengths of the killed step's inputs (proxy used, section 2).
- Whether the D+1 tennis rows and the as-of filter change the ~4.5 GiB projection materially (linear extrapolation from
  two 100,000-row marks; not run to completion).
Scratch: C:/Users/neelj/AppData/Local/Temp/claude/s806/ qmeasure.py, mkqview.py, q08_mlb*.jsonl, q08_nba*.jsonl, q08_tennis*.jsonl.
