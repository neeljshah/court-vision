GAP G386 | sport basketball first | worktree a22 | log cx_g386_pin_copy_one_pass
**RANK 5 BY DIRECT QUALITY, FIRST TO DISPATCH AS INFRASTRUCTURE. G379 lost 16/29 pinned sources within about 30 min. Landed docs/evidence/tracking/g377_restore_receipt_2026-09-10/summary.json SHA-256 97c2933ab366da9c1c4a267a80fbe905cb0493228581e8bd3bf170f5c05a6f8c; G379 summary hash is cited in G382. A hash without retained reader bytes does not preserve rated pixels.**
**WHERE THIS ROW RUNS:** pod read-only source access plus own bounded staging; PC receiver stores and reads back bytes. CPU/network only; 40 min preparation, 90 capture, 30 controls, 20 receipt.
**PREMISE (step 0, BINDING before-condition):** inventory every source needed by G379/G373/G378 readers and existing receiver receipts; distinguish a manifest, a retained native image and a retained replay source.
If an existing tool proves one-pass capture and receiver readback for >=30 distinct sections, report PREMISE FALSE and reuse it. Otherwise census the complete available pool; fewer than 30 -> preparation-only NOT VALIDATED, no uncontrolled waiting.
METHOD (sealed before capture metrics):
1. Freeze a 30-section even draw over video/time ordering from the whole metadata census, >=10 videos; preserve all failed attempts. Choose the reader contract before reading: full source for replay, or sealed native target/context pixels for rating only.
2. Open each selected source ONCE; stream that handle into own staging while computing raw SHA-256 and byte count. Record before/after handle metadata; detect mutation, short reads and errors. Never hash then reopen a possibly replaced pathname.
3. Decode/probe the captured copy, not the live name: archive full source path, size, dimensions, codec, frame indices/PTS, crop/scale and pixel/context hashes. A transform has its own identity; a JPEG sheet cannot stand in for its native source.
4. Send the required bytes and manifest to the PC; receiver writes a temporary object, reads it back independently, hashes it, opens every requested pixel and acknowledges an immutable content/version ID.
5. State CAPTURED only after receiver acknowledgement; filename reuse creates a new version. Read failures stay ABSENT/CHANGED, never a silent substitute or a reason to block production tracking.
6. Process bounded batches, staging <=1.5 GB and all own scratch <2 GB; source files never removed. Release only this tool's staging after reader inventory, fulfilled leases and receiver receipt; preserve required full clips off-pod for replay rows.
7. In scratch only, simulate unlink/replacement during capture, concurrent mutation, short read, receiver corruption and retry. No live prune or guard changes; repeat manifest export from fixed captured inputs twice.
ACCEPTANCE RULE:
| field | binding value |
|---|---|
| metric | Receiver-verified captures/all 30 sealed attempts; verified required objects/all reader-required objects; mutation detection, false receipts and repeat manifest identity. |
| before | G379 lost 16/29 pins; G377 retained 1,377 byte-verified files but named 13 missing dependencies. No one-pass guarantee established. |
| bar | 30/30 captured or explicitly failed attempts accounted for; capture coverage 1.000 required for DONE; 100 pct receiver byte/pixel agreement; zero false CAPTURED receipts; every scratch control exact; repeat exports identical. |
| n | 30 distinct sections/>=10 videos, even sample; reader objects exhaustive within those contracts. Constructed faults never count toward the sampled n. |
| eye check | 30 native receiver renders, one sealed interior frame per section evenly spread across the draw; failed captures receive missing cards, never replacement sources. |
| must not move | Feeder/daemon/guard, live corpus and tracking files, historical identities/seals, flags/registry; no deployment, deletion or restart outside own staging. |
| verdict | DONE for complete preserved sample and controls; PARTIAL/NOT VALIDATED for losses/insufficient supply; PREMISE FALSE if existing tool already proves this contract. |
EVIDENCE: docs/evidence/tracking/g386_pin_copy_one_pass_2026-09-10.md and matching directory with reader_contract.csv, census.csv, attempts.csv, source_identity.csv, receiver_receipts.csv, pixel_checks.csv, faults.csv, export_hashes.json, summary.json, renders/ and common receipts.
TEST: tests/platformkit/test_g386_pin_copy_one_pass.py alone: replaced-path handle identity, mutated/truncated input, independent receiver corruption, versioned retry and receipt-before-staging-release.
VERSION 2026-09-10 - proposed; no retention or admission policy is deployed.


ORCHESTRATOR FOOTER (binding, 2026-09-10 night): codex terra PREPARES (prereg sealed alone as its OWN commit, `SEAL sha256 <hex>` over every byte above the seal line); a Claude finisher MEASURES; codex-sol VERIFIES; `src/`, `kernel/`, `api/`, `intel/` READ only (PROPOSED diffs only); never write `data/registry/`, never flip a flag, never touch the register; **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** as the memo; every new file <= 300 lines; vocabulary follows contract Q6 with an automated scan (patterns built from character codes); n >= 30 with even sampling; ASCII stdout; **NEVER PARK.** Astra source: docs/research/astra_night_review_2026-09-10.md (local-only).
