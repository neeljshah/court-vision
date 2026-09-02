# Harness / signals / system gap register -- 2026-09-03 (living; one gap = one lane)

Rule: a gap is closed only by a measured artifact (metric, exact denominator, n,
and for any scored claim a prereg sealed before the metric). Harness thresholds
and gate values NEVER move. Calibration language only -- no dollar, ROI or edge
claim ever appears in a row, an artifact or a memo.
NEXT_GAP_ID: S31  (allocated by the orchestrator ONLY; lanes never invent ids.
OWNERSHIP IN FORCE 2026-09-03: account 1 = this harness session holds THIS counter (S); account 2 = the tracking session holds G (G33). Account 1 dispatches codex ONLY into worktrees a10-a12.
S-ids start at S01 so they can never collide with the tracking register's G-ids.
S28/S29 allocated 2026-09-03 by the roadmap-audit lane.)
ONE COUNTER, ONE HOLDER: if two sessions are running (see the two-account handoff
docs/evidence/tracking/HANDOFF_TRACKING_ACCOUNT2_2026-09-02.md), exactly one of
them may increment this header. Say which in the first turn of the day.
Specs cite docs/evidence/tracking/CODEX_SPEC_TEMPLATE.md; verifiers apply the
spec's ACCEPTANCE RULE + VERIFIER_CONTRACT.md B1-B10 + the quant additions Q1-Q6
below, and nothing else. A rule absent from the spec's ACCEPTANCE RULE cannot be
used to reject -- a verifier that needs one files a NEW row instead.

Plan detail for every row: docs/research/organization-sprint/MASTER_ROADMAP_2026-09-03.md
section 2. Landings append one line to docs/evidence/RESULTS_LEDGER_SYSTEM.md
(create on the first landing; same format as the tracking ledger).

Order: S01, S02, S03, S04, S05, S06; S19 and S20 in parallel from day 1; then
S07, S08, S09, S13, S10, S11, S12, S15, S16, S21, S22, S23, S24, S17, S14, S18,
S25, S26, S27. S28 and S29 are week-1 fillers whenever a lane is free -- S28
BEFORE the first unattended night's push.

ACCEPTANCE DEFAULTS (audit 2026-09-03): 14 rows were missing at least one of the
five required elements (metric / denominator / before / bar / n / must-not-move).
The defaults that fill them, and the CONSTRUCT carve-out from the n>=30 rail, are
in MASTER_ROADMAP section 2 under "AUDIT 2026-09-03 -- ACCEPTANCE DEFAULTS". A
spec copies them in verbatim; a verifier may not reject a CONSTRUCT row on n>=30.

This register SUPERSEDES the H/X/A/D rows in SYSTEM_GAPS_2026-09-01.md. The
mapping is NOT one-to-one: H01->S02+S03, H05->S07+S08+S09, H02+X05->S06,
H03->S05, H04->S04 (and tracking G16), H06->S10, H07->S01, X01->S19, X03->S20,
X04->S21, A02->S22, A03->S23, A04->S24, D01->S25, D02->S26; X02/A01/A05 are
CLOSED with no S-row; S11-S18 and S27-S29 are new.

