GAP S294 | sport nba (in-game) | worktree aXX | log cx_s294_incumbent_conformal_full_s86_blocks
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: S276 CLOSED AT LIMIT (attempt 2 candidate 19cae3f4c in worktree a17, verify memo 194b75dd7 REJECT): the
  full source WAS replayed on the pod (465,249 ticks / 1,593 games; 12 grouped cells and the S101 24-cell
  regression exact; peak pod RSS printed) and rejected ONLY because (a) the CPCV groups were five equal-date
  groups instead of S86's six tick-balanced date blocks (scripts/platformkit/eval_gate/s94_nba_early_shrinkage.py
  lines 93-103; cpcv.py lines 47-55) and (b) the prior dated S276 memo and JSON were edited in place. This row
  applies the verifier CORRECTION DIFFs verbatim. Recover code: `git show 19cae3f4c:<path> > <path>` (scripts/tests).
PREMISE (step 0, INFORMATIONAL): print the six S86 block boundaries (first/last game_date, n_ticks, n_games per
  block) from s94_nba_early_shrinkage.py's block routine on the frozen grid; print n_ticks/n_games via a game_id-
  only stream (expect 465,249 / 1,593); quote S265's worst cell and widest half-width from its landed memo.
CHANGE (step 1, the verifier's CORRECTION DIFFs verbatim): "restore the two prior dated artifacts byte-for-byte
  and publish their correction under a new dated erratum name"; "derive CPCV groups from the exact six S86
  tick-balanced blocks, hold each block once with the fixed embargo, reseal, rerun, and rearchive". Additive
  only: the S276 sibling module under scripts/platformkit/eval_gate/ (<= 300 lines) imports the landed S265
  callbacks unchanged; S265 constants and sample entrypoint byte-identical. Seal a prereg FIRST as its own commit
  (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show :<path>, verified with git show
  HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above the seal line). Run ONLY via
  ~/bin/pod_run <aN> --fetch <outputs> -- <command> (B5 NOTE); print pod RSS; md5 parity of every shipped input
  both sides. Never write data/ or docs/research/; never rewrite an existing artifact (new dated filenames).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = full-source empirical coverage vs nominal (0.90, 0.80) + mean half-width per grouped cell,
                  STATIC arm; S101 24-cell regression vs the committed JSON; denominator both sides
  before        = S276 attempt 2: 465,249 / 1,593 replayed, 12 cells exact, S101 24/24 exact, but five
                  equal-date groups (REJECT); S265 sample: worst OT 0.833333333, widest P2 0.90 0.207218181
  bar           = CPCV groups equal the six S86 tick-balanced blocks (printed block table identical to s94's);
                  each block held once with the fixed embargo; denominator 465,249 / 1,593 on the stream census
                  and the scored set; every cell >= 400 ticks reported (else ABSENT_BECAUSE); S101 24-cell
                  regression <= 1e-9; the S276 artifacts byte-identical with the erratum under a new dated name
  n             = 1,593 games / 465,249 ticks (full source; not a sample)
  eye check     = n/a (S-row); reproduction = verifier replays the fetched JSON/CSV, re-diffs every cell, the S101
                  match and the block table; the test recomputes ONE grouped cell from the archived CSV
  must not move = COVERAGE_MIN_GROUP/MAX_GROUPS; the S86 block design; S265 constants/entrypoint; the committed
                  S101 JSON; every S276 artifact; nothing charged
NON-TAUTOLOGY: state the full-source vs S265 worst-cell and widest-half-width comparison explicitly; name the
  local reference path used for the S101 ticks (the data/cache/eval_gate copy), never an absent path.
EVIDENCE: docs/evidence/harness/S294_incumbent_conformal_full_s86_blocks_2026-09-04.md + JSON + paired-loss CSV
  (gzip if needed, under 50 MB) + the erratum file + the pod log tail. TEST: one per-file test recomputing one
  grouped cell from the archived CSV (< 200 MB); run only that file.
REPORT: block table, denominators, cell table, S101 line, pod RSS, md5 parity, test line, SHA. No push. NEVER PARK.
