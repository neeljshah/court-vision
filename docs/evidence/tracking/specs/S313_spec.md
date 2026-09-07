GAP S313 | sport all | worktree aXX | log cx_s313_answers_roundtrip
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: allocated 2026-09-07 by the orchestrator's harness finish audit (orchestrator-held; NOT a lane input). This is THE single real harness <->
  intelligence/answers connection row: one measured S-result -> receipt -> the actual resolver/composer answer, plus the completion manifest. S23 (bbf49a597),
  S24 (863a62d72), S232, or a source_artifact string alone cannot establish it. It ABSORBS S290's four-sport tail feasibility as its capability manifest
  (MERGED 2026-09-07; no separate S290 dispatch).
DEPENDENCY: consumes the accepted outputs of S296, S310 and S312 when they land; an unlanded route is reported NOT_TESTABLE, never fabricated.
WHERE: local enumeration plus adapters in safe trees (scripts/platformkit/, domains/); the answers files one at a time on the pod via ~/bin/pod_run.
PREMISE (step 0): S71 (a5aaa0541) still reports 5 red probes against a <= 1 bar; S275 (17f8b6218) recorded 8/8 explicit calibration-basis reads with flip
  delta 0. Neither proves that S296/S310/S312 answers CONSUME their verified outputs. Enumerate, printing each path: the supported routes, the real resolver
  entrypoints, and the current readers. ABSORBED S290 MANIFEST COUNTS, to be RECOUNTED and never assumed: gate_corpus_nba_close.parquet 1,814 rows, p_close
  563/1,814, tails <= 0.15: 25 and >= 0.85: 60 (n=85); gate_corpus_mlb_close.parquet 39,162 rows, p_close 910, tails 1 and 1 -- the register says MLB tail
  n=0 and the S290 spec says n=2, so RECOUNT and score using neither unverified count; gate_corpus_soccer.parquet 25,834 rows and
  gate_corpus_tennis.parquet 41,886 rows carry no p_close (p_base is a MODEL baseline and is never substituted for a close). Reconcile the ACTUAL joined
  outputs, not merely the absence of p_close in the raw spines; S02/S03/S10 already measured close joins.
LIMIT (step 1): a route whose prerequisite is missing emits a measured NOT_TESTABLE naming that exact prerequisite; it never emits a number.
CHANGE (step 2): connect accepted receipts to the ACTUAL answer composer through safe-tree adapters; trace ONE real end-to-end route and record the status of
  EVERY declared route, including S223 source -> S232 candidate -> factory outcome -> answer feedback. Additive only, new dated artifacts; never write data/,
  data/registry/ or docs/research/; no flag flip; no gated-tree edit (api/, intel/, src/, kernel/ stay read-only).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric = trace-receipt coverage of the funnel stages and its connection entries, field-exactness of supported-route answers, and refusal correctness on
           broken fixtures.
  before = S71 5 red probes against a <= 1 bar; S275 8/8 basis reads with flip delta 0; no complete new S-result-to-answer trace exists.
  bar = 6/6 funnel stages AND 2/2 connection entries carry real trace receipts; 100 pct of supported-route answers preserve artifact hash, basis, n, CI,
        measured_as_of and verdict EXACTLY; every missing, stale, corrupt or unverified fixture REFUSES the numeric claim; S71's <= 1-red bar is rechecked and
        ANY remaining red touching this chain BLOCKS FINISHED; derived freshness may never exceed its oldest required input.
  sign = a correct refusal is a pass; a fabricated or silently defaulted number is an automatic REJECT.
  n = 6 funnel stages + 2 connection entries + every declared route (CONSTRUCT: enumerated exhaustively, not sampled), plus 4 (CONSTRUCT) for the absorbed
      nba/mlb/soccer/tennis capability rows.
  eye check = n/a (S-row); reproduction = verifier recomputes one landed loss from its archived rows and re-reads the composed answer.
  must not move = every landed artifact and its hash; the +0.004 bar; S71 and S275 evidence; api/, intel/, src/, kernel/; data/registry/.
NON-TAUTOLOGY: NULL, BEHIND, NOT_TESTABLE, CLOSED AT LIMIT and teacher-training-only labels must SURVIVE the full answer unchanged; a route dropped from the
  manifest to raise coverage is an automatic REJECT.
LIVENESS: repeat the round trip AFTER a consumer restart before claiming live connectivity; otherwise label the result OFFLINE VERIFIED / LIVE NOT VERIFIED.
EVIDENCE: docs/evidence/harness/S313_answers_roundtrip_2026-09-07.md + summary JSON + the route-status table + the capability manifest (Q9).
TEST: exactly one new per-file test with full package imports covering: real landed loss-to-answer recomputation; a corrupted receipt; a missing receipt; a
  stale timestamp; a default-basis flip; denied runtime tracking access. Run only that file.
BAN: never write data/ or docs/research/; no gated-tree change; no flag flip; no registry write; no forced git operation; calibration language only.
REPORT: route-status table, the 6/6 and 2/2 receipts, the S71 red recheck, the capability manifest, test line, SHA, NOT VERIFIED list. No push. NEVER PARK.
