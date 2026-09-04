GAP G218 | sport all | worktree a7 | log g218_degraded_substitute_audit
**MEASUREMENT AND PROPOSAL ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. Build
in `scripts/platformkit/tracking/`.

**S1 MACHINE: RUN LOCALLY. Do NOT use the pod** -- G216 is measuring concurrency throughput there and
extra load corrupts its numbers. This row is static reading plus, at most, tiny local import probes.
If you believe you need the pod, STOP and say why instead of using it.

**WHY THIS ROW EXISTS -- THIS DEFECT CLASS HAS ALREADY PRODUCED TWO REAL PRODUCTION BUGS TONIGHT AND
THE SEARCH FOR MORE HAS NEVER BEEN SYSTEMATIC.**

`scripts/platformkit/tracking/silent_handler_census.py` (landed) currently reports **118 exception
handlers, 57 silent, and 37 both silent AND broad** (bare `except:` or `except Exception:`). That
census says WHERE handlers are. It does not say which ones are DANGEROUS, and that is this row's job.

**The defect shape, abstracted from the two confirmed instances:**
  1. **`src/tracking/osnet_reid.py`** -- the OSNet load fails, `except Exception:` catches it, an
     **UNTRAINED** `mobilenet_v2(weights=None)` is installed as the feature extractor, and
     **`self.available = True`** is set. Re-identification then runs on a randomly initialised network.
     Nothing in any output said so. Fixing it made re-ID **6.8x faster** (0.103 s -> 0.0152 s for 17
     crops), which is itself evidence the fallback was live in production.
  2. **`src/tracking/ball_detect_track.py:31/34/38/79`** -- a four-rung model-path resolution whose
     last rung is a generic `YOLO("yolov8n.pt")` COCO model rather than the fine-tuned ball model.
     Same shape: intended artifact missing, plausible substitute installed, no signal emitted.
  **Root cause of both: `data/` and `models/` are gitignored, so the git-archive deploy carried no
  weights, and every handler on the path reported success anyway.**

**THE COMMON SIGNATURE, and it is what you are hunting:** an exception is caught, execution CONTINUES
with a substitute or default that is **lower fidelity than what was intended**, a **success flag or
plausible return value** is produced, and **no trace reaches the logs, the output tables or any
status field.** A handler that catches, degrades, and ANNOUNCES the degradation is NOT this defect.

THE QUESTION: **which of the 37 silent-and-broad handlers can silently substitute a lower-fidelity
behaviour for the intended one, and what would each one cost if it fired in production?**

METHOD:
  1. Re-run the census yourself and **name the exact counts you audited** -- do not inherit mine; the
     file set moves. Name your ELIGIBLE DENOMINATOR and every exclusion.
  2. **Read each silent-and-broad handler and classify it into exactly one bucket**, stating the
     reason in one line with a `file:line` citation:
       - **DEGRADED-SUBSTITUTE** -- continues with a lower-fidelity model, default, or fallback path.
         **This is the dangerous bucket.**
       - **OPTIONAL-FEATURE** -- the guarded thing is genuinely optional and its absence is not a
         fidelity loss (say why).
       - **BENIGN** -- cleanup, best-effort logging, teardown, an already-reported condition.
       - **UNCLEAR** -- you could not determine it from the code. **Use this bucket honestly rather
         than forcing a classification**; an inflated DEGRADED count is worse than an honest UNCLEAR.
  3. **POSITIVE CONTROL, and this is a hard gate on your method: your classification MUST independently
     land the OSNet handler and the ball-model rung in DEGRADED-SUBSTITUTE.** If your criteria miss
     either known defect, **your criteria are not sensitive enough -- say so and revise them before
     reporting any count.** State explicitly that you checked this.
  4. For every DEGRADED-SUBSTITUTE, state **what the substitute is**, **what fidelity is lost**, and
     **whether anything observable would reveal it** (a log line, a status field, a column, a timing
     change). **"Nothing would reveal it" is the finding that matters.**
  5. **Rank the DEGRADED-SUBSTITUTE handlers by blast radius** -- would firing it affect every frame,
     one clip, or one optional export? Say which are on the tracking hot path.
  6. **Deliver PROPOSALS ONLY, clearly marked human-gated, for anything in `src/`.** The proposal shape
     that already worked tonight is: keep the fallback, but make it SAY SO. Do not propose removing
     fallbacks wholesale -- a fallback that keeps a long run alive has value; an unannounced one does
     not. **Do not apply any `src/` change.**

**HONEST LIMITATIONS to state, not discover:** this is STATIC reading, so it establishes what a handler
CAN do, never that it HAS fired in production. Do not claim any handler is currently firing unless you
have runtime evidence, and if you obtain runtime evidence say exactly how. The census is `ast`-based and
sees only the trees it walks; name them.

ACCEPTANCE RULE:
  metric        = every silent-and-broad handler classified into one of four buckets with a file:line
                  citation and a one-line reason; the DEGRADED-SUBSTITUTE set ranked by blast radius;
                  an explicit statement of whether the two known defects were re-found by the criteria
  before        = 118 handlers / 57 silent / 37 silent-and-broad are LOCATED but unclassified; two
                  defects of this class were found by hand, and nobody knows whether there are more
  bar           = NO pass bar. **"All 37 are benign or optional and the two known defects were the only
                  ones" is a FULL SUCCESS** and would be strong evidence the tree is healthier than
                  feared. Do not inflate the dangerous bucket to make the row look productive.
  n             = every silent-and-broad handler in the audited trees (CONSTRUCT, exhaustive)
  eye check     = none; this row is code reading
  must not move = every threshold, bar and verdict, the coordinate contract, `src/` (READ ONLY -- do
                  NOT apply a single fix), the pod (DO NOT USE IT), the corpus
EVIDENCE: docs/evidence/tracking/g218_degraded_substitute_audit_2026-09-04.md with the counts you
measured, the full four-bucket classification table, the positive-control result, the blast-radius
ranking, the human-gated proposals, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