| id | area | gap (measured) | evidence | status |
|----|------|----------------|----------|--------|
| S01 | harness | `run_gap_arms_real_corpus.py:18-19` `_BASELINE_TICKS` 144,424 and `_BASELINE_WINDOW_TICKS` 14,802 match nothing on disk (real: 52,558 / 7,158); a two-line fix, not the one-liner the burst plan recorded | E4_PROMOTION_RESULT_2026-09-01.md section 3; module read on disk (108 LOC) | RE-DISPATCHED codex a10 cx_s01_baseline_const 2026-09-03 after the worktree data-junction fix (attempt 1 returned NO STORE because worktrees lack the gitignored data/ tree -- an environment defect, not counted as an attempt) (was H07) |
| S02 | harness | soccer gate corpus carries a target but no market close: `p_base` is a Poisson MODEL baseline, so the sport cannot enter walk-forward against a close. Gate corpus EXISTS (25,834 rows) -- this is a close JOIN, not a corpus build | RENAISSANCE_HARNESS_DEEP_PLAN_2026-09-02 section 2.2; `data/cache/combo/gate_corpus_soccer.parquet`; odds 16,322 rows 2019-08-02..2026-05-24, 100.0 pct joinable, 0 null closes | RE-DISPATCHED codex a11 cx_s02_close_join_soccer 2026-09-03 after the worktree data-junction fix (attempt 1 NO DATA, same environment defect, not counted) (was H01a) |
| S03 | harness | tennis same, with two disjoint `corpus_unit`s: ATP 25,831/30,616 = 84.4 pct joinable, WTA 8,028/11,270 = 71.2 pct. `b365w`/`b365l` are winner/loser oriented and LEAKY beside the de-leaked `_p1`/`_p2` (verified row 0) | same; `data/cache/combo/gate_corpus_tennis.parquet` 41,886 rows | OPEN (was H01b) |
| S04 | harness | the teacher->student gate is a RULE, not code: no module runs student vs id-fixed-effect baseline vs student+ids, so no "tracking improved a model" claim is permissible today | SYSTEM_GAPS H04 / tracking register G16; `scripts/platformkit/eval_gate/student_gate.py` verified ABSENT | DISPATCHED codex a12 cx_s04_student_gate 2026-09-03 (was H04/G16) |
| S05 | harness | every calibration piece exists and nothing composes them per (sport, regime): reliability bins, `max_loser_wp`, Murphy decomposition, per-regime isotonic, ECE, sharpness, resolution all present; `max_loser_wp` has never gated a promotion and `docs/evidence/calibration/` holds only `foundry_run_*` | deep plan section 1 "Calibration craft"; dir listing verified | OPEN (was H03) |
| S06 | harness | no nested-CV stacker over the arms; online Hedge trails its best arm (regret +2.063 inside a 66.79 bound over 158 rounds) with three named structural causes -- coverage asymmetry, two bad arms, regime heterogeneity (-0.0053 innings 1-3 vs +0.0484 innings 7+) | X05 (c75b60074); HEDGE_TRIAL_RESULT_2026-09-01; `eval_gate/stacker.py` ABSENT, prior art at `combo/stack_fit.py` + `combo/nested_cv.py` | OPEN (was H02/X05) -- CHARGED, SERIAL, LAST |
| S07 | harness | no primacy rule: where a forward settled series and a backtest disagree, nothing says the forward number is the claim, and a retrospective-only number is not labelled | SYSTEM_GAPS H05; `ingame/forward_evidence_scoreboard.py` (291 LOC) | OPEN (was H05a) |
| S08 | harness | replication is a convention, not a gate: `combo/fwer_budget.min_corpora_eff` (:55) exists and no call site consults it, so a single-window AHEAD is downgraded only by memo | deep plan risk 3; E4_PROMOTION_RESULT (no disjoint MLB window on disk) | OPEN (was H05b) |
| S09 | harness | gate-manifest staleness does not BLOCK a claim: evidence rows fall back to mtime, so staleness is WRITE time, not MEASUREMENT time | deep plan section 1 "Reproducibility"; `scripts/platformkit/eval_gate/gate_manifest.py` | OPEN (was H05c) |
| S10 | corpus | MLB odds end 2021-11-02 while `games_current.parquet` runs to 2026-07-12, so all 22 MLB mechanisms are NOT_TESTABLE against a modern close | deep plan section 2.2 (confirmed at data level); MECHANISM_WIRING_MLB_2026-09-01 | OPEN (was H06) |
| S11 | signals | no hypothesis grammar and no dedup: `foundry_runner.py:23` rebuilds ONE hardcoded matrix and `signal_foundry.register` (:51) is hand-called, so throughput is 13 charged trials in the program's lifetime | deep plan section 3; modules read on disk (108 / 246 LOC) | OPEN |
| S12 | signals | no cost tiering and no fixed T1->T2 promotion rule; without one, cheap screens are the garden of forking paths with extra steps | deep plan section 3 "Cost tiers"; Gelman & Loken (2013) | OPEN |
| S13 | harness | the FWER ledger is FLAT and GLOBAL: 13 rows of `{at, predictor, sport, start, end, k_cumulative}`; nine unrelated basketball trials charged between prereg and launch took K 3 -> 12 and flipped a verdict | `data/cache/eval_gate/backtest_fwer.jsonl` (13 rows verified); HEDGE_TRIAL_RESULT_2026-09-01 | OPEN -- SHARED-MODULE TOKEN |
| S14 | harness | no within-family FDR: only Bonferroni `deflated_p` exists, so a family of hundreds of related hypotheses is priced as if every one were independent | `eval_gate/deflated_metrics.py:63`; `combo/fwer_budget.py:42`; statsmodels 0.14.4 installed, BSD 3-Clause (licence read) | OPEN -- LAST; the ONLY change that loosens a bar, gated on a frozen families spec |
| S15 | signals | no results DB: a re-proposed hypothesis is a fresh trial rather than a lookup, and nothing indexes the trial artifacts | deep plan section 3 "Runner and results DB"; `data/cache/eval_gate/hypotheses.sqlite` verified ABSENT | OPEN |
| S16 | signals | the runner cannot run continuously on grammar: `run_pass` (:51) rebuilds a fixed matrix and sleeps 900 s (:88) | `scripts/platformkit/foundry_runner.py` read on disk | OPEN |
| S17 | harness | decay monitoring alarms on n, not ESS: at the measured ICC 0.291 / design effect 87.4, 47,104 ticks are n_eff 539, so a 7-day tick window can be n_eff < 10 and the alarm is noise. One monitor exists where three are needed | `eval_gate/ledger.drift_report` (:86, disjoint windows correct); `ingame/gap_effective_n.py` (:30, :53, :62) | OPEN -- build now, arm after S20 |
| S18 | execution | sizing has no cross-market covariance, no impact model and no capacity: `venue_fees.expected_value_after_fees` (:156) nets FEES only | X05 memo; module read on disk (194 LOC); sklearn 1.6.1 installed, BSD 3-Clause | BLOCKED on S20 (0 settled rows) |
| S19 | execution | book capture pass wall ~105 s at 9 games x 2 sides vs a 5 s target; governed orderbook fetches ~3.6 s each | SYSTEM_GAPS X01; CAPTURE_CADENCE_ROOTCAUSE_2026-09-01 | OPEN (was X01) |
| S20 | execution | maker pool EMPTY; the forward CLV series has 0 settled rows locally, so sizing, capacity, adverse selection, decay monitoring and the program's only claim surface are all downstream of a week that has not run | SYSTEM_GAPS X03; EXECUTION_ENFORCEMENT_MATRIX_2026-09-01 | OPEN (was X03) -- THE KEYSTONE. PREMISE RE-MEASURED 2026-09-03 04:25 UTC from /proc: `inplay_capture_runner` IS alive (pid 8608 since 08-31 16:02 UTC, heartbeat m2_inplay_capture fresh), so the plan's 'runner not running' is FALSIFIED; still 0 bets all-time (paper_today n_placed_alltime 0), the default CLV ledger file is absent on the pod, and NO supervisor process (see S30). Premise memo lane running: docs/evidence/harness/S20_premise_2026-09-03.md |
| S21 | ops | pod code lags master. CORRECTED 2026-09-03: the G15b/G29b/G01c backlog is CLEARED -- ledger row G14b records 48 files deployed 2026-09-02 ~22:05, md5-identical, imports ok, keeper 3127042 / daemon 3127047 restarted (commit c7816aecd). What is outstanding is G08 (f07c71cd7) and every landing from 2026-09-03 forward. Two steps the row was missing: resolve the pod ssh port from the `config.pod` alias (it drifts, 40045 -> 40048) and fail loud rather than hardcoding it; record the new daemon pid from `/proc` only, never `pgrep` | SYSTEM_GAPS X04; RESULTS_LEDGER.md row G14b (2026-09-02); memory pod_tracking_ops_2026_09_01 | OPEN (was X04) -- premise re-scoped, not closed |
| S22 | analytics | soccer 0/15 and tennis 0/23 mechanisms wired, blocked only by the close join | SYSTEM_GAPS A02; MECHANISM_WIRING_RESULT_2026-09-01 | BLOCKED on S02 / S03 |
| S23 | analytics | the `harness_health` MCP artifact has no generator | SYSTEM_GAPS A03; MCP_ADVANCE_2026-09-01 | OPEN (was A03) |
| S24 | ops | artifact refresh has no scheduler (`fleet_on` false) | SYSTEM_GAPS A04; MCP_ARTIFACT_FRESHNESS_2026-09-01 | OPEN (was A04) |
| S25 | corpus | the ingest content gate LANDED and has never run on the real queue: no queue JSON re-gated, and the pod daemon plus the local downloader still run the old code | RESULTS_LEDGER.md G01c row (4212afa1e, 14 tests pass, "NOT verified" list) | BLOCKED on S21 |
| S26 | corpus | the called-pitch CSV is cached at 66,665 rows but `command_target` columns need video only baseball METRIC_LOCAL produces, so the framing gate stays NOT_TESTABLE | SYSTEM_GAPS D02; FRAMING_PREREG_RESULT_2026-09-01 | BLOCKED on the tracking baseball lane; it is what blocks S04's first REAL trial |
| S27 | analytics | the answer contract is documented but not mechanical: nothing enforces `source_artifact` + `as_of` + verdict on every answer, or a refusal in their absence | `docs/AI_CONSUMER_CONTRACT.md` (129 lines, verified) | OPEN |
| S28 | ops | secrets-scan and the data//vault/ staging guard exist only as prose in three runbooks; push to public `origin master` is allowed by the 2026-09-07 override, so the one step protecting the public repo is the one a long unattended night skips. No hook enforces it (the SessionStart `loop_status.sh` hook proves the mechanism works here) | `.claude/settings.local.json` (SessionStart hook present, no pre-push guard); `.claude/rules/data-vault-nocommit.md`; TRACKING_PROGRAM_STATE section 4 step 4 | OPEN (new 2026-09-03, audit) |
| S29 | ops | the FWER audit trail has no backup: `data/cache/eval_gate/backtest_fwer.jsonl` (13 rows verified) is what every `deflated_p` in the program is computed against, `hypotheses.sqlite` (S15) will join it, both are gitignored and pod-authoritative, and a volume loss or bad write makes every past verdict unreproducible | `data/cache/eval_gate/` listing (backtest_fwer.jsonl, .lock, two trial JSONs, gate_manifest.json -- no backup); S15 | OPEN (new 2026-09-03, audit) |

