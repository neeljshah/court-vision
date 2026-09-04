GAP S239 | sport all | worktree aXX | log cx_s239_clv_countdown_metric
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: quant_principles_2026-09-04.md: "CLV as the sports-specific yardstick... JOB_EVIDENCE_PACKET's own
do-not-claim list: no real close-based CLV reading exists yet [see JOB_EVIDENCE_PACKET.md's retracted-figure
entry for exact wording -- do not re-quote its number here]... the yardstick is built but not yet populated...
S-row: track 'days until first real close-based CLV reading' as an explicit countdown metric on the program
dashboard rather than an implicit future date buried in a do-not-claim note." Measured 2026-09-04:
`data/frontend/clv_ledger.jsonl` = 20 rows (2 legacy, 18 open, 0 settled, 0 integrity flags);
`data/frontend/analytics/execution_status.json` reports `n_settled: "INSUFFICIENT"`, `row_classes.settled: 0`.
Register: S32 (pairing-bridge blocker) CLOSED 2026-09-04; S20 ("THE KEYSTONE") OPEN, week bar (>=200 settled /
>=2 sports / >=7 days) unmet; S18 BLOCKED on S20; S19's cadence bar unexercised (n_live_games=0, 41 samples).
PREMISE (step 0): reproduce the clv_ledger.jsonl row-class counts and execution_status.json's INSUFFICIENT/0
fields above; reproduce S20/S32's CURRENT register status (S32 CLOSED, S20 OPEN, week bar unmet), not this memo's.
LIMIT (step 1): if the capture stores expose no settlement-RATE field at all (only a point-in-time count), a
numeric day-countdown is UNDEFINED at 0 settled/day and the row reports the blocker chain by name instead,
labelled UNDEFINED, never a fabricated ETA.
CHANGE (step 2): additive-only module `scripts/platformkit/live_edge/clv/clv_countdown.py` (<=300 LOC):
`countdown(ledger_path, execution_status_path) -> dict` reading the two stores above, returning
{n_settled_today, settlement_rate_per_day (from ledger history if present, else null), days_to_first_reading
(rate>0 ? ceil((min_bar-n_settled)/rate) : "UNDEFINED"), blockers: [named open register rows, e.g. S20/S18/S19]}.
No edit to clean_readout.py, clv_trial.py or run_clv_trial.py (import-only, reads the files they already read).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = days_to_first_reading (or UNDEFINED) plus the printed blocker list, computed from the two
                  named capture stores
  before        = no explicit countdown metric exists anywhere on disk; the date is "buried in a do-not-claim
                  note" per the source memo, with 0 settled rows measured today
  bar           = countdown() reproduces n_settled=0 and settlement_rate_per_day=null/0 from today's stores,
                  therefore returns days_to_first_reading == "UNDEFINED" (not a fabricated number) with >= 1
                  named blocker printed; on a CONSTRUCT fixture with a nonzero settlement history the function
                  returns a finite integer matching hand computation to the day
  n             = 2 cases (today's real 0-settled stores; 1 CONSTRUCT fixture with nonzero rate) (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier reruns countdown() on both cases and diffs the dict
  must not move = the ledger/execution_status field names and file locations; every existing threshold
NON-TAUTOLOGY: UNDEFINED at 0 settled is the correct answer today, not hidden behind a placeholder date; the
blocker list names CURRENT open register rows, never a stale snapshot.
EVIDENCE: docs/evidence/harness/S239_clv_countdown_metric_2026-09-04.md + the countdown JSON. ASCII only.
Calibration language only: no dollar/ROI/profit/edge words; CLV = match-the-close only; never a retracted figure.
TEST: one new per-file test (real-store UNDEFINED case + CONSTRUCT nonzero-rate case), run only that file.
REPORT: today's countdown() output, CONSTRUCT case, blockers, test line, SHA. Commit pathspec, no push. NEVER PARK.
