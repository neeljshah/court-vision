# S516 live shadow fills candidate

CANDIDATE: 22/22 enumerated construct cases pass; independent verification pending.
Machine: local Windows laptop, Python fixture runs only. No capture archives were opened.
Before: 0/22 (modules absent). After: 22/22 enumerated cases pass, plus the extra B3/B4 regression tests, across five test files (16 + 5 + 11 + 7 + 1 passed per file). Bar: 22/22; no exclusions.
Candidate parent HEAD: ec50a3121e5ee08433be6c431c53d58acfaaedd1. Verification base: 586ec022422e6d8e5390d5fff0a47add546c14d8. DIFFER.
Candidate bytes are uncommitted; the file hashes below identify the implementation.

## Binding before-condition output (this session)
```text
docs/evidence/forward/live_shadow: ABSENT
docs/evidence/forward/markouts: ABSENT
data/cache/ingame_books_local/kalshi/mlb/2026-09-25.jsonl: ABSENT
data/cache/ingame_books_local/kalshi/mlb/2026-09-26.jsonl: ABSENT
2026-09-25 fixture: 7 rows; 5 snapshot, 1 trade_gap, 1 trade_backfill_closed
2026-09-26 fixture: 189 rows; 93 snapshot, 95 trade, 1 trade_backfill_closed
95 prints; 95 unique IDs; 0 created after receipt
created_min 2026-09-25T23:59:33.989274Z; created_max 2026-09-26T00:05:00.114289Z
lag_min 194.171501; lag_median 320.101313; lag_max 862.120317 seconds
max_trade_receipt 2026-09-26T00:13:56.109591Z
```
The full-shard probe is unavailable here. The copied fixtures match both Amendment 2 digests.
The markouts directory is absent here, rather than present and empty in the dispatch probe.

## Landed interfaces read before coding
```python
scripts.platformkit.execution.forward_replay_io.stamp(value: 'object') -> 'Decimal'
scripts.platformkit.execution.forward_replay_io.iso(value: 'Decimal') -> 'str'
scripts.platformkit.execution.tape_fill_sim.simulate_fills(quote_events: 'list[dict]', trades: 'list[NormalizedPrint | Refusal]', book_snapshots: 'list[dict]', params: 'dict') -> 'dict'
scripts.platformkit.execution.tape_fill_adapters.from_s341_trade(row: dict) -> scripts.platformkit.execution.tape_fill_adapters.NormalizedPrint | scripts.platformkit.execution.tape_fill_adapters.Refusal
scripts.platformkit.execution.tape_fill_adapters.NormalizedPrint(trade_id: str, ticker: str, ts: float, side: str, price: int, count: decimal.Decimal) -> None
scripts.platformkit.execution.capture_book_adapter.to_mark_tick(row: 'dict') -> 'dict'
scripts.platformkit.execution.fill_realism_markout.accept_fee(value: 'object', *, cumulative_increment: 'bool' = True) -> 'tuple[Decimal | None, str]'
scripts.platformkit.execution.markout_causal.resolve_marks(fill: 'Dict[str, Any]', ticks: 'Sequence[Dict[str, Any]]', horizons_s: 'Sequence[float]' = (30.0, 120.0, 300.0), max_wait_s: 'float' = 30.0, *, max_book_age_s: 'Optional[float]' = None) -> 'Dict[float, Dict[str, Any]]'
scripts.platformkit.execution.markout_causal.markout_strict(fill: 'Dict[str, Any]', mark: 'Optional[Dict[str, Any]]') -> 'MarkoutResult'
scripts.platformkit.execution.markout_causal.summary_strict(fills: 'Sequence[Dict[str, Any]]', ticks: 'Sequence[Dict[str, Any]]', *, horizons_s: 'Sequence[float]' = (30.0, 120.0, 300.0), max_wait_s: 'float' = 30.0, cluster_key: 'str' = 'game_id', n_intents: 'Optional[int]' = None, intents: 'Optional[Sequence[Any]]' = None, max_book_age_s: 'Optional[float]' = None) -> 'Dict[str, Any]'
scripts.platformkit.execution.fill_realism_io.MemoryGuard.__init__(self, ceiling: 'int' = 1073741824) -> 'None'
scripts.platformkit.execution.fill_realism_io.MemoryGuard.check(self) -> 'None'
```
Read S515 live_shadow_quoter.py, live_shadow_io.py and live_shadow_cli.py in full.
Landed difference: run and p0 records omit schema; arm records require live_shadow_v1.
The landed simulator decimal_fees option supplies authoritative exact fee strings; its legacy float field is discarded.

