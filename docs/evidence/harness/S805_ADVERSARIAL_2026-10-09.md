# S805 adversarial tier (2026-10-09, PAPER ONLY)

Tier: one Opus subagent; mutants in its own scratch copy (C:/Users/neelj/AppData/Local/Temp/claude/s805_adv/), every pytest
through gate.py, one at a time. Candidate HEAD 5cf856028 (code commit abdc3b9f1), base 0666dbc99.

## Round 1 -- verdict and table (verbatim, condensed)

ACCEPT WITH CORRECTIONS

Baseline green: s805 5, forward_capture_stream 36, stream_integration 8, qualification_daily 31. After all 15 mutants the md5s
of forward_capture_slim, forward_capture_stream and forward_capture_stream_sql match the candidate.
| id | mutant | result | first killing test |
|---|---|---|---|
| N1 | slim drops http_status | killed | s805 equals_landed |
| N2 | slim drops scheduled_start_utc | killed | s805 equals_landed (+26 fcs, +2 integration) |
| N3 | slim drops _refusal | killed | s805 equals_landed (+3 fcs) |
| N4 | slim drops date | killed | s805 equals_landed (+26 fcs, +3 integration) |
| N5 | sharing key ignores type (True vs 1) | killed | s805 slim_keeps_only... |
| N6 | Decimal counted as plain (shared) | killed | s805 slim_keeps_only... |
| N7 | invalid counts also set to 0 | killed | s805 equals_landed |
| N8 | copy _refusal only when the full row lacks one | SURVIVED | changes output (preset 5 stays int, landed writes "5") |
| N9 | zip not strict, last slim row dropped | killed | s805 equals_landed (+28 fcs, +3 integration) |
| N10 | copy-back removed | killed | s805 refused_rows_of_a_linked_game... |
| N11 | sharing key ignores home_abbr | killed | s805 equals_landed (+1 fcs) |
| N12 | presence not kept | killed | s805 refused_rows... (+23 fcs, +3 integration) |
| N13 | COUNTED drops "pages" | SURVIVED | changes output (invalid pages links instead of invalid_count) |
| N14 | sharing key ignores _refusal | killed | s805 equals_landed (+3 fcs) |
| N15 | sharing key ignores scheduled_start_utc | killed | s805 equals_landed; metadata_conflict |
Findings: (1) N8 and N13 are test gaps that change output; constructs [state(0), state(1,_refusal=5), state(2,_refusal=["x"]),
state(3,_refusal=True)] and [state(0), state(1,pages=-1), state(2,pages="3"), state(3,pages=True)] pass on the candidate and fail
under the mutants; an invalid "count" has the same exposure. (2) Real-bug hunt: none. Four compare() constructs (the two above,
falsy preset refusals "", 0, None, False, shared twins mixed with refused twins) pass on the candidate and on master. _links reads
only READ + COUNTED; its only state-row mutation is the _refusal annotation; an annotated shared row re-raises the same string on
its next visit; pass 2 reads native with the same ORDER BY while store.output writes another table.
Scratch: tree/tests/platformkit/execution/test_adv_s805.py, work/n.log, work/mut5.py.

## Builder response (fix round 1, tests only)
Added test_preset_non_str_refusals_are_stringified_as_the_landed_loader (5 / ["x"] / True) and
test_invalid_pages_and_count_are_refused_as_the_landed_loader (pages -1 / "3" / True, count -2 / 1.0: invalid_count 5).
Re-applied N8: 1 failed; N13: 1 failed; restored: 7 passed.

## Round 2 (head f96b4e6ab; no code change since abdc3b9f1) -- verbatim verdict, condensed
ACCEPT. All 15 mutants killed; baseline s805 7 passed, forward_capture_stream 36 passed; code md5s restored after the run.
s805 / fcs failures per mutant: N1 3/0, N2 5/26, N3 3/3, N4 5/26, N5 1/0, N6 1/0, N7 4/0, N8 1/0 (KILLED new:
test_preset_non_str_refusals_are_stringified_as_the_landed_loader), N9 5/28, N10 3/0, N11 2/1, N12 3/23,
N13 1/0 (KILLED new: test_invalid_pages_and_count_are_refused_as_the_landed_loader), N14 3/3, N15 2/0. Log s805_adv/work/n2.log.
