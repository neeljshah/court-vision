# CENSUS RULE -- a reported count must be recomputable from committed bytes

Written by row G319 on 2026-09-08, binding on every memo written after that date. NOT applied
retroactively: landed memos are frozen and their unbacked counts carry a caveat instead.

1. **SCOPE.** Every count a memo reports over a MUTABLE source -- a ledger, a corpus listing, a job
   root, a log, a live directory, anything that can change between two reads. A count taken over an
   artifact already committed in the same repository is out of scope; the artifact is its own proof.

2. **THE OBLIGATION.** Such a count must be recomputable from committed bytes, by one of two routes:
   - **Snapshot.** The bytes of the source as they stood at the moment of the count are committed.
   - **Snapshot list.** When the bytes are too large to commit (over 5 MB per file), a committed
     hash-chained list carries, per snapshot, its `sha256`, its row count and its timestamp; and the
     PROJECTION of only the columns the count uses is committed in place of the full bytes.

3. **ORDER.** The snapshot is taken AFTER the preregistration seal and BEFORE the count, and the
   count is computed FROM THE SNAPSHOT, never from the live source. A count read from a live source
   and a snapshot taken afterwards are two measurements and must not be presented as one.

4. **THE FALLBACK.** A count with neither route behind it is reported in the memo as
   `NOT RECOMPUTABLE`, in those words, beside the number -- never silently, and never dropped from
   the memo to avoid saying so.

5. **REPEATED READS.** When a memo reports a sequence of reads of one source -- three reads of a
   growing ledger, a before and an after -- EACH read needs its own snapshot or its own snapshot-list
   entry. One snapshot backs exactly one read. A sequence backed by a single snapshot is reported
   with that one read `RECOMPUTABLE` and every other read `NOT RECOMPUTABLE`.

6. **WHAT THIS RULE IS NOT.** It does not say a count is correct. `RECOMPUTABLE` means only that a
   committed artifact reproduces the number. Whether it is the right number is for the verifier.

## The check

`scripts/platformkit/tracking/census_recomputable.py` applies clauses 1, 2 and 4 to a memo after the
fact and prints one verdict per count: `RECOMPUTABLE`, `NOT RECOMPUTABLE`, `UNPARSED` (a count-shaped
token whose line names no source, so the check declines to judge it) or `ABSENT` (the memo itself is
not committed). It parses prose heuristically and says what it could not parse. A green check is
evidence, not proof: clause 3 is an ORDER it cannot see from committed bytes and must be shown by the
commit sequence, and clause 5 is a per-read obligation it cannot see because it judges the integers
in a sequence, not the reads behind them.
