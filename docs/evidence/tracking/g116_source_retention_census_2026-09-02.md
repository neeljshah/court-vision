# G116 source-retention census

**Verdict: ACCEPT.** This is a read-only, point-in-time census of source
presence for every canonical pod tracking table. No source video, table,
bridge, daemon, threshold, coordinate contract, verdict, or pod process was
changed. The census follows
[`VERIFIER_CONTRACT.md`](VERIFIER_CONTRACT.md), including A7 and section B.

## Frozen population and method

At `2026-09-02T22:59:52Z`, one read-only pod pass found **199** directories
containing `data/tracking/<table>/tracking_data.csv`. This supersedes G109's
frozen 196-table population: the corpus was live during this measurement, and
it grew through 197 and 198 while the preliminary read-only probes ran.

For each of the 199 table directories, the census derived its source key from
the daemon/bridge filename convention and `stat`-read matching video files in
the three allowed locations: `data/footage_corpus/`, `data/videos/`, and
`data/footage_bridge/`. A `g89_` table uses the named underlying source key
(for example, `g89_tennis_10` maps to `tennis_10`). The complete per-table
record, locations, matched filenames, and priority-set flags are committed in
[`table_source_census.csv`](g116_retention/table_source_census.csv). A ledger
claim was never accepted as source presence.

The priority definition is deliberately reproducible. The current
jump-gate subset is G109's seven eligible rows plus `tennis_07`, which G114
subsequently measured as eligible; the two post-G109 additions
`football_wPk3WVHBib4` and `soccer_2TwKQrkV7FA` both declare `image_px` and
are not eligible. A memo-cited table is one whose exact table token occurs in
a HEAD-committed `docs/evidence/tracking/*.md` memo, excluding `specs/` and
`RESULTS_LEDGER.md`; the matched committed paths are retained in
[`memo_cited_tables.csv`](g116_retention/memo_cited_tables.csv).

## Retention result

| Scope | Retained / tables | Fraction |
|---|---:|---:|
| All tracking tables | 73 / 199 | 36.68% |
| baseball | 13 / 36 | 36.11% |
| basketball | 6 / 6 | 100.00% |
| football | 9 / 44 | 20.45% |
| kbo | 13 / 37 | 35.14% |
| npb | 8 / 25 | 32.00% |
| soccer | 7 / 26 | 26.92% |
| tennis | 11 / 16 | 68.75% |
| wnba | 4 / 7 | 57.14% |
| unknown routing | 2 / 2 | 100.00% |
| Jump-gate eligible | 8 / 8 | 100.00% |
| Cited in a committed memo | 61 / 94 | 64.89% |

Of the 73 retained-table matches, 71 are in `data/footage_corpus/`, one is
in `data/videos/`, and one is in the active bridge stage. The 126 absent
sources are explicit `source_present=False` rows in the census, not omitted
from any denominator. In particular, the five legacy `tennis_01` through
`tennis_05` tables remain absent, consistent with G114. Presence alone is not
historic reproducibility: G110 already demonstrated that an extant source can
have changed its timeline/content.

[`retention_summary.csv`](g116_retention/retention_summary.csv) is the
additive source for every fraction above.

## Why sources disappeared

Two distinct code paths exist.

The legacy inline bridge documents its policy as:

> `download -> scp -> track on pod -> delete local AND remote copies immediately.`

Its `push_and_track` path then executes `_ssh("rm -f %s" % remote, ...)` in a
`finally` block, while the local cleanup removes the staged local files. That
is the path used when the bridge selects `push_and_track` rather than
`push_staged`.

The decoupled daemon policy differs. `track_daemon.py:33-35` says:

> `Where a tracked video goes instead of being deleted.`

and assigns `CORPUS = Path("data/footage_corpus")`; its completion path calls
`retain(video, CORPUS, ...)`. The implementation in
`track_daemon_done.py:170-181` is `video.replace(corpus / video.name)`. The
bridge routes explicitly by `push = push_staged if decouple else
push_and_track`, so staged/daemon work retains the source while legacy inline
work reclaims it.

