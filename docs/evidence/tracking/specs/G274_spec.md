GAP G274 | sport wnba | worktree a6 | log g274_second_shot_replication
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` and `src/tracking/player_detection.py` are HUMAN-GATED.** Build in
`scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G273 may be running on a5; N=2 is optimal). **Check first, do NOT
interrupt a running row, and EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G241b, G267, G270 AND G271 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- THE ENTIRE TRACKING-QUALITY FINDING RESTS ON ONE CAMERA SHOT.**
G267, G269, G270, G271 and G272b all analyse **the same span: source frames 19599-23399**, chosen because
G241b located the first shot cut at about distance 3,876. Every number in the chain -- **10.5 pct on-court
implausible steps, 61.3 pct of impossible steps fully on court, 79 of 98 ids affected, 58 pct with 83+ px
image displacement** -- comes from **that one shot of that one clip.**

**Every one of those memos carries "one shot" in its limitations, and nobody has tested it.** A camera shot
is a specific framing, zoom and slice of play; **the defect profile could be entirely different in another
shot**, and if the numbers do not replicate then the chain describes a moment rather than the system.

THE QUESTION: **does the tracking-defect profile replicate in a DIFFERENT camera shot of the same clip?**

METHOD:
  1. **PICK A SECOND SHOT AND JUSTIFY IT.** G241b inventoried **15 `scene > 0.40` cut candidates** across
     its 10,000-frame span and named an abrupt matched-feature drop at **distance 9,823 (327 to 162
     matches)**. **Use that inventory to choose a span that is clearly inside a different shot**, state its
     source-frame range, and **say how you verified no cut lies within it.** Prefer a span of comparable
     length to G267's 3,801 frames; if the shot is shorter, use what it has and say so.
  2. **A SECOND SHOT NEEDS ITS OWN MAP, AND THAT IS THE HARD PART -- DO NOT SKIP IT.** G233d's published
     map is anchored to seed frame 19599. **Direct-to-seed matching across a cut is exactly what G241b
     showed collapses.** So either **(i)** establish that the new span still matches the 19599 seed with
     usable geometry -- **report matches, inliers and RMS, and say plainly if it does not** -- or **(ii)**
     report that no valid map exists for the second shot and **STOP.** **Stopping is a full success**: it
     would mean the chain cannot be replicated without a second hand label, which is itself the operational
     finding.
  3. **ONLY WITH A VALID MAP, repeat G267's measurement exactly** on the new span: court-space speeds,
     the above-40-ft/s fraction, p99 and max, the in-court partitioning of G270, and G271's per-id
     concentration and image-displacement split. **Use the same definitions and the same 40 ft/s and
     83 px figures -- change nothing so the two shots are comparable.**
  4. **REPORT EVERY FIGURE SIDE BY SIDE WITH THE FIRST SHOT'S**, in one table. **State plainly whether the
     profile replicates.**
  5. **A DIFFERENT PROFILE IS THE MORE INTERESTING OUTCOME** -- it would mean the defect depends on
     framing or play context and that the first shot's numbers must not be quoted as system-wide. **Say so
     directly if that is what you find.**
  6. **Do NOT propose a production change, filter, gate or threshold; do NOT touch `src/`; do NOT re-detect
     the first span** (G241: the detector is non-deterministic, so the first shot's numbers must be quoted
     from G267's retained records, not recomputed).
  7. **The population is detector boxes, not authenticated players** (G225: 19 boxes, 2 visibly on-court
     people). **Name the denominator; never say "players" unqualified.**

**DISK GUARD, CORRECTED SCOPE:** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`** -- the scope
the 50 GB quota is enforced on, last about **36,400 MB** with roughly 13.6 GB free, and **note a peer
session now writes compute scratch under `/workspace/wt`, which a subtree measurement cannot see.**
**`dd conv=fsync` probe before writing, STOP and report if it fails.** Stream the decode; never write a
full decode to disk. **Do NOT delete any corpus source or the two abandoned partials in the bridge
directory.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** two shots of ONE clip in ONE arena is a replication, not a
population. **The second shot's detections are a fresh draw of a non-deterministic detector** -- report to
three decimals and do not treat small differences as signal. **If the second shot's map comes from the same
19599 seed, its quality is not guaranteed to match the first shot's**, and G252's 5 px / 19 px figures were
measured on the first -- **say what you measured rather than importing them.** Identity remains unvalidated
everywhere in this programme.

ACCEPTANCE RULE:
  metric        = the second shot's span with its no-cut verification; the map validity evidence (matches,
                  inliers, RMS) or a clear statement that no valid map exists; then, with a valid map, the
                  full G267/G270/G271 figure set for the second shot **side by side with the first**; and a
                  plain replication verdict
  before       = the entire tracking-defect chain rests on frames 19599-23399, one shot of one clip, and
                 every memo in it carries "one shot" as an untested limitation
  bar          = NO pass bar. **"No valid map exists for a second shot without another hand label" is a
                 FULL SUCCESS** and an important operational finding. **"The profile replicates" would make
                 the chain a property of the system rather than a moment.** **"The profile differs" is the
                 most interesting outcome** and would forbid quoting the first shot's numbers as
                 system-wide. Do not tune, and do not import the first shot's figures as if measured.
  n            = 1 clip, 2 shots, the frame spans and box counts you state -- name every denominator in the
                 verdict line, and name the box population, not "players"
  eye check    = none required for the replication; if you judge map validity by render, judge on
                 INDEPENDENT geometry and remember G257's 20 px eye limit
  must not move = every threshold, bar and verdict, G233d's published map and labels, G267's retained
                  records and span, the 40 ft/s and 83 px definitions, the court model, the coordinate
                  contract, `src/` and `domains/` (READ and IMPORT ONLY), the pod daemon and keeper, the
                  corpus
EVIDENCE: docs/evidence/tracking/g274_second_shot_replication_2026-09-04.md with the shot selection and
no-cut verification, the map validity evidence, the side-by-side figure table, the replication verdict,
every disk-guard probe with the `du -sm /workspace` figure, bytes freed, and a NOT VERIFIED list. **ADD A
RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.

---

**AMENDMENT 2026-09-04 12:25 -- TWO CORRECTIONS TO THE HOLD RULE AND THE DISK FIGURE.
Both were measured just now; treat these as overriding the text above.**

**1. COUNT DISTINCT LANE WORKTREES, NOT PYTHON PIDs.** The hold rule above says to hold until a pod lane
is free, and a sibling row is currently holding on a FALSE reading because **one lane routinely shows two
python PIDs** -- a module runner and its child, both with the same `cwd`. A direct check just now returned
`LANE 3084857 /workspace/wt/a17` and `LANE 3085457 /workspace/wt/a17`: **two PIDs, ONE occupied lane.**
**So: collect the `cwd` of every python process under `/workspace/wt/a*`, reduce to the SET of distinct
worktree directories, and compare THAT count against 2.** Exclude your own process, your checker and its
parent as before. **Report the distinct-worktree set you observed, not just the number.**

**2. THE DISK FIGURE ABOVE IS STALE. `du -sm /workspace` is 40,059 MB right now**, not about 36,400, so
free space against the 50 GB quota is roughly **10 GB, not 13.6 GB** -- **the peer session under
`/workspace/wt` is consuming steadily and disk, not GPU, is now the binding constraint** (the GPU measured
1 MiB used and 0 pct utilisation at the same moment). **Re-measure `du -sm /workspace` yourself before
writing anything, budget against what you actually observe, keep crops and any decode modest, and STOP and
report if the `dd conv=fsync` probe fails.** **Do NOT delete any corpus source or the two abandoned
partials in the bridge directory** to make room; report the shortfall instead.