## Construct evidence and disclosures
Run A: 48 side-seconds; one through fragment; order means -0.005 at 60 s and 0.045 at 300 s.
Run B: mid 116 side-seconds, blend 58; mid three fragments / two filled orders / two contracts.
Run B NO order means -0.025 at 60 s and 0.055 at 300 s; YES 300 s mean -0.085.
Both arms remain INSUFFICIENT. Equality at 30 games removes that count label; no statistical claim is made.
Submit latency 2.0 s and cancel latency 1.0 s are assumptions; margin 1800 s is a declared constant.
Queue depth is unknown. queue_ahead_1 is a touch bound, not a measurement. The two passes stay separate.
queue_from_snapshot is omitted: the landed simulator has no per-order age cap; one shared snapshot list cannot enforce the 5 s limit for every order.
Per-ticker drains and overlapping gaps determine finality; global watermark is only a capture-liveness diagnostic.
The emitted_ts 60 s distinction is heuristic; late live rows are refused and replay rows stay in their own section.
Per-fill fee increments follow a cumulative ceiling. Zero increments are accepted only within an order with positive total fee.
Queue priority across re-quotes is not modelled. Marks use the stripped view; raw refusals remain diagnostics.
Partial mark coverage and unscored reasons remain explicit. Order-level means use quantity weights and total order fee.
Inventory policy independent_intent_zero is not a position history. No realized-outcome inference is made.
Fee schedule: venue_fees:kalshi-maker:2026-09-01:0.0175. Exact decimal representation and 24-hour expiry bounds refuse absurd inputs.
Dedupe signatures grow with served trade IDs; only window-bounded prints and marks are retained.
Atomic output retains a prior sidecar and receipt digest for recovery after interrupted publication.
Run A refusal counts (unit: named input/observation or quote-print diagnostic events): {"duplicate_trade_identical": 0, "mark_unstripped_refused:inconsistent_touch": 36}
Run A mark coverage (denominator: in-window snapshot rows): {"accepted": 68, "rows_in_window": 68}
Run A observation denominator: 4.

## Generated inventory (LF-normalized bytes; resolution JSONL or source text)
| Path | Bytes | Lines | SHA-256 |
| --- | ---: | ---: | --- |
| C:/Users/neelj/nba-harness-h181/scripts/platformkit/execution/live_shadow_fills.py | 12692 | 260 | 4256a3167812fb494d72c091482262681556ea06f98938172eedcc47250ae30b |
| C:/Users/neelj/nba-harness-h181/scripts/platformkit/execution/live_shadow_fills_books.py | 11757 | 261 | 4b59171979945a4eb5b1ec4e4258c16e5fd6aab5d2da7be7da41f8e67b0501c5 |
| C:/Users/neelj/nba-harness-h181/scripts/platformkit/execution/live_shadow_fills_io.py | 14301 | 278 | 3f89e62d511b18c410bf152ce5af06da8752d517e9fbc2dd623bb49dff918d6a |
| C:/Users/neelj/nba-harness-h181/scripts/platformkit/execution/live_shadow_fills_report.py | 11873 | 218 | 53980dc29ee8054115ed60a848ed69dd15b373fc7ee124e1cb88386548c12ac3 |
| C:/Users/neelj/nba-harness-h181/tests/platformkit/execution/test_live_shadow_fills.py | 17676 | 296 | 33c8935afde8e53433ad47c67e596f8a21c6e065caffd3c21d32eba24d0a96b0 |
| C:/Users/neelj/nba-harness-h181/tests/platformkit/execution/test_live_shadow_fills_b3.py | 10508 | 187 | 150c2bc3c7181a287a962c4bc5ea72af8846691dc6c00441b8b275267a1c02c8 |
| C:/Users/neelj/nba-harness-h181/tests/platformkit/execution/test_live_shadow_fills_b4.py | 3227 | 79 | ade4e87949b96806054156c689c385f8f089e29a2ed3194c30bd503149b2e997 |
| C:/Users/neelj/nba-harness-h181/tests/platformkit/execution/test_live_shadow_fills_io.py | 11801 | 201 | e07ee2e03a5d086e9df200ca65f9c9ab37f34042f704543e889606c5610d6f13 |
| C:/Users/neelj/nba-harness-h181/tests/platformkit/execution/test_live_shadow_fills_memo.py | 14542 | 154 | 02403ad5cc46711e05497b7966215c37f6d7c78eb5eb4b0bd9611f8474cf8efe |
| C:/Users/neelj/nba-harness-h181/tests/platformkit/execution/fixtures/s516_books_root/kalshi/mlb/2026-09-25.jsonl | 26743 | 7 | f4b1d560d6d7e1f167ac4c45120b0694e3a588ece26c3c3a60d4b2b0e13d7aeb |
| C:/Users/neelj/nba-harness-h181/tests/platformkit/execution/fixtures/s516_books_root/kalshi/mlb/2026-09-26.jsonl | 580622 | 189 | 0defb940aad16764669ea4ec03fe721ad2c08a13187e849949d6396e78e5edf9 |
| C:/Users/neelj/nba-harness-h181/tests/platformkit/execution/fixtures/s515_real_books.jsonl | 124926 | 26 | 3d8bcb29f85490542e7b4f23da78b6ebc9b22badfda07609ae7417995211e782 |
| C:/Users/neelj/nba-harness-h181/tests/platformkit/execution/fixtures/s515_real_schedule.json | 223 | 10 | bd48c732d9be7d4db9eb7e7706b6c5e4f3c7f1e1c63e9f526aa49dd3e97a6744 |
| C:/Users/neelj/nba-harness-h181/tests/platformkit/execution/fixtures/s515_real_state.jsonl | 13677 | 12 | 5558b08dcdfc76193dc80998c85050fea4395f6779c2eec3c0e719ac1d63e65f |
| C:/Users/neelj/nba-harness-h181/tests/platformkit/execution/fixtures/s516_seal.json | 1331 | 15 | b7b3ccd9a8619f552952dc1872bbccd278effcb2e7a8106f4acd91bf21a56446 |
| C:/Users/neelj/nba-harness-h181/.gitattributes | 2234 | 37 | fe57154c0a84efe90576bb6b581ec7000b0d46302c5388dfd134743840dd9d55 |

