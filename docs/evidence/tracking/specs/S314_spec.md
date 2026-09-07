GAP S314 | sport nba | worktree aXX | log cx_s314_teach_packet_qualification
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: allocated 2026-09-07 from docs/research/astra_teach_feasibility_2026-09-07.md ranked experiment S-TEACH-0 (orchestrator-held; NOT a lane input). FIRST dispatch of the TEACH lane and the
  gate on S312 (amended 2026-09-07b) and S315. The CENSUS HALF is PRE-LANDED by the orchestrator: docs/evidence/harness/S314_teach_packet_census_2026-09-07.md plus
  S314_census_local_2026-09-07.jsonl and S314_census_pod_2026-09-07.jsonl -- read those three first. THIS ROW IS THE ALIGNMENT HALF and re-verifies the before-condition, never assumes it.
DEPENDENCY: dispatch after S311 (safe pod transport). Census and alignment arithmetic are local; any frame decode runs on the pod.
WHERE: local = reading committed records/artifacts, arithmetic, one per-file test. pod = frame decode and native-image reads, run with ~/bin/pod_run <aN> --ship <code> --fetch <evidence> --
  <cmd>, scratch /workspace/wt/<aN> only, NEVER the deployed tree /workspace/nba-ai-system.
PREMISE (step 0) BINDING BEFORE-CONDITION: a complete source census must identify >= 2 NBA broadcasts having ALL of prior API history (PBP) AND final outcomes AND native source images AND
  declared source PTS AND independent observation labels. If ANY item is missing, STOP and report BLOCKED naming the missing item -- a valid result that earns its own register row. An
  unavailable authoritative inventory is BLOCKED: census prerequisite unavailable, never proof of corpus absence. Publish nested counts N_footage -> N_API -> N_outcome -> N_qualified with every
  exclusion, alias and overlapping reason, printing path, rows and first 3 ids per stage. Freeze the selection WITHOUT reading outcome values.
LIMIT (step 1): a qualified but undersized packet is INSUFFICIENT -- not a NULL and not a pass. Two broadcasts qualify an INSTRUMENT SCREEN only; they never clear S04 or license a teaching claim.
CHANGE (step 2): stage 30 TIME-STRATIFIED intervals per broadcast (60 total), deliberately including cuts, replays and intervals with missing detections. Per interval audit frame identity,
  player continuity, and >= 2 game-clock anchors per LIVE interval; break identical clocks by source event order and REJECT ambiguous period/clock alignment rather than imputing it. Additive
  only: new dated artifacts, no rewrite of any existing artifact, no data/ write.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric = (a) fraction of the 60 ATTEMPTED staged intervals resolving UNIQUELY to the correct official game_id and period within 1 game-clock second; (b) per candidate signal, the agreement
           fraction of its PREREGISTERED independent observation labels over the FULL attempted packet.
  before = no interval has ever been aligned and teacher_qualification had no image-space definition before S312 VERSION 2026-09-07b; the 2026-09-07 census gives N_qualified = UNKNOWN
           (local 351 tracked -> 19 with PBP -> 19 with outcome; pod 31 tracked CSVs / 3 official ids -> 0 with PBP).
  bar = ALL of: (a) >= 90 pct of the 60 attempted intervals resolve uniquely and within 1 game-clock second, with ZERO accepted replays and ZERO wrong-game joins; (b) a signal QUALIFIES only if
        its preregistered independent observation labels agree >= 90 pct on the FULL attempted packet, ABSTENTIONS COUNTED AS FAILURES -- otherwise close that measurement recipe AT LIMIT.
        Denominators are attempted intervals, never surviving intervals.
  n = 60 attempted intervals (30 per broadcast x 2 broadcasts), published as the attempted denominator beside the nested corpus counts.
  eye check = n/a (S-row); reproduction = the verifier replays the keyed interval table and recomputes both fractions from the archived rows.
  must not move = the two 90 pct bars; the 1 game-clock-second tolerance; the zero-replay and zero-wrong-game rails; every G-route registration verdict and producer hash (recorded SEPARATELY
        from teacher_qualification, per S312 A1); data/registry/; all prior dated evidence.
NON-TAUTOLOGY: the denominator is the ATTEMPTED interval set fixed before measurement, never the set that survived; every dropped interval is counted by reason. If excluding the failing
  intervals is what makes the fraction good, the metric is circular -- say so and report REJECT yourself.
TEST: exactly one new per-file test with full package imports covering all five plants -- wrong game ids, reversed clock direction, repeated clocks, one cut and one replay -- each of which MUST
  FAIL CLOSED with no accepted join. Run only that file.
BUDGET: 3,600-second wall stop; 10 min source audit, 35 min measurement, 15 min replay/archive. On expiry report BUDGET LIMIT with the completed counts; never infer a general negative from an
  incomplete packet. EXPECTED FAILURE (not a surprise): truncated broadcasts, frozen game clock, absent event ids, low detection recall, unreliable footpoints.
EVIDENCE: docs/evidence/harness/S314_teach_packet_qualification_2026-09-07.md + summary JSON + the keyed per-interval CSV + the nested count table + a NOT VERIFIED list. New dated filenames only.
BAN: never write data/ or docs/research/; no gated-tree change; no flag flip; no registry write; no forced git operation; calibration language only.
REPORT: verdict first, nested census counts, both fractions with attempted denominators, per-signal teacher_qualification, RSS, test line, SHA, NOT VERIFIED list. No push. NEVER PARK.
