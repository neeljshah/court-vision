# System gap register -- 2026-09-01 (living; one gap = one lane; tracking gaps live in tracking/TRACKING_GAPS_2026-09-01.md)

Frame: the program is problem-finding. Each row names a gap, the measured
state, the LIMIT achievable with what we have (broadcast footage, public feeds,
our corpora), and the artifact that closes it. Calibration language only.

## Execution (in-game, prediction markets)
| id | gap (measured) | limit with what we have | status |
|----|----------------|-------------------------|--------|
| X01 | book capture pass wall ~105 s at 9 games x 2 sides vs 5 s target (governed orderbook fetches ~3.6 s each) | ~10 s with a request governor + parallel per-market fetch; 5 s needs fewer sides or a stream | OPEN (capture live since ticker fix 366b10038) |
| X02 | EVENT_REACTIVE unreachable: feed lag p90 28.9 s vs 5 s gate; venue ahead 95.6 pct; src_ts coverage 100 pct | slow-state maker quoting is the ceiling on public feeds; event-reactive needs a faster source | MEASURED, honest REJECT (dc82fdce3) |
| X03 | maker pool EMPTY; forward CLV series has 0 settled rows locally | needs the paper-live week on the pod (one-writer node) | OPEN |
| X04 | daemon/pod code lags master (gumbo poller, tennis adapter); daemon restart pending after G02/G03 | deploy discipline: git-archive + md5 check + restart runbook | OPEN |
| X05 | Hedge combiner trails its best arm; E4 AHEAD is guard-dominated (+0.0257 of +0.0296) | combination value must come from a nested-CV stacker, not online Hedge | MEASURED (c75b60074) |

## Harness / quant
| id | gap | limit | status |
|----|-----|-------|--------|
| H01 | soccer + tennis cannot enter backtest_runner (no games.parquet; soccer odds totals-only; tennis decimal p1/p2, ATP-only spine, WTA disjoint) | derived games.parquet + decimal-aware devig + totals runner | OPEN |
| H02 | no nested-CV stacker / meta-learner over arms with PBO printed | one module, one charged trial | OPEN |
| H03 | no per-regime isotonic recalibration with reliability bins + max-loser-WP (expert feedback) | one module | OPEN |
| H04 | teacher->student gate (student beats player-id fixed effects OOS) is a rule, not code | one module; prerequisite for any "tracking improved a model" claim | OPEN |
| H05 | S2 tier: prospective-first ledger primacy, replication-as-gate mechanical, gate-manifest staleness blocks claims | spec exists in NOW.md | OPEN |
| H06 | MLB frozen corpus 2010-2021 vs mechanism ingredients 2022+ -> all 22 MLB mechanisms NOT_TESTABLE | rebuild the MLB trial corpus on 2022+ games+odds | OPEN |
| H07 | run_gap_arms_real_corpus _BASELINE_TICKS 144,424 matches nothing on disk (52,558 real) | one-line fix + test (PROPOSED in E4 result memo) | OPEN |

## Analytics / intelligence
| id | gap | limit | status |
|----|-----|-------|--------|
| A01 | 27/27 NBA mechanisms wired: 0 AHEAD of close pregame (expected); value must be in-game + player grain | pregame = match the close; in-game conditioning is the lane | MEASURED |
| A02 | soccer 0/15, tennis 0/23 mechanisms wired (blocked by H01) | after H01 | OPEN |
| A03 | harness_health MCP artifact has no generator; strength_atlas fix needs server restart; P1/P2 gated diffs need human | small | OPEN |
| A04 | artifact refresh has no scheduler (fleet_on false) | one cron/loop entry | OPEN |
| A05 | README/packet claim rows reconciled (103,048 generated / 101,864 provenance-verified); "verified" = arithmetic, not accuracy | keep the caveat everywhere the number appears | CLOSED (20c1cd3a9) |

## Corpus / data
| id | gap | limit | status |
|----|-----|-------|--------|
| D01 | ingest accepted junk across sports; census + quarantine shipped; legacy queue items never re-gated | re-run content gate on every queued item | OPEN (G01) |
| D02 | called-pitch CSV cached (66,665 rows) but command_target columns need video -> framing gate NOT_TESTABLE | closes only via baseball METRIC_LOCAL + command_meter | OPEN |

Order: X01, X04, H04, H01, H02, D01, H03, H06.
