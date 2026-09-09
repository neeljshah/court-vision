GAP G366 | sport all (basketball fixtures first) | worktree a12 | log cx_g366_gate_confirmation

**GATE-CONFIRMATION ROW, SUCCESSOR TO G359 (DONE 2026-09-09 54d88e4c: on the 34 sealed sections
`zero_step_share` and `distinct_position_ratio` are PRODUCTION_SCHEMA_ARTIFACTs -- clear 0.706 / 0.735 under M0
rows-as-written, 1.000 / 1.000 under M1 evaluated-ticks-only with the sealed thresholds unchanged;
`median_step_distance` is THRESHOLD_MISCALIBRATED (M0 clear 0.941, M1 0.088; v2 candidate 76.995468 preregistered,
unscored); `stationary_track_share` is invariant under the collapse; frozen + id-merge plants detected 34/34 in both
arms; the ball-shift "detection" equals A0's own false-rejection cells). Codex PREPARES, a Claude finisher MEASURES on
the pod.** `src/`, `kernel/`, `api/`, `intel/` are READ and IMPORT only. Build additively beside
`g359_held_position.py`. NEVER write `data/registry/`, never flip a flag, never MOVE a sealed threshold (v2 is an
ADDITIVE column beside v1), never touch the register.

**WHERE THIS ROW RUNS:** ON THE POD, in `/workspace/wt/a10` (`python3 -m` from the worktree root; tables under
`data/tracking` -> `/workspace/data/tracking`, READ ONLY; snapshot the ledger first). FRESH sections = clips the
current daemon tracked on 2026-09-09 or later (they carry the G354 px fields), pinned by YouTube id + offset +
sha256 per G361 (an NBA game id alone is not a source), DISJOINT from G358's 34 sealed sections and from every
game they came from.

**PREMISE (step 0, BINDING before-condition):** re-read G359's `decision.csv`, `held_share.csv`, `arms.csv`
(committed at 54d88e4c) and PRINT the per-gate classes with their denominators; confirm `held_share.csv` and
`arms.csv` retain pre-collapse denominators and plant outcomes. **If fewer than 3 of the 4 gates carry a class,
the premise is FALSE: STOP, memo, commit, report PREMISE FALSE.**

METHOD (sealed before any fresh number):
  1. **FRESH SET (CONSTRUCT over the snapshot, then even sample if > 40):** >= 30 full sections / >= 10 games,
     >= 150 unique evaluated frames each, disjoint as above; archive the eligibility census.
  2. **ARTIFACT GATES (`zero_step_share`, `distinct_position_ratio`):** on the fresh set under M1 with the
     sealed thresholds: A0 rejection share per gate (bar <= 0.05); and an evaluated-tick audit: the M1 collapse
     count per section vs the producer's `evaluated_frames` / stride from the ledger (report the per-section
     ratio; bar: median within 0.90-1.10).
  3. **STATIONARY CONTROLS (`stationary_track_share`):** plant synthetic genuinely-stationary tracks (sealed
     count and share) into copies of >= 10 fresh sections; the gate must detect the plant under BOTH arms
     (>= 0.80) and clear the unplanted fresh sections under M1 (A0 rejection <= 0.05).
  4. **THRESHOLD GATE (`median_step_distance`):** score G359's preregistered v2 candidate (76.995468) on the
     FRESH set only (never on the 34 that produced it): A0 rejection under M1 <= 0.05 with v2; plant detection
     (frozen / id-merge / ball-shift where identifiable) >= 0.80 with v2; v1 stays in place; v2 is an ADDITIVE
     column with its rejection direction stated.
  5. **REACH:** per gate, the share of fresh sections where the gate is reachable (not NOT_APPLICABLE); name
     every gate blocked by an absent `frame_size_source` / dims field; NOT_APPLICABLE never passes a required gate.
  6. CHANGE NOTHING ELSE; no src hook; no flag.

ACCEPTANCE RULE:
  metric        = per-gate A0 rejection on fresh sections (M1, with M0 beside it); plant detection per arm; the
                  v2 rejection and detection; the evaluated-tick ratio table; the reach table
  before        = G359's classes on the 34 sealed sections (numbers above)
  bar           = >= 30 fresh sections / >= 10 games, disjoint; A0 rejection <= 0.05 per confirmed gate under M1;
                  plants >= 0.80 where identifiable; evaluated-tick ratio median within 0.90-1.10; 0 hidden
                  samples; original gates and thresholds unchanged; v2 additive
  n             = >= 30 sections (sampled evenly if > 40 eligible); >= 10 planted sections per plant type
  eye check     = REQUIRED: 10 evenly spaced strips (M0 rows vs M1 ticks for one track, per section) <= 200 KB
  must not move = every sealed threshold, `src/`, `data/`, `data/registry/`, every flag, the daemon
  verdict       = **DONE** (gates confirmed; a teacher admission filter may use M1 + confirmed gates) /
                  **PARTIAL** (name the gate) / **PREMISE FALSE**
EVIDENCE: `docs/evidence/tracking/g366_gate_confirmation_2026-09-09.md` (<= 60 lines; VERDICT line 1; NOT VERIFIED;
wall time; SHA-256s) + `.../g366_gate_confirmation_2026-09-09/fresh_sections.csv`, `gates_fresh.csv`, `plants.csv`,
`v2.csv`, `ticks.csv`, `reach.csv`, `strips/`, `summary.json`. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT.**
TEST: `tests/platformkit/test_g366_gate_confirmation.py` alone (v2 is additive and v1 untouched; NOT_APPLICABLE
never passes a required gate; the fresh set is disjoint from the sealed 34 by section AND game; the planted
stationary track raises the share as designed). **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: codex prepares the prereg (sealed alone: disjointness rule, sampling rule, plant definitions,
bars, v2 direction), the modules, the test and the memo skeleton, exits `agent: PREPARED FOR FINISHER` with
`python3 -m` commands; the Claude finisher snapshots, samples, runs the arms, plants, scores (Q1). Vocabulary
follows contract Q6; automated scan required. COMMIT: explicit pathspec only; prereg sealed as its OWN commit
first (`SEAL sha256 <hex>`). ASCII stdout. **NEVER PARK.**

VERSION 2026-09-09
