# G114 tennis coordinate declaration

**Verdict: CLOSED AT LIMIT -- none of the five legacy tables is honestly
repairable.** G114 explicitly accepts this result. Adding `court_feet` to any
target would turn unknown, possibly carried-calibration values into a declared
physical coordinate space. No code, threshold, coordinate contract, rung,
harness verdict, image-pixel table, pod file, pod process, or re-track changed.

## Premise and current denominator

G109's frozen read at `2026-09-02T22:33:31Z` was 16 tennis tables: 7 eligible,
5 missing coordinate/schema, 2 empty, and 2 insufficient. The live current
result is not the frozen result: it is **16 total, 8 eligible, 5 missing, 2
empty, and 1 insufficient**. `tennis_07` is now a 7,128-row, 2,925-frame
court-feet table with a unique modal stride. This concurrent corpus growth,
not G114, falsifies G109's frozen 7-eligible premise for the current count.

The full before/after record is
[`tennis_census_before_after.csv`](g114_tennis_declare/tennis_census_before_after.csv).

## The five tables, individually opened

Each target was opened from the live canonical pod path
`data/tracking/<table>/tracking_data.csv`. Each has a data row, its own
row/frame count, the five-column header `frame,track_id,cls,x,y`, no coordinate
declaration, no `observation` or `calibration` field, and a directory that
contains only the CSV. The individual observations are committed in
[`per_table_diagnosis.csv`](g114_tennis_declare/per_table_diagnosis.csv).

| Table | Rows / frames | UTC mtime | Diagnosis | Repairable? |
|---|---:|---|---|---|
| `tennis_01` | 9,547 / 4,510 | 06:04:44 | Legacy unprovenanced coordinates; no sidecar | No |
| `tennis_02` | 2,421 / 1,951 | 06:48:34 | Legacy unprovenanced coordinates; no sidecar | No |
| `tennis_03` | 5,610 / 3,392 | 07:30:24 | Legacy unprovenanced coordinates; no sidecar | No |
| `tennis_04` | 7,492 / 3,789 | 07:31:13 | Legacy unprovenanced coordinates; no sidecar | No |
| `tennis_05` | 4,303 / 2,905 | 07:39:12 | Legacy unprovenanced coordinates; no sidecar | No |

All five writes predate `f16b3863a` (`2026-09-01T15:32:50Z`), which stopped
the tennis adapter reusing a previous homography when the current frame lacked
an accepted solve. Before that fix, emitted rows carry neither a declaration
nor provenance that can distinguish a fresh solve from a carried matrix. G42
measured that carried calibration could dominate the old regime. The current
adapter already calls `stamp_court_space_rows` for its validated output, so
there is no missing current producer declaration to change.

For each target, no source asset was found in the checked live pod locations
`data/footage_corpus/` or `data/videos/`, and no sidecar exists beside the CSV.
Therefore retroactive declaration cannot be validated from pixels or retained
calibration evidence. This is **not** a claim that target footage was
unsolvable: no table is judged unrepairable because of a footage solve failure,
so the spec's conditional footage eye-check rule does not apply. Source absence
prevents an eye check and is an explicit limit below, not a solve-failure label.

## Repair decision and measured result

No repair was made. The valid producer behavior already exists for new output;
backfilling legacy CSVs would fabricate a coordinate declaration. The final
second read-only census is recorded in the CSV and is the measured after count.

## VERIFIER_CONTRACT self-check

This memo follows [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including A7
and section B.

### A

- **A1:** No code changed; no new per-file test exists.
- **A2:** The denominator was recomputed from all 16 source directories, not
  inferred from G109. The committed census names its measurement times and
  counts.
- **A3:** The decision set is exhaustive. No render claim is used; no target
  source frame remains and no footage-solvability judgment is made from that.
- **A4:** The unit is one canonical source-table directory. All 16 are distinct,
  including each `g89_tennis_*` table once.
- **A5:** Evidence only: no field or reader changed.
- **A6:** This is an explicit-path evidence commit in `a2`; archive landing,
  ledger/register changes, and deployment remain verifier work.
- **A7:** Before reporting, every repository path named here is checked: this
  memo; both `g114_tennis_declare` CSVs; G109; G42; G47; G57; the G114 spec;
  and `VERIFIER_CONTRACT.md`.

### B

- **B1:** Clear. The complete 16-directory population and five targets are
  named before the no-repair decision; no failure is excluded.
- **B2:** Clear. No schema, field, status, reader, or code changed.
- **B3:** Clear. Missing coordinate evidence remains an explicit blocker.
- **B4:** Clear. No claim, queue, retry, or ownership code changed.
- **B5:** Clear. Pod interaction only read existing files and streamed stdout;
  no copy, deploy, restart, kill, re-track, or pod artifact occurred.
- **B6:** Clear. No module, import, command, or test was moved or retired.
- **B7:** Clear. This is an exhaustive table census, not head-slice evidence.
- **B8:** Clear. No fitted model or residual is claimed.
- **B9:** Clear. The denominator is distinct source-table directories, not rows,
  frames, or track IDs.
- **B10:** Clear. No bar, threshold, contract, rung, or verdict changed.

## NOT VERIFIED

- Whether a target footage frame had a valid fresh solve: source assets are
  absent from checked pod stores, so no pixel eye check or revalidation exists.
- Whether a source archive exists outside `data/footage_corpus/` and
  `data/videos/`.
- The mechanism or time of the `tennis_07` corpus update; only its current table
  contents are measured.
- Any quality or jump outcome after a hypothetical valid re-track. None ran.
- No focused test ran because no code changed; no full test suite ran.
