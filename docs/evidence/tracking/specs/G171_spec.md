GAP G171 | sport all | worktree a2 | log cx_g171_reference_store_immutable
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it (A5, A7, Q8); self-check section B.
RAILS: also read .claude/skills/lane-spawn-rails/SKILL.md and obey its RAILS block, including
RUNPOD FOR ALL HEAVY WORK.

THE DEFECT, measured 2026-09-03 (G170). `footage_bridge` documents that ONE reference clip per sport
is kept permanently "so tracking work can be re-measured". It does not hold.
`data/videos/reference/tennis.mp4` has mtime 2026-09-03 09:45:18 and is 2,024,970,178 bytes; every
other sport's reference dates from 2026-08-31 or 2026-09-01 and none exceeds 831 MB. The bridge's
tennis lane overwrote the permanent reference with the full game it had just downloaded, replacing a
38 MB clip with a 2 GB one MID-SESSION, between two measurements that both cite "the reference clip".

Nothing is retracted over it -- both files decode 28,773 frames and are the same content at two
encodes -- but a store described as permanent that silently mutates makes every "re-measure it later"
promise in the register conditional.

DO THIS:
  (a) Find the write path. Quote with file:line where a reference clip is written or replaced, and
      state the CONDITION under which it overwrites an existing one. Q8: verify from code, do not
      infer from the symptom.
  (b) Say whether overwriting is intentional (e.g. "keep the best/longest clip") or accidental. If
      intentional, the defect is that it is undocumented and unversioned, not that it happens --
      say which it is and do not assume malice in the code.
  (c) Report, over the ELIGIBLE DENOMINATOR of sports with a reference file, how many have been
      overwritten since first write, using mtimes. Name each.
  (d) Land the SMALLEST additive fix that makes the store trustworthy. The orchestrator's preference,
      offered to be argued with: never replace an existing reference; write a NEW sibling name and
      leave the original. Do NOT delete or rewrite any existing reference file, and do NOT restore
      the old tennis clip -- it is gone and pretending otherwise is worse than recording the loss.
  (e) A5 IS MANDATORY: grep every reader of `data/videos/reference/` -- specs, lanes, memos, code --
      and report them before changing what that directory contains or how it is named.

DO NOT change any threshold, bar, the coordinate contract, the eligibility definition, or a verdict.
DO NOT delete footage.

ACCEPTANCE RULE:
  metric        = the quoted write path and overwrite condition; the count of overwritten references
                  over the eligible denominator, each named; the A5 reader list
  before        = the store is documented permanent and is not; one reference was replaced mid-session
  bar           = NO pass bar. Success is the mechanism established and the reader list produced.
                  "Intentional and merely undocumented" is a full success and may end in a docs change.
  n             = every sport with a reference file (CONSTRUCT, exhaustive)
  eye check     = replaced by REPRODUCTION (Q7): show the mtimes and sizes you measured
  must not move = every threshold and bar, the coordinate contract, every existing footage file
EVIDENCE: docs/evidence/tracking/g171_reference_store_immutable_2026-09-03.md with the quoted path,
the overwrite condition, the per-sport table, the A5 survey, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
TEST: exactly one new per-file test if you change code; run only that file. NEVER a full pytest.
POD: READ-ONLY, batched. Never kill or restart the daemon or keeper.
COMMIT: explicit pathspec only, in a2, no push. Report the sha.
NEVER PARK.
