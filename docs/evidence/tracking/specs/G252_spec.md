GAP G252 | sport wnba | worktree a5 | log g252_projection_accuracy_in_pixels
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (N=2 is optimal per G200/G216). **Check first, do NOT interrupt a
running row, and say in your memo that you checked and when you began. EXCLUDE YOUR OWN PROCESS AND YOUR
OWN CHECKER COMMAND** -- a G243c dispatch refused on a self-match. The `track_daemon`,
`keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and `foundry_runner` are PERMANENT
residents and the load floor.

**READ THE LANDED G233d, G242, G244, G247 AND G248 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- G248's NUMBERS CONTAIN AN UNEXPLAINED OBSERVATION, AND IT MAY EXPLAIN ALL FOUR
NEGATIVES AT ONCE.**
Four rows have now failed to find any automatic validity signal: G242 (acceptance accepts 89/89), G244 (no
match diagnostic; cut drops inside ordinary variation), G247 (no quad-shape check; every invalid map is a
well-formed quad), and G248 (no projected-line/image-agreement signal). **That closure stands and this row
does not reopen it.**

**But look at G248's edge-response contrast, which is the gradient magnitude ON the projected curves minus
the gradient at perpendicular control offsets:**

| class | n | min | median | p90 | max |
|---|---:|---:|---:|---:|---:|
| VALID | 27 | -67.888245 | **-47.325077** | -34.870512 | -23.571737 |
| INVALID | 28 | -57.526115 | **-45.145500** | -33.599431 | -13.773243 |

**It is NEGATIVE for the VALID class, and strongly so.** On frames a human judged correct, the projected
court lines sit on **less** edge structure than points a short distance away. **If the projections were
landing on painted lines, this number should be positive.**

**THE HYPOTHESIS THIS ROW TESTS -- and it is a hypothesis, not a finding: our best calibration may be
EYE-VALID BUT NOT PIXEL-ACCURATE.** A projected line offset by several pixels still looks right to a human
at render scale while missing a thin painted line entirely. If that is true, **every pixel-precise
statistic was doomed regardless of its design**, and the four negatives share one cause.

**And the programme has never measured this.** Every calibration verdict to date is a binary eye
judgement. **Nobody has put a number on how accurate a "valid" calibration actually is.**

THE QUESTION: **for frames a human labelled VALID, what is the perpendicular distance in pixels between a
projected court line and the nearest actual painted line in the image?**

METHOD:
  1. **REUSE COMMITTED DATA. Do not re-run the match and do not relabel.** Use G247's persisted per-frame
     homographies, G244's committed blind labels at
     `docs/evidence/tracking/g244_blind_validity_labels_2026-09-04.csv`, and the same 89 stride-2000
     frames decoded in ONE sequential pass at full resolution. **The G242 renders are 960x540 overlays and
     are NOT suitable as image input** -- a render-scale measurement would beg the very question being
     asked.
  2. **For the VALID frames, sample points along each projected court line and measure the PERPENDICULAR
     DISTANCE to the nearest detected line or strong edge in the image**, within a stated search radius.
     **State the search radius and say plainly that any true offset beyond it is censored** -- a censored
     measurement reported as a small offset would be the wrong answer.
  3. **Report the distribution of that offset: median, p90 and max, per line type** (sideline, baseline,
     lane boundary, free-throw line, arc, centre circle) **and pooled.** Report **how many sampled points
     found no candidate at all within the radius**, because that count matters as much as the distances.
  4. **Report the same distribution for the INVALID and CANNOT_JUDGE classes**, so the VALID figure has
     context. **Do NOT present this as a validity signal** -- G244, G247 and G248 already closed that, and
     this row is about magnitude, not separation.
  5. **CONNECT IT TO THE KNOWN ERROR BUDGET.** G140's p90 label repeatability is 11.39 px at 1920x1080,
     and G233d's seed used four hand labels. **Say whether the measured offset is consistent with label
     noise alone, or larger than it.** That is the interpretive question worth answering.
  6. **STATE PLAINLY WHETHER THE HYPOTHESIS IS SUPPORTED.** If VALID offsets are large -- several pixels or
     more -- say the eye check tolerates error that no pixel-precise statistic can see. **If VALID offsets
     are near zero, the hypothesis is REFUTED and G248's negative contrast needs a different explanation;
     say so and do not invent one.** A refutation here is as valuable as a confirmation.
  7. **Do NOT fit a threshold, do NOT propose a validity gate, do NOT re-open the signal-separation
     question, and do NOT propose a production change.**

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~33,093 MB of 50,000), STOP and report if it fails.**
**Stream the decode; never write a full decode to disk. Do NOT re-commit G242's 12.4 MB artifact. Do NOT
delete any corpus source or the two abandoned partials in `footage_bridge`.** Delete every temporary
artifact and report bytes freed.

**HONEST LIMITATIONS to state, not discover:** 89 frames, ONE clip, ONE seed, ONE arena, a wide stride, and
**labels inherited from G244's single labeller, not made by you.** **This row does NOT validate those
labels.** "Nearest detected line" is itself a detector output and can be wrong or absent -- **report the
no-candidate count and do not silently drop those samples.** The search radius censors large offsets by
construction. **A measured offset is not an accuracy claim about calibration generally**: it is the offset
of one seed's projection on one clip. Nothing here bears on automatic calibration, which remains 0/17, and
nothing here reopens the validity-signal closure.

ACCEPTANCE RULE:
  metric        = the perpendicular offset distribution (median, p90, max) between projected court lines
                  and the nearest image line, per line type and pooled, for VALID and for the other two
                  classes; the no-candidate count; the stated search radius and censoring; and a plain
                  verdict on whether the eye-valid-but-not-pixel-accurate hypothesis is supported
  before       = every calibration verdict in this programme is a binary eye judgement; the pixel accuracy
                 of a "valid" projection has never been measured, and G248 found negative edge contrast on
                 VALID frames with no explanation
  bar          = NO pass bar. **"VALID projections are offset by N px, so the eye tolerates what pixel
                 statistics cannot" is one full success** and would explain four negatives with one cause.
                 **"VALID projections are pixel-accurate, so the hypothesis is refuted" is an equally full
                 success** and would mean G248's contrast needs another explanation -- say so without
                 inventing one. Do not fit a threshold and do not reopen the separation question.
  n            = 89 frames, of which 27 VALID / 28 INVALID / 34 CANNOT_JUDGE, 1 clip, 1 seed -- state every
                 denominator in the verdict line
  eye check    = none required; this row is distances. Commit a few annotated examples if they aid a reader
  must not move = every threshold, bar and verdict, G222's matcher settings, the seed construction, the
                  court model, the coordinate contract, the harness, G244's committed labels, G247's
                  persisted matrices, `src/` and `domains/` (READ and IMPORT ONLY), the pod daemon and
                  keeper, the corpus, the two abandoned partials
EVIDENCE: docs/evidence/tracking/g252_projection_accuracy_in_pixels_2026-09-04.md with the decode method,
the search radius and censoring statement, the per-line-type and pooled offset distributions for all three
classes, the no-candidate counts, the comparison against G140's 11.39 px p90, the plain hypothesis
verdict, every disk-guard probe, bytes freed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN
THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