Git history dates the corpus-retention change to commit `76894f2ef2`,
`2026-09-01T10:12:15-05:00` (`fix(daemon): stop destroying the corpus a fix
has to be measured against`). A second read-only `stat` of every table CSV,
recorded in [`policy_timing.csv`](g116_retention/policy_timing.csv), found
that 114 of the 126 missing-source tables have a tracking CSV mtime before
that policy commit, while 12 have a later mtime. Thus the corpus policy
post-dates the overwhelming majority of missing table artifacts. CSV mtime
does not prove the exact deletion event or execution route for any individual
table; especially, the twelve later missing rows cannot be assigned to the
inline bridge versus another path from code inspection alone.

## Disk-cost bound

The 73 current corpus video files total **10,349,220,066 bytes** (9.64 GiB),
with a mean of **141,770,137.89 bytes** (135.20 MiB) per file. Retaining one
current-mean source file for every one of the 199 tracking tables projects to
**28,212,257,440 bytes** (26.27 GiB). The complete stat-derived inventory and
calculation are in
[`corpus_file_inventory.csv`](g116_retention/corpus_file_inventory.csv) and
[`corpus_cost_bound.csv`](g116_retention/corpus_cost_bound.csv). This is a
one-file-per-table bound, not a storage-capacity finding: available pod disk
was not measured, so affordability is **NOT VERIFIED**.

## Recommendation

Adopt a source-retention tier: retain the exact source bytes for every table
cited by a committed memo and every jump-gate-eligible table; for every other
tracked table, retain a deterministic reacquisition manifest containing the
source URL, selected source filename/rung, duration, FPS, frame count,
dimensions, byte size, and SHA-256. The manifest should be written before a
source can be discarded and associated with its table, not inferred later
from a filename. G110 shows deterministic decoding is sufficient once the
same bytes are present, while G96 and G110 show that a re-download can change
the upstream asset; checksum and timebase fields make that loss detectable.

## VERIFIER_CONTRACT self-check

### A

- **A1:** No code or test was added; no per-file test exists to rerun.
- **A2:** The headline fractions were recomputed from the committed
  `table_source_census.csv` and its 199 distinct `table` values; the results
  equal `retention_summary.csv`.
- **A3:** No render metric applies. This is an exhaustive table census; all
  units were stat-checked rather than sampled from a head slice.
- **A4:** The denominator is one distinct canonical source-table directory;
  `table_source_census.csv` has 199 unique table values.
- **A5:** Evidence only; no field, schema, or reader changed.
- **A6:** This lane makes an explicit-path evidence commit in `a2`. Archive
  landing, RESULTS_LEDGER/register append, and master-side test rerun remain
  verifier work under the contract's stated verifier scope.
- **A7:** Before reporting, every repository evidence path named in this memo
  will be checked for existence, including this memo, all six derived CSVs,
  G109, G110, G114, the G116 spec, and `VERIFIER_CONTRACT.md`.

### B

- **B1:** Clear. The complete 199-table frozen read is in the census before
  any retained/absent calculation; all 126 absent rows remain named.
- **B2:** Clear. No production schema, field, status, reader, or code changed.
- **B3:** Clear. Missing source evidence is an explicit absent result, not a
  quarantine or quality verdict.
- **B4:** Clear. No claim, queue, retry, or ownership behavior changed.
- **B5:** Clear. Pod interaction consisted only of read-only `find`, `stat`
  metadata, headers, and directory listings; no copy, deploy, restart, kill,
  re-track, deletion, or move occurred.
- **B6:** Clear. No module, test, import, or command was moved or retired.
- **B7:** Clear. The metric uses every source-table directory in the frozen
  read, not a head slice.
- **B8:** Clear. No fitted model or residual is claimed.
- **B9:** Clear. Each denominator unit is a distinct source-table directory,
  not a row, frame, or reused track identifier.
- **B10:** Clear. No harness threshold, gate, coordinate contract, or verdict
  changed.

## NOT VERIFIED

- Byte-identical historical reproducibility for any retained source: presence
  does not recover an old source checksum, URL, duration, FPS, or timeline.
- An archive outside the three examined locations.
- The exact runtime route or source-deletion event for each of the twelve
  missing tables whose CSV mtime is after the corpus-policy commit.
- Pod free-space capacity or whether the 26.27 GiB extrapolated bound is
  affordable.
- Any table or source state after the `2026-09-02T22:59:52Z` frozen census.
- No focused test ran because no source code was added; no full test suite ran.
