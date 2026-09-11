GAP G385 | sport basketball | worktree a13 | log cx_g385_nonplay_shadow_mask
**RANK 4 - MEASURE A NON-PLAY ADMISSION MASK. Landed docs/evidence/tracking/g375_corpus_sport_purity_2026-09-10/summary.json SHA-256 87e23d4fd9900dd421756996de814300d4c7c67a175b9ddbb7694c68c1a54a0a; labels.csv SHA-256 84a7d8e26f54f3043b4b5ca5c505e0d54301db52abca18fa123e6cf01300c834. G375's presence-neighbour diagnostic did not establish sport identity; this row measures non-play masking separately from known-video identity.**
**WHERE THIS ROW RUNS:** PC development/reference and CPU scoring; pod frozen embedding extraction only if needed. 30 min prepare, 100 reference, 30 scoring, 20 receipt; no feeder or daemon caller.
**PREMISE (step 0, BINDING before-condition):** reproduce G375's 127/281 non-play midpoints and six OTHER_SPORT frames from one video. Census the whole candidate source pool against ALL G375/G364 development video IDs.
Require 30 preserved, development-disjoint sections from >=10 videos for the fixed draw; insufficient supply -> NOT VALIDATED, no label reuse as confirmation. If an independently validated mask already exists, report PREMISE FALSE.
METHOD (sealed before fresh validation ratings):
1. Build ONE dev-only classifier from G375's frozen ResNet-18 embeddings and definite labels: L2 logistic regression, C=1, balanced classes, solver liblinear, seed 385, max_iter=1000; UNKNOWN excluded from training only and explicitly listed.
2. Train PLAY versus definite NONPLAY/OTHER_SPORT/NON_SPORT, freeze weights/preprocessing/hash before validation. Mask a tick only at p(non-play)>=0.95; other readable ticks KEEP; missing/invalid evidence UNKNOWN and passes through.
3. Draw 30 eligible sections evenly across competition/video/time; 12 even strictly interior ticks per section =360 planned frames. Pin/copy pixels first; no midpoint-only whole-section decision.
4. Terra and sol independently label all native frames PLAY/NONPLAY/OTHER_SPORT/NON_SPORT/UNKNOWN without scores; adjudicate blind, preserve disagreements. Publish sampled tick masks only, never infer that an unobserved part of a section is non-play.
5. Score false masks on true PLAY, captured definite non-play, UNKNOWN/pass-through and milliseconds per section. Preserve original gate decisions beside the proposed mask, full schemas and all 360 attempted ticks.
6. Report a separate exact-ID known-video mask for G375's soccer source as a descriptive control. One source is not a learned sport classifier, and fewer than 30 examples cannot validate sport rejection.
7. Any feeder/daemon integration is a PROPOSED diff only; no section quarantine, deletion, source relabelling, claim suppression or production mask.
ACCEPTANCE RULE:
| field | binding value |
|---|---|
| metric | False masks/all reference PLAY; masked/all definite non-play; UNKNOWN/all planned frames; paired gate/mask decisions and runtime. |
| before | 452 per mille non-play at G375's rated midpoints; no independently scored tick mask. Fresh sample before = unmasked counts on exactly these same 360 keys. |
| bar | >=30 PLAY and >=30 definite non-play; Wilson95 upper false-mask rate <=0.05 and lower non-play capture >=0.50; all 360 attempts represented; zero masks from absent evidence. No general sport-purity claim. |
| n | 360 planned frames/30 sections/>=10 videos; each scored class >=30, else PARTIAL. Class counts and uncertainty may make the bars infeasible; no top-up after labels. |
| eye check | 30 evenly spaced validation frames plus every harmful PLAY mask as supplemental renders, without changing the scored set. |
| must not move | Live feeder/daemon/content gate, source tables, G374 threshold, all masks/flags and original G375 labels; no shared-module edit. |
| verdict | DONE if all proposed mask bars pass; PARTIAL/NOT VALIDATED otherwise. Every result remains an unused research mask. |
EVIDENCE: docs/evidence/tracking/g385_nonplay_shadow_mask_2026-09-10.md and matching directory with dev_exclusions.csv, model_identity.json, frames.csv, ratings.csv, reference.csv, paired_masks.csv, confusion.csv, runtime.csv, summary.json, renders/ and common receipts.
TEST: tests/platformkit/test_g385_nonplay_shadow_mask.py alone: missing input passes through, dev-video disjointness, full planned denominator, additive schema and no section-level suppression.
VERSION 2026-09-10 - proposed; new mask bars are prospective and fixed.


ORCHESTRATOR FOOTER (binding, 2026-09-10 night): codex terra PREPARES (prereg sealed alone as its OWN commit, `SEAL sha256 <hex>` over every byte above the seal line); a Claude finisher MEASURES; codex-sol VERIFIES; `src/`, `kernel/`, `api/`, `intel/` READ only (PROPOSED diffs only); never write `data/registry/`, never flip a flag, never touch the register; **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** as the memo; every new file <= 300 lines; vocabulary follows contract Q6 with an automated scan (patterns built from character codes); n >= 30 with even sampling; ASCII stdout; **NEVER PARK.** Astra source: docs/research/astra_night_review_2026-09-10.md (local-only).
