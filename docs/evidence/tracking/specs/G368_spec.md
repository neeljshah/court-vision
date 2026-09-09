GAP G368 | sport all (basketball fixtures first) | worktree a12 | log cx_g368_evaluated_tick_motion

**PRODUCER-AUDIT ROW, SUCCESSOR TO G366 (PARTIAL 2026-09-09 c1b7b211: on 59 fresh sections the evaluated-tick
ratio -- M1 collapsed rows / the ledger's `evaluated_frames` -- has median 0.153 (p10 0.023, p90 0.554), i.e. the
producer writes a position update on far fewer ticks than it reports as evaluated; positions are HELD across
evaluated ticks, not only between them; `stationary_track_share` rejects 12/59 unplanted fresh sections under both
arms). Codex PREPARES, a Claude finisher MEASURES on the pod.** `src/` (the producer: `src/pipeline/unified_pipeline.py`,
`src/tracking/*`) is READ and IMPORT only -- this row ATTRIBUTES held runs to producer branches by reading the code
and the tables; any producer change is a PROPOSED diff under `docs/research/organization-sprint/` (sha256 in the
memo), never applied here. Build in `scripts/platformkit/tracking/g368_*.py`. NEVER write `data/registry/`, never
flip a flag, never move a sealed threshold, never touch the register.

**WHERE THIS ROW RUNS:** ON THE POD, in `/workspace/wt/a12` (`python3 -m` from the worktree root; tables under
`data/tracking` -> `/workspace/data/tracking`, READ ONLY; snapshot the ledger first). Fresh sections = the G366
fresh set (`fresh_sections.csv`, 59 sections / 14 games, on master) plus any newer clips that satisfy the same
eligibility, pinned per G361.

**PREMISE (step 0, BINDING before-condition):** recompute, on the G366 fresh set, per section: rows n, evaluated
ticks n (the row builder's own tick marker if the table carries one, else the ledger's `evaluated_frames` /
stride), and the share of evaluated ticks on which at least one track's (x, y) CHANGES vs the previous tick.
PRINT the table. **If the median motion share is >= 0.90 (positions move on nearly every evaluated tick), the
premise is FALSE: STOP, memo, commit, report PREMISE FALSE (G366's ratio would then be a collapse-rule artifact,
which the memo must say).**

METHOD (sealed before any number):
  1. **HELD-RUN CENSUS (`held_runs.csv`):** per track: run lengths (in evaluated ticks) of byte-identical (x, y);
     per section: the distribution (p50 / p90 / max), the share of ticks inside runs of length >= 2, >= 5, >= 30.
  2. **ATTRIBUTION (`attribution.csv`):** read the producer once (cite file:line for every branch) and name every
     path that can emit a row without a fresh detection-driven position: e.g. coasting / prediction-only rows, the
     `inferred` flag gating (G333), off-frame handling, re-identification holds, ball-table carry-over. For each
     held run, attribute it to a branch using the fields the table carries (`inferred`, `coast*`, `status`,
     confidence, detection flags -- name them) or mark UNATTRIBUTED. Bar: >= 0.95 of held ticks attributed.
  3. **CONTROLS:** (a) a synthetic table where every tick moves -> motion share 1.000, 0 held runs; (b) a synthetic
     table with a planted 30-tick coast flagged `inferred` -> attributed 100 pct; (c) the G358 sealed 34 sections
     as a second corpus snapshot (report the same tables; no bar).
  4. **CONSEQUENCE TABLE:** for each held-run class, whether M1 (G359) removes it, keeps it, or splits it; and the
     motion share after removing attributed coasting rows -- the number the teacher admission filter needs.
  5. **PROPOSAL (docs/research only):** if >= 0.20 of evaluated ticks are producer coasts, a PROPOSED diff that
     stamps every row with `position_source in {DETECTION, PREDICTION, HELD}` (additive column), with its sha256 in
     the memo; no src edit, no flag. CHANGE NOTHING ELSE.

ACCEPTANCE RULE:
  metric        = motion share per section (median, p10, p90); held-run distributions; attribution shares per
                  branch with file:line; UNATTRIBUTED share; the consequence table; the two synthetic controls
  before        = G366: tick-ratio median 0.153; stationary rejection 12/59; no attribution
  bar           = >= 30 fresh sections / >= 10 games; attribution >= 0.95 of held ticks; controls exact; every
                  branch cited by file:line; 0 src edits; the proposal (if any) is a research note only
  n             = >= 30 sections (CONSTRUCT over the fresh set + G358's 34 as a second snapshot)
  eye check     = REQUIRED: 10 evenly spaced strips (one track's x/y vs tick with held runs shaded) <= 200 KB
  must not move = `src/`, every sealed threshold, `data/`, `data/registry/`, every flag, the daemon
  verdict       = **DONE** / **PARTIAL** (name the unattributed share) / **PREMISE FALSE**
EVIDENCE: `docs/evidence/tracking/g368_evaluated_tick_motion_2026-09-09.md` (<= 60 lines; VERDICT line 1; NOT
VERIFIED; wall time; SHA-256s) + `.../g368_evaluated_tick_motion_2026-09-09/motion.csv`, `held_runs.csv`,
`attribution.csv`, `consequence.csv`, `controls.csv`, `strips/`, `summary.json`, `PROPOSED_position_source.md`
(if written; docs/research copy cited by sha256). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT.**
TEST: `tests/platformkit/test_g368_evaluated_tick_motion.py` alone (the two synthetic controls; the run-length
census on a constructed table; an unattributed run stays UNATTRIBUTED; the seal check). **NEVER a full pytest.**
Every new file <= 300 lines.
DIVISION OF LABOUR: codex prepares the prereg (sealed alone: the tick marker rule, run definition, branch list with
file:line, attribution rule, bars), the modules, the test and the memo skeleton, exits `agent: PREPARED FOR
FINISHER` with `python3 -m` commands; the Claude finisher snapshots, measures, attributes and scores (Q1).
Vocabulary follows contract Q6; automated scan required. COMMIT: explicit pathspec only; prereg sealed as its OWN
commit first (`SEAL sha256 <hex>`). ASCII stdout. **NEVER PARK.**

VERSION 2026-09-09
