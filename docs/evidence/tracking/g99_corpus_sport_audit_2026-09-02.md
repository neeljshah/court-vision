# G99 Corpus Sport-Label Audit

**Date:** 2026-09-02
**Verdict:** ACCEPT WITH CORRECTIONS - four current corpus clips are football-labelled association-soccer footage.
**Contract:** `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections A and B.

## Scope and method

This is a data-integrity census only. It did not rename, move, delete, re-track,
or otherwise modify a source clip, queue, adapter, threshold, coordinate contract,
or existing verdict.

A read-only live listing of `/workspace/nba-ai-system/data/footage_corpus` found
**66** `.mp4` clips, rather than the row's starting 63: football 9, KBO 12, MLB
13, NCAA basketball 6, NPB 6, soccer 6, tennis 9, WNBA 5. The three additions
are `kbo_2WqtNa-uUZU`, `mlb_231Mmqijar8`, and `soccer_cS4OpYJ0Pps`.

For each file, a read-only pod process decoded frames at 20%, 50%, and 80% of
its frame range, JPEG-encoded the three-frame sheet in memory, and streamed it
to this local evidence directory. This is a full clip census with three interior
samples per clip, not a head slice. No classifier or detector selected a sport.
Exact frame indices, frame counts, and paths are in
`g99_corpus_audit/sample_manifest.json`; the human eye labels are in
`g99_corpus_audit/audit_labels.csv`.

The actual-sport taxonomy intentionally retains the corpus's league-level
categories (`kbo`, `mlb`, `npb`, `ncaa_basketball`, `wnba`). Baseball and
basketball studio, replay, data, and game-programming views are assigned the
sport they visibly cover; they are not cross-label errors merely because a
sample is not live play.

## Result

**4 of 66 clips differ from their label.** All four are football-labelled and
visibly show association soccer. They reproduce G95's four-of-nine finding; no
additional sport-category discrepancy appeared in the other 57 clip reviews.

### Full confusion table: labelled category x actual category

| Labelled \ actual | football | kbo | mlb | ncaa_basketball | npb | soccer | tennis | wnba | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| football | 5 | 0 | 0 | 0 | 0 | 4 | 0 | 0 | 9 |
| kbo | 0 | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 12 |
| mlb | 0 | 0 | 13 | 0 | 0 | 0 | 0 | 0 | 13 |
| ncaa_basketball | 0 | 0 | 0 | 6 | 0 | 0 | 0 | 0 | 6 |
| npb | 0 | 0 | 0 | 0 | 6 | 0 | 0 | 0 | 6 |
| soccer | 0 | 0 | 0 | 0 | 0 | 6 | 0 | 0 | 6 |
| tennis | 0 | 0 | 0 | 0 | 0 | 0 | 9 | 0 | 9 |
| wnba | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 5 |
| Total | 5 | 12 | 13 | 6 | 6 | 10 | 9 | 5 | 66 |

### Mislabel origin and timing

| Exact game_id | Actual | Observed label source | Timing conclusion |
|---|---|---|---|
| `football_34GmmlakBYU` | soccer | Corpus filename `football__football_34GmmlakBYU.mp4` has two football prefixes; daemon ledger has `sport=football`. | Acquisition-time category assignment is supported; later daemon corruption is not. Historic queue row is absent. |
| `football_B7znSVfBnM4` | soccer | Corpus filename `football__football_B7znSVfBnM4.mp4` has two football prefixes; daemon ledger has `sport=football`. | Acquisition-time category assignment is supported; later daemon corruption is not. Historic queue row is absent. |
| `football_gek9fXGlwas` | soccer | Corpus filename `football__football_gek9fXGlwas.mp4` has two football prefixes; daemon ledger has `sport=football`. | Acquisition-time category assignment is supported; later daemon corruption is not. Historic queue row is absent. |
| `football_h-_3BmAh9po` | soccer | Corpus filename `football__football_h-_3BmAh9po.mp4` has two football prefixes; daemon ledger has `sport=football`. | Acquisition-time category assignment is supported; later daemon corruption is not. Historic queue row is absent. |

The bridge stages a file as `{sport}__{game_id}` and the daemon derives its
sport from that prefix before selecting its adapter. The matching filenames and
ledger rows show the bad category existed before daemon processing. The current
pod and worktree retain neither the historic football queue nor matching bridge
ledger entries. Thus association soccer being called “football” at source is a
**suspected** naming collision, not a proven repository defect; checking its
original titles/queue rows belongs to separate acquisition remediation.

## Published numbers exposed, not recomputed here

- G47's labelled-football contract-rejection result, **30/42**, is not a
  football-only count: four clips in that group are soccer. Its “largest single
  block” statement is invalidated until a clean-corpus recomputation.
- G47's labelled-soccer result, **15/25**, is not a complete soccer population:
  four observed soccer clips were omitted into the football group. This row
  does not recompute either corrected number.
- The four named per-clip harness verdicts were routed/interpreted as football;
  their daemon rows carry football coordinate-contract failures. Their sport
  conclusions are exposed pending separate remediation and rerun.
- Bridge lane accounting is exposed for these four football-prefixed files.
- G95 retained these clips in its denominator (48/108 surveyed frames) and
  already documented the correction. Its football visibility shares must not
  be cited as football-only calibration evidence; no G95 metric is recomputed.

## Evidence

- `docs/evidence/tracking/g99_corpus_audit/audit_labels.csv`
- `docs/evidence/tracking/g99_corpus_audit/sample_manifest.json`
- `docs/evidence/tracking/g99_corpus_audit/clip_001.jpg` through `clip_066.jpg`
- `docs/evidence/tracking/g99_corpus_audit/review_*.jpg` (review boards used
  to examine all contact sheets)

## NOT VERIFIED

- Exact historical queue rows, source URLs/titles, and bridge log entries for
  the four mismatches are not retained in either observed environment. The
  source-naming-collision explanation is suspected, not proved.
- This is a 66-clip snapshot. Later bridge arrivals are outside this census.
- The 184-game daemon-ledger population was not re-audited. No harness result,
  threshold, coordinate representation, or score was recomputed.
- No remediation was performed; all source files remain under original names.

## Verifier self-check

### A7 evidence paths

Before commit, check the memo, G99 spec, verifier contract, G95 and G47 source
memos, labels CSV, manifest, every manifest-declared contact sheet, and every
`review_*.jpg` path. Any missing listed path makes this result NOT VALIDATED.

### Section B

- **B1:** All 66 listed clips are retained; the four mismatches are named.
- **B2:** All artifacts are additive evidence; no schema, reader, or status changed.
- **B3:** No gate behavior changed.
- **B4:** No claim, queue, ownership, or failure path changed.
- **B5:** Pod frames were decoded and encoded in memory only; no pod source,
  code, deploy, daemon, queue, or artifact was written.
- **B6:** No module moved or retired.
- **B7:** Every clip provides 20/50/80-percent interior samples; no head slice.
- **B8:** No fitted transform or residual is evidence here.
- **B9:** The denominator is 66 distinct corpus file paths, once each in both
  manifest and labels; frames and alternate resolutions are not substituted.
- **B10:** No threshold, gate, adapter mapping, or coordinate contract changed.
