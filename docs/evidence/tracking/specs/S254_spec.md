GAP S254 | sport mlb (in-game) | worktree aXX | log cx_s254_mlb_phase_recal_fwer_sealed
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S209_VERIFY_2026-09-03.md (a18) REJECTed on Q1 (no sealed prereg predating scoring) and Q4 (inherited
  archive not purged / no symmetric embargo) while every ACCEPTANCE item passed: 15 buckets, 0 BH survivors,
  reproduced to <= 4.44e-14. NEW GAPs: the S88 paired-loss CSV omits the pre-burn 47,104/158 rows (metadata only,
  cannot be independently recomputed); ISO weeks 27/28 share four game IDs. S233 (a17, FALSIFIED): no shared
  purge+embargo+seal utility landed; reuse cpcv_engine.py's own `_purged` symmetric-embargo helper instead.
PREMISE (step 0): re-measure and print the S209 numbers from docs/evidence/harness/s88_phase_recal_2026-09-04.csv
  (4,311,731 bytes, sha256 b7cc67e0ff39a8f20b9b12e981ce93c2ace55374b38d9805e092ada99f9ba91d): 33,920 evaluated /
  11,087 informative ticks, 127 informative game clusters; Brier incumbent 0.174603353 / recal 0.176079848 /
  market 0.170852958; 15-bucket raw labels 1 IMPROVED + 1 WORSE -> 0 BH survivors. If falsified, STOP, memo, commit.
LIMIT (step 1): regenerate the full paired-loss series, including the pre-burn 47,104/158 rows, from
  scripts/platformkit/ingame/s88_phase_recal.py's own S06 47,104-tick/158-game partition rather than reading the
  CSV. Count whole-game clusters surviving purge + symmetric embargo. If fewer than 30, CLOSED AT LIMIT.
CHANGE (step 2): one new additive module under scripts/platformkit/ingame/ (e.g. s254_mlb_phase_recal_fwer_sealed.py)
  plus one per-file test: (a) prereg JSON naming 15 buckets, q=0.05, whole-game replication, sealed via the
  existing hashlib.sha256(Path(prereg_path).read_bytes()).hexdigest() pattern (s58_clamp_family_trial.py:222 et
  al.) BEFORE any scoring; (b) import cpcv_engine.py's `_purged` helper read-only for a symmetric nonzero embargo;
  (c) partition replication on whole game clusters, never ISO week. Rails: additive only; helper <= 300 lines
  (test_loc_rail_scope.py); never write data/ (never data/registry/); no flag on; no edits under src/ kernel/
  api/ intel/ scripts/team_system/; one store at a time, <= 300 MB; register and ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = 15-bucket BH q=0.05 table (raw p, BH p, label) plus whole-game-cluster replication, on the
                  regenerated purged+embargoed series; denominator = printed eval/informative tick and cluster n
  before        = S209: 33,920/11,087/127; 0 BH survivors; Q1 FAIL (no sealed prereg), Q4 FAIL (no purge/embargo)
  bar           = the prereg seal predates every score (assert timestamp order); purge + symmetric nonzero
                  embargo assertions pass; replication partitioned on whole game clusters, 0 clusters split
                  across ISO weeks 27/28; the full 15-bucket table is reported -- 0 survivors is a valid result
  n             = >= 30 whole-game replication clusters; 15 buckets (CONSTRUCT, exhaustive)
  eye check     = n/a (S-row); reproduction = the verifier reproduces every raw p, BH p and replication CI from
                  the regenerated archive plus the sealed prereg alone, and re-verifies the seal hash itself
  must not move = q=0.05 and the 15 bucket definitions byte-identical to S209; eval_gate thresholds, the FWER
                  ledger, K, and flags unchanged; nothing charged
NON-TAUTOLOGY: report all 15 buckets (incl. the two losing their raw label under BH) and every whole-game cluster
  excluded by the purge/embargo boundary with its exact reason; never narrow the family to survivors.
EVIDENCE: docs/evidence/harness/S254_mlb_phase_recal_fwer_sealed_2026-09-04.md -- sealed-prereg proof, 15-bucket
  table, purge/embargo log, whole-game replication table, NOT VERIFIED list, summary JSON, paired-loss series (Q9).
TEST: scripts/platformkit/ingame/test_s254_mlb_phase_recal_fwer_sealed.py -- one new per-file test; run only it.
REPORT: seal proof, 15-bucket table, purge/embargo assertions, replication verdict, LIMIT verdict, test, SHA.
  Commit by pathspec, no push. NEVER PARK.
