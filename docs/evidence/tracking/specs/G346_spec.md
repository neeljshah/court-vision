GAP G346 | sport all | worktree aX | log cx_g346_frozen_video_gate

**CORPUS DEFECT ROW: FROZEN / STATIC VIDEO SECTIONS (local + pod census; codex PREPARES, a finisher
MEASURES).** `src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in `scripts/platformkit/`
(the feeder gate lives in `scripts/platformkit/footage_content_gate.py` -- extend, never fork). NEVER write
`data/registry/`, never flip a flag, never delete a section, never touch
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHERE THIS ROW RUNS:** the gate + tests LOCALLY (conda `basketball_ai`; synthetic constructs); the census
on the pod corpus under `/workspace/wt/<wt>/` (CPU only, nice -n 19; read the pod corpus and the ledger
read-only; never touch the daemon pid 1596016 or the guards; nohup detached; short polls).

**WHY THIS ROW EXISTS.** G338 (2026-09-08) measured that 2 of its 6 sealed sections were FROZEN video:
`basketball__eurocup-qrWmO434a0k_s90.mp4` (mean absolute inter-frame delta 0.18 over the sealed indices,
~1,208 bytes per frame) and `nba__XCaGht2GmPg_s6720.mp4` (delta 2.65, ~1,150 bytes per frame) against
8,237-18,057 bytes per frame on live sections; both produced ZERO person rows at every detector input size.
A frozen section costs a daemon slot, lands a degenerate ledger row and pollutes every census denominator.
The ingest gate (`footage_content_gate.py`) does not measure temporal liveness. Also from G338: the corpus
holds 4 sections at 1280x720, ALL from one game -- resolution cohorts are confounded with games.

**PREMISE (step 0, BINDING before-condition):** print the gate's current checks (`file:line`) and confirm
none measures inter-frame change; on the two G338 sections (copy read-only from the pod, or from the local
staged corpus if present) print bytes per frame and the mean absolute inter-frame delta at 320x180 over
>= 60 sampled frames. **If the gate already rejects them, the premise is FALSE: STOP, write the memo,
commit, report PREMISE FALSE.**

METHOD:
  1. **LIVENESS CHECK (additive, `footage_content_gate.py` or a sibling `footage_liveness.py`, <= 150
     lines):** sample 60 frames spread across the file at 320x180 grayscale; mean absolute inter-frame
     delta (0-255 scale) and the share of consecutive pairs with delta < 1.0; bytes per frame from
     container size / frame count. Verdict FROZEN when the share of near-identical pairs >= 0.90 OR bytes
     per frame < 2,000 at >= 720p (proposed thresholds -- prereg them; report both cues separately).
     Additive field `liveness` in the gate's report; the gate's existing decisions do not change in this
     row (no flag flip): the new field is REPORTED and a `--reject-frozen` option defaults OFF.
  2. **CENSUS (finisher, pod):** run the liveness check over every section currently in the pod corpus
     and every source the ledger lists with rows < 50 (the degenerate rows G329 found); table: n sections,
     n FROZEN, n LIVE, bytes-per-frame quantiles, delta quantiles; cross with the ledger: how many
     FROZEN sections produced ledger rows and with how many rows (n). Resolution x game cross-table
     (n sections per resolution, n distinct games per resolution) to state the confound.
  3. **FEEDER HOOK PROPOSAL.** A <= 10-line PROPOSED change to the local feeder (the scratchpad feeder
     scripts are orchestrator tooling; the repo-side bridge is `scripts/platformkit/footage_bridge.py`)
     that runs the liveness check after the cut and skips shipping a FROZEN section, as a PROPOSED
     snippet in the memo (the orchestrator applies it to the feeder).
  4. **TESTS.** Synthetic: a 60-frame all-identical clip -> FROZEN; a clip with moving noise -> LIVE; the
     gate's existing per-file test still passes unchanged; the default path (option OFF) is byte-identical.
  5. CHANGE NOTHING ELSE. Never delete a section in this row (deletion is the volume guard's job and needs
     the ledger row; say so).

**HONEST LIMITATIONS to state, not discover:** a static wide shot of an empty court is LIVE but useless
(the view class is G341's); thresholds are proposals; the census is a snapshot of a rotating corpus (G335
lesson: seal the file list and digests at census time).

ACCEPTANCE RULE:
  metric        = premise prints; the liveness check + tests; the corpus census with n; the ledger cross;
                  the resolution x game table; the PROPOSED feeder hook
  before        = no temporal liveness check anywhere in ingest; two of six G338 sections were frozen
  bar           = both G338 sections classify FROZEN and >= 3 sealed live sections classify LIVE; the
                  default gate path is byte-identical (test); every census cell carries n; 0 deletions
  n             = every section in the pod corpus at census time (sealed list); 60 frames each
  eye check     = OPTIONAL: one contact sheet of 6 sampled frames for each FROZEN section (<= 150 KB)
  must not move = `src/`, `data/`, `data/registry/`, every gate decision, every flag, the pod daemon and
                  guards, every section file, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** with the item that failed and why.
EVIDENCE: `docs/evidence/tracking/g346_frozen_video_gate_2026-09-08.md` (<= 60 lines; VERDICT line 1; tables;
NOT VERIFIED; wall time; SHA-256s) + `.../g346_frozen_video_gate_2026-09-08/census.csv` and
`resolution_games.csv` (integer cells zero-padded to 6 digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME
COMMIT** (one `>>` append, LF). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g346_footage_liveness.py` plus the gate's existing test file, each alone.
**NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: thresholds, sample rule), the check,
the tests and the memo skeleton, and exits `PREPARED FOR FINISHER` with the exact pod census command; it
must NOT run the census itself (Q1). Absent sections or `data/registry` in the worktree are reported, never
a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
