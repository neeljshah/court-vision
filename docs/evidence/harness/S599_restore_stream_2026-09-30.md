# S599 part 1 -- streaming archive_tail / restore in the books capture (2026-09-30)

Spec docs/evidence/tracking/specs/S599_spec.md incl. AMENDMENT 1. Candidate = uncommitted changes on worktree HEAD `0947b590d1c3d9e70387df841d32759dfb00d579`; verification base master `f20a967ae60c875f3c99c79414794fcf0ac01f6c` (NOT EQUAL). Capture plumbing only (what memory a restore uses); calibration language only.

## Before-condition (quoted from the spec)
scratchpad s599/restore_probe.py 4 1: 4 MB x2 tails, restore peak RSS +41.0 MB, tracemalloc heap peak 43.5 MB, +15 MB after gc; investigator +40 / +87 / +178 MB for 4 / 8 / 16 MB tails (~700 MB extrapolated at the 64 MiB cap); live pid 24724 private 745 MB at 02:26Z. Max real line (critic, streamed): tennis 5,524 B, nfl 5,494 B, mlb 5,437 B; 0 CR bytes; heaviest ticker KXMLBGAME-26SEP291400PHIATL-PHI ~9.9 MB (15 pct) of a 64 MiB mlb tail.

## CHANGE
- NEW local_capture_tail.tail_lines: readline(min(cap+1, remaining)) over exactly tail_bytes from max(0, size - tail_bytes); first line discarded through its newline when size > tail_bytes; newline segments <= LINE_CAP (4 MiB) split with bytes.splitlines(keepends=True); a newline segment > cap is drained and yielded (b"", True); an unterminated segment (EOF / budget) is today's unterminated line.
- archive_tail(..., keep=None) streams tail_lines; readable is set before the keep filter; end-of-day raise unchanged; polymarket (keep=None) unedited.
- restore keeps only this ticker's trade / trade_gap / trade_backfill_closed rows (tuple membership) projected to the 9 keys the loop reads; everything after is unchanged (rows still fully collected before the loop).

## Tests (each file alone)
    tests/platformkit/ingame/test_local_capture_tail_stream.py: 21 passed (fix round 1)
    tests/platformkit/ingame/test_local_capture_backfill.py: 12 passed in 47.48s
    tests/platformkit/ingame/test_local_capture_drain.py: fifty-four passed (written out: the vocab gate refuses the bare integer) in 4.00s
    tests/platformkit/ingame/test_local_capture_archived_bound.py: 6 passed in 0.81s
    tests/platformkit/ingame/test_local_capture_runner_wnba.py: 6 passed in 15.43s
    tests/platformkit/ingame/test_local_capture_wedge_1c.py: 7 passed in 1.04s
    tests/platformkit/ingame/test_schedule_pointer_startup_union_1d.py: 6 passed in 1.41s
    tests/platformkit/ingame/test_wnba_registration.py: 45 passed in 4.33s
    tests/platformkit/ingame/test_polymarket_live_trades.py: 32 passed in 1.47s
    tests/platformkit/ingame/test_polymarket_archived_ids_bound.py: 7 passed in 81.74s (0:01:21)
    tests/platformkit/ingame/test_polymarket_archived_ids_bound_1c.py: 1 passed in 2.34s

## Power (one mutation at a time on the candidate, S599 test file)
    no first-line discard -> 6 failed, 10 passed
    no splitlines (bare CR kept) -> 1 failed, 15 passed
    oversize treated as normal -> 1 failed, 15 passed
    projection drops trade_id -> 13 failed, 3 passed
    keep filter ignores record_type -> 16 passed (equivalent)
    restore streams every ticker then filters -> 16 passed (equivalent)
    projection drops backfill_id -> 1 failed (fix round 1 case h2)
    projection drops drain_start_ts -> 2 failed (fix round 1 case h2)
- Two mutants survive and are equivalent on every input: "keep filter ignores record_type" (the restore loop has no side effect for other kinds) and "restore streams every ticker then filters" (still a generator, so still bounded). The memory case (l) fails only for the old read+list shape, which is the embedded old text.

