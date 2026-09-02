# G108 corpus relabel and G47 recompute

**Verdict: ACCEPT WITH CORRECTIONS.** This remediation follows
`docs/evidence/tracking/VERIFIER_CONTRACT.md`, including A7 and the B1-B10
self-check below. Four association-soccer clips were relabelled from football
without changing their content or tracking tables. The corrected G47 snapshot
is football **26/38** (was 30/42) and soccer **19/29** (was 15/25).

## Scope and label of record

G99 eye-audited all 66 clips at three interior frames each. Its labels and
contact sheets `clip_002.jpg`, `clip_004.jpg`, `clip_005.jpg`, and
`clip_006.jpg` identify these four as association soccer; this remediation did
not repeat that eye check.

Before correction, the label lived in three current pod records for every
clip:

1. the outer corpus filename prefix, `football__{game_id}.mp4`;
2. the report directory and embedded report property,
   `data/tracking_reports/football/{game_id}.json` and `sport=football`;
3. the matching `data/tracking/track_daemon_ledger.jsonl` row, including its
   sport-specific coordinate-contract diagnostic.

All three records now carry soccer. There were no matching files in the live
stage, no current queue entry, and no bridge ledger or retained historic queue
record. The preserved `data/tracking/{game_id}/tracking_data.csv` tables have
no sport field and were deliberately not renamed or rewritten: their historic
game IDs and unchanged rows are the evidence of what the wrong routing
produced.

The correction was an atomic rename of exactly these four corpus files plus
their report moves and four ledger-row edits. It did not move a clip into the
stage directory, re-download, re-track, change the coordinate contract, or
change a harness threshold. The before and after content SHA-256 values are
identical and are recorded in
`g108_relabel/correction_manifest.json`.

## G47 snapshot recomputation

This corrects the fixed G47 point-in-time census, not the later-changing live
report tree. G47's four affected reports were all named football
coordinate-contract-only rejections. Reclassifying the same four reports gives
the following direct arithmetic:

| Sport | G47 before | Reclassified reports | Corrected G47 after |
|---|---:|---:|---:|
| football | 30 / 42 | minus 4 / minus 4 | **26 / 38** |
| soccer | 15 / 25 | plus 4 / plus 4 | **19 / 29** |

The denominator change is only the four named reports; no row is excluded and
the combined football-plus-soccer count remains 45/67. Football is **not** the
largest single contract-rejection block after correction: baseball remains 66,
while football is 26 and soccer is 19. Football remains larger than soccer,
but that is a different claim.

The live report tree continued to receive unrelated reports after G47's 187
report snapshot. Its post-correction counts are therefore not substituted for
the historical metric: at verification it contained 195 reports, with football
26 contract-only reports in 38 files and soccer 20 contract-only reports in 30
files. The one additional soccer contract-only report is outside G47's frozen
25-report soccer denominator.

## Four verdict rescoring results

Each original report was a football coordinate-contract rejection. The existing
tracking CSV was then evaluated once with the unchanged soccer harness profile;
no video was decoded and no tracking table was regenerated. All four remained
coordinate-contract rejections, as measured rather than assumed.

| Game ID | G99 sheet | Before | After |
|---|---|---|---|
| `football_34GmmlakBYU` | `clip_002.jpg` | FAIL: `coordinate_contract`, football `image_px` | FAIL: `coordinate_contract`, soccer `image_px` |
| `football_B7znSVfBnM4` | `clip_004.jpg` | FAIL: `coordinate_contract`, football `image_px` | FAIL: `coordinate_contract`, soccer `image_px` |
| `football_gek9fXGlwas` | `clip_005.jpg` | FAIL: `coordinate_contract`, football `image_px` | FAIL: `coordinate_contract`, soccer `image_px` |
| `football_h-_3BmAh9po` | `clip_006.jpg` | FAIL: `coordinate_contract`, football `image_px` | FAIL: `coordinate_contract`, soccer `image_px` |

The full old/new labels, report locations, verdict heads, and unchanged content
hashes are durable in `g108_relabel/correction_manifest.json`. The result is
consistent with G91 and G101: this corpus does not presently provide a justified
soccer coordinate representation. It is not a soccer tracking-quality score.

## Recurrence prevention proposal

At acquisition, require the queue producer to store an explicit canonical sport
value from the source's own taxonomy: `american_football` maps to the existing
football adapter and `association_football` maps to soccer before the bridge
forms `{sport}__{game_id}`. A bare source category of `football` must remain
reviewable rather than being silently mapped by a detector; detectors are chosen
from this label and cannot independently validate it. This is not implemented
here because the historic queue/source-title records are absent and the current
queue producer that created them cannot be identified from the retained state.
Adding an ungrounded mapping or rejecting all current football entries would be
a broader acquisition change, not the small correction G108 authorizes.

## NOT VERIFIED

- The original source titles, historic queue rows, and the exact source naming
  collision are not retained, so collision remains suspected rather than proved.
- No future queue-builder enforcement was deployed or tested.
- No clip was re-tracked and no soccer `court_feet`/metric representation or
  tracking-quality verdict was produced.
- The post-G47 live report arrivals were not backdated into the fixed G47
  snapshot arithmetic.

## Verifier self-check

### A2-A7

- **A2:** `correction_manifest.json` independently exposes all four moved
  units and the input arithmetic: 30-4=26, 42-4=38, 15+4=19, and 25+4=29.
- **A3:** no renders support the correction metric; G99's complete 66-clip,
  three-interior-frame audit is cited instead of a new sample.
- **A4:** the manifest has four unique `game_id` values and four distinct
  content hashes.
- **A5:** readers of the changed daemon-ledger sport field were grepped
  (`night_report.py` is the consumer); report readers were grepped across the
  report tree. The correction preserves the existing JSON schema and moves the
  report to the directory matching its embedded `sport`, so no reader contract
  changes.
- **A6:** this lane committed only its explicit local evidence paths; landing,
  archive, RESULTS_LEDGER, and register updates are verifier actions in master.
- **A7:** all named repository evidence paths were checked immediately before
  commit: this memo, `g108_relabel/correction_manifest.json`, G108 spec,
  verifier contract, G99 memo and labels CSV, plus G99 sheets `clip_002.jpg`,
  `clip_004.jpg`, `clip_005.jpg`, and `clip_006.jpg`.

### Section B

- **B1:** all four moved reports are named and retained in the arithmetic; no
  failed row was excluded.
- **B2:** no schema or status value changed; report JSON remains in the same
  schema and its directory agrees with its existing `sport` property.
- **B3:** no gate behavior changed.
- **B4:** no claim, queue, or retry ownership path changed.
- **B5:** no source module or deployment was copied to the pod; a bounded
  inline evaluation used existing CSVs only.
- **B6:** no module moved or retired.
- **B7:** this is a four-clip correction, not a render sample; the cited G99
  evidence used three interior frames for every corpus clip.
- **B8:** no fitted residual is presented as independent evidence.
- **B9:** units are four distinct game IDs and their content hashes, not reused
  frames or track IDs; G47 denominators remain report files.
- **B10:** no harness threshold, gate value, or coordinate-contract value moved.
