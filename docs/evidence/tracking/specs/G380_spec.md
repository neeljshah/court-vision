GAP G380 | sport basketball first | worktree aXX | log cx_g379_producer_provenance

**PRODUCER-PROVENANCE ROW (astra next-rows review 2026-09-10 rank 1: "the highest-leverage justified immediate DEPLOYED change"),
SUCCESSOR TO G368 (CLOSED AT LIMIT: motion share median 0.279919 over 44 sections, coast_row_share 0.382881, 0.584961 of held steps
branch-unresolved as CLAMP_OR_SUBPIXEL; PROPOSED position_source column b87dbd02...), G370 (PARTIAL: provenance on 0/34 sections, the
observation column constant) and G376 (DONE pending verify: the ledger DECLARES ceil(decoded/stride) ticks; producer-evaluated
denominators 28,276 / 53,250 vs declared 45,842 / 89,655; fix 1b: M1-corrected zero-observation shares 0.483449 / 0.603362 of
producer-evaluated ticks, the over-count explaining 0.610 / 0.531 of G370's gap and the held-position collapse most of the rest --
the two defects this row stamps at the source; PROPOSED evaluated_tick_ids sidecar) and G372 PHASE B (PARTIAL adjudicated: the
claim-time sidecar overlay pinned 43/43 unique sections but could not bind re-claims (xb write, 43/81 attempts) and, deployed
2026-09-10T19:34Z, coincided with a re-claim LOOP -- repeat-row share 1.000 in the 30-120 min windows, 0 after the revert at 22:15Z --
so it was REVERTED; its defects (idempotent bind, weight-digest glob, exception scope, _PENDING leak, test_g328 regression, the
re-claim path) are BINDING CARRY-OVER here).** Codex PREPARES the additive producer
patch + readers + tests; a Claude finisher runs the paired scratch replay; the DEPLOY overlay is a separate authorized phase after a
sol ACCEPT of the code (as G372). `src/` and `scripts/run_clip.py` / `track_daemon.py` are HUMAN-GATED: PROPOSED diffs only in the
landing repo; the overlay is applied ONLY to `/workspace/deploy/nba-ai-system` under the 2026-09-08 authorization, with a backup, a
smoke, ONE restart and a 20-min watchdog revert (the G372 phase-B protocol). NEVER write `data/registry/`, never flip a flag, never
change a coordinate, clamp, cadence, weight or threshold, never touch the register.

**WHERE THIS ROW RUNS:** ON THE POD, `/workspace/wt/aXX`; scratch paired replay of >= 30 preserved sections (sources copied to scratch
BEFORE the quota guard prunes them: files >= 90 min old are pruned above 35 GB; scratch < 2 GB); CPU + GPU for the replay (one job at
a time, free VRAM read first, thread caps); the deployed daemon is restarted ONCE only in the authorized phase.

**PREMISE (step 0, BINDING before-condition):** re-read G368's attribution.csv, G370's decisions.csv and G376's classification.csv and
PRINT: branch-unresolved held share (expect 0.584961), provenance-carrying rows (expect 0), producer-evaluated vs declared ticks
(expect 28,276 / 45,842 and 53,250 / 89,655); **if any landed producer table already carries a per-row source label on >= 0.95 of
rows, the premise is FALSE: STOP, memo, commit, report.**

METHOD (sealed before any number):
  1. **ADDITIVE FIELDS, written by the branch that emits the row:** `position_source in {DETECTION, PREDICTION, HELD, CLAMP,
     SUBPIXEL, UNKNOWN}` + `source_branch` (file:line id) + `matched_event_id` for DETECTION; and a per-section `evaluated_tick_ids`
     receipt (the producer's actual evaluated frame indices, written at run end) with `attempted_frames_capped`; the ledger gains
     `evaluated_tick_receipt_path` (additive). Every existing column, value and status stays byte-identical (B2).
  2. **TRACE CONTROLS:** synthetic frames that force each branch (fresh detection, coast, clamp, subpixel hold, id merge) and check the
     stamped label equals the branch taken (100 pct); an independent trace (monkeypatched at import in scratch) logs every branch
     entry and is diffed against the stamped labels row by row.
  3. **PAIRED SCRATCH REPLAY:** >= 30 preserved sections / >= 10 videos, original vs patched producer, same weights and caps: every
     non-provenance column byte-identical; claim-to-finish seconds paired (after/before median <= 1.10); receipt tick ids equal the
     trace's evaluated set 100 pct.
  4. **READER SURVEY (A5):** every reader of the tracking CSV fields and of ledger `evaluated_frames` (grep, cite file:line); none
     asserts a closed key set; the two G376 proposals P1/P2 are folded in as additive.
  5. **AUTHORIZED DEPLOY PHASE (after sol ACCEPT of 1-4):** overlay + backup + smoke + ONE restart + 60-min live window: receipts
     present on 100 pct of completed sections, labels present on 100 pct of rows, the paired-replay identity re-checked on 10 live
     sections; watchdog revert on any failure. CHANGE NOTHING ELSE.

ACCEPTANCE RULE:
  metric        = trace-consistent labels / all emitted rows; receipt tick ids / all traced attempts; unchanged-column identity;
                  paired seconds-per-clip ratio; live receipt coverage
  before        = provenance 0 rows; declared ticks over-count by 0.38-0.41; G368 unresolved 0.584961
  bar           = 100 pct label agreement with the trace; 100 pct receipt agreement; 0 unchanged-field differences; after/before
                  median <= 1.10 on >= 30 paired sections else the throughput clause is NOT VALIDATED; live coverage 1.000 on >= 30
                  sections / >= 10 videos; missing events labelled UNKNOWN and reported (never dropped)
  n             = >= 30 preserved sections / >= 10 videos (SAMPLED even); 5 branch controls (CONSTRUCT); live 60-min window
  eye check     = REQUIRED: 30 evenly spaced overlays with labels coloured by source, incl. HELD and CLAMP runs
  must not move = weights, coordinates, clamps, cadence, thresholds, flags, every existing column; G370's masks stay as landed
  verdict       = **DONE** / **PARTIAL** (name the clause) / **PREMISE FALSE**; the landing is ADJUDICATED (deploy under authorization)
EVIDENCE: `docs/evidence/tracking/g379_producer_provenance_2026-09-10.md` (<= 60 lines; VERDICT line 1; NOT VERIFIED; wall time;
SHA-256s incl. the PROPOSED diff and the deployed-file hashes) + `.../g379_producer_provenance_2026-09-10/{prereg,trace.csv,
per_tick.csv,reader_survey.csv,paired_runtime.csv,live_receipts.csv,hash_receipt.json,summary.json,overlays/,PROPOSED_*.diff}`.
**ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT.**
TEST: `tests/platformkit/test_g379_producer_provenance.py` alone (each branch control stamps its label; a missing event is UNKNOWN;
receipt equals trace on a fixture; the seal). **NEVER a full pytest.** Every new file <= 300 lines. Vocabulary follows contract Q6;
automated scan required. Prereg sealed as its OWN commit first. ASCII stdout. **NEVER PARK.**

VERSION 2026-09-10 (deploy phase reuses G372's protocol PLUS a 30-min repeat-share watch: unique game_id share of new ledger rows must stay >= 0.80 or REVERT)
