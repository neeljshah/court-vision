GAP S273 | sport mlb (in-game) | worktree a17 | log cx_s273_mlb_ingame_latency_screen
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: successor to S213 (latency ledger: MLB p50 41.0 s / p90 102.0 s, GUMBO captured_at - ts, 40,291 paired
  ticks/90 game clusters, 91.539248 pct coverage; NBA/WNBA/soccer/tennis NOT MEASURABLE, no captured_at). The
  orchestrator's own allocation named "S208/S209" as the MLB corpus, but S208 is verified to be the NBA
  phase-recal row -- corrected here to S209's archive re-score (33,920 evaluated ticks/11,087 informative/127
  informative game clusters, s88_phase_recal_2026-09-04.csv) and its sealed successor S254 (47,104 evaluated
  ticks/14,611 informative/158 game clusters, data/cache/ingame_grade_joined, 505 JSONL files, machine
  C:\Users\neelj\nba-track-a13 -- NOT present in this repo's data/, so this row verifies presence on its run
  machine first). Route: scripts/platformkit/ingame/s254_mlb_phase_recal_fwer_sealed.py, whose states() builds
  state_ts from each row's `ts` field (:74).
PREMISE (step 0, INFORMATIONAL): print S213's p50/p90 (41.0/102.0 s); print S254's denominators
  (47,104/14,611/158) from its committed summary JSON; confirm ingame_grade_joined is readable on the run
  machine, else STOP and report FALSIFIED per Q8.
CHANGE (step 1): additive; three arms of the identical S254 route (same buckets, embargo, splits, code
  byte-identical) differing ONLY in one shift applied to `ts` before `state_ts` is built: none (no delay), +41.0
  s (p50), +102.0 s (p90) -- shifting the STATE side later relative to price, never the reverse. Seal a prereg
  FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show :<path>,
  verified with git show HEAD:<path>) fixing the three delays and the unchanged bucket/embargo/split design.
  Score all three through cpcv_evaluate (scripts/platformkit/eval_gate/cpcv_engine.py) with purge and the
  existing symmetric embargo; report the pooled BH-survivor count and the largest single-bucket delta for each
  arm. Never write data/registry/, never flip a flag; S254's own artifacts untouched (new dated filenames only).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = pooled 15-bucket BH-survivor count and largest single-bucket delta (Brier incumbent minus
                  candidate) with game-clustered 95 pct CI, for each of the 3 arms (none / p50 / p90)
  before        = S254 (no-delay, already sealed): BH survivors 0 of 15, largest raw delta +0.015260 (late|
                  leading_big, BH p 0.311641, NOT_REPLICATED)
  bar           = all 3 arms reported with an identical 15-row bucket table; "the near-null improvement does not
                  grow at either delay" or "the p90 arm's largest delta and survivors are <= no-delay's" is a
                  valid SUCCESS, including "vanishes"
  n             = >= 30 game clusters per arm (158 available per S254), printed per arm
  eye check     = n/a (S-row); reproduction = verifier reruns all 3 arms from the sealed seed and diffs every
                  bucket
  must not move = S254's summary.json/paired_loss.csv, its bucket/embargo/split design, the +0.004 bar;
                  backtest_fwer.jsonl untouched, K unread, nothing charged
NON-TAUTOLOGY: all 15 buckets reported for every arm, incl. ones already NO_CHANGE at zero delay; a shrinking
  survivor count alone is not evidence (S254 already has 0 survivors) -- the comparison is the largest delta.
EVIDENCE: docs/evidence/harness/S273_mlb_ingame_latency_screen_2026-09-04.md + summary JSON + 3 paired-loss CSVs.
TEST: one per-file test asserting the ts-shift function adds exactly the named delay to one fixture row.
REPORT: 3-arm bucket table, largest-delta comparison, RSS, test line, SHA. No push. NEVER PARK.