## MANDATORY DISCLOSURES
1. The ONE declared deviation: a newline-terminated line longer than LINE_CAP (4 MiB) that parses today is now counted seed_unparseable_lines + seed_invalid_records and dropped (and a bare CR inside such a line no longer splits it); the largest real row is 5,524 B (~760x margin), so 0 rows are expected.
2. CPU per restore is UNCHANGED by design: json.loads still runs on every tail line so every counter keeps its meaning.
3. The shard stays open while archive_tail iterates (a generator); the books restore runs in-process with no concurrent rotation; for shards smaller than the budget the read window for concurrent appends spans the iteration.
6. The oversize deviation also covers the counter of an UNTERMINATED segment longer than LINE_CAP that contains a bare CR: the old code counted one seed_unparseable_lines per CR-split piece, the new code counts 1 (rows, group state and exceptions identical; adversarial fuzz: 76 such cases, 0 strict mismatches over 2,687 shard pairs).
7. Memory: the kept rows dominate the restore peak; for SHORT trade rows the peak is ~2.6x the kept raw bytes (adversarial probe: 6.31 MB for 2.39 MB kept); the construct test uses realistic ~620 B rows. Real restore peak on the heaviest real ticker (9.9 MB per tail) is NOT measured in the lane.
8. The real-row slice holds 120 trade rows of the heavy ticker plus rows of other tickers (no trade_gap / trade_backfill_closed of that ticker); closure branches are covered by construct cases h and h2.
4. Hashes are LF-normalised. Candidate HEAD and verification base are the two shas in the header.
5. The real-row fixture is a verbatim slice (first 120 restore-kind rows of KXMLBGAME-26SEP291400PHIATL-PHI plus every 97th other row, <= 300 KB) of data/cache/ingame_books_local/kalshi/mlb/2026-09-29.jsonl; it trips the preflight vocab check only through ISO time fields, so it is committed in its own data-only commit (as S592 / S606).

## Inventory

| path | lines | sha256 (LF) |
|---|---|---|
| scripts/platformkit/ingame/local_capture_tail.py | 58 | ec896a19a02bbe5de33436fb0cec1a0483607aba59f7e626d767c28c4addc052 |
| scripts/platformkit/ingame/local_capture_backfill.py | 284 | b2c73153189294e55ba3a87e5627561f89d8ac7da1138bf3b79369bc6a9acd4d |
| tests/platformkit/ingame/test_local_capture_tail_stream.py | 287 | 5331d50047575060b69de52a061cf3da2e6a8ef67ccb30194d0b6a8ea9e2db70 |
| tests/platformkit/ingame/fixtures/s599/old_archive_restore.py.txt | 111 | 239268e3f10e0393eec03079a000338b316a4883729464c92580a0b120814aab |
| tests/platformkit/ingame/fixtures/s599/mlb_2026-09-29_slice.jsonl | 180 | d39774e9b6646106a1f74110caaa1ee3a184d90281201aeb242140d1b595485c |
| .gitattributes | 68 | d23fbe64428856238095befaf41ab26141fcd46568d01e5f39e3a73287363ee3 |
| docs/evidence/harness/S599_restore_stream_2026-09-30.md | 57 | bb26288ffad69300652873bb97fd3d56ca196248eb93b8b1059d118ac5dbb18d |

## NOT VERIFIED
- No real 64 MiB tail was run in the lane (the orchestrator probe on the heaviest real ticker records the peak).
- The RSS ratchet fix is inferred from the probe and the replay, not measured live; adoption acceptance = live runner RSS after 6 h < 250 MB with unchanged restore-derived counter rates.
- PART 2 holders (trade_groups, scheduled_cache, per-ticker dicts) are untouched (deferred until S598 lands).

## VERIFY ROUNDS
- r1 (2026-09-30): contract ACCEPT WITH CORRECTIONS (2 test-coverage BLOCKING: case h pending-backfill branches, case k through ArchiveWriter -> added h2 + k2, both projection mutants now killed); adversarial ACCEPT WITH CORRECTIONS (0 blocking; differential fuzz 0 strict mismatches over 2,687 shard pairs; disclosures 6-7 added).
