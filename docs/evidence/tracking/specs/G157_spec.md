GAP G157 | sport tennis | worktree a2 | log cx_g157_retrack_yield
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A2, A3, A7 and Q8;
self-check section B before reporting. This is a MEASUREMENT of a rebuild that is happening WHILE you
watch. Move nothing, start nothing, kill nothing.

THE SITUATION. The old pod died on 2026-09-03 and took every gate-eligible table with it. A
replacement is up, the footage bridge is running seven lanes, and the track daemon is consuming
staged games as they arrive. So new tracking tables are being produced continuously on the pod at
`/workspace/nba-ai-system/data/tracking/`, and new ledger rows at
`/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl`. This row measures the YIELD of
that rebuild for tennis specifically.

CORRECTED PREMISES you must start from, not the older ones:
  - The local eligible count is **1, not 0** (G154, reproduced by G150): `G83_tennis_09` reaches the
    unchanged gate. Do not repeat "0 eligible".
  - New ledger rows **do** carry `decoded_frames`. The first real row on the new pod read
    `decoded_frames = 39035`, `coverage_pct = 0.1565`. G149's producer gap is answered.
  - The `court_feet` declaration is stamped UNCONDITIONALLY (G152), so "declares court_feet" is NOT
    evidence of recovered geometry. Report geometry separately from declaration, always.

MEASURE, read-only, over a stated observation window:
  (a) Census every tennis table now present on the pod. For each: rows, distinct frames,
      `coordinate_space`, and the share of rows with `calibration_provenance = solved`. Give the
      ELIGIBLE DENOMINATOR (the number of tennis source-table directories you enumerated) and take
      every share over it. Never a bare sample size.
  (b) Apply the UNCHANGED jump-gate eligibility definition -- reuse
      `scripts/platformkit/g154_local_table_census.py`, which landed today and already implements it,
      rather than writing a second implementation that could drift. Report how many tennis tables
      reach the gate and the first-blocker breakdown for the rest, in G109's vocabulary.
  (c) For every tennis ledger row in your window, report `decoded_frames`, `coverage_pct`, `rows`,
      `seconds` and the failure heads. This is the first tennis data in the program that carries an
      auditable decoded-frame denominator, so present it as the two-column comparison G147 has been
      blocked on: coverage as the harness computes it, and coverage against decoded frames. If a row
      lacks the denominator, say so and exclude it explicitly by name (B1: never drop rows silently).
  (d) State the window: first and last timestamp, and how many tennis games completed inside it. If
      ZERO tennis games completed in your window, that is a full success -- report the window, report
      zero, and say what the bridge queue depth and staging state were. Do NOT wait for one to finish
      and do NOT poll in a blocking loop.
  (e) A3 APPLIES: if you sample tables or rows for any detail, sample EVENLY across the set, never a
      head slice. Say how you sampled.

DO NOT change any threshold, the 0.90 coverage bar, the 10-eligible bar, the coordinate contract, the
eligibility definition, or any verdict. Do not re-track anything. Do not stage, move or delete any
pod file. Do not restart or kill the daemon or the keeper -- the orchestrator owns both.

ACCEPTANCE RULE:
  metric        = tennis table census with the eligible denominator named; gate-reaching count and
                  first-blocker breakdown; per-row decoded_frames/coverage two-column comparison
  before        = the rebuild's tennis yield is entirely unmeasured; no tennis row has ever carried
                  an auditable decoded-frame denominator
  bar           = NO pass bar. Success is the census with its window stated. Zero completed tennis
                  games in the window is a full success.
  n             = every tennis table present on the pod in your window (CONSTRUCT, exhaustive)
  eye check     = REQUIRED on 5 frames sampled EVENLY from one gate-reaching tennis table if any
                  exists; otherwise state that none exists and skip, saying so explicitly
  must not move = every threshold and bar, the coordinate contract, the eligibility definition,
                  tracking_harness.py, every verdict, and every pod file and process
EVIDENCE: docs/evidence/tracking/g157_retrack_yield_2026-09-03.md with the census table, the
two-column comparison, the stated window, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g157_yield/ BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. NEVER a full pytest.
POD: STRICTLY READ-ONLY. The daemon and the bridge are LIVE. Never kill or restart anything.
COMMIT: explicit pathspec only, in a2, no push. Report the sha.
NEVER PARK: do not poll your own jobs or the pod in a blocking loop; never end waiting.
