# Historical cloud run -- acceptance correction, 2026-10-02

STATUS: HOLD. The original cloud run below did not satisfy the binding five-file acceptance rule: four tests failed. Its subset verdict and PORTABLE approval are withdrawn. Counts remain historical observations, not acceptance evidence. Missing real files establish no preservation proof. The S637 Codex fix memo supersedes the candidate assessment; fresh Ubuntu and real-host verification are pending.

# S637 cloud result -- test hermeticity round 2 (2026-10-02, desk-improve routine)

Row: S637 (OPEN, PORTABLE, Test health lane, no live owner, no prior cloud/S637-* branch).
Why this row: claim check `git ls-remote --heads origin 'cloud/*'` showed that every PORTABLE row in
AUTOMATED_PAPER_DESK_ARCHITECTURE_2026-09-30.md section 2 (S691-S703, S705, S707, S709) and in
QUANT_GRADE_BUILD_SLATE_2026-09-30.md section 2 (S660, S663, S664, S666-S672, S674-S679, S682-S689)
already has a cloud branch. So the row comes from source (c): an unowned PORTABLE row in DESK_STATE section 4.
S639 was skipped because it is in the S534 seal addendum, and S546/S547/S596/S564 were skipped because they need live data.
Branch: cloud/S637-2026-10-02. Candidate 96ee0b27 (tests + spec); base bb34a09c (origin/trunk).
Spec: docs/evidence/tracking/specs/S637_spec.md (base) + docs/evidence/harness/S637_spec_2026-10-02.md
(cloud deltas C1-C6, AMENDMENT 1 from the critic, AMENDMENT 2 from the verifiers).

## Verdicts (codex unavailable; each tier was an independent Opus sub-agent that did not build)
- Pre-build critique: REVISE (11 items) -> folded as AMENDMENT 1.
- CONTRACT tier: ACCEPT WITH CORRECTIONS. (1) D6 handled as a scratch probe; (2) memo missing;
  (3) D5/D7 must be carried into the memo. All three are addressed by this memo and AMENDMENT 2.
- ADVERSARIAL tier: ACCEPT WITH CORRECTIONS. 11 mutations, all red then reverted. (1) memo missing;
  (2) A1.7 ts-None clause. Addressed by this memo and AMENDMENT 2.
- No REJECT; no re-verify round needed.

## Per-file results (one file per process; fastapi+httpx pip-installed, since cloud setup.sh lacks them)
CLEAN = `python3 -m pytest <file> -q -p no:cacheprovider`
ARMED = `PYTHONPATH=<scratchpad>/plug python3 -m pytest <file> -q -p no:cacheprovider -p armed_host`
(C1 scratch plugin, not committed: points PF.SENTINEL_PATH at an existing tmp file and cached_board_read._DEFAULT_PATH
at a tmp stale one-card board. Nothing is written under data/.)

| file | before CLEAN | before ARMED | after CLEAN | after ARMED |
|---|---|---|---|---|
| progress/test_ci_boundary_invariants.py | 8 pass | 8 pass (inv2 does not reproduce; C1 allowed) | 8 pass | 8 pass |
| progress/test_progress_ledger.py | 2F (:48,:103 data) | 2F (:43,:101 engine_enabled) | 2F DATA_ABSENT (:73,:128) | 2F DATA_ABSENT (:73,:128) |
| test_aggregate_clv_to_corpus.py | 4 pass | 1F (:121) | 5 pass | 5 pass |
| test_bestbets_compute.py | 1F (tier :457) | 4F | 24 pass | 24 pass |
| showcase/test_rooms_calibration_ledger_replay.py | 2F data, replay vacuous | same | 3 pass + 2F DATA_ABSENT | same |

- Register reds reproduced under ARMED on the base: 7. The candidate still had four failing tests; the full file acceptance rule was NOT met.
- A1.2 line progression: armed-before :43/:101 (engine_enabled), after :73/:128 (data absence only). With the fixture removed, the reds return to the engine_enabled lines.
- run_file peak RSS: every file is <= 180 MB (the verifier measured 137 MB replay, 135 MB bestbets). TRIVIAL here: with no real parquet, even the old code is cheap (A1.9).
- Restore proof (contract tier, one process, two owned modules): PF.SENTINEL_PATH == _REAL afterwards, both CLEAN (repo path) and ARMED (plugin tmp path).
- Mutations (adversarial tier): M1a-c drop fixture; M2 rewrite _REAL; M3 cadence writes sentinel; M4 drop _no_daemon_cache; M5 empty
  _clean_cards; M6 absent PRICE_SERIES; M7a 400 ticks; M7b game 4 outranks game 3; M8 real-path guard; M9 B card -> A; M10 old tier
  assertion red on both old and new code. All 11 went red. Probes: the dailies distractor reaches _pick_games; the lint subprocess turns red on a
  banned token.
- Scope: only the five test files + the spec + this memo. Line counts 416 (+25), 132, 216, 526 (+25), 154. ASCII, `git diff --check` clean.

## Disclosures
- D1: the sentinel property changed. The tests now prove "inert whenever the flag reads absent, live when present" (new test_armed_tmp_sentinel_unlocks_corpus); they no longer prove anything about the real path.
- D2: the fixture is module-scoped with its own MonkeyPatch context (S576 AMENDMENT 2 item 2). The ABSENT tmp path is shared by every test in a module. No current test creates it; a future test that did would arm the later tests.
- D3: replay is no longer a real-data unit test. A code-side streaming read was rejected (it would change a published-artifact producer).
- D4: the calibration and ledger room tests and the progress_ledger real-funnel assertions still read real artifacts. They are DATA_ABSENT on the cloud and are not skipped.
- D5: not owned here: test_bestbets_compute_stale.py, test_bestbets_compute_runner.py, test_unattended_readiness_probe.py:110 and test_rb_p0_03_daemon_heartbeats.py:192. The last two import SENTINEL_PATH by name, so they are exposed to the armed host. Candidate follow-up row; no id allocated.
- D6: production finding, not fixed. A ts=None row inside a picked game makes replay.build() raise `TypeError '<' not supported between
  instances of 'NoneType' and 'int'` at rooms/replay.py:49 (_downsample sort). This was found by a scratch probe and reproduced by the contract tier, and it is not covered by a committed test (AMENDMENT 2).
- D7: test_tier_filter_passed_through asserted a contract the route does not have: tier is applied after compute by _apply_filters, and is never passed to compute. It was red as `None == 'A'` on any host without a daemon board. It is rewritten to assert the A card is kept and the B card dropped; this corrects a stale assertion and does not weaken it.

## NOT VERIFIED
- The laptop armed host with real data/ (the real 361 B sentinel, the real best_bets.json, real funnel artifacts). The 5/5 there needs a laptop run.
- The 2490 MB replay RSS case (no real parquet in the clone).
- The real ts dtype of mlb_price_series.parquet (the synthetic store assumes int64 epoch seconds).
- Whether the real daemon board is stale (register state).
- Before/after stat of the real data files (absent on the cloud; the guards compare None == None on the clean host, and are non-vacuous only under ARMED).

PORTABLE: NOT VERIFIED for the corrected candidate; the historical subset was insufficient.
Calibration and execution-quality language only; PAPER ONLY; no production module, no seal-pinned file, no data/ write.
