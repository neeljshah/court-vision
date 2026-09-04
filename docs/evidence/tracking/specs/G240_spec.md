GAP G240 | sport wnba | worktree a6 | log g240_adapter_determinism_hash
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. Build in
`scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G233d may be running; N=2 is optimal per G200/G216). **Check first, do
NOT interrupt a running row, and say in your memo that you checked and when you began** -- G236b did this
correctly: it found G225 active, waited, re-checked, and only then began. The `track_daemon`,
`keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and `foundry_runner` are PERMANENT
residents and the load floor.

**WHY THIS ROW EXISTS -- IT WOULD SETTLE A QUESTION SIX ROWS COULD NOT, AND IT IS CHEAP.**

**Six rows hunted the route's non-determinism and exhausted every enumerated candidate:** G189 and G190
(FP16, the cuDNN tuner, torch seeds, FP32), G195 (OpenCV's six RNG sites), G198 (the prefetch cache),
G199 (wall-clock branching), and **G203, which showed decode is byte-identical -- 1,200 frame hashes per
run across three fresh processes, zero differences.** The standing conclusion is that **the route
consumes identical pixels in identical order and its output still differs, with no identified source.**
**Every one of those rows ran the LEGACY route (`run_clip` / `unified_pipeline`).**

**G225 then ran NINE ADAPTER jobs -- three model arms times three repetitions -- and every arm produced
IDENTICAL emitted row counts across its three runs: 64,171 three times (`yolov8n`), 113,733 three times
(`yolov8s`), 98,979 three times (`yolov8m`). Its nano arm also reproduced G226c's independent baseline
exactly, including median track length 205 and 207 distinct ids.**

**BUT IDENTICAL ROW COUNTS DO NOT PROVE IDENTICAL ROW CONTENT.** Two runs can emit the same number of
rows with different coordinates or different track ids. **G203 set the standard here -- it hashed 1,200
frames per run rather than counting them -- and this row must meet it.**

THE QUESTION: **are two adapter runs of the same clip and configuration byte-identical in their emitted
table, or merely the same size?**

METHOD:
  1. **Run the basketball adapter THREE times on the same clip with identical arguments.** Use
     `wnba__wnba_01.mp4` and `--max-frames 6000`, matching G226c and G225's nano arm, so any result is
     directly comparable to their landed figures. **Write each run to its OWN new tracking directory and
     say which.**
  2. **Hash the emitted `tracking_data.csv` of each run (SHA-256) and report all three.** **That is the
     headline.** Identical hashes across three fresh processes would be a far stronger statement than
     G225's row counts.
  3. **If the hashes differ, DO NOT stop at "not deterministic" -- localise it**, exactly as G203 did for
     decode. Compare the tables row by row and report **how many rows differ, which COLUMNS differ, and
     whether the differences are in coordinates, track ids, ordering, or a float in the last decimal
     places.** A one-ulp float difference and a re-numbered identity are completely different findings
     with completely different causes.
  4. **Report the row count for each run beside the hash**, so a reader can see whether G225's
     equal-count observation reproduces independently.
  5. **State plainly whether the adapter path is repeatable on this evidence, and be precise about the
     denominator: three runs, one clip, one configuration.** **Do NOT generalise to "the adapter is
     deterministic"** -- that is a much larger claim than three runs support, and I want the limit stated
     in the verdict line itself.
  6. **Do NOT touch the legacy route, do NOT re-open the G189-G203 investigation, and do NOT propose a
     fix or a production change.** This row answers one comparison.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE on this pod (it reports the whole cluster filesystem
against a 50 GB volume cap; a `Disk quota exceeded` incident followed that misreading). **`dd conv=fsync`
probe before writing, record `du -sm /workspace/nba-ai-system/data` (baseline ~32,660 MB of 50,000), STOP
and report if it fails.** Three tracking directories at roughly 64,000 rows each are small, but **delete
every temporary artifact when done and report bytes freed.** Delete no corpus source and no legacy table.

**HONEST LIMITATIONS to state, not discover:** three runs on one clip in one configuration is an
EXISTENCE check, not a determinism proof -- **byte-identical output here would show the adapter did not
vary on these three draws, nothing more.** The pod is shared and its permanent residents run throughout,
so this is not a clean-machine result. **A difference found here would NOT contradict G225**, whose
claim was only about row counts. And nothing here bears on the legacy route's non-determinism, whose
source remains unidentified.

ACCEPTANCE RULE:
  metric        = SHA-256 of each of three emitted tables plus their row counts; and, if the hashes
                  differ, the count of differing rows with the columns involved and the nature of the
                  difference
  before       = six rows failed to identify the legacy route's non-determinism; G225 observed equal ROW
                 COUNTS across nine adapter runs but never compared content
  bar          = NO pass bar. **"The three hashes differ" is a FULL SUCCESS** and would show G225's equal
                 counts were a weaker signal than they looked. **"All three are identical" is the other
                 full success** and would give the programme its first repeatable measurement path. Do
                 not tune anything, and do not overstate either outcome.
  n            = 3 runs, 1 clip, 1 configuration -- state this denominator in the verdict line
  eye check    = none; this row is hashes and diffs
  must not move = every threshold, `imgsz`, `conf`, `min_players`, bar and verdict, the coordinate
                  contract, the harness, `src/` and `domains/` (READ and IMPORT ONLY), the legacy route,
                  the pod daemon and keeper, the corpus, the legacy tables
EVIDENCE: docs/evidence/tracking/g240_adapter_determinism_hash_2026-09-04.md with the three directory
paths, the three SHA-256 values and row counts, any row-level difference analysis, the explicit
three-run/one-clip denominator, every disk-guard probe, bytes freed, the load context, and a NOT VERIFIED
list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
