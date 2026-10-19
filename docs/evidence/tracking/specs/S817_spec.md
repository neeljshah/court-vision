# S817 -- the issue scanner's sibling per-line reads refuse a record nested past the decoder limit (PAPER ONLY)

## Premise (measured 2026-10-13 21:5xZ on master 1a897a4e3, read-only, Python 3.10)
- Eight per-line `json.loads` catches in five scanner modules omit RecursionError (found by the S816 contract tier,
  S816_RESULT NEW GAP): paper_desk_issue_checks.py:264 (`_tick`, tick journal; ValueError, TypeError, AttributeError),
  paper_desk_issue_offday.py:25 (`_census`, the output_tail's last line; ValueError only) and :60 (`_scan`, journal;
  ValueError, TypeError, AttributeError), paper_desk_issue_refusals.py:73 (`check`, journal; + KeyError),
  paper_desk_issue_tick.py:30 (`valid`, journal; ValueError, TypeError, AttributeError), paper_desk_issue_capture.py:113
  (`configured_sports`, the desk config; OSError, ValueError, TypeError, KeyError, IndexError, AttributeError), :145
  (`outages`, supervisor journal; ValueError, TypeError, KeyError) and :250 (`coverage`, state shard tail; same tuple).
- `json.loads("[" * 10000 + "0" + "]" * 10000)` raises RecursionError. These files are written by OTHER processes
  (the tick, the supervisors, the state capture, the owner's config), so unlike S816 the input is realistic. Today the
  RecursionError climbs to `Context.guard` / `scan()`'s per-check `except Exception`: the whole check (obligations,
  tick_silent or capture) becomes scan_check_error FAIL with its PASS verdicts downgraded to UNKNOWN, instead of one
  counted bad line. offday and refusals run under the obligations guard (checks.py:297-300 call off_day / refusal_keys);
  off_day also runs under the d1 guard (`_d1`, checks.py:226), so one deep off-day journal line failed d1 as well
  (adversarial tier probe p5 on master: check_errors 4 = tick, tick_silent, refusal_keys, d1).
- NOT a site: paper_desk_issue_refusals.py:47 re-parses a detail file that `ctx.read` (S815 catch) has already accepted,
  so a deep detail file never reaches it.

## Change (owned files only; one token on one line per site, no new line in the 300-line modules)
- RecursionError joins the except tuple at each of the eight sites, so the deep record takes the branch the site already
  defines: `_tick` journal_bad_lines +1; `_census` returns None (the caller counts offday_unclean_census); `_scan` bad +1
  (offday_journal_bad_lines); refusals `continue` (counted by `_tick` on the same lines); tick `valid` None
  (tick_silent_bad_lines +1 in `check`); `configured_sports` scope_config_unreadable +1 and the S735 fallback tuple;
  `outages` journal_bad_lines +1; `coverage` coverage_bad_rows +1 and incomplete (verdict UNKNOWN).
- NEW tests/platformkit/ops/test_paper_desk_issue_s817.py: the decoder premise plus one 10,000-deep case per site, each
  asserting the counted reason AND, where a later line exists, that the row after the deep line is still read.

## Clauses
- V1 The fixture overflows json.loads itself (pytest.raises RecursionError) -- the tests have power.
- V2 `checks._tick` over [deep line, one tick_ok row]: journal_bad_lines 1 and tick_refused tick PASS.
- V3 `offday._census` on a deep output_tail returns None; `offday.off_day` over a deep journal/<day-1> line returns None
  with offday_journal_bad_lines 1.
- V4 `refusals.check` over [deep line, one night row with an unlisted key]: step_refusal_key night/<key> emitted.
- V5 `tick.valid` on the deep line is None; `tick.check` over [deep line, one tick_ok row]: tick_silent_bad_lines 1 and
  tick_silent PASS.
- V6 `capture.configured_sports` on a deep config returns ("mlb", "nfl") with scope_config_unreadable 1; `capture.outages`
  over a deep supervisor journal line counts journal_bad_lines 1 and emits nothing; `capture.coverage` over a deep state
  row counts coverage_bad_rows 1 and emits served_coverage_gap UNKNOWN.
- V7 Every site test fails on master's modules (the RecursionError escapes there); the premise test passes on master.
  Every other except-branch behaviour is unchanged; the five modules keep their line counts (checks and capture at 300).
- V8 No money or return language; PAPER ONLY.

ACCEPTANCE RULE: V1-V8 all hold on the branch diff + per-file test output (worktree and main).

## AMENDMENT 1 (2026-10-14 16:3xZ, paper-desk-improve run; folded from the cloud pre-build critic of cloud/S817-2026-10-12)
- Site (9) added: paper_desk_issue_refusals.py `_detail_refusals` second read (`strict_json(path.read_bytes()...)`, except
  OSError, ValueError at the sha check). The premise exclusion above ("NOT a site") holds only while the detail file is
  unchanged between `ctx.read` (S815 catch) and that second read; a file rewritten deep in between reaches the second read
  unguarded and the RecursionError escapes `_detail_refusals` into the refusal_keys guard. Change = the same one token;
  the deep rewrite takes the existing failed-read branch (data None -> detail_sha_mismatch +1, return None).
- V6a: `refusals._detail_refusals` with `ctx.read` returning a valid detail and the on-disk file rewritten deep (sha of the
  deep bytes carried by the row) returns None with detail_sha_mismatch 1. V7 reads "nine" sites; the premise run on
  master's modules is expected 9 failed / 1 passed. Every other clause unchanged. ACCEPTANCE RULE: V1-V8 incl. V6a.
- Provenance: cloud/S817-2026-10-12 (59c7bcc5b; cloud result + verify memos ACCEPT, Python 3.10.20 and 3.11.17) covers the
  same nine sites; this laptop landing supersedes that branch (cloud-lander disabled since 10-01), credited in the memo.
