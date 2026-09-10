GAP G374 | sport basketball | worktree a10 | log cx_g374_court_presence_validation

**VALIDATION ROW FOR THE FROZEN G364 HEAD, SUCCESSOR TO G364 PHASE 1 (PARTIAL 2026-09-10 c6dd183f4: development reference complete --
240 blind sheets, terra+sol kappa 0.916186, 125 USABLE_COURT / 74 CLOSEUP / 40 CROWD_GRAPHICS / 1 UNKNOWN; ResNet-18 frozen features
(resnet18-f37072fd.pth); head FROZEN at the sealed threshold 0.30 before any validation fetch; development NON_COURT reach 479.166667 per
mille vs G360's rule 13.020833; the SEALED validation quota (60 COURT / 60 NON_COURT / 180 from ABSTAIN out of 300) is UNSATISFIABLE
because the frozen head abstains on only 14 of 360 validation-pool frames (38.888889 per mille), so no validation frame was rated and no
metric exists).** Codex PREPARES the quota rule + sampler + scorer bindings, a Claude finisher draws, rates (blind terra + sol) and scores.
`src/`, `kernel/`, `api/`, `intel/` READ and IMPORT only. Build additively in `scripts/platformkit/tracking/g374_*.py` (import
`g364_sampler` / `g364_sheets` / `g364_score` / `g364_predict`; copy none). NEVER write `data/registry/`, never flip a flag, never move
the frozen threshold 0.30, never refit the head, never touch the register.

**WHERE THIS ROW RUNS:** ON THE POD, `/workspace/wt/aXX`; the G364 lane artifacts (validation_pool.csv, validation_predictions.csv,
validation_pool_embeddings.npz, model.json, model_identity.json, sources_validation.csv) are READ ONLY inputs, pinned by sha256 in the
prereg; no GPU (predictions already exist); raters on the PC under the RAM gate.

**PREMISE (step 0, BINDING before-condition):** re-read model.json / model_identity.json / validation_predictions.csv and PRINT: the head
sha256 and threshold (expect 0.30), the pool census (expect 360: 224 COURT / 122 NON_COURT / 14 ABSTAIN) and the game-disjointness
against dev.csv (expect empty overlap). **If the frozen head or threshold differs from G364's landed model_identity.json, the premise is
FALSE: STOP, memo, commit, report (a refit happened; G364 stays PARTIAL and this row does not score).**

METHOD (sealed before any draw):
  1. **ADJUDICATED QUOTA (the fix, sealed here, never adapted after a draw):** draw 300 keys from the 360-frame pool as: ALL ABSTAIN frames
     (14); then COURT and NON_COURT strata filled EVENLY (fixed spacing, seeded start) with counts proportional to availability, capped so
     each stratum contributes >= 60 and the total is exactly 300; every excluded key listed with its reason; nothing depends on a label.
  2. **BLIND RATING:** sheets built from the 300 keys before any label is read (<= 200 KB each; the G364 renderer); raters terra + sol
     label the four classes with no prediction shown; disagreements adjudicated blind by the finisher; kappa reported.
  3. **SCORE ONCE:** precision / recall / Wilson 95 pct for USABLE_COURT vs the reference, abstention share, per-competition table; the
     reference-mode confusion.csv fields `scope, prediction, reference_label, count` and the prediction manifest fields `frame_key,
     prediction, court_probability, model_sha256` (astra's G372 handoff keys) are emitted byte-for-byte.
  4. **CONTROL:** the development in-sample numbers are re-printed beside the validation numbers and labelled NOT evidence (B8).
  5. CHANGE NOTHING ELSE; no threshold move; no refit; no flag; no src hook.

ACCEPTANCE RULE:
  metric        = validation precision and recall for USABLE_COURT with Wilson 95 pct bounds; abstention share; kappa; per-competition
  before        = G364 phase 1: no validation metric exists; dev NON_COURT reach 479.166667 per mille (in-sample)
  bar           = precision >= 0.90 AND recall >= 0.80 on the sealed 300 (Wilson lower bounds reported beside the point estimates);
                  >= 60 rated per predicted stratum; kappa reported; 0 threshold moves; 0 refits
  n             = 300 frames / >= 15 games / >= 8 competitions (the pinned pool); 2 raters + adjudication
  eye check     = REQUIRED: 30 evenly spaced sheets with both ratings and the prediction, incl. every ABSTAIN frame
  must not move = the frozen head (sha256), threshold 0.30, the dev reference, the G360 content gate, every flag, `data/registry/`
  verdict       = **VALIDATED** / **PARTIAL** (name the unmet bar) / **PREMISE FALSE** with the numbers
EVIDENCE: `docs/evidence/tracking/g374_court_presence_validation_2026-09-10.md` (<= 60 lines; VERDICT line 1; NOT VERIFIED; wall time;
SHA-256s) + `.../g374_court_presence_validation_2026-09-10/{validation.csv,excluded.csv,ratings.csv,reference.csv,predictions.csv,
confusion.csv,summary.json,sheets/}`. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT.**
TEST: `tests/platformkit/test_g374_court_presence_validation.py` alone (quota never exceeds availability; even draw is not a head slice;
excluded keys listed; the seal). **NEVER a full pytest.** Every new file <= 300 lines. Vocabulary follows contract Q6; automated scan required.
Prereg sealed as its OWN commit first (`SEAL sha256 <hex>`). ASCII stdout. **NEVER PARK.**

VERSION 2026-09-10
