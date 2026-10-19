# S813 adversarial tier 2026-10-09 (PAPER ONLY)

Three rounds, Opus subagents, one mutant at a time on the worktree module, restored from pristine copies after each
(drivers in C:\Users\neelj\AppData\Local\Temp\claude\s813_scratch\: mut.py, mut2.py, mut3.py). Each mutant ran
test_paper_desk_issue_refusals_s813.py and _s803.py, one process per file, with the RAM / pump.stop gate before every run.

## Round 1 on d99c75dea -- REJECT: 12 of 16 killed
- KILLED: M1 no confinement, M2 confine to CACHE, M3 allow the directory, M4 skip sha, M5 hash with newline, M7 malformed only
  for list, M8 malformed returns {}, M9 counters swapped, M10 sha before confinement, M12 unresolved prefix, M13 read before
  confinement, M14 except drops ValueError.
- SURVIVED: M6 sha checked only when str (untested), M11 string-prefix confinement (sibling journal_details_evil untested),
  M16 real defect -- a failed sha read set digest None, so a row carrying `detail_sha256: null` passed unverified;
  M15 rstrip (equivalent). Also: the sha was computed from a second read, not the bytes parsed.
- Defect hunt: sibling dir, backslash traversal, `C:decoy.json`, NUL, outside-repo, an unprivileged junction under a scratch
  journal_details -- all refused. Fix round 1 (063a5d02f): one read hashed + parsed + used; failed read or non-str sha = mismatch.

## Round 2 on 063a5d02f -- REJECT (tests only, no defect): 15 of 16 ported round-1 mutants killed (M15 equivalent)
- New on the fix: N1 use ctx.read's parse, N3 drop `data is None`, N6 skip falsy sha, N11 drop the None return -- KILLED.
- SURVIVED, not equivalent: N2 catch only OSError, N4 parse a second read, N5 drop isinstance(detail, dict), N9 failed read -> b''.
- SURVIVED, equivalent or safer: N7 errors=replace, N8 except Exception, N10 json.loads, N12 latin-1.
- Fix round 2 (8311c6d98, tests only): one-read call count, undecodable second read, verified non-dict detail, failed read vs
  sha256(b""). Lead re-ran mut2.py: N2 N4 N5 N9 KILLED.

## Round 3 on 8311c6d98 -- ACCEPT
- mut2.py re-run independently: 24 of 29 killed; M15 N7 N8 N10 N12 survive, equivalent or strictly safer.
- mut3.py, 10 new: R2 `detail or refusals`, R4 except -> inside, R5 sha prefix match, R6 counter removed, R8 sha only when str
  -- KILLED. R1 `in` vs `==` at the call site, R3 drop the str guard, R7 direct children only, R9 lowercase compare, R10 data[:-1]
  -- SURVIVED, each equivalent for an honest bound_row / atomic writer or stricter.
- Restore proven every round: git status clean, module cmp-equal to the pristine copy.
- Final: 55 mutant runs over three rounds; every behaviour-changing mutant for an honest writer is killed.