| S30 | ops | the pod paper stack runs ORPHANED: bankroll_daemon 8606, inplay_capture_runner 8608, pm_paper_tick_runner 8609, settle_sweep_daemon 8994 all have ppid 1 (started 2026-08-31 16:02 UTC by a supervisor whose m9_supervisor heartbeat stopped 08-31 20:12 UTC); no `python -m supervisor` process exists, so a dead child is never relaunched and the S20 week has no keeper. Starting a second supervisor over live children risks two writers (the S20 integrity stop rule) -- adoption behaviour must be read from supervisor/supervisor.py before any launch | /proc scan 2026-09-02 04:16 UTC via the config.pod alias; daemon_heartbeats listing; supervisor/_singleton.py | OPEN (new 2026-09-03, harness session) -- resolve with the S20 premise memo |

## Quant additions to the verifier contract (Q1-Q6)

These are appended to docs/evidence/tracking/VERIFIER_CONTRACT.md and apply to
every S-row exactly as B1-B10 apply to every G-row. Codex self-checks them before
reporting; the verifier applies A + B1-B10 + Q1-Q6 and nothing else.

- **Q1 PREREG SEALED BEFORE SCORING.** Any scored comparison names its prereg
  artifact and the SHA-256 seal embedded in it, and the seal predates the first
  metric. No seal, no scored claim.
