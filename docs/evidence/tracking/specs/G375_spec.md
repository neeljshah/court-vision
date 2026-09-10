GAP G375 | sport all (basketball ledger first) | worktree a3 | log cx_g375_corpus_sport_purity

**CORPUS SPORT-PURITY ROW (from G364 phase 1 PARTIAL f1d000f7, NEW GAP: the "basketball" tracking ledger contains non-basketball
sections -- `bleague-oW8psSa2hf4_s2598` decodes to LaLiga soccer footage and `fiba--x4DRmtYn4Q_s3530` to press-conference / posed
team-photo content; both passed the feeder's landed content gate, which screens playing-surface colour, border and cut continuity but
never the SPORT).** A Claude finisher PREPARES (prereg sealed alone first) and MEASURES on the pod. `src/`, `kernel/`, `api/`, `intel/`
and the landed gate `scripts/platformkit/footage_content_gate.py` are READ and IMPORT only; any gate change is a PROPOSED diff under
the evidence dir (sha256 in the memo). Build additively in `scripts/platformkit/tracking/g375_*.py`. NEVER write `data/registry/`,
never flip a flag, never move the gate's thresholds, never touch the register, never delete or move a tracked section.

**WHERE THIS ROW RUNS:** ON THE POD, `/workspace/wt/a3` (`python3 -m` from the worktree root; CPU only, <= 4 cores, threads = 1);
ledger + tables `/workspace/data/tracking` READ ONLY (snapshot the ledger first); sources re-fetched only where a sheet needs a
frame the tables do not carry (one native frame per section, yt-dlp recipe, pinned per G361); raters = codex terra + sol ON THE
PC under the RAM gate (free RAM >= 2.8 GB, < 3 codex.exe; one lane at a time; G373/G374 raters share the PC).

**PREMISE (step 0, BINDING before-condition):** on the ledger snapshot, count sections per sport label and per source-tag prefix
(nba / ncaa_basketball / wnba / gleague / fiba / euroleague / bleague / acb / cba / lnb / ...), PRINT the table, and re-decode ONE
native frame for the two named sections; **if both decode to basketball play, the premise is FALSE: STOP, memo, commit, report.**

METHOD (sealed before any rating):
  1. **SAMPLE:** every unique game_id in the snapshot (duplicates collapsed) = the population N; draw 300 sections EVENLY (fixed
     spacing, seeded start; never a head slice), stratified by source-tag prefix proportional to availability, min 10 per prefix
     where available; excluded keys listed.
  2. **SHEET:** one native frame per sampled section at the sealed offset (the section's midpoint tick), <= 200 KB, no overlay.
  3. **BLIND RATING:** terra + sol label each sheet: BASKETBALL_PLAY / BASKETBALL_NONPLAY (bench, crowd, graphics, interviews) /
     OTHER_SPORT (name it) / NON_SPORT / UNKNOWN; disagreements adjudicated blind by the finisher; kappa reported.
  4. **ATTRIBUTION:** for every non-BASKETBALL_PLAY section, which gate decision admitted it (`screen()` accept / review, its
     max_surface_permille, the liveness verdict) from the feeder log where present, else UNKNOWN; per-prefix impurity table.
  5. **PROPOSAL (evidence dir only):** a PROPOSED additive `sport_purity` field for the content gate (a cheap frozen-embedding
     nearest-class score against the G364 dev reference is allowed as the candidate signal; report its separation on the 300 as a
     DIAGNOSTIC, never as a gate result). CHANGE NOTHING ELSE; no flag; no threshold moved.

ACCEPTANCE RULE:
  metric        = impurity share (non-BASKETBALL_PLAY / 300) with Wilson 95 pct bounds, overall and per prefix; OTHER_SPORT and
                  NON_SPORT counts named; kappa; the admitting-gate attribution table
  before        = G364: 2 of 240 development frames were non-basketball content (CROWD_GRAPHICS 40/240 incl. them); no census exists
  bar           = 300 sampled / >= 10 prefixes covered; kappa reported; 100 pct of non-play sections attributed or UNKNOWN; 0 gate
                  thresholds moved; 0 sections deleted; the proposal is a research note only
  n             = 300 sections (SAMPLED, not CONSTRUCT); 2 raters + adjudication; >= 30 per reported prefix, else descriptive
  eye check     = REQUIRED: every OTHER_SPORT / NON_SPORT sheet plus 20 evenly spaced BASKETBALL_PLAY sheets
  must not move = the landed content gate and its thresholds, the feeder, the daemon, every table, `data/registry/`, every flag
  verdict       = **MEASURED** (impurity share with bounds) / **PARTIAL** (name the unmet clause) / **PREMISE FALSE**
EVIDENCE: `docs/evidence/tracking/g375_corpus_sport_purity_2026-09-10.md` (<= 60 lines; VERDICT line 1; NOT VERIFIED; wall time;
SHA-256s) + `.../g375_corpus_sport_purity_2026-09-10/{census.csv,sample.csv,excluded.csv,ratings.csv,reference.csv,attribution.csv,
summary.json,sheets/,PROPOSED_sport_purity_gate.md}`. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT.**
TEST: `tests/platformkit/test_g375_corpus_sport_purity.py` alone (even stratified sampler never a head slice; excluded keys listed;
the seal). **NEVER a full pytest.** Every new file <= 300 lines. Vocabulary follows contract Q6; automated scan required. Prereg sealed
as its OWN commit first (`SEAL sha256 <hex>`). ASCII stdout. **NEVER PARK.**

VERSION 2026-09-10
