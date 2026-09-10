GAP G364 | sport basketball | worktree a13 | log cx_g364_learned_court_presence

**LEARNED COURT-PRESENCE ROW, CONDITIONAL SUCCESSOR TO G360 (PARTIAL 2026-09-09 8bb0f91ba: the sealed 22-unit
premise could not be reconstructed -- 10 of 22 units were named by NBA game id only and had no re-fetchable video
id; on the 12 recoverable units the line-family cue was ANTI-correlated (AUC 0.091) and the surface cue rested on a
single positive; the prereg's NON_COURT branch (zero long segments) is reachable on 013 per mille of sampled frames,
so a rule-based held-out set cannot be balanced). Codex PREPARES, a Claude finisher trains and scores on the pod
GPU, blind model raters build the reference.** `src/`, `kernel/`, `api/`, `intel/` are READ and IMPORT only. Build in
`scripts/platformkit/tracking/g364_*.py`. NEVER write `data/registry/`, never flip a flag, never edit the landed content
gate or the router thresholds, never touch the register.

**WHERE THIS ROW RUNS:** ON THE POD, in `/workspace/wt/a3` (`python3 -m` from the worktree root; one RTX 3090; frozen
backbone only -- no fine-tuning of the backbone; cache embeddings once). Sections are re-fetched with
`/workspace/YTDLP_RECIPE.txt` and EVERY source is PINNED by YouTube id + requested offset + sha256 + fetch UTC in
`sources.csv` BEFORE any frame is used (G361 identity rules; an NBA game id alone is NOT a source). Scratch under
`/workspace/g364_scratch/` (< 5 GB, deleted after embedding); never write into `data/footage_bridge`.

**PREMISE (step 0, BINDING before-condition):** re-read G360's `premise.csv` and `balance_probe.csv` and PRINT: (a) no
rule cue reaches AUC >= 0.75 on >= 2 positives; (b) the rule's NON_COURT reach is < 020 per mille of sampled frames.
**If a rule cue reaches AUC >= 0.75 on >= 5 positives AND its negative reach is >= 020 per mille, the premise is
FALSE: STOP, memo, commit, report PREMISE FALSE (G360 is then finished instead).**

METHOD (sealed before any rating or training):
  1. **BACKBONE + HEAD:** frozen features from a weights file already on the box (torchvision ImageNet weights
     cached offline, or the deployed YOLO backbone) named by sha256 in the prereg; a linear / logistic head over
     pooled features; classes USABLE_COURT / CLOSEUP / CROWD_GRAPHICS / UNKNOWN; an abstention band on the head's
     margin, threshold PREREGISTERED on development only.
  2. **DEVELOPMENT SET:** >= 20 sections / >= 8 games / >= 3 competitions, pinned; 12 EVENLY spaced interior
     positions per section (never a head slice); labels from two blind model raters (terra, sol) on sheets carrying
     NO score, adjudicated blind; development labels are never reused for validation.
  3. **VALIDATION SET (sealed BEFORE rating, game-DISJOINT from development):** >= 300 frames / >= 30 sections /
     >= 10 games / >= 3 competitions, even sampling; quotas by the FROZEN head's prediction (>= 60 predicted court,
     >= 60 predicted non-court, the rest from the abstention band). Measure the negative reach on development FIRST:
     if predicted non-court is < 020 per mille there, report LIMIT instead of sampling thousands of frames.
  4. **RATING:** terra + sol blind on validation sheets (frame + 3-frame strip, <= 200 KB); adjudication blind by
     the delegate; Cohen kappa; UNKNOWN retained with its share.
  5. **SCORING:** confusion; precision of predicted court and recall of USABLE_COURT with Wilson 95 pct intervals;
     abstention share; per-competition breakdown; the head and threshold are FROZEN before the validation split is
     touched (B8: no refit, no second candidate).
  6. **CONSUMER (only if VALIDATED):** a PROPOSED feeder gate line (docs/research, sha256 in the memo) and the
     G362 section-selection text; no src hook; no flag. CHANGE NOTHING ELSE.

ACCEPTANCE RULE:
  metric        = the premise printout; `sources.csv`; dev/validation censuses; both raters' sheets + adjudication
                  with kappa; confusion; precision / recall with intervals; abstention; per-competition
  before        = no validated court-presence gate (G350 WIDE 0.10; G360 rule cues refuted / unbalanceable)
  bar           = validation sealed before rating, game-disjoint, evenly sampled; >= 300 frames / >= 30 sections /
                  >= 10 games / >= 3 competitions; >= 30 per scored class; precision >= 0.90 AND recall >= 0.80;
                  0 score values leaked into sheets; 0 threshold or head changes after the seal; 0 src edits
  n             = >= 300 validation frames; 2 raters + adjudication
  eye check     = REQUIRED: the rated sheets are the evidence (<= 200 KB each, committed)
  must not move = `src/`, `data/`, `data/registry/`, the content gate, the router thresholds, every flag, the daemon
  verdict       = **VALIDATED** / **NOT VALIDATED** with the numbers / **LIMIT** (negative reach) / **PARTIAL** /
                  **PREMISE FALSE**
EVIDENCE: `docs/evidence/tracking/g364_learned_court_presence_2026-09-09.md` (<= 60 lines; VERDICT line 1; NOT
VERIFIED; GPU minutes; SHA-256s) + `.../g364_learned_court_presence_2026-09-09/sources.csv`, `dev.csv`,
`validation.csv`, `ratings.csv`, `confusion.csv`, `model.json` (feature extractor sha256, head weights, threshold),
`sheets/`, `raters/`. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT.**
TEST: `tests/platformkit/test_g364_learned_court_presence.py` alone (synthetic embeddings train a separable head;
the sampler never returns a head slice; the sheet builder writes no score; validation games are disjoint from
development). **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: codex prepares the prereg (sealed alone: backbone + head definition, abstention rule, sampling
rules, quotas, label set, bars), the embedder, the sampler, the sheet builder, the trainer, the scorer, the test and
the memo skeleton, exits `agent: PREPARED FOR FINISHER` with `python3 -m` commands; the Claude finisher pins sources,
embeds, trains on development, freezes, seals validation, runs the blind raters and scores (Q1). Vocabulary follows
contract Q6; automated scan required. COMMIT: explicit pathspec only; prereg sealed as its OWN commit first (`SEAL
sha256 <hex>`). ASCII stdout. **NEVER PARK.**

VERSION 2026-09-09
