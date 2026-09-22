GAP S373 | sport all (maker channel) | worktree harness-h31 (master-based) | log cx_s373
# ONE adapter from captured book rows to the three downstream schemas (audit finding 4)

OWNED FILES (NEW): scripts/platformkit/execution/capture_book_adapter.py, tests/platformkit/execution/test_capture_book_adapter.py,
tests/platformkit/execution/fixtures/s341_real_snapshots_2026-09-21.jsonl (the orchestrator copies 6 verbatim public snapshot rows
into the worktree before dispatch). No landed module is edited.
DEFECT (audit, reproduced): a real captured book row (fields response_end_ts, yes_bid, yes_ask, no_bid, no_ask, raw_market with
fixed-point strings, book ladders) yields missing_book_clock from the quote engine (it wants src_ts / best_bid_cents /
best_ask_cents), feeds nothing usable to tape_fill_sim book_snapshots, and gives no_tick_in_window in the markout (it wants src_ts
+ yes_home_prob). Nothing connects the capture to the chain.
CHANGE: capture_book_adapter exposes three pure functions over ONE captured snapshot row, all Decimal, all using response_end_ts as
the availability clock (timezone-aware, parsed with venue_time.parse_venue_time): to_quote_book(row) -> {best_bid_cents,
best_ask_cents, src_ts}; to_fill_snapshot(row) -> the book_snapshots shape tape_fill_sim reads, with displayed size at each level
from the ladder and at the touch from raw_market yes_bid_size_fp / yes_ask_size_fp (strings -> Decimal); to_mark_tick(row) ->
{src_ts, ticker, game_id when supplied, yes_home_prob = mid as a probability, book_age_sec = 0 at capture}. The YES / NO mapping is
explicit and tested (a NO bid at p is a YES ask at 100 - p); a one-sided, crossed or locked book, a missing clock, a non-finite or
out-of-range price returns a refusal with a reason -- never a guessed mid. Every fixture row must convert without refusal unless
it is genuinely one-sided, and the test asserts the refusal reason in that case.

AUTHORITY: docs/evidence/harness/AUDIT_EXEC_CHAIN_2026-09-21.md (quote the finding text in the memo). RULES: EDIT ONLY the row-owned modules named above (all were created on
2026-09-21 by this program; the module edits are REQUIRED -- this is NOT a tests-only row) plus their test files; never edit
venue_fees.py, executor/lifecycle.py, paper_maker.py or any other pre-existing module. Keep every public signature and every
existing reason code byte-compatible; ADD fields, never rename (contract B2). Re-run each reproduction from the audit FIRST and
quote it failing, then show it fixed. Construct / fixture tests only; no real archive, no network, no measured number.
ACCEPTANCE: every per-file test of every touched module passes, run one file at a time; each file <= 300 lines. Vocabulary
follows contract Q6; automated scan required; assemble retracted-figure literals from single digits. The memo
docs/evidence/harness/S373_capture_book_adapter_2026-09-21.md ends with a NOT VERIFIED list. The pod is OFF.
