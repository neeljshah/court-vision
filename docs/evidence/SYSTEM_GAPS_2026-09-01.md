# System gap register -- 2026-09-01 -- **SUPERSEDED, HISTORICAL INDEX ONLY**

**DO NOT WORK FROM THIS FILE.** As of 2026-09-03 every live row here is tracked
in `docs/evidence/HARNESS_GAPS_2026-09-03.md` as an S-row, and the S-row is the
one with the acceptance rule. This file is kept because the H/X/A/D ids are cited
by a dozen memos and by MASTER_ROADMAP section 2; it is the decoder ring, not the
queue. It was leaving OPEN statuses on rows already being worked as S-rows, which
is how the same gap gets built twice.

MAPPING (audited 2026-09-03; deliberately NOT one-to-one):

| here | S-row | note |
|---|---|---|
| X01 | S19 | request governor |
| X02 | -- | CLOSED, honest REJECT; no S-row by design |
| X03 | S20 | THE KEYSTONE |
| X04 | S21 | premise re-scoped: the G15b/G29b/G01c deploys are DONE (ledger G14b); G08 and later are outstanding |
| X05 | S06 (S18 reads its memo) | folds into the stacker |
| H01 | S02 **and** S03 | one H-row, two S-rows (soccer, tennis) |
| H02 | S06 | |
| H03 | S05 | |
| H04 | S04 | also tracking row G16, now SUPERSEDED BY S04 |
| H05 | S07, S08 **and** S09 | one H-row, three S-rows |
| H06 | S10 | |
| H07 | S01 | |
| A01 | -- | MEASURED; no S-row by design |
| A02 | S22 | |
| A03 | S23 | |
| A04 | S24 | |
| A05 | -- | CLOSED |
| D01 | S25 | |
| D02 | S26 | dependency marker |
| -- | S11-S18, S27, S28, S29 | new; no H/X/A/D antecedent |

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
| H01 | soccer + tennis cannot enter backtest_runner. **PREMISE CORRECTED 2026-09-03**: "no games.parquet" is FALSE -- gate-ready corpora exist for all four sports at `data/cache/combo/gate_corpus_<sport>.parquet` (verified row counts: soccer 25,834, tennis 41,886, mlb 38,809, nba 1,814). They lack a market CLOSE column, not a corpus. H01 is a close JOIN | one join module (S02/S03), not a corpus build | SUPERSEDED by S02 + S03 |
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

Order: SUPERSEDED. The live order is the S-order in
`docs/evidence/HARNESS_GAPS_2026-09-03.md` and MASTER_ROADMAP section 2:
S01, S02, S03, S04, S05, S06; S19 and S20 in parallel from day 1; then S07, S08,
S09, S13, S10, S11, S12, S15, S16, S21-S24, S17, S14, S18, S25-S27, with S28/S29
as week-1 fillers. The old line above (X01, X04, H04, H01, H02, D01, H03, H06)
is kept only to show what changed; do not follow it.
