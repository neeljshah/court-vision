GAP G377 | sport all | worktree a19 | log cx_g377_restore_receipt

**RETAIN-AND-RESTORE ROW (astra pod-loss review 2026-09-10 section E and next-rows review seed RETAIN_AND_RESTORE): hashes and a
synced directory count are not proof that an off-pod bundle restores native evidence and scoring state. Today's losses: G369 20/55
sources gone at pin time; G368 lost 53 of G366's 59 sections and the 6 survivors DIFFER; G370 25/118 pinned tables mutated under the
live daemon; the 09-09 pod's disk vanished with G367/G364 phase-1 work.** A Claude finisher PREPARES (prereg sealed alone) and
MEASURES on the PC (receiver side) with read-only pod probes. `src/`, `kernel/`, `api/`, `intel/` READ only. Build additively in
`scripts/platformkit/tracking/g377_*.py`. NEVER write `data/registry/`, never flip a flag, never delete or prune anything, never touch
the register.

**WHERE THIS ROW RUNS:** on the PC from the off-pod copies (lane branches `pod/track-a7 a13 a10 a18` = the G363 / G364 / G367 / G370
closures on master and their landed evidence dirs; `data/pod_backup_2026-09-10/tracking` + the synced ledger; the private remote's
`backup/track-*` refs) into an ISOLATED scratch root (never the original paths); pod access READ ONLY (`sha256sum`, `ls`, `git show`)
to compare receiver bytes against the live copies where they still exist. CPU only; the PC RAM gate applies (free >= 2.8 GB; one
python process < 800 MB RSS).

**PREMISE (step 0, BINDING before-condition):** for each of the four closures list every file the landed memo names or the row's
readers open (scripts/platformkit/tracking/g363_*.py, g364_*.py, g367_*.py, g370_*.py import paths and their evidence-dir reads) and
PRINT: files named / files present off-pod / files present on the pod / bytes; **if all four closures are 100 pct present off-pod
with matching digests before any restore, the premise is FALSE for the recovery part: STOP that part, report, continue the
readback-and-recompute part only.**

METHOD (sealed before any number):
  1. **DEPENDENCY MANIFEST** per closure: path, role (prereg / reference / prediction / native pixels / code / test / ledger row),
     required-by (file:line of the reader), off-pod location, digest; missing = named, never inferred.
  2. **RESTORE** each closure into `<scratch>/<row>/` from off-pod sources only, byte-verify against the committed blob (`git
     hash-object --no-filters` / `git cat-file`) and against the live pod copy where present; native pixels come only from committed
     sheets/PNGs or the synced tracking store, never from a re-fetch (a re-fetch is a NEW identity and is reported as such).
  3. **RECOMPUTE** one archived decision per closure from the restored bytes with the landed code (G363 held-out C0 from
     predictions + reference; G364 dev confusion from ratings + predictions; G367 recovery.csv from the fixtures; G370 usable-control
     rejection from controls.csv) and diff against the archived summary values byte-for-byte.
  4. **RETENTION CONTRACT (proposal, evidence dir only):** identity-before-prune -- a prune candidate is eligible only after a
     receiver acknowledgement (digest + readback) exists; reader leases for sealed sets; versioned identities for moved / re-supplied
     sources; a byte budget derived from the measured ~41 GB quota and today's ~1.8 GB/h table growth.
  5. CHANGE NOTHING ELSE; no prune, no flag, no src hook.

ACCEPTANCE RULE:
  metric        = restorable required files / entire manifest per closure; digest agreement; recomputed decisions / archived decisions
  before        = no restore receipt exists; today's losses as enumerated above
  bar           = 100 pct digest and identity agreement for every file present off-pod; 100 pct of recomputed decisions equal to the
                  archived values; every missing file NAMED with the row it disables; 0 replenished held-out executions; 0 deletions
  n             = 4 closures (CONSTRUCT; exhaustive enumeration, no sampling)
  eye check     = REQUIRED: 8 restored native pixels (2 per closure) shown beside their committed sheets
  must not move = every seal, bar, flag; the live pod bytes; original evidence paths (scratch only)
  verdict       = **DONE** / **PARTIAL** (name the closure and the missing files) / **PREMISE FALSE** (recovery part)
EVIDENCE: `docs/evidence/tracking/g377_restore_receipt_2026-09-10.md` (<= 60 lines; VERDICT line 1; NOT VERIFIED; wall time;
SHA-256s) + `.../g377_restore_receipt_2026-09-10/{dependency_manifest.csv,restore_hashes.csv,decision_diff.csv,missing.csv,
PROPOSED_retention_contract.md,summary.json,eye/}`. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT.**
TEST: `tests/platformkit/test_g377_restore_receipt.py` alone (a missing file is NAMED not skipped; a digest mismatch fails the
closure; the seal). **NEVER a full pytest.** Every new file <= 300 lines. Vocabulary follows contract Q6; automated scan required.
Prereg sealed as its OWN commit first (`SEAL sha256 <hex>`). ASCII stdout. **NEVER PARK.**

VERSION 2026-09-10