- **Q2 LEDGER CHARGED BEFORE THE METRIC.** A charged trial appends its ledger row
  before it computes anything, and reports the K it read AT LAUNCH. K read after
  scoring is an automatic reject (nine unrelated trials once moved K 3 -> 12
  between prereg and launch and flipped a verdict).
- **Q3 NO BAR OR THRESHOLD MOVED.** Every bar in the spec is byte-identical to the
  bar in the artifact. A bar discovered to be unmeetable is reported as CLOSED AT
  LIMIT, never lowered (the ">= 95 pct tennis join" is the standing example).
- **Q4 LEAK CONTRACT VIA CPCV.** Anything scored out-of-sample runs through
  `walk_forward` or `cpcv_evaluate` with purging and a symmetric embargo, and any
  meta-learner consumes OOF series only, asserted to reproduce each arm's own
  reported metric to 1e-9.
- **Q5 TWO CORPORA FOR ANY AHEAD.** An AHEAD names its second corpus or
  `corpus_unit` and prints `min_corpora_eff` at the current K. If it cannot be
  satisfied, the verdict is labelled SINGLE-WINDOW in the artifact AND the
  register row.
- **Q6 CALIBRATION LANGUAGE ONLY.** No dollar, ROI, profit or "edge" language in
  any artifact, memo, ledger line or register row; none of the retracted figures
  (+18.38, 0.119, +54, 78.11, 8.94, 54.57) appears outside an explicit retraction
  context. Accuracy is not edge; an honest REJECT, NULL or BEHIND is a success.