Per-case before/after: 1: 0/1 -> 1/1, 2: 0/1 -> 1/1, 3: 0/1 -> 1/1, 4: 0/1 -> 1/1, 5: 0/1 -> 1/1, 6: 0/1 -> 1/1, 7: 0/1 -> 1/1, 8: 0/1 -> 1/1, 9: 0/1 -> 1/1, 10: 0/1 -> 1/1, 11: 0/1 -> 1/1, 12: 0/1 -> 1/1, 13: 0/1 -> 1/1, 14: 0/1 -> 1/1, 15: 0/1 -> 1/1, 16: 0/1 -> 1/1, 17: 0/1 -> 1/1, 18: 0/1 -> 1/1, 19: 0/1 -> 1/1, 20: 0/1 -> 1/1, 21: 0/1 -> 1/1, 22: 0/1 -> 1/1.
Generated from inventory() and write_memo() in test_live_shadow_fills_memo.py; test outputs: ['16 passed in 2.18s', '5 passed in 5.60s', '11 passed in 1.29s', '7 passed in 8.69s', '1 passed']
LF attributes: tests/platformkit/execution/fixtures/s516_* text eol=lf; tests/platformkit/execution/fixtures/s516_books_root/** text eol=lf; docs/evidence/forward/live_shadow/* text eol=lf.
Validation: the five per-file pytest commands (-q -p no:cacheprovider), both CLI --help routes, and contract_preflight with the owned paths and S516 spec.
Preflight: final preflight includes this memo (see the fix-round report).

## FIX 1 (spec AMENDMENT 3, r1 Opus tier 2: 0 blocking, 5 SHOULD, 5 NOTE)
B3a time base: every receipt instant (need, watermark, ticker_drains, interval decision/submit/cancel/live_start/live_end, fill_ts, mark_ts) is an exact ISO UTC string; the integer ns stay as <name>_ns and assumptions.time_base = ns_after_<D>T00:00:00Z. Pinned by test_b3a_iso_time_base.
B3b one refusal per row: a row counted emitted_invalid is not counted again but still closes earlier orders. Pinned by test_b3b_one_refusal_per_row.
B3c shadow streaming: D+1 shadow rows are read only while a quote group is open and t <= D+1 00:10:00Z; run_meta records shadow_rows_read and shadow_bytes_read. Pinned by test_b3c_shadow_streaming.
B3d test gaps: pinned by test_b3d_case8_rates_and_blend, test_b3d_replay_nonce_and_zero_life, test_b3d_through_bound_checks, test_b3d_case7_trade_identity, test_b3d_case11_missing_next_books, test_b3d_case4_prefilter_nonserved, test_b3d_case6_through_across_passes, and the memo-table comparison in test_case22_inventory.
B3e labels: fill_rate_per_quote_hour.through is now fragments_per_quote_hour beside the per-order per-side rates; agreeing duplicate_run rows are report diagnostics (diag), only disagreeing ones stay refusals. Pinned by test_b3e_labels.
B3e omission (B1g): per-order simulate_fills calls with 5 s snapshot windows were possible and were not done; queue_from_snapshot stays omitted.
B3f sentinel: test_case19_vocabulary also rejects the bare integer 1000000.
B3g memo: NOT VERIFIED below records the measured live trade-tape lag and the orchestrator probe.
B3h probe rule: this lane ran no data probes; fixtures only.

## FIX 2 (spec AMENDMENT 4, r2 tier 1 Opus: 0 blocking, 3 SHOULD, 1 CORRECTION, 2 NOTE)
B4a section counters. Before (replay-only shard, one zero-life quote pair): top-level refusals {"zero_life_intervals": 2}. After: top-level {}, replay section_refusals {"zero_life_intervals": 2}, live section_refusals empty. zero_life_intervals, replay_stamped_rows, queue_unknown, markout_refused:* and through_bound_* now live in section_refusals (result key on the live section object and on replay). Pinned by test_b4a_section_counters_replay_only and test_b4a_receipt_sections.
B4b one refusal per row. Before (emitted_ts 2027-99-99 with a t_epoch in 2099): {"emitted_invalid": 1, "future_records": 1}. After: {"emitted_invalid": 1}. Pinned by test_b4b_bad_emitted_and_future_time_counted_once.
B4c day-D streaming. Before (generator of 30,000 quote rows): tracemalloc peak 81.6 MiB (visible-row list). After: 57.6 MiB, dominated by the 60,000 retained interval dicts; reduce_rows takes an iterator, pass 1 keeps run rows only (run_rows= second iterator, scratch counters), pass 2 keeps open-group state and intervals. Pinned by test_b4c_streaming_bound_30000_rows (bound 64 MiB). Full-night RSS remains UNVERIFIED.
B4d memo shas: write_memo runs git rev-parse for HEAD and master and prints EQUAL or DIFFER from the real values; tests never call git and compare only the inventory table and the header shape.
B4e exit codes. Before: an internal ValueError such as through_bound_exceeded went to parser.error (exit 2). After: exit 5 with the token on stderr; exit 2 only for invalid_date and invalid_arguments. Pinned by test_b4e_exit_codes.
B4f memo: the round-2 orchestrator re-probe is recorded under NOT VERIFIED.

## NOT VERIFIED
No live-night receipt, full-night RSS, per-ticker completeness in an actual night, or S515 live-run rows were exercised.
No network, pod, settlement data, full test suite, or production wiring was exercised. Fixture memory is not a full-night measurement.
The live trade tape was MEASURED (orchestrator, KXMLBGAME-26SEP291400PHIATL-ATL) to lag about 2 h during the game, so no live-night receipt can reach FINAL before the drain completes.
Orchestrator real-row probe (not repeated here): 20 real S515 rows and the real 09-29 books shard, rc 0, PROVISIONAL ticker_trade_incomplete, 0 input prints, peak RSS 27.1 MiB.
Round-2 orchestrator re-probe (real 09-29 rows, not repeated here): rc 0, PROVISIONAL ticker_trade_incomplete, peak RSS 27.3 MiB, ISO instants present, time_base ns_after_2026-09-29T00:00:00Z.
Round-3 orchestrator re-probe (real 09-29 rows, not repeated here): rc 0, PROVISIONAL ticker_trade_incomplete, 38 mid intervals, peak RSS 27.1 MiB.
FIX 3 (orchestrator, r3 tier-1 Opus REJECT on B4b): a bad-emitted p0 row is counted once (emitted_invalid only); shadow_track_unparsed moved to diagnostics (diag:) so a row never adds two refusals; reduce_rows refuses a one-shot iterator without run_rows (single_pass_iterator). Pinned by test_b4b_r3_bad_emitted_p0_counted_once and test_b4c_r3_single_pass_iterator_refused.
B4c: rss_within_bar is measured only for fixtures and the 30,000-row tracemalloc bound; a full-night peak RSS is UNVERIFIED until the orchestrator measures one.
Independent verifier acceptance and a sandbox commit remain pending.
