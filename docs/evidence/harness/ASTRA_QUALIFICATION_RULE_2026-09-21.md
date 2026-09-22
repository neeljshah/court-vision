# Forward qualification rule as proposed by the astra design lane (2026-09-21)

Archived verbatim by the orchestrator. The FROZEN version, with one recorded deviation (90 percent / 480 decisions instead of 95 / 600, decided before any forward game was examined), is AMENDMENT 2 of docs/evidence/tracking/specs/S362_spec.md.

Freeze and commit this rule before examining any forward game. Thresholds are inclusive. Qualification is score-blind.

1. Per DECISION: At availability time t, require book receipt age <=5 seconds and state receipt age <=15 seconds, both nonnegative. Use response_end_ts; future records are invisible. Require exact game linkage, an adapter-accepted two-sided book with required touch sizes, live state and valid reservation. A refused snapshot cannot refresh the book timestamp. Any failure causes abstention and increments every applicable reason count. BOOK_ONLY_ABLATION cannot qualify.

2. Per GAME: Use one prospectively selected canonical ticker and the fixed observation window [scheduled_start, scheduled_start+3600 seconds). The denominator is all 3600 wall-clock seconds, including stoppages, missing capture and delayed starts; never trim to available records.

Require >=95% time coverage and >=600 qualified decisions using distinct accepted book receipts. A qualified decision covers time from its receipt until the earliest of the next decision, book freshness expiry, state freshness expiry, reservation expiry, observed invalidation or window end. Merge overlapping intervals; uncovered time remains in the denominator. Duplicate records create neither additional decisions nor coverage.

Retain book receipt-gap median <=45 seconds, p95 <=90 seconds and maximum <=120 seconds. Require maximum state receipt gap <=30 seconds. Measure gaps between usable receipts, including uncovered leading and trailing window boundaries; absent streams have a 3600-second gap. Use nearest-rank quantiles.

Any positive-duration overlap with a declared trade_gap or host_gap disqualifies the entire game; this prevents informative outages from improving coverage through denominator removal. Require successful trade pagination through the window's closing watermark; unresolved completeness disqualifies. Quiet tape is valid.

Zero-fill games qualify when these requirements pass and count toward coverage and game totals. They contribute no fill-conditional measurement. Mark availability does not determine game qualification: subsequent authorized analysis qualifies 30/120/300-second horizons independently using the first same-ticker observation within [fill+h, fill+h+30 seconds].

3. Per SPORT-WEEK: Require >=4 distinct qualified games within each frozen sport/family stratum per complete ISO week, Monday 00:00 UTC through the following Monday. Assign games by scheduled start. Fewer than 4 breaks that family's eight-week streak; no pooling across sports or stitching missing weeks. Preserve the separate floors of 30 qualified games per sport and 30 fill-bearing games before interval adjudication.

4. FAILED games: Publish FAIL, integer diagnostic counts, covered/total milliseconds, and all applicable reason codes: BOOK_STALE, STATE_STALE, ADAPTER_REFUSED, LINKAGE_INVALID, NOT_LIVE, RESERVATION_INVALID, COVERAGE_LOW, DECISIONS_LOW, BOOK_CADENCE, STATE_GAP, TRADE_GAP, HOST_GAP, TAPE_INCOMPLETE. Compute no losses, fill rates, markouts or fee-adjusted measurements. Retain failed games in scheduled denominators.

The 95% coverage requirement is most likely to be regretted: 4-5% inconsistent-touch refusals nearly exhaust its allowance before scheduler jitter. Nevertheless, observing a forward game makes relaxation retrospective selection. Improve capture prospectively; an unmeetable bar remains CLOSED AT LIMIT under Q3.
