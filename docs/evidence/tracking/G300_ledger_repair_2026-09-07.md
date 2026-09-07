# G300 -- RESULTS_LEDGER.md repair (2026-09-07)

STATUS: DONE. 17 clobbered ledger row lines across 9 gap ids restored by APPEND; the tracking lander
`~/bin/codex-land-g` changed so it can never rewrite the ledger again.

## 1. The defect

`~/bin/codex-land-g` step 6 told the lander to "append the VERIFY memo's proposed ledger line to
docs/evidence/tracking/RESULTS_LEDGER.md as its last line". It did not forbid a whole-file rewrite, and
the landers implemented the append by reading the file and writing it back. Every such rewrite dropped
the rows the model did not carry forward. Two landings account for all of it:

- `3eeef35cf` (G296b) and `ace539619` (G298) between them removed the G289 / G290 / G292 / G293 / G294 /
  G295 / G297 / G298 / G299 rows.
- `1e3a4f97a` (G293) removed the G299 rows written by `07adb0c36` / `846783b60`.

Memos and landing commits were never touched, so every row was recoverable from git history.

## 2. Recovery method (auditable)

Iterate `git log --format=%h --reverse -- docs/evidence/tracking/RESULTS_LEDGER.md` (344 versions),
collect every line starting `| 20` or `20`, and set-difference against HEAD. 21 lines were historical-only;
4 of those (G17, G22, G27, G30) are later EDITS of rows whose gap id still has a row at HEAD, so they were
NOT restored. The remaining 17 lines belong to 9 gap ids with no row at HEAD at all and were appended in
their last-seen order, under a dated heading, with no existing line touched:
`git diff --numstat` on the repair commit is `37  0` -- 37 insertions, ZERO deletions.

RESTORED IDS: G289 G290 G292 G293 G294 G295 G297 G298 G299 (17 row lines).

Recovery script: `scratchpad/ledger_recover.py` (session-local, not committed; the method above reproduces
it in six lines).

## 3. Lander fix

`~/bin/codex-land-g` step 6 now instructs the lander to append with ONE shell redirect
(`{ echo '<line>'; echo; } >> docs/evidence/tracking/RESULTS_LEDGER.md`, or a python open-in-'a'
equivalent), and forbids reading-and-rewriting, mode 'w', `sed -i`, heredocs and editors over the file. It
then requires `git diff --numstat -- docs/evidence/tracking/RESULTS_LEDGER.md` to show a ZERO deletion
column, and a `git checkout --` + retry if it does not. Backup of the pre-change file:
`~/bin/codex-land-g.bak_2026-09-07`. `sh -n` passes; the file is one line longer in characters only (17
lines before and after) and its CRLF endings are preserved.

`~/bin/codex-land` (the HARNESS lander) carries the same ambiguous wording for
`docs/evidence/RESULTS_LEDGER_SYSTEM.md` ("append ... as the last line"). It was NOT changed: the harness
loop is live and owns that file. Measured blast radius there is much smaller -- 91 historical-only lines
across 337 versions, but only ONE gap id (S301) has no row at HEAD. Reported to the orchestrator for the
harness owner to fix.

## 4. SELF-CHECK -- every G id with a landing commit has at least one ledger row

Method: every id at the head of a git-log subject (`^G[0-9]+[a-z]?`) = 151 ids; a ledger row "belongs" to
an id when a pipe-delimited cell starts with that id. 260 distinct ids carry a ledger row.

RESULT: 18 of the 151 ids still have NO ledger row. **None of them is a clobber victim** -- a scan of all
344 ledger versions shows no row for any of them ever existed, so these are rows that were never written
(the 2026-09-02/03 era, before the ledger line became part of the landing contract):

G52, G182, G182b, G184, G185, G186, G186b, G187, G188, G189, G190, G191, G192, G192b, G193, G194, G196, G202.

G202 is an allocation-and-HOLD commit, not a landing, so it is expected to have no row. The other 17 are
real landings whose memos exist and whose findings are in the register; writing their rows retrospectively
is NOT done here because a ledger row must be the landing verifier's own numbers, and this row would be
inventing them.

NOT VERIFIED:
- That the 17 restored lines are byte-identical to what the original landers intended -- they are
  byte-identical to the last version of each line that ever existed in git, which is the best available.
- That no ledger row was lost in a commit that ALSO deleted the file and re-added it under another name.
- The `~/bin/codex-land-g` change is a PROMPT change; no lander has run since, so it is untested in flight.
- The `RESULTS_LEDGER_SYSTEM.md` figure (91 historical-only lines) is a count, not an adjudication of which
  are edits and which are losses.
